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
