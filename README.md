※本READMEは主にAIによって記述されています。

# nagi

**自律型秘書AI** - タスク管理を自律的にサポートし、ユーザーを支えるパートナー的存在

## 概要

nagiは、指示待ちではなく、自らの判断でユーザーを管理・支援する「自律型エージェント」です。音声・テキスト・画像による自然な対話でタスクを自動整理し、最適な行動を提案します。

### コアコンセプト

- **Autonomous Secretary**: タスクの分解・整理・優先順位付けを自律的に実行
- **Natural Input**: 思いついたことをそのまま投げ込める、心理的ハードルゼロの入力
- **Hybrid Operation**: チャットによる自然言語操作と、GUIによる直接操作の両立

## 主な機能

### タスク管理

- **2軸優先度**: 重要度 x 緊急度のマトリクスで自動優先順位付け
- **エネルギーレベル**: タスクの実行難易度(HIGH/LOW)を考慮した提案
- **Top3推薦**: AIが今日やるべきタスクTop3を自動選定
- **自動タスク分解**: 大きなタスクを3-5個のステップに分割し、各ステップに進め方ガイドを付与
- **タスク依存関係**: 前後関係やブロッカーを管理
- **繰り返しタスク**: テンプレートからの自動生成

### プロジェクト管理

- **プロジェクト単位の整理**: タスク・フェーズ・マイルストーンでの階層管理
- **KPI管理**: 売上・開発・運用などのKPIテンプレートとカスタム指標
- **コンテキスト保持**: プロジェクトごとの目標・重要ポイント・READMEを記憶・活用
- **ガントチャート / カンバンボード**: ビジュアルなプロジェクト進捗管理
- **メンバー管理**: 招待制のチームコラボレーション (OWNER / MANAGER / MEMBER)

### ミーティング管理

- **定例会議**: 繰り返しパターン付きのミーティング管理
- **アジェンダ管理**: 議題の作成・タスク紐付け・タスク化ラップアップ
- **ミーティングセッション**: 録音・文字起こし・議事録生成
- **カレンダー表示**: 週次/月次のスケジュール一覧

### スケジュール管理

- **デイリースケジュール**: タイムブロックでの作業計画
- **フォーカス設定**: 今日集中したいテーマ・避けたい作業を指定
- **スケジュールスナップショット**: 日別のスケジュール保存・復元
- **延期/今日やる**: ワンタップでのタスクリスケジュール

### チーム連携

- **構造化チェックイン**: ブロッカー/相談/進捗/リクエストのカテゴリ付き報告
- **チェックイン集約**: AIによる週次サマリー自動生成
- **リアルタイム同期**: WebSocketによるチーム間のライブ更新
- **通知**: アプリ内通知・未読管理

### AI対話

- **マルチモーダル入力**: テキスト・音声・画像・PDFに対応
- **ストリーミング応答**: リアルタイムのAI応答表示
- **承認ワークフロー**: AIの提案をユーザーが確認してから実行
- **フォローアップ質問**: インタラクティブなフォーム形式での確認
- **コンテキスト記憶**: ユーザー特性・プロジェクト背景・作業手順を記憶
- **モデル選択**: 実行時にLLMモデルを切り替え可能

### メモリ (知識ベース)

- **ユーザーメモリ**: 個人の特性・好み・行動パターンを学習
- **プロジェクトメモリ**: 案件固有の文脈・決定事項・SOPを蓄積
- **仕事メモリ (Skills)**: 再利用可能な作業手順・自動化パターンを保存
- **セマンティック検索**: メモリ全体の横断検索

### ブラウザ自動化 (Chrome拡張)

- **ブラウザエージェント**: AIによるWebページ操作の自動実行
- **ハイブリッドRPA**: 確定的ステップ + AI判断フォールバック
- **ワークフロー録画**: 手動操作を録画し、再利用可能なスキルに変換
- **チャットからの委任**: 会話の流れでブラウザ操作を自動委任

### ネイティブアプリ (Windows)

- **Push-to-Talk**: F8キーで音声入力 (グローバルホットキー)
- **フローティングUI**: 常駐ミニウィンドウでの音声入力・応答確認
- **HUDオーバーレイ**: 録音・変換・プレビュー状態の表示
- **ワンタイムコード認証**: Webアプリとのシームレスな連携

### 実績 & 進捗

- **アチーブメント**: 個人・プロジェクト単位の達成記録
- **スキル経験値**: タスク完了に基づくスキル成長の追跡
- **共有リンク**: アチーブメントの外部共有
- **週次プログレス**: ビジュアルな進捗チャート

### ダッシュボード

- **デイリーブリーフィング**: AIによる今日のサマリー
- **Today's Top3**: 今日の最優先タスク
- **スケジュール概要**: 今日のタイムライン
- **週次進捗チャート**: 完了タスクのトレンド
- **ダーク/ライトモード**: テーマ切り替え

## 技術スタック

### Backend
| 技術 | 用途 |
|------|------|
| FastAPI (Python 3.11+) | Webフレームワーク |
| Google ADK | エージェントフレームワーク |
| Gemini 3 Pro/Flash | メインLLM |
| LiteLLM | マルチLLMプロバイダー (Claude, GPT等) |
| SQLite / Firestore | データベース (Local / GCP) |
| APScheduler | バックグラウンドジョブ |

### Frontend
| 技術 | 用途 |
|------|------|
| React 19 + TypeScript | UIフレームワーク |
| Vite | ビルドツール |
| React Router v7 | ルーティング |
| TanStack Query | データフェッチ・キャッシュ |
| Framer Motion | アニメーション |
| Luxon | 日時処理 (タイムゾーン対応) |

### Architecture
- **Clean Architecture + Repository Pattern**: インフラ層の抽象化
- **環境切り替え**: `ENVIRONMENT` 変数でLocal/GCPを切り替え
- **リアルタイム**: WebSocketによるライブ通知

## プロジェクト構造

```
nagi/
├── backend/                    # FastAPI Backend
│   ├── app/
│   │   ├── api/               # APIエンドポイント
│   │   ├── agents/            # ADKエージェント定義
│   │   ├── services/          # ビジネスロジック
│   │   ├── tools/             # エージェントツール (Function Calling)
│   │   ├── models/            # Pydanticスキーマ
│   │   ├── interfaces/        # 抽象インターフェース
│   │   ├── infrastructure/    # 実装 (local/ , gcp/)
│   │   └── core/             # 設定・例外
│   ├── tests/                 # テスト
│   └── main.py
│
├── frontend/                  # React Frontend
│   └── src/
│       ├── api/              # APIクライアント
│       ├── components/       # UIコンポーネント
│       ├── pages/            # ページ
│       ├── hooks/            # カスタムフック
│       └── styles/           # グローバルCSS
│
├── chrome_extension/          # Chrome拡張 (ブラウザ自動化)
├── native/                    # Windowsネイティブアプリ (PTT)
└── CLAUDE.md                 # 開発ガイド
```

## セットアップ

### 必要な環境
- Python 3.11+
- Node.js 18+
- Git

### 1. クローン

```bash
git clone <repository-url>
cd Secretary_Partner_AI
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env
```

`.env` の必須項目:

```env
ENVIRONMENT=local
LLM_PROVIDER=gemini-api
GOOGLE_API_KEY=your_api_key_here   # https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. 起動

```bash
# Backend (ターミナル1)
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Frontend (ターミナル2)
cd frontend && npm run dev
```

http://localhost:5173 でアクセスできます。

## 環境変数

### 基本設定

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `ENVIRONMENT` | 実行環境 | `local` |
| `LLM_PROVIDER` | LLMプロバイダー (`gemini-api` / `litellm` / `vertex-ai`) | `gemini-api` |
| `GOOGLE_API_KEY` | Gemini API Key | - |
| `GEMINI_MODEL` | Geminiモデル | `gemini-2.5-flash` |
| `HOST` / `PORT` | サーバー | `0.0.0.0` / `8080` |
| `ALLOWED_ORIGINS` | CORS許可オリジン | `["http://localhost:5173"]` |

### LLMプロバイダー

| プロバイダー | 変数 | 用途 |
|-------------|------|------|
| **gemini-api** (推奨) | `GOOGLE_API_KEY` | 最も簡単。Gemini APIを直接利用 |
| **litellm** | `LITELLM_MODEL`, AWS/OpenAI認証情報 | Bedrock (Claude), GPT等 |
| **vertex-ai** | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` | GCP本番環境向け |

## 開発

```bash
# Backend
uvicorn main:app --reload          # 開発サーバー
pytest                              # テスト
pytest -m e2e                       # E2Eテスト (実APIコール)
pytest --cov=app                    # カバレッジ
ruff check app/                     # Linter
adk web                             # ADK Web UI (エージェントデバッグ)

# Frontend
npm run dev                         # 開発サーバー
npm run build                       # ビルド
npm run lint                        # Lint
```

### テスト戦略

| レベル | 手法 | 対象 |
|--------|------|------|
| Unit | モック | ビジネスロジック |
| Integration | SQLite in-memory | リポジトリ層 |
| E2E | 実APIコール | エージェントフロー |

AI機能のテストでは実際のAPIを使用します（モックなし）。

## APIドキュメント

起動後、以下で確認:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

### 主要エンドポイント

| カテゴリ | エンドポイント | 説明 |
|---------|---------------|------|
| 対話 | `POST /api/chat` | メインの対話 (テキスト・音声・画像) |
| タスク | `GET/POST/PATCH/DELETE /api/tasks` | タスクCRUD |
| タスク分解 | `POST /api/tasks/{id}/breakdown` | AIによるタスク分解 |
| Today | `GET /api/today/top3` | 今日のTop3 |
| プロジェクト | `GET/POST /api/projects` | プロジェクト管理 |
| フェーズ | `/api/phases/*` | フェーズ管理 |
| ミーティング | `/api/recurring-meetings/*` | 定例会議管理 |
| アジェンダ | `/api/meeting-agendas/*` | アジェンダ管理 |
| メモリ | `/api/memories/*` | メモリCRUD・検索 |
| 実績 | `/api/achievements/*` | アチーブメント |
| 通知 | `/api/notifications/*` | 通知管理 |
| リアルタイム | `/api/realtime/ws` | WebSocket接続 |

## トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| `ModuleNotFoundError` | `pip install -e ".[dev]"` で再インストール |
| `GOOGLE_API_KEY is not set` | `.env` にAPIキーを設定 ([取得先](https://aistudio.google.com/apikey)) |
| `Cannot connect to backend` | Backend起動確認: http://localhost:8080/docs |
| `CORS Error` | `.env` の `ALLOWED_ORIGINS` にフロントエンドURLを追加 |
| タスクが表示されない | `rm backend/secretary.db` でDB初期化後、再起動 |

## デプロイ

GCP / AWS EC2 へのデプロイ手順は `DEPLOYMENT.md` を参照。

```bash
# 環境切り替え
ENVIRONMENT=gcp
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

## 開発ガイドライン

詳細は `CLAUDE.md` を参照。

- **Clean Architecture**: インフラ層を抽象化し、テスタビリティを確保
- **KISS**: シンプルな実装を優先
- **TDD**: テストファースト
- **Pydanticバリデーション**: LLM出力は必ず検証、エラー時はリトライ

---

