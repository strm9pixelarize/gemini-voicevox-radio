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

sys.path.insert(0, str(TOOLS))
from job_common import build_word_sheet, fetch_latest_article, load_blog_used, load_json, log, make_excerpt, probe_duration_sec, run, save_blog_used, save_podcast_episode  # noqa: E402
SLOTS = {"12": ("12時", "こんにちは"), "15": ("15時", "こんにちは"),
         "18": ("18時", "こんばんは"), "21": ("21時", "こんばんは")}


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
            "content": content}


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
    build_word_sheet(topics, article, sheet_path, "gadget-common.md", extra_text=extra_text)

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
