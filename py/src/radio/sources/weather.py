"""気象庁データ取得 (getWeather.php の Python 移植).

元との対応:
- getWeatherReport() -> weather_report()
- confirmAqc()       -> _confirm_aqc() (アメダス品質フラグの確認)
- findIndex()         -> _find_index()

意図的に変えた点 (STRUCTURE.md #1/#2/#3/#5):
- 実行部と関数を分離した。import しても何も走らない (CLI は __main__ のみ)
- エラー時は文字列をデータに混ぜず、例外 (RuntimeError) で返す
- 対象エリアは AREAS のデータ定義に寄せた
- 全取得にタイムアウトが付く (http_util)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .http_util import fetch_json, fetch_text

JST = ZoneInfo("Asia/Tokyo")
JMA_BASE = "https://www.jma.go.jp/bosai"


@dataclass(frozen=True)
class Area:
    name: str
    area: str        # 府県予報区コード (例: 東京都 "130000")
    detail_area: str # 詳細予報エリア (例: 東京地方 "130010")
    stnid: str       # アメダス観測所番号 (例: 北の丸公園 "44132")


# エリア番号: https://www.jma.go.jp/bosai/common/const/area.json
# 観測所番号: https://www.jma.go.jp/bosai/amedas/const/amedastable.json
AREAS: tuple[Area, ...] = (
    Area("東京", "130000", "130010", "44132"),
    Area("埼玉", "110000", "110010", "43241"),
    Area("千葉", "120000", "120010", "45212"),
)


def _confirm_aqc(data) -> str:
    """アメダス値 [値, 品質フラグ] を文字列化する。品質フラグ 0 が正常。"""
    if not isinstance(data, (list, tuple)) or len(data) < 2:
        return "データなし"
    if data[1] == 0:
        return str(data[0])
    return "品質情報を確認して下さい"


def _find_index(areas: list, code: str) -> int | None:
    for i, item in enumerate(areas):
        if item.get("area", {}).get("code") == code:
            return i
    return None


def _squash(text: str, sep: str) -> str:
    return sep.join(re.split(r"\s+", text.strip()))


def weather_report(area: Area) -> dict:
    """1エリア分の天気レポートを dict で返す (元の出力キーと互換)。"""
    # 1. アメダスの最新時刻から、3時間単位のファイル名を決める
    try:
        latest_raw = fetch_text(f"{JMA_BASE}/amedas/data/latest_time.txt")
        latest = datetime.fromisoformat(latest_raw.strip())
    except Exception as exc:
        raise RuntimeError(f"最新時刻データの取得に失敗しました: {exc}") from exc

    yyyymmdd = latest.strftime("%Y%m%d")
    h3 = f"{(latest.hour // 3) * 3:02d}"

    # 2. 天気概況
    overview_text = "取得失敗"
    try:
        overview = fetch_json(f"{JMA_BASE}/forecast/data/overview_forecast/{area.area}.json")
        if overview.get("text"):
            overview_text = _squash(overview["text"], "\n")
    except Exception:
        pass

    # 3. 翌日の天気予報
    tomorrow_weather = "取得失敗"
    try:
        forecast = fetch_json(f"{JMA_BASE}/forecast/data/forecast/{area.area}.json")
        areas = forecast[0]["timeSeries"][0]["areas"]
        idx = _find_index(areas, area.detail_area)
        if idx is not None and len(areas[idx].get("weathers", [])) > 1:
            tomorrow_weather = _squash(areas[idx]["weathers"][1], " ")
    except Exception:
        pass

    # 4. アメダス最新値 (気温・10分降水量)
    latest_temp = "データなし"
    latest_precip = "データなし"
    try:
        amedas = fetch_json(
            f"{JMA_BASE}/amedas/data/point/{area.stnid}/{yyyymmdd}_{h3}.json"
        )
        if isinstance(amedas, dict) and amedas:
            point = amedas[max(amedas.keys())]
            latest_temp = _confirm_aqc(point.get("temp"))
            latest_precip = _confirm_aqc(point.get("precipitation10m"))
    except Exception:
        pass

    return {
        "現在の気温": f"{latest_temp} 度",
        "現在の降水量(10分あたり)": f"{latest_precip} mm",
        "翌日の天気": tomorrow_weather,
        "天気概況": overview_text,
    }


def get_weather(areas: tuple[Area, ...] = AREAS) -> dict:
    """元の getWeather.php の JSON 出力と同形の dict を返す。"""
    now = datetime.now(JST)
    return {
        "取得日": now.strftime("%Y年%m月%d日 %H時%M分"),
        "datas": {a.name: weather_report(a) for a in areas},
    }


if __name__ == "__main__":
    print(json.dumps(get_weather(), ensure_ascii=False, indent=2))
