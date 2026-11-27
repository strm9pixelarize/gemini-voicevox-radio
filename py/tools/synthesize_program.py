#!/usr/bin/env python3
"""長編原稿（掛け合い台本）を VOICEVOX で音声化する。

使い方（ホスト op3060m で）:
  VOICEVOX_HOST=http://voicevox.enoki.local PYTHONPATH=src \
    python3 tools/synthesize_program.py <原稿.txt> --out <出力.mp3>

- 話者は Engine の /speakers から名前で解決する（推測で ID を決めない）。
  めたん=四国めたん、つむぎ=春日部つむぎ、ずんだもん=ずんだもん、
  いずれもスタイル「ノーマル」を優先する。解決した ID は冒頭に表示する。
- 行間には 0.35 秒の無音を入れる（スポットと同じ較正）。
- 最終段で loudnorm により音量を目標 LUFS に揃える（--no-loudnorm で無効）。
  --bgm を渡すと、BGM をループして下に敷き、声に合わせて自動で
  引っ込ませる（ダッキング）処理も最終段で行う。
  --intro / --outro を渡すと、本編の前後にジングルを連結する
  （連結した全体に loudnorm をかけるので音量の段差は出ない）。
  頭と末尾には --pad-sec 秒（既定 2 秒）の無音を入れる
  （AzuraCast 側のつなぎで頭・尻が切れないようにするため）。
- --title / --artist を渡すと、最終 MP3 に ID3 タグ (title / artist /
  date=生成日) を付ける。AzuraCast の Now Playing でファイル名でなく
  番組名が出るようにするため (2026-11-20)。
- --artwork を渡すと、その画像をカバーアート (APIC) として埋め込む。
  Now Playing やポッドキャストで番組ごとの絵が出るようにするため
  (2026-11-26)。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from radio.voicevox import VoiceVoxClient, host_from_env  # noqa: E402

GAP_SEC = 0.35
CAST = {"めたん": "四国めたん", "つむぎ": "春日部つむぎ", "ずんだもん": "ずんだもん",
        "ひまり": "冥鳴ひまり", "はう": "雨晴はう", "トバリ": "夜語トバリ"}
LINE_RE = re.compile(r"^(めたん|つむぎ|ずんだもん|ひまり|はう|トバリ):\s*(.+)$")


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


def _ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-v", "error", *args],
                          capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[:300]}")


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


def finalize(wav_bytes: bytes, mp3_path: Path, duration: float,
             bgm: Path | None, bgm_db: float, target_i: float,
             loudnorm_on: bool, intro: Path | None = None,
             outro: Path | None = None, pad_sec: float = 2.0,
             title: str | None = None,
             artist: str | None = None,
             jingle_volume: float = 1.0,
             artwork: Path | None = None) -> None:
    """最終段: BGM を敷き、ジングルを前後に付け、loudnorm で音量を揃える。"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found")
    tmp_voice = mp3_path.with_name(mp3_path.stem + ".voice.wav")
    tmp_mix = mp3_path.with_name(mp3_path.stem + ".mix.wav")
    tmp_full = mp3_path.with_name(mp3_path.stem + ".full.wav")
    tmp_norm = mp3_path.with_name(mp3_path.stem + ".norm.wav")
    tmp_pad = mp3_path.with_name(mp3_path.stem + ".pad.wav")
    try:
        tmp_voice.write_bytes(wav_bytes)
        src = tmp_voice
        if bgm is not None:
            dur = f"{duration:.2f}"
            fade_out = max(0.0, duration - 3)
            # 声は VOICEVOX のモノラル前提でステレオ化してから BGM と混ぜる。
            # loudnorm は混ぜた後にかける (BGM 込みの最終音量で揃えるため)
            fc = (
                "[0:a]aresample=48000,pan=stereo|c0=c0|c1=c0,"
                "asplit=2[v][key];"
                f"[1:a]aresample=48000,volume={bgm_db:.1f}dB,"
                f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.2f}:d=3,"
                f"atrim=0:{dur}[bed];"
                "[bed][key]sidechaincompress=threshold=0.03:ratio=6:"
                "attack=150:release=800[duck];"
                "[v][duck]amix=inputs=2:duration=first:normalize=0,"
                f"alimiter=limit=0.9,atrim=0:{dur}[out]"
            )
            _ffmpeg(["-i", str(tmp_voice), "-stream_loop", "-1",
                     "-i", str(bgm), "-filter_complex", fc,
                     "-map", "[out]", str(tmp_mix)])
            src = tmp_mix
            print(f"bgm: {bgm.name} ({bgm_db:+.0f} dB, ducking on)")
        if intro is not None or outro is not None:
            # イントロ → 本編 → アウトロ の順に連結する。全パートを
            # 48kHz ステレオへ揃えてから concat する
            inputs: list[str] = []
            parts: list[int] = []
            if intro is not None:
                inputs += ["-i", str(intro)]
                parts.append(len(parts))
            inputs += ["-i", str(src)]
            parts.append(len(parts))
            if outro is not None:
                inputs += ["-i", str(outro)]
                parts.append(len(parts))
            # ジングル (先頭と末尾) だけ音量を調整できるようにする。
            # 本編は jingle_volume の影響を受けない
            def _seg(j: int, i: int) -> str:
                is_jingle = ((j == 0 and intro is not None)
                             or (j == len(parts) - 1 and outro is not None
                                 and len(parts) > 1))
                vol = f",volume={jingle_volume:.3f}" if is_jingle else ""
                return (f"[{i}:a]aresample=48000{vol},"
                        f"aformat=channel_layouts=stereo[p{j}]")
            fc = ";".join(_seg(j, i) for j, i in enumerate(parts))
            fc += ";" + "".join(f"[p{j}]" for j in range(len(parts)))
            fc += f"concat=n={len(parts)}:v=0:a=1[out]"
            _ffmpeg(inputs + ["-filter_complex", fc, "-map", "[out]",
                              str(tmp_full)])
            src = tmp_full
            names = " + ".join(
                ([intro.name] if intro is not None else [])
                + ["本編"]
                + ([outro.name] if outro is not None else []))
            print(f"jingle: {names}")
        if loudnorm_on:
            measured = measure_loudnorm(src, target_i)
            _ffmpeg(["-i", str(src), "-af",
                     loudnorm_filter(target_i, measured),
                     "-ar", "48000", str(tmp_norm)])
            src = tmp_norm
            src_i = measured["input_i"] if measured else "?"
            print(f"loudnorm: {src_i} LUFS -> target {target_i} LUFS")
        if pad_sec > 0:
            # 頭と末尾に無音を足す (loudnorm の後に足すので音量は不変)
            ms = int(round(pad_sec * 1000))
            _ffmpeg(["-i", str(src), "-af",
                     f"adelay={ms}|{ms},apad=pad_dur={pad_sec}",
                     str(tmp_pad)])
            src = tmp_pad
            print(f"pad: +{pad_sec:.1f}s head/tail silence")
        encode = ["-i", str(src)]
        if artwork is not None:
            encode += ["-i", str(artwork), "-map", "0:a", "-map", "1:v",
                       "-codec:v", "copy",
                       "-metadata:s:v", "title=Album cover",
                       "-metadata:s:v", "comment=Cover (front)"]
            print(f"artwork: {artwork.name}")
        encode += ["-codec:a", "libmp3lame", "-b:a", "128k"]
        if title or artist:
            if title:
                encode += ["-metadata", f"title={title}"]
            if artist:
                encode += ["-metadata", f"artist={artist}"]
            encode += ["-metadata", f"date={datetime.now():%Y-%m-%d}"]
            print(f"tags: title={title} / artist={artist}")
        _ffmpeg(encode + [str(mp3_path)])
    finally:
        for tmp in (tmp_voice, tmp_mix, tmp_full, tmp_norm, tmp_pad):
            tmp.unlink(missing_ok=True)


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
    ap.add_argument("--bgm", help="下に敷く BGM のファイル (任意)")
    ap.add_argument("--bgm-volume-db", type=float, default=-18.0,
                    help="BGM の音量調整 (dB、既定 -18)")
    ap.add_argument("--target-lufs", type=float, default=-16.0,
                    help="loudnorm の目標ラウドネス (既定 -16 LUFS)")
    ap.add_argument("--no-loudnorm", action="store_true",
                    help="loudnorm をかけない")
    ap.add_argument("--intro", help="本編の前に付けるジングル (任意)")
    ap.add_argument("--outro", help="本編の後に付けるジングル (任意)")
    ap.add_argument("--jingle-volume", type=float, default=1.0,
                    help="ジングル (intro/outro) の音量倍率 (既定 1.0、"
                         "0.85 で15%下げ)")
    ap.add_argument("--pad-sec", type=float, default=2.0,
                    help="頭と末尾に入れる無音の秒数 (既定 2、0 で無効)")
    ap.add_argument("--title", help="ID3 タグの title (番組名、任意)")
    ap.add_argument("--artist", help="ID3 タグの artist (任意)")
    ap.add_argument("--artwork", help="カバーアート画像 (任意)")
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
    bgm = Path(args.bgm) if args.bgm else None
    if bgm is not None and not bgm.exists():
        raise SystemExit(f"BGM ファイルがありません: {bgm}")
    intro = Path(args.intro) if args.intro else None
    if intro is not None and not intro.exists():
        raise SystemExit(f"イントロファイルがありません: {intro}")
    outro = Path(args.outro) if args.outro else None
    if outro is not None and not outro.exists():
        raise SystemExit(f"アウトロファイルがありません: {outro}")
    artwork = Path(args.artwork) if args.artwork else None
    if artwork is not None and not artwork.exists():
        raise SystemExit(f"アートワークファイルがありません: {artwork}")
    finalize(wav_bytes, out, duration, bgm, args.bgm_volume_db,
             args.target_lufs, not args.no_loudnorm, intro, outro,
             args.pad_sec, args.title, args.artist,
             jingle_volume=args.jingle_volume, artwork=artwork)
    print(f"done: {out} ({out.stat().st_size} bytes, "
          f"audio {duration / 60:.1f} min, synth {time.perf_counter() - t0:.0f}s)")


if __name__ == "__main__":
    main()
