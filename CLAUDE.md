# nagi - Development Guide

## Build & Verification
- Always use `npm run build` (not `tsc`) to check for build errors in this project.
- Verify you're in the correct project directory (Secretary_Partner_AI) before running commands.

## Project Overview
自律型秘書AI「nagi」のバックエンド。
タスク管理を自律的にサポートし、ユーザーを支えるパートナー的存在。

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

## UI/UX Design Principles

### AI生成ボタンの方針
**重要**: AIで何かを生成する系のボタンは、即実行ではなく「チャットへのプロンプト自動入力」とする。

**理由**
- 壁打ちできる（「やっぱ3つにまとめて」など調整可能）
- 途中で気が変わっても柔軟に対応
- やり直しやすい
- 思考の流れを中断しない

**実装パターン**
```
[生成ボタン] 押下
    ↓
新規チャット画面を開き、メッセージ欄にプロンプトを自動入力
（例: 「フェーズ『設計』からタスクを作成して。担当者は適切に割り当てて」）
    ↓
ユーザーが確認・編集して送信
    ↓
AIが対話的に処理
```

**対象例**
- フェーズからタスク作成
- プロジェクト概要からフェーズ分解
- タスクの自動分割
- その他、AIが判断を伴う生成処理全般

**担当者の自動割り当て**
- メンバーが1人のプロジェクトでは、AIが自動で割り当てる
- 複数人の場合は、AIがコンテキストから適切に判断または確認

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
## Timezone Policy
- Backend is UTC-first: store timestamps in UTC and run backend internal time calculations in UTC.
- Frontend is timezone-aware: render and interpret date/time values in the user's timezone.
- Use shared frontend date/time helpers for parsing and formatting; avoid ad-hoc `new Date(...)` timezone logic.
- Timezone resolution order is:
  1. `currentUser.timezone` (server-saved user preference)
  2. Browser timezone from `Intl.DateTimeFormat().resolvedOptions().timeZone` when user timezone is unset
- `all_day` tasks are fixed to the user's local day boundary (`00:00` to `23:59`) and converted to UTC for persistence.


## Frontend Routing Policy
- プロジェクト詳細ページは `ProjectDetailV2Page` (`/projects/:projectId/v2`) を使用する。旧 `ProjectDetailPage` は削除済み。
- `/projects/:projectId` へのアクセスは `/projects/:projectId/v2` にリダイレクトされる。
- プロジェクト詳細へのナビゲーションは常に `/projects/${id}/v2` を指定すること。

## Prompt Layering Policy
- Keep `secretary_core_prompt` minimal: principles, safety, tone, and output rules only.
- Do not add use-case specific procedures (e.g. exact task/project/meeting operation flows) to core.
- Put use-case specific procedures in skill prompts (`secretary_skill_prompts`) and load them by runtime profile.
- Tool details should be short and index-like in core/runtime sections; long operational playbooks belong to skills.
- When migrating or adding behavior, update skill prompts first; only add to core if it is universally applicable.

## Workflow Guidelines
- Before starting implementation, confirm the exact scope of the request. Ask clarifying questions about: (1) which components/modules are in scope, (2) which level of hierarchy the change targets, (3) whether the request covers the full system or a subset. Do NOT assume scope.

## Tech Stack & Conventions
- This project uses TypeScript (frontend) and Python (backend).
- Frontend is React with CSS variables for theming (light/dark mode). Always use CSS variables instead of hardcoded colors.
- When fixing dark mode issues, check for hardcoded color values across all modal and component CSS files.

## Git Workflow
- After completing code changes, always run the build to verify before committing.
- When committing, use descriptive commit messages in the style the user prefers.
- Push to the correct branch — double-check which branch you're on before pushing.

## Common Pitfalls
- When working with dates and times, always handle timezone-aware datetimes. Use UTC internally and convert to local timezone only at display. Never use naive datetimes without timezone info — always attach tzinfo. Use a helper function for safe `astimezone()` calls on potentially naive datetimes.
- When fixing query/cache invalidation issues, search the entire codebase for ALL related query keys and invalidation calls. Use grep to find every instance — partial fixes cause sync bugs.

