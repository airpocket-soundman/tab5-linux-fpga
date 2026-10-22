# Tab5のネットワークと追加ストレージ

## ネットワーク

対象はこのフォークの`m3-lab`構成。USBシリアルまたは液晶のrootシェルから操作する。
2026-10-22、このフォークで実ルーターへのSTA接続、設定のフラッシュ保存と再起動後の再接続、PCからm5ユーザーへのSSH鍵認証ログインを確認した。SSHクライアント/サーバーのlocalhost接続も確認済み。接続先ごとの設定・認証は必要。

```sh
tab5-wifi status
tab5-wifi sta
```

`sta`はSSID、Wi-Fiパスワード、国コードを順に対話入力する。日本では国コードに`JP`を入力する。
パスワード入力は画面に表示しない。空欄は暗号化なしのネットワークを指定する。
現行設定処理の制約に合わせ、SSID・パスワードの引用符とバックスラッシュは受け付けない。
ESP32-C6の2.4 GHzに対応するアクセスポイントを使用する。

設定は`/boot/config.txt`の既存Wi-Fi項目を置換して保存する。USBストレージ機能を使わない
Tab5でも、`easystick-bootsync`が約3秒の更新停止後にフラッシュへ保存し、接続を切り替える。
切り替え中はSSH接続が切れることがある。ログの`Saved to flash`を確認する。
`Staged for the next reboot`の場合はソフト再起動で保存する仕組みで、自動再起動することがある。
保存完了前に電源を切らない。

```sh
tab5-wifi ap
```

これで保存済みのAP設定に戻す。`sta`は`/boot/wpa_supplicant.conf`を書き換えないため、
生成済みAPのSSID・パスワードを再利用する。AP設定ファイルを別途変更した場合は先に復元する。
認証情報は`/boot/credentials.txt`にあるため、公開ログやリポジトリへコピーしない。

## SSH

サーバーはDropbearがTCP/22で待ち受ける。PCからは`ssh m5@<Tab5のIPアドレス>`で接続し、
初回生成された`m5`のパスワードを使用する。rootでのSSHログインは無効。
公開鍵認証は`/boot/authorized_keys`へクライアント公開鍵を置くと保存・適用される。
現在のサーバーホスト鍵は起動ごとに変わるため、再接続時の鍵確認にはその点を考慮する。

Tab5側にも`ssh`、`dbclient`、`scp`を搭載する。`ssh user@host`で他機器へ接続できる。
PC側の新しい`scp`でSFTPサーバーが見つからない場合は、`scp -O`で従来のSCP転送を使用する。
`S03loopback`がlocalhost用の`lo`を起動する。外部とのSSH疎通は別に実機検証する。

## アプリの追加

現在のOSはBuildrootによるRV32IMAC・NOMMU・bFLT構成で、読み取り専用のSquashFSを使う。
Debian系の`apt`で通常の`.deb`を追加する構成ではない。microSDの増設でも実行形式の制約は変わらない。
必要なアプリは対応するBuildrootツールチェーンで作り、rootfsまたは追加ストレージへ配置する。

## microSDのマウント

実験用SPI対応イメージでは、起動時の`S30tab5-sdcard`が最大10秒待ち、既存のFAT/exFATを
`/mnt/sdcard`へマウントする。第1パーティションがある場合はそれを優先する。
フォーマットやパーティション変更は行わない。カードが未初期化の場合はマウント失敗として扱う。

カードの種類が`SD`で容量があり、対応するブロックデバイスが存在することを確認する。
Linuxが`removable=0`と報告しても、sysfsでTab5の`spi-microsd`コントローラー配下と確認できる
SDカードは対象とする。C6のSDIO機器、eMMC、フラッシュMTDは対象にしない。

```sh
/etc/init.d/S30tab5-sdcard status
/etc/init.d/S30tab5-sdcard start
```

読み書き可能な実マウントを確認した後だけ、`tab5/data`・`tab5/logs`・`tab5/cache`をカード内に
作成する。ユーザー・グループは1000、マスクは0022、アクセス時刻の更新は無効。
読み取り専用の場合やマウント失敗時にはこれらの保存先を作らず、RAMへの代替保存もしない。
停止時は`/etc/init.d/S30tab5-sdcard stop`を実行する。使用中の場合は強制アンマウントしない。
