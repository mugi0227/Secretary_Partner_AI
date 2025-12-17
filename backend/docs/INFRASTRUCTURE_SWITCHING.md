# Infrastructure Switching Guide

このドキュメントでは、各種インフラストラクチャを別のプロバイダーに切り替える手順を説明します。

---

## 1. Database

### SQLite → Firestore
1. `ENVIRONMENT=gcp` に設定
2. `GOOGLE_APPLICATION_CREDENTIALS` にサービスアカウントのパスを設定
3. `app/infrastructure/gcp/firestore_repository.py` が自動的に使用される

### SQLite → PostgreSQL
1. `app/interfaces/` のリポジトリインターフェースを確認
2. `app/infrastructure/postgres/` ディレクトリを作成
3. 各リポジトリを実装（ITaskRepository, IProjectRepository等）
4. `app/api/deps.py` のファクトリーに条件分岐を追加
5. `DATABASE_URL` を PostgreSQL 接続文字列に変更

---

## 2. LLM Provider

### Gemini API (推奨: 手軽)
Local環境でもGCP環境でも使える、最も手軽な方法。

1. `LLM_PROVIDER=gemini-api` に設定
2. `GOOGLE_API_KEY` を設定（[Google AI Studio](https://aistudio.google.com/apikey)から取得）
3. `GEMINI_MODEL=gemini-2.0-flash` を設定

### Vertex AI (GCP環境のみ)
GCPプロジェクトとサービスアカウントが必要。

1. `ENVIRONMENT=gcp` に設定
2. `LLM_PROVIDER=vertex-ai` に設定
3. `GOOGLE_CLOUD_PROJECT` を設定
4. `GOOGLE_APPLICATION_CREDENTIALS` にサービスアカウントのパスを設定
5. `GEMINI_MODEL=gemini-2.0-flash` を設定

### LiteLLM (Bedrock, OpenAI等)
1. `LLM_PROVIDER=litellm` に設定
2. 使用するプロバイダーに応じて認証情報を設定:

**Bedrock (via LiteLLM)**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `LITELLM_MODEL=bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`

**OpenAI (via LiteLLM)**
- `OPENAI_API_KEY`
- `LITELLM_MODEL=gpt-4o`

### 新しいLLMプロバイダーを追加する場合
1. `app/interfaces/llm_provider.py` の `ILLMProvider` を確認
2. `app/infrastructure/{provider}/` に実装クラスを作成
3. `app/core/config.py` の `LLM_PROVIDER` Literal型に追加
4. `app/api/deps.py` の `get_llm_provider()` に条件分岐を追加

---

## 3. Authentication

### Firebase Auth → AWS Cognito
1. `app/infrastructure/aws/cognito_auth.py` を作成
2. `IAuthProvider` インターフェースを実装
3. `app/api/deps.py` の `get_auth_provider()` を更新
4. 環境変数を追加:
   - `AWS_COGNITO_USER_POOL_ID`
   - `AWS_COGNITO_CLIENT_ID`

### Firebase Auth → Auth0
1. `app/infrastructure/auth0/auth0_provider.py` を作成
2. `IAuthProvider` インターフェースを実装
3. 環境変数を追加:
   - `AUTH0_DOMAIN`
   - `AUTH0_CLIENT_ID`
   - `AUTH0_CLIENT_SECRET`

---

## 4. Speech-to-Text

### Google Speech API → OpenAI Whisper (Local)
1. `pip install openai-whisper` を実行
2. `ENVIRONMENT=local` に設定
3. `app/infrastructure/local/whisper_provider.py` が使用される

### Google Speech API → AWS Transcribe
1. `app/infrastructure/aws/transcribe_provider.py` を作成
2. `ISpeechToTextProvider` インターフェースを実装
3. AWS認証情報を設定

---

## 5. Scheduler

### APScheduler → Cloud Scheduler
1. `ENVIRONMENT=gcp` に設定
2. Cloud Scheduler で `/api/heartbeat` を定期呼び出しするジョブを作成
3. APScheduler の起動をスキップ（`ENVIRONMENT` で制御）

### APScheduler → AWS EventBridge
1. EventBridge ルールを作成
2. Lambda または API Gateway 経由で `/api/heartbeat` を呼び出し
3. 認証トークンを EventBridge の入力に含める

---

## 6. Storage

### Local File System → Google Cloud Storage
1. `app/infrastructure/gcp/storage_provider.py` を実装
2. `GOOGLE_CLOUD_STORAGE_BUCKET` を設定
3. `IStorageProvider` インターフェースを使用

### Local File System → AWS S3
1. `app/infrastructure/aws/s3_provider.py` を作成
2. `IStorageProvider` インターフェースを実装
3. 環境変数を追加:
   - `AWS_S3_BUCKET`

---

## インターフェース一覧

| Interface | Purpose | Implementations |
|-----------|---------|-----------------|
| `ITaskRepository` | タスク永続化 | SQLite, Firestore |
| `IProjectRepository` | プロジェクト永続化 | SQLite, Firestore |
| `ILLMProvider` | LLM呼び出し | Gemini, LiteLLM |
| `IAuthProvider` | 認証 | Firebase, Mock |
| `ISpeechToTextProvider` | 音声認識 | Google Speech, Whisper |
| `IStorageProvider` | ファイル保存 | Local, GCS |

---

## 新しいプロバイダー追加時のチェックリスト

- [ ] 対応するインターフェースを確認
- [ ] `app/infrastructure/{provider}/` に実装を作成
- [ ] `app/api/deps.py` のファクトリー関数を更新
- [ ] 必要な環境変数を `.env.example` に追加
- [ ] このドキュメントに手順を追記
- [ ] ユニットテストを作成
- [ ] 統合テストを作成
