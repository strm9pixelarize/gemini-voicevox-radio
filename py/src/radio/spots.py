"""情報スポットの定型原稿生成 (schedule.yaml レーン2).

設計 (2026-11-17 決定):
- 天気 (:45) と交通 (:15) は LLM を使わず、定型フォーマットに最新
  データを差し込む。長編の原稿には混ぜない (2レーン分離)。
- 尺は約3分 (180秒)。合わせ方は atempo の速度上げではなく項目数の
  削減 (trim_items)。そのため原稿生成は文字数バジェット制にする。
  バジェットの初期値は暫定で、実測 (make_spot.py が出す
  「総文字数 / 音声秒数」) で較正する。
- 1行 = 1回の合成単位。行の区切りがそのまま間の取り方になる。
"""
from __future__ import annotations

import re

from .sources.traffic import get_traffic
from .sources.weather import get_weather

# バジェット: VOICEVOX 標準速度で約180秒に収まる総文字数。
# 2026-11-17 実測で較正済み (speaker=2, 行間0.35秒):
#   天気 474字/13行 -> 音声 96.9秒、交通 848字/23行 -> 音声 182.6秒。
#   読み上げは約5.0字/秒で、行間が1行あたり0.35秒乗る。
#   180秒・約23行なら 860字がほぼ一致する。
DEFAULT_MAX_CHARS = 860


def _speech(text: str) -> str:
    """読み上げ向けの軽い整形。記号の除去と単位の読み替えのみ。"""
    text = text.replace("【", "").replace("】", "")
    text = text.replace(" mm", "ミリ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fit(lines: list[str], max_chars: int) -> list[str]:
    """バジェットを超える分は後ろから落とす (trim_items)。"""
    out: list[str] = []
    total = 0
    for line in lines:
        if out and total + len(line) > max_chars:
            break
        out.append(line)
        total += len(line)
    return out


def weather_lines(data: dict | None = None, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """天気スポットの原稿行リスト。data は get_weather() の戻り値。"""
    if data is None:
        data = get_weather()
    lines = [f"天気情報をお伝えします。{data['取得日']}の情報です。"]
    for name, report in data["datas"].items():
        lines.append(_speech(
            f"{name}。現在の気温は{report['現在の気温']}、"
            f"降水量は{report['現在の降水量(10分あたり)']}。"
            f"明日の天気は{report['翌日の天気']}。"
        ))
    # 概況は関東全体で1回だけ (エリアごとに繰り返さない)。
    # 文ごとに割って合成単位を細かくする。
    overview = next(iter(data["datas"].values()))["天気概況"]
    for sentence in _speech(overview).split("。"):
        if sentence.strip():
            lines.append(sentence.strip() + "。")
    lines.append("以上、天気情報でした。")
    return _fit(lines, max_chars)


def traffic_lines(data: dict | None = None, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """交通スポットの原稿行リスト。data は get_traffic() の戻り値。"""
    if data is None:
        data = get_traffic()
    opening = f"{data['time']}をお伝えします。"
    closing = "以上、交通情報でした。"
    items = [_speech(m) for m in data["datas"]]
    budget = max_chars - len(opening) - len(closing)
    picked = _fit(items, budget)
    lines = [opening, *picked]
    omitted = len(items) - len(picked)
    if omitted > 0:
        lines.append(f"このほかにも、{omitted}件の交通情報があります。")
    lines.append(closing)
    return lines


BUILDERS = {"weather": weather_lines, "traffic": traffic_lines}


def build_lines(kind: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    if kind not in BUILDERS:
        raise ValueError(f"unknown spot kind: {kind} (weather|traffic)")
    return BUILDERS[kind](max_chars=max_chars)


if __name__ == "__main__":
    import sys
    kind = sys.argv[1] if len(sys.argv) > 1 else "weather"
    result = build_lines(kind)
    for line in result:
        print(line)
    print(f"-- {len(result)} lines, {sum(len(l) for l in result)} chars", file=sys.stderr)
