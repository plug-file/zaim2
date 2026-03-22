# Billion — 資産ダッシュボード

資産データを毎日自動取得し、GitHub Pagesでダッシュボード表示するツールです。

## 構成

```
docs/
├── dashboard.html             # ダッシュボード（GitHub Pages）
├── data.json                  # 資産データ（Actions が自動更新）
├── manifest.json              # PWA設定
├── sw.js                      # Service Worker
├── icon-192.png               # アプリアイコン
├── icon-512.png               # アプリアイコン（大）
└── apple-touch-icon.png       # iOS用アイコン
```

## セットアップ手順

### 1. GitHub Secrets の設定
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で必要な認証情報を登録してください。

### 2. GitHub Pages の設定
リポジトリの **Settings → Pages → Source → Deploy from a branch**
- Branch: `main`
- Folder: `/docs`

### 3. 動作確認
**Actions → Run workflow** で手動実行して確認。

## 自動実行スケジュール

毎日 **11:00 JST** に自動実行されます。
