# Linux向け外部RAM利用準備：Cファイルmock

更新日：2026-10-23。

## 目的と制約

`tools/fpga-memory/file_probe.c`は、C11標準ライブラリだけで小さなバッファによる保存と検証を反復する参照プログラムである。Linux向けユーザーランドの準備として、PCで範囲・分割・内容照合・エラー検出を検証する。`--mock`が必須で、`tmpfile()`で作成する一時ファイルだけを利用する。ファイル名、デバイス名、ネットワークアドレスの入力は受け付けない。

FPGA通信・DDR3・GPIO・PARLIO・DMA・IRQ・Linuxドライバの実装ではなく、wire ABIを定めない。通常RAMやswapの増設を実現するものでもない。Tab5上での実行は未検証。ターゲット用にコンパイルできても、ターゲットで起動・動作確認したという意味ではない。

一時ファイル容量は`--size`と同じで、最大128MiB。必要な空き容量は実行環境の一時ファイル用ファイルシステムに依存する。Tab5の`/tmp`等に容量相当の空きがあるとは仮定しない。RAM上のファイルシステムで実行すればそのRAMを消費するため、外部DDR3の効果を測る試験にはならない。ホストのファイルI/O時間からFPGA性能を推定しない。

## CLIと動作

```text
cc -std=c11 -O2 -Wall -Wextra -Werror tools/fpga-memory/file_probe.c -o file-probe
./file-probe --mock --size 65539 --chunk 31
./file-probe --mock --size 65539 --chunk 31 --inject-corruption 65538
```

| 引数 | 範囲・動作 |
| --- | --- |
| --mock | 必須。一時ファイルbackendのみ |
| --size | 1〜134217728バイト。既定1048593 |
| --chunk | 1〜65536バイト。既定4096 |
| --inject-corruption | 0〜size-1のバイト位置。1回目の書き込み完了後、その位置のbit7を反転 |

65536バイトの固定staticバッファを使用し、可変長配列・動的確保・再帰を使わない。小さなstack設定でもこのバッファをstackへ置かない。標準ライブラリ内部やプロセス起動時のメモリ使用量は別であり、全RAM使用量を65536バイト以下とする主張ではない。

1. CRC-32の既知ベクタ`123456789 → cbf43926`を確認する。
2. 1回目のaddress依存パターンを分割して書き込む。
3. 同じ領域を分割して読み出し、全バイトを期待パターンと比較する。生成時と読み出し時のCRCも比較する。
4. 異なるseedのパターンで全領域を書き直し、もう一度全バイトとCRCを確認する。
5. ファイルのclose成功を確認してから、成功JSONを1行だけ出力する。

二回のpassは同じファイル領域を上書きして検証する。別オブジェクトへのcopyや二重保持ではない。read/writeごとにseekを行い、標準Cの更新ストリームの入出力切り替え条件を守る。ファイル位置は上限128MiBなので32bit signed longの範囲に収まる。

## パターンとCRC

アドレス`i`に対して以下の32bit unsigned演算を行い、最下位8bitを保存する。全アドレスは128MiB未満で、32bitに収まる。乗算の32bit周回は意図したもの。単純な251バイト周期のパターンと異なり、アドレスの上位bitも混合する。ただし、全てのアドレス誤配線や故障を検出できる保証はなく、実DDR3の電気試験の代用にはならない。

```text
x = i XOR seed
x = x XOR (x >> 16)
x = x * 0x7feb352d  (mod 2^32)
x = x XOR (x >> 15)
x = x * 0x846ca68b  (mod 2^32)
x = x XOR (x >> 16)
byte = x AND 255
```

seedはpass1で`0x9e3779b9`、pass2で`0x85ebca6b`。CRC-32は反転poly `0xedb88320`、init `0xffffffff`、最終xor `0xffffffff`。分割ごとに内部状態を引き継ぐ。JSONには最終値を8桁小文字hexで記録する。これはホスト照合用のCRCであり、通信プロトコルのCRCではない。

## 成功・失敗の観測

成功時のJSONには、`mock:true`、`physical_link_tested:false`、`bytes_per_pass`、二回分の合計`bytes_verified`、`verified_passes:2`、`chunk`、`working_buffer_bytes:65536`、`crc32_pass1`、`crc32_pass2`、read/writeの確認成功回数を含める。

終了codeは成功0、検証またはファイルI/O失敗1、引数不正2。失敗時はstderrへ理由を出し、成功JSONは出力しない。自動再試行・原子性・回復機能は提供しない。短いread/write、seek失敗、close失敗を検査する。途中失敗すれば一時ファイルの内容が部分変更済みの場合がある。

## 自動照合と容量を増やした確認

独立したPythonパターン・CRC実装と比較するrunnerは以下で実行する。

```text
python tools/fpga-memory/run_file_probe.py --cc cc
python tools/fpga-memory/run_file_probe.py --cc cc --sanitize
python tools/fpga-memory/run_file_probe.py --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig
python tools/fpga-memory/run_file_probe.py --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig --sanitize
```

Windowsホストの既存Zigで通常実行と`--sanitize`要求付き実行の両方が成功した。それぞれ6種類のサイズ×3種類のchunkの18ケースで独立CRCと一致し、不正引数13例を終了code2で、破損注入3例を終了code1で拒否した。`--sanitize`はAddressSanitizer・UndefinedBehaviorSanitizerのコンパイラオプションを要求し、コンパイル失敗時に自動で外して再試行しない。この結果はターゲット用のinstrumentationやTab5実行を確認したものではない。

64MiB・chunk65536の実行では、同じファイルを2passで合計134217728バイト検証した。read/write各2048回、CRCはpass1=`433b8578`、pass2=`645740d1`。実行時間・プロセスRAM最大値は測定していない。

## 確認記録と次の作業

Windowsホストの既存Zigで`-std=c11 -O2 -Wall -Wextra -Werror`コンパイル成功。size65539・chunk31の2passで131078バイトを検証し、read/write各4230回、CRCはpass1=`0c3b5aab`、pass2=`afbf1a5e`。同条件で末尾65538を破損させると、pass1・byte65538の不一致として終了code1、stdout空で失敗した。

今後はLinuxホストで同じベクタを照合し、必要に応じて対象SDKでコンパイルする。実機が使える段階で、ファイルmockの小容量実行と実際の外部RAM backendを別々に確認する。実通信に進む前にaddress幅・最大長・要求ID・timeout・部分進捗・reset時の扱いを別仕様で定義する。L2〜L4の実機完了条件はこのmockでは達成しない。

## Tab5向けNOMMUビルド結果

2026-10-23、[offline-memory実行39959725472](https://github.com/airpocket-soundman/tab5-linux-fpga/actions/runs/39959725472) がGCC・ClangのASan/UBSan検査とNOMMUビルドに成功した。ソースは `faaca39`、SDKは既存の `tab5-terminal-sdk`（実行39765710691）をSHA-256照合後に使用した。

artifact `tab5-memory-file-probe` に実行ファイル、build-info、SHA256SUMSを保存。実行ファイルのSHA-256は `132cce3f8d4bda673cf60649d09d2d26f7870d42f685c99e31605dc9b4e76d15`。取得後の再照合も成功した。

`check_flat.py` による静的確認：bFLT revision4、entry68、初期化領域89,352 bytes、BSS82,872 bytes、要求stack32,768 bytes、relocation46件。ヘッダ上の範囲・再配置表・非圧縮形式を検査したもので、ロード成功や実機の最大RAM消費を証明しない。

Tab5向けバイナリを生成したが、Tab5へ転送・実行・書込みはしていない。実機再開後は小さいサイズからtmpfile保存先・空き容量・終了時の解放を確認する。これはファイルbackendの診断であり、DDR3接続やPARLIO backendを実装したものではない。
