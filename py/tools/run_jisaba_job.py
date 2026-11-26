#!/usr/bin/env python3
"""「自鯖のある生活」の自動生成ジョブ（1回実行して終わる）。

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
from job_common import build_word_sheet, fetch_latest_article, load_blog_used, load_json, log, make_excerpt, probe_duration_sec, program_artwork, run, save_blog_used, save_podcast_episode  # noqa: E402
SLOTS = {"12": ("12時", "こんにちは"), "15": ("15時", "こんにちは"),
         "18": ("18時", "こんばんは"), "21": ("21時", "こんばんは")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=sorted(SLOTS),
                    help="放送枠 (12/15/18/21)")
    args = ap.parse_args()
    time_str, greeting = SLOTS[args.slot]

    out_dir = Path(os.environ.get("PROGRAM_OUT_DIR", "/data/output"))
    state_file = Path(os.environ.get(
        "PROGRAM_STATE_FILE", "/data/state/jisaba_state.json"))
    work = Path(os.environ.get(
        "PROGRAM_WORK_DIR", "/data/state/jisaba_work")) / args.slot
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    topics_path = Path(os.environ.get(
        "PROGRAM_TOPICS", "/data/state/jisaba_topics.json"))
    if not topics_path.exists():
        seed = load_json(TOOLS / "jisaba_topics.json", [])
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

    sheet_path = work / "word_sheet.json"
    build_word_sheet(topics, article, sheet_path, "jisaba-common.md")

    trial_dir = work / "trial"
    cmd = [sys.executable, "tools/make_jisaba.py",
           "--out-dir", str(trial_dir),
           "--topics-json", str(topics_path_out),
           "--article-json", str(article_path),
           "--extra-dict", str(sheet_path)]
    run(cmd, PY_DIR)
    mp3 = out_dir / f"program_{args.slot}_latest.mp3"
    synth_cmd = [sys.executable, "tools/synthesize_program.py",
                 str(trial_dir / "jisaba_program_fixed.txt"),
                 "--out", str(mp3),
                 "--title", "自鯖のある生活",
                 "--artist", "ねるるの日常(健全版)",
                 # ジングルは本編より少し大きめに聞こえるので 15% 下げる
                 "--jingle-volume", "0.85"]
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
    # イントロ/アウトロは番組フォルダ (jisaba/) にあれば付ける
    if bgm_base is not None:
        intro = bgm_base / "jisaba" / "intro.mp3"
        if intro.exists():
            synth_cmd += ["--intro", str(intro)]
            log("intro: jisaba/intro.mp3")
        outro = bgm_base / "jisaba" / "outro.mp3"
        if outro.exists():
            synth_cmd += ["--outro", str(outro)]
            log("outro: jisaba/outro.mp3")
    # 番組アートワークがあれば、カバーアートとして埋め込む
    art = program_artwork("jisaba")
    if art is not None:
        synth_cmd += ["--artwork", str(art)]
        log(f"artwork: {art.name}")
    run(synth_cmd, PY_DIR)

    # サイト表示用のサイドカー JSON (MP3 と同名で隣に上書き)。
    # 音声化が成功したときだけ書くので、内容は常に最新の放送と一致する
    sidecar = {
        "kind": "jisaba",
        "program": "自鯖のある生活",
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
    sidecar_path = out_dir / f"program_{args.slot}_latest.json"
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False,
                                       indent=2), encoding="utf-8")
    log(f"sidecar: {sidecar_path.name}")

    # ポッドキャスト用に、日付入りの固定名でも保存する
    desc_lines = ["お題: " + " / ".join(topics)]
    if article.get("title"):
        desc_lines.append(f"ブログピックアップ: {article['title']}")
    save_podcast_episode(mp3, sidecar, "\n".join(desc_lines))

    state["next_index"] = (idx + 3) % len(pool)
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
