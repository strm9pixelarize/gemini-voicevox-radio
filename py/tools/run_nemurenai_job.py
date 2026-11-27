#!/usr/bin/env python3
"""「ねるるの眠れない話」の自動生成ジョブ（1回実行して終わる）。

run_scheduler.py から放送枠の10分前に呼ばれ、次の一連を行う:
  1. お題プールから次の3件と、語りテーマを1件選ぶ
     （ローテーション、状態ファイルで管理）
  2. 単語シートを作る（新出単語の読みを LLM に自動で付けさせる）
  3. make_nemurenai.py で原稿を生成する
  4. synthesize_program.py で音声化し、output に program_<枠>_latest.mp3 を置く
  5. サイト表示用に program_<枠>_latest.json も MP3 の隣に置く

環境変数:
  PROGRAM_OUT_DIR       出力先 (既定 /data/output、番組間で共有)
  NEMURENAI_STATE_FILE  状態ファイル (既定 /data/state/nemurenai_state.json)
  NEMURENAI_WORK_DIR    作業ディレクトリ (既定 /data/state/nemurenai_work)
  NEMURENAI_TOPICS      お題プール (既定 /data/state/nemurenai_topics.json、
                        無ければ tools/nemurenai_topics.json から種をコピー)
  NEMURENAI_STORY_TOPICS 語りテーマプール
                        (既定 /data/state/nemurenai_story_topics.json、
                        無ければ tools/nemurenai_story_topics.json から種をコピー)
                        ※他番組と環境変数を共用するとプールと状態が
                        混ざるため、必ず NEMURENAI_ 専用名を使うこと
  ANTHROPIC_API_KEY     make_nemurenai が直接 API を叩くために使う
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PY_DIR = TOOLS.parent

sys.path.insert(0, str(TOOLS))
from job_common import build_word_sheet, load_json, log, probe_duration_sec, program_artwork, run, save_podcast_episode  # noqa: E402
SLOTS = {"21": ("21時", "こんばんは")}


def seed_pool(env_name: str, default_path: str, seed_name: str) -> list:
    path = Path(os.environ.get(env_name, default_path))
    if not path.exists():
        seed = load_json(TOOLS / seed_name, [])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seed, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return load_json(path, [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=sorted(SLOTS),
                    help="放送枠 (21)")
    args = ap.parse_args()
    time_str, greeting = SLOTS[args.slot]

    out_dir = Path(os.environ.get("PROGRAM_OUT_DIR", "/data/output"))
    state_file = Path(os.environ.get(
        "NEMURENAI_STATE_FILE", "/data/state/nemurenai_state.json"))
    work = Path(os.environ.get(
        "NEMURENAI_WORK_DIR", "/data/state/nemurenai_work")) / args.slot
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    pool = seed_pool("NEMURENAI_TOPICS", "/data/state/nemurenai_topics.json",
                     "nemurenai_topics.json")
    if len(pool) < 3:
        raise RuntimeError("topic pool needs at least 3 entries")
    story_pool = seed_pool("NEMURENAI_STORY_TOPICS",
                           "/data/state/nemurenai_story_topics.json",
                           "nemurenai_story_topics.json")
    if len(story_pool) < 1:
        raise RuntimeError("story topic pool needs at least 1 entry")

    state = load_json(state_file, {"next_index": 0})
    idx = int(state.get("next_index", 0)) % len(pool)
    topics = [pool[(idx + k) % len(pool)] for k in range(3)]
    s_idx = int(state.get("story_index", 0)) % len(story_pool)
    story_theme = story_pool[s_idx]
    log(f"slot {args.slot}: topics={topics} story={story_theme}")

    topics_json = {"topics": topics, "story_theme": story_theme,
                   "time": time_str, "greeting": greeting}
    topics_path_out = work / "topics.json"
    topics_path_out.write_text(json.dumps(topics_json, ensure_ascii=False),
                               encoding="utf-8")

    sheet_path = work / "word_sheet.json"
    build_word_sheet(topics + [story_theme], {}, sheet_path,
                     "nemurenai-common.md")

    trial_dir = work / "trial"
    cmd = [sys.executable, "tools/make_nemurenai.py",
           "--out-dir", str(trial_dir),
           "--topics-json", str(topics_path_out),
           "--extra-dict", str(sheet_path)]
    run(cmd, PY_DIR)
    mp3 = out_dir / f"program_{args.slot}_latest.mp3"
    synth_cmd = [sys.executable, "tools/synthesize_program.py",
                 str(trial_dir / "nemurenai_program_fixed.txt"),
                 "--out", str(mp3),
                 "--title", "ねるるの眠れない話",
                 "--artist", "ねるるの日常(健全版)",
                 # ジングルは本編より少し大きめに聞こえるので 15% 下げる
                 "--jingle-volume", "0.85"]
    # BGM は assets/neruru_bgm フォルダの曲をローテーションで使う
    # (無ければ声のみ)。コンテナでは assets は /data/assets にマウント
    # される (compose 参照)。PROGRAM_BGM_DIR で上書きもできる
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
    # イントロ/アウトロは番組フォルダ (nemurenai/) にあれば付ける
    if bgm_base is not None:
        intro = bgm_base / "nemurenai" / "intro.mp3"
        if intro.exists():
            synth_cmd += ["--intro", str(intro)]
            log("intro: nemurenai/intro.mp3")
        outro = bgm_base / "nemurenai" / "outro.mp3"
        if outro.exists():
            synth_cmd += ["--outro", str(outro)]
            log("outro: nemurenai/outro.mp3")
    # 番組アートワークがあれば、カバーアートとして埋め込む
    art = program_artwork("nemurenai")
    if art is not None:
        synth_cmd += ["--artwork", str(art)]
        log(f"artwork: {art.name}")
    run(synth_cmd, PY_DIR)

    # 語りの題名（素材 JSON から。取れなければテーマ名で代用）
    story_title = story_theme
    try:
        _sm = json.loads((trial_dir / "material_story.json").read_text(
            encoding="utf-8"))
        if _sm.get("title"):
            story_title = str(_sm["title"])
    except Exception:
        pass

    # サイト表示用のサイドカー JSON (MP3 と同名で隣に上書き)。
    # 音声化が成功したときだけ書くので、内容は常に最新の放送と一致する
    sidecar = {
        "kind": "nemurenai",
        "program": "ねるるの眠れない話",
        "slot": args.slot,
        "air_time": f"{args.slot}:00",
        "generated_at": datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "mp3": mp3.name,
        "duration_sec": probe_duration_sec(mp3),
        "topics": topics,
        "story": {"theme": story_theme, "title": story_title},
    }
    sidecar_path = out_dir / f"program_{args.slot}_latest.json"
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False,
                                       indent=2), encoding="utf-8")
    log(f"sidecar: {sidecar_path.name}")

    # ポッドキャスト用に、日付入りの固定名でも保存する
    desc_lines = ["お題: " + " / ".join(topics),
                  f"トバリの小さな語り: {story_title}"]
    save_podcast_episode(mp3, sidecar, "\n".join(desc_lines))

    state["next_index"] = (idx + 3) % len(pool)
    state["story_index"] = (s_idx + 1) % len(story_pool)
    state["last_slot"] = args.slot
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    log(f"done: {mp3}")


if __name__ == "__main__":
    main()
