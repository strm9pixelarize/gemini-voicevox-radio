"""情報スポットを1本生成する (Phase 1 の縦切り).

天気/交通の取得 -> 定型原稿 -> VOICEVOX 合成 -> WAV 結合 -> MP3 化
までを通す。ホスト (op3060m) 上で実行すること。VOICEVOX には
Apache プロキシ経由 (ポート80, VOICEVOX_HOST=http://voicevox.enoki.local)
で接続する。

Usage:
  VOICEVOX_HOST=http://voicevox.enoki.local \
    PYTHONPATH=src python3 tools/make_spot.py weather
  VOICEVOX_HOST=http://voicevox.enoki.local \
    PYTHONPATH=src python3 tools/make_spot.py traffic --speaker 2

出力: output/{kind}_latest.mp3 と {kind}_latest.txt (原稿)。
計測値 (総文字数 / 合成所要秒 / 音声秒数) を標準出力に出す。

ジングル: --jingle-in / --jingle-out で音声ファイル (mp3/wav 等、
ffmpeg で読める形式) を指定すると、声の前後に付ける。未指定時は
--assets-dir (既定 ../assets) の jingle_in.mp3 / jingle_out.mp3 を
探し、あれば使う。ジングルの秒数ぶん、原稿バジェットは自動で
差し引かれる (読み上げ約5.0字/秒で換算。--max-chars 明示時は除く)。
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, "src")

from radio.spots import DEFAULT_MAX_CHARS, build_lines  # noqa: E402
from radio.voicevox import VoiceVoxClient, host_from_env  # noqa: E402

GAP_SEC = 0.35  # 行間の無音
CHARS_PER_SEC = 5.0  # 実測 (2026-11-17): 読み上げ速度の較正用
VOICE_RATE = 24000  # VOICEVOX の WAV に合わせる


def concat_wavs(wavs: list[bytes], gap_sec: float = GAP_SEC) -> tuple[bytes, float]:
    """同一形式の WAV を無音を挟んで結合し、(WAVバイト列, 秒数) を返す。"""
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
            # ヘッダのフレーム数は当てにしない (パイプ出力の WAV は
            # サイズ欄が不定になる)。実データ長から数える。
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


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as w:
        frames = w.readframes(w.getnframes())
        count = len(frames) // (w.getnchannels() * w.getsampwidth())
        return count / w.getframerate()


def load_as_voice_wav(path: Path) -> bytes:
    """任意の音声ファイルを声と同じ形式 (24kHz mono 16bit WAV) に変換する。"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-ar", str(VOICE_RATE), "-ac", "1", "-f", "wav", "pipe:1"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path}: {proc.stderr.decode()[:300]}")
    return proc.stdout


def to_mp3(wav_bytes: bytes, mp3_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found (WAV のままでは出力できない)")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", "pipe:0",
         "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3_path)],
        input=wav_bytes, capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[:300]}")


def resolve_jingle(explicit: str | None, assets_dir: Path, name: str) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise RuntimeError(f"jingle not found: {p}")
        return p
    for ext in ("mp3", "wav", "m4a", "ogg"):
        p = assets_dir / f"{name}.{ext}"
        if p.exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["weather", "traffic"])
    ap.add_argument("--speaker", type=int, default=2,
                    help="VOICEVOX スタイルID (既定: 2 = 四国めたん ノーマル)")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--max-chars", type=int, default=0,
                    help="原稿の文字数バジェット (0 = spots の既定値)")
    ap.add_argument("--jingle-in", default=None, help="入りのジングル音声ファイル")
    ap.add_argument("--jingle-out", default=None, help="出のジングル音声ファイル")
    ap.add_argument("--assets-dir", default="../assets",
                    help="ジングルの既定の置き場 (jingle_in.mp3 等を探す)")
    ap.add_argument("--no-jingle", action="store_true", help="ジングルを使わない")
    args = ap.parse_args()

    # --- ジングル (先に秒数を確定させ、原稿バジェットから差し引く) ---
    jingle_wavs: dict[str, bytes] = {}
    jingle_sec = 0.0
    if not args.no_jingle:
        assets = Path(args.assets_dir)
        for key, explicit, name in (
            ("in", args.jingle_in, "jingle_in"),
            ("out", args.jingle_out, "jingle_out"),
        ):
            p = resolve_jingle(explicit, assets, name)
            if p is not None:
                data = load_as_voice_wav(p)
                jingle_wavs[key] = data
                sec = wav_duration(data)
                jingle_sec += sec
                print(f"jingle {key}: {p} ({sec:.2f}s)")

    budget = args.max_chars or DEFAULT_MAX_CHARS
    if jingle_wavs and not args.max_chars:
        budget = max(200, budget - int(jingle_sec * CHARS_PER_SEC))
        print(f"char budget adjusted for jingles: {budget}")

    lines = build_lines(args.kind, max_chars=budget)
    total_chars = sum(len(l) for l in lines)
    print(f"script: {len(lines)} lines, {total_chars} chars")
    for line in lines:
        print(f"  {line}")

    host = host_from_env()
    print(f"VOICEVOX_HOST = {host}")
    wavs: list[bytes] = []
    t0 = time.perf_counter()
    with VoiceVoxClient(host) as vv:
        print(f"engine version: {vv.version()}")
        for line in lines:
            lt0 = time.perf_counter()
            wavs.append(vv.synthesize_line(line, args.speaker))
            print(f"  synth {time.perf_counter() - lt0:6.2f}s  {line[:24]}")
    synth_sec = time.perf_counter() - t0

    segments: list[bytes] = []
    if "in" in jingle_wavs:
        segments.append(jingle_wavs["in"])
    segments.extend(wavs)
    if "out" in jingle_wavs:
        segments.append(jingle_wavs["out"])
    wav_bytes, duration = concat_wavs(segments)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = out_dir / f"{args.kind}_latest.mp3"
    to_mp3(wav_bytes, mp3_path)
    (out_dir / f"{args.kind}_latest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "kind": args.kind,
        "speaker": args.speaker,
        "lines": len(lines),
        "chars": total_chars,
        "synth_sec": round(synth_sec, 2),
        "jingle_sec": round(jingle_sec, 2),
        "audio_sec": round(duration, 2),
        "target_sec": 180,
        "output": str(mp3_path),
        "size": mp3_path.stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
