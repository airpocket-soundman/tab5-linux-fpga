# Tab5のターミナルとエディタ

## 操作経路

Tab5本体ではLinuxのコンソールとシェルが動く。USB-Cのシリアル接続、またはWi-Fi経由のSSHから操作できる。液晶はLinuxコンソールの表示先であり、デスクトップのウィンドウ型ターミナルではない。USB-Aキーボード用のドライバは組み込み済みだが、実キーボードによる入力は未検証。

```sh
ssh m5@<Tab5のIPアドレス>
```

## 編集と保存

microSDを使用する例。最初に`/etc/init.d/S30tab5-sdcard status`でカードが読み書き可能な状態か確認する。

```sh
vim /mnt/sdcard/tab5/data/memo.txt
nano /mnt/sdcard/tab5/data/memo.txt
sl
```

- Vim: `i`で入力、`Esc`で入力を終了、`:wq`とEnterで保存して終了。保存を破棄する場合は`:q!`。
- nano: 通常どおり入力し、`Ctrl+O`、Enterで保存、`Ctrl+X`で終了。
- sl: ターミナル上でSLを表示する。`sl -l`は小さな車両を使う。

元からあるBusyBoxの`vi`も保持する。追加したVimとnanoは本物の上流ソフトを小さく構成したもので、別コマンドへの名前の付け替えではない。

## この構成での機能範囲

Vim tinyでは外部シェル実行・外部フィルタを無効にする。`:!`や`:r !`、ジョブ、内蔵ターミナル、GUI、大きなruntime一式は対象外。最小の`defaults.vim`を同梱する。nanoもtiny構成で、設定ファイル読み込みと詳細helpなどを省略する。通常の編集と保存を実機確認した。日本語の入力・表示と大きなファイルの編集は別途検証が必要。

このNOMMU Linux向けに静的bFLT形式でクロスビルドする。Debian向け実行ファイルやaptで追加する方法は使用できない。[再ビルド手順](../linux/tab5/terminal-apps/README.md)を参照する。

## 検証記録

2026-10-22、Tab5 LinuxのSSH仮想端末（xterm、80×24）で次を確認した。

| アプリ | 確認結果 |
| --- | --- |
| Vim 9.1.2148 tiny | 通常初期画面、入力、`:wq`保存・終了、microSDから内容の読み戻しに成功 |
| nano 8.2 tiny | 入力、Ctrl+OとEnterによる保存、Ctrl+X終了、microSDから内容の読み戻しに成功 |
| sl 5.02 | `sl -l`が21,591バイトの画面更新を出力し、終了コード0で復帰 |
| slの本体コンソール | TERM=linux、/dev/tty1へ出力して終了コード0。fb0 blank=0。今回の目視確認は別途 |

VimはbFLTスタック64KiBでは初期画面後にSEGVとなった。同じ実行ファイルのスタック割当だけを256KiBへ変更すると、対話編集と保存に成功した。nanoは64KiB、slは32KiB。外部シェル実行を無効化したVimパッチも維持する。

アプリ本体は内蔵フラッシュに配置した。旧Linuxのphysmapが7MiBを4MiBに切り下げていた問題を0080で修正し、実機でMTD=7,340,032bytesと5.4MB rootfsの起動を確認した。microSDは編集データの保存先として使用する。SD上のアプリを呼ぶ構成もビルドで選べるが、SD実行は未確認。

使用kernelはCI39763573194/source be09cac。アプリはCI39761292328/source0493c7a、Vimスタック調整rootfsはCI39765103193/source70be4cb。rootfs SHA256は`870371f9d86c6b42205f20fefcc4af390c7b2b25668ff9da3ef675bcc6338fff`。詳しいハッシュ・制約は[起動記録](BRINGUP_2026-10-22.md)を参照。
