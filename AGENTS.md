# 開発の入口

作業前に [開発目的と引き継ぎ](docs/DEVELOPMENT_GOALS.md) と対象ディレクトリの説明を読む。

- このリポジトリはTab5 Linux本体とFPGA通信ドライバを担当する。FPGA回路・研究評価は関連研究リポジトリで管理する。
- 上流の動作報告と、このフォークでの実機検証を区別する。未検証のGPIO、PARLIO DMA、SMP、液晶を動作済みと記載しない。
- 起動基準は現状の1コア構成とし、上流更新と独自ドライバを段階的に検証する。
- ハードウェア変更前にキャリア側の共通仕様を照合する。FPGA DDR3を透過的なメインRAM増設として扱わない。
- 作業終了時に実施内容、確認結果、未解決事項、次の作業を記録する。
- GitHubリポジトリのローカル配置は所有者に合わせる。airpocket-soundman配下は `D:\github\airpocket-soundman`、Factory-IoT配下は `D:\github\Factory-IoT` を使用する。
