"""Generate the public project guide and HTML from the same reviewed facts (stdlib only)."""
import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs/site'

def esc(value):
    return html.escape(value, quote=True)

def build():
    d = json.loads((ROOT / 'docs/project-status.json').read_text(encoding='utf-8'))
    refs = d['evidence']
    def link(key):
        label, url = refs[key]
        return f'<a href="{esc(url)}">{esc(label)} ↗</a>'
    sections = []
    def section(id, number, title, body):
        sections.append(f'<section id="{id}" aria-labelledby="{id}-title"><div class="section-heading"><span>{number}</span><h2 id="{id}-title">{title}</h2></div>{body}</section>')
    section('purpose','01','何を、なぜ作るのか', '<div class="purpose-grid">'+''.join(f'<article><span class="index">0{i+1}</span><h3>{esc(t)}</h3><p>{esc(v)}</p></article>' for i,(t,v) in enumerate(d['purpose']))+'</div>')
    section('architecture','02','LinuxとFPGA、それぞれの役割', '<p class="lead">OSはTab5、データ領域と演算はFPGAへ。通信ドライバが二つをつなぎます。</p><figure><img src="assets/architecture.svg" width="1120" height="450" alt="構成案。Tab5のアプリからLinux通信ドライバ、未確定の8bit PARLIOを通してTang Primer 20Kの制御回路と128MB DDR3へ接続。C6はSDIOでTab5に接続。"><figcaption>構成案：FPGAへの経路は開発目標です。接続・動作確認済みの配線図ではありません。</figcaption></figure><div class="callout"><strong>128MBは外部データ領域</strong><p>アプリが転送を要求し、FPGA側でデータを読み書きします。Linuxの通常RAMが透過的に増える構成ではありません。</p></div><figure><img src="assets/transfer.svg" width="1120" height="240" alt="転送の概念。アプリが要求し、ドライバが転送、FPGAがDDR3に保存・演算し、完了とデータを返す。プロトコルは未確定。"><figcaption>READ / WRITEの概念図。パケット形式、バッファ管理、エラー処理は今後設計します。</figcaption></figure>')
    section('specification','03','仕様と設計の前提','<div class="table-wrap"><table><caption>確認した前提と、これから固める仕様</caption><thead><tr><th scope="col">項目</th><th scope="col">内容・状態</th></tr></thead><tbody>'+''.join(f'<tr><th scope="row">{esc(k)}</th><td>{esc(v)}</td></tr>' for k,v in d['specs'])+'</tbody></table></div>')
    section('progress','04','どこまで確認できたか','<p class="lead">完了率ではなく、検証した範囲と証拠で進捗を示します。</p><div class="status-list">'+''.join(f'<article class="status-row"><span class="badge {"verified" if state=="確認済み" else "pending"}">{esc(state)}</span><div><h3>{esc(title)}</h3><p>{esc(body)}</p>{link(ref)}</div></article>' for state,title,body,ref in d['status'])+'</div><aside class="callout amber"><strong>最後に記録した実機の状態</strong><p>P4は単体ESP-IDF表示テストのまま。Linuxへは戻していません。C6はESP-Hosted-NGのままです。USB付近の発熱原因は未解決で、温度は測定していません。</p></aside>')
    section('roadmap','05','開発計画と完了条件','<p class="lead">現在はL0が進行中。日付による期限は未設定です。各段階の完了条件を満たしてから次へ進みます。</p><ol class="roadmap">'+''.join(f'<li><div class="phase">{esc(code)}</div><div><span class="phase-state">{esc(state)}</span><h3>{esc(title)}</h3><p>{esc(body)}</p></div></li>' for code,state,title,body in d['milestones'])+'</ol><p class="note">カーネル更新、SMP、FPGAドライバ追加を同時に行わず、1コア構成との差を変更ごとに確認します。ST7121の表示対応はL0の前提を整える実験です。</p>')
    section('next','06','次に行うこと','<ol class="next-list">'+''.join(f'<li>{esc(s)}</li>' for s in d['next'])+'</ol>')
    section('repositories','07','関連リポジトリの分担','<div class="repo-list">'+''.join(f'<article><h3><a href="https://github.com/airpocket-soundman/{name}">{name} ↗</a></h3><p>{esc(desc)}</p></article>' for name,desc in d['repos'])+'</div><p class="note">上流：<a href="https://github.com/Riti0208/tab5-linux">Riti0208/tab5-linux</a> → <a href="https://github.com/tsuyoshi-otake/m5stamp-p4-c6-linux">tsuyoshi-otake/m5stamp-p4-c6-linux</a>。上流の動作報告と、このフォークの検証を区別します。著作権表示とライセンスを維持します。</p>')
    section('sources','08','記録と根拠','<ul class="sources">'+''.join('<li>'+link(k)+'</li>' for k in refs)+'</ul><p class="note">公開するのは確認結果と参照先です。認証情報を含む生ログや、ローカルのビルド出力は掲載しません。実機記録にはOSコミット、FPGAビットストリーム識別子、環境、コマンド、結果、残課題を残します。</p>')
    nav=[('purpose','目的'),('architecture','構成'),('specification','仕様'),('progress','進捗'),('roadmap','計画'),('sources','資料')]
    output='''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Tab5 NOMMU LinuxとTang Primer 20Kをつなぐ開発プロジェクト。目的、仕様、構成図、検証状況、開発計画を公開しています。"><meta name="theme-color" content="#102c32"><title>Tab5 Linux × FPGA — 開発ガイド</title><link rel="icon" href="assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="assets/style.css"></head><body>
<a class="skip" href="#main">本文へ移動</a><header><a class="brand" href="#">TAB5 <span>LINUX × FPGA</span></a><nav aria-label="主要ナビゲーション">'''+''.join(f'<a href="#{id}">{label}</a>' for id,label in nav)+'''</nav></header><main id="main"><div class="hero"><div><p class="eyebrow">OPEN DEVELOPMENT / PROJECT GUIDE</p><h1>小さなLinuxから、<br>FPGAの可能性へ。</h1><p class="hero-copy">'''+esc(d['intro'])+'''</p><div class="hero-actions"><a class="button" href="#progress">開発の現在地を見る ↓</a><a class="text-link" href="https://github.com/airpocket-soundman/tab5-linux-fpga">GitHubでソースを読む ↗</a></div><p class="updated">記録更新 '''+d['updated']+''' · 実機検証と設計案を区別して公開</p></div><figure class="hero-art"><img src="assets/device.svg" width="580" height="440" alt="Tab5タブレットとFPGA基板の概念イラスト。実機写真や確定した基板設計ではありません。"><figcaption>Tab5 + Tang Primer 20K / 概念イラスト</figcaption></figure></div><div class="snapshot"><div><span>現在の段階</span><strong>L0 · 起動基準の確立</strong></div><div><span>実機で確認</span><strong>1コアLinux / 単体液晶表示</strong></div><div><span>これから検証</span><strong>Linux液晶 / FPGA通信</strong></div></div>'''+''.join(sections)+'''</main><footer><div class="brand">TAB5 <span>LINUX × FPGA</span></div><p>airpocket-soundman · 開発中の研究プロジェクト</p><a href="https://github.com/airpocket-soundman/tab5-linux-fpga/blob/main/LICENSE">ソースのライセンス</a></footer></body></html>
'''
    md=['# Tab5 Linux × FPGA — プロジェクトガイド','',f"更新日：{d['updated']}",'',d['intro'],'','## 目的','']
    for t,v in d['purpose']: md += [f'### {t}','',v,'']
    md += ['## 構成','', '![構成案](site/assets/architecture.svg)','', '図は設計構想であり、動作確認済みの配線図ではありません。','', '![転送概念](site/assets/transfer.svg)','', '## 仕様と前提','', '| 項目 | 内容・状態 |','| --- | --- |']
    md += [f'| {k} | {v} |' for k,v in d['specs']]
    md += ['', '## 開発進捗','']
    for state,title,body,ref in d['status']:
        label,url=refs[ref]
        md += [f'### {title} — {state}','',body,'',f'根拠：[{label}]({url})','']
    md += ['最後に記録した実機はP4が単体ESP-IDF表示テスト、C6がESP-Hosted-NG。Linuxには戻していません。USB付近の発熱原因・正常性は未判定です。','','## 開発計画','', '日付による期限は未設定。カーネル更新・SMP・FPGAドライバ追加は段階的に行います。','', '| 段階 | 状態 | 作業 | 完了条件 |','| --- | --- | --- | --- |']
    md += ['| '+' | '.join(row)+' |' for row in d['milestones']]
    md += ['', '## 次の作業','']+[f'{i+1}. {s}' for i,s in enumerate(d['next'])]
    md += ['', '## リポジトリの分担','']+[f'- [{name}](https://github.com/airpocket-soundman/{name})：{desc}' for name,desc in d['repos']]
    md += ['', '## 記録と根拠','']+[f'- [{label}]({url})' for label,url in refs.values()]
    md += ['', '上流の動作報告とフォークの検証を区別します。生ログ・認証情報は公開せず、実機結果にはOSコミットとFPGA識別子、環境、コマンド、結果、残課題を残します。','', '<!-- Generated by tools/build-project-docs.py. Edit docs/project-status.json. -->','']
    return {SITE/'index.html':output, ROOT/'docs/PROJECT_OVERVIEW.md':'\n'.join(md)}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true',help='Fail if generated documents are stale')
    args=parser.parse_args()
    for path, content in build().items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != content:
                raise SystemExit(f'Stale generated document: {path.relative_to(ROOT)}')
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8',newline='\n')
    print('Project documents are current.' if args.check else 'Generated Markdown and HTML project guide.')

if __name__ == '__main__':
    main()
