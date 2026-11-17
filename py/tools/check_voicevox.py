"""External VOICEVOX connectivity check.

Run this ON THE USER'S HOST (or in the generator container) - the
enoki.local name only resolves inside the home LAN.

Usage:
  VOICEVOX_HOST=http://voicevox.enoki.local \
    PYTHONPATH=src python3 tools/check_voicevox.py

Prints: engine version, speaker list (name / style / id), and the
wall-clock time to synthesize one sample line with the first speaker.
"""
import sys
import time

sys.path.insert(0, "src")

from radio.voicevox import VoiceVoxClient, host_from_env  # noqa: E402


def main() -> int:
    host = host_from_env()
    print(f"VOICEVOX_HOST = {host}")
    with VoiceVoxClient(host) as vv:
        try:
            print(f"version: {vv.version()}")
        except Exception as exc:
            print(f"FAILED to reach engine: {exc}")
            return 1
        speakers = vv.speakers()
        print(f"speakers: {len(speakers)} characters")
        first_id = None
        for sp in speakers:
            for style in sp.get("styles", []):
                print(f"  id={style['id']:>3}  {sp['name']} / {style['name']}")
                if first_id is None:
                    first_id = style["id"]
        if first_id is not None:
            text = "こんにちは。これは外部ボイスボックスの接続テストです。"
            t0 = time.perf_counter()
            wav = vv.synthesize_line(text, first_id)
            dt = time.perf_counter() - t0
            print(f"synthesis test: speaker={first_id}, {len(wav)} bytes, {dt:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
