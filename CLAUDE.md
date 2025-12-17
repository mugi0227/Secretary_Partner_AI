# Secretary Partner AI - Development Guide

## Project Overview
ADHD向け自律型秘書AI「Brain Dump Partner」のバックエンド。
ユーザーの「脳内多動」を受け止め、タスク管理を自律的にサポートする。

## Architecture
Clean Architecture + Repository Pattern
- GCP環境とLocal環境を`ENVIRONMENT`変数で切り替え可能
- すべての外部依存はインターフェースで抽象化

## Directory Structure
```
backend/
├── app/
│   ├── api/           # FastAPI Routers
│   ├── core/          # Config, Logger, Exceptions
│   ├── models/        # Pydantic Schemas
│   ├── services/      # Business Logic
│   ├── agents/        # ADK Agents
│   ├── tools/         # Agent Tools
│   ├── interfaces/    # Abstract Interfaces
│   └── infrastructure/
│       ├── gcp/       # GCP implementations
│       └── local/     # Local implementations
└── tests/
```

## Development Commands
```bash
# 仮想環境作成 & 依存インストール
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# 開発サーバー起動
uvicorn main:app --reload

# テスト実行
pytest                  # 全テスト
pytest -m e2e          # E2Eのみ（実APIコール）
pytest --cov=app       # カバレッジ付き

# ADK Web UI（エージェントテスト用）
adk web
```

## Environment Variables
`.env.example` を `.env` にコピーして設定：

**基本設定**
- `ENVIRONMENT`: "local" or "gcp"
- `LLM_PROVIDER`: "gemini-api" (推奨), "vertex-ai" (GCPのみ), "litellm"

**Gemini API (手軽、推奨)**
- `GOOGLE_API_KEY`: [Google AI Studio](https://aistudio.google.com/apikey)から取得
- `GEMINI_MODEL`: "gemini-2.0-flash" (デフォルト)

**Vertex AI (GCP環境)**
- `GOOGLE_CLOUD_PROJECT`: GCPプロジェクトID
- `GOOGLE_APPLICATION_CREDENTIALS`: サービスアカウントJSONのパス
- `GEMINI_MODEL`: "gemini-2.0-flash" (デフォルト)

**LiteLLM (Bedrock等)**
- `LITELLM_MODEL`: "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
- AWS認証情報またはOPENAI_API_KEY等

## Infrastructure Switching Guide
各種インフラをGCP以外に変更する手順は `docs/INFRASTRUCTURE_SWITCHING.md` に記載。
新しいプロバイダーを追加した場合は必ず追記すること。

## Progress Tracking
タスク完了後は計画ファイルのチェックボックスを更新すること：
`C:\Users\shuhe\.claude\plans\woolly-bubbling-hopcroft.md`

## Testing Strategy
1. **Unit Tests**: モック使用、ビジネスロジック検証
2. **Integration Tests**: SQLite in-memory、リポジトリ検証
3. **E2E Tests**: 実APIコール、エージェントフロー検証

AI機能のテストではモックを使用せず、実際のAPIを呼び出すこと。

## Key Conventions
- TDD: テストを先に書いてから実装
- インターフェース優先: 実装前に必ずインターフェースを定義
- Pydanticバリデーション: LLM出力は必ずPydanticで検証、失敗時は最大2回リトライ
- 重複チェック: タスク作成前に必ず類似タスクをチェック

## Code Quality Principles

### KISS (Keep It Simple, Stupid)
- シンプルな実装を優先する
- 過度な抽象化を避ける
- 必要になるまで複雑な機能を追加しない (YAGNI)

### 単一責任原則 (SRP)
- 各クラス・関数は1つの責任のみを持つ
- 変更理由が複数ある場合は分割を検討
- サービス層は1つのドメイン操作に集中

### コードの長さ制限
- **関数**: 最大50行を目安（超える場合は分割）
- **クラス**: 最大200行を目安
- **ファイル**: 最大400行を目安
- 長くなる場合は責任を分割して複数ファイルに
