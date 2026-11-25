# 求人ウォッチ(ブラウザ確認ページ) — 設置手順

決めた検索条件に合う新着を、毎朝7:30に自動チェックして
**ブラウザで見られるページ(GitHub Pages)** に公開する仕組みです。
GitHub Actions の無料枠で動き、サーバーも Secrets の登録も不要です。

## 仕組み

```
毎日7:30(日本時間)に GitHub Actions が起動
  → sources.yaml のRSSフィードを取得
  → キーワードでフィルタ & state.json(既読)と照合
  → 新着に NEW バッジを付けた確認ページ(site/index.html)を生成
  → GitHub Pages に公開 & state.json をリポジトリに保存
```

スマホ・PCのブラウザで開くだけで新着が分かります(LINEのような通知は届きません。
見に行くスタイルです)。

## セットアップ(約10分)

1. **GitHubアカウントを作る**(未登録の場合)— https://github.com/signup
   でユーザー名・メールアドレス・パスワードを登録(無料)。

2. **リポジトリを作る** — このフォルダの中身を GitHub の**公開リポジトリ(Public)**
   にアップします。※ Pages を無料で使うには公開リポジトリが必要です。
   この仕組みはパスワード等の秘密情報を含まないため、公開して問題ない作りに
   なっています(載るのはニュース・求人へのリンクだけです)。

3. **Workflow の書き込み権限を許可** — 「Settings → Actions → General →
   Workflow permissions」で **Read and write permissions** を選択
   (state.json の保存に必要)。

4. **GitHub Pages を有効化** — 「Settings → Pages → Build and deployment →
   Source」で **GitHub Actions** を選択。

4. **試す** — 「Actions → job-watch → Run workflow」を押して手動実行。
   完了後、ページURLは「Settings → Pages」の上部に表示されます
   (`https://<あなたのユーザー名>.github.io/<リポジトリ名>/`)。
   ※ プライベートリポジトリで Pages を見るには Free プランでは公開範囲が
   パブリックになる点に注意(求人リンクだけのページなので問題は少ないですが、
   気になる場合は公開リポジトリ+Secretsなしが前提のこの構成のままで問題ありません)。

5. **毎朝の習慣** — ページをブックマークするか、スマホのホーム画面に追加。
   新着ゼロの日も「新着はありません — 監視は正常に動いています」と出るので、
   仕組みが生きているかも一目で分かります。

## 条件を変えるには

`sources.yaml` を編集してコミットするだけです。

- キーワードの追加・除外(`include_keywords` / `exclude_keywords`)
- 監視フィードの追加(`sources:` にURLを1行)
- 新着として記録する件数の上限(`max_items_per_run`)

## ローカルでテストするには

```bash
pip install -r requirements.txt
python job_watch.py     # site/index.html が生成されるのでブラウザで開く
```

## 注意

多くの求人サイトはRSSを公開していません。この仕組みは「RSSで取れる新着」を確実に
拾うもので、タウンワーク等のサイト全体を監視するものではありません。
サイト横断の網羅には各サイトのメールアラートを併用してください。

## ファイル一覧

| ファイル | 役割 |
|---|---|
| `.github/workflows/job-watch.yml` | 毎日7:30(JST)に自動実行+Pages公開の定義 |
| `job_watch.py` | フィード取得・フィルタ・ページ生成の本体 |
| `sources.yaml` | キーワードと監視フィードの設定 |
| `state.json` | 既読リストと履歴(自動更新。手で書き換えない) |
