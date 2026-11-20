#!/usr/bin/env python3
"""AKIBA PC Hotline! の RSS から、ガジェットマニアの新コーナー
「AKIBAピックアップ」用の記事を選んで本文まで取る。

設計 (2026-11-20 決定):
  - フィードは RSS 1.0 (RDF)。名前空間つきでパースする
    (make_news 試作時に Impress の RDF が素のパースで失敗した前例あり)
  - 選ぶのは2本。新製品ニュース優先、セール記事は基本除外
  - カテゴリの偏り対策 (同系統が重なったら次点へ)
  - 使用済み URL は呼び出し側が state で管理し、used に渡す

Usage:
  python3 py/tools/akiba.py          # 選別結果を目視確認する
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

FEED_URL = "https://akiba-pc.watch.impress.co.jp/data/rss/1.0/ah/feed.rdf"
NS = {"rss": "http://purl.org/rss/1.0/",
      "dc": "http://purl.org/dc/elements/1.1/"}

# セール・価格情報とみなして基本除外する語 (タイトル判定)
SALE_WORDS = ["セール", "SALE", "お買い得", "お得", "値下げ", "割引",
              "クーポン", "最安", "特価", "還元", "ブラックフライデー",
              "BLACK FRIDAY", "価格情報", "プライスダウン"]
# 新製品らしさの語 (優先スコア)
NEW_WORDS = ["発売", "発表", "登場", "予約開始", "予約受付", "リリース",
             "販売開始", "投入", "新モデル", "新製品", "新ブランド"]
# 偏り対策のカテゴリ判定 (タイトルに含まれる語 → 系統)
CATEGORIES = {
    "マウス": ["マウス", "トラックボール"],
    "キーボード": ["キーボード", "キーキャップ"],
    "モニター": ["モニター", "ディスプレイ"],
    "PCケース": ["PCケース", "ケース"],
    "ストレージ": ["SSD", "HDD", "メモリカード", "USBメモリ"],
    "メモリ": ["メモリ", "DRAM"],
    "GPU": ["グラフィック", "ビデオカード", "GPU", "GeForce", "Radeon"],
    "マザーボード": ["マザーボード"],
    "CPU": ["CPU", "プロセッサ"],
    "ノートPC": ["ノートPC", "ノートパソコン"],
    "ミニPC": ["ミニPC", "小型PC"],
    "スマホ・タブレット": ["スマホ", "スマートフォン", "タブレット"],
    "オーディオ": ["イヤホン", "ヘッドホン", "スピーカー"],
    "ゲーム機・周辺": ["ゲームパッド", "コントローラー", "ゲーム機"],
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "radio-akiba"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch_items() -> list[dict]:
    """フィードを取り、{title, link, date, description} の一覧を返す。"""
    root = ET.fromstring(get(FEED_URL).encode())
    items = []
    for it in root.findall("rss:item", NS):
        title = (it.findtext("rss:title", "", NS) or "").strip()
        link = (it.findtext("rss:link", "", NS) or "").strip()
        if title and link:
            items.append({
                "title": title, "link": link,
                "date": (it.findtext("dc:date", "", NS) or "").strip(),
                "description": (it.findtext("rss:description", "", NS)
                                or "").strip(),
            })
    return items


def is_sale(title: str) -> bool:
    return any(w in title for w in SALE_WORDS)


def new_score(title: str) -> int:
    return sum(1 for w in NEW_WORDS if w in title)


def category(title: str) -> str:
    for cat, words in CATEGORIES.items():
        if any(w in title for w in words):
            return cat
    return "その他"


def select(items: list[dict], used: set[str], n: int = 2) -> list[dict]:
    """新製品優先・セール除外・未使用・カテゴリ非重複で n 本選ぶ。

    条件を満たす候補が足りなければ、カテゴリ重複を許して埋める
    (セール除外と未使用だけは崩さない)。
    """
    cands = [it for it in items
             if it["link"] not in used and not is_sale(it["title"])]
    cands.sort(key=lambda it: -new_score(it["title"]))  # 同点はフィード順
    picked: list[dict] = []
    seen_cat: set[str] = set()
    for it in cands:
        if len(picked) >= n:
            break
        cat = category(it["title"])
        if cat in seen_cat and cat != "その他":
            continue
        picked.append(it)
        seen_cat.add(cat)
    if len(picked) < n:  # カテゴリ重複を許して埋める
        for it in cands:
            if len(picked) >= n:
                break
            if it not in picked:
                picked.append(it)
    return picked


class _P(HTMLParser):
    """make_news.article_body と同じ <p> 抽出 (依存を増やさないため複製)。"""

    def __init__(self):
        super().__init__()
        self.in_p = False
        self.texts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.in_p = True

    def handle_endtag(self, tag):
        if tag == "p":
            self.in_p = False
            self.texts.append("\n")

    def handle_data(self, data):
        if self.in_p:
            self.texts.append(data)


def article_body(url: str, limit: int = 2200) -> str:
    p = _P()
    p.feed(get(url))
    body = re.sub(r"\n{2,}", "\n", "".join(p.texts)).strip()
    return body[:limit]


def pick_with_bodies(used: set[str], n: int = 2) -> list[dict]:
    """選別して本文まで付けた記事リストを返す (本文が取れたものだけ)。"""
    out = []
    for it in select(fetch_items(), used, n):
        try:
            body = article_body(it["link"])
        except Exception:
            continue
        if len(body) < 200:  # 本文が薄い記事は素材にしない
            continue
        out.append({**it, "body": body})
    return out


if __name__ == "__main__":
    items = fetch_items()
    print(f"feed: {len(items)} items")
    for it in select(items, set()):
        print(f"- [{category(it['title'])}] {it['title']}")
        print(f"  {it['link']}")
