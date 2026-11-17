# Python 移植 (作業中)

Phase 1: 情報スポットの取得系のみ移植済み。標準ライブラリのみ (依存ゼロ)。

## 動作確認 (2026-11-17 実データで確認済み)

```bash
cd py
PYTHONPATH=src python3 -m radio.sources.weather   # 気象庁 (getWeather.php 移植)
PYTHONPATH=src python3 -m radio.sources.traffic   # JARTIC (getJartic.php 移植)
```

どちらも元の PHP と同形の JSON を標準出力に出す。
元との差分は ../STRUCTURE.md と各モジュール冒頭の docstring を参照。
