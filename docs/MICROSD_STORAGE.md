# Tab5 microSDストレージ仕様と実装候補

更新日：2026-10-22

## 状態と目的

ユーザーの「ストレージが足りなければmicroSDを使う」という要求を、Tab5 Linuxの保存領域拡張として扱う。本資料は仕様と未適用の実装候補であり、現在のLinuxでmicroSDが使えることを示すものではない。

現在はST7121液晶でLinuxの表示・1コア起動・シリアル操作を確認した段階。microSDのカード認識、マウント、読み書き、Wi-Fiとの同時動作は未検証で、カードの有無・容量・既存ファイルシステムも未確認である。本資料の作成ではカーネル、Device Tree、boot shim、実機フラッシュを変更していない。

## 保存先の仕様

16MB内蔵フラッシュの起動OSと読み取り専用rootfsを維持し、microSDを大容量データの保存先として追加する。

| 用途 | 保存先の仕様 |
| --- | --- |
| microSDマウント先 | `/mnt/sdcard` |
| アプリデータ・測定結果・転送ファイル | `/mnt/sdcard/tab5/data` |
| 永続ログ | `/mnt/sdcard/tab5/logs` |
| 再生成できるキャッシュ | `/mnt/sdcard/tab5/cache` |
| OS起動に必要なファイル | 引き続き内蔵フラッシュ |

対応後は容量の大きい保存処理からこの保存先を選べるようにする。内蔵rootfsの容量不足を検出して任意のファイルを自動移動する機能や、rootfs全体の透過的な拡張を意味しない。`/boot/config.txt`の永続化も別課題であり、microSDの追加だけでは実現しない。

- マウントに成功したことを確認してから保存用ディレクトリを作成する。未マウントの`/mnt/sdcard`へ書き込み、RAMを使い切る動作を避ける。
- SDがない、マウントできない、空き容量が足りない場合、大容量の保存処理は理由を示して終了する。永続化が必要なデータをRAMへ黙って退避しない。
- RAM上の一時データとログは上限を設ける。ログのローテーション、キャッシュの削除対象、空き容量の下限は各アプリの設定として定める。測定結果など保存が必要なデータは自動削除しない。
- カードがなくても内蔵フラッシュから起動でき、シリアル操作と既存機能を使えることを維持する。
- 初回は既存カードを読み取り専用で確認し、書き込み検証後に読み書き可能な運用へ進める。カードやパーティションを自動フォーマットしない。
- ファイルシステムの種類・カード識別情報・マウント状態を確認する。将来、別のブロック機器が増えても誤選択しないよう、デバイス名だけに依存しない識別を使う。
- 書き込み中にカードを抜かない。取り外し前に保存を停止し、同期・アンマウントを完了する。

microSDは保存容量を増やすもので、通常RAMや透過的なメモリ増設にはならない。NOMMUの制約は残る。Debian/Ubuntuの環境へ変わるわけではなく、`apt`によるパッケージ追加を可能にする仕様ではない。

## 配線と電源の確認結果

メーカーのTab5 PinmapとEspressif Tab5 BSP 1.3.2の`bsp_storage.c`で次を確認した。

| 信号 | Tab5 GPIO | SDMMC時 | SPI時 |
| --- | --- | --- | --- |
| DAT0 | 39 | DAT0 | MISO |
| DAT1 | 40 | DAT1 | 未使用 |
| DAT2 | 41 | DAT2 | 未使用 |
| DAT3 | 42 | DAT3 | CS |
| CLK | 43 | CLK | SCLK |
| CMD | 44 | CMD | MOSI |

物理microSDはSDMMCのslot 0に接続される。BSPはカード検出・書き込み禁止ピンを使用していない。SPI方式もBSPとメーカーの使用例に存在する。

カード側の電源制御にはP4内蔵LDO channel 4を使う。BSPは`sd_pwr_ctrl_new_on_chip_ldo()`へchannel 4を渡し、ESP-IDF 5.5.5の既定host設定は`io_voltage = 3.3f`。初期候補では3.3Vを維持し、1.8Vへの切替やUHS動作を対象にしない。液晶MIPI PHYのLDO3とは区別する。

Linux側には今回のカード用LDO制御をまだ追加していない。初期実装ではboot shimでLDO4を3.3Vとして取得・保持し、Linuxへ引き継ぐ候補を検討する。ハンドオフ後も給電が維持されることを実機で確認する。再初期化時に共有SDMMCコントローラをリセットしてC6を切断しないことも必要になる。

GPIO39〜44はTab5内部のmicroSD用配線として扱う。キャリア側の[共通ハードウェア仕様](../../tab5-tang-primer20k-carrier/docs/ESP32P4_FPGA_共通ハード仕様.md)にあるFPGA用の暫定GPIO一覧には含まれていない。将来のピン追加時も内部カードとの競合を確認する。

## 現在のSDMMCドライバでの障害

Wi-Fi用C6はSDMMC slot 1をGPIO8〜13経由で使用する。物理microSDのslot 0と同じDW MMCコントローラ`0x50083000`、同じ割込みを共有する。

現在のDevice Treeの`sdmmc1`ノードは`snps,slot-id = <1>`でC6側を指定している。使用中のkernel-kitの`drivers/mmc/host/dw_mmc.c`は`host->slot`を一つだけ持ち、slot初期化と割込み処理もその一つを扱う。`snps,slot-id`は物理slot番号を選択する変更であり、複数slotを同時に使えるようにする変更ではない。

同じMMIO範囲を持つslot 0用ノードをもう一つ追加しても、独立したホストにはならない。リソースの二重所有、共有レジスタ・割込み・クロックの競合が起きるため、この方法は採用しない。

native SDMMCで両方を使うには、単一コントローラ内の複数slot対応を実装する必要がある。少なくともslotごとのMMC host、要求の共有キューと切替、slot 1のSDIO割込み、カード検出、バス幅・クロック・電源状態、削除・再走査を扱う。既存`0009-easystick-dw-mmc-divider0.patch`ではCLKSRCが0のため両slotがdivider 0を使うので、クロック変更と別slotの状態保持も再評価する。C6 Wi-Fiとカード読み書きの同時検証が必要な、別の開発段階とする。

## 初期候補：独立したSPI GPIO経路

初回のカード読み書き確認には、microSDだけを標準`spi-gpio`と`mmc_spi`で扱う方法を候補とする。C6のslot 1とDW MMCドライバを維持し、物理microSDを別のLinux SPI controllerとして登録する。GPIO操作がCPU処理になるため低速で、性能やWi-Fi併用時の負荷は未確認である。

現kernel-kitにはGPIO bank 1のドライバと`gpio1`ラベルがある一方、SPIは設定無効で、ESP32-P4用ハードウェアSPIドライバも見当たらない。初期候補に必要な追加設定は以下。実際の設定適用、依存項目の解決、ビルドは未実施である。

```text
CONFIG_SPI=y
CONFIG_SPI_MASTER=y
CONFIG_SPI_BITBANG=y
CONFIG_SPI_GPIO=y
CONFIG_MMC_SPI=y
```

`CONFIG_MMC_BLOCK=y`、`CONFIG_FAT_FS=y`、`CONFIG_VFAT_FS=y`は調査したST7121カーネルで有効。exFATとext4は無効であり、初期候補は既存のFAT32カードとする。大容量カードの既存exFATを使用する場合は、その対応を別途追加・検証し、勝手にフォーマットしない。

以下は未適用のDevice Tree案。GPIO bank 1はGPIO32から始まるため、記載するoffsetはGPIO番号から32を引いた値になる。

```dts
/ {
    microsd_spi: spi-microsd {
        compatible = "spi-gpio";
        #address-cells = <1>;
        #size-cells = <0>;
        sck-gpios = <&gpio1 11 GPIO_ACTIVE_HIGH>;  /* GPIO43 */
        mosi-gpios = <&gpio1 12 GPIO_ACTIVE_HIGH>; /* GPIO44 */
        miso-gpios = <&gpio1 7 GPIO_ACTIVE_HIGH>;  /* GPIO39 */
        cs-gpios = <&gpio1 10 GPIO_ACTIVE_LOW>;   /* GPIO42 */
        num-chipselects = <1>;

        microsd: mmc@0 {
            compatible = "mmc-spi-slot";
            reg = <0>;
            spi-max-frequency = <400000>;
            voltage-ranges = <3300 3300>;
        };
    };
};
```

`mmc_spi`の初期化下限は400kHzなので、案の最大周波数も400kHzにする。`spi-gpio`の実効速度を保証する値ではない。カード検出IRQを省略した場合、現在の`of_mmc_spi.c`は検出をpollingにする。GPIO matrixの出力選択、pull-up、信号の待機状態、再起動時のカードのモードは実機で確認し、既存GPIOドライバの影響も調査する。

## 検証と次の作業

1. カードの有無、容量、ファイルシステム、保持すべき既存データを確認する。
2. USBキーボード対応など進行中の起動基準を確定し、microSDは独立した変更としてビルドする。
3. LDO4の3.3V給電とSPI GPIO設定を追加し、カード認識・容量表示までを読み取りで確認する。
4. 読み取り専用でマウントし、既存ファイルが読めることとメモリ使用量を記録する。
5. 検証用の小さなファイルで書き込み・読み戻し・ハッシュ一致・同期・再起動後の保持を確認する。
6. Wi-Fi通信と併用して、C6切断、タイムアウト、データ破損、CPU負荷と転送速度を確認する。
7. カード未挿入、マウント失敗、容量不足時の挙動と、指定保存先へのログ・データ保存を確認する。

本資料で完了したのは配線、BSP電源設定、既存kernel-kitの制限、実装候補の調査である。カード対応は未実装・未検証。将来の高速化はnative SDMMCの複数slot対応またはハードウェアSPI対応として検討する。

## 根拠

- [M5Stack Tab5公式Pinmap](https://docs.m5stack.com/en/core/Tab5)
- [M5Stack microSD SPI使用例](https://docs.m5stack.com/en/arduino/m5tab5/microsd)
- [Espressif Tab5 BSP storage実装](https://github.com/espressif/esp-bsp/blob/master/bsp/m5stack_tab5/src/bsp_storage.c)（調査ではローカルBSP 1.3.2を使用）
- [ESP-IDF 5.5.5 SD既定設定](https://github.com/espressif/esp-idf/blob/v5.5.5/components/esp_driver_sdmmc/include/driver/sdmmc_default_configs.h)
- [ESP-IDF 5.5.5 LDO電源制御](https://github.com/espressif/esp-idf/blob/v5.5.5/components/sdmmc/sd_pwr_ctrl/sd_pwr_ctrl_by_on_chip_ldo.c)
- リポジトリの`linux/dts/easystick-stamp-p4.dts`、`linux/boot-shim/main/m2_sdmmc.c`、`linux/kernel-patches/0009-easystick-dw-mmc-divider0.patch`
- フォークCI run `39729147095`のkernel-kit内`dw_mmc.c`、`mmc_spi.c`、`of_mmc_spi.c`、`gpio-esp32p4.c`とDT binding
