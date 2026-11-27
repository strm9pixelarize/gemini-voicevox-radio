#!/usr/bin/env python3
"""
ガジェットマニア台本 機械チェック v3.9（安定版1.3）

v3.9：安定版1.2 で生成した原稿（fixed_6）で見落とした問題・誤検出を直す
  - F13 の誤検出をなくした：めたんのツッコミ（「落ち着いてくださいまし」）を、問いかけとして扱わない
  - F26 お題の切り出しに「〜から始めましょう」を追加
  - F27 日付の漢数字（「二〇二〇年九月三日」→「2020年9月3日」。機械で直せる）
  - W20 読み上げに向かない記号に「Ω」「μ」と、数字の間のハイフン（「3-2-1」）を追加
  - W22 素材の使用場面をそのまま台詞にしたもの（「〜する場面があるのだ」）、記事の不備についての注記
        （「名前が欠けていて」「書き間違い」）、コーナー内の段取り（「二つ目の話題」「本題へ進み」）を追加
  - W32・W33 締めの言い回しに「読んでみたいな」「見てみるよ」「欲しくなっちゃった」を追加
  - W37 放送の時間帯と合わない言葉（15時の放送で「今夜」）
  - W38 オープニング・エンディングの発言数が12回を超えている
  - --apply-fix：話者ラベルのない行（E01）も「「A」を削除する」で行ごと消せるようにした

統合版（Muse 側の追加を v3.9 に再適用）：
  - 数値の単位を拡張（個・本・台・ビット・バイト・チャネル・センチ・グラム・キロ・メガ・ギガ・テラ・件・段階ほか）、「十分」の誤検出を除外
  - 繰り返し語の上限は F23、構成ラベルの混入は F29（v3.7 の F24 と衝突するため振り直し）
  - ファイル全体の文字数の下限チェック（W07、--total-min。上限は設けない）
  - F16 の照合で正式名に「表記の統一」を適用してから比べる（notation 引数）
  - レポートに話者別の発言数・ずんだもん のだ率・んです回数と、人間の確認用リスト（数値・カタカナ語）を出す

v3.8：2026-11-18 の原稿（fixed_4）で見落とした問題を拾う
  - F25 台詞の中にキャラクター名が混ざった言葉（「ズンダ・ヒーター」）
  - F26 お題の切り出しに順番の言い方（「次は」「さて、次のお題は」「今日のお題に移りましょう」）。--topic-starts が必要
  - F27 数字のカタカナ書き（「ニジュウゴメガバイト」→「25メガバイト」。機械で直せる）
  - F28 よく知られた略語に正式名を添えている（「ユーエスビー、つまりユニバーサルシリアルバス」。機械で直せる）
  - F20 同じコーナーで一字一句同じ発言を、20字未満の短い発言でも拾う（「照明も、ちょっとずつ試してみるね！」×2）
  - W32 つむぎの締めが「〜してみようかな」「〜してみるね」型
  - W33 締めのような一言のあとに発言が続いている（コーナーの終わりの蛇足）
  - W34 めたんのたしなめの相手が、直前に話した人と違う（はしゃいだのはずんだもんなのに「つむぎさん、落ち着いて」）
  - W35 エンディングで本編の説明を言い直している
  - W36 同じ正式名を2回以上言っている
  - W16 つむぎの身の上話に「うちでも」「置いといた」「あぶなかった」型を追加
  - W22 「意外な話」「意外に知られていない」「記事の細かい内容」「ボクの感想なのだ」などを追加
  - ツッコミの目印に「止めて」「止まりません」「控えて」「ほどがある」などを追加（W26・W28）
  - W31 キャラクター名（ずんだもん の「ずんだ」）を表記ゆれとして拾わない。指摘の行番号を正しくした
  - 「よく知られた略語」の一覧は、--common の共通部品から読む

v3.7：新しく出た言葉の検出
  - W30 辞書にない略語の読み：アルファベットを1文字ずつ読んだカタカナ（エスアイエム、ピーオーイー など）で、
        読み辞書にも materials の readings にもないものを一覧にする（確認して辞書に足す）
  - F24 同じ語が2回続いている（ピーオーイーピーオーイー など。「XX」を「X」にする指示を出す）
  - W31 表記ゆれ：同じ語のカタカナとひらがな（ハンダ／はんだ）、末尾の長音の有無（カテゴリ／カテゴリー）
  - つむぎの口調（W19）で「どうぞ」を「〜ぞ」として拾わない

v3.6：
  - 早口の場面の構成（W25〜W28）
    W25 早口のあとではないのに、ずんだもんが我に返っている（「はっ、失礼したのだ」だけが浮いている）
    W26 ツッコミが早口より先に入っている
    W27 お題・ブログの最後の発言がつむぎの締めになっていない（お題は --topic-starts が必要）
    W28 お題・ブログに、早口→ツッコミの場面がない（お題は --topic-starts が必要）
  - W24 ブログで、ずんだもんが記事の内容を紹介している（「記事によると」など。紹介はめたんの役）
  - 最低文字数の基準を見直し：お題・ブログとも 1500字（プロンプトの目標は 1600字のまま）
  - 早口・ツッコミの判定のしきい値は「v3.6 のしきい値」の定数にまとめた
  - 読み辞書の置き換えで、数字の直後の単位（400ppm、40Gbps）も置き換えるようにした

v3.5：
  - 発言の使い回し：生成部分に、ほぼ同じ発言が2回ある（F20 / W21）
  - 固定文の重複：生成部分に、固定文とほぼ同じ発言がある（F21。削除の指示を出す）
  - 素材メモ・見出しの漏れ：「確かめられていない」「意外な知識」など、素材の確認用メモや
    構成の見出しの言葉が台詞に出ている（W22）
  - 記事の公開日：--materials の article_published が新しいのに「事情が変わっている」と言っている（F22）、
    古いのに一言がない（W23）
  - しきい値は「v3.5 のしきい値」の定数にまとめた

v3.4：
  - です・ます調に「でしょう」を追加（ずんだもん・つむぎ）
  - 語尾の崩れ（W15）に「〜ようなのだ」（落ちようなのだ など）を追加
  - オープニングの名乗り直し（F17）に「わたくしめたんが」「ボクずんだもんは」型を追加
  - 禁止語に「お聞きいただ」「ご視聴」を追加
  - つむぎの疑問の形（W19）：「〜だよ？」「〜んだ？」「〜か？」と、
    疑問詞（なんで・どうして など）があるのに「〜んだ。」で終わる文を追加

v3.3：
  - 文字化け（�）・制御文字を ERROR（E06）
  - --apply-fix：修正指示のうち「「A」を「B」に」「全体を「X」に」「「A」を削除する」
    「N行目の直後に追加：「X」」の形を、LLMを通さずに置き換える。
    それ以外の指示（抽象的な指示）は --residual-out で、置き換え後の行番号に直した修正プロンプトにする
  - --verify-fix：LLMが修正した台本（script）を、修正前（--before）と修正指示で照合する
    （指示のない行の変化・行の消失・指示にない行の追加・指示どおりに直っていない行）
  - 数値（W08）で「一度」「一日」を拾わない

v3.2：
  - 禁止語「お聴きいただ」（「いただき」「いただいて」の両方）
  - めたんの文末の「のだ」（FIX）とタメ口（WARN）
  - つむぎの「〜のか？」「〜ぞ」「何だ。」（WARN）
  - ずんだもんの「だのだ」（FIX）
  - 読み上げに向かない記号（℃、×、かっこ など）（WARN）
  - 数値の単位に「℃」「度」「ミリ」「ギガビーピーエス」などを追加
  - --extra-fix の指示がある行は、機械の指示を外して重複させない

v3.1：禁止語（F10）の修正指示に、該当する文をそのまま入れる。数値（W08）で小数（2.4など）を正しく拾う

v3 の追加:
  - です・ます調に「ください」を追加
  - 「いい質問」の直前のつむぎの発言が「？」で終わっていなければ WARN
  - 数字・英字の前後に残った空白（「ワイファイ 7」）を WARN
  - 「〜いこうなのだ」「〜しようのだ」型の語尾の崩れを WARN
  - つむぎの「わたしの家」などを、身の上話の可能性として WARN
  - オープニングでの名乗り直しを FIX
  - --extra-fix：人が書いた修正指示を、修正プロンプトに足す
  - 記事の案内の既定値を、共通部品 v4 のアドレスに更新

v2 の追加:
  - です・ます調の判定を拡大（ました・ません・すみません など）
  - 呼び方の違反（ずんだもんの「あなた」「君」「〇〇さん」など）
  - めたんの問いかけの相手と、次の話者のずれ
  - めたんの受けの言い回し（「〜わけですね」「〜ということですね」）の重複
  - 発言回数の下限、禁止語「毎週」、「前回」など過去の放送への言及
  - 「〜のだ、〜のだ」の繰り返し（口調見本のコピー）
  - 固定文の語中の空白
  - --topic-starts：通し台本の本編を、お題ごとに分けて上限を数える
  - --materials：素材と照合（固定文のタイトル、略称を正式名より先に使っていないか）

使い方:
  # 通しの台本をチェック
  python3 gadget_check.py script.txt --common gadget_common_v7.txt

  # 読み辞書で英字を置き換えた台本を書き出してからチェック
  python3 gadget_check.py script.txt --common gadget_common_v7.txt --apply-dict script_dict.txt

  # NGの行から修正プロンプトを組み立てる
  python3 gadget_check.py script.txt --common gadget_common_v7.txt \
      --fix-template gadget_fix_prompt_v2.txt --fix-out fix_prompt.txt

  # セクション単体（お題1つ分など）をチェック
  python3 gadget_check.py topic1.txt --type topic

  # 通しの台本で、お題1〜3の開始行を渡してお題ごとに数える
  python3 gadget_check.py script.txt --common gadget_common_v7.txt --topic-starts 31,85,135

  # 素材と照合する（形式は MATERIALS_HELP を参照）
  python3 gadget_check.py script.txt --common gadget_common_v7.txt --materials materials.json

  # 修正指示を機械で適用し、適用後の台本をチェックする（残った指示は修正プロンプトにする）
  python3 gadget_check.py script.txt --common gadget_common_v7.txt \
      --apply-fix fix_prompt.txt --apply-out script_fixed.txt \
      --fix-template gadget_fix_prompt_v2.txt --residual-out fix_prompt_rest.txt

  # LLMが修正した台本を、修正前の台本と修正指示で照合してからチェックする
  python3 gadget_check.py script_llm.txt --common gadget_common_v7.txt \
      --verify-fix fix_prompt.txt --before script.txt

終了コード:
  0 = 問題なし / 1 = 修正対象または警告あり / 2 = 必ず止める問題あり

判定の種類:
  ERROR : 必ず止める（話者ラベル、英字、固定文、改行）
  FIX   : 修正プロンプトに回す（口調、回数、連続発言など）
  WARN  : 人が見て判断する（言い切り語、数値、文字数など）

標準ライブラリのみで動作します（Python 3.8 以上）。
"""
import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

SPEAKERS = ("めたん", "つむぎ", "ずんだもん", "ひまり", "はう", "トバリ")
LABEL_RE = re.compile(r"^(めたん|つむぎ|ずんだもん|ひまり|はう|トバリ): (.*)$")

# ---------------------------------------------------------------------------
# 既定値（--common を指定すると共通部品ファイルの内容で上書きされる）
# ---------------------------------------------------------------------------
DEFAULT_FIXED: List[Tuple[str, str]] = [
    ("挨拶", "めたん: {挨拶}。四国めたんです。"),
    ("挨拶", "つむぎ: {挨拶}！ 春日部つむぎだよ。"),
    ("挨拶", "ずんだもん: {挨拶}なのだ。ずんだもんなのだ。"),
    ("時刻", "めたん: 時刻は{時刻}になりました。"),
    ("番組名", "めたん: 毎時45分はガジェットマニアのお時間です。"),
    ("お題紹介", "めたん: 今日のお題は{お題1}、{お題2}、{お題3}、そして今日のブログピックアップからは{記事タイトル}について解説します！"),
    ("ブログ紹介", "めたん: 続いては今日のブログピックアップですわ。エノキ電気ニュースから届いた、{記事タイトル}という記事をご紹介します。"),
    ("記事の案内", "めたん: ご紹介した記事は、ブログ、ドット、アーキテクチュラル、エヌ、ドット、ネットでご覧いただけますので、是非見てみてください！"),
    ("提供", "めたん: 本日のガジェットマニアは、エノキ電気、全日本ダークウェブ普及協会の提供でお送りしました。"),
    ("スポンサー紹介", "めたん: エノキ電気は「自由をデザインする」をキャッチフレーズに、{*}"),
    ("スポンサー紹介", "めたん: 全日本ダークウェブ普及協会は「オニオンでええやん！」をキャッチフレーズに、{*}"),
    ("締め", "ずんだもん: 次の45分も、ニッチな沼にご招待するのだ。"),
    ("締め", "めたん: ガジェットマニアでした。お聴きいただきありがとうございました。"),
]

# 固定文のブロック名 → その固定文の後ろに続く生成セクション名
SECTION_AFTER_FIXED = {
    "挨拶": "冒頭",
    "時刻": "冒頭",
    "番組名": "OP",
    "お題紹介": "本編",
    "ブログ紹介": "ブログ",
    "語り紹介": "語り",
    "記事の案内": "ED",
    "提供": "締め",
    "スポンサー紹介": "締め",
    "締め": "締め",
}

# セクションごとの上限・下限
#   min_chars : 最低文字数（話者ラベルを除く本文）
#   dewa      : めたんの「では」始まりの上限
#   iishitsumon : 「いい質問」の上限
#   kuse      : ずんだもんの「〜ね、」「〜な、」の上限
#   min_turns : 最低発言数
#   uke       : めたんの「〜わけですね」「〜ということですね」型の受けの上限
SECTION_LIMITS = {
    "OP": dict(min_chars=400, min_turns=8, dewa=1, iishitsumon=0, kuse=2, uke=1),
    # 最低文字数は、プロンプトの目標（お題・ブログとも1600字）より少し低くしてある。
    # 重複を削ると目標をわずかに下回ることが多いため（v3.6 で見直し）
    "本編": dict(min_chars=4500, min_turns=60, dewa=3, iishitsumon=3, kuse=6, uke=3),  # お題3つ分
    "お題": dict(min_chars=1500, min_turns=20, dewa=1, iishitsumon=1, kuse=2, uke=1),
    "ブログ": dict(min_chars=1500, min_turns=20, dewa=1, iishitsumon=1, kuse=2, uke=1),
    "語り": dict(min_chars=1200, min_turns=12, dewa=0, iishitsumon=0, kuse=0, uke=0),
    "ED": dict(min_chars=500, min_turns=8, dewa=1, iishitsumon=0, kuse=2, uke=1),
    "冒頭": dict(min_chars=0, min_turns=0, dewa=0, iishitsumon=0, kuse=0, uke=0),
    "締め": dict(min_chars=0, min_turns=0, dewa=0, iishitsumon=0, kuse=0, uke=0),
    "全体": dict(min_chars=7800, min_turns=0, dewa=4, iishitsumon=2, kuse=8, uke=4),
}
TYPE_TO_SECTION = {"op": "OP", "topic": "お題", "blog": "ブログ", "ed": "ED"}


def limits_for(sec: str) -> dict:
    if sec in SECTION_LIMITS:
        return SECTION_LIMITS[sec]
    if sec.startswith("お題"):
        return SECTION_LIMITS["お題"]
    return SECTION_LIMITS["全体"]


# です・ます調の検出（かぎかっこ内の引用は除外してから判定）
#   「ました」「まして」「ましょう」「ません」「すみません」も拾う
#   「ましな（マシな）」は拾わない
DESU_MASU_RE = re.compile(r"(です|ます|まし(?=[たてょ])|ません|ください|下さい|ございま|でしょう)")
# めたんの「では」始まり（「それでは」も数える）
DEWA_RE = re.compile(r"^(それでは|では)")
# めたんの受けの言い回し（文末が「〜わけですね」「〜ということですわね」など）
UKE_RE = re.compile(r"(わけ|ということ|というわけ)(です|でございます)(わ)?(ね|よね)?$")
# 呼び方の違反（話者 → (パターン, 説明)）
NAMING_RULES = {
    "ずんだもん": [
        (re.compile(r"あなた"), "「あなた」"),
        (re.compile(r"君(?!津)"), "「君」"),
        (re.compile(r"つむぎさん"), "「つむぎさん」（正しくは「つむぎ」）"),
        (re.compile(r"めたんさん"), "「めたんさん」（正しくは「めたん」）"),
    ],
    "つむぎ": [
        (re.compile(r"ずんだもんさん"), "「ずんだもんさん」（正しくは「ずんだもん」）"),
        (re.compile(r"めたん(?!さん)"), "「めたん」（正しくは「めたんさん」）"),
    ],
    "めたん": [
        (re.compile(r"ずんだもん(?!さん)"), "「ずんだもん」（正しくは「ずんだもんさん」）"),
        (re.compile(r"つむぎ(?!さん)"), "「つむぎ」（正しくは「つむぎさん」）"),
    ],
}
# めたんの呼びかけ（「つむぎさん、」「つむぎさんは」など。「つむぎさんに」は呼びかけではない）
ADDRESS_RE = re.compile(r"(つむぎ|ずんだもん)さん(?=[、,]|は|も|って|ったら|$)")
# 問いかけ・お願いとみなす文末
ASK_ENDINGS = ("か", "かしら", "でしょう", "よね", "ください", "くださいな", "くださいまし", "のですが")
# 同じ言い回しの繰り返し（「沼が深いのだ、沼が深いのだ」）
REPEAT_RE = re.compile(r"([^、。！？]{2,}?)のだ、\1のだ")
# 存在しない過去の放送への言及（人が確認）
PAST_SHOW_WORDS = ("前回", "先週", "以前の放送", "この前の放送", "前の放送")
# 数字・英字の前後に残った空白（「ワイファイ 7」）
ALNUM_SPACE_RE = re.compile(r"(?<=[぀-ヿ一-鿿])[ 　]+(?=[0-9０-９A-Za-z])|(?<=[0-9０-９A-Za-z])[ 　]+(?=[぀-ヿ一-鿿])")
# 「〜いこうなのだ」「〜しようのだ」型の崩れ
# 「〜のようなのだ」「同じようなのだ」は正しい形なので拾わない
VOLITIONAL_RE = re.compile(r"(いこう|しよう|みよう|やろう)な?のだ|ようのだ|(?<![のなじ])ようなのだ")
# つむぎの身の上話の可能性（人が判断）
TSUMUGI_SELF_RE = re.compile(r"わたしの(家|うち|部屋|パソコン|スマホ|スマートフォン|会社|職場|学校|家族|母|父|お母さん|お父さん|親|兄|姉|弟|妹|友達)|(わたし|この前|最近)(が|も)?買った"
                             # v3.8：「うちでも」「置いといた」「あぶなかった」型（持ち物・体験を作っている）
                             r"|(?<![そのこ])うち(でも|では|の(?!ち)|に)|置いといた|置いてた|置きっぱなし|あぶなかった|まずかったかも"
                             r"|わたし(が|も)?(使って|持って)(る|た)|届いたのに|うちの子")
# 読み上げに向かない記号
SYMBOL_RE = re.compile(r"[℃×÷±%％→（）()Ωμ]|(?<=\d)[-－](?=\d)")  # v3.9：Ω、μ、「3-2-1」
# めたんのタメ口の文末
METAN_CASUAL_ENDINGS = ("んだ", "だよ", "じゃん", "だね")
# つむぎの口調の崩れ（文末）
TSUMUGI_ROUGH_ENDINGS = ("のか", "ぞ", "何だ")
TSUMUGI_OK_ENDINGS = ("どうぞ",)
# つむぎの疑問の形の崩れ（「？」込みで見る）
TSUMUGI_ROUGH_Q_RE = re.compile(r"[^。！？!?]*(?:だよ|んだ|だ|か)[？?]")
# 疑問詞があるのに「〜んだ。」で終わる文（「なんでそんなことできるんだ。」）
#   「そんなに」「こんなに」「いつも」「何も」「誰か」などは疑問詞として数えない
TSUMUGI_WH_RE = re.compile(r"(なんで|なぜ|どうして|どうやって|どこ(?![かも])|だれ(?![かも])|誰(?![かも])"
                           r"|いつ(?![かもで])|(?<![んそこあど])なに(?![かも])|何(?![かも度回]))")
# オープニングでの名乗り直し
SELF_NAME_RE = {
    "めたん": re.compile(r"めたん(です|でございます|と申します)|わたくし[、 ]?めたん"),
    "つむぎ": re.compile(r"つむぎ(です|だよ|と申します)|わたし[、 ]?つむぎ"),
    "ずんだもん": re.compile(r"ずんだもん(なのだ|です|だよ)|ボク[、 ]?ずんだもん"),
}
# ずんだもんの「〜ね、」「〜な、」（「大切な、」のような形容の「な」は拾わない）
ZUNDA_KUSE_RE = re.compile(r"(ね、|(?<=[てでどけらもしば])な、)")
# ずんだもんの文末として認める形
ZUNDA_ENDINGS = ("のだ", "のだな", "のだよ", "のだぞ", "のだね", "のか", "なのか")
# 生成部分で使ってはいけない言葉
BANNED_IN_GENERATED = {
    "ご来場": "「ご来場」は使わない（ラジオなので「お聴きいただき」）",
    "来週": "「来週」とは言わない（毎時放送のため）",
    "毎週": "「毎週」とは言わない（毎時放送のため）",
    "お聴きいただ": "お礼・お聴きいただく系の言葉は固定文と重なるので、生成部分では言わない",
    "お聞きいただ": "ラジオでは「お聴き」と書く。お聴きいただく系の言葉は固定文と重なるので、生成部分では言わない",
    "ご視聴": "ラジオなので「ご視聴」とは言わない",
    "お便り": "存在しないお便りに触れない",
    "投稿": "存在しない投稿に触れない",
    "ご質問": "存在しない質問・募集に触れない",
}
# 人が確認すべき言い切り語
ASSERTION_WORDS = ("無限", "絶対", "必ず", "不可能", "確実に", "100%", "100パーセント", "完全に")
# 数値・金額（素材にある数字か人が確認する）
NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)(ギガビーピーエス|メガビーピーエス|キロヘルツ|メガヘルツ|ギガヘルツ|ヘルツ|ミリメートル|パーセント|％|%|℃|度|円|倍|割|サンプル|ボルト|週間|か月|ヶ月|個|本|枚|台|冊|人|時|分|秒|日|年|ビット|バイト|チャネル|ミリ|センチ|メートル|グラム|キロ|メガ|ギガ|テラ|件|段階)")
# ---------------------------------------------------------------------------
# v3.5 のしきい値（調整するときはここだけ変える）
# ---------------------------------------------------------------------------
DUP_MIN_CHARS = 20          # 使い回しを調べる発言の最低文字数（「はっ、失礼したのだ。」などの短い定型を外す）
DUP_FIX_RATIO = 0.95        # これ以上似ていたら FIX（ほぼ同じ発言）
DUP_WARN_RATIO = 0.80       # これ以上似ていたら WARN（言い回しの使い回しの可能性）
DUP_SHARE = 0.80            # 短いほうの発言のこの割合以上が、そのまま相手に入っていたら FIX（一言足した使い回しも拾う）
FIXED_DUP_RATIO = 0.80      # 生成部分の発言が、固定文とこれ以上似ていたら FIX
OLD_ARTICLE_DAYS = 365      # 公開日からこの日数を過ぎた記事を「古い記事」とする（materials の old_article_days で上書き）
# 素材の確認用メモが台詞に漏れたときの言葉（ネタ出しの uncertain、事実確認の注記など）
#   普通の台詞にも出る言葉（「素材にして」「自信がない場合は」「動作確認されていない」）は拾わない
MEMO_LEAK_RE = re.compile(r"確かめられていない|(?<!動作)確認されていない|(?<!動作)確認できていない|断定はできない|断定できない"
                          r"|素材にない|素材の範囲|目安と明記|事実確認"
                          r"|記事に書いてあることではな|記事に書いてあるわけではな|ボクの感想なのだ"
                          # v3.9：素材の「使用場面」をそのまま台詞にしたもの、記事の不備についての注記
                          r"|場面があるのだ|場面が、まさに|という場面|名前が欠け|欠けていて|書き間違い|具体的には書かれていない|記事の不備")
# 構成の見出し・進行の言葉が台詞に出ているもの（プロンプトの言葉がそのまま出やすい）
HEADING_LEAK_WORDS = ("意外な知識", "つまずきやすい点", "初心者がつまずき", "要点の", "お題のコーナー",
                      "このコーナーの内容", "ここまでとさせていただきます", "お話を整理",
                      "意外な話", "意外に知られていない", "意外と知られていない", "豆知識", "記事の細かい内容",
                      # v3.9：コーナー内の段取り
                      "二つ目の話題", "続いて二つ目", "続いて三つ目", "三つ目ですわ", "本題へ進み", "本題に入り",
                      "感想をお二人に", "伺ってまいりましょう")
# 古い記事に添える一言の目印
OLD_ARTICLE_NOTE_RE = re.compile(r"事情が変わ|状況が変わ|今とは違")

# ---------------------------------------------------------------------------
# v3.6 のしきい値（早口の場面の判定）
# ---------------------------------------------------------------------------
# 今日の原稿8本で測った値：早口は180字以上がほとんど。130字台でも6文以上なら早口。
# 長い説明は190字近くでも4文以下だった
RANT_MIN_CHARS = 180        # ずんだもんの発言がこの文字数以上なら「早口の発言」とみなす
RANT_SHORT_CHARS = 130      # この文字数以上で、
RANT_SHORT_SENTS = 6        # この文の数以上でも「早口の発言」とみなす（短い文をたたみかける早口）
# ツッコミの目印（めたん・つむぎの発言）
TSUKKOMI_RE = re.compile(r"落ち着いて(?=くださ|ね|な|よ|[、。！!？?]|$)|結構ですわ|熱くな|熱が入|早口|語りすぎ|戻ってきて|そこまでで|それくらいに"
                         r"|うっとり|目が輝|興奮|キラキラ|遠くへ行|ストップ|夜はちゃんと寝|また今度|今は結構|別の機会|その話は"
                         r"|止めて|止まりません|語りが止ま|控えて|そこで一度|ほどがある|ほどほどに|きらきら|そこまでに")
# ずんだもんが我に返る目印
RECOVER_RE = re.compile(r"^はっ|失礼したのだ|申し訳ないのだ|面目ないのだ")
# ブログで、記事の内容を伝える言い方（めたんの役）
ARTICLE_REPORT_RE = re.compile(r"記事によると|記事によれば|記事では|記事に(?:出て|書いて|あ)る|記事の(?:筆者|著者)|筆者は|著者の方は")

# ---------------------------------------------------------------------------
# v3.7 新しく出た言葉の検出
# ---------------------------------------------------------------------------
# アルファベットの読み（長いものから並べる）
LETTER_NAMES = ("ダブリュー", "エックス", "エイチ", "ジェー", "キュー", "アール", "ディー", "ティー", "ゼット",
                "エー", "ビー", "シー", "イー", "エフ", "ジー", "アイ", "ケー", "エル", "エム", "エヌ", "オー",
                "ピー", "エス", "ユー", "ブイ", "ワイ")
LETTER_RUN_RE = re.compile("(?:" + "|".join(LETTER_NAMES) + "){2,}")
KATA_RUN_RE = re.compile(r"[ァ-ヴー]+")
KNOWN_KANA: List[str] = []  # 読み辞書の読み（main で --common から読み込む）
YURE_MIN_CHARS = 3          # 表記ゆれを調べる語の最低文字数

# 数値として数えない語（「一度切る」「一日中」など）
NUMBER_IGNORE = ("一度", "一日")

KATAKANA_RE = re.compile(r"[ァ-ヶー]{4,}")

LABEL_LEAK_WORDS = ("初心者がやりがちな失敗", "マニアだけが知っている小ネタ")

REPEAT_WORDS = {"めちゃくちゃ": 2, "めちゃめちゃ": 2}


def extract_numbers(text: str) -> List[str]:
    out = []
    for m in NUMBER_RE.findall(text):
        s = "".join(m)
        if s == "十分":  # 「十分に」の「十」は数値ではない
            continue
        out.append(s)
    return out


def apply_notation(text: str, notation) -> str:
    """共通部品の「表記の統一」を文字列に適用する（長いキーから）"""
    if not notation:
        return text
    pairs = notation.items() if isinstance(notation, dict) else notation
    for k, v in sorted(pairs, key=lambda kv: len(kv[0]), reverse=True):
        text = text.replace(k, v)
    return text
# 文字化け・制御文字・ゼロ幅文字
BROKEN_RE = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‍﻿]")
ASCII_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]+")
JP_CHAR = r"[぀-ヿ一-鿿]"
INNER_SPACE_RE = re.compile(rf"(?<={JP_CHAR})[ 　]+(?={JP_CHAR})")
QUOTE_RE = re.compile(r"「[^」]*」|『[^』]*』")

# ---------------------------------------------------------------------------
# v3.8 のしきい値と言葉の一覧
# ---------------------------------------------------------------------------
NAMES_RE = re.compile(r"ずんだもん|めたん|つむぎ")
# 台詞の中に、キャラクター名のカタカナが言葉の一部として混ざったもの（「ズンダ・ヒーター」）
#   「メタン」はガスの名前として出るので外す
NAME_MIX_RE = re.compile(r"[ァ-ヴー・]*(?:ズンダ|ツムギ)[ァ-ヴー・]*")
# お題の切り出しでの順番の言い方（お題の最初の、めたんの発言だけを見る）
SEQ_WORDS_RE = re.compile(r"^(さて、|それでは、|では、)?(次は|次のお題|続いて|最初のお題|一つ目|二つ目|三つ目|最後のお題)"
                          r"|今日のお題に移|次のお題に移|お題に移りま|(?<![こ何])から(?:始めましょう|始めますわ|参りましょう)")  # 「どこから始めましょうか」は振りなので外す
# 数字のカタカナ書き（「ニジュウゴメガバイト」）。位の言葉（ジュウ・ヒャク・セン・マン）を含むものだけ
KANA_DIGITS = {"イチ": 1, "ニ": 2, "サン": 3, "ヨン": 4, "ゴ": 5, "ロク": 6, "ナナ": 7, "ハチ": 8, "キュウ": 9}
KANA_UNITS = {"ジュウ": 10, "ヒャク": 100, "ビャク": 100, "ピャク": 100, "セン": 1000, "ゼン": 1000, "マン": 10000}
KANA_NUM_RE = re.compile(r"(?<![ァ-ヴー])((?:キュウ|イチ|サン|ヨン|ロク|ナナ|ハチ|ジュウ|ヒャク|ビャク|ピャク|セン|ゼン|マン|ニ|ゴ)+)"
                         r"(?=メガ|ギガ|テラ|キロ|ミリ|センチ|バイト|ビット|ワット|ボルト|ヘルツ|パーセント|件|個|円|回|年|枚|本|台|人|倍|度|分|秒|時間|日)")
# よく知られた略語（正式名を言わない）。--common の「よく知られた略語（…）」で上書きする
WELL_KNOWN_ABBR = ["ユーエスビー", "ピーシー", "オーエス", "ワイファイ", "エスエヌエス", "エルイーディー", "シム"]
FULLNAME_LINK = r"(?:、つまり|、すなわち|こと)"
FULLNAME_MIN = 8            # 正式名とみなすカタカナの最低文字数
# つむぎの締めにしてはいけない言い回し（お題 v6：「〜してみたい」「〜してみようかな」で終わらせない）
CLOSE_TRY_RE = re.compile(r"[てで]み(ようかな|るね|るよ|たい|たいな|よう|たくなっ[^。！？!?]*)[。！!？?]*$"
                          r"|欲しくなっ[^。！？!?]*[。！!？?]*$")  # v3.9：「読んでみたいな」「見てみるよ」「欲しくなっちゃった」
CLOSE_TAIL = 6              # コーナーの最後のこの発言数の中で、締めの言い回しのあとに発言が続いていたら W33
DUP_EXACT_MIN = 8           # 同じコーナーで、この文字数以上の発言が一字一句同じなら F20（短い定型も拾う）
ED_ECHO_MIN = 12            # エンディングの発言が、本編の発言とこの文字数以上つながって同じなら W35（言い直し）
ED_ECHO_KANJI = 4           # その一致の中に、漢字がこの字数以上あるときだけ（決まり文句・お題名を外す）

# ---------------------------------------------------------------------------
# v3.9 のしきい値と言葉の一覧
# ---------------------------------------------------------------------------
# 日付の漢数字（「二〇二〇年九月三日」）。アラビア数字で書く決まり
KANJI_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
KANJI_YMD_RE = re.compile(r"[〇零一二三四五六七八九]{4}年(?:[一二三四五六七八九十]{1,3}月)?(?:[一二三四五六七八九十]{1,3}日)?")
# 放送の時間帯と合わない言葉（固定文「時刻は{時刻}になりました。」の時刻で判定）
TIME_WORDS = {
    "朝": ("こんばんは", "今夜", "今晩"),
    "昼": ("こんばんは", "今夜", "今晩", "おはよう"),
    "夜": ("こんにちは", "おはよう", "今朝"),
}
TIME_RE = re.compile(r"時刻は(\d{1,2})時")
# 発言数の上限（オープニング・エンディングのプロンプトは 8〜12回）
MAX_TURNS = {"OP": 12, "ED": 12}


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------
@dataclass
class Line:
    no: int                      # ファイル上の行番号（1始まり）
    raw: str
    speaker: Optional[str]
    text: str                    # 話者ラベルを除いた本文
    fixed: Optional[str] = None  # 固定文ならブロック名
    section: str = "全体"


@dataclass
class Finding:
    level: str                   # ERROR / FIX / WARN
    code: str
    lines: List[int]
    message: str
    instruction: str = ""        # 修正プロンプトに渡す指示（FIX / 一部の ERROR）


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    reference: tuple = ([], [])

    def add(self, *args, **kwargs):
        self.findings.append(Finding(*args, **kwargs))


# ---------------------------------------------------------------------------
# 共通部品ファイルの読み込み
# ---------------------------------------------------------------------------
def parse_common(path: str) -> Dict[str, List[str]]:
    blocks: Dict[str, List[str]] = {}
    current = None
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line.startswith("## "):
                current = line[3:].strip()
                blocks[current] = []
                continue
            if current is not None:
                blocks[current].append(line)
    return blocks


def block_text(blocks: Dict[str, List[str]], name: str) -> Optional[str]:
    """プロンプトに差し込む形（# で始まる行を除き、前後の空行を落とす）"""
    if name not in blocks:
        return None
    lines = [l for l in blocks[name] if not l.startswith("#")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def fixed_from_common(blocks) -> Optional[List[Tuple[str, str]]]:
    if "固定文" not in blocks:
        return None
    result, sub = [], None
    for line in blocks["固定文"]:
        if line.startswith("### "):
            sub = line[4:].strip()
        elif line.strip() and not line.startswith("#") and sub:
            result.append((sub, line.strip()))
    return result or None


def dict_from_common(blocks) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    entries, unify = [], []
    for line in blocks.get("読み辞書", []):
        m = re.match(r"^- (.+?) = (.+)$", line.strip())
        if m:
            for term in m.group(1).split(" / "):
                entries.append((term.strip(), m.group(2).strip()))
    for line in blocks.get("表記の統一", []):
        m = re.match(r"^- (.+?) → (.+)$", line.strip())
        if m:
            unify.append((m.group(1).strip(), m.group(2).strip()))
    return entries, unify


# ---------------------------------------------------------------------------
# 読み辞書の適用
# ---------------------------------------------------------------------------
def to_halfwidth_ascii(text: str) -> str:
    def conv(ch):
        code = ord(ch)
        if 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A or 0xFF10 <= code <= 0xFF19:
            return chr(code - 0xFEE0)
        return ch
    return "".join(conv(c) for c in text)


def apply_dictionary(text: str, entries, unify) -> str:
    text = to_halfwidth_ascii(text)
    # 長い語から順に置き換える（「SD」が「SDA」を壊さないように）
    for term, kana in sorted(entries, key=lambda e: len(e[0]), reverse=True):
        if re.search(r"[A-Za-z]", term):
            # 前は英字だけを見る（「400ppm」「40Gbps」のように数字の直後の単位も置き換える）
            pattern = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z0-9])"
        else:
            pattern = re.escape(term)
        text = re.sub(pattern, kana, text)
    for src, dst in unify:
        if dst.startswith(src) and len(dst) > len(src):
            pattern = re.escape(src) + f"(?!{re.escape(dst[len(src):])})"
        else:
            pattern = re.escape(src)
        text = re.sub(pattern, dst, text)
    return text


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------
def template_to_regex(tpl: str) -> re.Pattern:
    parts = re.split(r"(\{[^}]+\})", tpl)
    rx = ""
    for p in parts:
        if re.fullmatch(r"\{[^}]+\}", p):
            rx += ".+?" if p != "{*}" else ".*"
        else:
            rx += re.escape(p)
    return re.compile("^" + rx + "$")


def parse_lines(raw_lines: List[str]) -> List[Line]:
    result = []
    for i, raw in enumerate(raw_lines, 1):
        if not raw.strip():
            continue
        m = LABEL_RE.match(raw)
        if m:
            result.append(Line(i, raw, m.group(1), m.group(2)))
        else:
            result.append(Line(i, raw, None, raw))
    return result


def mark_fixed(lines: List[Line], fixed: List[Tuple[str, str]], report: Report):
    """固定文を探し、欠落・順番違いを報告する"""
    compiled = [(name, tpl, template_to_regex(tpl)) for name, tpl in fixed]
    pos = -1
    for name, tpl, rx in compiled:
        found = None
        for idx in range(pos + 1, len(lines)):
            if lines[idx].fixed is None and rx.match(lines[idx].raw.strip()):
                found = idx
                break
        if found is None:
            anywhere = [l.no for l in lines if rx.match(l.raw.strip())]
            if anywhere:
                report.add("ERROR", "E03", anywhere,
                           f"固定文「{name}」の位置が番組の並びと違う: {short(tpl)}")
            else:
                report.add("ERROR", "E03", [],
                           f"固定文「{name}」が見つからない: {short(tpl)}")
            continue
        lines[found].fixed = name
        pos = found


def assign_sections(lines: List[Line], single_section: Optional[str]):
    if single_section:
        for l in lines:
            l.section = single_section
        return
    if not any(l.fixed for l in lines):
        for l in lines:
            l.section = "全体"
        return
    current = "冒頭"
    for l in lines:
        if l.fixed:
            current = SECTION_AFTER_FIXED.get(l.fixed, current)
            l.section = "固定文"
        else:
            l.section = current


def split_topics(lines: List[Line], starts: List[int], report: Report):
    """本編を、指定した開始行でお題1〜Nに分ける"""
    honpen = [l for l in lines if l.section == "本編"]
    if not honpen:
        report.add("WARN", "W14", [], "--topic-starts を指定したが、本編の行が見つからない")
        return
    first, last = honpen[0].no, honpen[-1].no
    starts = sorted(starts)
    if starts[0] != first:
        report.add("WARN", "W14", [starts[0]],
                   f"--topic-starts の最初の行（{starts[0]}行目）が本編の最初の行（{first}行目）と違う")
    bad = [s for s in starts if not (first <= s <= last)]
    if bad:
        report.add("WARN", "W14", bad, f"--topic-starts に本編の範囲（{first}〜{last}行目）外の行がある")
    for l in honpen:
        idx = sum(1 for s in starts if s <= l.no)
        l.section = f"お題{max(idx, 1)}"


def short(s: str, n: int = 28) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n] + "…"


def strip_quotes(text: str) -> str:
    return QUOTE_RE.sub("", text)


def sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[。！？!?]", text) if s.strip()]


def fmt_lines(nos: List[int]) -> str:
    return "・".join(str(n) for n in nos)


# ---------------------------------------------------------------------------
# チェック本体
# ---------------------------------------------------------------------------
def check(raw_lines: List[str], fixed, single_section: Optional[str],
          topic_starts: Optional[List[int]] = None,
          materials: Optional[dict] = None,
          total_chars: int = 0, total_min: int = 7800, total_max: int = 0,
          notation=None) -> Tuple[Report, List[Line]]:
    report = Report()
    lines = parse_lines(raw_lines)

    # W07 ファイル全体の文字数の下限のみ（上限は設けない。長尺は可という運用）
    if single_section is None and total_chars:
        if total_chars < total_min:
            report.add("WARN", "W07", [],
                       f"ファイル全体の文字数 {total_chars}字（目安の下限 {total_min}字）")
        elif total_max and total_chars > total_max:
            report.add("WARN", "W07", [],
                       f"ファイル全体の文字数 {total_chars}字（指定された上限 {total_max}字）")

    # E01 話者ラベル
    for l in lines:
        if l.speaker is None:
            label = l.raw.split(":")[0] if ":" in l.raw else ""
            guess = suggest_label(label)
            hint = f"「{guess}: 」に直す" if guess else "「めたん: 」「つむぎ: 」「ずんだもん: 」のどれかに直す"
            report.add("ERROR", "E01", [l.no], f"話者ラベルが不正: {short(l.raw)}",
                       f"{l.no}行目：話者ラベルを{hint}")

    # E02 英字
    for l in lines:
        # 話者ラベルが壊れている行は E01 で扱うので、ラベル部分は英字チェックから外す
        body = l.raw if l.speaker else (l.raw.split(":", 1)[1] if ":" in l.raw else l.raw)
        found = ASCII_RE.findall(body if l.speaker is None else l.raw)
        if found:
            words = "、".join(dict.fromkeys(found))
            report.add("ERROR", "E02", [l.no], f"英字が残っている: {words}",
                       f"{l.no}行目：英字「{words}」をカタカナに直す")

    # E06 文字化け・制御文字（固定文も含めて見る）
    for l in lines:
        m = BROKEN_RE.search(l.raw)
        if m:
            s, e = max(m.start() - 8, 0), min(m.end() + 8, len(l.raw))
            around = l.raw[s:e].replace("�", "�")
            report.add("ERROR", "E06", [l.no], f"文字化け・制御文字がある: …{around}…",
                       f"{l.no}行目：「{around}」の部分に文字化けがある。前後の文脈から正しい文字に直す")

    # E04 改行（発言の間に空行がない）/ W05 空行が多すぎる
    blank_run = 0
    for i, raw in enumerate(raw_lines, 1):
        if not raw.strip():
            blank_run += 1
            continue
        if i > 1 and raw_lines[i - 2].strip():
            report.add("ERROR", "E04", [i - 1, i],
                       "発言の間に空行がない（発言の途中で改行している可能性）",
                       f"{i - 1}行目と{i}行目：1つの発言にまとめるか、別の発言なら話者ラベルを付ける")
        if blank_run >= 2:
            report.add("WARN", "W05", [i], f"直前に空行が{blank_run}行ある")
        blank_run = 0

    # 固定文とセクション
    if single_section is None and fixed:
        mark_fixed(lines, fixed, report)
    assign_sections(lines, single_section)
    if topic_starts and single_section is None:
        split_topics(lines, topic_starts, report)

    generated = [l for l in lines if l.speaker and not l.fixed]

    # W01 固定文の語中の空白（差し込んだ値の読み辞書の置き換え漏れで起きる）
    for l in lines:
        if l.fixed and (INNER_SPACE_RE.search(l.text) or ALNUM_SPACE_RE.search(l.text)):
            report.add("WARN", "W01", [l.no],
                       f"固定文「{l.fixed}」の語の途中に空白がある（差し込む値を生成コード側で直す）: " + short(l.text))

    # 行ごとのチェック
    for l in generated:
        body = strip_quotes(l.text)

        if l.speaker == "ずんだもん":
            m = sorted(set(DESU_MASU_RE.findall(body)))
            if m:
                report.add("FIX", "F01", [l.no], f"ずんだもんにです・ます調: {'、'.join(m)}",
                           f"{l.no}行目：ずんだもんの発言にです・ます調（{'、'.join(m)}）がある。文末をすべて「〜のだ」「〜なのだ」にし、内容は変えない")
            if "のだ" not in body:
                report.add("FIX", "F02", [l.no], "ずんだもんの発言に「のだ」が1つもない",
                           f"{l.no}行目：ずんだもんの文末を「〜のだ」「〜なのだ」にする")
            else:
                bad = [s for s in sentences(body) if not s.rstrip("、…〜～ー").endswith(ZUNDA_ENDINGS)]  # v3.8：「のだ〜」も認める
                if bad:
                    report.add("WARN", "W03", [l.no],
                               "ずんだもんの文末が「のだ」以外: " + " / ".join(short(s, 16) for s in bad))

        if l.speaker == "つむぎ":
            m = sorted(set(DESU_MASU_RE.findall(body)))
            if m:
                report.add("FIX", "F04", [l.no], f"つむぎにです・ます調: {'、'.join(m)}",
                           f"{l.no}行目：つむぎのです・ます調（{'、'.join(m)}）をタメ口（〜の？、〜じゃん、〜だよ）に直す")

        if l.speaker == "めたん":
            n = len(sentences(l.text))
            if n > 2:
                report.add("FIX", "F05", [l.no], f"めたんの発言が{n}文",
                           f"{l.no}行目：めたんの発言を2文以内にまとめる")

        for word, why in BANNED_IN_GENERATED.items():
            if word in l.text:
                # 抽象的な指示だと修正係が直さないことがあるので、該当する文をそのまま示す
                sent = next((s for s in re.findall(r"[^。！？!?]+[。！？!?]?", l.text) if word in s), l.text)
                report.add("FIX", "F10", [l.no], f"禁止語「{word}」",
                           f"{l.no}行目：「{sent.strip()}」の文に「{word}」がある（{why}）。この文を、「{word}」を使わない言い方に書き換える")

        for word in LABEL_LEAK_WORDS:
            if word in l.text:
                report.add("FIX", "F29", [l.no], f"構成ラベル「{word}」が台本に混入",
                           f"{l.no}行目：構成ラベルの言葉「{word}」を台本から取り除き、自然な言い回しにする")

        if re.search(r"(…|\.\.\.)\s*$", l.text):
            report.add("FIX", "F11", [l.no], "「…」で切りっぱなし",
                       f"{l.no}行目：「…」で終わらせず、文を最後まで言い切る")

        if INNER_SPACE_RE.search(l.text) or ALNUM_SPACE_RE.search(l.text):
            report.add("WARN", "W01", [l.no], "語の途中に空白がある: " + short(l.text))

        sym = sorted(set(SYMBOL_RE.findall(body)) | set(re.findall(r"(?<=\d)[-－](?=\d)", l.text)))  # 数字の間のハイフンはかぎかっこの中も見る
        if sym:
            report.add("WARN", "W20", [l.no], f"読み上げに向かない記号: {' '.join(sym)}（「度」「倍」などの言葉に置き換えるか、かっこは削る）")

        if l.speaker == "めたん":
            sents = sentences(body)
            noda = [s for s in sents if s.endswith(("のだ", "なのだ"))]
            if noda:
                report.add("FIX", "F18", [l.no], "めたんの文末が「のだ」（ずんだもんの語尾）",
                           f"{l.no}行目：めたんの「{short(noda[0], 30)}」の文末が「のだ」になっている。めたんの丁寧な口調（〜ですわね、〜ですのね など）に直す")
            casual = [s for s in sents if s.endswith(METAN_CASUAL_ENDINGS)]
            if casual:
                report.add("WARN", "W18", [l.no], "めたんの文末がタメ口: " + " / ".join(short(s, 16) for s in casual))

        if l.speaker == "つむぎ":
            rough = [s for s in sentences(body) if s.endswith(TSUMUGI_ROUGH_ENDINGS) and not s.endswith(TSUMUGI_OK_ENDINGS)]
            rough += [m.group(0).strip() for m in TSUMUGI_ROUGH_Q_RE.finditer(body)
                      if not m.group(0).rstrip("？?").endswith(TSUMUGI_ROUGH_ENDINGS)]
            rough += [x.strip() for x in re.findall(r"[^。！？!?]+。", body)
                      if x.rstrip("。").endswith("んだ") and TSUMUGI_WH_RE.search(x)]
            if rough:
                report.add("WARN", "W19", [l.no], "つむぎの口調の崩れ（〜の？ にする）: " + " / ".join(short(s, 16) for s in rough))

        if l.speaker == "ずんだもん" and "だのだ" in body:
            report.add("FIX", "F19", [l.no], "ずんだもんの語尾の崩れ「だのだ」",
                       f"{l.no}行目：「だのだ」を「なのだ」に直す")

        if l.speaker == "ずんだもん":
            m = VOLITIONAL_RE.search(body)
            if m:
                report.add("WARN", "W15", [l.no], f"語尾の崩れ: 「{m.group(0)}」（「〜していくのだ」「〜するのだ」など）")

        if l.speaker == "つむぎ":
            m = TSUMUGI_SELF_RE.search(body)
            if m:
                report.add("WARN", "W16", [l.no], f"つむぎの身の上話の可能性（設定にない話か確認）: 「{m.group(0)}」")

        if l.section == "OP":
            rx = SELF_NAME_RE.get(l.speaker)
            if rx and rx.search(body):
                report.add("FIX", "F17", [l.no], f"オープニングで{l.speaker}が名乗り直している",
                           f"{l.no}行目：{l.speaker}が自分の名前を名乗っている。名前はすでに挨拶で名乗っているので、名乗りの部分を削り、番組での役割の紹介にする")

        # F15 呼び方
        for rx, label in NAMING_RULES.get(l.speaker, []):
            if rx.search(body):
                report.add("FIX", "F15", [l.no], f"{l.speaker}の呼び方: {label}",
                           f"{l.no}行目：{l.speaker}の呼び方{label}を、呼び方の設定どおりに直す")

        # W11 同じ言い回しの繰り返し
        m = REPEAT_RE.search(body)
        if m:
            report.add("WARN", "W11", [l.no], f"同じ言い回しの繰り返し（口調見本のコピーの可能性）: 「{short(m.group(0), 24)}」")

        # W13 過去の放送への言及
        past = [w for w in PAST_SHOW_WORDS if w in body]
        if past:
            report.add("WARN", "W13", [l.no], f"過去の放送への言及（存在しない話か確認）: {'、'.join(past)}")

        hits = [w for w in ASSERTION_WORDS if w in l.text]
        if hits:
            report.add("WARN", "W02", [l.no], f"言い切り語（内容を確認）: {'、'.join(hits)}")

        nums = extract_numbers(l.text)
        nums = [n for n in nums if n not in NUMBER_IGNORE]
        if nums and l.section != "ブログ":  # ブログの数値は記事素材の確認で見る
            report.add("WARN", "W08", [l.no], f"数値（素材にあるか確認）: {'、'.join(dict.fromkeys(nums))}")

    # セクションごとのチェック
    sections = [s for s in dict.fromkeys(l.section for l in lines) if s != "固定文"]
    for sec in sections:
        limits = limits_for(sec)
        sec_lines = [l for l in generated if l.section == sec]
        if not sec_lines:
            continue

        chars = sum(len(l.text) for l in sec_lines)
        report.stats[sec] = dict(chars=chars, turns=len(sec_lines))
        if chars < limits["min_chars"]:
            report.add("WARN", "W04", [], f"[{sec}] 文字数 {chars}字（最低 {limits['min_chars']}字）")
        if len(sec_lines) < limits["min_turns"]:
            report.add("WARN", "W09", [], f"[{sec}] 発言数 {len(sec_lines)}回（最低 {limits['min_turns']}回）")

        uke = [l.no for l in sec_lines if l.speaker == "めたん"
               and any(UKE_RE.search(s) for s in sentences(strip_quotes(l.text)))]
        if len(uke) > limits["uke"]:
            report.add("FIX", "F12", uke,
                       f"[{sec}] めたんの「〜わけですね」「〜ということですね」型の受けが{len(uke)}回（上限{limits['uke']}）",
                       f"{fmt_lines(uke[limits['uke']:])}行目：めたんの「〜わけですね」「〜ということですね」型の受けが続いている。この行の受けを、短い相づちや次の問いかけなど別の言い方にする")

        if sec in ("冒頭", "締め"):
            report.add("WARN", "W06", [l.no for l in sec_lines],
                       f"[{sec}] 固定文の間に生成された発言がある")

        dewa = [l.no for l in sec_lines if l.speaker == "めたん" and DEWA_RE.match(l.text)]
        if len(dewa) > limits["dewa"]:
            report.add("FIX", "F06", dewa, f"[{sec}] めたんの「では」始まりが{len(dewa)}回（上限{limits['dewa']}）",
                       f"{fmt_lines(dewa)}行目：めたんの「では」で始まる発言が多い。{limits['dewa']}回まで残し、残りは別の書き出し（相手の発言を受けた一言、問いかけなど）にする")

        ii = [l for l in sec_lines if "いい質問" in l.text]
        if len(ii) > limits["iishitsumon"]:
            nos = [l.no for l in ii]
            report.add("FIX", "F07", nos, f"[{sec}] 「いい質問」が{len(ii)}回（上限{limits['iishitsumon']}）",
                       f"{fmt_lines(nos)}行目：「いい質問」が多い。{limits['iishitsumon']}回まで残し、残りは削除する")
        for l in ii:
            prev = prev_line(lines, l)
            if prev is None or prev.speaker != "つむぎ":
                report.add("FIX", "F07", [l.no], "「いい質問」の直前がつむぎの質問ではない",
                           f"{l.no}行目：直前がつむぎの質問ではないので「いい質問」を削除する")
            elif not prev.text.rstrip().endswith(("？", "?")):
                report.add("WARN", "W17", [prev.no, l.no],
                           "「いい質問」の直前のつむぎの発言が「？」で終わっていない（質問になっているか確認）")

        kuse = [(l.no, len(ZUNDA_KUSE_RE.findall(strip_quotes(l.text))))
                for l in sec_lines if l.speaker == "ずんだもん"]
        total = sum(c for _, c in kuse)
        if total > limits["kuse"]:
            nos = [n for n, c in kuse if c]
            report.add("FIX", "F03", nos, f"[{sec}] ずんだもんの「〜ね、」「〜な、」が{total}回（上限{limits['kuse']}）",
                       f"{fmt_lines(nos)}行目：ずんだもんの「でもね、」「だけどな、」のような「〜ね、」「〜な、」が多い。{limits['kuse']}回まで残し、残りは削除するか別の言い方にする")

    # F13 めたんの問いかけの相手と、次の話者
    speaking = [l for l in lines if l.speaker]
    for a, b in zip(speaking, speaking[1:]):
        if a.fixed or b.fixed or a.speaker != "めたん":
            continue
        body = strip_quotes(a.text).rstrip()
        sents = sentences(body)
        if not sents:
            continue
        last = sents[-1]
        is_ask = body.endswith(("？", "?")) or last.endswith(ASK_ENDINGS)
        if not is_ask or TSUKKOMI_RE.search(body):  # v3.9：ツッコミのあとは誰が話してもよい
            continue
        found = ADDRESS_RE.findall(last) or ADDRESS_RE.findall(body)
        if not found:
            continue
        target = found[-1]
        if b.speaker != target:
            report.add("FIX", "F13", [a.no, b.no],
                       f"めたんが{target}さんに問いかけているのに、次の発言が{b.speaker}",
                       f"{a.no}行目：めたんの問いかけの呼びかけを、次に答える{b.speaker}に合わせて「{b.speaker}さん」に直す（内容は変えない）")

    # 連続発言
    # 話者ラベルが壊れた行（E01）をまたいだ組み合わせは判定しない
    for a, b in zip(lines, lines[1:]):
        if a.speaker is None or b.speaker is None or a.speaker != b.speaker:
            continue
        if a.fixed and b.fixed:
            continue
        if not a.fixed and not b.fixed:
            report.add("FIX", "F08", [a.no, b.no], f"{a.speaker}が2回続けて話している",
                       f"{a.no}行目と{b.no}行目：{a.speaker}が続けて話している。1つの発言にまとめるか、間に別の人の短い相づちを入れる")
        elif not a.fixed and b.fixed:
            report.add("FIX", "F09", [a.no], f"コーナー最後の発言者が直後の固定文（{b.fixed}）と同じ{a.speaker}",
                       f"{a.no}行目：コーナーの最後の発言が、直後の固定文と同じ{a.speaker}になっている。この行を別の人の締めの一言に書き換える")
        # 固定文の直後に同じ話者が生成文で続くのは自然な流れとして許容する

    check_duplicates(lines, generated, report)
    check_leaks(generated, report)
    check_structure(lines, generated, report)
    known = KNOWN_KANA + [r.get("kana", "") for r in ((materials or {}).get("readings") or [])]
    check_new_words(generated, known, report)
    check_v38(lines, generated, report)
    check_v39(lines, generated, report)
    # 固定文の重複（F21）で削除する行には、ほかの書き換えの指示を出さない
    f21 = {f.lines[0] for f in report.findings if f.code == "F21"}
    for f in report.findings:
        if f.code != "F21" and f.instruction and f.lines and f.lines[0] in f21:
            f.instruction = ""

    # F23 繰り返し語の上限
    for word, limit in REPEAT_WORDS.items():
        occ = [(l.no, i) for l in generated for i in range(l.text.count(word))]
        if len(occ) > limit:
            report.add("FIX", "F23", [n for n, _ in occ],
                       f"「{word}」が{len(occ)}回（上限{limit}回）",
                       "全文で2回までに減らす")

    # レポート用の集計（話者別の発言数、ずんだもん のだ率・んです）
    from collections import Counter
    turns = Counter(l.speaker for l in generated if l.speaker)
    zunda = [l.text for l in generated if l.speaker == "ずんだもん"]
    noda = sum(1 for t in zunda for s in re.split(r"(?<=[。！？])", t) if "のだ" in s)
    z_sentences = sum(1 for t in zunda for s in re.split(r"(?<=[。！？])", t) if s.strip())
    # 話者別は番組ごとに顔ぶれが違うので、出てきた話者をそのまま数える
    report.stats["__speakers__"] = {
        "turns": dict(turns),
        "noda_rate": round(100 * noda / z_sentences) if z_sentences else 0,
        "ndesu": sum(t.count("んです") for t in zunda)}

    # 人間の確認用リスト（数値・カタカナ語）
    nums_ref, kata_ref = [], []
    for l in generated:
        nums_ref += extract_numbers(l.text)
        kata_ref += KATAKANA_RE.findall(l.text)
    report.reference = (list(dict.fromkeys(nums_ref)),
                        list(dict.fromkeys(kata_ref)))

    if materials:
        check_materials(lines, generated, materials, report, notation)

    report.findings.sort(key=lambda f: ({"ERROR": 0, "FIX": 1, "WARN": 2}[f.level], f.lines[0] if f.lines else 0))
    return report, lines


def check_duplicates(lines: List[Line], generated: List[Line], report: Report):
    """F20 / W21 生成部分の使い回し、F21 固定文と同じ内容の発言"""
    def ratio(a: str, b: str) -> float:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        return sm.ratio() if sm.real_quick_ratio() >= DUP_WARN_RATIO and sm.quick_ratio() >= DUP_WARN_RATIO else 0.0

    # F21 固定文とほぼ同じ発言（固定文の頭に一言足したものも拾う）
    fixed_lines = [l for l in lines if l.fixed]
    fixed_hit = set()
    for g in generated:
        for f in fixed_lines:
            if g.speaker != f.speaker:
                continue
            r = difflib.SequenceMatcher(None, g.text, f.text, autojunk=False).ratio()
            contains = len(f.text) >= DUP_MIN_CHARS and f.text.rstrip("！!。") in g.text
            if r >= FIXED_DUP_RATIO or contains:
                fixed_hit.add(g.no)
                report.add("FIX", "F21", [g.no, f.no],
                           f"固定文「{f.fixed}」（{f.no}行目）と同じ内容の発言が生成部分にある: {short(g.text, 30)}",
                           f"{g.no}行目：「{g.text}」を削除する")
                break

    # F20 / W21 生成部分どうしの使い回し
    cand = [g for g in generated if len(g.text) >= DUP_MIN_CHARS and g.no not in fixed_hit]
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if a.speaker != b.speaker:
                continue
            r = ratio(a.text, b.text)
            sm = difflib.SequenceMatcher(None, a.text, b.text, autojunk=False)
            share = sm.find_longest_match(0, len(a.text), 0, len(b.text)).size / min(len(a.text), len(b.text))
            if r >= DUP_FIX_RATIO or share >= DUP_SHARE:
                where = "別のコーナー" if a.section != b.section else "同じコーナー"
                report.add("FIX", "F20", [a.no, b.no],
                           f"{where}にほぼ同じ発言がある（{a.section} {a.no}行目 / {b.section} {b.no}行目）: {short(b.text, 30)}",
                           f"{b.no}行目：{a.no}行目と同じ発言の使い回しになっている。{b.no}行目を、"
                           f"この行の前後の話の流れ（{b.section}）に合った別の発言に書き換える")
            elif r >= DUP_WARN_RATIO:
                report.add("WARN", "W21", [a.no, b.no],
                           f"言い回しがよく似た発言（似ている度合い {r:.2f}）: {short(a.text, 20)} / {short(b.text, 20)}")


def is_rant(l: Line) -> bool:
    if l.speaker != "ずんだもん":
        return False
    n = len(l.text)
    return n >= RANT_MIN_CHARS or (n >= RANT_SHORT_CHARS and len(sentences(strip_quotes(l.text))) >= RANT_SHORT_SENTS)


def check_structure(lines: List[Line], generated: List[Line], report: Report):
    """W24〜W28 早口の場面とコーナーの構成"""
    for i, l in enumerate(generated):
        prev_z = next((g for g in reversed(generated[:i]) if g.speaker == "ずんだもん" and g.section == l.section), None)
        next_z = next((g for g in generated[i + 1:] if g.speaker == "ずんだもん" and g.section == l.section), None)
        # W25 早口のあとではないのに我に返っている
        if l.speaker == "ずんだもん" and RECOVER_RE.search(l.text):
            if prev_z is None or not is_rant(prev_z):
                report.add("WARN", "W25", [l.no],
                           "ずんだもんが我に返っているが、直前のずんだもんの発言が早口になっていない"
                           "（早口の場面を入れるか、我に返る言い方を外す）")
        # W26 ツッコミが早口より先
        if l.speaker in ("めたん", "つむぎ") and TSUKKOMI_RE.search(l.text):
            if prev_z is not None and not is_rant(prev_z) and next_z is not None and is_rant(next_z):
                report.add("WARN", "W26", [l.no, next_z.no],
                           f"ツッコミ（{l.no}行目）が、早口（{next_z.no}行目）より先に入っている")
        # W24 ブログで、ずんだもんが記事の内容を紹介している
        if l.section == "ブログ" and l.speaker == "ずんだもん":
            m = ARTICLE_REPORT_RE.search(strip_quotes(l.text))
            if m:
                report.add("WARN", "W24", [l.no],
                           f"ブログで、ずんだもんが記事の内容を紹介している（「{m.group(0)}」）。記事の紹介はめたん、ずんだもんは意見・用語の説明にする")

    # W27・W28 コーナーごとの構成（お題は --topic-starts で分けたときだけ）
    # つむぎ・ずんだもんが居ない番組（ねるるの眠れない話）では構成が違うので対象外
    if not any(g.speaker == "つむぎ" for g in generated):
        return
    secs = [s for s in dict.fromkeys(g.section for g in generated) if s.startswith("お題") and s != "お題" or s == "ブログ"]
    for sec in secs:
        sl = [g for g in generated if g.section == sec]
        if not sl:
            continue
        if sl[-1].speaker != "つむぎ":
            report.add("WARN", "W27", [sl[-1].no],
                       f"[{sec}] 最後の発言が{sl[-1].speaker}になっている（つむぎの締めの一言で終える）")
        ok = False
        for j, g in enumerate(sl):
            if is_rant(g) and any(x.speaker in ("めたん", "つむぎ") and TSUKKOMI_RE.search(x.text) for x in sl[j + 1:j + 3]):
                ok = True
                break
        if not ok:
            report.add("WARN", "W28", [],
                       f"[{sec}] 早口→ツッコミの場面がない（ずんだもんの{RANT_MIN_CHARS}字以上の発言の直後にツッコミ）")


def check_new_words(generated: List[Line], known_kana: List[str], report: Report):
    """W29 同じ語の重複、W30 辞書にない略語の読み、W31 表記ゆれ"""
    first_seen: Dict[str, int] = {}
    for g in generated:
        body = strip_quotes(g.text)
        # W29 同じカタカナ語が2回続いている
        # 擬音（ジュウジュウ）と、辞書の読みの中の繰り返し（エイチディーディー）は外す
        m = re.search(r"([ァ-ヴー]{4,})\1", body)
        if m and not any(m.group(0) in k for k in known_kana):
            report.add("FIX", "F24", [g.no], f"同じ語が2回続いている: {m.group(0)}",
                       f"{g.no}行目：「{m.group(0)}」を「{m.group(1)}」に")
        # W30 アルファベット読みの並びで、辞書にないもの
        for run in KATA_RUN_RE.findall(body):
            for lm in LETTER_RUN_RE.finditer(run):
                w = lm.group(0)
                if not any(w in k for k in known_kana):
                    first_seen.setdefault(w, g.no)
    if first_seen:
        items = sorted(first_seen.items(), key=lambda x: x[1])
        report.add("WARN", "W30", [n for _, n in items],
                   "辞書にない略語の読み（読みと、正式名を言うべきかを確認して、読み辞書か readings に足す）: "
                   + "、".join(f"{w}（{n}行目）" for w, n in items))

    # W31 表記ゆれ
    # キャラクター名（ずんだもん の「ずんだ」など）は表記ゆれとして見ない
    texts = {g.no: NAMES_RE.sub("", strip_quotes(g.text)) for g in generated}
    text = "\n".join(texts.values())
    runs = set(KATA_RUN_RE.findall(text))
    kata2hira = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
    seen = set()
    for r in sorted(runs, key=len):
        if len(r) < YURE_MIN_CHARS or r in seen:
            continue
        hira = r.translate(kata2hira)
        if "ー" not in r and hira != r and re.search(rf"(?<![ぁ-ん]){re.escape(hira)}", text):
            hira_rx = re.compile(rf"(?<![ぁ-ん]){re.escape(hira)}")
            no = next(n for n, t in texts.items() if hira_rx.search(t))
            report.add("WARN", "W31", [no], f"表記ゆれ：「{r}」と「{hira}」（どちらかにそろえる。表記の統一に足すと自動でそろう）")
            seen.add(r)
        if not r.endswith("ー") and any((r + "ー") in x for x in runs if x != r):
            # 「カテゴリ」が長音なしで出てくる行（「カテゴリー」の一部ではないもの）
            short_rx = re.compile(rf"(?<![ァ-ヴー]){re.escape(r)}(?!ー)")
            no = next((g.no for g in generated if short_rx.search(g.text)), None)
            if no is not None:
                report.add("WARN", "W31", [no], f"表記ゆれ：「{r}」と「{r}ー」（どちらかにそろえる。表記の統一に足すと自動でそろう）")
                seen.add(r)


def check_leaks(generated: List[Line], report: Report):
    """W22 素材の確認用メモ・構成の見出しの言葉が台詞に出ている"""
    for g in generated:
        body = strip_quotes(g.text)
        memo = list(dict.fromkeys(m.group(0) for m in MEMO_LEAK_RE.finditer(body)))
        head = [w for w in HEADING_LEAK_WORDS if w in body]
        if memo:
            sent = next((x for x in re.findall(r"[^。！？!?]+[。！？!?]?", body) if MEMO_LEAK_RE.search(x)), body)
            report.add("WARN", "W22", [g.no],
                       f"素材の確認用メモが台詞に出ている可能性: {'、'.join(memo)}「{short(sent.strip(), 30)}」")
        if head:
            report.add("WARN", "W22", [g.no],
                       f"構成の見出し・進行の言葉が台詞に出ている: {'、'.join(head)}（話の流れの中の言い方にする）")


def kana_to_int(tok: str) -> Optional[int]:
    """「ニジュウゴ」→ 25。読めなければ None"""
    names = sorted(list(KANA_DIGITS) + list(KANA_UNITS), key=len, reverse=True)
    parts, i = [], 0
    while i < len(tok):
        n = next((x for x in names if tok.startswith(x, i)), None)
        if n is None:
            return None
        parts.append(n)
        i += len(n)
    total, section, digit = 0, 0, None
    for p in parts:
        if p in KANA_DIGITS:
            if digit is not None:
                return None
            digit = KANA_DIGITS[p]
        else:
            u = KANA_UNITS[p]
            if u == 10000:
                total += (section + (digit or 0)) * u
                section = 0
            else:
                section += (digit if digit is not None else 1) * u
            digit = None
    return total + section + (digit or 0)


def check_v38(lines: List[Line], generated: List[Line], report: Report):
    """v3.8 の判定（F25〜F28、W32〜W36、F20 の短い重複）"""
    abbr_alt = "|".join(sorted((re.escape(a) for a in WELL_KNOWN_ABBR), key=len, reverse=True))
    letters = "(?:" + "|".join(LETTER_NAMES) + ")"
    fullnames: Dict[str, List[int]] = {}
    for g in generated:
        body = strip_quotes(g.text)
        # F25 キャラクター名の混入
        for m in NAME_MIX_RE.finditer(body):
            report.add("FIX", "F25", [g.no], f"台詞の中にキャラクター名が混ざった言葉がある: 「{m.group(0)}」",
                       f"{g.no}行目：「{m.group(0)}」は意味の通らない言葉になっている。前後の文脈に合う一般的な言葉に直す（ほかの部分は変えない）")
        # F27 数字のカタカナ書き
        for m in KANA_NUM_RE.finditer(body):
            tok = m.group(1)
            if not any(u in tok for u in KANA_UNITS):
                continue
            v = kana_to_int(tok)
            if v is None:
                continue
            unit = body[m.end():m.end() + 6]
            unit = re.match(r"メガ|ギガ|テラ|キロ|ミリ|センチ|バイト|ビット|ワット|ボルト|ヘルツ|パーセント|件|個|円|回|年|枚|本|台|人|倍|度|分|秒|時間|日", unit).group(0)
            report.add("FIX", "F27", [g.no], f"数字がカタカナで書かれている: {tok}{unit}",
                       f"{g.no}行目：「{tok}{unit}」を「{v}{unit}」に")
        # F28 よく知られた略語に正式名を添えている
        if abbr_alt:
            for m in re.finditer(rf"({abbr_alt}){FULLNAME_LINK}([ァ-ヴー]{{{FULLNAME_MIN},}})", body):
                report.add("FIX", "F28", [g.no], f"よく知られた略語に正式名を添えている: {m.group(1)}",
                           f"{g.no}行目：「{m.group(0)}」を「{m.group(1)}」に")
            for m in re.finditer(rf"([ァ-ヴー]{{{FULLNAME_MIN},}})(?:、つまり|、すなわち)({abbr_alt})(?![ァ-ヴー])", body):
                report.add("FIX", "F28", [g.no], f"よく知られた略語に正式名を添えている: {m.group(2)}",
                           f"{g.no}行目：「{m.group(0)}」を「{m.group(2)}」に")
        # W36 用：略語と正式名の組を集める
        for m in re.finditer(rf"((?:{letters}){{2,}}){FULLNAME_LINK}([ァ-ヴー]{{{FULLNAME_MIN},}})", body):
            fullnames.setdefault(m.group(2), [])
        for m in re.finditer(rf"([ァ-ヴー]{{{FULLNAME_MIN},}})(?:、つまり|、すなわち)((?:{letters}){{2,}})", body):
            fullnames.setdefault(m.group(1), [])
    # W36 同じ正式名を2回以上言っている
    for name in fullnames:
        nos = [g.no for g in generated if name in g.text]
        if len(nos) >= 2:
            report.add("WARN", "W36", nos,
                       f"同じ正式名を{len(nos)}回言っている: {short(name, 24)}（2回目からは略語だけにする）")

    # W34 ツッコミの相手が、直前に話した人と違う
    #   早口のあとに、つむぎが一言はさんでからめたんがツッコむ流れは正しいので外す
    speaking = [l for l in lines if l.speaker]
    for i, b in enumerate(speaking):
        if i == 0 or b.fixed or b.speaker != "めたん":
            continue
        m = re.match(r"^(つむぎ|ずんだもん)さん、", b.text)
        if not (m and TSUKKOMI_RE.search(b.text)):
            continue
        a = speaking[i - 1]
        if a.speaker in ("めたん", m.group(1)):
            continue
        aa = speaking[i - 2] if i >= 2 else None
        if aa is not None and aa.speaker == m.group(1) and (is_rant(aa) or TSUKKOMI_RE.search(a.text)):
            continue  # 早口 → つむぎの一言 → めたんのツッコミ の流れ
        report.add("WARN", "W34", [a.no, b.no],
                   f"めたんが{m.group(1)}さんをたしなめているが、直前に話したのは{a.speaker}（相手が違わないか確認）")

    # セクションごと
    secs = [x for x in dict.fromkeys(g.section for g in generated)]
    for sec in secs:
        sl = [g for g in generated if g.section == sec]
        is_topic = sec.startswith("お題")
        # F26 お題の切り出しで順番の言い方
        if is_topic and sec != "お題" and sl and sl[0].speaker == "めたん":
            m = SEQ_WORDS_RE.search(sl[0].text)
            if m:
                report.add("FIX", "F26", [sl[0].no], f"[{sec}] お題の切り出しに順番の言い方: 「{m.group(0)}」",
                           f"{sl[0].no}行目：「{m.group(0)}」のような順番の言い方を削り、お題の名前から切り出す。ほかのお題の切り出しと同じ言い回しにしない。ほかの部分は変えない")
        # F20 同じコーナーで一字一句同じ発言（短い定型も含む）
        seen: Dict[Tuple[str, str], int] = {}
        for g in sl:
            key = (g.speaker, g.text.strip())
            if len(key[1]) < DUP_EXACT_MIN or RECOVER_RE.search(key[1]):
                continue
            if key in seen and len(key[1]) < DUP_MIN_CHARS:  # 20字以上は check_duplicates で拾う
                report.add("FIX", "F20", [seen[key], g.no],
                           f"[{sec}] 同じ発言が2回ある（{seen[key]}行目 / {g.no}行目）: {short(g.text, 30)}",
                           f"{g.no}行目：「{g.text.strip()}」を削除する")
            seen.setdefault(key, g.no)
        # W32・W33 つむぎの締めの言い回し
        if is_topic or sec == "ブログ":
            for j, g in enumerate(sl):
                if g.speaker != "つむぎ":
                    continue
                hit = next((x for x in sentences(strip_quotes(g.text)) if CLOSE_TRY_RE.search(x + "。")), None)
                if hit is None:
                    continue
                if j == len(sl) - 1:
                    report.add("WARN", "W32", [g.no],
                               f"[{sec}] つむぎの締めが「〜してみようかな」型: 「{short(hit, 24)}」（このお題で分かったことへの感想にする）")
                elif j >= len(sl) - CLOSE_TAIL:
                    report.add("WARN", "W33", [g.no, sl[-1].no],
                               f"[{sec}] 締めのような一言（{g.no}行目「{short(hit, 16)}」）のあとに、まだ{len(sl) - 1 - j}発言続いている（締めの重複・蛇足がないか確認）")

    # W35 エンディングで本編の説明を言い直している
    body_lines = [g for g in generated if g.section.startswith("お題") or g.section in ("本編", "ブログ")]
    for e in (g for g in generated if g.section == "ED"):
        best, src = 0, None
        for b in body_lines:
            sm = difflib.SequenceMatcher(None, e.text, b.text, autojunk=False)
            mt = sm.find_longest_match(0, len(e.text), 0, len(b.text))
            if mt.size > best:
                best, src = mt.size, (b, e.text[mt.a:mt.a + mt.size])
        # 決まり文句（「この沼の面白いところなのだ」）やお題名だけの一致は外す：漢字が ED_ECHO_KANJI 字以上ある一致だけ
        if best >= ED_ECHO_MIN and src and len(re.findall(r"[一-鿿]", src[1])) >= ED_ECHO_KANJI:
            report.add("WARN", "W35", [e.no, src[0].no],
                       f"エンディングで本編（{src[0].no}行目）の説明を言い直している可能性: 「{short(src[1], 24)}」")


def kanji_num(s: str) -> int:
    if "十" in s:
        a, _, b = s.partition("十")
        return (KANJI_DIGIT.get(a, 1) if a else 1) * 10 + (KANJI_DIGIT.get(b, 0) if b else 0)
    return int("".join(str(KANJI_DIGIT[c]) for c in s))


def kanji_date_to_digits(src: str) -> str:
    m = re.fullmatch(r"([〇零一二三四五六七八九]{4})年(?:([一二三四五六七八九十]{1,3})月)?(?:([一二三四五六七八九十]{1,3})日)?", src)
    out = f"{kanji_num(m.group(1))}年"
    if m.group(2):
        out += f"{kanji_num(m.group(2))}月"
    if m.group(3):
        out += f"{kanji_num(m.group(3))}日"
    return out


def check_v39(lines: List[Line], generated: List[Line], report: Report):
    """v3.9 の判定（F27 の日付の漢数字、W37 時間帯、W38 発言数の上限）"""
    for g in generated:
        for m in KANJI_YMD_RE.finditer(g.text):
            src = m.group(0)
            report.add("FIX", "F27", [g.no], f"日付が漢数字で書かれている: {src}",
                       f"{g.no}行目：「{src}」を「{kanji_date_to_digits(src)}」に")
    hour = next((int(m.group(1)) for l in lines if l.fixed for m in [TIME_RE.search(l.text)] if m), None)
    if hour is not None:
        band = "朝" if 4 <= hour < 10 else "昼" if 10 <= hour < 18 else "夜"
        for g in generated:
            hit = [w for w in TIME_WORDS[band] if w in g.text]
            if hit:
                report.add("WARN", "W37", [g.no],
                           f"放送は{hour}時（{band}）なのに、時間帯の合わない言葉がある: {'、'.join(hit)}")
    for sec, mx in MAX_TURNS.items():
        n = sum(1 for g in generated if g.section == sec)
        if n > mx:
            report.add("WARN", "W38", [], f"[{sec}] 発言数 {n}回（上限 {mx}回。プロンプトは8〜12回）")


def parse_date(s: str):
    import datetime
    m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", s or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def check_article_date(generated: List[Line], mat: dict, report: Report):
    """F22 新しい記事に「事情が変わっている」の一言 / W23 古い記事に一言がない"""
    import datetime
    pub = parse_date(mat.get("article_published", ""))
    if pub is None:
        return
    on_air = parse_date(mat.get("broadcast_date", "")) or datetime.date.today()
    limit = int(mat.get("old_article_days", OLD_ARTICLE_DAYS))
    age = (on_air - pub).days
    blog = [g for g in generated if g.section == "ブログ"]
    notes = [g for g in blog if OLD_ARTICLE_NOTE_RE.search(g.text)]
    if age <= limit:
        for g in notes:
            sent = next((x for x in re.findall(r"[^。！？!?]+[。！？!?]?", g.text) if OLD_ARTICLE_NOTE_RE.search(x)), g.text)
            report.add("FIX", "F22", [g.no],
                       f"記事は公開から{age}日（{pub}）で新しいのに、古い記事向けの一言がある",
                       f"{g.no}行目：「{sent.strip()}」を削除する")
    elif blog and not notes:
        report.add("WARN", "W23", [blog[0].no],
                   f"記事は公開から{age}日（{pub}）たっているのに、「今は事情が変わっているかも」の一言がない")


MATERIALS_HELP = """\
--materials に渡すJSON（キーはすべて任意。あるものだけ照合する）
{
  "topics": ["お題1（カタカナ版）", "お題2", "お題3"],
  "article_title": "記事タイトル（カタカナ版。ブログ素材の title_spoken）",
  "article_published": "2026-11-16（ブログ素材の published。2026年11月16日 の形でもよい）",
  "broadcast_date": "2026-11-18（放送日。省略すると今日）",
  "old_article_days": 365,
  "readings": [
    {"term": "GaN", "kana": "ガン", "full": "窒化ガリウム"},
    {"term": "NAS", "kana": "ナス", "full": "ネットワークアタッチドストレージ"}
  ]
}
- topics / article_title：お題紹介・ブログ紹介の固定文に入っているかを確認（ERROR E05）
- readings：full がある語だけ、略称（kana）を正式名（full）より前の行で使っていないかを確認（FIX F16）
  比較の前に「・」と空白を取り除く。同じ行の中で略称が先でも許容する（「ガン、つまり窒化ガリウム」）
- article_published：公開から old_article_days 日以内なのに「事情が変わっている」と言っていれば FIX F22、
  過ぎているのに一言がなければ WARN W23
"""


def norm(s: str) -> str:
    return re.sub(r"[・･\s　]", "", s)


def check_materials(lines: List[Line], generated: List[Line], mat: dict, report: Report, notation=None):
    check_article_date(generated, mat, report)
    # E05 固定文に差し込んだタイトル
    by_name = {}
    for l in lines:
        if l.fixed:
            by_name.setdefault(l.fixed, l)
    expect = []
    for t in mat.get("topics", []) or []:
        expect.append(("お題紹介", t))
    title = mat.get("article_title")
    if title:
        expect += [("お題紹介", title), ("ブログ紹介", title)]
    for name, value in expect:
        l = by_name.get(name)
        if l and norm(value) not in norm(l.text):
            report.add("ERROR", "E05", [l.no],
                       f"固定文「{name}」に素材のタイトルが入っていない（差し込む値が別のものになっている可能性）: {short(value, 30)}")

    # F16 略称を正式名より先に使っていないか
    for r in mat.get("readings", []) or []:
        kana, full = r.get("kana"), r.get("full")
        if not kana or not full:
            continue
        full = apply_notation(full, notation)
        nk, nf = norm(kana), norm(full)
        first_kana = next((l for l in generated if nk in norm(l.text)), None)
        if first_kana is None:
            continue
        first_full = next((l for l in generated if nf in norm(l.text)), None)
        if first_full is None:
            report.add("FIX", "F16", [first_kana.no], f"略称「{kana}」の正式名「{full}」を一度も言っていない",
                       f"{first_kana.no}行目：「{kana}」を初めて使うこの発言で、正式名「{full}」も言う")
        elif first_full.no > first_kana.no:
            report.add("FIX", "F16", [first_kana.no, first_full.no],
                       f"略称「{kana}」を、正式名「{full}」（{first_full.no}行目）より先に使っている",
                       f"{first_kana.no}行目：「{kana}」を初めて使うこの発言で、正式名「{full}」も言う（{first_full.no}行目の正式名の説明はそのまま残してよい）")


def prev_line(lines: List[Line], target: Line) -> Optional[Line]:
    prev = None
    for l in lines:
        if l is target:
            return prev
        if l.speaker:
            prev = l
    return None


def suggest_label(label: str) -> Optional[str]:
    cleaned = re.sub(r"[A-Za-z0-9\s]", "", label)
    kata2hira = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
    cleaned = cleaned.translate(kata2hira)
    if cleaned in SPEAKERS:
        return cleaned
    # 文字が混ざって壊れた場合（例：「つwarmぎ」→「つぎ」）は、最初と最後の文字で推定する
    candidates = [sp for sp in SPEAKERS if cleaned and sp[0] == cleaned[0] and sp[-1] == cleaned[-1]]
    return candidates[0] if len(candidates) == 1 else None


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------
def print_report(report: Report, path: str):
    print(f"■ チェック対象: {path}")
    if report.stats:
        print("■ セクション別の文字数・発言数")
        for sec, s in report.stats.items():
            if sec == "__speakers__":
                continue
            print(f"  {sec:　<4} {s['chars']:>5}字 / {s['turns']:>3}発言")
        sp = report.stats.get("__speakers__")
        if sp:
            print("■ 話者別: " + " / ".join(
                f"{name} {n}発言" for name, n in sp["turns"].items()))
            if sp["turns"].get("ずんだもん"):
                print(f"■ ずんだもん のだ率: {sp['noda_rate']}% / んです: {sp['ndesu']}回")
    counts = {lv: sum(1 for f in report.findings if f.level == lv) for lv in ("ERROR", "FIX", "WARN")}
    print(f"■ 結果: ERROR {counts['ERROR']}件 / FIX {counts['FIX']}件 / WARN {counts['WARN']}件")
    for f in report.findings:
        where = f"{fmt_lines(f.lines)}行目" if f.lines else "-"
        print(f"  [{f.level:<5}] {f.code} {where}: {f.message}")
    nums_ref, kata_ref = report.reference
    if nums_ref:
        print(f"■ 数値の一覧（人の確認用）: {'、'.join(nums_ref)}")
    if kata_ref:
        print(f"■ カタカナ語の一覧（人の確認用）: {'、'.join(kata_ref)}")


def build_fix_request(report: Report, lines: List[Line], include_errors: bool = True) -> str:
    items = []
    for f in report.findings:
        if f.instruction and (f.level == "FIX" or (include_errors and f.level == "ERROR")):
            items.append(f"- {f.instruction}")
    fixed_nos = [l.no for l in lines if l.fixed]
    if fixed_nos:
        items.append(f"- {fmt_lines(fixed_nos)}行目は固定文なので変更しない")
    return "\n".join(dict.fromkeys(items))


def numbered_script(lines: List[Line]) -> str:
    return "\n\n".join(f"[{l.no}] {l.raw}" for l in lines)


def build_fix_prompt(template_path: str, request: str, script: str, blocks) -> str:
    with open(template_path, encoding="utf-8") as f:
        prompt = f.read()
    # テンプレート内の「（書き方の例）」は、モデルが実際の指示と取り違えるので取り除く
    prompt = re.sub(r"（書き方の例）\n(?:- .*\n?)+", "", prompt)
    prompt = prompt.replace("{修正指示}", request)
    prompt = prompt.replace("{行番号つき台本}", script)
    for name in re.findall(r"\{共通:([^}]+)\}", prompt):
        text = block_text(blocks, name) if blocks else None
        if text is not None:
            prompt = prompt.replace(f"{{共通:{name}}}", text)
        else:
            print(f"注意: 共通部品「{name}」が見つからないため、差し込まずに残しました", file=sys.stderr)
    return prompt


# ---------------------------------------------------------------------------
# 修正指示の機械適用と、LLMの適用結果の照合（v3.3）
# ---------------------------------------------------------------------------
@dataclass
class Instruction:
    raw: str
    nos: List[int]                 # 指示の対象になる元の行番号
    kind: str                      # replace / whole / insert / protect / free
    pairs: List[Tuple[str, str]] = field(default_factory=list)  # replace の（元, 新）。削除は新が ""
    text: str = ""                 # whole / insert の新しい行
    note: str = ""                 # 機械で適用できなかった理由


def load_instructions(path: str) -> List[str]:
    """修正プロンプト全体（「# 修正指示」の節を読む）か、「- 」で始まる指示だけのファイルを読む"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^# 修正指示\n(.*?)(?=^# |\Z)", text, re.S | re.M)
    body = m.group(1) if m else text
    body = body.split("（書き方の例）")[0]
    return [l.rstrip() for l in body.splitlines() if l.startswith("- ")]


def parse_instruction(raw: str) -> Instruction:
    m = re.match(r"^- ([\d・、]+)行目は固定文なので変更しない", raw)
    if m:
        return Instruction(raw, [int(x) for x in re.findall(r"\d+", m.group(1))], "protect")
    m = re.match(r"^- (.+?行目(?:の直後に追加)?)[：:](.*)$", raw)
    if not m:
        return Instruction(raw, [], "free", note="行番号が読み取れない")
    head, body = m.group(1), m.group(2).strip()
    nos = [int(x) for x in re.findall(r"\d+", head)]
    if len(nos) != 1:
        return Instruction(raw, nos, "free")
    if head.endswith("の直後に追加"):
        mm = re.fullmatch(r"「(.*)」", body)
        if mm and LABEL_RE.match(mm.group(1)):
            return Instruction(raw, nos, "insert", text=mm.group(1))
        return Instruction(raw, nos, "free", note="追加する行の形が読み取れない")
    mm = re.fullmatch(r"全体を「(.*)」に", body)
    if mm:
        if LABEL_RE.match(mm.group(1)):
            return Instruction(raw, nos, "whole", text=mm.group(1))
        return Instruction(raw, nos, "free", note="新しい行に話者ラベルがない")
    mm = re.fullmatch(r"「(.*)」(?:の文)?を削除(?:する)?", body)
    if mm and "」を「" not in mm.group(1):
        return Instruction(raw, nos, "replace", pairs=[(mm.group(1), "")])
    if body.startswith("「") and body.endswith("」に"):
        pairs = []
        for p in body[1:-2].split("」に、「"):
            ab = p.split("」を「")
            if len(ab) != 2 or not ab[0]:
                return Instruction(raw, nos, "free")
            pairs.append((ab[0], ab[1]))
        return Instruction(raw, nos, "replace", pairs=pairs)
    return Instruction(raw, nos, "free")


@dataclass
class Entry:
    orig: Optional[int]   # 元の行番号（追加した行は None）
    text: str
    free: bool = False    # 機械で適用しない指示がある行（LLMが変えてよい）


def apply_instructions(raw_lines: List[str], instrs: List[Instruction]):
    """機械で適用できる指示を適用する。戻り値：（出力の行, 適用した指示, 残った指示, 元→新の行番号）"""
    cur = {l.no: l.raw for l in parse_lines(raw_lines)}
    protected = {n for i in instrs if i.kind == "protect" for n in i.nos}
    applied, residual, free_nos, dropped = [], [], set(), set()
    inserts: Dict[int, List[str]] = {}
    for ins in instrs:
        if ins.kind == "protect":
            continue
        no = ins.nos[0] if ins.nos else None
        if ins.kind != "free":
            if no not in cur:
                ins.kind, ins.note = "free", f"{no}行目が台本にない"
            elif no in protected and ins.kind != "insert":
                ins.kind, ins.note = "free", "固定文の行への指示"
        if ins.kind == "whole":
            if ins.text.split(": ")[0] != cur[no].split(": ")[0]:
                ins.note = "話者が元の行と違う（そのまま適用した）"
            cur[no] = ins.text
            applied.append(ins)
        elif ins.kind == "replace":
            s = cur[no]
            for a, b in ins.pairs:
                n = s.count(a)
                if n == 0 and b and b in s:
                    ins.note = (ins.note + " " if ins.note else "") + f"「{short(b, 20)}」はすでに入っている"
                    continue
                if n != 1:
                    ins.kind, ins.note = "free", f"「{short(a, 20)}」が行の中に{n}件"
                    break
                s = s.replace(a, b)
            if ins.kind == "replace":
                m = LABEL_RE.match(s)
                if (m and not m.group(2).strip()) or not s.strip():  # v3.9：話者ラベルのない行（E01）も消せる
                    dropped.add(no)
                    ins.note = "削除で本文が空になったので、行ごと削除した"
                cur[no] = re.sub(r"^((?:めたん|つむぎ|ずんだもん): )\s+", r"\1", s)
                applied.append(ins)
        elif ins.kind == "insert":
            inserts.setdefault(no, []).append(ins.text)
            applied.append(ins)
        if ins.kind == "free":
            residual.append(ins)
            free_nos.update(ins.nos)
    entries: List[Entry] = []
    for no in sorted(cur):
        if no not in dropped:
            entries.append(Entry(no, cur[no], no in free_nos))
        entries += [Entry(None, t) for t in inserts.get(no, [])]
    renum = {e.orig: i * 2 + 1 for i, e in enumerate(entries) if e.orig is not None}
    return entries, applied, residual, renum


def renumber(raw: str, renum: Dict[int, int]) -> str:
    """指示の先頭部分（「：」まで）の行番号を、置き換え後の行番号に直す"""
    head, sep, rest = raw.partition("：")
    head = re.sub(r"\d+", lambda m: str(renum.get(int(m.group(0)), m.group(0))), head)
    return head + sep + rest


def entries_text(entries: List[Entry]) -> str:
    return "\n\n".join(e.text for e in entries) + "\n"


def diff_hint(exp: str, act: str, limit: int = 3) -> str:
    sm = difflib.SequenceMatcher(None, exp, act, autojunk=False)
    parts = [f"「{exp[i1:i2]}」→「{act[j1:j2]}」"
             for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    return " / ".join(parts[:limit]) + (" …" if len(parts) > limit else "")


def verify_fix(before_raw: List[str], after_raw: List[str], instrs: List[Instruction]) -> List[Finding]:
    """LLMが修正した台本を、修正前の台本に指示を機械で当てた結果（期待値）と比べる"""
    expected, _, _, _ = apply_instructions(before_raw, instrs)
    actual = parse_lines(after_raw)
    out: List[Finding] = []

    def where(e: Entry) -> str:
        return f"元の{e.orig}行目" if e.orig else "追加される行"

    sm = difflib.SequenceMatcher(None, [e.text for e in expected], [a.raw for a in actual], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        exp, act = expected[i1:i2], actual[j1:j2]
        if tag == "equal":
            for e, a in zip(exp, act):
                if e.free:
                    out.append(Finding("WARN", "V04", [a.no],
                                       f"{where(e)}は指示があるのに変わっていない（指示が反映されたか確認）"))
            continue
        for e, a in zip(exp, act):
            if not e.free:
                out.append(Finding("ERROR", "V01", [a.no],
                                   f"{where(e)}が指示どおりになっていない: {diff_hint(e.text, a.raw)}",
                                   f"{a.no}行目：全体を「{e.text}」に"))
        prev_no = actual[j1 + len(exp[:len(act)]) - 1].no if j1 + min(len(exp), len(act)) > 0 else 0
        for e in exp[len(act):]:
            pos = f"（修正後の{prev_no}行目の後）" if prev_no else "（修正後の先頭）"
            if e.free:
                out.append(Finding("WARN", "V02", [prev_no] if prev_no else [],
                                   f"{where(e)}が消えている{pos}。指示の内容が行の削除なら問題ない: {short(e.text, 30)}"))
            else:
                out.append(Finding("ERROR", "V02", [prev_no] if prev_no else [],
                                   f"{where(e)}が消えている{pos}: {short(e.text, 30)}",
                                   f"{prev_no}行目の直後に追加：「{e.text}」"))
        near_free = any(x.free for x in expected[max(i1 - 1, 0):i2 + 1])
        for a in act[len(exp):]:
            out.append(Finding("WARN" if near_free else "ERROR", "V03", [a.no],
                               f"指示にない行が追加されている: {short(a.raw, 30)}"))
    return out


def main():
    ap = argparse.ArgumentParser(description="ガジェットマニア台本 機械チェック")
    ap.add_argument("script", help="チェックする台本ファイル")
    ap.add_argument("--common", help="共通部品ファイル（固定文・読み辞書・差し込みブロックを読む）")
    ap.add_argument("--total-min", type=int, default=7800,
                    help="ファイル全体の文字数の下限（W07、既定7800）")
    ap.add_argument("--total-max", type=int, default=0,
                    help="ファイル全体の文字数の上限（W07、0で無効＝上限なし）")
    ap.add_argument("--type", choices=["full", "op", "topic", "blog", "ed"], default="full",
                    help="full=通しの台本（既定） / それ以外=セクション単体")
    ap.add_argument("--apply-dict", metavar="OUT", help="読み辞書で置き換えた台本を書き出し、その台本をチェックする")
    ap.add_argument("--json", metavar="OUT", help="結果をJSONで書き出す")
    ap.add_argument("--fix-out", metavar="OUT", help="修正指示と行番号つき台本を書き出す")
    ap.add_argument("--fix-template", metavar="PATH", help="修正プロンプトのテンプレート（--fix-out と併用）")
    ap.add_argument("--topic-starts", metavar="N,N,N",
                    help="通しの台本で、お題1〜3の最初の行番号（カンマ区切り）。お題ごとに上限を数える")
    ap.add_argument("--materials", metavar="JSON", help="素材と照合する（--materials-help で形式を表示）")
    ap.add_argument("--materials-help", action="store_true", help="--materials のJSON形式を表示して終了")
    ap.add_argument("--extra-fix", metavar="TXT",
                    help="人が書いた修正指示（「- 31行目：〜」の形、1行1件）を修正プロンプトに足す")
    ap.add_argument("--apply-fix", metavar="PATH",
                    help="修正指示（修正プロンプト全体か「- 」の指示だけのファイル）を機械で適用する。--apply-out と併用")
    ap.add_argument("--apply-out", metavar="OUT", help="--apply-fix で置き換えた台本の書き出し先。この台本をチェックする")
    ap.add_argument("--residual-out", metavar="OUT",
                    help="--apply-fix で機械適用できなかった指示を、置き換え後の行番号で修正プロンプトにする（--fix-template を使う）")
    ap.add_argument("--verify-fix", metavar="PATH",
                    help="script をLLMの修正結果として、--before の台本と修正指示で照合する")
    ap.add_argument("--before", metavar="PATH", help="--verify-fix で使う、修正前の台本")
    if "--materials-help" in sys.argv:
        print(MATERIALS_HELP)
        sys.exit(0)
    args = ap.parse_args()

    with open(args.script, encoding="utf-8") as f:
        text = f.read()

    blocks = parse_common(args.common) if args.common else {}
    fixed = (fixed_from_common(blocks) if blocks else None) or DEFAULT_FIXED
    if blocks:
        KNOWN_KANA.extend(k for _, k in dict_from_common(blocks)[0])
        for line in (x for v in blocks.values() for x in v):
            m = re.search(r"よく知られた略語（(.+?)）", line)
            if m:
                abbr = [a.strip() for a in re.split(r"[、,]", m.group(1).replace("など", "")) if a.strip()]
                if abbr:
                    WELL_KNOWN_ABBR[:] = abbr
                break

    target = args.script
    if args.apply_fix and args.verify_fix:
        sys.exit("--apply-fix と --verify-fix は同時に使えません")

    if args.apply_fix:
        if not args.apply_out:
            sys.exit("--apply-fix には --apply-out が必要です")
        instrs = [parse_instruction(x) for x in load_instructions(args.apply_fix)]
        entries, applied, residual, renum = apply_instructions(text.splitlines(), instrs)
        text = entries_text(entries)
        with open(args.apply_out, "w", encoding="utf-8") as f:
            f.write(text)
        target = args.apply_out
        print(f"修正指示を機械で適用しました: {len(applied)}件 → {args.apply_out}")
        for ins in applied:
            if ins.note:
                print(f"  注意: {ins.raw[:40]}… … {ins.note}")
        if residual:
            print(f"機械で適用できなかった指示: {len(residual)}件（LLMで直す）")
            for ins in residual:
                print(f"  {ins.raw}" + (f"  ※{ins.note}" if ins.note else ""))
            if args.residual_out:
                protect = [renumber(i.raw, renum) for i in instrs if i.kind == "protect"]
                request = "\n".join([renumber(i.raw, renum) for i in residual] + protect)
                rest_lines = text.splitlines()
                rest_script = numbered_script(parse_lines(rest_lines))
                if args.fix_template:
                    out = build_fix_prompt(args.fix_template, request, rest_script, blocks)
                else:
                    out = f"# 修正指示\n{request}\n\n# 台本（行番号つき）\n{rest_script}\n"
                with open(args.residual_out, "w", encoding="utf-8") as f:
                    f.write(out)
                print(f"残りの指示の修正プロンプトを書き出しました: {args.residual_out}")
        else:
            print("すべての指示を機械で適用しました")

    verify_findings: List[Finding] = []
    if args.verify_fix:
        if not args.before:
            sys.exit("--verify-fix には --before が必要です")
        with open(args.before, encoding="utf-8") as f:
            before_text = f.read()
        instrs = [parse_instruction(x) for x in load_instructions(args.verify_fix)]
        verify_findings = verify_fix(before_text.splitlines(), text.splitlines(), instrs)
        nb, na = len(parse_lines(before_text.splitlines())), len(parse_lines(text.splitlines()))
        print(f"■ 修正結果の照合: 修正前 {nb}発言 → 修正後 {na}発言（指示 {len(instrs)}件）")

    if args.apply_dict:
        if not blocks:
            sys.exit("--apply-dict には --common が必要です")
        entries, unify = dict_from_common(blocks)
        text = apply_dictionary(text, entries, unify)
        with open(args.apply_dict, "w", encoding="utf-8") as f:
            f.write(text)
        target = args.apply_dict
        print(f"読み辞書を適用して書き出しました: {args.apply_dict}")

    single = None if args.type == "full" else TYPE_TO_SECTION[args.type]
    starts = None
    if args.topic_starts:
        try:
            starts = [int(x) for x in args.topic_starts.split(",") if x.strip()]
        except ValueError:
            sys.exit("--topic-starts は行番号をカンマ区切りで指定してください（例：31,85,135）")
    materials = None
    if args.materials:
        with open(args.materials, encoding="utf-8") as f:
            materials = json.load(f)
    notation = dict_from_common(blocks)[1] if blocks else None
    report, lines = check(text.splitlines(), fixed, single, starts, materials,
                          total_chars=len(text), total_min=args.total_min,
                          total_max=args.total_max, notation=notation)
    if verify_findings:
        # 照合で「全体を〜に」と直す行は、ほかの指示を外す（同じ行への指示が重ならないように）
        whole_nos = {f.lines[0] for f in verify_findings if f.code == "V01"}
        for f in report.findings:
            if f.instruction and f.lines and f.lines[0] in whole_nos:
                f.instruction = ""
        report.findings += verify_findings
        report.findings.sort(key=lambda f: ({"ERROR": 0, "FIX": 1, "WARN": 2}[f.level], f.lines[0] if f.lines else 0))
    print_report(report, target)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"stats": report.stats, "findings": [asdict(x) for x in report.findings]},
                      f, ensure_ascii=False, indent=2)

    if args.fix_out:
        request = build_fix_request(report, lines)
        if args.extra_fix:
            with open(args.extra_fix, encoding="utf-8") as f:
                extra = [x.rstrip() for x in f if x.strip().startswith("- ")]
            body_lines = request.splitlines()
            # 人の指示がある行は、機械の指示を外す（同じ行への指示が食い違わないように）
            human_nos = set()
            for x in extra:
                m = re.match(r"^- (\d+)行目", x)
                if m:
                    human_nos.add(int(m.group(1)))
            def first_no(x):
                m = re.match(r"^- (\d+)", x)
                return int(m.group(1)) if m else None
            keep = [x for x in body_lines if "固定文なので" not in x and first_no(x) not in human_nos]
            fixed_note = [x for x in body_lines if "固定文なので" in x]
            request = "\n".join(dict.fromkeys(keep + extra + fixed_note))
        if not request.strip() or all(l.startswith("- ") and "固定文なので" in l for l in request.splitlines()):
            print("修正プロンプトに回す項目はありません")
        else:
            script = numbered_script(lines)
            if args.fix_template:
                out = build_fix_prompt(args.fix_template, request, script, blocks)
            else:
                out = f"# 修正指示\n{request}\n\n# 台本（行番号つき）\n{script}\n"
            with open(args.fix_out, "w", encoding="utf-8") as f:
                f.write(out)
            print(f"修正プロンプトを書き出しました: {args.fix_out}")

    levels = {f.level for f in report.findings}
    sys.exit(2 if "ERROR" in levels else 1 if levels else 0)


if __name__ == "__main__":
    main()
