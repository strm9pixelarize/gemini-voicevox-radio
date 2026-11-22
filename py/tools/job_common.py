#!/usr/bin/env python3
"""長編ランナー3本 (gadget / jisaba / blog) の共通部品。

元は各ランナーに複製されていた関数群をここに寄せた (2026-11-23)。
各関数の本体は複製時代から変更していない。build_word_sheet だけは、
番組ごとの共通プロンプト名 (gadget-common.md / jisaba-common.md) を
引数 common_file で受ける形に統一した。
"""
from __future__ import annotations

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


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def run(cmd: list[str], cwd: Path) -> None:
    log("run: " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout[-3000:], flush=True)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr[-2000:], flush=True)
        raise RuntimeError(f"command failed rc={proc.returncode}: {cmd[1]}")


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


def save_podcast_episode(mp3: Path, sidecar: dict, description: str) -> None:
    """ポッドキャスト用の固定名コピーを保存する (失敗しても続行)。"""
    try:
        sys.path.insert(0, str(TOOLS))
        from podcast_copy import save_episode
        save_episode(mp3, sidecar, description)
    except Exception as e:
        log(f"podcast: save failed ({e}); continuing")


def build_word_sheet(topics: list[str], article: dict, out_path: Path,
                     common_file: str, extra_text: str = "") -> None:
    """記事とお題から新出の英字単語を抜き、読みを LLM に付けさせて保存する。"""
    sys.path.insert(0, str(TOOLS))
    import gadget_check as gc
    import make_program as mp

    source = ("\n".join(topics) + "\n" + article.get("content", "")
              + "\n" + extra_text)
    blocks = gc.parse_common(str(PY_DIR.parent / "prompts/parts" / common_file))
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
