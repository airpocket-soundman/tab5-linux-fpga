# Tab5 タッチ操作とBluetoothキーボード

2026-10-23時点の開発記録。実装・ビルド・実機確認を区別する。

## コンソール位置の調査

ユーザーから、vi終了時に限らず通常画面でもクリア後のプロンプトが
最下段になるとの報告。実機のVT情報は80列22行、カーソルは初期状態で
(0,21)だった。`clear`の実体であるBusyBoxの出力はESC [ HとESC [ Jで、
先頭移動を含んでいた。tty1へ直接clearした後は(0,0)、LCDシェルへの
WINCHでプロンプトを再描画すると(4,0)となった。これによりVT上での
最上段復帰は確認したが、報告された操作経路で下端に戻る原因は未確定。
物理画面もユーザーが確認表示・プロンプトとも最上段に見えると確認した。
シリアルとLCDは別TTYであり、
一方へのclearが他方へ反映されるわけではない。

## タッチと履歴

- 0081はST7121/ST7123タッチの単指入力を40ms周期で取得するLinuxドライバ。
  内部GPIO31/32のI2Cと0x55を使用し、0x43エキスパンダのP5だけを解除する。
  LCDのP4など他の出力を保持する。boot shimは変更しない。
- 0082はtty1限定の128行の履歴。静的RAM40KiB、最大160列。
  実際の入力バッファを差し替えず、履歴のglyphと属性を表示する。
  新しい出力で通常画面へ戻り、CSI 3 Jで履歴を消す。
  代替画面の捕捉を除外し、リサイズ・フォント変更などで履歴を破棄する。
- `tab5-touch-scroll`はevdevのフレームからスワイプを検出し、標準の
  TIOCLINUXによる行スクロールを要求する。別VTでは操作しない。
  S98サービスが起動する。方向の初期値は画面回転1に合わせたraw X正方向。
  実際の指操作で軸・向きを確認する必要がある。
- 共通ビルドは`EASYSTICK_BOARD=tab5 TAB5_TOUCH=1`で有効化。
  詳細は[実装説明](../tools/tab5-console/README.md)。

初版faf4126のカーネル・DTはCI39868276918でコンパイル成功。
レビューで代替画面と履歴破棄を補強した06b20f1のカーネル・DTも
CI39870672763で成功し、入力ツールCI39869439768のrootfsと実機へ書き込んだ。
書き込み前にSDをunmount済みと確認し、kernel/rootfs/DTBだけを更新。
boot shimと保存済みWi-Fi設定領域は保持した。

| 実機へ書いたファイル | bytes | SHA-256 |
| --- | ---: | --- |
| Image | 6,919,612 | `542a85c1715a14b069d68aa24e94a5a8eca0b692a49134f68c98e046c330481e` |
| DTB | 6,940 | `a963bf80c9ec40866c2aa8e226d1e0ef45c15d42152f49fc98e9c3aebd5146ff` |
| rootfs | 5,525,504 | `afb142689eeb0ca5ba0e9054d14663dedf3177af2df9d6ad1ccba1d9bf6c0424` |

実機は1コアで起動。タッチFW1・10 contacts・720×1280を認識し、
`Tab5 ST712x Touchscreen`がevent0へ登録、スクロールdaemonも起動した。
Wi-Fiは同じIPへ接続しPCからping成功、SDはFAT32/RWでmount。
SSH経由のVim・nanoの編集/SD保存/正常終了、SLの21,591 bytesの画面更新と
正常終了、シェル復帰を再確認した。テスト側の古い`[New File]`起動文字列条件は
Vimの実際の`[New]`表示に合わせて判定を訂正し、E1187等の起動エラーはなかった。

実機tty1へ200行を出力し、helperで128行さかのぼってfb0のhash変化を確認。
同時にvcs1のhashは不変、通常画面へ戻すとfb0/vcs1とも元のhashへ一致した。
これは履歴がlive文字データを上書きしないことの確認で、指操作の確認とは別。
実際の上下スワイプもユーザーが「上下スクロールできる」と確認した。
ログはローカルoutのinput-boot-safe.log/input-console-smoke.json/
input-terminal-results.json。古いカーネルでは履歴機能がないため、新しいhelper
だけを入れても履歴は増えない。

入力ツールCI39869279304と39869439768は成功。MGMT status/complete、
HID/GATT探索、長いreport map、番号付き・番号なしUHID入力、不正通知を
通信fixtureで確認した。タッチ処理は実daemonにsyscall mockを接続し、
同じ座標の再タップ、SYN_DROPPED、EINTR、初期座標取得失敗後の再試行、
極端な座標差の要求上限を確認した。BLE helperは101,216 bytes、stack64KiB。
再構成rootfsは約5.27MiBで7MiB上限内。これらは実機入力の代わりにはならない。

## Bluetooth方針

候補名はユーザー申告の`K68 BT5.0`。名称だけではBLE HIDか確定しない。
現行実機カーネルはBT無効。既存C6はBLE/SDIO対応のcapabilityを通知して
いるが、フォークでHCI・ペアリング・キー入力を確認したことはない。
C6はBLEのみのため、Classic専用キーボードには対応できない。

通常のBlueZ一式はこのNOMMU/static構成にそのまま追加できないため、
`TAB5_BLE=1`の明示設定でカーネルHCI・UHIDとESP-HostedのBT経路を有効化し、
最小のユーザーランドを別途開発する。標準のWi-Fiのみのビルドは維持する。
新しいカーネルに合わせたESP-Hostedモジュールが必要で、既存のkoを使って
BT対応済みとは扱わない。ペアリングモードはテスト準備ができてから依頼する。

05326d0のBT有効カーネルとESP-HostedはCI39871455474でビルド成功。
同じkoをrootfsへ組み込んだCI39872139940も成功。カーネルは7,284,380 bytesで
0x780000の上限内、koは166,432 bytes。0037でBT送信エラー時のskb二重解放と
送受信の所有権移譲後参照を修正し、Wi-Fi処理は変更していない。
高速ビルドではbuild-m1のquiet既定と同じく0023/0029/0030/0031を除外した。
とくに0030/0031は未renderedアドレスを使う実験テンプレートで、通常版へ
無条件に適用してはいけない。Ubuntuのコンパイラ配布が低速だったため、
同じパッケージを主archive mirrorから取得するよう変更した。

このBT版を実機へ書き込み、hci0登録・タッチ再認識・Wi-Fi/SD維持を確認。
rootfsは5,541,888 bytes、SHA-256は
`213f09cce91225c796300abb030453dbb4388366c9bc4bcb945006f9990a671b`。
カーネルSHA-256は`01b56ce4fddc00e23491d868df164cffc48ac4e627ac76398b27eff1a1117f6b`。
スキャン開始はできたが、`Unable to create CMAC crypto context`が発生し、
ペアリングは未実施。実際に不足していたのはCMAC自体ではなく、
BT Kconfigがimplyするだけの`CONFIG_CRYPTO_AES`が既存のn設定で無効だったこと。
93ba540でAESを明示有効化した。スキャンの自然停止後にStop Discoveryが
Rejectedになる正常な競合も修正し、回帰fixtureを追加。再ビルド・再検証中。

AES修正版93ba540はカーネルCI39872872633で成功、対応moduleを含む
rootfsのCI39873299488も成功。SDのunmountを確認して実機へ反映した。

| 現在のAES有効版 | bytes | SHA-256 |
| --- | ---: | --- |
| Image | 7,309,392 | `2ef26d1167bdc8ffdb5d04c58d9075824bce16d1f37829c9be368dc1e284745c` |
| rootfs | 5,541,888 | `0bd5691890be3ae582307f5639568b4220fc5ae42fd405f783fcb2b8c357c44a` |

DTBは上のタッチ版と同じ。再起動後もhci0・touch event0・SDを認識。
`tab5-ble-hid scan K68`はexit0で終了し、CMAC crypto contextエラーは消えた。
K68はまだペアリングモードにしてもらっていないため検索では未発見。
Bluetoothの初期化と検索の確認であり、キーボード接続・入力の確認ではない。
ユーザーへペアリングモードを依頼し、実機キー入力のテストを待っている。

## 次の確認

次はK68の発見・ペアリング・実際のキー入力を確認する。入力確認と同時に
Wi-Fi/SSH・SD・表示の併用を再確認する。通常clearの報告経路は未再現だが、
直接clearと実プロンプトの最上段復帰は実機で確認済み。
初版にはペア情報の永続化・自動再接続・自動起動がなく、これらは次段階。
