Brain Dump Partner (Secretary Agent) - 最終要件定義・設計書
1. プロジェクト概要
1.1 コンセプト
Product Name: Brain Dump Partner
Target: 脳内多動やADHD傾向を持つ「隠れた天才（Hidden High Potentials）」。
Core Value:
Zero Friction Input: 入力コストを極限までゼロにする（叫ぶだけ、撮るだけ）。
Autonomous Secretary: 指示待ちではなく、自らの判断でユーザーを管理・支援する「自律型エージェント」。
No Management: ユーザーは「管理」をしない。AIが管理し、ユーザーは「実行（作業）」だけに集中する。
Philosophy: タスク管理の4工程のうち、①収集 ②加工 ③整理 はAIが全責任を持つ。ユーザーの責任は ④実行 のみ とする。
1.2 技術スタック & アーキテクチャ方針
Backend: Python (FastAPI)
Agent Framework: Google Cloud Agent Development Kit (ADK) / Vertex AI SDK
Design: Multi-Agent構成（Main Secretary + Planner Agent）。
Reliability: Pydantic によるLLM出力のスキーマ検証・修復と、リトライロジックの実装。
Design Pattern: Clean Architecture / Repository Pattern
目的: Google Cloud (本番・ハッカソン) と Local環境 (OSS・社内利用) を設定一つで切り替え可能にするため。
Infrastructure層 を Interface で抽象化し、GcpFirestoreRepository と SqliteRepository を差し替え可能にする。
2. タスク管理フロー要件 (The 4 Phases)
① 収集 (Capture)
機能: マルチモーダル入力（音声、画像、テキスト）。
要件:
ユーザーは整理されていない思考（Brain Dump）をそのまま投げる。
システムは生の入力を Capture ログとして保存し、そこから「タスク」「事実」「感情」を抽出する。
Idempotency (重複排除): 直近の入力内容と比較し、同一のタスクが重複して生成されないように制御する。
② 加工 (Clarify)
機能: 構造化と属性推定。
要件:
Actionable化: 曖昧な発言（例：「税金」）を、具体的な行動（例：「封筒を開ける」）に変換する。
属性付与: 以下の属性をAIが文脈から推定して付与する。
Project: どの案件か（不明ならInbox）。
Importance / Urgency: 重要度と緊急度 (High/Medium/Low)。
Energy Level: そのタスクの着手に必要な心理的ハードル (High/Low)。
③ 整理 (Organize & Schedule)
機能: スケジューリングと優先順位付け。
要件:
Logic over LLM: スケジュールはLLMの直感だけに頼らず、「ロジック（Solver Tool）」 を併用する。
Dependency: 「タスクAが終わらないとBはできない」という依存関係を考慮する。
Capacity: 1日の稼働時間（バケツ容量）を超えないように調整し、溢れたら「明日に回しますか？」と提案する。
Incubator: AIが生成した計画は決定事項とせず、「未確定」としてユーザーに提示し、承認（Goサイン）を得るプロセスを挟む。
④ 実行 (Engage)
機能: 着手支援（Focus Mode）。
要件:
・仕事のやり方を明確にする
・チャットでの相談で、そのプロジェクトについてのコンテキストを維持しながら、壁打ちしてくれる。
・なんなら、資料作成までできると〇。claude のskillsなど参考にしたらできたりしないのだろうか。
3. データモデル設計 (Schema)
3.1 Task (ユーザーのタスク)
{
  "id": "uuid",
  "project_id": "uuid", // Optional (InboxならNull)
  "title": "確定申告の書類を集める",
  "description": "青い封筒を探すこと",
  "status": "TODO",     // TODO, IN_PROGRESS, WAITING, DONE
  "importance": "HIGH", // HIGH, MEDIUM, LOW
  "urgency": "HIGH",    // HIGH, MEDIUM, LOW
  "energy_level": "LOW", // HIGH(重い), LOW(軽い) - 着手ハードルの指標
  "estimated_minutes": 15,
  "due_date": "datetime",
  "parent_id": "uuid",  // 親タスクID
  "dependency_ids": ["uuid"], // これより先に終わらせるべきタスク
  "source_capture_id": "uuid", // 生成元のCapture ID
  "created_by": "AGENT", // USER, AGENT
  "created_at": "datetime",
  "updated_at": "datetime"
}


3.2 Project (案件・コンテキスト)
{
  "id": "uuid",
  "name": "A社開発案件",
  "description": "要件定義からリリースまで",
  "status": "ACTIVE",
  "context_summary": "先方の担当は佐藤さん。定例は火曜日。" // RAGや会話から抽出
}


3.3 AgentTask (秘書の自律行動ToDo)
{
  "id": "uuid",
  "target_user_id": "uuid",
  "trigger_time": "2025-12-15T10:00:00",
  "action_type": "CHECK_PROGRESS", // CHECK_PROGRESS, ENCOURAGE, WEEKLY_REVIEW
  "status": "PENDING",             // PENDING, COMPLETED, CANCELLED, SNOOZED
  "payload": {
    "target_task_id": "uuid",
    "message_tone": "gentle"
  }
}


3.4 Memories (AIの記憶)
UserMemory: ユーザー個人の特性（Fact, Preference, Pattern）。
ProjectMemory: プロジェクト固有の文脈。
WorkMemory (Global): 【重要】 特定の仕事の手順やノウハウ（例：経費精算フロー）。Planner Agentが参照する。
4. エージェント設計 (Multi-Agent)
4.1 Main Secretary Agent (Primary)
役割: ユーザー対話、オーケストレーター、CRUD操作、自律行動。
責務: ユーザーの入力を受け取り、適切なToolやSub-Agentに振り分ける。
4.2 Planner Agent (Sub-Agent)
役割: タスク分解と実行ガイド作成の専門家。
ロジック:
WorkMemory を検索し、社内規定や手順書が存在するか確認。
存在すればそれに準拠、なければ一般的知識でタスクを分解。
心理的ハードルを下げるための「実行ガイド」を生成。
5. API エンドポイント定義 (Interface)
A. 対話 & 入力
POST /api/chat: メイン対話。音声/画像/テキストを受け取り、レスポンスとActionを返す。
POST /api/captures: 生ログ保存用。
B. タスク管理
GET /api/tasks: 検索・フィルタ。
POST /api/tasks: 作成。
PATCH /api/tasks/{task_id}: 更新。
DELETE /api/tasks/{task_id}: 削除。
POST /api/tasks/{task_id}/breakdown: Planner Agentによる分解実行。
GET /api/today/top3: 今やるべきタスクTop3（依存関係と容量を考慮したSolverの結果）。
C. 記憶 & コンテキスト
GET /api/projects
POST /api/projects/{id}/documents: RAG用ドキュメント追加。
GET /api/memories/work: 手順書の参照。
D. 自律駆動
POST /api/heartbeat: 定期実行トリガー（Cloud Schedulerから叩く）。
Logic: AgentTask DBを確認し、期限が来たタスクを実行。ただし Quiet Hours（深夜など）は避ける。
6. Agent Tools (Function Calling)
BackendのService層メソッドをラップし、Agentが実行可能なToolとして定義する。
Tool名
説明
重要な引数
create_task
タスク作成
title, energy_level, estimated_minutes
search_similar_tasks
重複チェック
title, similarity_threshold
breakdown_task
タスク分解 (Planner呼び出し)
task_id, context
check_schedule_feasibility
Solver実行
task_list, capacity_hours
schedule_agent_task
秘書行動の予約
action_type, execute_at
search_work_memory
手順・ノウハウ検索
query

7. ディレクトリ構造 (Repository Pattern)
backend/
├── app/
│   ├── api/                # Router (Endpoints)
│   ├── core/               # Config, Logger, Prompts
│   ├── models/             # Pydantic Schemas
│   ├── services/           # Business Logic
│   │   ├── agent_service.py   # Main Agent Logic
│   │   ├── planner_service.py # Sub Agent Logic
│   │   ├── scheduler_service.py # ★Solver Logic (Dependency/Capacity calculation)
│   │   └── task_service.py    # CRUD Logic
│   ├── tools/              # Agent Tools definitions
│   ├── interfaces/         # Abstract Base Classes
│   └── infrastructure/     # Concrete Implementations
│       ├── gcp/            # VertexAI, Firestore
│       └── local/          # LiteLLM, SQLite
└── main.py


