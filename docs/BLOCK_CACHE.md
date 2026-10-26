# 外部RAMの小容量ブロックキャッシュ試作

更新日：2026-10-26。ホストの一時ファイルを外部データ領域に見立て、同じ小領域を繰り返し読む用途について、保存するデータ量を制限したread cacheを試作する。Tab5、FPGA、PARLIO、Linuxドライバには接続しない。

## 用途と構造

画像の小領域、索引、字形、処理中タイルのように同じデータを再利用する場合、P4側へ小さなblockを残すことで外部READ要求を省く構成を検討できる。連続一回走査では利益がなく、必要なbyte数より多いblockを先読みする場合もある。今回のモデルはこのアクセス意味を検証し、実機での高速化を判定しない。

`tools/fpga-memory/block_cache.py` の `BlockCache` はLRUで最大block数を制限する。末尾以外は固定block長、末尾は残りのbyte数だけ保存する。read結果は呼出し側が保持するimmutable bytes。writeはbackendへ直ちに渡して関連cacheを捨て、未反映のdirty dataを保持しない。

backendの `describe(handle)` がサイズ・revisionを返し、毎回のread/writeで寿命とrevisionを確認する。backendを直接write/copyしてもrevision変化で古いblockを捨てる。revisionは検証済みwriteの実行前に進み、途中で短いwriteやI/O例外になった場合も古いcacheを有効と扱わない。free、別instanceのhandle、close後はcache hitだけで読出しを成立させない。

このrevisionはホストAPIの内部契約であり、FPGAの正式ABI・wire要求ID・DDR整合性機構ではない。単一スレッドの同期実行を想定し、別スレッドや外部デバイスが処理中に領域を更新する場合の一貫性は保証しない。

## 再現する比較

```text
python tools/fpga-memory/cache_demo.py --mock
python -m unittest discover -s tools/fpga-memory -p test_block_cache.py -v
```

demoは65,539 bytesのobjectを用意し、全体addressに依存する同一データをdirect読出しとcache読出しにそれぞれ保存する。4個のwindowを16回読み、毎回のbyte列と連結したSHA-256を比較する。blockは256 bytes、保持上限8個、backendの単一転送上限4,096 bytes。処理時間は計測しない。

2026-10-26、Windows/Python 3.12でdemoを実行し、以下を確認した。

| 項目 | cacheなし | cacheあり |
| --- | --- | --- |
| アプリのwindow要求 | 64回 | 64回 |
| アプリへ返したデータ | 5,024 bytes | 5,024 bytes |
| backend READ要求 | 64回 | 5回 |
| backend READデータ | 5,024 bytes | 1,027 bytes |
| 初回4windowのbackend要求 | 4回 | 5回 |
| 残り15回分のbackend要求 | 60回 | 0回 |

両結果のSHA-256は `7362a15d59ba012132c5fa55600cd9c9826a046e622731f408a3e818dcf1f789`。cacheは初回にblock境界を跨ぐため要求が増え、その後の再利用で省けることを示す。この要求数の差は選んだアクセス列だけの結果であり、FPGA帯域、CPU負荷、処理時間の改善率ではない。

## メモリ量と今後

保持payloadの上限は256×8＝2,048 bytesで、demo末尾では5block・1,027 bytesを保持した。この値はプロセスRAM使用量ではない。Pythonのキー・handle・LRUメタデータ、一時的なbackend読出し、read結果の組立てとbytesへの変換、呼出し側が保持する返却値が別途必要になる。NOMMU Linuxで使う際にはC実装のbuffer寿命と実メモリ使用量を測定する必要がある。

次は異なるアクセス列でhit/missと過剰読出しを比較し、再利用が乏しい場合は直接転送を選べるようにする。実backendへ接続する前に、外部更新の通知、reset時の全無効化、部分write失敗時の復旧を正式に定義する。主記憶や透過的なmalloc領域を増やす機構ではない。

## 開発・確認記録

基準コミットは `c1cd5e4`。Windows / Python3.12で、cache12件、revision5件、既存memory14件・bFLT2件の合計33テストが成功した。キャッシュの500操作の固定seed試験では、cache経由／backend直接の書込みと読出しを独立したbytearrayへ照合した。

revisionは型・範囲・転送上限の検査後、ファイル書込みを試みる前に更新する。失敗で一部のデータだけ変わっていても旧cacheが無効になる。readではrevisionを進めない。describe結果はコピーしたmetadataであり、呼出し側が変更してもbackendに影響しない。free/closeで寿命管理を破棄する。

不正要求によってcache統計やbackend I/Oが増えないこと、LRU順、末尾block、短い／失敗read、copy先更新、clear/invalidate、free・close・別instanceの拒否も確認した。返却値はimmutable bytesで、cache内payloadは設定容量以内。プロセスRAM最大値を測定したものではない。

本作業はこのLinuxリポジトリ内の追加のみ。MeOSや実機へアクセスしていない。次は実backendの能力照会・完了通知・同時書込みの扱いを定義し、必要に応じてC版へ移植する。backendがrevisionを適切に管理できない状態で、このcacheを実DDR3へ接続しない。
