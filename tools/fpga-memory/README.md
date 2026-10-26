# 外部RAMオブジェクトのホストmock

目的、APIの扱い、確認結果、未解決事項は
[開発記録](../../docs/OFFLINE_RAM_DEVELOPMENT.md)を参照。

```text
python tools/fpga-memory/memory_mock.py --mock
python tools/fpga-memory/memory_mock.py --mock --size 67108864 --transfer-limit 65536
python -m unittest discover -s tools/fpga-memory -p test_memory_mock.py -v
```

追加パッケージ不要。PCの一時ファイルだけを利用し、Tab5・FPGA・GPIO・COMへ接続しない。
既存の `tools/fpga-link/` の接続試験v0にはメモリopcodeを追加しない。
CLIは1オブジェクト128MiB、1転送1MiBを上限とし、一時ファイル容量はsizeの2倍。

Linuxだけで実行できるC版は [Cファイルモデル診断](../../docs/LINUX_MEMORY_PROBE.md) を参照。`run_file_probe.py --cc cc --sanitize` で独立期待値・不正引数・破損検出を検証する。標準CIはMeOSを取得せず、このリポジトリ内で完結する。

容量制限付きLRU/write-throughキャッシュは [設計・結果・制約](../../docs/BLOCK_CACHE.md) を参照。`python tools/fpga-memory/cache_demo.py --mock` で繰返し読出しの同一性とbackend要求回数を比較できる。時間や実機性能は測定しない。
