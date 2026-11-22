#!/usr/bin/env python3
"""ネルラジニュース（昼）の原稿生成（試作）。

NHK と ITmedia の RSS から見出しを取り、深堀り候補の記事本文を
スクレイピングして素材にし、LLM にニュース原稿を書かせる。
後処理で読み辞書（ガジェットマニア共通部品）をかけ、英字の残りを報告する。

使い方:
  python3 py/tools/make_news.py --out-dir test/news_trial1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "py/tools"))

import gadget_check as gc  # noqa: E402
import make_program as mp  # noqa: E402

FEEDS = [("NHK", "https://www.nhk.or.jp/rss/news/cat0.xml", 5),
         ("ITmedia", "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", 8)]


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "radio-news"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


class P(HTMLParser):
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


def article_body(url: str, limit: int = 1800) -> str:
    p = P()
    p.feed(get(url))
    body = re.sub(r"\n{2,}", "\n", "".join(p.texts)).strip()
    return body[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "test/news_trial1"))
    ap.add_argument("--time-label", default="お昼の12時",
                    help="放送時刻の言い方（例: 午前10時、午後1時）")
    ap.add_argument("--exclude-file",
                    help="深堀りで避けるタイトル一覧 (JSON)。当日使い回し防止")
    ap.add_argument("--chosen-file",
                    help="深堀りに選んだタイトルを書き出す先 (JSON)")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    exclude = set()
    if args.exclude_file and Path(args.exclude_file).exists():
        exclude = set(json.loads(
            Path(args.exclude_file).read_text(encoding="utf-8")))

    headlines, deep = [], []
    for source, url, take in FEEDS:
        root = ET.fromstring(get(url).encode())
        items = root.findall(".//item")[:take]
        for it in items:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if title and link:
                headlines.append({"source": source, "title": title,
                                  "link": link})
        # 深堀りは未使用の先頭2件の本文を取る (使い回し防止)
        picked = 0
        for it in items:
            if picked >= 2:
                break
            link = (it.findtext("link") or "").strip()
            title = (it.findtext("title") or "").strip()
            if not title or title in exclude:
                continue
            try:
                deep.append({"source": source, "title": title,
                             "body": article_body(link)})
                picked += 1
                print(f"[deep] {source}: {title[:30]} "
                      f"({len(deep[-1]['body'])} chars)", flush=True)
            except Exception as e:
                print(f"[deep] {source} failed: {e}", flush=True)
    if args.chosen_file:
        Path(args.chosen_file).write_text(
            json.dumps([d["title"] for d in deep], ensure_ascii=False),
            encoding="utf-8")
    print(f"[materials] headlines={len(headlines)} deep={len(deep)}",
          flush=True)
    (out / "materials.json").write_text(
        json.dumps({"headlines": headlines, "deep": deep},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    hl_text = "\n".join(f"- [{h['source']}] {h['title']}" for h in headlines)
    deep_text = "\n\n".join(
        f"### [{d['source']}] {d['title']}\n{d['body']}" for d in deep)
    tpl = (ROOT / "prompts/steps/news-program.md").read_text(encoding="utf-8")
    prompt = (tpl.replace("{時刻}", args.time_label)
              .replace("{ヘッドライン}", hl_text)
              .replace("{深堀り素材}", deep_text))
    script = mp.strip_fence(mp.call_llm(prompt, 8192))
    # （ヘッドライン）のような見出し行が混ざることがあるので機械的に落とす
    script = "\n".join(
        ln for ln in script.splitlines()
        if not ln.strip()
        or re.match(r"^(めたん|つむぎ|ずんだもん):", ln))

    blocks = gc.parse_common(str(ROOT / "prompts/parts/gadget-common.md"))
    entries, unify = gc.dict_from_common(blocks)
    script = gc.apply_dictionary(script, entries, unify)

    # ニュースは固有名詞が多いので、残った英字は LLM に読みを付けさせて
    # もう一度辞書をかける (ガジェットマニアの自動解決と同じ考え方)
    left = sorted(set(re.findall(r"[A-Za-z]{2,}", script)))
    if left:
        script_lines = script.splitlines()
        items = []
        for w in left:
            hit = next((ln for ln in script_lines if w in ln), "")
            items.append(f"- {w}（使用例: {hit[:80]}）")
        prompt_r = mp.RESOLVE_PROMPT.replace("{単語リスト}",
                                             "\n".join(items))
        try:
            data = json.loads(mp.strip_fence(mp.call_llm(prompt_r, 2000)))
        except ValueError:
            data = []
        pairs = []
        for item in data if isinstance(data, list) else []:
            term = str(item.get("term", "")).strip()
            kana = str(item.get("kana", "")).strip()
            if (term and term in script
                    and re.fullmatch(r"[ァ-ヶー・]+", kana)):
                pairs.append((term, kana))
        if pairs:
            script = gc.apply_dictionary(script, entries + pairs, unify)
            general = [p for p in pairs if mp.is_general_term(p[0])]
            if general:
                mp.append_to_common_dictionary(general)
            print(f"[resolve] {len(pairs)} words resolved "
                  f"({len(general)} added to dictionary)", flush=True)
    (out / "news_program.txt").write_text(script, encoding="utf-8")

    lines = [ln for ln in script.splitlines() if ln.strip()]
    bad_label = [ln for ln in lines
                 if not re.match(r"^(めたん|つむぎ|ずんだもん):", ln)]
    ascii_left = sorted(set(re.findall(r"[A-Za-z]{2,}", script)))
    print(f"[done] {len(script)} chars, {len(lines)} lines, "
          f"bad_label={len(bad_label)}, ascii_left={ascii_left}")


if __name__ == "__main__":
    main()
