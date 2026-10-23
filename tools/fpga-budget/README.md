# GPU VRAM配置・読戻し帯域の計算

このツールはPC上の算術モデルである。FPGA・Tab5・DDR3へアクセスせず、クロック、DMA、Linux/MeOS ABI、実際のメモリマップを定義しない。

```text
python tools/fpga-budget/budget.py
python tools/fpga-budget/budget.py --width 720 --height 1280 --available-readback-bps 20000000
python tools/fpga-budget/budget.py --width 321 --height 241 --readback strided
python -m unittest discover -s tools/fpga-budget -p test_budget.py -v
```

Python 3.10以降・標準ライブラリのみ。形式はRGB565 LE、depthはuint16。標準ではcolor2面、depth1面、128MiBの仮定容量、1MiB予約領域。これらは実機の利用可能容量ではなく変更可能な入力条件である。

region offsetは仮想arena先頭からの相対値。64-byte境界に配置するのはモデル内の選択で、DDR3やDMAの要求として確定した値ではない。strideは省略時にrowbytesを64-byteへ切り上げ、指定時は幅以上・2-byte整列を検査する。上流GPUのABIを置き換えない。

`readback=packed`は行の有効画素のみ返す仮定、`strided`は行パディングも転送する仮定。1フレームにつき完了したcolor1面を回収する。double bufferingだから2面を毎回回収する計算ではない。容量予算と転送予算を分けて出力する。

レートの `_bps` は **bytes/second** でありbit/sではない。`--available-readback-bps` は利用者が与える仮定の有効payload帯域で、実測値を自動取得しない。その帯域で転送だけに必要な最低時間とFPS上限を示す。payload予算が足りても、演算・待ち・CPUコピー・LCD出力込みで成立することを示さない。

640×360・stride1280の場合、color/depth各460,800 bytes、color2+depth1で1,382,400 bytes。colorを30回/s回収する有効payloadは13,824,000 bytes/s。720×1280ではそれぞれ5,529,600 bytesと55,296,000 bytes/s。配置paddingと予約領域は別途加算する。

テストは容量ぴったり／1byte不足、配置と非重複、strideとpacked/strided差、帯域境界、符号・型・極端値、depthなしを確認する。新規入力はuint64範囲に限定し、極端な値によるfloat変換の失敗も拒否する。
