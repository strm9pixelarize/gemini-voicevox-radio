#!/usr/bin/env python3
"""ブログトークの原稿生成（セクション分割方式）。

1回の LLM 呼び出しでは長尺が出ないため、ガジェットマニアと同じく
セクションごとに分けて生成し、最後に結合する。

処理の流れと、対応するプロンプト (prompts/steps/):
  1. 素材抽出    blog-talk-extract.md  記事 → 素材JSON (あらまし/山3つ/読み)
  2. オープニング blog-talk-opening.md  挨拶・記事紹介・山の予告
  3. 深掘り ×3   blog-talk-deep.md     山ごとに1回ずつ呼ぶ
  4. クロージング blog-talk-closing.md  感想戦と締め
  5. 結合 → 読み辞書 → 英字の自動解決 (ネルラジニュースと同じ後処理)

出力 (out-dir):
  materials.json           抽出した素材
  section_opening.txt / section_deep1..3.txt / section_closing.txt
  blog_talk_full.txt       結合直後
  blog_talk_program.txt    最終版 (run_blog_job.py が音声化する)

使い方:
  python3 py/tools/make_blog_talk.py --out-dir test/blog_talk_trial2 \
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
LABEL_RE = re.compile(r"^(めたん|つむぎ|ずんだもん):")


def fill(template: str, **vars: str) -> str:
    out = template
    for k, v in vars.items():
        out = out.replace("{" + k + "}", v)
    return out


def label_lines(text: str) -> str:
    """話者ラベルの行だけ残す（見出し等の混入対策）。"""
    return "\n".join(
        ln for ln in text.splitlines()
        if not ln.strip() or LABEL_RE.match(ln))


def last_turns(script: str, n: int = 2) -> str:
    turns = [ln for ln in script.splitlines() if ln.strip()]
    return "\n\n".join(turns[-n:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "test/blog_talk_trial2"))
    ap.add_argument("--article-json", required=True,
                    help="ブログ記事の JSON (title/date/content/url)")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    steps = ROOT / "prompts/steps"

    article = json.loads(Path(args.article_json).read_text(encoding="utf-8"))
    title = article.get("title", "ブログ記事")
    date = article.get("date", "")
    content = article.get("content", "")[:CONTENT_LIMIT]
    print(f"[materials] article: {title} ({date}) {len(content)} chars",
          flush=True)

    blocks = gc.parse_common(str(ROOT / "prompts/parts/gadget-common.md"))
    entries, unify = gc.dict_from_common(blocks)

    def conv(t: str) -> str:
        return gc.apply_dictionary(t, entries, unify)

    # --- 1. 素材抽出 ---
    tpl = (steps / "blog-talk-extract.md").read_text(encoding="utf-8")
    prompt = fill(tpl, 記事タイトル=title, 記事の日付=date, 記事本文=content)
    materials = None
    for attempt in range(2):
        try:
            materials = json.loads(mp.strip_fence(mp.call_llm(prompt, 4000)))
            break
        except ValueError:
            print(f"[extract] JSON parse failed (attempt {attempt + 1})",
                  flush=True)
    if not isinstance(materials, dict) or not materials.get("mountains"):
        raise RuntimeError("material extraction failed")
    mountains = materials["mountains"][:3]
    summary = str(materials.get("summary", ""))
    # 抽出された読みは、この生成限りの辞書として足す
    known = {t for t, _ in entries}
    for r in materials.get("readings", []):
        term, kana = str(r.get("term", "")), str(r.get("kana", ""))
        if (term and term not in known
                and re.fullmatch(r"[ァ-ヶー・]+", kana)):
            entries.append((term, kana))
            known.add(term)
    entries.sort(key=lambda p: -len(p[0]))
    (out / "materials.json").write_text(
        json.dumps(materials, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"[extract] mountains={[m.get('title') for m in mountains]}",
          flush=True)

    # --- 2. オープニング ---
    tpl = (steps / "blog-talk-opening.md").read_text(encoding="utf-8")
    prompt = fill(tpl, 記事タイトル=title, あらまし=summary,
                  山タイトル一覧="、".join(
                      str(m.get("title", "")) for m in mountains))
    sections: dict[str, str] = {}
    sections["opening"] = conv(label_lines(
        mp.strip_fence(mp.call_llm(prompt, 3000))))
    print(f"[section] opening ({len(sections['opening'])} chars)", flush=True)

    # --- 3. 深掘り ×3 ---
    tpl = (steps / "blog-talk-deep.md").read_text(encoding="utf-8")
    prev = last_turns(sections["opening"])
    for i, mtn in enumerate(mountains, start=1):
        prompt = fill(tpl, 記事タイトル=title,
                      山タイトル=str(mtn.get("title", "")),
                      山の素材=str(mtn.get("detail", "")),
                      直前の行=prev)
        body = conv(label_lines(
            mp.strip_fence(mp.call_llm(prompt, 6000))))
        sections[f"deep{i}"] = body
        prev = last_turns(body)
        print(f"[section] deep{i} ({len(body)} chars)", flush=True)

    # --- 4. クロージング ---
    talked = "\n".join(
        f"- {m.get('title', '')}: {str(m.get('detail', ''))[:120]}"
        for m in mountains)
    tpl = (steps / "blog-talk-closing.md").read_text(encoding="utf-8")
    prompt = fill(tpl, 記事タイトル=title, 話した内容=talked, 直前の行=prev)
    sections["closing"] = conv(label_lines(
        mp.strip_fence(mp.call_llm(prompt, 3000))))
    print(f"[section] closing ({len(sections['closing'])} chars)", flush=True)

    for name, body in sections.items():
        (out / f"section_{name}.txt").write_text(body, encoding="utf-8")

    # --- 5. 結合と後処理 ---
    order = (["opening"] + [f"deep{i}" for i in range(1, len(mountains) + 1)]
             + ["closing"])
    script = "\n\n".join(sections[k].strip() for k in order) + "\n"
    (out / "blog_talk_full.txt").write_text(script, encoding="utf-8")
    print(f"[assemble] {len(script)} chars", flush=True)

    script = gc.apply_dictionary(script, entries, unify)
    # 残った英字は LLM に読みを付けさせてもう一度辞書をかける
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
    bad_label = [ln for ln in lines if not LABEL_RE.match(ln)]
    ascii_left = sorted(set(re.findall(r"[A-Za-z]{2,}", script)))
    print(f"[done] {len(script)} chars, {len(lines)} lines, "
          f"bad_label={len(bad_label)}, ascii_left={ascii_left}")


if __name__ == "__main__":
    main()
