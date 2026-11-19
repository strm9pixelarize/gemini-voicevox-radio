#!/usr/bin/env python3
"""長編番組の自動生成ジョブ（1回実行して終わる）。

run_scheduler.py から放送枠の10分前に呼ばれ、次の一連を行う:
  1. お題プールから次の3件を選ぶ（ローテーション、状態ファイルで管理）
  2. ブログの最新記事を取得する（失敗したら同梱の予備記事を使う）
  3. 単語シートを作る（新出単語の読みを LLM に自動で付けさせる）
  4. make_program.py で原稿を生成する
  5. synthesize_program.py で音声化し、output に program_<枠>_latest.mp3 を置く

環境変数:
  PROGRAM_OUT_DIR    出力先 (既定 /data/output)
  PROGRAM_STATE_FILE 状態ファイル (既定 /data/state/program_state.json)
  PROGRAM_WORK_DIR   作業ディレクトリ (既定 /data/state/program_work)
  PROGRAM_TOPICS     お題プール (既定 /data/state/program_topics.json、
                     無ければ tools/program_topics.json から種をコピー)
  BLOG_URL           ブログの URL (既定 https://blog.architectural-n.net)
  ANTHROPIC_API_KEY  make_program が直接 API を叩くために使う
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PY_DIR = TOOLS.parent
SLOTS = {"12": ("12時", "こんにちは"), "15": ("15時", "こんにちは"),
         "18": ("18時", "こんばんは"), "21": ("21時", "こんばんは")}


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fetch_latest_article(blog_url: str) -> dict:
    """ブログの一覧から最新記事を取り、タイトル・日付・本文を返す。"""
    def get(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "radio-job"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    index = get(blog_url.rstrip("/") + "/")
    m = re.search(r'href="(/posts/[^"]+\.html)"', index)
    if not m:
        raise RuntimeError("article link not found in blog index")
    page = get(blog_url.rstrip("/") + m.group(1))
    title_m = re.search(r"<title>([^<]+)</title>", page)
    title = (title_m.group(1).split("|")[0].strip() if title_m else "ブログ記事")
    date_m = re.search(r"(20\d\d-\d\d-\d\d)", page)
    texts: list[str] = []

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_p = False

        def handle_starttag(self, tag, attrs):
            if tag == "p":
                self.in_p = True

        def handle_endtag(self, tag):
            if tag == "p":
                self.in_p = False
                texts.append("\n")

        def handle_data(self, data):
            if self.in_p:
                texts.append(data)

    P().feed(page)
    content = "".join(texts).strip()
    if len(content) < 100:
        raise RuntimeError("article body too short")
    return {"title": title, "date": date_m.group(1) if date_m else "",
            "content": content}


def build_word_sheet(topics: list[str], article: dict, out_path: Path) -> None:
    """記事とお題から新出の英字単語を抜き、読みを LLM に付けさせて保存する。"""
    sys.path.insert(0, str(TOOLS))
    import gadget_check as gc
    import make_program as mp

    source = "\n".join(topics) + "\n" + article.get("content", "")
    blocks = gc.parse_common(str(PY_DIR.parent / "prompts/parts/gadget-common.md"))
    entries, _ = gc.dict_from_common(blocks)
    known = {t for t, _ in entries}
    cands = set()
    for m in re.finditer(r"[A-Za-z]+(?:[-.][A-Za-z0-9]+)*|\d+(?:\.\d+)?[A-Za-z]+",
                         source):
        tok = m.group(0)
        if len(tok) >= 2 and tok not in known:
            cands.add(tok)
    sheet = []
    if cands:
        lines = source.splitlines()
        items = []
        for w in sorted(cands):
            hit = next((ln for ln in lines if w in ln), topics[0])
            items.append(f"- {w}（使用例: {hit[:80]}）")
        prompt = mp.RESOLVE_PROMPT.replace("{単語リスト}", "\n".join(items))
        data = json.loads(mp.strip_fence(mp.call_llm(prompt, 2000)))
        readings = {str(d.get("term", "")): str(d.get("kana", ""))
                    for d in data if isinstance(d, dict)}
        for w in sorted(cands):
            kana = readings.get(w, "")
            ok = bool(kana) and re.fullmatch(r"[ァ-ヶー・]+", kana)
            sheet.append({"term": w, "kana": kana if ok else "",
                          "status": "auto" if ok else "blank"})
    out_path.write_text(json.dumps(sheet, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    log(f"word sheet: {len(sheet)} terms "
        f"({sum(1 for s in sheet if s['status'] == 'blank')} blank)")


def run(cmd: list[str], cwd: Path) -> None:
    log("run: " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout[-3000:], flush=True)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr[-2000:], flush=True)
        raise RuntimeError(f"command failed rc={proc.returncode}: {cmd[1]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=sorted(SLOTS),
                    help="放送枠 (12/15/18/21)")
    args = ap.parse_args()
    time_str, greeting = SLOTS[args.slot]

    out_dir = Path(os.environ.get("PROGRAM_OUT_DIR", "/data/output"))
    state_file = Path(os.environ.get(
        "PROGRAM_STATE_FILE", "/data/state/program_state.json"))
    work = Path(os.environ.get(
        "PROGRAM_WORK_DIR", "/data/state/program_work")) / args.slot
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    topics_path = Path(os.environ.get(
        "PROGRAM_TOPICS", "/data/state/program_topics.json"))
    if not topics_path.exists():
        seed = load_json(TOOLS / "program_topics.json", [])
        topics_path.parent.mkdir(parents=True, exist_ok=True)
        topics_path.write_text(json.dumps(seed, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    pool = load_json(topics_path, [])
    if len(pool) < 3:
        raise RuntimeError("topic pool needs at least 3 entries")

    state = load_json(state_file, {"next_index": 0})
    idx = int(state.get("next_index", 0)) % len(pool)
    topics = [pool[(idx + k) % len(pool)] for k in range(3)]
    log(f"slot {args.slot}: topics={topics}")

    blog_url = os.environ.get("BLOG_URL", "https://blog.architectural-n.net")
    try:
        article = fetch_latest_article(blog_url)
        log(f"article: {article['title']} ({article['date']})")
    except Exception as e:
        log(f"blog fetch failed ({e}); using fallback article")
        article = load_json(TOOLS / "fallback_article.json", {})
    article_path = work / "article.json"
    article_path.write_text(json.dumps(article, ensure_ascii=False),
                            encoding="utf-8")
    topics_json = {"topics": topics, "time": time_str, "greeting": greeting}
    topics_path_out = work / "topics.json"
    topics_path_out.write_text(json.dumps(topics_json, ensure_ascii=False),
                               encoding="utf-8")

    sheet_path = work / "word_sheet.json"
    build_word_sheet(topics, article, sheet_path)

    trial_dir = work / "trial"
    run([sys.executable, "tools/make_program.py",
         "--out-dir", str(trial_dir),
         "--topics-json", str(topics_path_out),
         "--article-json", str(article_path),
         "--extra-dict", str(sheet_path)], PY_DIR)
    mp3 = out_dir / f"program_{args.slot}_latest.mp3"
    synth_cmd = [sys.executable, "tools/synthesize_program.py",
                 str(trial_dir / "gadget_program_fixed.txt"),
                 "--out", str(mp3)]
    # BGM は assets/neruru_bgm フォルダの曲をローテーションで使う
    # (無ければ声のみ)。曲を増やすときはフォルダにファイルを足すだけ。
    # コンテナでは assets は /data/assets にマウントされる (compose 参照)。
    # PROGRAM_BGM_DIR でフォルダごと上書きもできる
    bgm_dirs = [PY_DIR.parent / "assets" / "neruru_bgm",
                Path("/data/assets/neruru_bgm")]
    if os.environ.get("PROGRAM_BGM_DIR"):
        bgm_dirs.insert(0, Path(os.environ["PROGRAM_BGM_DIR"]))
    bgm_base = next((d for d in bgm_dirs if d.is_dir()), None)
    tracks: list[Path] = []
    if bgm_base is not None:
        tracks = sorted(
            p for p in bgm_base.iterdir()
            if p.is_file() and p.suffix.lower() == ".mp3")
    if tracks:
        bgm_idx = int(state.get("bgm_index", 0)) % len(tracks)
        synth_cmd += ["--bgm", str(tracks[bgm_idx])]
        state["bgm_index"] = bgm_idx + 1
        log(f"bgm: {tracks[bgm_idx].name} ({bgm_idx + 1}/{len(tracks)})")
    # イントロ/アウトロは番組フォルダ (gadget_mania/) にあれば付ける
    if bgm_base is not None:
        intro = bgm_base / "gadget_mania" / "intro.mp3"
        if intro.exists():
            synth_cmd += ["--intro", str(intro)]
            log("intro: gadget_mania/intro.mp3")
        outro = bgm_base / "gadget_mania" / "outro.mp3"
        if outro.exists():
            synth_cmd += ["--outro", str(outro)]
            log("outro: gadget_mania/outro.mp3")
    run(synth_cmd, PY_DIR)

    state["next_index"] = (idx + 3) % len(pool)
    state["last_slot"] = args.slot
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    log(f"done: {mp3}")


if __name__ == "__main__":
    main()
