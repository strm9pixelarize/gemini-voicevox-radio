#!/usr/bin/env python3
"""パワープレイ用に、曲を専用ジングルで包んだ1ファイルを作る。

毎時30分のパワープレイ枠で流す曲を、専用のイントロ/アウトロで挟んで
「パワープレイだ」と分かる形にする。処理は synthesize_program.finalize
を再利用し、番組と同じ流儀に揃える:
  イントロ → (1秒の間) → 曲 → (1秒の間) → アウトロ を連結 →
  loudnorm で -16 LUFS に統一 → 頭と末尾に2秒の無音。
  ID3 の title は「<曲名> (パワープレイ)」、
  artist は元の曲のものを引き継ぐ。

使い方:
  python3 tools/make_powerplay.py <曲.mp3>
  → <出力先>/powerplay_latest.mp3
  曲が替わっても出力名は固定なので、AzuraCast 側のプレイリストは
  そのまま使える (番組の *_latest.mp3 と同じ考え方)。

イントロ/アウトロは assets/neruru_bgm/powerplay/intro.mp3 /
outro.mp3 があれば自動で使う (--intro / --outro で上書き可、
どちらか片方だけでも可。両方無ければ曲だけを整えて出す)。

環境変数:
  PROGRAM_OUT_DIR  出力先 (既定 /data/output)
  PROGRAM_BGM_DIR  assets の場所の上書き (他のジョブと同じ)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PY_DIR = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from synthesize_program import finalize  # noqa: E402


def probe_duration_sec(path: Path) -> float:
    """MP3 の長さ (秒)。取れなければ 0。"""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)], capture_output=True, text=True,
            timeout=30)
        return round(float(proc.stdout.strip()), 1)
    except Exception:
        return 0.0


def probe_tags(path: Path) -> dict:
    """MP3 の ID3 タグ (title / artist)。取れなければ空 dict。"""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags",
             "-of", "json", str(path)], capture_output=True, text=True,
            timeout=30)
        tags = json.loads(proc.stdout).get("format", {}).get("tags", {})
        return {k.lower(): v for k, v in tags.items()}
    except Exception:
        return {}


def find_jingles() -> tuple[Path | None, Path | None]:
    """assets/neruru_bgm/powerplay/ の intro/outro を探す。"""
    bgm_dirs = [PY_DIR.parent / "assets" / "neruru_bgm",
                Path("/data/assets/neruru_bgm")]
    if os.environ.get("PROGRAM_BGM_DIR"):
        bgm_dirs.insert(0, Path(os.environ["PROGRAM_BGM_DIR"]))
    base = next((d for d in bgm_dirs if d.is_dir()), None)
    if base is None:
        return None, None
    intro = base / "powerplay" / "intro.mp3"
    outro = base / "powerplay" / "outro.mp3"
    return (intro if intro.exists() else None,
            outro if outro.exists() else None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("song", help="パワープレイにする曲の MP3")
    ap.add_argument("--out",
                    help="出力 MP3 (既定 <PROGRAM_OUT_DIR>/powerplay_latest.mp3)")
    ap.add_argument("--intro", help="イントロの上書き (任意)")
    ap.add_argument("--outro", help="アウトロの上書き (任意)")
    ap.add_argument("--gap-sec", type=float, default=1.0,
                    help="ジングルと曲の間に入れる無音 (秒、既定 1)")
    args = ap.parse_args()

    song = Path(args.song)
    if not song.exists():
        raise RuntimeError(f"song not found: {song}")
    if os.environ.get("PROGRAM_OUT_DIR"):
        out_dir = Path(os.environ["PROGRAM_OUT_DIR"])
    elif Path("/data/output").is_dir():
        out_dir = Path("/data/output")
    else:
        # ホスト上の clone で直接実行された場合 (コンテナ外) は
        # リポジトリ直下の output/ に出す
        out_dir = PY_DIR.parent / "output"
    out = Path(args.out) if args.out else out_dir / "powerplay_latest.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    auto_intro, auto_outro = find_jingles()
    intro = Path(args.intro) if args.intro else auto_intro
    outro = Path(args.outro) if args.outro else auto_outro
    print(f"song: {song.name}")
    print(f"intro: {intro.name if intro else 'なし'} / "
          f"outro: {outro.name if outro else 'なし'}")

    tags = probe_tags(song)
    song_title = tags.get("title") or song.stem
    title = f"{song_title} (パワープレイ)"
    artist = tags.get("artist") or "ねるるの日常(健全版)"

    # finalize は WAV バイト列を受けるので、曲を WAV にデコードして渡す。
    # このとき曲の前後に gap 分の無音を足しておくと、連結後に
    # 「イントロ → 間 → 曲 → 間 → アウトロ」の並びになる
    tmp_wav = out.with_name(out.stem + ".song.wav")
    try:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(song)]
        if args.gap_sec > 0:
            gap_ms = int(round(args.gap_sec * 1000))
            cmd += ["-af",
                    f"adelay={gap_ms}|{gap_ms},apad=pad_dur={args.gap_sec}"]
            print(f"gap: ジングルと曲の間に {args.gap_sec:.1f}s の無音")
        cmd += ["-ar", "48000", "-ac", "2", str(tmp_wav)]
        subprocess.run(cmd, check=True)
        wav_bytes = tmp_wav.read_bytes()
    finally:
        tmp_wav.unlink(missing_ok=True)
    finalize(wav_bytes, out, probe_duration_sec(song),
             bgm=None, bgm_db=-18.0, target_i=-16.0, loudnorm_on=True,
             intro=intro, outro=outro, pad_sec=2.0,
             title=title, artist=artist)
    print(f"done: {out}")


if __name__ == "__main__":
    main()
