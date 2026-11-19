"""Discord Webhook への通知 (生成ジョブの開始・成功・失敗・警告).

環境変数 DISCORD_WEBHOOK_URL が設定されているときだけ送信する
(未設定なら何もしない)。送信に失敗しても呼び出し元の生成処理を
止めないよう、例外はすべてこの中で握りつぶす。

使い方:
    from notify import notify
    notify("start", "▶ 生成開始: ガジェットマニア 21時枠")
    notify("success", "✅ 生成完了: ...", "要約テキスト")
    notify("error", "❌ 生成失敗: ...", "エラーの末尾")
"""
from __future__ import annotations

import json
import os
import urllib.request

_COLORS = {
    "start": 0x5865F2,    # Discord ブルーパープル
    "success": 0x2ECC71,  # 緑
    "warn": 0xF1C40F,     # 黄
    "error": 0xE74C3C,    # 赤
    "info": 0x3498DB,     # 青
}


def notify(level: str, title: str, body: str = "") -> bool:
    """Discord に embed を1件送る。送れたら True、未設定/失敗は False。"""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return False
    payload = {
        "username": "ネルラジ生成通知",
        "embeds": [{
            "title": title,
            "description": body[:1500],
            "color": _COLORS.get(level, _COLORS["info"]),
        }],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "neruru-radio-notify/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 204)
    except Exception as exc:  # 通知失敗で生成を止めない
        print(f"notify failed: {exc}", flush=True)
        return False
