#!/usr/bin/env python3
"""ブログトークの原稿生成。

ブログ記事1本を素材に、3人の座談会形式の原稿を LLM に書かせる。
後処理はネルラジニュースと同じ型：読み辞書（ガジェットマニア共通部品）を
かけ、残った英字は LLM に読みを付けさせてもう一度辞書をかける。

使い方:
  python3 py/tools/make_blog_talk.py --out-dir test/blog_talk_trial1 \
      --article-json article.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "py/tools"))

import gadget_check as gc  # noqa: E402
import make_program as mp  # noqa: E402

CONTENT_LIMIT = 7000  # プロンプトに渡す記事本文の上限 (字)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "test/blog_talk_trial1"))
    ap.add_argument("--article-json", required=True,
                    help="ブログ記事の JSON (title/date/content/url)")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    article = json.loads(Path(args.article_json).read_text(encoding="utf-8"))
    title = article.get("title", "ブログ記事")
    date = article.get("date", "")
    content = article.get("content", "")[:CONTENT_LIMIT]
    print(f"[materials] article: {title} ({date}) {len(content)} chars",
          flush=True)
    (out / "materials.json").write_text(
        json.dumps({"title": title, "date": date,
                    "url": article.get("url", "")},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    tpl = (ROOT / "prompts/steps/blog-talk.md").read_text(encoding="utf-8")
    prompt = (tpl.replace("{記事タイトル}", title)
              .replace("{記事の日付}", date)
              .replace("{記事本文}", content))
    script = mp.strip_fence(mp.call_llm(prompt, 16384))
    # 見出し行などが混ざることがあるので、話者ラベルの行だけ残す
    script = "\n".join(
        ln for ln in script.splitlines()
        if not ln.strip()
        or re.match(r"^(めたん|つむぎ|ずんだもん):", ln))

    blocks = gc.parse_common(str(ROOT / "prompts/parts/gadget-common.md"))
    entries, unify = gc.dict_from_common(blocks)
    script = gc.apply_dictionary(script, entries, unify)

    # 記事固有の固有名詞が残りやすいので、残った英字は LLM に読みを
    # 付けさせてもう一度辞書をかける (ニュースと同じ自動解決)
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
    (out / "blog_talk_program.txt").write_text(script, encoding="utf-8")

    lines = [ln for ln in script.splitlines() if ln.strip()]
    bad_label = [ln for ln in lines
                 if not re.match(r"^(めたん|つむぎ|ずんだもん):", ln)]
    ascii_left = sorted(set(re.findall(r"[A-Za-z]{2,}", script)))
    print(f"[done] {len(script)} chars, {len(lines)} lines, "
          f"bad_label={len(bad_label)}, ascii_left={ascii_left}")


if __name__ == "__main__":
    main()
