#!/usr/bin/env python3
"""長編番組の自動生成ジョブ（1回実行して終わる）。

run_scheduler.py から放送枠の10分前に呼ばれ、次の一連を行う:
  1. お題プールから次の3件を選ぶ（ローテーション、状態ファイルで管理）
  2. ブログの最新記事を取得する（失敗したら同梱の予備記事を使う）
  3. 単語シートを作る（新出単語の読みを LLM に自動で付けさせる）
  4. make_program.py で原稿を生成する
  5. synthesize_program.py で音声化し、output に program_<枠>_latest.mp3 を置く
  6. サイト表示用に program_<枠>_latest.json (話題3件とブログピックアップ)
     も MP3 の隣に置く (cast.architectural-n.net が読む)

環境変数:
  PROGRAM_OUT_DIR    出力先 (既定 /data/output)
  PROGRAM_STATE_FILE 状態ファイル (既定 /data/state/program_state.json)
  PROGRAM_WORK_DIR   作業ディレクトリ (既定 /data/state/program_work)
  PROGRAM_TOPICS     お題プール (既定 /data/state/program_topics.json、
                     無ければ tools/program_topics.json から種をコピー)
  BLOG_URL           ブログの URL (既定 https://blog.architectural-n.net)
  BLOG_USED_FILE     ブログピックアップの使用済みリスト
                     (既定 /data/state/blog_used.json、番組間で共有)
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


def fetch_latest_article(blog_url: str,
                         used: set[str] | None = None) -> tuple[dict, bool]:
    """ブログの一覧から、未読の最新記事を1本取る (AKIBAピックアップ方式)。

    一覧の並び順 (新しい順) に、used に無い最初の記事を選ぶ。全部使用
    済みなら最新記事に戻って新しい周回を始める。戻り値は
    (記事, 周回リセットしたか)。記事の形は {title, date, url, content}。
    """
    def get(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "radio-job"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    base = blog_url.rstrip("/")
    index = get(base + "/")
    links: list[str] = []
    for m in re.finditer(r'href="(/posts/[^"]+\.html)"', index):
        if m.group(1) not in links:
            links.append(m.group(1))
    if not links:
        raise RuntimeError("article link not found in blog index")
    used = used or set()
    fresh = [l for l in links if base + l not in used]
    reset = not fresh
    pick = fresh[0] if fresh else links[0]
    page = get(base + pick)
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
            "url": base + pick,
            "content": content}, reset


def blog_used_path() -> Path:
    return Path(os.environ.get("BLOG_USED_FILE",
                               "/data/state/blog_used.json"))


def load_blog_used() -> list[str]:
    """ブログピックアップの使用済み記事 URL (番組間で共有する)。"""
    data = load_json(blog_used_path(), [])
    return data if isinstance(data, list) else []


def save_blog_used(used: list[str]) -> None:
    """使用済みリストを保存する (直近200件だけ保持、AKIBA と同じ)。"""
    path = blog_used_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(used[-200:], ensure_ascii=False),
                    encoding="utf-8")


def fetch_friend_article(feed_url: str) -> dict:
    """友人のブログ (WordPress) の RSS から最新記事を1件取る。

    返す形は fetch_latest_article と同じ {title, date, url, content}。
    ブログピックアップの後半で、自分の記事の後に読むための素材。
    """
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    req = urllib.request.Request(feed_url,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    root = ET.fromstring(raw)
    item = root.find("./channel/item")
    if item is None:
        raise RuntimeError("no item in friend feed")

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1

        def handle_endtag(self, tag):
            if tag in ("script", "style") and self.skip:
                self.skip -= 1

        def handle_data(self, data):
            if not self.skip:
                self.parts.append(data)

    html = item.findtext(
        "{http://purl.org/rss/1.0/modules/content/}encoded") or ""
    if not html:
        html = item.findtext("description") or ""
    ex = TextExtractor()
    ex.feed(html)
    content = re.sub(r"\s+", " ", " ".join(ex.parts)).strip()
    if len(content) < 200:
        raise RuntimeError("friend article body too short")
    date = ""
    pub = item.findtext("pubDate")
    if pub:
        try:
            date = parsedate_to_datetime(pub).date().isoformat()
        except (TypeError, ValueError):
            date = ""
    return {"title": (item.findtext("title") or "").strip(),
            "date": date,
            "url": (item.findtext("link") or "").strip(),
            "content": content}, reset


def build_word_sheet(topics: list[str], article: dict, out_path: Path,
                     extra_text: str = "") -> None:
    """記事とお題から新出の英字単語を抜き、読みを LLM に付けさせて保存する。"""
    sys.path.insert(0, str(TOOLS))
    import gadget_check as gc
    import make_program as mp

    source = ("\n".join(topics) + "\n" + article.get("content", "")
              + "\n" + extra_text)
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
        # 候補が多いと応答が途中で切れて JSON が壊れる (アキバ本文が
        # 加わって候補が増えたため実際に発生)。予算を広げて再試行し、
        # それでも駄目なら単語シートなしで進める (原稿側にも自動解決
        # があるので、シートは無くても番組は作れる)
        data = []
        for budget in (3000, 6000):
            try:
                data = json.loads(mp.strip_fence(mp.call_llm(prompt, budget)))
                break
            except ValueError:
                log(f"word sheet: JSON parse failed (budget {budget}), "
                    "retrying" if budget == 3000 else
                    "word sheet: JSON parse failed; continuing without sheet")
                data = []
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


def probe_duration_sec(path: Path) -> float | None:
    """完成した MP3 の長さ (秒)。ffprobe が無い/失敗したら None。"""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)], capture_output=True, text=True,
            timeout=30)
        return round(float(proc.stdout.strip()), 1)
    except Exception:
        return None


def make_excerpt(text: str, limit: int = 120) -> str:
    """記事本文の冒頭を、表示用の抜粋 (1行、limit 字まで) に整える。"""
    flat = re.sub(r"\s+", " ", text or "").strip()
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "…"


def save_podcast_episode(mp3: Path, sidecar: dict, description: str) -> None:
    """ポッドキャスト用の固定名コピーを保存する (失敗しても続行)。"""
    try:
        sys.path.insert(0, str(TOOLS))
        from podcast_copy import save_episode
        save_episode(mp3, sidecar, description)
    except Exception as e:
        log(f"podcast: save failed ({e}); continuing")


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
    blog_used = load_blog_used()
    fetched_article = None
    blog_reset = False
    try:
        fetched_article, blog_reset = fetch_latest_article(
            blog_url, set(blog_used))
        log(f"article: {fetched_article['title']} ({fetched_article['date']})")
    except Exception as e:
        log(f"blog fetch failed ({e}); using fallback article")
    article = fetched_article or load_json(TOOLS / "fallback_article.json", {})
    article_path = work / "article.json"
    article_path.write_text(json.dumps(article, ensure_ascii=False),
                            encoding="utf-8")
    topics_json = {"topics": topics, "time": time_str, "greeting": greeting}
    topics_path_out = work / "topics.json"
    topics_path_out.write_text(json.dumps(topics_json, ensure_ascii=False),
                               encoding="utf-8")

    # AKIBAピックアップ用に、新製品ニュースを2本取る (失敗しても番組は作る)
    sys.path.insert(0, str(TOOLS))
    import akiba as akiba_mod

    akiba_arts: list[dict] = []
    akiba_path = work / "akiba.json"
    try:
        akiba_arts = akiba_mod.pick_with_bodies(set(state.get("akiba_used", [])))
        log(f"akiba: {[a['title'][:30] for a in akiba_arts]}")
    except Exception as e:
        log(f"akiba fetch failed ({e}); skipping corner")
    akiba_text = ""
    if akiba_arts:
        akiba_path.write_text(json.dumps(akiba_arts, ensure_ascii=False),
                              encoding="utf-8")
        akiba_text = "\n".join(a["title"] + "\n" + a["body"]
                               for a in akiba_arts)

    # 友人ブログの最新記事を取る (ブログピックアップの後半で読む。
    # 失敗しても番組は作る)
    friend: dict = {}
    friend_path = work / "friend.json"
    friend_feed = os.environ.get(
        "FRIEND_BLOG_FEED", "https://blog.caramelos.xyz/feed/")
    try:
        friend = fetch_friend_article(friend_feed)
        friend_path.write_text(json.dumps(friend, ensure_ascii=False),
                               encoding="utf-8")
        log(f"friend: {friend['title'][:30]}")
    except Exception as e:
        friend = {}
        log(f"friend fetch failed ({e}); skipping friend pickup")
    extra_text = akiba_text
    if friend:
        extra_text += "\n" + friend["title"] + "\n" + friend["content"]

    sheet_path = work / "word_sheet.json"
    build_word_sheet(topics, article, sheet_path, extra_text=extra_text)

    trial_dir = work / "trial"
    cmd = [sys.executable, "tools/make_program.py",
           "--out-dir", str(trial_dir),
           "--topics-json", str(topics_path_out),
           "--article-json", str(article_path),
           "--extra-dict", str(sheet_path)]
    if akiba_arts:
        cmd += ["--akiba-json", str(akiba_path)]
    if friend:
        cmd += ["--friend-json", str(friend_path)]
    run(cmd, PY_DIR)
    mp3 = out_dir / f"program_{args.slot}_latest.mp3"
    synth_cmd = [sys.executable, "tools/synthesize_program.py",
                 str(trial_dir / "gadget_program_fixed.txt"),
                 "--out", str(mp3),
                 "--title", "ガジェットマニア",
                 "--artist", "ねるるの日常(健全版)"]
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

    # サイト表示用のサイドカー JSON (MP3 と同名で隣に上書き)。
    # 音声化が成功したときだけ書くので、内容は常に最新の放送と一致する
    sidecar = {
        "kind": "gadget",
        "program": "ガジェットマニア",
        "slot": args.slot,
        "air_time": f"{args.slot}:00",
        "generated_at": datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "mp3": mp3.name,
        "duration_sec": probe_duration_sec(mp3),
        "topics": topics,
        "blog_pickup": {"title": article.get("title", ""),
                        "date": article.get("date", ""),
                        "url": article.get("url", ""),
                        "excerpt": make_excerpt(article.get("content", ""))},
    }
    if akiba_arts:  # AKIBAピックアップも表示用に載せる (コーナーが無い回はキー自体なし)
        sidecar["akiba_pickup"] = [
            {"title": a.get("title", ""), "url": a.get("link", ""),
             "excerpt": make_excerpt(a.get("body", ""))}
            for a in akiba_arts]
    if friend:  # 友人ブログピックアップも表示用に載せる
        sidecar["friend_pickup"] = {
            "blog_name": "エレクトロライフ",
            "title": friend.get("title", ""),
            "date": friend.get("date", ""),
            "url": friend.get("url", ""),
            "excerpt": make_excerpt(friend.get("content", ""))}
    sidecar_path = out_dir / f"program_{args.slot}_latest.json"
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False,
                                       indent=2), encoding="utf-8")
    log(f"sidecar: {sidecar_path.name}")

    # ポッドキャスト用に、日付入りの固定名でも保存する
    desc_lines = ["お題: " + " / ".join(topics)]
    if article.get("title"):
        desc_lines.append(f"ブログピックアップ: {article['title']}")
    if akiba_arts:
        desc_lines.append("AKIBAピックアップ: "
                          + " / ".join(a["title"] for a in akiba_arts))
    if friend:
        desc_lines.append(
            f"友人ブログピックアップ: {friend.get('title', '')}")
    save_podcast_episode(mp3, sidecar, "\n".join(desc_lines))

    state["next_index"] = (idx + 3) % len(pool)
    if akiba_arts:  # 使った記事は次回から選ばない (直近200件だけ保持)
        used_list = list(state.get("akiba_used", []))
        used_list += [a["link"] for a in akiba_arts]
        state["akiba_used"] = used_list[-200:]
    if fetched_article and fetched_article.get("url"):
        # 読んだ記事は次回から選ばない (番組間で共有、AKIBA と同じ流儀)
        if blog_reset:
            save_blog_used([fetched_article["url"]])
        else:
            save_blog_used(blog_used + [fetched_article["url"]])
        log(f"blog_used: {fetched_article['url']}")
    state["last_slot"] = args.slot
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    log(f"done: {mp3}")


if __name__ == "__main__":
    main()
