# Tab5 microSDストレージ仕様と実装状況

更新日：2026-10-22

## 状態と目的

ユーザーの「ストレージが足りなければmicroSDを使う」という要求を、Tab5 Linuxの保存領域拡張として扱う。boot shim、SPI GPIO、MMCブロックデバイス、FAT/exFATの設定と起動時マウント処理を実装した。FAT32カードで認識・読み書き・再起動後のデータ一致を確認した試験実装である。

実機の空の16GB microSD（識別名`USD00`）を認識し、容量31,090,688 sectors、既存FAT32パーティション`/dev/mmcblk0p1`を確認した。読み取り専用と読み書き可能の両マウント、保存用ディレクトリ作成に成功した。16KiBの乱数ファイルを作成・同期・アンマウントし、再起動後の自動RWマウントとcksum一致（1702212710、16384 bytes）を確認した。試験ファイルは削除済み。SDマウント中のWi-Fi接続とPCからのSSHログインも成功した。exFATカード、Wi-Fiとの同時高負荷、転送性能は未検証。本節はその時点の確認結果を示し、保存機能全体の完了とは扱わない。

## 保存先の仕様

16MB内蔵フラッシュの起動OSと読み取り専用rootfsを維持し、microSDを大容量データの保存先として追加する。

| 用途 | 保存先の仕様 |
| --- | --- |
| microSDマウント先 | `/mnt/sdcard` |
| アプリデータ・測定結果・転送ファイル | `/mnt/sdcard/tab5/data` |
| 永続ログ | `/mnt/sdcard/tab5/logs` |
| 再生成できるキャッシュ | `/mnt/sdcard/tab5/cache` |
| OS起動に必要なファイル | 引き続き内蔵フラッシュ |

容量の大きい保存処理からこの保存先を使う。各アプリからの利用は個別に接続・検証する。内蔵rootfsの容量不足を検出して任意のファイルを自動移動する機能や、rootfs全体の透過的な拡張を意味しない。`/boot/config.txt`の永続化も別課題であり、microSDの追加だけでは実現しない。

- マウントに成功したことを確認してから保存用ディレクトリを作成する。未マウントの`/mnt/sdcard`へ書き込み、RAMを使い切る動作を避ける。
- SDがない、マウントできない、空き容量が足りない場合、大容量の保存処理は理由を示して終了する。永続化が必要なデータをRAMへ黙って退避しない。
- RAM上の一時データとログは上限を設ける。ログのローテーション、キャッシュの削除対象、空き容量の下限は各アプリの設定として定める。測定結果など保存が必要なデータは自動削除しない。
- カードがなくても内蔵フラッシュから起動でき、シリアル操作と既存機能を使えることを維持する。
- 初回の実機確認では既存カードを読み取り専用で確認してから、読み書き可能なマウントへ進めた。起動スクリプトは読み書き可能なマウントを試し、失敗時は読み取り専用へフォールバックする。カードやパーティションの作成・フォーマット・修復は自動実行しない。
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

カード側の電源制御にはP4内蔵LDO channel 4を使う。BSPは`sd_pwr_ctrl_new_on_chip_ldo()`へchannel 4を渡し、ESP-IDF 5.5.5の既定host設定は`io_voltage = 3.3f`。今回の実装でも3.3Vを維持し、1.8Vへの切替やUHS動作を対象にしない。液晶MIPI PHYのLDO3とは区別する。

`TAB5_MICROSD_SPI=1`のboot shimでLDO4を3.3Vとして取得・保持し、GPIO39/42/43/44をGPIO経路へ設定してLinuxへ引き継ぐ。Linuxのマウントまで実機確認した。native SDMMCコントローラをカード用に再初期化せず、C6用の既存経路を維持する。

GPIO39〜44はTab5内部のmicroSD用配線として扱う。キャリア側の[共通ハードウェア仕様](../../tab5-tang-primer20k-carrier/docs/ESP32P4_FPGA_共通ハード仕様.md)にあるFPGA用の暫定GPIO一覧には含まれていない。将来のピン追加時も内部カードとの競合を確認する。

## 現在のSDMMCドライバでの障害

Wi-Fi用C6はSDMMC slot 1をGPIO8〜13経由で使用する。物理microSDのslot 0と同じDW MMCコントローラ`0x50083000`、同じ割込みを共有する。

現在のDevice Treeの`sdmmc1`ノードは`snps,slot-id = <1>`でC6側を指定している。使用中のkernel-kitの`drivers/mmc/host/dw_mmc.c`は`host->slot`を一つだけ持ち、slot初期化と割込み処理もその一つを扱う。`snps,slot-id`は物理slot番号を選択する変更であり、複数slotを同時に使えるようにする変更ではない。

同じMMIO範囲を持つslot 0用ノードをもう一つ追加しても、独立したホストにはならない。リソースの二重所有、共有レジスタ・割込み・クロックの競合が起きるため、この方法は採用しない。

native SDMMCで両方を使うには、単一コントローラ内の複数slot対応を実装する必要がある。少なくともslotごとのMMC host、要求の共有キューと切替、slot 1のSDIO割込み、カード検出、バス幅・クロック・電源状態、削除・再走査を扱う。既存`0009-easystick-dw-mmc-divider0.patch`ではCLKSRCが0のため両slotがdivider 0を使うので、クロック変更と別slotの状態保持も再評価する。C6 Wi-Fiとカード読み書きの同時検証が必要な、別の開発段階とする。

## 実装：独立したSPI GPIO経路

microSDだけを標準`spi-gpio`と`mmc_spi`で扱う方法を採用した。C6のslot 1とDW MMCドライバを維持し、物理microSDを別のLinux SPI controllerとして登録する。GPIO操作がCPU処理になるため低速で、性能やWi-Fi併用時の負荷は未確認である。

基準kernel-kitのGPIO bank 1ドライバと`gpio1`ラベルを利用する。SPIは基準設定では無効で、ESP32-P4用ハードウェアSPIドライバも見当たらなかった。`linux/tab5/microsd-spi.config.fragment`で追加する主要設定は以下。ビルド済みのカーネルを実機で起動し、カード認識を確認した。

```text
CONFIG_SPI=y
CONFIG_SPI_MASTER=y
CONFIG_SPI_BITBANG=y
CONFIG_SPI_GPIO=y
CONFIG_MMC_SPI=y
```

fragmentは`CONFIG_MMC_BLOCK=y`、`CONFIG_MSDOS_PARTITION=y`、FAT/VFAT、exFAT、NLSの各設定も組込みで有効化する。今回の実機確認は既存のFAT32カードで行った。exFATは実装設定に含むが実カード未検証であり、動作確認済みとは扱わない。ext4は今回の対象外とする。非対応形式でも勝手にフォーマットしない。

以下は適用した`linux/dts/tab5-microsd-spi.dtsi`の主要設定。GPIO bank 1はGPIO32から始まるため、記載するoffsetはGPIO番号から32を引いた値になる。

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
            no-1-8-v;
        };
    };
};
```

`mmc_spi`の初期化下限は400kHzなので、設定の最大周波数も400kHzにする。`0079-spi-gpio-honor-delay.patch`でbitbangの半周期待機を有効にし、最大速度の指定を無視してGPIOを連続操作する既存実装を変更した。400kHzは設定値で、測定済みの実効速度ではない。カード検出IRQを省略し、`of_mmc_spi.c`が検出をpollingにする。再起動・カードのモード遷移・取り外し後の再認識は追加検証する。

## 起動時のマウント処理

`linux/m3-lab/rootfs-overlay/etc/init.d/S30tab5-sdcard`は既存のSDファイルシステムだけを扱う。カードやパーティションのフォーマット・修復は行わない。

- `/sys/block/mmcblk*`から、SD種別、正のブロック数、実在するブロックデバイスを確認する。boot/RPMBなどの名前は候補から除外する。
- `removable=1`を通常候補とする。SPI接続SDが`removable=0`と報告される場合は、sysfsの解決済みdeviceパスがTab5の`spi-microsd/.../mmc_host/...`に属すると確認できる場合だけ例外として認める。
- 第1パーティションがあればそれを選び、なければカード全体を候補とする。今回の実機では`/dev/mmcblk0p1`を選択した。
- カードの検出を最大約10秒待ち、見つからなければSDなしで起動を続ける。別の機器がマウント先を使っている場合は変更しない。
- vfat、exfatの順に読み書き可能なマウントを試し、失敗した場合は同じ順に読み取り専用で試す。成功後も`/proc/mounts`で選んだデバイス・マウント先・ファイルシステムが一致することを確認する。
- 選択したカードが読み書き可能でマウントされた場合だけ`tab5/data`、`tab5/logs`、`tab5/cache`を作成する。読み取り専用ならディレクトリ作成を行わず、その状態を表示する。

これは起動時の検出・マウント処理であり、抜き差しイベントごとに自動マウントする常駐サービスではない。スクリプトの再起動後の自動実行と保存内容の保持は、今回の進行中の検証に含めて別途記録する。

## 検証と次の作業

1. 進行中の小さなファイルの書き込み・読み戻し・ハッシュ一致、同期・アンマウント・再マウント後の一致確認を完了し、ログを残す。
2. 再起動後の自動マウントと保存内容保持、メモリ使用量を確認する。
3. Wi-Fi通信と併用して、C6切断、タイムアウト、データ破損、CPU負荷と転送速度を確認する。
4. カード未挿入、マウント失敗、容量不足時の挙動と、指定保存先へのログ・データ保存を確認する。
5. exFATの実カードを使う場合、その認識・読み書き・再マウントを追加検証する。

完了したのはSPI経路・電源・カーネル・マウント処理の実装と、16GB FAT32カードの認識、読み取り専用／読み書き可能のマウント、ディレクトリ作成までである。ファイル内容の整合性と再マウント後の保持は未完了。将来の高速化はnative SDMMCの複数slot対応またはハードウェアSPI対応として検討する。

## 根拠

- [M5Stack Tab5公式Pinmap](https://docs.m5stack.com/en/core/Tab5)
- [M5Stack microSD SPI使用例](https://docs.m5stack.com/en/arduino/m5tab5/microsd)
- [Espressif Tab5 BSP storage実装](https://github.com/espressif/esp-bsp/blob/master/bsp/m5stack_tab5/src/bsp_storage.c)（調査ではローカルBSP 1.3.2を使用）
- [ESP-IDF 5.5.5 SD既定設定](https://github.com/espressif/esp-idf/blob/v5.5.5/components/esp_driver_sdmmc/include/driver/sdmmc_default_configs.h)
- [ESP-IDF 5.5.5 LDO電源制御](https://github.com/espressif/esp-idf/blob/v5.5.5/components/sdmmc/sd_pwr_ctrl/sd_pwr_ctrl_by_on_chip_ldo.c)
- リポジトリの`linux/dts/easystick-stamp-p4.dts`、`linux/boot-shim/main/m2_sdmmc.c`、`linux/kernel-patches/0009-easystick-dw-mmc-divider0.patch`
- 今回の実装：`linux/dts/tab5-microsd-spi.dtsi`、`linux/tab5/microsd-spi.config.fragment`、`linux/kernel-patches/0079-spi-gpio-honor-delay.patch`、`linux/m3-lab/rootfs-overlay/etc/init.d/S30tab5-sdcard`
- フォークCI run `39729147095`のkernel-kit内`dw_mmc.c`、`mmc_spi.c`、`of_mmc_spi.c`、`gpio-esp32p4.c`とDT binding
