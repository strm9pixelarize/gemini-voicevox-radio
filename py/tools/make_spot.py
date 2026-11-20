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
MP3 には ID3 タグ (title=天気情報/交通情報、artist、date=生成日) を
付ける (2026-11-20、長編・ニュースと同方針)。
音量も長編・ニュースと同じ -16 LUFS に loudnorm (2パス) で揃える
(2026-11-20)。

ジングル/BGM: 種別専用アセット (assets/neruru_bgm/<kind>/ の
intro.mp3 / outro.mp3 / bgm.mp3、2026-11-20 に SUNO で生成) があれば
優先して使う。--jingle-in / --jingle-out 指定時はそちらが優先。
種別専用が無い場合は従来どおり --assets-dir (既定 ../assets) の
jingle_in.mp3 / jingle_out.mp3 を探す。BGM は声の下にダッキング
付きでループ再生する (長編の finalize と同じ方式・音量 -18 dB)。
ジングルの秒数ぶん、原稿バジェットは自動で差し引かれる
(読み上げ約5.0字/秒で換算。--max-chars 明示時は除く。BGM は対象外)。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")

from radio.spots import DEFAULT_MAX_CHARS, build_lines  # noqa: E402
from radio.voicevox import VoiceVoxClient, host_from_env  # noqa: E402

GAP_SEC = 0.35  # 行間の無音
CHARS_PER_SEC = 5.0  # 実測 (2026-11-17): 読み上げ速度の較正用
VOICE_RATE = 24000  # VOICEVOX の WAV に合わせる
# ID3 タグ (Now Playing でファイル名でなく種別名を出すため)
SPOT_TITLES = {"weather": "天気情報", "traffic": "交通情報"}
SPOT_ARTIST = "ねるるの日常(健全版)"


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


TARGET_I = -16.0  # 長編・ニュースと共通の目標ラウドネス (LUFS)


# loudnorm の2ヘルパーは synthesize_program.py と同じ実装。
# 共通モジュールへの切り出しは今後の課題 (STRUCTURE 候補)
def measure_loudnorm(src: Path, target_i: float) -> dict | None:
    """loudnorm の測定パス。測れたら測定値の dict、失敗したら None。"""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(src), "-af",
         f"loudnorm=I={target_i}:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"], capture_output=True)
    blocks = re.findall(r"\{[^{}]*\}",
                        proc.stderr.decode(errors="replace"), re.S)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if "input_i" in data:
            return data
    return None


def loudnorm_filter(target_i: float, measured: dict | None) -> str:
    base = f"loudnorm=I={target_i}:TP=-1.5:LRA=11"
    if not measured:
        return base
    return (base + f":measured_I={measured['input_i']}"
            f":measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}"
            f":measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true")


def to_mp3(wav_bytes: bytes, mp3_path: Path, title: str | None = None) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found (WAV のままでは出力できない)")
    # 音量調整 (2パス loudnorm) の測定のため、一旦ファイルに書く
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(wav_bytes)
        tmp = Path(tf.name)
    try:
        measured = measure_loudnorm(tmp, TARGET_I)
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
               "-af", loudnorm_filter(TARGET_I, measured),
               "-codec:a", "libmp3lame", "-b:a", "128k"]
        if title:
            cmd += ["-metadata", f"title={title}",
                    "-metadata", f"artist={SPOT_ARTIST}",
                    "-metadata", f"date={datetime.now():%Y-%m-%d}"]
        proc = subprocess.run(cmd + [str(mp3_path)], capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[:300]}")
        if measured:
            print(f"loudnorm: {measured['input_i']} LUFS "
                  f"-> target {TARGET_I} LUFS")
    finally:
        tmp.unlink(missing_ok=True)


def find_audio(base: Path, stem: str) -> Path | None:
    """base/<stem>.(mp3|wav|m4a|ogg) を探す。"""
    for ext in ("mp3", "wav", "m4a", "ogg"):
        p = base / f"{stem}.{ext}"
        if p.exists():
            return p
    return None


def resolve_jingle(explicit: str | None, assets_dir: Path, name: str) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise RuntimeError(f"jingle not found: {p}")
        return p
    return find_audio(assets_dir, name)


BGM_DB = -18.0  # 声に対する BGM の音量 (長編の --bgm-volume-db 既定と同じ)


def mix_bgm(voice_bytes: bytes, bgm: Path, duration: float) -> bytes | None:
    """声の WAV (24kHz mono) の下に BGM をループで敷く (ダッキング付き)。

    synthesize_program.finalize と同じレシピをモノラルで。失敗したら
    None を返し、呼び出し側は BGM なしで続行する (放送を止めない)。
    """
    if shutil.which("ffmpeg") is None:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(voice_bytes)
        tmp = Path(tf.name)
    try:
        dur = f"{duration:.2f}"
        fade_out = max(0.0, duration - 3)
        fc = (
            "[0:a]asplit=2[v][key];"
            f"[1:a]aresample={VOICE_RATE},volume={BGM_DB:.1f}dB,"
            f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.2f}:d=3,"
            f"atrim=0:{dur}[bed];"
            "[bed][key]sidechaincompress=threshold=0.03:ratio=6:"
            "attack=150:release=800[duck];"
            "[v][duck]amix=inputs=2:duration=first:normalize=0,"
            f"alimiter=limit=0.9,atrim=0:{dur}[out]"
        )
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
             "-stream_loop", "-1", "-i", str(bgm),
             "-filter_complex", fc, "-map", "[out]",
             "-ar", str(VOICE_RATE), "-ac", "1", "-f", "wav", "pipe:1"],
            capture_output=True)
        if proc.returncode != 0 or not proc.stdout:
            return None
        return proc.stdout
    finally:
        tmp.unlink(missing_ok=True)


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
    ap.add_argument("--bgm", default=None, help="声の下に敷く BGM ファイル")
    ap.add_argument("--no-bgm", action="store_true", help="BGM を使わない")
    args = ap.parse_args()

    # --- ジングル (先に秒数を確定させ、原稿バジェットから差し引く) ---
    # 優先順: 明示指定 > 種別専用 (neruru_bgm/<kind>/intro|outro) > 共有
    jingle_wavs: dict[str, bytes] = {}
    jingle_sec = 0.0
    if not args.no_jingle:
        assets = Path(args.assets_dir)
        kind_dir = assets / "neruru_bgm" / args.kind
        for key, explicit, name, kind_stem in (
            ("in", args.jingle_in, "jingle_in", "intro"),
            ("out", args.jingle_out, "jingle_out", "outro"),
        ):
            if explicit:
                p = resolve_jingle(explicit, assets, name)
            else:
                p = find_audio(kind_dir, kind_stem)
                if p is None:
                    p = resolve_jingle(None, assets, name)
            if p is not None:
                data = load_as_voice_wav(p)
                jingle_wavs[key] = data
                sec = wav_duration(data)
                jingle_sec += sec
                print(f"jingle {key}: {p} ({sec:.2f}s)")

    # --- BGM (種別専用のみ。声の下に敷くのでバジェットには影響しない) ---
    bgm_path: Path | None = None
    if not args.no_bgm:
        if args.bgm:
            bgm_path = Path(args.bgm)
            if not bgm_path.exists():
                raise RuntimeError(f"bgm not found: {bgm_path}")
        else:
            bgm_path = find_audio(
                Path(args.assets_dir) / "neruru_bgm" / args.kind, "bgm")

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

    voice_bytes, voice_sec = concat_wavs(wavs)
    bgm_used: str | None = None
    if bgm_path is not None:
        mixed = mix_bgm(voice_bytes, bgm_path, voice_sec)
        if mixed is not None:
            voice_bytes = mixed
            bgm_used = str(bgm_path)
            print(f"bgm: {bgm_path} ({BGM_DB:+.0f} dB, ducking on)")
        else:
            print(f"bgm: mixing failed, continuing without bgm: {bgm_path}")

    segments: list[bytes] = []
    if "in" in jingle_wavs:
        segments.append(jingle_wavs["in"])
    segments.append(voice_bytes)
    if "out" in jingle_wavs:
        segments.append(jingle_wavs["out"])
    wav_bytes, duration = concat_wavs(segments)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = out_dir / f"{args.kind}_latest.mp3"
    to_mp3(wav_bytes, mp3_path, SPOT_TITLES[args.kind])
    (out_dir / f"{args.kind}_latest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "kind": args.kind,
        "speaker": args.speaker,
        "lines": len(lines),
        "chars": total_chars,
        "synth_sec": round(synth_sec, 2),
        "jingle_sec": round(jingle_sec, 2),
        "bgm": bgm_used,
        "audio_sec": round(duration, 2),
        "target_sec": 180,
        "output": str(mp3_path),
        "size": mp3_path.stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
