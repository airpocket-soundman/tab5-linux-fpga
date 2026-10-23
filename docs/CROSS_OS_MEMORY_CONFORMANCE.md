# Linux・MeOS外部RAMモデルの共通データ照合

更新日：2026-10-23。

Linux側PythonとMeOS側ポータブルCの独立したホスト実装に、同じ入力を与えて退避・復元結果を照合する。OS上の動作・通信ABI・DDR3・DMA・性能の互換性を証明する試験ではない。

## 実行

MeOSフォークのローカルコピーと、既存のホストCコンパイラを明示する。追加Pythonパッケージは不要。リポジトリを自動取得せず、依存ファイルやコンパイラがない場合は終了する。

```text
python tools/fpga-memory/compare_meos.py --meos-root D:/github/airpocket-soundman/tab5-meos-fpga --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig
```

通常のホストCコンパイラでは `--cc cc` とし `--zig` を省く。MeOS側の `experiments/fpga-memory/fpga_memory.c` と `demo_memory.c` をC11・警告をエラー扱いで一度だけコンパイルする。実行形式は一時ディレクトリに作成し、終了時に削除する。Tab5のビルド・書き込みやシリアル操作は行わない。

## 試験契約

入力サイズ `1, 31, 32, 33, 4097, 65539` bytesと単一転送上限 `31, 4096` bytesの全12組を実行する。境界の前後と端数を含み、最大入力でも約64KiBであり、大容量データを一括生成しない。両demoには次の引数を渡す。

```text
--mock --size SIZE --transfer-limit LIMIT
```

データは全体offsetを `i` として `i % 251`。sourceに分割保存し、targetへ復元した内容のCRC32を計算する。runnerは両実装を呼ばずにPython標準 `zlib.crc32` で997byte単位の期待値を作る。実装間の値が同じだけでは合格にせず、独立した期待値にも一致することを要求する。

JSONの必須フィールドは次のとおり。

| フィールド | 受理条件 |
| --- | --- |
| `bytes_verified` | 入力サイズと等しい整数。boolは拒否 |
| `transfer_limit` | 入力上限と等しい整数。boolは拒否 |
| `readback_crc32` | 小文字16進8桁の文字列、独立期待CRCと一致 |
| `physical_link_tested` | JSONのfalse。0や省略は拒否 |

CRC32はランダムな破損検出用であり暗号学的完全性の保証ではない。個々の実装の境界・handle寿命・故障注入試験を代替しない。同期CモデルとPythonファイルモデルは割当方式、保存先、実行環境が異なる。成功は上記入力に対するデータ意味の一致を示す。

runnerの最終JSONは `cases_passed: 12` と各期待CRCを出力し、`physical_link_tested`、`linux_runtime_tested`、`meos_runtime_tested`、`performance_measured` を全てfalseとする。プロセス失敗、JSON形式違反、CRC不一致は終了コード1、依存ファイル不足・コンパイラ不在は引数エラーで終了する。

## 2026-10-23の確認結果

Windows、Python 3.12、既存Zigで上記コマンドを実行し、12組全て成功した。Cを一度コンパイルし、両実装をそれぞれ12回実行した。確認した実装は同日作業ツリーの新規コードであり、MeOSの開始HEADは `7562806eb9a538d5f2c8f13efcac379b47919d84`、Linuxは `f37b830d878b8e52b4e06f983f38ef1c828f5061`。

| サイズbytes | 独立期待CRC32（両転送上限で一致） |
| --- | --- |
| 1 | `d202ef8d` |
| 31 | `4d786d77` |
| 32 | `91267e8a` |
| 33 | `e4908305` |
| 4097 | `27d94e23` |
| 65539 | `d589ee6e` |

存在しないMeOSルートを指定したときの依存不足エラーも確認した。JSON検査単体では正常値の受理、および `physical_link_tested:0`、整数欄のbool、誤ったCRCの拒否を確認した。実機・性能の確認は行っていない。

## 次の接続先

正式メモリwire仕様ができたら、同じ入力データをC/Python codecとRTL simulationへ適用する。パケット識別、timeout、reset、部分更新、再送、buffer generationの契約を別途検証する。ホスト試験の完了をL2〜L4、MeOS実機GUI、DDR3全域照合の完了として扱わない。
