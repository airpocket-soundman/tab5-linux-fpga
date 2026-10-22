# Tab5 単体液晶テスト（ESP-IDF、Linux不使用）

ESP-IDF 5.5.5とEspressifのM5Stack Tab5 BSP 1.3.2を使用する。
BSPがタッチコントローラから液晶リビジョンを判別し、ST7121、ST7123、ILI9881Cの初期化を選択する。

画面上部にRGBの帯、下部に白い帯、中央に左右へ動く黄色い四角と点滅する四角を表示する。
バックライトは30%。アプリはWi-Fi、C6との通信、FPGA、カメラ、音声を開始しない。

ESP-IDF環境でこのディレクトリから実行する：

```sh
idf.py set-target esp32p4
idf.py build
idf.py -p COM22 flash monitor
```

ESP32-P4 revision v1.x向け設定を使用する。ポート番号は実機に合わせる。
書き込みは既存P4ファームウェアを置換する。C6ファームウェアはこのプロジェクトから書き換えない。
Linuxのフラッシュ配置とは異なるため、Linuxに戻すときは保存済みのLinux全体イメージを書き込む。

今回のホストではPlatformIO配布のESP-IDF 5.5.5、対応GCC 14.2.0、Python環境 `D:/tmp/tab5-idf-env` を使用し、出力先を `build-p4` とした。
生成された `flasher_args.json` に書き込みアドレスと対象ファイルを記録する。

起動確認と実際の表示確認は別に記録する。発熱の正常性は本テストだけでは判定できない。

2026-10-22：P4 revision v1.3、ST7121（タッチFW=1）の実機へ書き込み、720x1280の初期化とアニメーション更新ログを確認。ユーザーによる画面表示の目視確認済み。詳細は `../../docs/BRINGUP_2026-10-22.md`。
