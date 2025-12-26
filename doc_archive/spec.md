Brain Dump Partner (Secretary Agent) - 要件定義・設計書
1. プロジェクト概要
1.1 コンセプト
Brain Dump Partner: 脳内多動なユーザーのための、入力コストゼロの「外付け前頭葉」。
Autonomous Secretary: 指示待ちではなく、自らの判断でユーザーを管理・支援する「自律型エージェント」。
Hybrid Operation: チャットによる自然言語操作と、GUIによる直接操作（クリックで分解など）の双方向性を担保する。
1.2 技術スタック & アーキテクチャ方針
Backend: Python (FastAPI)
Agent Framework: Google Cloud Agent Development Kit (ADK) / Vertex AI SDK
Design: マルチエージェント構成（Main Secretary + Planner Agent）。
Reliability: Pydantic によるLLM出力のスキーマ検証・修復と、リトライロジックの実装。
Design Pattern: Clean Architecture / Repository Pattern
目的: Google Cloud (本番・ハッカソン) と Local環境 (OSS・社内利用) を設定一つで切り替え可能にするため。
Infrastructure層 を Interface で抽象化し、GcpFirestoreRepository と SqliteRepository を差し替え可能にする。
2. データモデル設計 (Schema)
2.1 Task (ユーザーのタスク)
タスクは優先度を2軸で管理し、ステータスを持つ。ADHD文脈に合わせたフィールドを追加。
{
  "id": "uuid",
  "project_id": "uuid", // Optional (InboxならNull)
  "title": "確定申告の書類を集める",
  "description": "青い封筒を探すこと",
  "status": "TODO",     // TODO, IN_PROGRESS, WAITING, DONE
  "importance": "HIGH", // HIGH, MEDIUM, LOW (重要度)
  "urgency": "HIGH",    // HIGH, MEDIUM, LOW (緊急度)
  "energy_level": "LOW", // HIGH(重い), LOW(軽い) - 着手ハードルの指標
  "estimated_minutes": 15,
  "due_date": "datetime",
  "parent_id": "uuid",  // 親タスクID
  "source_capture_id": "uuid", // どの入力(音声/画像)から生まれたか (重複排除用)
  "created_by": "AGENT", // USER, AGENT
  "created_at": "datetime",
  "updated_at": "datetime"
}


2.2 Project (案件・コンテキスト)
{
  "id": "uuid",
  "name": "A社開発案件",
  "description": "要件定義からリリースまで",
  "status": "ACTIVE",
  "context_summary": "先方の担当は佐藤さん。定例は火曜日。" // RAGや会話から抽出された文脈
}


2.3 AgentTask (秘書の自律行動ToDo)
秘書自身のタスク。
{
  "id": "uuid",
  "target_user_id": "uuid",
  "trigger_time": "2025-12-15T10:00:00",
  "action_type": "CHECK_PROGRESS", // CHECK_PROGRESS, ENCOURAGE, WEEKLY_REVIEW
  "status": "PENDING",             // PENDING, COMPLETED, CANCELLED, SNOOZED
  "payload": {
    "target_task_id": "uuid",
    "message_tone": "gentle"
  },
  "retry_count": 0
}


2.4 Memories (AIの記憶)
記憶領域を3つのスコープに分割し、さらに情報の種類（Type）で管理する。
UserMemory: ユーザー個人の特性。
Type: FACT (事実: 子供がいる), PREFERENCE (好み: 朝型), PATTERN (傾向: 締め切り直前まで動かない)
ProjectMemory: Project.context_summary および RAGドキュメント。
WorkMemory (Global): 特定の仕事の手順やノウハウ。
Type: RULE (手順・禁則事項: 経費はXXシステムを使うこと)
2.5 Capture (入力ログ)
音声・画像・テキストの「原文」を保存し、タスク生成の証跡とする。
{
  "id": "uuid",
  "user_id": "uuid",
  "content_type": "AUDIO", // TEXT, AUDIO, IMAGE
  "content_url": "gs://...", // Cloud Storage URL
  "transcription": "あー、確定申告やらなきゃ...",
  "processed": true, // タスク化済みか
  "created_at": "datetime"
}


3. エージェント設計 (ADK & Multi-Agent)
3.1 Main Secretary Agent (Primary)
役割: ユーザーとの対話窓口、オーケストレーター、タスクのCRUD、自律行動の実行。
Idempotency (重複排除):
音声入力からタスク生成する際、Capture IDや内容の類似度を確認し、直近（例: 10分以内）に類似タスクが作成されていないかチェックする。
類似タスクがある場合は「これと同じですか？」と確認、または統合を提案する。
3.2 Planner Agent (Sub-Agent)
役割: タスク分解と実行ガイド作成の専門家。
プロセス:
タスクのタイトルとProjectを見る。
WorkMemory を検索し、該当する手順（例：経費精算手順）がないか確認する。
手順があればそれに従い、なければ一般的な知識で、心理的ハードルの低い「マイクロステップ」に分解する。
各サブタスクに対して「実行ガイド（1行アドバイス）」を付与する。
4. API エンドポイント定義 (Interface)
A. Chat & Captures (対話・入力) 【新規】
POST /api/chat: メインの対話入口。
Input: text, audio, image, mode (dump / consult / breakdown)
Output: assistant_message, related_tasks[], suggested_actions[]
Logic: 入力を Capture として保存 → Main Agent起動 → Tool実行 → レスポンス生成。
POST /api/captures: 音声・画像のアップロード専用。
B. Tasks (CRUD)
GET /api/tasks
POST /api/tasks
PATCH /api/tasks/{task_id}
DELETE /api/tasks/{task_id}
POST /api/tasks/{task_id}/breakdown: 指定タスクをPlanner Agentを用いて分解。
GET /api/today/top3: 【新規】 今日の最優先タスクTop3を取得（ルールベース×AIスコアリング）。
C. Projects
GET /api/projects
POST /api/projects
PATCH /api/projects/{project_id}
DELETE /api/projects/{project_id}
POST /api/projects/{project_id}/documents
D. Agent Tasks & Memories
GET /api/agent_tasks
POST /api/agent_tasks
PATCH /api/agent_tasks/{id}
GET /api/memories/work
POST /api/memories/work
E. Heartbeat (自律駆動)
POST /api/heartbeat
UX制御: Quiet Hours（例: 深夜2時〜6時）は通知系タスクの実行をスキップまたは翌朝にスケジュールし直すロジックを含める。
5. Agent Tools (Function Calling)
| Tool名 | 説明 | 引数 |
| create_task | タスク作成 | title, importance, urgency, energy_level, project_id, ... |
| update_task | タスク編集 | task_id, status, ... |
| delete_task | タスク削除 | task_id |
| search_similar_tasks | 重複チェック | title, days_lookback |
| breakdown_task | タスク分解 | task_id, context |
| schedule_agent_task | 秘書行動の予約 | action_type, execute_at, payload |
| search_work_memory | 手順検索 | query |
| add_to_memory | 記憶追加 | memory_type, content |
6. ディレクトリ構造 (Repository Pattern)
backend/
├── app/
│   ├── api/                # Router (Endpoints)
│   ├── core/               # Config, Logger
│   ├── models/             # Pydantic Schemas
│   ├── services/           # Business Logic
│   │   ├── agent_service.py   # Main Agent Logic
│   │   ├── planner_service.py # Sub Agent Logic
│   │   ├── task_service.py    # CRUD Logic
│   │   └── capture_service.py # Input Processing
│   ├── tools/              # Agent Tools definitions
│   ├── interfaces/         # Abstract Base Classes
│   └── infrastructure/     # Concrete Implementations
│       ├── gcp/            # VertexAI, Firestore
│       └── local/          # LiteLLM, SQLite
└── main.py


7. コーディングAIへの指示（Prompting Guide）
Clean Architectureの厳守: infrastructure 層の分離とDIパターンの利用。
ハイブリッド対応: 環境変数による実装の切り替え。
堅牢性 (Reliability):
LLMからのJSON出力は必ず Pydantic で検証し、形式エラーの場合は修正プロンプトでリトライするロジック（最大2回）を入れること。
音声入力からのタスク作成時は、必ず search_similar_tasks 相当のロジックを挟み、重複作成を防ぐこと。
Planner Agent: WorkMemory を活用した手順準拠のタスク分解。
