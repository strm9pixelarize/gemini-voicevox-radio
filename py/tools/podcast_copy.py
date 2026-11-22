#!/usr/bin/env python3
"""ポッドキャスト配信用に、完成した長編 MP3 を固定名で保存する。

各ジョブランナー (run_program_job / run_jisaba_job / run_blog_job) が
生成成功直後に save_episode() を呼ぶ。放送用は program_<枠>_latest.mp3 の
上書き方式だが、ポッドキャストのエピソードには消えない固定ファイルが
必要なため、日付入りの別名でコピーを残す。

保存先: <出力先>/podcast/<種別>/<YYYY-MM-DD>_<種別>_<枠>.mp3
  例: /data/output/podcast/gadget/2026-11-22_gadget_12.mp3
- ファイル名の番組名は種別 (gadget / jisaba / blog) で表す。日本語の
  番組名は ID3 タイトルとサイドカー JSON に入れる (AzuraCast 側で
  URL 化されるファイル名を ASCII に保つため)
- 同じ日に同じ枠が再生成されても同名へ上書きされ、エピソードは
  重複しない
- ID3 は ffmpeg の -metadata で付け直す (synthesize_program.py と
  同じ流儀)。artist は元の MP3 のものをそのまま引き継ぐ:
  title=「<番組名> <YYYY-MM-DD>」/ album=<番組名> / date=<YYYY-MM-DD>
- エピソード情報のサイドカー JSON を MP3 と同名で隣に置く
  (番組名・枠・生成時刻・尺・説明文)

環境変数:
  PODCAST_OUT_DIR  保存先ルート (既定は MP3 と同じ出力先の podcast/)
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}",
          flush=True)


def probe_duration_sec(path: Path) -> float | None:
    """MP3 の長さ (秒)。ffprobe が無い/失敗したら None。"""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)], capture_output=True, text=True,
            timeout=30)
        return round(float(proc.stdout.strip()), 1)
    except Exception:
        return None


def save_episode(mp3: Path, info: dict,
                 description: str = "") -> Path | None:
    """完成 MP3 をポッドキャスト用に保存し、保存先パスを返す。

    info は各ランナーが作るサイト表示用サイドカーと同じ dict で、
    kind / program / slot / generated_at / duration_sec を使う。
    失敗したら None を返してログに残す (放送ジョブは止めない)。
    """
    try:
        kind = str(info["kind"])
        program = str(info["program"])
        slot = str(info["slot"])
        generated_at = str(info.get("generated_at") or "")
        date = generated_at[:10] or f"{datetime.now():%Y-%m-%d}"
        title = f"{program} {date}"
        root = Path(os.environ.get("PODCAST_OUT_DIR",
                                   str(mp3.parent / "podcast")))
        dest_dir = root / kind
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = f"{date}_{kind}_{slot}"
        dest = dest_dir / f"{name}.mp3"
        tmp = dest_dir / f".{name}.tmp.mp3"
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
               "-c", "copy", "-id3v2_version", "3",
               "-metadata", f"title={title}",
               "-metadata", f"album={program}",
               "-metadata", f"date={date}",
               str(tmp)]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=600)
        if proc.returncode != 0:
            log(f"podcast: ffmpeg failed: {proc.stderr.strip()[-300:]}")
            tmp.unlink(missing_ok=True)
            return None
        os.replace(tmp, dest)
        duration = info.get("duration_sec")
        if duration is None:
            duration = probe_duration_sec(dest)
        episode = {
            "kind": kind,
            "feed": program,
            "program": program,
            "slot": slot,
            "title": title,
            "date": date,
            "generated_at": generated_at,
            "duration_sec": duration,
            "file": dest.name,
            "description": description,
        }
        (dest_dir / f"{name}.json").write_text(
            json.dumps(episode, ensure_ascii=False, indent=2),
            encoding="utf-8")
        log(f"podcast: saved {dest}")
        return dest
    except Exception as e:
        log(f"podcast: save failed ({e})")
        return None
