#!/usr/bin/env python3
"""ブログトークの自動生成ジョブ（1回実行して終わる）。

run_scheduler.py から平日の放送10分前に呼ばれ、次の一連を行う:
  1. ブログの記事一覧から、まだ取り上げていない記事を1本選ぶ
     （新しい順。使い切ったらローテーションをリセットする）
  2. make_blog_talk.py で座談会原稿を生成する
  3. synthesize_program.py で音声化し、output に
     blog_talk_latest.mp3 を置く（毎回上書き）

環境変数:
  BLOG_TALK_OUT_DIR    出力先 (既定 PROGRAM_OUT_DIR、それも無ければ /data/output)
  BLOG_TALK_STATE_FILE 状態ファイル (既定 /data/state/blog_talk_state.json)
  BLOG_TALK_WORK_DIR   作業ディレクトリ (既定 /data/state/blog_talk_work)
  BLOG_URL             ブログの URL (既定 https://blog.architectural-n.net)
  ANTHROPIC_API_KEY    make_blog_talk が直接 API を叩くために使う
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


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "radio-job"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch_article_paths(blog_url: str) -> list[str]:
    """ブログの一覧から記事パスを新しい順に集める。"""
    index = get(blog_url.rstrip("/") + "/")
    paths: list[str] = []
    for m in re.finditer(r'href="(/posts/[^"]+\.html)"', index):
        if m.group(1) not in paths:
            paths.append(m.group(1))
    if not paths:
        raise RuntimeError("article link not found in blog index")
    return paths


def fetch_article(blog_url: str, path: str) -> dict:
    """記事ページからタイトル・日付・本文を取り出す。"""
    page = get(blog_url.rstrip("/") + path)
    title_m = re.search(r"<title>([^<]+)</title>", page)
    title = (title_m.group(1).split("|")[0].strip()
             if title_m else "ブログ記事")
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
            "content": content, "url": blog_url.rstrip("/") + path}


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
    out_dir = Path(os.environ.get(
        "BLOG_TALK_OUT_DIR",
        os.environ.get("PROGRAM_OUT_DIR", "/data/output")))
    state_file = Path(os.environ.get(
        "BLOG_TALK_STATE_FILE", "/data/state/blog_talk_state.json"))
    work = Path(os.environ.get(
        "BLOG_TALK_WORK_DIR", "/data/state/blog_talk_work"))
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    blog_url = os.environ.get("BLOG_URL", "https://blog.architectural-n.net")

    state = load_json(state_file, {"used_urls": []})
    used = list(state.get("used_urls", []))

    article = None
    try:
        paths = fetch_article_paths(blog_url)
        fresh = [p for p in paths
                 if blog_url.rstrip("/") + p not in used]
        if not fresh:
            log("article pool exhausted; resetting rotation")
            used = []
            fresh = paths
        for path in fresh:
            try:
                article = fetch_article(blog_url, path)
                break
            except Exception as e:
                log(f"article fetch failed ({path}): {e}")
        if article is None:
            raise RuntimeError("no article could be fetched")
        log(f"article: {article['title']} ({article['date']})")
    except Exception as e:
        log(f"blog fetch failed ({e}); using fallback article")
        article = load_json(TOOLS / "fallback_article.json", {})
        article.setdefault("url", "")

    article_path = work / "article.json"
    article_path.write_text(json.dumps(article, ensure_ascii=False),
                            encoding="utf-8")

    trial_dir = work / "trial"
    run([sys.executable, "tools/make_blog_talk.py",
         "--out-dir", str(trial_dir),
         "--article-json", str(article_path)], PY_DIR)

    mp3 = out_dir / "blog_talk_latest.mp3"
    run([sys.executable, "tools/synthesize_program.py",
         str(trial_dir / "blog_talk_program.txt"),
         "--out", str(mp3)], PY_DIR)

    if article.get("url"):
        used.append(article["url"])
    state["used_urls"] = used
    state["last_title"] = article.get("title", "")
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False),
                          encoding="utf-8")
    log(f"done: {mp3}")


if __name__ == "__main__":
    main()
