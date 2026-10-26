# Linux用MicroPython GPIOモジュール

2026-10-26。MicroPython 1.22.2のnative user C moduleとして`tab5gpio.Pin`を実装する。標準`machine`モジュールの置換ではない。Linux GPIO character deviceを共有C API経由で利用し、Pinオブジェクトが排他的line fdを保持する。サブプロセス・シェル・sysfsは使用しない。

```python
from tab5gpio import Pin

# 以下は実機接続・電源・外部回路を確認した後の実行例。
with Pin(16, Pin.OUT, value=0) as pin:
    pin.on()
    print(pin.value())
    pin.off()
```

`Pin(id, mode=Pin.IN, *, value=0)`、`value()`、`value(0/1)`、`on()`、`off()`、`deinit()`、context managerを提供する。modeはIN=0 / OUT=1。引数は整数のみでbool・文字列・浮動小数点・暗黙の整数変換を拒否し、mode/valueは0または1に限定する。入力で`value=1`を指定できない。無効引数はboard確認やGPIO open前に拒否する。

許可ピン、内部機器・予約ピンの拒否、Tab5の識別、controllerの識別とline対応は隣接する`../gpio/`の共有C APIに従う。GPIO番号はESP32-P4のGPIO番号であり、ヘッダの物理ピン番号ではない。出力の初期値はline要求時に指定する。pull、drive strength、IRQ、PWM、I2C、SPI、UARTはこのモジュールの対象外。

`deinit`は冪等。終了後の読書き・context再入場は`OSError`となる。GC finalizerもcloseするが、回収時点は非決定的なので明示的な`deinit`または`with`を基本とする。closeが失敗した場合もfd所有権を先に消去し、closeの再試行・GCで再利用済みfdを閉じない。明示的closeのエラーは`OSError`、finalizer内のcloseエラーは抑制する。close後の電気的な出力値・保持状態は保証しない。

## ビルド

upstreamの`examples/usercmodule/cexample`、`py/py.mk`、`py/misc.h`、`extmod/vfs_posix_file.c`の1.22.2実装を参照した。`USER_C_MODULES`には本ディレクトリ自体ではなく親の`linux/tab5`を指定する。

```sh
make -C ports/unix VARIANT=standard \
    USER_C_MODULES=/absolute/repo/linux/tab5
```

`MICROPY_ENABLE_FINALISER=1`が必須で、不足するvariantではコンパイルを停止する。デフォルトは`tab5_gpio.c`と`tab5_gpio_linux.c`をリンクし、テスト用関数やbackend切替APIを公開しない。rootfsへの組込みはBuildroot側のパッケージ設定で行う。

## 実機なしの試験

ホストテスト専用バイナリは以下で作成する。これはGPIOへの接続機能を持たず、模擬backendを実行時に実backendへ切り替えることもできない。productionバイナリと異なるbuildディレクトリを使う。

```sh
make -C ports/unix VARIANT=standard BUILD=build-tab5gpio-test \
    USER_C_MODULES=/absolute/repo/linux/tab5 TAB5_GPIO_TEST_BACKEND=1
cd /absolute/repo/linux/tab5/gpio-micropython
/absolute/micropython/ports/unix/build-tab5gpio-test/micropython test_mock.py
```

`test_validation.py`は有効なGPIOをopenしない引数検査であり、本番backendのバイナリでも実行できる。`test_mock.py`は引数拒否時のopen回数0、入出力、排他要求、入力への書込み拒否、context正常／例外終了、close失敗、fd再利用、GC解放を検査する。テスト専用の`_test_stats`と`_test_fail_close`はcompile-time flagがある場合のみ存在する。

実機のGPIO信号、電圧、周辺回路、カーネルの排他・controller検出は本モジュールのホスト試験で成立を確認したことにはならない。Tab5上の起動・実機操作・外部波形は未検証である。
