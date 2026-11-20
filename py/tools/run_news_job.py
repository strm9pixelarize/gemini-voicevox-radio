#!/usr/bin/env python3
"""ニュース番組「ネルラジニュース」の自動生成ジョブ（1回実行して終わる）。

run_scheduler.py から放送枠の10分前に呼ばれ、次の一連を行う:
  1. make_news.py で最新ニュースの原稿を生成する
     （深堀りは当日に使ったタイトルを避け、毎回新しい話題にする）
  2. synthesize_program.py で音声化し、output に news_<枠>_latest.mp3 を置く

環境変数:
  NEWS_OUT_DIR    出力先 (既定 PROGRAM_OUT_DIR、それも無ければ /data/output)
  NEWS_STATE_FILE 状態ファイル (既定 /data/state/news_state.json)
  NEWS_WORK_DIR   作業ディレクトリ (既定 /data/state/news_work)
  ANTHROPIC_API_KEY  make_news が直接 API を叩くために使う
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PY_DIR = TOOLS.parent
SLOTS = {"10": "午前10時", "11": "午前11時", "13": "午後1時",
         "14": "午後2時", "16": "午後4時", "17": "午後5時",
         "19": "午後7時", "20": "午後8時", "22": "午後10時"}


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=sorted(SLOTS),
                    help="放送枠 (10/11/13/14/16/17/19/20/22)")
    args = ap.parse_args()

    out_dir = Path(os.environ.get(
        "NEWS_OUT_DIR", os.environ.get("PROGRAM_OUT_DIR", "/data/output")))
    state_file = Path(os.environ.get(
        "NEWS_STATE_FILE", "/data/state/news_state.json"))
    work = Path(os.environ.get(
        "NEWS_WORK_DIR", "/data/state/news_work")) / args.slot
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    state = load_json(state_file, {"date": today, "used_deep": []})
    if state.get("date") != today:
        state = {"date": today, "used_deep": []}
    exclude_path = work / "exclude.json"
    exclude_path.write_text(json.dumps(state["used_deep"],
                                       ensure_ascii=False), encoding="utf-8")
    chosen_path = work / "chosen.json"

    trial_dir = work / "trial"
    run([sys.executable, "tools/make_news.py",
         "--out-dir", str(trial_dir),
         "--time-label", SLOTS[args.slot],
         "--exclude-file", str(exclude_path),
         "--chosen-file", str(chosen_path)], PY_DIR)

    chosen = load_json(chosen_path, [])
    state["used_deep"] = sorted(set(state["used_deep"]) | set(chosen))
    state["last_slot"] = args.slot
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False),
                          encoding="utf-8")
    log(f"deep-dives used today: {len(state['used_deep'])}")

    mp3 = out_dir / f"news_latest.mp3"
    run([sys.executable, "tools/synthesize_program.py",
         str(trial_dir / "news_program.txt"),
         "--out", str(mp3),
         "--title", "ネルラジニュース",
         "--artist", "ねるるの日常(健全版)"], PY_DIR)
    log(f"done: {mp3}")


if __name__ == "__main__":
    main()
