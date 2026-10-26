# GPIOカーネル経路の確認と修正

更新日：2026-10-26。コード・ホストMMIOモデルの確認結果。GPIO端子の物理動作は未検証。

## 出典と問題

`versions.lock.json` と `linux/build-m1.sh` のnetwork profileは、WHY2025 `bd790395c14968a27c00f962c9cd08d66f39de24` の `patches/linux/0002-gpio-esp32p4.patch` をLinux `acb7cf4c1184e27622be0faf89244d5001ed1e87`（6.18.35）へ適用する。ローカルのvendorは未展開だったため、固定コミットの原文を取得して確認した。参照0002のSHA-256は `c51e63afe2bbab043375eecd969cd6ce66951a6d72eb9ec0906f7c1a58ab7ae9`。

- [固定GPIOドライバパッチ](https://github.com/mrbreaker/why2025-linux/blob/bd790395c14968a27c00f962c9cd08d66f39de24/patches/linux/0002-gpio-esp32p4.patch)
- [Linux gpio-mmio.c](https://github.com/gregkh/linux/blob/acb7cf4c1184e27622be0faf89244d5001ed1e87/drivers/gpio/gpio-mmio.c)
- [固定ESP-IDF GPIOレジスタ定義](https://github.com/espressif/esp-idf/blob/2c211b236707889e8400c4dc5644dd5c4ee071e0/components/soc/esp32p4/register/hw_ver1/soc/gpio_reg.h)
- [固定ESP-IDF SoC能力定義](https://github.com/espressif/esp-idf/blob/2c211b236707889e8400c4dc5644dd5c4ee071e0/components/soc/esp32p4/include/soc/soc_caps.h)

元ドライバはENABLE_W1TS/W1TCをgeneric GPIOのdirection状態レジスタとして渡す。しかしgeneric実装はdirection変更時にbank全体のshadowと反転値を書き、初期化時にも同様の同期書込みを行う。W1TCは1を立てた端子の出力を解除するため、他の端子、特にboot shimが設定した出力を解除し得る。既存DTSのbacklight hogはこの現象の回避策であり、任意端子の安全な制御を保証しない。

## 0083の変更

`linux/kernel-patches/0083-gpio-esp32p4-isolate-direction.patch` は0002の後に適用する。

1. generic初期化へdirectionレジスタを渡さず、初期化のbank全体書込みをなくす。
2. direction_input/outputは指定端子のBITだけW1TC/W1TSへ書く。outputは値をラッチしてから出力を有効にする。値設定自体のgeneric W1TS/W1TC処理は既存の単一bit操作を維持する。
3. get_directionは読出し用ENABLE（bank0=`0x20`、bank1=`0x2c`）から判定する。
4. requestは指定端子だけを一度入力にしてから、GPIO matrix出力選択を256、出力許可をGPIO_ENABLE側にし、値・OE反転を解除する。ルート変更直後に古いラッチ値を出力しないための順序であり、要求した出力値は後続のdirection_outputで設定する。既存IO_MUXのMCU_SEL=1とinput enable設定も維持する。IO_MUX未マップ時は成功扱いしない。
5. freeは解放する端子だけを入力にする。boot時のperipheral routeを復元する機構ではなく、要求終了後の出力解除を目的とする。
6. bankラベルを固定し、存在しないGPIO55以降をbank1から除く。固定ESP-IDFは55端子（0〜54）を定義しており、元ドライバの57端子というコメントは一致しない。

pull-up/down/disableは既存set_configで扱う。ドライブ強度、alternate function、任意peripheralの奪取や回復は今回のユーザーAPIに含めない。Linuxのconsumer管理で要求済み端子は排他とし、userspaceでも許可した外部端子だけを扱う必要がある。

requestで一度入力にするため、要求対象自身がboot時に既に出力していた場合は一時的に出力が解除される。backlight hogなども取得時にはこの挙動を受ける。他の未要求端子の出力は変更しない。無瞬断のperipheral引継ぎを保証する変更ではない。

## ユーザーランドが参照する識別

| 項目 | bank0 | bank1 |
| --- | --- | --- |
| gpiochip label | `esp32p4-gpio-bank0` | `esp32p4-gpio-bank1` |
| chipinfo.lines | 32 | 23 |
| 端子番号 | 0〜31 | 32〜54 |
| chip-relative offset | GPIO番号 | GPIO番号−32 |

`gpiochipN` のNは登録順に依存するため固定しない。GPIO_GET_CHIPINFO_IOCTLでname/label/linesを確認する。元のlabelはplatform device名由来であり、未修正カーネルを新ラベルと同一と推測しない。DTのMMIOアドレスが同じ二つのbankを、デバイス番号や名前の部分一致だけで選ばない。

GPIO character device v2には `CONFIG_GPIO_CDEV=y` が必要。新規APIはv2 ioctlを使うため `CONFIG_GPIO_CDEV_V1=n` を推奨する。sysfs GPIO ABIや `/dev/mem` は必要ない。カーネル設定とパッチのビルダーへの組込み、生成された最終.configの確認は別の統合手順で行う。

## ホスト確認

固定0002をローカルファイルへ保存したうえで、次を実行する。テスト自身はネットワーク取得・vendor展開・GPIO操作を行わない。

```text
python tools/test_gpio_kernel_patch.py --reference PATH/0002-gpio-esp32p4.patch --cc D:/tmp/tab5-test-tools/ziglang/zig.exe --zig
```

2026-10-26、Windows/Python 3.12・既存Zigで成功。0002のハッシュを照合し、元のドライバを復元して0083を実際に適用した。そこからdirection/input/output/get_direction/free/requestの実際の関数を抽出し、C11のmock MMIOで55端子を検査した。他端子の値・方向を維持すること、値を先に書くこと、解放時の単一端子入力化、bank相対とglobal pinの区別、指定pad以外のmatrix/IO_MUXレジスタ不変を確認した。generic初期化にdirectionレジスタを渡さないこと、各callbackの登録、labelとbank1の端子数も検査する。

これはカーネル全体のコンパイルや物理端子の検証ではない。次はビルド後、Tab5を利用できる時点でchipinfoとconsumerを読み、回路図で確認した外部端子を一つずつ測定する。LCD・SD・I2C・Wi-Fi等の内部機器を含む他端子が維持されること、解放後入力状態、GPIO入力値、出力ラッチと物理値、pull、再要求を実機で照合する。
