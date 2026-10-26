# Tab5 Linux GPIO cdev v2

Linux GPIO character device v2を使う専用C APIとシェルコマンド。GPIOの排他的なline requestを保持し、入力値の取得と出力値の設定を行う。MicroPythonモジュールもこのC APIを共有する。実機動作、電圧、波形、配線先との競合は未検証。

## 有効化条件

- `CONFIG_GPIO_CDEV=y`とGPIO cdev v2対応ヘッダが必要。v1へのfallbackや直接MMIOアクセスは行わない。
- このフォークのGPIO driver修正が必要。bank0のlabel=`esp32p4-gpio-bank0`・32lines、bank1=`esp32p4-gpio-bank1`・23linesを確認する。従来の曖昧なlabelでは動作を拒否する。
- `/proc/device-tree/compatible`のNUL区切り項目に`m5stack,tab5`が必要。別基板での操作を拒否する。
- デバイスの既存アクセス権を使う。一般ユーザー向けのchmodや権限拡大は行わない。

SoC GPIO番号の許可リストは`2,3,4,5,16,18,45,47,48,51`。GPIO19はUSBとの疑義が残るため拒否し、その他のピンもすべて拒否する。この許可リストは基板配線・接続先の安全性を保証するものではない。FPGAの通信用に使用中なら、その接続と所有権を確認してから操作する。

`/dev/gpiochip0`等の番号を固定しない。gpiochip0〜255を列挙し、chipinfoのlabel・line数・動的な`gpiochipN`名の形式を検査する。bank0ではSoC番号をそのままoffset、bank1ではSoC番号−32をoffsetとする。一致するcontrollerが複数ある場合も拒否する。

## シェル

```text
tab5-gpio list
tab5-gpio read 16
tab5-gpio hold 16 1 --seconds 5
```

`list`はポリシーを表示し、GPIOデバイスを開かない。`read`は入力として一時的にlineを要求して一度読み、解放する。`hold`は出力と初期値を同じline requestで設定し、指定時間（1〜3600秒）fdを保持してから解放する。方向を先に設定して別の操作で初期値を書く方式は採らない。

出力の寿命はfd所有期間である。コマンド終了後に値を保持するone-shot出力APIは提供しない。このフォークのdriver修正では解放したピンを入力に戻すが、解放後の電圧や外付け回路の状態は保証しない。SIGINT/SIGTERMを受けた場合も解放する。pull、IRQ、debounce、open-drainの設定は提供しない。未対応機能を成功扱いにしない。

## C APIと試験

`tab5_gpio.h`の`struct tab5_gpio`を`TAB5_GPIO_INITIALIZER`で初期化する。
`tab5_gpio_open`、`get`、`set`、`close`はlibc形式で成功値または−1とerrnoを返す。
getの成功値は0/1。入力に対するsetは拒否する。closeは二回呼んでも二重解放せず、closeが失敗した場合も所有fdを無効化する。失敗時に同じfdを無条件で再closeすると別の資源を閉じる可能性があるためである。利用者は構造体をコピーして所有権を複製しない。

```text
python linux/tab5/gpio/run_tests.py --cc cc
python linux/tab5/gpio/run_tests.py --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig
cc -std=c11 -O2 -Wall -Wextra -Werror linux/tab5/gpio/tab5_gpio.c linux/tab5/gpio/tab5_gpio_linux.c linux/tab5/gpio/tab5_gpio_cli.c -o tab5-gpio
```

host試験はLinux adapterをリンクせず、`tab5_gpio_ops`へ偽のsyscallを注入する。実際のデバイス・GPIO・シリアル・ネットワークにはアクセスしない。全GPIO番号の許可・拒否、validation前のI/Oなし、bank mapping、別controller/不正label/line数/重複controllerの拒否、排他要求の失敗、初期値、入力へのset拒否、close失敗を含む資源解放を確認する。Cコンパイルとhost試験は物理GPIOの動作証拠ではない。

2026-10-26、Windowsの既存Zigで`-std=c11 -O2 -Wall -Wextra -Werror`のコンパイルと注入試験が成功した。assertは最適化ビルドでも明示的に有効化する。Linux adapterのioctl、シェルCLI、MicroPythonの実機実行はこの試験の対象外。

実機が利用できる段階では、driver修正とv2有効化を含むイメージの起動、chipinfo、入力、出力初期値、同一ピン二重要求の拒否、終了後の入力への復帰、他ピン不変を順に確認する。外部配線前には共通キャリア仕様とI/O電圧を照合する。
