# MeOS相当機能のLinux対応

更新日：2026-10-27。作業開始コミット：`0208849`。

## 現状

| 機能 | Linux側の実装 | このフォークの実機確認 |
| --- | --- | --- |
| MicroPython | 既存1.22.2 NOMMU Unix版に`tab5io.Pin`を追加。m3-labの既定構成に含む | 今回未実施 |
| シェルGPIO | `tab5-gpio info/get/hold`を追加、GPIO character device v2を有効化 | 未確認 |
| 周辺機器一覧 | `tab5-peripherals`を追加。USB、ストレージ、映像、GPIO、MicroPythonを列挙 | 未確認 |
| USBメモリ | SCSI・USB Storage・FAT/exFATの任意追加フラグメントを用意 | HSホスト対応が未実装のため未確認 |
| USBカメラ | UVC・V4L2設定と`tab5-camera`の単一YUYVフレームBMP保存を追加 | HSホスト対応が未実装のため未確認 |
| BMP表示 | `tab5-image`で情報・チェックサム表示とfbdevへの描画 | 未確認 |
| USB HID／Ethernet | HID、CDC-ECM/NCM、RTL8152/8153の任意追加設定 | HSホスト対応が未実装のため未確認 |

MeOS側の既存実装全体との対照は[機能移植一覧](MEOS_FEATURE_PARITY.md)を参照。

USBメモリとUSBカメラはまだ使用可能になっていない。MeOSのUSB DMAコードを
Linuxにコピーするだけでは、IRQ、DMA API、キャッシュ同期、切断処理、電源管理と
USBコアへの接続を満たさない。既存の`usb_otg11`はGPIO26/27を使うFS回路で、
Tab5では音声と競合するためdisabledのまま維持する。

## ビルドと使い方

従来の入口を使用する。今回追加したGPIO・一覧ツールはTab5構成で選択する。

```sh
EASYSTICK_BOARD=tab5 bash linux/build-c68.sh --vendor /path/to/output --profile m3-lab
```

USBクラス層のビルド実験は上記に`EASYSTICK_TAB5_USB_CLASSES=1`を追加する。
コントローラは有効化しない。生成後の`.config`でStorage、UVC、HID、ECM等が
残ることをビルドの確認処理で検査する。イメージ容量とRAM消費の実測も必要。
未検証イメージである。

```sh
tab5-peripherals
micropython -c 'import sys; print(sys.implementation)'
micropython /boot/main.py
```

`EASYSTICK_LAB_TOOLS=0`は既存仕様どおりMicroPythonを除外する。
Unix版なのでESP-IDF版の`machine.Pin`などは提供しない。CPython全体との互換性も
意味しない。追加したLinux用APIは`tab5io.Pin`である。

GPIOはまず`tab5-peripherals`と`tab5-gpio info /dev/gpiochipN`で対象を確認する。
以下は構文例で、CHIP/OFFSETには回路とLinuxドライバを照合した値を入れる。

```sh
tab5-gpio get CHIP OFFSET
tab5-gpio hold CHIP OFFSET 1
# 別の端末からkill -TERM PID、または前面実行ならCtrl-Cで解放
```

OFFSETはチップ内番号でありGPIO番号と同一とは限らない。入力要求も方向を変更する。
`hold`は要求と同時に初期出力値を設定し、プロセスが生存中はラインを所有する。
終了後の電圧・方向はドライバ依存で、元の設定への復元は保証しない。
起動時や終了時に自動でピンを駆動せず、既存ドライバ所有のラインを強制解除しない。
ただしカーネルで未要求でも内部機器の予約ピンである可能性がある。

MicroPythonでは、照合済みのCHIP（文字列パス）とOFFSET（整数）を使う。
MeOSのGPIO番号をそのまま渡すAPIとは異なる。

```python
from tab5io import Pin
with Pin(CHIP, OFFSET, Pin.IN) as p:
    print(p.value())
# 出力試験を実施できる配線の場合のみ:
with Pin(CHIP, OFFSET, Pin.OUT, value=0) as p:
    p.on()
    p.off()
```

`value()`、`value(0/1)`、`on/off`、`deinit`、コンテキスト管理を実装。
初期出力はライン要求と同時に設定する。入力への書込みと解放後アクセスを拒否し、
Linuxのライン所有権で重複要求を拒否する。GC finalizerとプロセス終了でもFDを解放するが、
通常は`with`または`deinit()`を使う。解放後のピン状態はドライバ依存。
pull、IRQ、ADC/PWM/UART/SoftI2C/SoftSPI、MeOSの予約ピン表は実装していない。
このAPIもカーネルで未要求の内部ピンを判別するものではない。

## カメラとBMP

```sh
tab5-camera --info /dev/video0
tab5-camera capture /dev/video0 /tmp/frame.bmp 160 120
tab5-image --info /tmp/frame.bmp
tab5-image /tmp/frame.bmp /dev/fb0
```

`tab5-camera`はsingle-planar V4L2 MMAP captureを使い、BT.601 limited-range
YUYVだけを24bit BMPに変換する。既定160×120、返された実サイズの上限640×480。
ドライバが返した別形式、非対応色表現、インターレースを拒否する。取得の待機は
単調時計で最大10秒。エラーフレーム・短いフレームは再取得し、範囲外のインデックス・
過大サイズは拒否する。割込み・切断・失敗でもstream停止とバッファ解放を試みる。
既存ファイルは上書きせず、自分が新規作成した途中ファイルは保存失敗時に取り除く。
NOMMUでのドライバのMMAP対応、DMAとキャッシュ整合性は実機確認が必要。
1バッファ最大2MiB、要求は2バッファで、実機での確保成功を保証しない。

`tab5-image`は最大1920×1080の非圧縮24bit、RGB555/565 16bit BMPを行単位で読む。
情報表示は寸法とRGB24 FNV-1aを出し、MeOSのRGB565チェックサムとは区別する。
fbdevの16/24/32bit truecolor、strideとoffsetを確認し、左上から等倍でクリップ描画。
全画面画像バッファは確保しない。画面の回転・拡大、VTの占有、元の画面の復元は
行わず、コンソールとの同時描画は競合しうる。Linux側ST7121表示の実機確認は別途必要。
ネイティブツールにはbFLTの32KiBスタックを指定した。

キャリア共通仕様（2026-10-26）を照合済み。FPGA接続案のGPIO
18/19/5/3/4/2/48/47、16、45、51は割当を変更していない。
キャリア接続中の汎用GPIO試験に使わない。MeOSの外部ピン許可表はLinuxの
キーボード・電源・SDIO等の所有状態と異なるため、そのまま転用しない。

## 未解決と次の作業

1. Tab5 HSホストのレジスタ、PHY、クロック、IRQ、VBUS制御をMeOSと基板資料で照合し、LinuxのホストドライバとDTを実装する。
2. 列挙、USB抜き差し、ハブ、DMAキャッシュ同期、タイムアウト、切断後解放を確認する。
3. USBメモリは最初に読み取り専用でマウントし、別途書込・sync・umountを確認する。自動マウントは現状実装しない。
4. UVCホスト成立後、追加した`tab5-camera`で低解像度1フレーム取得・保存を実機確認する。MeOSの160×120 BMP取得実績をLinux実績と扱わない。
5. GPIOは外部未接続の空きピンから入力、出力、所有競合と終了を確認し、液晶・キーボード・Wi-Fi・シェルへの影響を調べる。
6. MicroPythonでREPL、ファイル実行、メモリ不足時の挙動と`tab5io.Pin`を実機確認し、残るI/O APIを設計する。

今回の変更はソフトウェア追加とホスト側検査まで。全体クロスビルド、実機への
書込み、L0回帰確認は未実施。対象基板や接続機器での動作済み機能を増やした記録ではない。

## 今回のホスト検査

Windows上のWSL Ubuntu 24.04で`python3 linux/tests/test-tab5-gpio.py`を実行。
GCCの`-Wall -Wextra -Werror`で実コードとioctl代替fixtureをコンパイルし、
情報表示、入力、出力初期値と待機前SIGTERM、不正引数、busy拒否、存在しない
デバイスの6試験が成功した。fixtureはGPIO16という番号を模擬するだけで、
実基板のGPIO16の使用を許可するものではない。
`bash -n linux/build-m1.sh`、一覧スクリプトの`sh -n`、`git diff --check`も確認する。
Linux/BuildrootサブモジュールとESP-IDFビルド環境は今回未展開で、
クロスビルド成功や実機動作の証拠ではない。

追加の`python3 linux/tests/test-tab5-media.py`の9試験では、実BMP codec、上下方向、
RGB555/565、fbdevのstride/offset/色、切断・待機期限・割込み・エラーフレーム・
MMAP失敗等のV4L2代替fixtureと解放、上書き拒否を検査した。
MicroPython 1.22.2公式ソースのSHA-256を既存パッケージの固定値と照合し、
同じNOMMU variant設定を使ってWSLのx86-64用にビルドした。
`python3 linux/tests/test-tab5-micropython.py HOST_MICROPYTHON`は実インタープリタ上で
GPIO ioctl代替を使用し、読書き、重複拒否、例外解放、GC、解放後アクセス拒否、
引数変換中の解放と100回の取得解放を確認した。
これはP4用クロスビルドや実GPIOを使用した試験ではない。
同じホスト検査のGitHub Actions定義を追加したが、CI実行はまだ行っていない。

## 実機書込みの準備（2026-10-27）

ユーザーから接続済みTab5への書込み・テストの許可を受け、接続を確認した。
この時点のWindowsのシリアル一覧はCOM1とMCU-LinkのCOM5
（VID:PID `1FC9:0143`）のみで、EspressifのUSB機器は未検出。
Tab5のポートを特定できないため、他機器への接続や書込みは行っていない。
ユーザーへ電源・データUSB接続の再確認を依頼した。

復旧候補としてこのフォークの成功済みCI run `39729147095`
（コミット`519c095`）の`tab5-assets`を
`D:\Workspace\tab5-linux-lab\recovery-519c095`へ取得。
`SHA256SUMS.txt`と`SHA256SUMS-c6.txt`の全項目が一致した。
これは今回の変更を含む新規ビルドではなく、ST7121でのLinux表示成功も示さない。
同じ作業ディレクトリの`esptool481`にesptool 4.8.1を準備し、version表示まで確認した。

実機フラッシュの読出し・書込み・起動テストはまだ未実施。
次はTab5ポートの検出、現行ファームと復旧手段の確認、P4フラッシュ保存、
今回の変更を含む候補のクロスビルド、書込み・読戻し検証、1コア起動と
GPIO/MicroPythonの限定テストの順に進める。C6は必要性を確認するまで更新しない。
