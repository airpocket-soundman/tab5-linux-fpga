# Tab5 MeOS → Linux 機能移植一覧

調査日：2026-10-27。参照したMeOS checkoutは`cfad4ad88092f84f99084bd4f12f7c60e6d2eb92`
（調査時working tree clean）。Linuxの開始コミットは`0208849`、今回の変更は作業ツリー上。
READMEの予定欄だけで判断せず、各機能の実装資料とソースを照合した。
MeOSの限定的な実機実績はLinuxの実績ではない。

## 対照表

| 機能 | MeOSの範囲・参照資料 | Linuxの現状と不足 |
| --- | --- | --- |
| USBホスト・ハブ | 独自DWC2 DMA、複数機器。`USB_IMPLEMENTATION.md`、`USB_HUB_IMPLEMENTATION.md` | Tab5のHSホスト/PHY/電源/IRQ/DMA統合が未実装。共通の優先課題 |
| USBメモリ、FAT/exFAT | 複数媒体の読書き・再起動後保持を限定確認 | Storage/SCSI/FAT/exFATクラスを任意追加。ホスト待ち。マウント・永続化未検証 |
| USBキーボード／マウス | ハブ配下キー入力を限定確認。マウスは計画と実績を個別確認する必要あり | USB HID/evdev設定を任意追加。USB入力はホスト待ち。Tab5 KeyboardのI2Cドライバは既存 |
| USB Ethernet | RTL8153のCDC-ECMでDHCP/ping/SSHを限定確認。`USB_ETHERNET_IMPLEMENTATION.md` | CDC-ECM/NCMとRTL8152/8153設定を任意追加。ネットワーク標準ツールは既存、ホスト待ち |
| USBカメラ | YUY2 160×120を1フレームBMP保存。連続映像未成立。`USB_CAMERA_IMPLEMENTATION.md` | UVC設定、V4L2情報表示・単一YUYV→BMP取得ツールを今回追加。ホスト待ち |
| 内蔵カメラ | SC202CS/CSI/ISP/RGB565取得の限定結果 | Linuxのセンサ・CSI・ISP・DMA経路は未実装 |
| BMP表示 | 16/24bit BMP、拡大/終了。`IMAGE_VIEWER.md` | 今回16/24bit解析・情報表示とfbdev描画を追加。拡大/回転/元画面復元は未実装 |
| microSD | SPI経由FAT/exFATの読書き・保持。`MICROSD_IMPLEMENTATION.md` | 既存MMCはC6 SDIO用。Tab5 SDソケットの別接続とドライバ/DTが必要 |
| Wi-Fi | MCU版C6との初期化・接続・DHCP/DNS/HTTP | LinuxのESP-Hosted-NG/設定スクリプトは既存。MeOSとC6ファームの方式が異なり、無条件に共用しない |
| SSHサーバ／クライアント | 並行起動の限定結果。`SSH_SERVER_IMPLEMENTATION.md` | Dropbearとlabクライアントは既存。フォーク実機の外部接続確認は別途必要 |
| SFTP・PCからのストレージ操作 | SFTP v3と標準ライブラリのPC helper。`STORAGE_HELPER.md` | DropbearだけでSFTPサーバが付くわけではない。NOMMUで動くsubsystemが未選定・未実装 |
| ANSI/DEC端末・エディタ | 独自端末の部分実装。`TERMINAL_IMPLEMENTATION.md` | Linux VT、serial/SSH ttyとBusyBox viは既存。xtermとの完全互換性は主張しない |
| SL/TUIアプリ | ネイティブSLの限定確認。`user/sl/README.md` | vi等は既存。SL等の追加アプリは未移植、NOMMU/サイズ予算を確認して選定 |
| タッチ | ST7123/ST7121の追加後に再検証中 | 入力ドライバ・DTは未実装。液晶のLinux実表示も別の確認項目 |
| Bluetooth入力 | BLE受動探索を限定確認。接続・HID入力は未確認 | C6 HCI経路なし、既定BT無効。両OSとも入力完了と扱わない |
| シェルGPIO | 予約ピン管理、所有、方向・値・解放。`IO_API.md` | GPIO cdevツール追加済み。MeOS相当のボード予約表・番号解決・解放時Hi-Zは未実装 |
| ADC | 生値取得、未校正。`IO_ANALOG.md` | Linux IIOドライバなし。生値取得・較正の区別を維持して実装が必要 |
| PWM | LEDC 1系統、波形未検証。`IO_ANALOG.md` | Linux PWMドライバ/DT/ユーザーAPIが必要 |
| UART | UART1 polling/内部loopback。外部配線は未確認。`IO_UART.md` | 既存UART0は回復経路。外部UART1ピン設定・所有管理・Python APIが不足 |
| SoftI2C/SoftSPI | 所有管理と有限transfer。外部通信未検証。`IO_PROTOCOLS.md` | 既存I2C-GPIOはKeyboard専用。ユーザー外部バスの予約とドライバ接続が必要 |
| MicroPython本体 | 1.26.1 native MeOS、VFS/REPL。`MICROPYTHON.md` | 1.22.2 Unix NOMMU、REPL/ファイル/ネットワークは既存。MeOS版への版数更新は別検証 |
| MicroPython I/O | machine.Pin/ADC/PWM/UART/SoftI2C/SoftSPI | 今回Linux用`tab5io.Pin`を追加。物理GPIO番号の互換性・pull/IRQ・他I/Oは未実装 |
| FPGAリンク／GUI | protocol/mock等。物理通信は未成立。`FPGA_LINK.md` | Linux通信ドライバ、実FPGA/DDR3評価は未完了。MeOSのmockを実機実績と扱わない |
| CPython/Pyxel | 調査・計画段階 | MeOSの実装済み機能には含めない。LinuxでもNOMMU・容量・互換性の評価が必要 |

参照資料は[固定したMeOSコミットのdocs](https://github.com/airpocket-soundman/tab5-meos-fpga/tree/cfad4ad88092f84f99084bd4f12f7c60e6d2eb92/docs)に対応。
MeOSコードはコピーせず、LinuxのGPIO cdev、V4L2、fbdevを用いて実装した。

## 実装順と完了条件

今回のユーザーランド追加は[使い方・確認結果](TAB5_PERIPHERALS.md)に記録。
GPIO 6試験、メディア9試験、実MicroPythonのホストfixtureが通っても、
実機で使用できる機能数が増えたとは扱わない。

1. 今回の変更をP4向けにビルドし、1コア・シェル・既存機能を回帰確認する。サイズ制限とGC/FD解放も確認する。
2. HS USBホストを実装し、1台の列挙・転送・切断・復帰を確立する。これがストレージ・HID・Ethernet・UVCの共通依存。
3. メモリを読み取り専用から確認し、書込・sync/umount・保持、ハブ複数機器、Ethernet、UVCの順で段階試験する。
4. GPIOドライバの他ピンへの方向設定の影響を確認し、ボード予約表と番号解決を導入する。その後、ADC/PWM/UART/外部I2C/SPIとPython APIを接続する。
5. microSD、SFTP、タッチ、内蔵カメラをそれぞれ単独で実装・検証する。SFTPはNOMMUでのプロセス起動と認証済みsubsystemの成立を先に確認する。

ハードウェア仕様はキャリア`f4939cbdc66823696448288a1dac7592a82c15f7`の
共通仕様（2026-10-26）を確認した。GPIO/DT配線と電源設定は今回変更していない。
新しいバスやピンを有効化する際に再照合する。

## 現在の実機制約

WindowsでCOM1とMCU-Link COM5のみを検出し、Tab5は未検出のまま。
実機書込み・テストのユーザー許可は継続しているが、対象を特定できるまでは書き込まない。
成功済みCI成果物は復旧用として保存しており、今回の新規実装のビルド成果物と区別する。
