"""長編番組の通し生成 (Phase 2).

フロー: ネタ出し (お題ごと) → ブログ抽出 → セクション生成
(OP/お題×3/ピックアップ/ED) → 固定文を「番組の並び」の順に
差し込んで結合 → 読み辞書を全体に適用 → 機械チェック
(gadget_check) → fix ループ (最大 --fix-rounds 周、既定3)。
fix のあとは固定文ガードで、書き換えられた固定文を結合時の
文面に復元してから再チェックする。

- 共通部品は prompts/parts/gadget-common.md の ## ブロックを
  {共通:名前} へ差し込む (# コメント行は除く)
- 読み辞書は素材を渡す前と、生成された台本の両方に適用する。
  置き換えは長い語から順に、英字の語は前後が英字でないときだけ
- 表記の統一は、目標の表記になっていない場合だけ置き換える

出力:
  gadget_program_raw.txt    結合直後 (辞書適用前)
  gadget_program_full.txt   辞書適用後 (fix ループの入力)
  gadget_program_fixed.txt  fix ループ後の最終版
  fix_prompt_round{N}.txt   各周の修正プロンプト
  gadget_program_round{N}.txt 各周の修正結果
  materials.json            チェッカー照合用 (お題/記事タイトル/
                            readings/お題の開始行)

Usage:
  python3 tools/make_program.py --out-dir ../../test/program_trial3 \
      [--article-json article.json] [--fix-rounds 3]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path.home() / ("workspace/custom-connectors/custom.anthropic/"
                        "bin/anthropic_api.py")
MODEL = os.environ.get("RADIO_MODEL", "claude-haiku-5-5")  # 2026-11-18 夜、対策（辞書底上げ・fix 行番号除去・再試行）込みで trial14 が ERROR 0・166秒で完走したためメインを 5.5 に切替。RADIO_MODEL で差し替え可能

TOPICS = [
    "ロジックアナライザでI2C/SPIを覗く",
    "ネステッド仮想化で入れ子のVM",
    "部品を安く買う電子部品通販の使い分け",
]
PICKUP_TITLE = "サイトのロゴをAIと作ったら、自分の元案に帰ってきた話"
PICKUP_MEMO = (
    "ブログ記事（2026-11-16）。サイトのロゴ作りの記録。手書き"
    "スケッチを幾何学化する案をAIと量産したが、最終的には書き手"
    "自身の以前の元案（ハッシュ記号の内部に縦線と対角線でNの形を"
    "描いた白ベタのシンボル）が本命と判明し、それを清書した版を"
    "採用した。ファビコンは、N入りのハッシュを主役に、右下に"
    "大きなリボンのA、左下に5本のアスタリスクを置いた角丸"
    "アイコン。ブログ用とラジオ用の派生ファビコンも作った。"
)
TIME = "3時45分"
GREETING = "こんばんは"


def load_blocks() -> dict[str, str]:
    text = (ROOT / "prompts/parts/gadget-common.md").read_text()
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                blocks[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "\n".join(buf).strip()
    for name, body in blocks.items():
        lines = [ln for ln in body.splitlines()
                 if not ln.startswith("#")
                 and not (ln.startswith("（") and ln.endswith("）"))]
        blocks[name] = "\n".join(lines).strip()
    return blocks


def _pairs(block_body: str, sep: str) -> list[tuple[str, str]]:
    pairs = []
    for line in block_body.splitlines():
        m = re.match(r"- (.+?)\s*" + re.escape(sep) + r"\s*(.+)", line.strip())
        if m:
            for key in m.group(1).split(" / "):
                pairs.append((key.strip(), m.group(2).strip()))
    return pairs


def load_dictionary(blocks: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(_pairs(blocks["読み辞書"], "="),
                  key=lambda p: -len(p[0]))


def load_notation(blocks: dict[str, str]) -> list[tuple[str, str]]:
    return _pairs(blocks.get("表記の統一", ""), "→")


def apply_replacements(text: str, pairs: list[tuple[str, str]],
                       notation: list[tuple[str, str]]) -> str:
    for src, dst in pairs:
        if re.fullmatch(r"[\x00-\x7F]+", src):
            text = re.sub(r"(?<![A-Za-z])" + re.escape(src) +
                          r"(?![A-Za-z])", dst, text)
        else:
            text = text.replace(src, dst)
    for src, dst in notation:
        if dst.startswith(src):
            suffix = dst[len(src):]
            text = re.sub(re.escape(src) + r"(?!" + re.escape(suffix) +
                          r")", dst, text)
        else:
            text = text.replace(src, dst)
    return text


def fill(template: str, blocks: dict[str, str], **vars: str) -> str:
    out = template
    for name, body in blocks.items():
        out = out.replace("{共通:" + name + "}", body)
    for k, v in vars.items():
        out = out.replace("{" + k + "}", v)
    return out


PROVIDER = os.environ.get("RADIO_LLM", "anthropic")
GEMINI_HELPER = Path.home() / ("workspace/custom-connectors/custom.google-gemini/"
                               "bin/gemini_api.py")
GEMINI_MODEL = "gemini-3.8-flash"


def _call_anthropic_direct(prompt: str, budget: int) -> tuple[str, str]:
    """ANTHROPIC_API_KEY がある環境（コンテナ等）では API を直接叩く。"""
    import urllib.request
    body = json.dumps({
        "model": MODEL, "max_tokens": budget,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        d = json.loads(resp.read())
    for b in d.get("content", []):
        if b.get("type") == "text":
            return b["text"].strip(), str(d.get("stop_reason"))
    return "", str(d.get("stop_reason"))


def _call_once(prompt: str, budget: int) -> tuple[str, str]:
    """LLM を1回呼んで (本文, 終了理由) を返す。本文が無い場合は ("", 理由)"""
    if PROVIDER != "gemini" and os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic_direct(prompt, budget)
    if PROVIDER == "gemini":
        p = subprocess.run(
            [sys.executable, str(GEMINI_HELPER), "generate",
             "--model", GEMINI_MODEL, "--max-tokens", str(budget),
             "--prompt", prompt, "--thinking-level", "LOW"],
            capture_output=True, text=True, timeout=900)
        if p.returncode != 0:
            raise RuntimeError(f"LLM call failed: {p.stderr[-500:]}")
        d = json.loads(p.stdout)
        cands = d.get("candidates") or []
        if not cands:
            return "", f"no candidates: {d.get('promptFeedback')}"
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(pt.get("text", "") for pt in parts
                       if not pt.get("thought"))
        return text.strip(), str(cands[0].get("finishReason"))
    p = subprocess.run(
        [sys.executable, str(HELPER), "messages", "--model", MODEL,
         "--max-tokens", str(budget), "--prompt", prompt,
         "--thinking", "disabled"],
        capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise RuntimeError(f"LLM call failed: {p.stderr[-500:]}")
    d = json.loads(p.stdout)
    # Sonnet 系は thinking ブロックが先に返ることがあるので、text ブロックを探す
    for b in d.get("content", []):
        if b.get("type") == "text":
            return b["text"].strip(), str(d.get("stop_reason"))
    return "", str(d.get("stop_reason"))


def call_llm(prompt: str, max_tokens: int) -> str:
    # thinking が予算を食い切ると本文が出ないことがある。その場合は
    # 予算を広げて1回だけ再試行する。Gemini の 503 (需要過多) は
    # 少し待って最大3回まで再試行する
    reason = ""
    for budget in (max_tokens, min(max_tokens * 3, 32768)):
        text = ""
        for attempt in range(4):
            try:
                text, reason = _call_once(prompt, budget)
                break
            except RuntimeError as e:
                if PROVIDER == "gemini" and "503" in str(e) and attempt < 3:
                    time.sleep(45)
                    continue
                raise
        if text:
            return text
        if reason not in ("max_tokens", "MAX_TOKENS"):
            break
    raise RuntimeError(f"no text in response: reason={reason}")


RESOLVE_PROMPT = """あなたは読み辞書の編集者です。ラジオ番組の台本に英字のまま残っている語について、読み上げ用のカタカナ読みを決めてください。

# 対象（語と、使用例の行）
{単語リスト}

# ルール
- 出力はJSON配列のみ。前置き・説明は書かない: [{"term": "台本に現れる表記そのもの", "kana": "カタカナ読み"}]
- 頭文字を1文字ずつ読む略語（LED、SIMなど）は、その読みにする
- 対象が単語の断片の場合は、使用例の行から元の単語・型番全体を term にする（例:「BASE」→「1000BASE-T」、「L」→「SO-01L」）
- term には数字や記号を含めてよいが、kana はカタカナのみにする（数字は読みに含めない。例: 1000BASE-T → センベースティー）
- 読みが判断できない語は含めない
"""


def unknown_words(report) -> list[str]:
    """チェック結果の E02 から、未登録の英字語を集める"""
    words: list[str] = []
    for f in report.findings:
        if f.code != "E02":
            continue
        body = f.message.split(": ", 1)[1] if ": " in f.message else ""
        for w in body.split("、"):
            w = w.strip()
            if w and w not in words:
                words.append(w)
    return words


def resolve_unknown_words(text: str, report) -> list[tuple[str, str]]:
    """未登録語について、LLM に文脈つきで読みを決めさせる"""
    words = unknown_words(report)
    if not words:
        return []
    lines = text.splitlines()
    items = []
    for w in words:
        hit = next((ln for ln in lines if w in ln), "")
        items.append(f"- {w}（使用例: {hit[:80]}）")
    prompt = RESOLVE_PROMPT.replace("{単語リスト}", "\n".join(items))
    try:
        data = json.loads(strip_fence(call_llm(prompt, 2000)))
    except ValueError:
        return []
    added: list[tuple[str, str]] = []
    for item in data if isinstance(data, list) else []:
        term = str(item.get("term", "")).strip()
        kana = str(item.get("kana", "")).strip()
        if (term and term in text and term not in dict(added)
                and re.fullmatch(r"[ァ-ヶー・]+", kana)):
            added.append((term, kana))
    return added


def is_general_term(term: str) -> bool:
    """恒常辞書に残すのは一般語彙だけにする（略語・英単語・単位）。
    型番や記事固有の固有名（D6b、SO-01L のような英数字混在）は番組限り。"""
    return bool(re.fullmatch(r"[A-Z]{2,}|[A-Za-z]{2,}", term)) or term in {"W"}


def append_to_common_dictionary(pairs: list[tuple[str, str]]) -> None:
    """自動解決した読みを、共通部品の読み辞書の末尾に追記する"""
    path = ROOT / "prompts/parts/gadget-common.md"
    lines = path.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "## 読み辞書")
    last = None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            break
        if re.match(r"^- .+ = .+$", lines[i].strip()):
            last = i
    if last is None:
        return
    lines[last + 1:last + 1] = [f"- {t} = {k}" for t, k in pairs]
    path.write_text("\n".join(lines) + "\n")


def strip_fence(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def restore_fixed_lines(before: str, after: str, fixed_list) -> tuple[str, list]:
    """fix で書き換え・削除された固定文を、結合時の文面に復元する。

    戻り値: (復元後のテキスト, [(復元した固定文, 行番号), ...])
    似た行があれば置き換え、無ければ次の固定文の直前に挿入する。
    """
    import difflib
    from collections import Counter

    import gadget_check as gc

    b = gc.parse_lines(before.splitlines())
    gc.mark_fixed(b, fixed_list, gc.Report())
    expected = [l.raw for l in b if l.fixed]

    a_raw = after.splitlines()
    counts = Counter(a_raw)
    missing = []
    for raw in expected:
        if counts[raw] > 0:
            counts[raw] -= 1
        else:
            missing.append(raw)

    restored = []
    exp_set = set(expected)
    for raw in missing:
        best_i, best_r = -1, 0.0
        for i, cand in enumerate(a_raw):
            if cand in exp_set or not cand.strip():
                continue
            r = difflib.SequenceMatcher(None, cand, raw).ratio()
            if r > best_r:
                best_i, best_r = i, r
        if best_i >= 0 and best_r >= 0.5:
            a_raw[best_i] = raw
            exp_set.add(raw)
            restored.append((raw, best_i + 1))
            continue
        insert_at = len(a_raw)
        pos = expected.index(raw)
        for nxt in expected[pos + 1:]:
            if nxt in a_raw:
                insert_at = a_raw.index(nxt)
                break
        a_raw[insert_at:insert_at] = [raw, ""]
        exp_set.add(raw)
        restored.append((raw, insert_at + 1))
    return "\n".join(a_raw).strip() + "\n", restored


def last_turns(script: str, n: int = 2) -> str:
    turns = [ln for ln in script.splitlines() if ln.strip()]
    return "\n\n".join(turns[-n:])


def main() -> int:
    global TOPICS, TIME, GREETING
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "test/program_trial3"))
    ap.add_argument("--article-json",
                    help="ブログ記事の JSON (title/date/content)。"
                         "あれば抽出プロンプトを使う")
    ap.add_argument("--akiba-json",
                    help="AKIBAピックアップ用記事の JSON "
                         "([{title/link/date/body} ×2])。"
                         "あればアキバピックアップのコーナーを生成する")
    ap.add_argument("--topics-json",
                    help="お題の JSON {topics: [3件], time, greeting}。"
                         "あれば既定のお題を差し替える")
    ap.add_argument("--fix-rounds", type=int, default=3,
                    help="fix ループの最大周数 (0 で無効、既定3)")
    ap.add_argument("--extra-dict",
                    help="番組限りの単語登録ファイル（単語シートの JSON）。"
                         "共通辞書に足して、この生成だけに使う")
    args = ap.parse_args()
    if args.topics_json:
        cfg = json.loads(Path(args.topics_json).read_text())
        TOPICS = cfg["topics"]
        TIME = cfg.get("time", TIME)
        GREETING = cfg.get("greeting", GREETING)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    blocks = load_blocks()
    pairs = load_dictionary(blocks)
    notation = load_notation(blocks)
    if args.extra_dict:
        # 単語シートを、お題タイトルの読み変換（conv）にも効かせる。
        # これをしないと固定文のお題紹介と materials のタイトルがずれて E05 になる
        _known = {t for t, _ in pairs}
        for item in json.loads(Path(args.extra_dict).read_text()):
            term, kana = item.get("term", ""), item.get("kana", "")
            if term and kana and term not in _known:
                pairs.append((term, kana))
                _known.add(term)
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
    steps = ROOT / "prompts/steps"

    def conv(t: str) -> str:
        return apply_replacements(t, pairs, notation)

    # --- 1. ネタ出し (お題) ---
    ideation_tpl = (steps / "ideation.md").read_text()
    materials: dict[str, str] = {}
    for i, topic in enumerate(TOPICS):
        prompt = fill(ideation_tpl, blocks, お題=topic, お題メモ="なし")
        raw = strip_fence(call_llm(prompt, 2500))
        materials[f"topic{i+1}"] = conv(raw)
        (out / f"ideation_topic{i+1}.json").write_text(materials[f"topic{i+1}"])
        print(f"[ideation] topic{i+1} done", flush=True)

    # --- 2. ブログ素材 ---
    article_published = ""
    if args.article_json:
        extract_tpl = (steps / "blog-extract.md").read_text()
        article = Path(args.article_json).read_text()
        try:
            article_published = json.loads(article).get("date", "")
        except ValueError:
            article_published = ""
        prompt = fill(extract_tpl, blocks, 記事JSON=article)
        raw = strip_fence(call_llm(prompt, 4000))
        materials["pickup"] = conv(raw)
        print("[extract] blog done", flush=True)
    else:
        prompt = fill(ideation_tpl, blocks,
                      お題=f"ブログ記事の紹介：{PICKUP_TITLE}",
                      お題メモ=PICKUP_MEMO)
        raw = strip_fence(call_llm(prompt, 2500))
        materials["pickup"] = conv(raw)
        print("[ideation] pickup (memo fallback) done", flush=True)
    (out / "material_pickup.json").write_text(materials["pickup"])

    # --- 2.5 AKIBAピックアップ素材 ---
    akiba_titles: list[str] = []
    if args.akiba_json and Path(args.akiba_json).exists():
        extract_tpl = (steps / "akiba-extract.md").read_text()
        akiba_raw = Path(args.akiba_json).read_text()
        prompt = fill(extract_tpl, blocks, 記事JSON=akiba_raw)
        raw = strip_fence(call_llm(prompt, 6000))
        materials["akiba"] = conv(raw)
        (out / "material_akiba.json").write_text(materials["akiba"])
        try:
            for a in json.loads(materials["akiba"]).get("articles", []):
                akiba_titles.append(a.get("title_spoken") or a.get("title", ""))
        except (ValueError, AttributeError):
            akiba_titles = []
        print(f"[extract] akiba done ({len(akiba_titles)} articles)",
              flush=True)

    # --- 固定文 (番組の並び順) ---
    topic_titles = [conv(t).replace("/", "と") for t in TOPICS]
    pickup_title = conv(PICKUP_TITLE)
    try:
        _pj = json.loads(materials["pickup"])
        if _pj.get("title_spoken"):
            pickup_title = _pj["title_spoken"]
    except (ValueError, AttributeError):
        pass
    # 固定文は gadget-common.md の「固定文」を正とする (ここに直書きしない)。
    # チェッカーと同じパーサで読み、{挨拶} {時刻} {お題N} {記事タイトル}
    # を実行時の値で差し替える。
    import gadget_check as _gc
    _fx_pairs = _gc.fixed_from_common(_gc.parse_common(
        str(ROOT / "prompts/parts/gadget-common.md"))) or []
    _fx_subs = {"挨拶": GREETING, "時刻": TIME, "記事タイトル": pickup_title,
                "アキバタイトル": akiba_titles[0] if akiba_titles else ""}
    _fx_subs.update({f"お題{i}": t
                     for i, t in enumerate(topic_titles, start=1)})
    _fx_by_sub: dict[str, list[str]] = {}
    for _sub, _line in _fx_pairs:
        for _k, _v in _fx_subs.items():
            _line = _line.replace("{" + _k + "}", _v)
        _fx_by_sub.setdefault(_sub, []).append(_line)

    def _fx_one(name: str) -> str:
        if name not in _fx_by_sub:
            raise SystemExit(
                f"gadget-common.md の固定文に「{name}」がありません")
        return _fx_by_sub[name][0]

    def _fx_many(name: str) -> list[str]:
        if name not in _fx_by_sub:
            raise SystemExit(
                f"gadget-common.md の固定文に「{name}」がありません")
        return _fx_by_sub[name]

    fixed = {
        "greet": _fx_many("挨拶"),
        "time": _fx_one("時刻"),
        "show": _fx_one("番組名"),
        "topics": _fx_one("お題紹介"),
        "akiba_intro": _fx_one("アキバ紹介"),
        "blog_intro": _fx_one("ブログ紹介"),
        "blog_link": _fx_one("記事の案内"),
        "credit": _fx_one("提供"),
        "sponsors": _fx_many("スポンサー紹介"),
        "close": _fx_many("締め"),
    }

    # --- 3. セクション生成 ---
    sections: dict[str, str] = {}

    tpl = (steps / "section-opening.md").read_text()
    sections["opening"] = conv(call_llm(
        fill(tpl, blocks, 直前の行=fixed["show"],
             直後の行=fixed["topics"]), 3000))
    print("[section] opening done", flush=True)

    tpl = (steps / "section-topic.md").read_text()
    next_fixed = {1: "（次のセクションは、めたんの振りから始まります）",
                  2: "（次のセクションは、めたんの振りから始まります）",
                  3: fixed["akiba_intro"] if akiba_titles
                     else fixed["blog_intro"]}
    prev = last_turns(sections["opening"])
    for i, topic in enumerate(TOPICS, start=1):
        sections[f"topic{i}"] = conv(call_llm(
            fill(tpl, blocks, 素材JSON=materials[f"topic{i}"],
                 直前の行=prev, 直後の行=next_fixed[i], お題=topic),
            6000))
        prev = last_turns(sections[f"topic{i}"])
        print(f"[section] topic{i} done", flush=True)

    # 記事の新旧（公開から1年を過ぎていれば「古い記事」）
    article_age = "新しい記事"
    if article_published:
        try:
            pub = datetime.date.fromisoformat(article_published)
            if (datetime.date.today() - pub).days > 365:
                article_age = "古い記事"
        except ValueError:
            pass
    if akiba_titles:
        tpl = (steps / "section-akiba.md").read_text()
        sections["akiba"] = conv(call_llm(
            fill(tpl, blocks, 素材JSON=materials["akiba"],
                 直前の行=fixed["akiba_intro"],
                 直後の行=fixed["blog_intro"]), 8000))
        print("[section] akiba done", flush=True)

    tpl = (steps / "section-pickup.md").read_text()
    sections["pickup"] = conv(call_llm(
        fill(tpl, blocks, 記事素材JSON=materials["pickup"],
             直前の行=fixed["blog_intro"], 記事の新旧=article_age), 6000))
    print("[section] pickup done", flush=True)

    talked = []
    for i, topic in enumerate(TOPICS, start=1):
        try:
            pts = json.loads(materials[f"topic{i}"])["points"][:2]
        except Exception:
            pts = []
        talked.append(f"お題{i}「{topic}」：" + "／".join(pts))
    if akiba_titles:
        try:
            sums = [a.get("summary", "")
                    for a in json.loads(materials["akiba"])["articles"]]
            talked.append("アキバピックアップ：" + "／".join(sums))
        except Exception:
            talked.append("アキバピックアップ：" + "／".join(akiba_titles))
    try:
        talked.append("ブログピックアップ：" +
                      json.loads(materials["pickup"])["summary"])
    except Exception:
        talked.append(f"ブログピックアップ：{pickup_title}")
    tpl = (steps / "section-ending.md").read_text()
    sections["ending"] = conv(call_llm(
        fill(tpl, blocks, 話した内容=conv("\n".join(talked)),
             直前の行=fixed["blog_link"]), 3000))
    print("[section] ending done", flush=True)

    for name, body in sections.items():
        (out / f"section_{name}.txt").write_text(body)

    # --- 4. 結合 (番組の並び) ---
    akiba_parts = ([fixed["akiba_intro"], sections["akiba"]]
                   if akiba_titles else [])
    parts = (fixed["greet"] + [fixed["time"], fixed["show"],
                               sections["opening"], fixed["topics"],
                               sections["topic1"], sections["topic2"],
                               sections["topic3"]] + akiba_parts +
             [fixed["blog_intro"],
              sections["pickup"], fixed["blog_link"],
              sections["ending"], fixed["credit"]]
             + fixed["sponsors"] + fixed["close"])
    raw_full = "\n\n".join(p.strip() for p in parts) + "\n"
    (out / "gadget_program_raw.txt").write_text(raw_full)
    print(f"[assemble] raw ({len(raw_full)} chars)", flush=True)

    # 素材メタデータ（チェッカーの --materials / --topic-starts 用）
    flat = [p.strip() for p in parts]
    starts, pos = [], 1
    for idx, p in enumerate(flat):
        if idx in (7, 8, 9):
            starts.append(pos)
        pos += p.count("\n") + 2
    # よく知られた略語は正式名を言わない方針（共通 v7）なので、その一覧に
    # ある読みの "full" は materials から落とす（F16 と F28 の衝突回避）
    _wk = re.search(r"よく知られた略語（([^）]*)）", blocks.get("番組", ""))
    well_known = {w.strip() for w in _wk.group(1).split("、")} if _wk else set()
    merged_readings, seen_terms = [], set()
    for key in ("topic1", "topic2", "topic3", "pickup"):
        try:
            for r in json.loads(materials[key]).get("readings", []):
                if r.get("term") and r["term"] not in seen_terms:
                    seen_terms.add(r["term"])
                    r = dict(r)
                    if r.get("kana") in well_known:
                        r["full"] = ""
                    merged_readings.append(r)
        except (ValueError, AttributeError):
            pass
    if akiba_titles:  # アキバ素材の読みは記事ごとに分かれているので集約
        try:
            for a in json.loads(materials["akiba"]).get("articles", []):
                for r in a.get("readings", []):
                    if r.get("term") and r["term"] not in seen_terms:
                        seen_terms.add(r["term"])
                        r = dict(r)
                        if r.get("kana") in well_known:
                            r["full"] = ""
                        merged_readings.append(r)
        except (ValueError, AttributeError):
            pass
    (out / "materials.json").write_text(json.dumps(
        {"topics": topic_titles, "article_title": pickup_title,
         "article_published": article_published,
         "broadcast_date": datetime.date.today().isoformat(),
         "readings": merged_readings, "topic_starts": starts},
        ensure_ascii=False, indent=1))
    print(f"[materials] topic_starts={starts}", flush=True)

    # --- 5. 機械チェック + fix ループ ---
    sys.path.insert(0, str(ROOT / "py/tools"))
    import gadget_check as gc

    common_path = ROOT / "prompts/parts/gadget-common.md"
    gc_blocks = gc.parse_common(str(common_path))
    fixed_list = gc.fixed_from_common(gc_blocks) or gc.DEFAULT_FIXED
    entries, unify = gc.dict_from_common(gc_blocks)
    if args.extra_dict:
        sheet = json.loads(Path(args.extra_dict).read_text())
        known = {t for t, _ in entries}
        for item in sheet:
            term, kana = item.get("term", ""), item.get("kana", "")
            if term and kana and term not in known:
                entries.append((term, kana))
                known.add(term)
                print(f"[extra-dict] {term} = {kana}", flush=True)
    full = gc.apply_dictionary(raw_full, entries, unify)
    full_path = out / "gadget_program_full.txt"
    full_path.write_text(full)
    print(f"[dict] {full_path} ({len(full)} chars)", flush=True)

    mat = {"topics": topic_titles, "article_title": pickup_title,
           "article_published": article_published,
           "broadcast_date": datetime.date.today().isoformat(),
           "readings": merged_readings}

    def run_check(text: str):
        return gc.check(text.splitlines(), fixed_list, None, starts, mat,
                        total_chars=len(text),
                        notation=dict(unify))

    def counts_of(rep) -> tuple[int, int, int]:
        c = {lv: 0 for lv in ("ERROR", "FIX", "WARN")}
        for f in rep.findings:
            c[f.level] += 1
        return c["ERROR"], c["FIX"], c["WARN"]

    auto_added: list[tuple[str, str]] = []

    def auto_resolve(text: str, report):
        """未登録語を自動で読み解決し、辞書の追記と適用まで済ませて返す"""
        known = {t for t, _ in entries}
        added = [p for p in resolve_unknown_words(text, report)
                 if p[0] not in known]
        if not added:
            return text, report
        entries.extend(added)
        auto_added.extend(added)
        permanent = [p for p in added if is_general_term(p[0])]
        if permanent:
            append_to_common_dictionary(permanent)
        (out / "auto_readings.json").write_text(json.dumps(
            [{"term": t, "kana": k} for t, k in auto_added],
            ensure_ascii=False, indent=1))
        for t, k in added:
            scope = "辞書に追加" if (t, k) in permanent else "番組限りで解決"
            print(f"[auto-dict] {t} = {k} を{scope}", flush=True)
        text = gc.apply_dictionary(text, entries, unify)
        report, _ = run_check(text)
        return text, report

    report, lines = run_check(full)
    full, report = auto_resolve(full, report)
    full_path.write_text(full)
    gc.print_report(report, str(full_path))

    current = full
    for rnd in range(1, args.fix_rounds + 1):
        request = gc.build_fix_request(report, lines)
        todo_items = [ln for ln in request.splitlines()
                      if ln.startswith("- ") and "固定文なので" not in ln]
        if not todo_items:
            print(f"[fix] round{rnd}: 修正対象なし、ループ終了", flush=True)
            break
        prompt = gc.build_fix_prompt(str(steps / "fix.md"), request,
                                     gc.numbered_script(lines), gc_blocks)
        (out / f"fix_prompt_round{rnd}.txt").write_text(prompt)
        new_text = None
        for attempt in range(2):
            resp = call_llm(prompt, 16384)
            # 修正係が行番号つきで返してくることがあるので、先頭の [N] を落とす
            resp_lines = [re.sub(r"^\[\d+\]\s*", "", ln)
                          for ln in resp.splitlines()]
            start = next((i for i, ln in enumerate(resp_lines)
                          if gc.LABEL_RE.match(ln)), None)
            if start is not None:
                new_text = "\n".join(resp_lines[start:]).strip() + "\n"
                break
            print(f"[fix] round{rnd}: 応答に台本が含まれていない"
                  f" (試行{attempt + 1})", flush=True)
        if new_text is None:
            # 2回とも台本の形で返らなかった場合は、その周を諦めて直前の原稿を残す
            print(f"[fix] round{rnd}: 修正を諦めてループ終了", flush=True)
            break
        new_text, restored = restore_fixed_lines(current, new_text,
                                                 fixed_list)
        for raw, ln in restored:
            print(f"[fix] round{rnd}: 固定文の書き換えを復元 "
                  f"({ln}行目): {raw[:40]}…", flush=True)
        current = new_text
        (out / f"gadget_program_round{rnd}.txt").write_text(current)
        report, lines = run_check(current)
        e, f_, w = counts_of(report)
        print(f"[fix] round{rnd} done: ERROR {e} / FIX {f_} / WARN {w}",
              flush=True)

    # fix ループが英字を再混入させることがあるので、最後にもう一度辞書を通す
    polished = gc.apply_dictionary(current, entries, unify)
    if polished != current:
        current = polished
        report, lines = run_check(current)
        e, f_, w = counts_of(report)
        print(f"[dict] fix 後に辞書を再適用: ERROR {e} / FIX {f_} / WARN {w}",
              flush=True)
    # それでも残る未登録語は、自動解決にかける
    current, report = auto_resolve(current, report)

    (out / "gadget_program_fixed.txt").write_text(current)
    print("[fix] final:", flush=True)
    gc.print_report(report, str(out / "gadget_program_fixed.txt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
