"""外部 HTTP 取得の共通部品。

元 PHP との違い: 全ての取得にタイムアウトを付ける (元は無制限で、
相手先が固まると定時生成全体が止まる構造だった)。
標準ライブラリのみで実装し、依存を増やさない。
"""
from __future__ import annotations

import json
import urllib.request

DEFAULT_TIMEOUT = 10  # 秒
USER_AGENT = "neruru-radio-py/0.1 (+schedule-driven fork)"


def fetch_bytes(url: str, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    return fetch_bytes(url, timeout=timeout).decode("utf-8")


def fetch_json(url: str, timeout: float = DEFAULT_TIMEOUT):
    return json.loads(fetch_text(url, timeout=timeout))
