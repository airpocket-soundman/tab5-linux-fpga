# シェルとMicroPythonからのGPIO操作

更新日：2026-10-26。Linux GPIO character device v2を使う実装を追加した。ホストの模擬試験・ビルド結果と、実端子の動作確認は区別する。既存Tab5へ転送・書込み・実行は行っていない。

## 利用するインターフェース

シェルでは `tab5-gpio`、MicroPythonでは `tab5gpio.Pin` を使う。両方が同じCコードで許可ピン、controller識別、入力／出力の検査、排他所有と解放を扱う。MicroPythonはCのline requestを直接保持し、subprocessやシェル経由で出力を設定しない。標準の `machine` モジュールを置き換えない。

Linuxの[GPIO v2 API](https://docs.kernel.org/userspace-api/gpio/chardev.html)のline request fdを保持している間だけ、そのピンを所有する。終了後の出力保持を約束するone-shot setterは提供しない。

## シェルの例

以下は新しいカーネル・ユーザーランドを導入し、対象ピンと外部回路を確認した後の実行例であり、今回実機では実行していない。既存のデバイス権限が必要。権限を自動で緩める機能はない。

```sh
# 許可ピンの一覧。このコマンド自体はGPIOデバイスに触れない。
tab5-gpio list

# GPIO16を入力として確保し、一度読んで解放する。
tab5-gpio read 16

# GPIO16を初期値1で確保し、5秒保持して解放する。
tab5-gpio hold 16 1 --seconds 5
```

`hold` の時間指定は1〜3600秒。初期値は出力方向の要求と一緒に設定する。通常終了、SIGINT、SIGTERMでfdを解放する。プロセスが異常終了した場合もkernelがfdを解放する。本フォークの修正ドライバは解放したピンだけを入力にするが、解放後の電圧や外付け回路の状態は保証しない。

## MicroPythonの例

```python
from tab5gpio import Pin

with Pin(16, Pin.OUT, value=0) as pin:
    pin.on()
    print(pin.value())
    pin.off()

with Pin(16, Pin.IN) as pin:
    print(pin.value())
```

`Pin(id, mode=Pin.IN, *, value=0)`、`value()`、`value(0/1)`、`on()`、`off()`、`deinit()`、`with` に対応。GPIO番号はSoC GPIO番号であり、コネクタの物理ピン番号ではない。modeとvalueは整数0/1のみを受け付ける。入力に対する書込み、bool・文字列・float・不正な番号は拒否する。

同じピンはシェルとMicroPython間でも同時確保できない。`deinit()`は二度呼んでも二重にcloseしない。`with`の終了では解放し、GCのfinalizerも補助的に解放する。GC時期は不定なので`with`または明示的`deinit()`を基本とする。

## 許可ピンと未対応機能

許可するのは `2, 3, 4, 5, 16, 18, 45, 47, 48, 51`。GPIO19はUSBとの疑義が残るため拒否し、それ以外も許可リストにないピンは拒否する。GPIO0/1のKeyboard、GPIO8〜15の無線関連、22のbacklight、24/25のUSBシリアル、31/32のシステムI2C、39/42/43/44のmicroSDなどの内部機器を再設定しない。

これは接続先や外付けFPGAとの競合がないことを実測したリストではない。FPGAの通信用に割り当てたピンを、同時に汎用GPIOとして操作してはならない。pull、IRQ、debounce、open-drain、PWM、ADC、I2C/SPI/UARTは本APIには含めない。

## 必要なカーネルとイメージへの組込み

- `0083-gpio-esp32p4-isolate-direction.patch`を、既存のGPIOドライバ0002の後へ適用する。
- `CONFIG_GPIO_CDEV=y`を有効化し、古いsysfs APIや直接MMIOへのfallbackは行わない。
- ドライバの安定label `esp32p4-gpio-bank0/1`とline数32/23を確認する。`gpiochip0`等の番号順には依存しない。
- `/proc/device-tree/compatible`にNUL区切りの`m5stack,tab5`が必要。別基板と旧ドライバは拒否する。
- `EASYSTICK_BOARD=tab5`のnetwork profileで `BR2_PACKAGE_TAB5_GPIO=y` を選ぶようビルド入口を更新した。シェルclientを配置し、MicroPythonを選択した場合は同じcoreをnative user moduleとして組み込む。Stamp-P4側の標準設定へは追加しない。

旧イメージのMicroPythonにはこのモジュールは入っていない。新しいユーザーランドと0083適用済みカーネルを揃えて導入する必要がある。今回のCI成果物はカーネル／DTBとユーザーランド実行ファイルであり、既存の実機ファームウェアを更新した結果ではない。Buildrootの全体イメージ再生成・実機での導入は残件。

## 失敗時の読み方

| エラー | 主な確認点 |
| --- | --- |
| EPERM | 許可されていないピン、入力に対する書込み |
| EBUSY | 既に他プロセス・Pinオブジェクトが所有している |
| ENODEV / ENOENT | Tab5識別、GPIO_CDEV、chip node、修正ドライバのlabel |
| EACCES | デバイスの既存アクセス権。root等の正当な権限で実行する |
| EBADF | `deinit()`後の読書き・再入場 |
| ENOTTY | カーネルが必要なGPIO v2 ioctlへ対応しているか |

未対応機能や失敗を模擬成功へ置き換える処理はない。

## 作業・検証記録

作業開始 `0a8198c`。このLinuxリポジトリだけを変更し、MeOS・COM・USB・実GPIOへの操作は行っていない。共通仕様はキャリア側の2026-10-26版と照合し、通信ピンや電源仕様自体は変更していない。

既存ドライバの方向変更・初期化で他ピンの出力を解除し得る問題を0083で修正した。指定ピンのbitだけを操作し、GPIO経路の設定と解放も追加した。根拠・固定ソース・55ピンのmock MMIO確認は [カーネル調査](GPIO_KERNEL_REVIEW.md) に記録する。要求対象そのものは経路設定前に一度入力にするので、既存出力を取得する際の一時変化はあり得る。他ピンを維持することと電気的な無変動を区別する。

[ユーザーランドCI40282692522](https://github.com/airpocket-soundman/tab5-linux-fpga/actions/runs/40282692522)で以下が成功した。

- GCC/Clangの共通core試験：全0〜99のピン選択、許可10ピンのbank対応、引数の先行検査、排他、chip重複、寿命・エラー時の解放。
- MicroPython1.22.2へnative moduleを実際に結合し、ホストで引数・入出力・排他・`with`・GC・fd再利用を確認。
- productionモジュールの不正引数試験と、mock専用関数がproductionに存在しないことを確認。
- rv32imac/ILP32/uClibc NOMMUのシェルclientとMicroPythonをビルド。bFLT形式と32KiB stackを検査。
- MicroPythonのbss_end+stack=475,312 bytesで、既存の512KiB allocation予算内。これは実機プロセス最大RAM量の測定ではない。

取得したartifactのSHA-256を再照合した。`tab5-gpio`は `7bfa2a7aecd854e891ebb34d6e2f52fcd502693ed578d97dd63f6ecfbf4bbce7`、MicroPythonは `bffafd64877f89fa21bbe6a1a766cac434896657f5c71ca45361f421b5defa7a`。source=`cd2800f`の成果物であり、後続の同ソース再ビルドは日時等でhashが異なる場合がある。

次の作業は全体イメージへの導入と、実機再開後の入力・出力レベル、他機能への影響、プロセス終了時の解放の確認。実端子の波形・電圧、物理外部機器の動作、カーネル変更後の既存機能回帰は未検証。

[追加CI40283127205](https://github.com/airpocket-soundman/tab5-linux-fpga/actions/runs/40283127205)ではLinux adapterのopen/read/ioctl/closeを全て置換し、boardのNUL解析、v2の方向・初期値・mask、失敗時のerrnoとfd解放をGCC/ClangのASan/UBSan付きで検証した。実GPIOのsyscallは実行していない。
