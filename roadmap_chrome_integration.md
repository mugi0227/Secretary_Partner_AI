# Chrome拡張機能統合 実装ロードマップ

## Phase 1: "The Eye" of Beginnings (MVP)
まずは「ボタン一つで現在の画面をAIに送る」機能を実現し、データのパイプラインを通す。

### 1-1. Chrome Extension 基盤作成
- [ ] `chrome-extension/` ディレクトリの作成
- [ ] `manifest.json` (V3) の作成
    - 権限: `activeTab`, `scripting`, `storage`
- [ ] `popup.html/tsx`: "Capture" ボタンのUI実装
- [ ] `background.js`: スクリーンショット撮影処理 (`chrome.tabs.captureVisibleTab`)

### 1-2. 認証連携 (The Bridge)
- [ ] Frontend: ログイン時にTokenを `localStorage` 等に保存する仕組みの確認
- [ ] Chrome Ext: Webアプリの特定ドメインの `localStorage` または Cookie からTokenを読み取る処理
- [ ] 送信テスト: 拡張機能から `POST /api/captures` へToken付きでリクエストを送る

### 1-3. Backend受け入れ態勢
- [ ] `Capture` モデルに `screenshot_url`, `source_url` フィールドがあるか再確認（あればOK）
- [ ] 画像を受け取り、Gemini Vision API (Proモデル推奨) に投げて「画像の説明」を生成する処理の実装

### 1-4. Frontendでの確認
- [ ] Dashboard または TasksPage に「未処理のCapture」を表示するエリアを作成
- [ ] 送信したスクショが見れることを確認

---

## Phase 2: "The Brain" Awakens (AI解析の強化)
送った画像から「ただのメモ」ではなく「タスク」を抽出する。

### 2-1. Structured Output from Gemini
- [ ] Backend: 画像解析プロンプトを改良し、JSON形式で「タスク名」「期限」「重要度」を返させるようにする
- [ ] Pydanticモデルで出力を検証・修正する

### 2-2. "Draft" UIの実装
- [ ] Frontend: `TaskFormModal` に「Captureからの自動入力」機能を実装
    - Capture一覧から「タスク化」ボタンを押すと、モーダルが開き、AIが解析したタイトルや期限が最初から入っている状態にする

---

## Phase 3: "The Meddlesome" Secretary (コンテキスト検知)
ユーザーがボタンを押さなくても、特定のページで情報を吸い上げる。

### 3-1. Content Scripts の実装
- [ ] `content_script.js` を作成
- [ ] Gmail / Google Calendar を開いた時だけ起動するロジック
- [ ] ページのテキスト（Subject, Dateなど）をDOMから抽出する実験

### 3-2. Context APIの実装 (Backend)
- [ ] `POST /api/captures` を拡張し、スクショなしの「テキスト情報のみ」も受け入れ可能にする（処理が軽いFlashモデルで捌く用）

### 3-3. 自動提案通知
- [ ] Frontend: リアルタイム通知（Polling または Simple Toast）
- [ ] 「Gmailの内容からタスク候補が見つかりました」というUIの実装

---

## Phase 4: Reality Show (Teams/Meeting連携)
### 4-1. Live Caption Scraper
- [ ] Teams (Web版) の字幕要素のCSSセレクタを特定
- [ ] `MutationObserver` を使い、新しい字幕が出るたびにテキストを取得
- [ ] 特定のキーワード（「タスク」「お願い」「期限」）に反応してBackendへ送信

### COST CONTROL (重要)
- [ ] Phase 3以降はAPIコール数が増えるため、Backendで「1ユーザーあたりのレート制限」や「重複送信の防止（ハッシュチェック）」を実装する。
