"""JARTIC traffic fetcher (getJartic.php ported to Python).

Changes from the original (see STRUCTURE.md #1/#2/#4):
- Top-level execution turned into functions (importing runs nothing,
  errors raise instead of exit).
- datas is always a list of strings. The original mixed a dict
  {"message": ...} into it only when there was no information.
- The long-term construction exclusion list is data, matched by
  (road, section) partial match instead of exact full-text match
  embedded in code.
"""
from __future__ import annotations

import json
from datetime import datetime

from .http_util import fetch_json

JARTIC_BASE = "https://www.jartic.or.jp/d/traffic_info/r1"
TARGET_JSON = f"{JARTIC_BASE}/target.json"
BODY_PATH = "s/301/C01.json"

EXCLUDED: tuple[tuple[str, str], ...] = (
    ("都心環状線", "新富町出口"),
    ("Ｋ６号川崎線", "川崎浮島ＪＣＴ"),
    ("高速八重洲線", "西銀座"),
)

NO_INFO_MESSAGE = "現在、該当する渋滞・通行規制情報はありません。"


def build_message(props: dict) -> str:
    road = props.get("r", "")
    pd = props.get("pd") or []
    if pd and pd[0]:
        road = pd[0]
    section = props.get("i", "")
    direction = props.get("d", "")
    cause = props.get("c", "")
    state = props.get("rd", "")
    delay = props.get("j", "")
    status = props.get("a", "")

    msg = "【" + road + "】"
    if direction:
        msg += "（" + direction + "）"
    if section:
        msg += " " + section + "で"
    if cause:
        if state == "規制なし":
            msg += cause + "が原因の規制がありましたが、現在は"
        else:
            msg += cause + "のため、"
    if delay:
        msg += delay + "の渋滞"
    msg += state
    if status:
        msg += "（" + status + "）"
    return msg


def is_excluded(message: str) -> bool:
    return any(road in message and section in message for road, section in EXCLUDED)


def get_traffic() -> dict:
    target = fetch_json(TARGET_JSON)
    last_update = target.get("target")
    if not last_update:
        raise RuntimeError("target (last update time) missing in JARTIC response")

    date = datetime.strptime(last_update, "%Y%m%d%H%M")
    head = date.strftime("%Y年%m月%d日 %H時%M分") + "時点での関東の交通情報"

    body = fetch_json(f"{JARTIC_BASE}/{last_update}/{BODY_PATH}")
    features = body.get("features", [])

    seen: set[str] = set()
    messages: list[str] = []
    for feature in features:
        props = feature.get("properties")
        if not props:
            continue
        rn = props.get("rn") or (
            props.get("r", "") + props.get("i", "")
            + props.get("d", "") + props.get("c", "")
        )
        if rn in seen:
            continue
        seen.add(rn)
        messages.append(build_message(props))

    messages = [m for m in messages if not is_excluded(m)]
    if not messages:
        messages = [NO_INFO_MESSAGE]
    return {"time": head, "datas": messages}


if __name__ == "__main__":
    print(json.dumps(get_traffic(), ensure_ascii=False, indent=2))
