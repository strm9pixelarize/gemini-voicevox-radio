# gemini-voicevox-radio フォーク設計メモ（スケジュール駆動版）

作成: 2026-11-16 / 元リポジトリ: jikantoki/gemini-voicevox-radio (GPL)

## 元設計との決定的な違い

| 項目 | 元 (ねるるラジオ) | 優フォーク |
|---|---|---|
| 生成頻度 | 毎時4本 × 24h = **96本/日 (672本/週)** | 長編4本/日 (30〜45分) + 情報は毎時 :15交通 / :45天気 (下記2レーン構成) |
| 起動 | cron 毎時54分 → 全枠一括生成 | スケジューラが「次の放送枠」だけを先行生成 |
| 放送 | AzuraCast 定時割り込み (00/15/30/45) | AzuraCast スケジュールプレイリスト（曜日・時刻指定）と生成側を一致させる |
| Podcast | 対象3番組を自動アーカイブ + RSS | `podcast: true` の番組だけをエピソード化。放送専用枠はフィードに流さない |
| LLM | Gemini 主、Ollama フォールバック | Provider 抽象化 (Claude/Gemini/Ollama)。本数が少ないので Muse を主役にできる |
| 尺 | 全枠 11分/660秒に atempo で収束 | 番組ごとに目標尺を設定 (例: 15分 / 25分) |

96本/日だと Muse API の従量課金、VOICEVOX 合成時間 (i3-8100 ホスト)、
MP3 保管量のどれを取っても破綻する。週7〜14本なら逆に全部が現実的になる。

## 核: schedule.yaml を唯一の「正」にする

ブログ運用 (src が正、生成物は使い捨て) と同じ流儀。
番組表はコードに埋めず、1ファイルの定義から生成・放送・Podcast を全部決める。

```yaml
# 例 (たたき台。番組名・曜日・時刻は未決定)
programs:
  - id: morning-news
    title: "朝のニュース枠 (仮)"
    schedule: { days: [mon, tue, wed, thu, fri], time: "07:00" }
    generate_before_minutes: 60        # 放送の何分前に生成するか
    duration_target_sec: 900           # 目標尺 15分
    prompt: prompts/morning-news.txt
    speakers: [metan, tsumugi, hau]    # VOICEVOX 話者
    llm: Muse                        # 番組ごとに provider を選べる
    azuracast: { station: "<未決定>", playlist: "morning-news" }
    podcast: false                     # 放送専用。フィードには載せない

  - id: weekly-gadget
    title: "週1の特集枠 (仮)"
    schedule: { days: [sat], time: "20:00" }
    generate_before_minutes: 180
    duration_target_sec: 1500          # 25分
    prompt: prompts/weekly-gadget.txt
    speakers: [metan, tsumugi, zundamon]
    llm: Muse
    azuracast: { station: "<未決定>", playlist: "weekly-gadget" }
    podcast: true                      # エピソード化 + RSS 更新
    podcast_feed: gadget               # フィードは番組単位
```

## 生成スケジューラの動き

1. 常駐 or cron の tick (例: 5分間隔) で schedule.yaml を読む
2. 「放送時刻 - generate_before」が過ぎていて、対象回の生成物がまだ無い枠だけ実行
   - 生成物は `episodes/<program-id>/<YYYY-MM-DD>.mp3` のように回ごとに一意
   - 既にあればスキップ (冪等)。再実行しても二重生成しない
3. パイプラインは元と同じ5段: プロンプト組立 → LLM原稿 → 発話パース →
   VOICEVOX合成・WAV結合 → FFmpegミックス (番組別 duration_target で atempo)
4. 完了後に AzuraCast メディアフォルダへ配置。`podcast: true` なら
   Podcast 保存先へもコピーし、その番組の RSS を更新
5. 失敗時は通知 (元は Mattermost。優環境では要差し替え検討) + 次 tick で再試行可

## AzuraCast 側との同期

- 生成スケジュールと放送スケジュールは本来2か所 (自作側 / AzuraCast側) に
  分かれる。ズレると「生成したのに流れない / 流すのに無い」が起きる
- 対策: schedule.yaml を正とし、AzuraCast 側のスケジュールプレイリストは
  それに合わせて作る (曜日・時刻・割り込み ON)。将来 AzuraCast API で
  プレイリスト生成まで自動化できるかは要調査 (未確認)

## 確定した番組構成 (2026-11-16 優の指定)

2レーンに分離する。具体定義は `schedule.yaml` が正。

### レーン1: 長編番組
- 毎日 **12 / 15 / 18 / 21 時** の4枠、各 **30〜45分** (週28本)
- 原稿は概算で約12,000〜16,000字になるため、LLM生成は1回で出さず
  幕ごとに分割生成して連結する方式にする (出力上限・話の継続性対策)
- 生成間隔は3時間あるので、合成時間を考えても先行生成は直列で回せる想定 (要実測)
- Podcast 化の単位 (全枠か、スロット別フィードか、選抜か) は未決定

### レーン2: 情報スポット (天気・渋滞)
- **毎時 :15 = 交通情報、:45 = 天気情報** を独立した短いコーナーとして流す (2026-11-17 決定。当初の「15分ごと」から具体化)
- 割り込み方式も決定: **AzuraCast のスケジュール機能で長編の途中にも強制割り込み**する。交通・天気で別々のスケジュールプレイリスト (interrupt ON) を作る
- 尺は **各約3分** (2026-11-17 決定)。3分に収める方法は atempo の速度上げではなく、読み上げる項目数 (渋滞箇所・観測地点) の削減を優先する
- 割り込み前提での注意点:
  - 長編は :00 開始で 30〜45分尺なので、:15 の交通は必ず番組の真ん中に入る。:45 の天気は、30分尺なら番組終了後、45分尺なら終了時刻とちょうど重なる
  - AzuraCast の現行割り込み仕様は「割り込まれたトラックはスポット終了後に途中から再開する」(公式 Issue #7554 で現行挙動として言及)。再開する分、放送タイムラインはスポット1回ごとに約3分後ろへずれる。45分尺の回が :15 と :45 の両方で割り込まれると終了は最大で約6分遅れになる。次の長編は 15:00 / 18:00 / 21:00 と間が空くため遅れは枠を跨いで累積しないが、45分尺の回は尺を少し短めに寄せるかは実装時に要調整
  - この再開挙動は同居人の環境 (元システム稼働環境) で確認済みのため、実機検証は不要として進める (2026-11-17 優の判断)
- 優の困りごと: 元は番組プロンプト内に天気・渋滞が混在し、番組の途中で
  唐突に情報が出て困惑することがある → **混ぜるのをやめるのが解決策**
  - 長編のプロンプトには天気・渋滞コンテキストを注入しない
  - 情報は定型フォーマットに最新データを差し込むだけにし、LLM の創作を入れない
    (唐突感が消え、コストもほぼゼロになり、読み間違いも減る)
  - 鮮度が命なので生成は放送の約5分前。ファイルは上書き式でアーカイブしない
  - Podcast には載せない (鮮度切れの天気・渋滞に聞き返す価値がないため)
  - 入り/出にジングルを挟み「情報コーナーである」ことを枠で明示する
- 長編放送中にも AzuraCast スケジュールで強制割り込みする (決定済み)。
  その分、ジングルによる枠明示が必須条件になる

## 着手順 (2026-11-17 提案)

全部を移植してから動かすのではなく、縦に1本通してから広げる。

- **Phase 0: 土台**
  1. GitHub フォーク → **完了 (2026-11-17)**: https://github.com/strm9pixelarize/gemini-voicevox-radio
     (公開、main のみ、元と同一コミット 4663d97)。残りは Python リポジトリの骨格作り
  2. ~~AzuraCast 割り込みの実機検証~~ → **不要 (2026-11-17 優が確認済みと報告)**:
     同居人の環境 (元システムの稼働環境) で、割り込む側・割り込まれる側の
     挙動は確認済みのため、そのまま進める
- **Phase 1: 情報スポットを先に完成させる (最初の縦切り)**
  - getWeather.php / getJartic.php の Python 移植 → **取得系は完了 (2026-11-17)**:
    `py/src/radio/sources/weather.py` / `traffic.py` を実データで動作確認済み
    (東京14.5度・翌日天気・概況、交通は関東の規制一覧を取得)。
    残り: 定型原稿 → VOICEVOX → ジングル付き3分MP3 → AzuraCast 配置
  - 定型原稿と生成パイプラインは実装済み (2026-11-17): 原稿生成は
    `py/src/radio/spots.py` (文字数バジェット+trim_items)、実行入口は
    `py/tools/make_spot.py` (取得→原稿→合成→WAV結合→MP3、計測値JSON出力)。
    原稿生成は実データ確認済み (天気13行474字 / 交通25行919字)、
    WAV結合とMP3化はダミー音声で検証済み。ホスト実機での1本通しも
    完了 (2026-11-17 21:32、output/ への生成を確認)。実測 (同日):
    天気 474字/13行 → 音声96.9秒・合成0.8秒、交通 848字/23行 →
    音声182.6秒・合成1.42秒。読み上げは約5.0字/秒＋行間0.35秒/行で、
    原稿バジェットは 860字に較正済み (spots.py)。合成は音声長の
    約1/120の時間で終わるため、長編の generate_before=180分は
    合成ではなく LLM 原稿生成側の余裕として Phase 2 で再検討する。
    天気は要素不足で約97秒止まり (474字が上限) — 要素追加か
    尺の許容は試聴印象を見て判断 (2026-11-17 優「問題ない」)。
    ジングル対応は実装済み (同日): make_spot.py が --jingle-in/
    --jingle-out、または ../assets の jingle_in.mp3 / jingle_out.mp3
    を自動検出し、声と同じ形式に変換して前後に接続。ジングル秒数
    ぶん原稿バジェットを自動で差し引く。ダミージングルで検証済み。
    対象ステーションは id=8「ねるるの日常(健全版)」に決定
    (2026-11-17 優、全番組・全スポット共通)。AzuraCast 配置まで
    完了し、2026-11-18 01:45 の天気スロットで割り込み再生が
    実際に発火したことを確認 → **Phase 1 完了**
  - 宿題 (後日): 割り込みの唐突感の改善。優「無理やり感が否めない」
    (2026-11-18)。候補はジングル音声の実配置と、入り/出の緩和
    (フェード等)。放送を回しながら判断する
  - 構造レビューは STRUCTURE.md に逐次記録する (優の追加注文 2026-11-17)
  - LLM を使わないので一番リスクが低く、データ取得・合成・ミックス・配置・
    放送という全工程の部品がここで揃う。長編側はこの部品の再利用になる
  - あわせて VOICEVOX の合成速度を実測する (3分スポットで実測→長編に換算し、
    generate_before_minutes=180 が妥当か決める)
- **Phase 2: 長編を1枠だけ**
  - Muse API の原稿テスト: 元 prompts を使い、話者行フォーマットが
    パーサーに通るか、分割生成 (3幕) で話が繋がるかを先に確認 (APIキーが必要)
  - 通ったら 21時枠だけを本番パイプラインに載せ、数日回して様子を見る
- **Phase 3: 展開**
  - 残り3枠 (12/15/18時) を追加、Podcast 化と RSS、スケジューラの常駐化、
    失敗通知

## 未決定事項

- [x] 番組のペース: 長編は毎日4枠 (12/15/18/21時)、情報は毎時 :15交通 / :45天気 に決定
- [ ] 番組ラインナップ (各長編枠のテーマ・話者)
- [x] 情報スポット: 毎時 :15 交通 / :45 天気、長編途中にも強制割り込み で決定
- [ ] 情報スポット: 稼働時間帯 (24hか放送時間帯のみか)
- [ ] Podcast 化の単位 (長編全枠か、スロット別か、選抜か)
- [x] 対象ステーション: 既存の id=8「ねるるの日常(健全版)」に決定
  (2026-11-17 優)。全番組・全スポットをこの局に載せる
- [ ] Podcast の公開先 (自鯖ブログ配下か、AzuraCast の Pages か、別ドメインか)
- [ ] VOICEVOX Engine の常駐方法 (Docker コンテナ想定)
- [ ] 失敗通知の宛先 (Mattermost は優環境に無い)

## ペースの目安

- 毎日1本 (週7本): Podcast として習慣化しやすい。Muse コストも最小クラス
- 週3本程度: 1本の尺を伸ばして特集型にできる。平日ニュース+週末特集の混成も可
- どちらでも元設計比で生成量は 1/48〜1/96。まず少なく始めて増やす方が、
  原稿の質チェック (話者形式の維持) も回しやすい

## 配置 (2026-11-17 決定)

ホスト配置先は /DATA/AppData/azuracast_program/ (優の提案、他の
/DATA/AppData/* 運用と同型):

    /DATA/AppData/azuracast_program/
      repo/            # フォークの git clone (py/, schedule.yaml, prompts/)
                       # リポジトリ直下の設計文書 (PLAN.md / STRUCTURE.md /
                       # CASTING.md / schedule.yaml) は Git 管理。CASTING.md
                       # (配役表) もここ — 決まった話者は schedule.yaml の
                       # speakers に転記する
      .env             # APIキー等。repo の外に置き Git 管理外
      assets/          # BGM・ジングルの実ファイル (Git 外)
      output/          # 生成 MP3 のステージング (traffic_latest.mp3 等)
      state/  logs/    # 実行状態とログ
      docker-compose.yml  # 生成系＋VOICEVOX (Portainer Stack 可)

配信への受け渡し: 生成コンテナに AzuraCast のステーションメディア
フォルダを bind mount し、完成 MP3 を直接置く。ホスト側の実パスは
対象ステーション決定後に docker inspect azuracast の Mounts で確認する。

### 受け渡しモデルの訂正 (2026-11-17 01:17 優)

元システムはイントラネットのサーバーをマウントして読みに行く方式だったが、
今回は採らない。音に関わる部分だけ外部サーバーに頼り、生成した音声の
置き場は自分のフォルダ (/DATA/AppData/azuracast_program/output/) にする。
→ 上記の「生成コンテナに AzuraCast メディアを bind mount」案は撤回。
外部が担う範囲 (VOICEVOX合成 / AzuraCast配信 / 両方) と、自分のフォルダ
から外部へどう渡すかは確認中。

### 受け渡しモデルの確定 (2026-11-18)

id=8 のメディア保存先は NAS マウント (/var/azuracast/intranet_music、
7局共有) だったため、AzuraCast 側の override に output/ の bind mount
を追加して解決した:
  /DATA/AppData/azuracast_program/output
    -> /var/azuracast/intranet_music/nerurus_room_rest (コンテナ内)
フォルダ名 nerurus_room_rest は優の命名。AzuraCast からは NAS 内の
フォルダに見えるが実体は output/ で、「生成物の正は自分のフォルダ」
は維持される。2026-11-18 に再作成とコンテナ内でのファイル確認まで
完了 (weather/traffic の mp3・txt が見える状態)。

### 外部に頼る範囲の決定 (2026-11-17 01:18 優)

外部サーバーに頼るのは **VOICEVOX 合成のみ**。原稿生成・スケジューラ・
AzuraCast・音声の置き場は全部自前ホスト側。
- 生成側は外部 VOICEVOX Engine の HTTP API (50021) を叩く。
  接続先は .env の VOICEVOX_HOST (元の env.php と同じ変数名)
- py/src/radio/voicevox.py にクライアントを作成済み。長編は数百回の
  audio_query/synthesis を回すため、接続を使い回す実装にした
- 実測ポイント: 外部合成の所要時間 (長編 generate_before=180分 の妥当性)、
  話者ID は外部 Engine 側の /speakers が正になる
- 接続先 URL は未提供 (決まったら .env に入れる)

接続先 (2026-11-17 優): voicevox.enoki.local
- 当初は VOICEVOX_HOST=http://voicevox.enoki.local:50021 (直接) の想定だったが、
  実機確認の結果、直接の 50021 は RTX1300 の IPフィルター (LAN1受信の
  ホワイトリスト+100009 reject) と宛先 jikantoki-sub の ufw (ALLOW に
  50021 が無い) の二段で遮断されていた
- 正規ルートはポート80経由: jikantoki-sub の Apache が ServerName
  voicevox.enoki.local のバーチャルホストで Engine (localhost:50021、
  version 0.25.2、0.0.0.0 で LISTEN) へリバースプロキシしている。
  op3060m から Host ヘッダ付き curl で Engine のトップページが返ることを確認
- よって .env は VOICEVOX_HOST=http://voicevox.enoki.local (ポート80)。
  接続元で名前解決できることが前提 (ホストは /etc/hosts に
  192.168.104.3 voicevox.enoki.local、コンテナは compose の extra_hosts)。
  ufw への 50021 追加は不要になった
- 疎通確認完了 (2026-11-17 19:14): op3060m の /etc/hosts に
  192.168.104.3 voicevox.enoki.local を追加済み。名前経由で /version
  (0.25.2)・/speakers が返り、audio_query→synthesis (speaker=2) で
  138,284 バイトの WAV (PCM 16bit mono 24000Hz) が生成できた。
  プロキシ経由の GET/POST/バイナリ転送すべて実証済みで、この件は完了
- .local 名なので解決できるのは自宅 LAN 内だけ。アシスタントの VM からは
  到達できないことを確認済み (名前は引けるが接続不可)
- そのため接続確認はホスト側で py/tools/check_voicevox.py を実行して行う
  (version / 話者一覧 / 1行合成の所要時間を出す)
