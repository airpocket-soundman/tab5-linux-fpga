# Tab5 Linux

## このフォークの目的

**tab5-linux-fpga** は、Tab5 NOMMU Linuxを基盤にTang Primer 20Kとの通信ドライバとOSビルド環境を開発します。研究計画・FPGA回路・評価アプリは [esp32p4-linux-fpga-memory](https://github.com/airpocket-soundman/esp32p4-linux-fpga-memory) で管理します。

着手前に [開発目的と引き継ぎ](docs/DEVELOPMENT_GOALS.md) を読んでください。2026-10-22、このフォークでST7121液晶表示、1コアLinux起動、USBシリアルシェル、Wi-Fi SoftAP/STA接続、PCからのSSH鍵認証ログイン、16GB FAT32 microSDの認識と書き込みを実機確認しました。使用イメージと残課題は [初回起動記録](docs/BRINGUP_2026-10-22.md) を参照してください。USB-Aキーボード対応は実験段階で、実キーボードによる入力は未検証です。以下の既存説明は上流の動作報告です。直接のフォーク元は [Riti0208/tab5-linux](https://github.com/Riti0208/tab5-linux) です。

Vim・nanoの編集とmicroSD保存、SLの実行も確認済みです。[使い方と機能制限](docs/TERMINAL_APPLICATIONS.md)を参照してください。FPGA向けには[基板なしのmock試験](docs/FPGA_LINK_PREPARATION.md)を追加し、C版はTab5でも513要求を確認しました。物理通信は未検証です。

タッチ入力・128行のコンソール履歴・NOMMU用BLEキーボードホストを実験実装しました。
入力処理の自動テストとビルドは成功し、実機で指の上下スクロールと履歴表示・復帰を確認しました。
BTはコントローラ認識と検索の正常終了まで確認し、ペアリング・キー入力は未検証です。
進捗と制限は[タッチとBluetoothの記録](docs/TOUCH_AND_BLUETOOTH.md)を参照してください。

[English](README.md)

**M5Stack Tab5**（ESP32-P4 + ESP32-C6）で、RISC-V の NOMMU Linux 6.18 をネイティブに動かします。5 インチの画面にコンソールを出して、**Tab5 Keyboard** から操作できます。Wi-Fi、SSH、BusyBox、MicroPython も使えます。エミュレータではなく、P4 の RISC-V コアの上でカーネルが直接動いています。

このリポジトリは、M5Stamp-P4 で同じ Linux を動かす [tsuyoshi-otake/m5stamp-p4-c6-linux](https://github.com/tsuyoshi-otake/m5stamp-p4-c6-linux) の fork です。Tab5 向けのビルドは `EASYSTICK_BOARD=tab5` で切り替えます。Stamp-P4 向けのビルドは元のまま動きます。移植の詳細は [docs/tab5.md](docs/tab5.md)（英語）にあります。

## 動くもの

| | |
| --- | --- |
| 画面 | 720x1280 の ST7123 パネル（MIPI-DSI）。Linux のコンソール（fbcon）を横向き、80x22 文字（Terminus 16x32 フォント）で表示 |
| キーボード | Tab5 Keyboard（A164）を I2C で接続し、Linux の入力デバイスとして使う。Sym・Aa・Ctrl・Alt にも対応 |
| Wi-Fi | ESP32-C6（ESP-Hosted NG、SDIO 接続）。最初は SoftAP。`/boot/config.txt` で家の Wi-Fi につなぐ station モードにもできる |
| シェル | 画面（tty1）と USB-C のシリアルで root シェル。SSH はユーザー `m5` で入れる（Dropbear） |
| ユーザーランド | BusyBox（vi、awk、wget など）、MicroPython（`python3`）、NTP による時刻合わせ |

対応していないもの：

- ST7123 以外のパネル（ILI9881C、ST7121 の版）
- タッチ、音声、カメラ
- USB-A のホストポート
- バッテリーと電源ボタンの扱い
- 2つ目の CPU コア

## Tab5 への書き込み

Tab5 のファームウェアを置き換えます。書き込む前に [docs/tab5.md](docs/tab5.md) を読んでください。コマンドもそこにあります。

1. **工場出荷時のフラッシュをバックアップする**（16 MB、`esptool.py read_flash`）。元のファームウェアに戻せるようにするためです。
2. **C6 を一度だけ書き換える。** Linux のドライバは C6 に ESP-Hosted NG が入っていることを前提にしていますが、Tab5 には ESP-Hosted-MCU が入って出荷されています。C6 には USB ポートがないので、一時的な P4 のプログラムが SDIO 経由で新しいファームを送ります。書き換えた後は、工場出荷のファームに戻しても Wi-Fi が使えません。使うには、C6 に ESP-Hosted-MCU を入れ直す必要があります。
3. **Linux のイメージを書き込む**（16 MB、`0x0` から）。USB-C でつないで書き込みます。

イメージは GitHub Actions の `tab5-build` ワークフローで作れます（成果物 `tab5-assets` に、Linux のイメージ、C6 のファーム、C6 用の OTA ホストが入っています）。リリースはまだありません。

## 使い方

- 画面に root シェルが出ます。Enter で始まります。`=` と `:` は、キーボードの Sym キーと組み合わせて入力します。
- Wi-Fi と SSH の認証情報は、最初の起動時に生成されます。`cat /boot/credentials.txt` で確認できます。最初は SoftAP（`m5-XXXX`、192.168.4.1）で起動するので、`ssh m5@192.168.4.1` で入れます。
- 家の Wi-Fi につなぐには、`vi` で `/boot/config.txt` を開いて `wifi_ssid=`、`wifi_psk=`、`country=` を設定します（行頭の `#` を消してください）。保存すると約 3 秒でフラッシュに保存され、反映されます。C6 は 2.4 GHz 帯のみに対応しています。

## ビルド

`tab5-build` ワークフローが、GitHub のランナー上ですべてをビルドします（1時間ほどかかります）。手元でビルドする場合は、下の元の README にある ESP-IDF と Buildroot の準備をしたうえで、次のコマンドを実行します。

```bash
EASYSTICK_BOARD=tab5 bash linux/build-c68.sh --vendor <out> --profile m3-lab
```

カーネルのドライバを書き換えるときは、`tools/tab5-kernel-build.sh` を使うと、ワークフローの成果物 `tab5-kernel-kit` からカーネルだけを数分でビルドし直せます。DTS だけを変えたときは、DTB のパーティション（`0xf10000`）だけを書き込めば足ります。

## クレジット

- [tsuyoshi-otake/m5stamp-p4-c6-linux](https://github.com/tsuyoshi-otake/m5stamp-p4-c6-linux)：この fork のもとになった Linux ディストリビューション
- [mrbreaker/why2025-linux](https://github.com/mrbreaker/why2025-linux)：ESP32-P4 の NOMMU カーネル移植と、画面に使っている MIPI-DSI の DRM ドライバ
- [Apache NuttX](https://github.com/apache/nuttx) の `esp32p4-tab5` と M5Stack の ESP-BSP：ST7123 の初期化値とタイミング
- M5Stack：Tab5 の回路図と、Tab5 Keyboard の I2C プロトコル

## ライセンス

GPL-2.0-only（[LICENSE](LICENSE)）。boot-shim など、個別の SPDX-License-Identifier があるファイルはそちらに従います。
