# Tab5 Linux FPGA 開発目的と引き継ぎ

更新日：2026-10-26

## 目的

M5Stack Tab5のNOMMU Linuxを基盤に、Tang Primer 20Kと通信するLinuxドライバとビルド環境を開発する。FPGA側の128MB DDR3を明示的なデータ保存・退避領域として使い、演算オフロードを可能にする。

Linux版ではLinuxのAPIや開発資産を利用して研究を進める。別リポジトリ [tab5-meos-fpga](https://github.com/airpocket-soundman/tab5-meos-fpga) でMeOS版も開発する。OS別の実装・検証を区別し、LinuxとMeOSの実行速度の優劣を実測前に主張しない。

主目的はFPGA側RAMの活用であり、小容量のP4作業バッファで大容量データを分割処理する。GPU用VRAMと描画構成も応用として検討する。実機が使えない期間の実装・試験は [2026-10-23開発記録](OFFLINE_DEVELOPMENT_2026-10-23.md) を参照する。

## リポジトリの役割

| リポジトリ | 管理するもの |
| --- | --- |
| [tab5-linux-fpga](https://github.com/airpocket-soundman/tab5-linux-fpga) | Tab5 Linux本体、起動処理、Device Tree、FPGA通信ドライバ、ユーザーランドへの接続、OSイメージのビルド |
| [esp32p4-linux-fpga-memory](https://github.com/airpocket-soundman/esp32p4-linux-fpga-memory) | 外部メモリ研究計画、用途別FPGA回路、評価アプリ、測定結果 |
| [tab5-tang-primer20k-carrier](https://github.com/airpocket-soundman/tab5-tang-primer20k-carrier) | 共通キャリア基板、回路・PCB、共通ハードウェア仕様の起点 |
| [tab5-fpga-gpu](https://github.com/airpocket-soundman/tab5-fpga-gpu) | 独立したGPU研究。初期段階の同時動作は要件に含めない |

Linuxソースを研究リポジトリへ丸ごとコピーせず、このフォークで履歴を保って開発する。評価結果には使用したOSコミットとFPGAビットストリームの識別情報を記録する。

## 出発点と現在の状態

- フォーク元：[Riti0208/tab5-linux](https://github.com/Riti0208/tab5-linux)。開始コミットは `ac23ca99e1a2f32769dc777f394d29e1f56525ba`。
- その移植元：[tsuyoshi-otake/m5stamp-p4-c6-linux](https://github.com/tsuyoshi-otake/m5stamp-p4-c6-linux)。Linux更新、SMP、割り込み・障害処理の修正を追跡する。
- 2026-10-22、ST7121用パネル初期化を追加し、ビルドと実機の液晶表示・1コア起動・シリアルシェル・Wi-Fi SoftAP起動を確認した。記録は [初回起動記録](BRINGUP_2026-10-22.md)。その後、Wi-Fi STA接続・再起動後の設定維持、PCからm5ユーザーへのSSH鍵認証ログイン、SSHクライアントとサーバーの接続、16GB FAT32 microSD認識と書き込みも確認した。USB root hub/HIDドライバは起動するが、実キーボードがないため入力は未検証で、L0全体は未完了。FPGA通信と転送性能は未検証。
- 基板なしの準備として、既存の接続試験v0と互換のcodec・mock CLI・故障注入テストを追加した。[基板なし準備](FPGA_LINK_PREPARATION.md)参照。PC上の照合であり、Tab5やFPGAの物理通信・L2完了を意味しない。
- Vim tiny・nano tinyのSSH端末での編集・microSD保存、SLの画面更新・正常終了を確認した。Vimのstackは実機で256KiBを必要とした。0080でphysmapのROMサイズ切り下げを修正し、Linuxから7MiB全域と大きいrootfsの起動を確認した。使い方は[ターミナルアプリ](TERMINAL_APPLICATIONS.md)。
- タッチ入力とtty1の128行履歴、NOMMU用BLE HIDホストを実験実装した。オフライン入力テストとbFLTビルドは成功。実機でタッチFW認識・指の上下スワイプ・履歴表示/復帰を確認。BTは暗号設定修正後のhci0認識とスキャン正常終了を確認し、K68のペアリング・入力は未検証。[開発記録](TOUCH_AND_BLUETOOTH.md)参照。
- 以下の既存READMEの動作記載は上流による報告であり、このフォークでの検証記録ではない。

上流のTab5版はLinux 6.18系、1コア起動、ST7123液晶、Tab5 Keyboard、Wi-Fi、SSHを対象とする。ILI9881CとST7121の液晶は未対応。詳細は [Tab5移植資料](tab5.md) と [日本語README](../README.ja.md) を参照する。

## 開発段階と完了条件

| 段階 | 作業 | 完了条件 |
| --- | --- | --- |
| L0 | 現状の1コア構成を再現する | ビルド手順、依存バージョン、イメージのハッシュ、起動ログを保存。シリアルシェル、対応液晶、キーボード、Wi-FiとSSHを確認し、メモリ情報を記録 |
| L1 | 上流修正を評価する | 修正の採否・依存関係を記録し、L0の機能を再確認。SMP有効化は安定性の検証後に判断 |
| L2 | FPGA通信の最小実装 | GPIO競合とPARLIO対応を確認し、低速のコマンド送受信とデータ照合を実機で完了 |
| L3 | ドライバとDMAを実装する | `/dev/`経由でREADとWRITEを実行し、タイムアウト、エラー通知、バッファ寿命、キャッシュ同期を検証 |
| L4 | 外部メモリ研究と接続する | 研究側の評価アプリから128MB全域を分割して読み書き・照合し、帯域、遅延、CPU負荷を記録 |

最初は既存の1コア構成を基準にする。カーネル更新、SMP有効化、FPGAドライバ追加を一度に行わず、変更ごとに基準との差を確認する。

## FPGA通信の方針

初期案は8bit PARLIOと制御線による接続。コマンド、アドレス、長さ、要求ID、ペイロード、CRC、READYまたは割り込みを検討する。DMAは目標であり、利用可能なLinuxドライバは未確定。SDIOや表示用DMAが動くことを、PARLIO DMA対応の証拠として扱わない。

GPIO割り当てと電源は、キャリア基板リポジトリと研究リポジトリの共通ハードウェア仕様を照合する。現在の割り当ては暫定で、内部機器との競合、GPIOドライバの他ピンへの影響、起動時の状態、IRQ、DMA、キャッシュ整合性を確認してから固定する。

## メモリ管理の前提

FPGA側DDR3はPARLIO経由の外部データ領域であり、P4が直接ロード・ストアできる通常のRAMではない。接続してもLinuxの空きRAMが128MB増えるわけではない。

P4に通常のMMUがない制約は残る。「FPGA仮想MMU」は研究上の仮称で、透過的なページング、通常のスワップ、無改造アプリの大容量mallocを目標達成済みと扱わない。まず明示的なREAD、WRITE、COPY、FILL、データ退避・復元、演算オフロードを扱う。

## 最初に行う作業

1. 手元のTab5のSoCリビジョンと液晶型番、キーボードを確認する。
2. P4の工場出荷フラッシュを保存し、C6の復元用ファームウェアと手順を確保する。P4のバックアップだけではC6は復元できない。
3. 上流の手順で現状をビルドし、L0を実行する。C6をESP-Hosted-NGへ更新すると、工場出荷ファームウェアのWi-Fiを使うにはC6も戻す必要がある。
4. READMEと `docs/tab5.md` で設定保存について記載が食い違うため、`/boot/config.txt` の編集・再起動後の永続化を実機で確認する。
5. 上流との差分を整理し、割り込み・障害処理など必要な修正から評価する。
6. PARLIOのレジスタ、DMA、ピン制御、Linux側の対応状況を調査し、最小通信を設計する。

ビルド入口は既存の `EASYSTICK_BOARD=tab5 bash linux/build-c68.sh --vendor <out> --profile m3-lab`。依存関係は `versions.lock.json` と `.gitmodules`、CI手順は `.github/workflows/tab5-build.yml` を参照する。Windowsでの開発環境はWSLまたはLinux CIなどから選び、実際に成功した環境を記録する。フォーク作成時点ではサブモジュールの取得やビルドは実行していない。

## 上流との付き合い方

ローカルの `origin` はこのフォーク、`upstream` はRiti版、`stamp-upstream` はStamp-P4版とする。新規作業ブランチは原則 `codex/` で始める。上流修正はTab5固有の電源、SDIO配線、液晶、キーボード、メモリ予約を維持できるか確認して取り込む。

上流の著作権表示とライセンスを維持し、依存ソフトのライセンス情報も保存する。上流由来の説明を、このフォークの実装済み機能として書き換えない。

## 実機不使用の準備（2026-10-23）

PC上のオブジェクト管理・分割保存復元モデル、MeOS向け同期C転送コア、両者の共通データ照合、GPUメモリ予算計算を追加した。これらは正式なwire ABIやOSドライバではなく、Tab5・FPGA・DDR3へのアクセスは行っていない。物理通信、DMA、割り込み、cache同期、L2〜L4の完了を示さない。

## 小容量キャッシュの試作（2026-10-26）

外部RAMの同一領域を再利用する用途向けに、最大block数を制限したLRU・write-through cacheをホストモデルに追加した。書込み試行前にrevisionを更新し、直接書込み・途中失敗・free/close後の古い内容を返さないことを検証する。時間・実機RAM量・転送性能の実測ではない。詳細と次の作業は [キャッシュ記録](BLOCK_CACHE.md) を参照する。

## 作業終了時の記録

変更目的、対象コミット、ビルド環境、検証機材、実行した確認、結果、残課題、次の一手を残す。実機結果にはコマンドとログを添付し、認証情報は公開しない。機能追加時はREADMEのフォーク固有の説明とこの開発段階を更新する。
