"""情報スポット生成スケジューラ (Portainer Stack の常駐プロセス).

毎時 :10 に交通情報、:40 に天気情報を生成する (放送は :15 / :45、
生成は5分前)。生成そのものは tools/make_spot.py をサブプロセスで
呼ぶだけ。同一時間帯の二重生成は state ファイル (JSON) で防ぐ。

環境変数:
  SPOT_OUT_DIR    出力先 (既定 /data/output)
  SPOT_ASSETS_DIR ジングル置き場 (既定 /data/assets)
  SPOT_STATE_FILE 状態ファイル (既定 /data/state/scheduler_state.json)
  VOICEVOX_HOST   make_spot 側が読む (サブプロセスへそのまま継承)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PY_DIR = Path(__file__).resolve().parent.parent  # py/
JOBS = [(10, "traffic"), (40, "weather")]  # (生成する分, 種別) 放送の5分前
# 長編: (生成する時, 分, 放送枠) 放送の10分前に生成開始
PROGRAM_JOBS = [(11, 50, "12"), (14, 50, "15"), (17, 50, "18"), (20, 50, "21")]
KEEP_DONE = 100  # state に残す直近の実行キー数


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"done": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def run_job(kind: str, out_dir: Path, assets_dir: Path) -> bool:
    cmd = [
        sys.executable, "tools/make_spot.py", kind,
        "--out-dir", str(out_dir),
        "--assets-dir", str(assets_dir),
    ]
    log(f"generate {kind}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=PY_DIR, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, flush=True)
    if proc.returncode != 0:
        log(f"FAILED {kind} (rc={proc.returncode})")
        if proc.stderr:
            print(proc.stderr[-2000:], flush=True)
        return False
    log(f"done {kind}")
    return True


def main() -> int:
    out_dir = Path(os.environ.get("SPOT_OUT_DIR", "/data/output"))
    assets_dir = Path(os.environ.get("SPOT_ASSETS_DIR", "/data/assets"))
    state_file = Path(os.environ.get(
        "SPOT_STATE_FILE", "/data/state/scheduler_state.json"))
    state = load_state(state_file)
    log(f"scheduler start: jobs={JOBS} out={out_dir} assets={assets_dir} "
        f"VOICEVOX_HOST={os.environ.get('VOICEVOX_HOST', '(unset)')}")
    while True:
        now = datetime.now()
        for minute, kind in JOBS:
            if now.minute != minute:
                continue
            key = f"{now:%Y-%m-%d %H}:{kind}"
            if key in state["done"]:
                continue
            if run_job(kind, out_dir, assets_dir):
                state["done"] = (state["done"] + [key])[-KEEP_DONE:]
                save_state(state_file, state)
        for hour, minute, slot in PROGRAM_JOBS:
            if (now.hour, now.minute) != (hour, minute):
                continue
            key = f"{now:%Y-%m-%d}:program-{slot}"
            if key in state["done"]:
                continue
            cmd = [sys.executable, "tools/run_program_job.py", "--slot", slot]
            log(f"generate program {slot}: {' '.join(cmd)}")
            proc = subprocess.run(cmd, cwd=PY_DIR, capture_output=True,
                                  text=True)
            if proc.stdout:
                print(proc.stdout[-3000:], flush=True)
            if proc.returncode == 0:
                state["done"] = (state["done"] + [key])[-KEEP_DONE:]
                save_state(state_file, state)
                log(f"done program {slot}")
            else:
                log(f"FAILED program {slot} (rc={proc.returncode})")
                if proc.stderr:
                    print(proc.stderr[-2000:], flush=True)
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
