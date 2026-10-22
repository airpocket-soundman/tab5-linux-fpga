# 公開ドキュメントの更新と運用

公開先：https://airpocket-soundman.github.io/tab5-linux-fpga/

## ファイルの役割

- `DEVELOPMENT_GOALS.md`：開発の目的、制約、段階、引き継ぎの方針。
- `project-status.json`：公開用の目的・仕様・進捗・計画・根拠の共通データ。
- `PROJECT_OVERVIEW.md`：生成したMarkdownの全体ガイド。
- `site/index.html`：同じデータから生成した公開HTML。
- `site/assets/`：外部依存のないCSSと、編集可能なSVGの概念イラスト。
- `BRINGUP_2026-10-22.md`：当日の検証記録。時系列で記載し、後段の結果を優先する。

## 更新手順

1. 根拠となる実機記録やCIのURL・対象コミットを確認する。
2. `docs/project-status.json` の該当箇所と更新日を変更する。目的や完了条件が変わった場合は `DEVELOPMENT_GOALS.md` も更新する。
3. リポジトリのルートで `python tools/build-project-docs.py` を実行する。Python 3の標準ライブラリのみを使う。
4. `python tools/build-project-docs.py --check` で生成物の一致を確認する。
5. HTMLをローカルで開き、文章、図、狭い画面の表示を確認する。必要なら `python -m http.server 8765 --directory docs/site` でプレビューする。
6. 共通データ、生成したMarkdownとHTML、必要な図をまとめてコミットする。

mainの対象ファイル更新で `project-pages` がGitHub Pagesへ自動公開する。PRでは生成物確認と成果物作成までで公開はしない。Pages設定はGitHub Actionsを利用する。
公開対象は `docs/site/` のみ。生ログ、認証情報、`out/` はアップロードしない。

このページは記録更新時点のスナップショットであり、実機やCI状態をリアルタイム取得しない。自動の進捗率や推定納期は掲載しない。新しい実装・検証に合わせて共通データを更新する。

## 2026-10-22 公開整備記録

- 実施内容：目的、仕様案、構成図、転送図、検証状態、L0〜L4の完了条件、関連リポジトリの分担を公開ガイドに統合した。
- 対象：mainの `519c095` を基準とし、実験ブランチの `6a2cf3d` と実機記録、CI成功を参照。実験コード自体はこの文書変更に含めない。
- 確認環境：Windows / Python 3.12。ハードウェアへの操作は行っていない。
- 確認結果：MarkdownとHTMLの生成一致、ページ内リンクとローカル画像の存在、SVGのXML構文検査が成功。ブラウザでPC表示、構成図、390px幅のレイアウトを確認。公開結果はGitHub Actionsの `project-pages` とGitHub Pagesのdeployment履歴に残す。
- 残課題：Linux ST7121実機表示、発熱の原因、L0残項目、FPGA通信は未完了。
- 次の作業：Linux調査の再開時に実機で検証し、その証拠を共通データへ反映する。
