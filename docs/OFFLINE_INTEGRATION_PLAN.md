# 実機なしで進める外部RAM・GPU統合準備

更新日：2026-10-23。主目標はLinux側で扱えるデータ量を、小容量の転送バッファとFPGA側DDR3によって増やすこと。GPUは別用途として検討する。この文書は統合方針と受入条件であり、メモリ通信の正式ABIを制定しない。

## 確認した出典

| 対象 | 確認版と資料 |
| --- | --- |
| Linux | 作業開始HEAD `f37b830d878b8e52b4e06f983f38ef1c828f5061`。`docs/DEVELOPMENT_GOALS.md`、`docs/FPGA_LINK_PREPARATION.md`、`tools/fpga-link/` |
| キャリア | `0ff1502e6d2f10f1681480de09087fb3953f39ed`。`docs/ESP32P4_FPGA_共通ハード仕様.md` |
| 外部メモリ研究 | `e4aa69d09b2643d6f62fe686ef0f3284b109c541`。共通ハード仕様、`docs/Project_A_P4_Linux_FPGA_Virtual_MMU.md` |
| GPU | `147a2154112f9fe4b213567d736f2bece6e9742b`。共通ハード仕様、`docs/link-bringup.md`、`docs/game-gpu-spec.md` |
| MeOS | `7562806eb9a538d5f2c8f13efcac379b47919d84`。`docs/DEVELOPMENT_GOALS.md`。GUI化が主目的、RAM活用は共通基盤を利用する研究対象 |

3リポジトリの共通ハード仕様のSHA-256は同一：`d40beeab2c50e7c188905835af0cd32350939d6a4e6cb164efce130d332e7956`。更新元はキャリア側とする。今回追加のmockは作業ツリー上の新規実装であり、上記コミットに含まれない。

## 互換性と実装境界

| 層 | 現在の契約 | 統合時の扱い |
| --- | --- | --- |
| 接続試験v0 | 固定8バイト、ID/echo/invert、CRC16、8bit sequence | 既存golden vectorsとC/Python互換を維持。メモリ操作のopcodeやアドレスを追加しない |
| Python link transport | 部分送受信、絶対deadline、失敗時reset、1要求ずつ | 物理backendの前段契約。resetは現在mockの状態破棄であり、FPGAリセットの保証ではない |
| C link transport | 完全8バイトの同期exchange | Pythonのdeadline/断片化と同一ではない。実backendで部分送受信・期限を別途実装する |
| 外部RAM mock | ホスト一時ファイル、opaque handle、オブジェクト内offset、分割read/write/copy | OS非依存の意味検証。v0との接続なし。ハンドルはPythonオブジェクトの同一性に依存し、wire上の整数IDではない |
| GPU G0案 | RGB565 LE、uint16 depth、buffer handle/generation、fence後に所有権返却 | memory mockの同期copy成功からGPU対応を推定しない。stride・format・alignment・重複禁止をGPU側で検査 |
| OSアダプタ | Linux `/dev/` ABI、MeOSのタスク待機は未確定 | 上位のデータ照合条件を共有し、ドライバ・スケジューラ・DMA管理はOS別にする |

既存vendorの出典・ハッシュ・利用条件は `tools/fpga-link/SOURCE.json` を維持する。GPU由来2ファイルは確認版でLICENSE/SPDX宣言がなく、本フォークによる再ライセンスを主張しない。

## 外部RAMの意味契約を先に検証する

アプリは生DDRアドレスやCPUポインタを保持せず、領域とoffsetでアクセスする。128MBという製品表記と、mockの `128 * 1024 * 1024` bytes設定を区別し、実装時には利用可能容量・予約領域・転送上限を照会する。全容量をP4に一括確保しない。

mockはfirst-fitの連続領域割当を行い、新規領域をゼロ初期化する。free/close後・別instance・偽造handleを拒否し、範囲は `length <= capacity - offset` 相当で検査する。copyは同一領域の重複にmemmove相当で対応する。これらはmockの意味であり、FPGA上のCOPY実装やゼロ化性能の実証ではない。

分割処理の途中失敗では、先行分割の更新が残り得る。全操作のatomicity、並列呼出し、自動再試行は保証しない。実機向けには完了済みbyte数、復旧後のオブジェクト無効化、要求の重複検出、reset後の世代管理を仕様化する必要がある。特にWRITE/COPY後の応答欠落で、未実行か完了済みかを判別せず再送してはならない。

次のABI提案でaddress/lengthのbit幅とendianness、最大payload、要求ID、CRC対象、エラー、期限、重複要求、能力照会、リセット、COPY重複条件を決める。その後に独立したcodecと共通vectorsを作る。現mockのメソッドや4096byte設定をそのまま正式ABIにしない。

## GPUとDDR3を共用する前の条件

初期はRAM用とGPU用を別ビットストリームとする。GPU仕様の640×360 RGB565はcolor/depth各460,800 bytes、double color + depthで1,382,400 bytes。全画像の毎フレーム回収は30fpsで13,824,000 bytes/sのpayloadを要し、命令・待機・LCD転送は別に加算される。8bit×40MHzの40MB/sは理論上限であり、実効帯域ではない。

共用は領域予約、buffer generation、描画中のCPU書込み禁止、fence、DDR仲裁、resetによる無効化を定義してから扱う。GPUのstride末尾計算、color/depth重複拒否、RGB565 LE、depthの大小比較はGPUの数値契約を正とする。汎用メモリCOPYの重複許可を描画バッファの重複許可へ拡張しない。MeOS GUIの矩形コピー・フォント・画像資源は、この所有権境界を守る別の利用者として設計する。

## ホストだけでの受入条件と確認結果

2026-10-23、Windows上のPythonで以下を実行した。GPIO、COM、Tab5、FPGA、フラッシュにはアクセスしていない。

```text
python -m unittest discover -s tools/fpga-link -p test_fpga_link.py
python -m unittest discover -s tools/fpga-memory -p test_memory_mock.py
python tools/fpga-memory/memory_mock.py --mock
```

既存link 14テスト、新規memory 12テストが成功。退避・復元demoは1,048,593 bytesを分割照合し、設定4096 bytesに対し最大単一転送4096 bytes、SHA-256は `f4bf9b8dec6e3e28b2ec33266145d244fe97a6bce1ec054ace053bab67d2ef9a`。ホストの一時ファイルとPython実行環境のメモリ量はTab5使用量を表さず、転送回数・時間もPARLIO性能ではない。

受入の中心は、端数分割の照合、範囲外の変更拒否、解放後handle拒否、割当失敗と結合、重複copy、少量バッファでの処理を再現できること。正式wire仕様ができたらCRC破損、短い送受信、期限超過、応答欠落、reset後の古い要求を同じ入力でC/Python/RTLへ適用する。mock成功でL2〜L4やDDR3検証を完了扱いしない。

## 実機再開時のゲート

| 順序 | 必要な確認 | 通過条件 |
| --- | --- | --- |
| 1 | キャリア・Tab5回路図・Core資料 | I/O電圧、電源、逆給電、Hi-Z、暫定GPIOとUSB関連定義の疑義を解消。ピン確定前にGPIO backendを有効化しない |
| 2 | 接続試験RTL・top・制約 | 共通vectorsでシミュレーション。DIR/OE/READY、200us方向切替猶予、通信停止時の出力解除を確認 |
| 3 | 低速v0往復 | ID・パターン照合、CRC・timeout後復帰。OS・bitstream・配線版・ログを保存 |
| 4 | DDR3とメモリAPI | 初期化・予約領域確認後、利用可能全域を小容量分割で書込/読出照合。境界・連続アクセス・reset・故障を確認 |
| 5 | Linux/MeOS backend | バッファ寿命、期限、IRQ、DMAとcache同期を検証。Linuxは既存1コア構成を基準にする |
| 6 | 用途比較 | 退避復元・分割処理を先に評価。GPUは描画だけでなく回収と表示込みでCPU版と比較 |

成果物は意味モデル、ホスト試験、互換性境界と本計画。未解決は正式メモリwire仕様、物理backend、DDR3接続、電気仕様、実効性能。次はこのモデルの入力・期待出力を共有し、研究側のRTL/API提案に接続する。
