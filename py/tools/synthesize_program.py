#!/usr/bin/env python3
"""長編原稿（掛け合い台本）を VOICEVOX で音声化する。

使い方（ホスト op3060m で）:
  VOICEVOX_HOST=http://voicevox.enoki.local PYTHONPATH=src \
    python3 tools/synthesize_program.py <原稿.txt> --out <出力.mp3>

- 話者は Engine の /speakers から名前で解決する（推測で ID を決めない）。
  めたん=四国めたん、つむぎ=春日部つむぎ、ずんだもん=ずんだもん、
  いずれもスタイル「ノーマル」を優先する。解決した ID は冒頭に表示する。
- 行間には 0.35 秒の無音を入れる（スポットと同じ較正）。
"""
from __future__ import annotations

import argparse
import io
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from radio.voicevox import VoiceVoxClient, host_from_env  # noqa: E402

GAP_SEC = 0.35
CAST = {"めたん": "四国めたん", "つむぎ": "春日部つむぎ", "ずんだもん": "ずんだもん"}
LINE_RE = re.compile(r"^(めたん|つむぎ|ずんだもん):\s*(.+)$")


def concat_wavs(wavs: list[bytes], gap_sec: float = GAP_SEC):
    if not wavs:
        raise ValueError("no wav data")
    params = None
    frames_all: list[bytes] = []
    total_frames = 0
    for data in wavs:
        with wave.open(io.BytesIO(data), "rb") as w:
            p = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if params is None:
                params = p
            elif p != params:
                raise ValueError(f"wav format mismatch: {p} != {params}")
            frames = w.readframes(w.getnframes())
            frames_all.append(frames)
            total_frames += len(frames) // (p[0] * p[1])
    nch, width, rate = params
    gap_frames = int(rate * gap_sec)
    silence = b"\x00" * gap_frames * nch * width
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(width)
        w.setframerate(rate)
        for i, frames in enumerate(frames_all):
            if i:
                w.writeframes(silence)
            w.writeframes(frames)
    duration = (total_frames + gap_frames * (len(wavs) - 1)) / rate
    return out.getvalue(), duration


def to_mp3(wav_bytes: bytes, mp3_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", "pipe:0",
         "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3_path)],
        input=wav_bytes, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[:300]}")


def resolve_speakers(vv: VoiceVoxClient) -> dict[str, int]:
    speakers = vv.speakers()
    resolved: dict[str, int] = {}
    for label, char_name in CAST.items():
        styles = []
        for sp in speakers:
            if sp.get("name") == char_name:
                styles = sp.get("styles", [])
                break
        if not styles:
            print(f"!! Engine に「{char_name}」が見つかりません。話者一覧:")
            for sp in speakers:
                for st in sp.get("styles", []):
                    print(f"  id={st.get('id')}  {sp.get('name')} / {st.get('name')}")
            sys.exit(1)
        pick = next((s for s in styles if s.get("name") == "ノーマル"), styles[0])
        resolved[label] = pick["id"]
        print(f"speaker: {label} = {char_name} / {pick.get('name')} (id={pick['id']})")
    return resolved


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", help="原稿テキスト（話者: 台詞 の形式）")
    ap.add_argument("--out", default="gadget_program.mp3", help="出力 MP3 パス")
    ap.add_argument("--gap", type=float, default=GAP_SEC, help="行間の無音（秒）")
    args = ap.parse_args()

    lines = []
    skipped = 0
    for raw in Path(args.script).read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(raw.strip())
        if m:
            lines.append((m.group(1), m.group(2)))
        elif raw.strip():
            skipped += 1
    print(f"script: {len(lines)} lines, {sum(len(t) for _, t in lines)} chars"
          f" (skipped {skipped} non-dialogue lines)")

    host = host_from_env()
    print(f"VOICEVOX_HOST = {host}")
    wavs: list[bytes] = []
    t0 = time.perf_counter()
    with VoiceVoxClient(host) as vv:
        print(f"engine version: {vv.version()}")
        ids = resolve_speakers(vv)
        for i, (label, text) in enumerate(lines, start=1):
            wavs.append(vv.synthesize_line(text, ids[label]))
            if i % 25 == 0 or i == len(lines):
                print(f"  synth {i}/{len(lines)} "
                      f"({time.perf_counter() - t0:.0f}s)", flush=True)
    wav_bytes, duration = concat_wavs(wavs, args.gap)
    out = Path(args.out)
    to_mp3(wav_bytes, out)
    print(f"done: {out} ({out.stat().st_size} bytes, "
          f"audio {duration / 60:.1f} min, synth {time.perf_counter() - t0:.0f}s)")


if __name__ == "__main__":
    main()
