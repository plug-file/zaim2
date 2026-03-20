# zaim2 — 資産ダッシュボード

Zaimの資産データを毎日自動取得し、GitHub Pagesでダッシュボード表示するツールです。

## 構成

```
zaim2/
├── zaim.py                        # データ取得・JSON生成スクリプト
├── requirements.txt               # Python依存ライブラリ
├── .github/workflows/update.yml  # GitHub Actions（毎日自動実行）
└── docs/
    ├── dashboard.html             # ダッシュボード（GitHub Pages）
    └── data.json                  # 資産データ（Actions が自動更新）
```

## セットアップ手順

### 1. リポジトリ作成
このリポジトリを GitHub に push します。

### 2. GitHub Secrets の設定
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で以下を登録：

| Secret名 | 内容 |
|---|---|
| `ZAIM_EMAIL` | Zaim のログインメールアドレス |
| `ZAIM_PASSWORD` | Zaim のログインパスワード |
| `GCP_JSON_KEY` | GCPサービスアカウントのJSONキー（文字列全体） |
| `SPREADSHEET_URL` | Google スプレッドシートのURL |
| `BITBANK_API_KEY` | bitbank の APIキー（不要なら空でも可） |
| `BITBANK_SECRET` | bitbank の APIシークレット（不要なら空でも可） |

### 3. GitHub Pages の設定
リポジトリの **Settings → Pages → Source → Deploy from a branch**
- Branch: `main`
- Folder: `/docs`

保存後、数分で `https://<ユーザー名>.github.io/zaim2/dashboard.html` で公開されます。

### 4. 動作確認
**Actions → Update Asset Dashboard → Run workflow** で手動実行して確認。

## 自動実行スケジュール

毎日 **11:00 JST** に自動実行されます。
変更する場合は `.github/workflows/update.yml` の cron 式を編集してください。

```yaml
- cron: '0 2 * * *'  # UTC 2:00 = JST 11:00
```

## ダッシュボード URL

```
https://<ユーザー名>.github.io/zaim2/dashboard.html
```
