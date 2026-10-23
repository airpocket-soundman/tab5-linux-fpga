# 実機不使用での開発記録 — 2026-10-23

## 目的と作業範囲

ユーザー指示によりTab5を利用せず、Linux側の外部RAM意味モデル、MeOS向け移植可能Cコア、互換性整理を並列開発した。RAM活用を主目的とし、GPUのVRAM・転送予算も検証可能な計算へ落とし込む。COM・USB・GPIO・ネットワーク経由のTab5操作、フラッシュ書き込みは行わない。

作業基準はLinux `f37b830`、MeOS `7562806`。MeOSの既存MicroPython変更は対象に含めない。

## 成果物

- [外部RAM意味モデル](OFFLINE_RAM_DEVELOPMENT.md)：ファイルを外部領域としたオブジェクト管理、分割処理、退避・復元、寿命・範囲・途中故障のテスト。
- [共通データの照合](CROSS_OS_MEMORY_CONFORMANCE.md)：Linux向けPythonモデルとMeOS向けC実装に同じ入力を渡すホスト試験。
- [統合条件](OFFLINE_INTEGRATION_PLAN.md)：既存接続試験v0、メモリ操作、GPU、OS別アダプタの境界と実機再開時の通過条件。
- [GPUバッファとfence](../tools/fpga-gpu-model/README.md)：描画中の所有権、timeout時の不確定状態、停止確認後の復帰、resetによるhandle無効化をモデル化。
- [VRAM・読戻し帯域計算](../tools/fpga-budget/README.md)：容量、stride、相対配置、必要payload帯域の算術モデル。
- `.github/workflows/offline-memory.yml`：Python試験とGCC/ClangによるC互換性試験。Tab5接続不要。
- MeOS側の `experiments/fpga-memory/`：同期callbackによる境界検査・分割転送とホスト試験。OSや物理backendへの組込みは未実施。

## 確認結果

確認環境はWindows、Python 3.12、既存Zig 0.13.0のhost C compiler。Linuxの既存link Python14件とC codec583ケースの基準試験が成功。新規memory14件、budget7件、GPU所有権13件、C CLI583ケース・513往復、両実装の共通12条件が成功。MeOS Cは8,514通りの位置・分割条件と途中失敗を検証した。双方の64MiB/64KiB復元CRC32は `8d536c88` で一致。詳細・実行コマンドは各文書へ記録する。GCC/ClangのCIでも共通照合とC試験が成功した。MeOSはaddress/undefined sanitizer付き。実行履歴は [Linux](https://github.com/airpocket-soundman/tab5-linux-fpga/actions/workflows/offline-memory.yml)、[MeOS](https://github.com/airpocket-soundman/tab5-meos-fpga/actions/workflows/offline-fpga-memory.yml) に残す。

データ照合、型・範囲検査、解放後や別instanceのhandle拒否、重複copy、短い読み書き・途中故障を検証する。64MiBの分割処理はPC上の一時ファイルによる模擬外部領域で行い、Tab5の常駐RAM量やDDR3・PARLIO帯域の実測とは区別する。

## 未解決事項と次の作業

正式なメモリwire ABI、物理transport、GPIO電気条件、DDR3コントローラ、DMA・IRQ・cache同期、OSタスクとの協調、GPU回路と表示経路は未検証。固定8byteの接続試験v0へ独自のメモリopcodeを追加しない。現在のcallback、handle、64-byte配置、転送上限は実験用の意味契約であり、そのままwire ABIとして固定しない。

次は共通入力・期待値をRTL試験と正式API設計へ接続する。基板・実機再開後は低速接続試験、DDR3全域分割照合、OS別backendの順に確認する。実機再開の指示があるまでデバイス操作を行わない。

追加レビューでGPUの画像世代とfence解放を補強。古い完了fenceで上書き済み画像を読めないこと、terminal fence解放で参照が残らないことを確認した。RAM割当は固定seedの1000操作を独立bytearray参照へ照合し、全解放後に全容量を再確保できた。

## Linux版への作業限定とC診断の追加

ユーザー指示により、以後はこのリポジトリだけを変更する。Linux PR #1は既存の開発ブランチ `codex/st7121-display` にマージした（merge `e617253`）。mainへの未検証のハードウェア変更一括取り込みは行わない。

追加した [Cメモリ診断](LINUX_MEMORY_PROBE.md) はtmpfileだけを操作するmockであり、ファイルパス・デバイスbackendを受け取らない。固定64KiBバッファをstatic領域に置き、住所に依存する2種類のパターンで書込み・読戻しを検査する。18条件の独立CRC照合、不正引数13件、破損注入3件を検査する。

ホストの64MiB/64KiB・2pass試験でCRC32 `433b8578` / `645740d1` を確認。書込み・読取り各2048回。128MiBは2passの照合合計であり、1passのデータ領域は64MiB。この数値をFPGA容量・帯域の実測として扱わない。

標準CIは外部のMeOSリポジトリを取得しない構成に変更。任意の過去比較runnerは履歴として残す。GCC/Clangのsanitizer検査と、既存SDKによるrv32imac NOMMU bFLTビルド・ヘッダ検査を追加した。ターゲットビルドはTab5での実行を意味しない。tmpfileの保存先と空き容量の確認は実機再開後の残件。
