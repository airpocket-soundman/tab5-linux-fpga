# GPUバッファ所有権のホストモデル

2026-10-23。GPU側仕様 `tab5-fpga-gpu` のコミット `147a2154112f9fe4b213567d736f2bece6e9742b`、`docs/game-gpu-spec.md` を参照する。RGB565/uint16 depthの画像範囲、色・深度領域の重複禁止、fenceでの所有権返却を、ホストの状態モデルで検証する。描画機能、実GPU対応、正式wire ABI、Linuxドライバの実装ではない。

```text
python -m unittest discover -s tools/fpga-gpu-model -p test_ownership.py -v
```

`register()` は仮想arena内の領域を登録する。整数はboolを拒否し、偶数offset、正のsize、arena境界を検査する。モデル内計算上限は64bit unsigned相当であり、ハードウェアアドレス幅の決定ではない。`submit()` はRGB565色とuint16深度に共通のwidth/height/strideを指定する。strideはrowbytes以上かつ2byte境界、最後の参照byteまで登録範囲内でなければならない。最後の行の未使用paddingは参照しない。

全引数を検証してから、二つのバッファの所有権をdeviceへ移す。同時実行は1jobに限定する。CPUのread/write/freeはdevice所有中に拒否し、別名登録した重複領域でも回避できない。不正submitは所有権とfenceを変更しない。handle/fenceはinstance内の不透明オブジェクトであり、整数番号の再構成、別session、free/reset後の古いhandleを拒否する。

状態は `pending → complete/failed/cancelled`、または `pending → uncertain → complete/failed/cancelled`。ローカルtimeoutは `uncertain` にするだけで所有権を返さない。`acknowledge()` はbackendが完了・停止を伴う失敗・キャンセル停止を確認した場合だけ呼ぶ。failed/cancelledの画像は有効な描画結果として扱わない。`reset_acknowledged()` はデバイスのアクセス停止を確認した後に呼び、全handle/fenceを無効化する。リセット要求の送信だけでこの関数を呼んではならない。

モデルは画像データを保存せず、失敗後の画像再初期化、DMAのcache同期、IRQ、物理reset、描画結果、転送時間を検証しない。アプリは成功fenceを確認して表示へ進み、失敗時には画像を再生成する必要がある。正式backendではacknowledgementの信頼性と実行停止を別途検証する。

2026-10-23、Windows/Python 3.12で8テスト成功。完了・停止失敗・キャンセル・timeout・reset、別名領域のCPUアクセス拒否、不正submitの無変更、stride末尾境界、古い／偽造／別sessionのhandleとfenceを検査した。Tab5、FPGA、GPIO、フラッシュへはアクセスしていない。
