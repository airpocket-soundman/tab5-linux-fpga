# FPGA通信の基板なし準備

更新日：2026-10-22。

## 実装と検証の範囲

`tools/fpga-link/` に、低速接続試験v0のPython codec、バイト列transport抽象、mock endpoint、CLI、テストを追加した。対象はPC上のCPythonまたはCPythonが利用できるLinux環境である。追加Pythonパッケージは不要。

Python版はTab5上では実行していない。C版は後述のとおりTab5上でもmockを実行した。Tab5のMicroPythonとの互換性は確認していない。GPIO、シリアル、PARLIO、DMA、IRQ、FPGA、DDR3へアクセスするbackendは実装していない。CLIは`--mock`を必須とし、結果にも`physical_link_tested: false`を表示する。

このv0はID・echo・bit反転による接続試験用である。128MB DDR3のREAD/WRITE/COPY/FILL、Linuxドライバの`/dev/` ABI、可変長パケット、CRC32の仕様は未確定で、本実装では追加していない。

## 照合した資料と出典

| リポジトリ | 確認した版 | 確認内容 |
| --- | --- | --- |
| tab5-tang-primer20k-carrier | `0ff1502e6d2f10f1681480de09087fb3953f39ed` | AGENTS、README、共通ハード仕様。基板・電気条件・ピンは未確定 |
| esp32p4-linux-fpga-memory | `e4aa69d09b2643d6f62fe686ef0f3284b109c541` | README、研究計画、共通ハード仕様。実装・実測は未収録 |
| tab5-fpga-gpu | `147a2154112f9fe4b213567d736f2bece6e9742b` | README、Project B、link-bringup、C codec、Python参照、golden vectors |
| tab5-linux-fpga | 作業開始HEAD `67d34d879fca66e203b285958626f8916cdfc80d` | 開発目的、現在のDTS、Wi-Fi・表示・microSD設定 |

3つの関連リポジトリの共通ハード仕様は同一のSHA-256だった。共通仕様の更新元は引き続きキャリア基板リポジトリとする。

[GPU側の接続試験仕様](https://github.com/airpocket-soundman/tab5-fpga-gpu/blob/147a2154112f9fe4b213567d736f2bece6e9742b/docs/link-bringup.md)と互換にした。上流の`bringup/tab5/main/link_protocol.h`と`bringup/tests/link_vectors.json`を`tools/fpga-link/vendor/`へ無改変で収録した。両ファイルの最終変更コミットは`a6ae7a1b00b32b63c09b6b608f5c9f2f296d2564`。取得元、版、各SHA-256は[SOURCE.json](../tools/fpga-link/SOURCE.json)に記録する。

確認したGPUリポジトリにはルートLICENSEがなく、この2ファイルにもライセンス・SPDX宣言がなかった。関連リポジトリの既存仕様との照合用に原文を保持し、上流ファイルをこちらでGPL等へ付け替えていない。第三者へ再配布する場合の上流利用条件は別途明文化が必要である。新規Python実装とテストは本リポジトリに合わせ`GPL-2.0-only`とし、既存Python参照のソースをコピーせず、記載されたwire仕様と標準CRC関数から実装した。

## 接続試験v0のバイト形式

固定8バイト、CRC対象は先頭6バイト。CRC-16/CCITT-FALSEはpoly=`0x1021`、init=`0xffff`、反転なし、xorout=0。CRCの格納は下位バイトから。既知解はASCII `123456789`に対して`0x29b1`。

| offset | 要求 | 応答 |
| --- | --- | --- |
| 0 | `0xa5` | `0x5a` |
| 1 | opcode | status: 0=成功、1=形式/CRC不正、2=未知opcode |
| 2 | sequence、uint8で周回 | 要求sequence |
| 3 | payload長、常に2 | 常に2 |
| 4–5 | payload 2バイト | 結果2バイト |
| 6–7 | CRC16 LE | CRC16 LE |

opcodeは1=ID（結果ASCII `TP`）、2=echo、3=各バイトbit反転。成功応答はmagic、CRC、sequence、status、length、opcodeに対応する結果を全て照合する。未知opcodeの成功応答も拒否する。

## transportとエラー処理

`Transport.write(data, deadline)`、`read(count, deadline)`、`reset()`を境界とする。deadlineは`time.monotonic()`の絶対値。実装は期限を守って復帰または`TimeoutError`を送出する契約であり、呼び出し先の無期限ブロックを別スレッドで強制中断する仕組みはない。

`LinkClient`は同時に1要求だけを扱い、短いwrite/readを最大8バイトまで組み立てる。受信EOF、不正な転送長、期限超過、CRC/sequence/status/結果不一致は例外となり、transportの部分要求・未消費応答を破棄する。再試行は自動で行わない。sequenceは要求ごとに消費し、255の次は0となる。この同期APIを複数スレッドから同時使用する契約はない。

mockは完全な8バイト要求から応答を生成する。1〜8バイトの断片化、未消費応答中の新要求拒否、エラー後の次要求への復帰を確認できる。DIR/READY/OE、クロック同期、200usの方向切替猶予、実時間のFPGAタイムアウトはモデル化していない。これらはGPU側RTLや基板の検証項目として残る。

## 実行方法

リポジトリルートから実行する。Linuxでは環境に合わせて`python`を`python3`に読み替える。

```text
python tools/fpga-link/fpga_link.py --mock id
python tools/fpga-link/fpga_link.py --mock echo 0x55 0xaa
python tools/fpga-link/fpga_link.py --mock invert 0x00 0xff
python tools/fpga-link/fpga_link.py --mock --fragment-size 1 selftest
python -m unittest discover -s tools/fpga-link -p test_fpga_link.py -v
```

Cの既存codecも検証する場合、ホストCコンパイラを明示する。コンパイル先はOSの一時ディレクトリで、終了時に削除する。コンパイラの導入や実機操作は行わない。

```text
python tools/fpga-link/run_c_codec.py --cc cc
```

2026-10-22のWindows確認では既存のZigを使用した。

```text
python tools/fpga-link/run_c_codec.py --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig
```

## 2026-10-22の確認結果

Windows PowerShell、Python 3.12、既存ホストZigで確認した。Tab5への書き込み、GPIO/COM操作は行っていない。

| 確認 | 結果 |
| --- | --- |
| Python unittest | 14テスト成功 |
| 共通golden vectors | 要求/応答と受理判定583件一致 |
| CLI selftest、fragment-size=1 | 上記583件とID＋全256値echo/反転の513要求が成功 |
| 無改変C codec | `-std=c11 -Wall -Wextra -Werror`でホストコンパイル成功、583件の受理判定と妥当な要求の再生成が一致 |
| CRC | 既知解と別のbit単位実装に一致 |
| 故障注入 | 全64bitの応答破損、CRC再計算済み応答フィールド不正、timeout、EOF、過大応答を拒否 |
| 状態/境界 | 1〜8バイト断片、sequence周回、未知opcode、uint8範囲外、未消費応答、失敗後の復帰を確認 |
| 出典ファイル | SOURCE.jsonのSHA-256と一致 |

これらはPC上のバイト列と制御処理の結果である。物理通信、RTL、DDR3アクセス、PARLIO DMA、転送帯域を検証した結果ではない。

## CPythonを必要としないC mock CLI

`tools/fpga-link/fpga_link.c`を追加した。既存の無改変`vendor/link_protocol.h`を使って要求生成と応答検査を行い、模擬FPGA応答生成はCで独立実装している。アプリケーションコードは8バイトの要求/応答と32バイト以下の行バッファを使い、可変長配列、再帰、malloc/calloc/reallocを使用しない。Cライブラリやプロセス起動時の内部メモリ使用までゼロとする主張ではない。

C側のtransport境界は完全な8バイトフレームを受け渡す`exchange()`関数ポインタ。mockは同期的に必ず復帰し、実デバイスの待ちやタイムアウトを扱わない。Python側の断片化・deadline APIと同じ実装だとは扱わない。実通信backendを追加する際には、部分送受信・期限・破棄・再試行方針を改めて実装する必要がある。

`--mock`が必須で、id/echo/invert/selftestの結果はJSONで表示する。`selftest`はIDと全256値echo/反転の513要求を実行し、8bit sequenceの周回も通る。`--vectors`はホストテスト用の標準入力インターフェースで、要求hexを1行ずつ入力し、不正CRC/形式を含む要求へのmock応答とC hostの受理判定を出力する。

```text
cc -std=c11 -O2 -Wall -Wextra -Werror tools/fpga-link/fpga_link.c -o fpga-link
./fpga-link --mock id
./fpga-link --mock echo 0x55 170
./fpga-link --mock invert 0 0xff
./fpga-link --mock selftest
python tools/fpga-link/run_c_cli.py --cc cc
```

2026-10-22、既存WindowsホストZigで次を実行した。

```text
python tools/fpga-link/run_c_cli.py --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig
```

`-std=c11 -O2 -Wall -Wextra -Werror`のコンパイルが成功し、C CLIの全583ベクタの応答と受理判定が、golden vectorsと独立Python実装の両方に一致した。CLIのid/echo/invertの3例、513要求selftest、不正引数・範囲外・不正hex・過大入力の14例の拒否も成功した。SOURCE.json、vendor header、golden vectorsはこの追加で変更していない。

C CLIはRV32IMAC/ILP32/uClibc static bFLTへクロスビルドし、Tab5上の`fpga-link --mock selftest`でも513要求の成功を確認した（CI39761292328/source0493c7a、83,548bytes、stack32KiB）。`physical_link_tested:false`のままであり、物理通信・DDR3は未検証。メモリ使用量の詳細測定も未実施。C CLIもGPIO/COM/FPGA/DDR3へ一切アクセスしない。

## GPIOと次の作業

共通仕様の暫定案はD0–D7=`18,19,5,3,4,2,48,47`、CLK16、READY45、DIR51。現行Wi-Fi8〜13、microSD39〜44、液晶backlight22、タッチ23、I2C31/32、外付けキーボード0/1との単純な番号重複は見つからなかった。

ただしBSPヘッダの`BSP_USB_NEG=GPIO19`と暫定D1=19には記述上の疑義がある。現在のUSB20はUTMI専用経路であり、ヘッダ定義だけで実電気的競合の有無を確定できない。キャリア・Tab5回路図のネット照合、GPIO行列、起動状態、I/O電圧、電源断時Hi-Zと逆給電を引き続き確認する。GPIOを動かす実装はこの確認後の別段階とする。

次の作業は、上流ファイルの利用条件明文化、FPGA側RTLを同じベクタでシミュレーション、キャリアのネットと電気仕様確認、実基板用top/制約作成、その後の低速ID/パターン往復試験。C実行形式のクロスビルドとTab5でのmock実行は完了したため、次は実機メモリ負荷の測定と、実基板の到着後に接続backendの検証を行う。

DDR3用APIを進める場合は別の提案書でaddress、transfer length、payload length、要求ID、エラー応答、重複要求、CRC、最大分割サイズを定義する。128MBをP4側に一括確保せず、少量バッファで分割し、`length <= capacity - address`による範囲検査とmock backendから検証する。現v0に正式メモリ操作opcodeを割り当てたものとして扱わない。
