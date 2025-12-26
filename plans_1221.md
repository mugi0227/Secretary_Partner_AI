# Secretary Partner AI - 実装計画 (2025-12-21)

## 背景

spec2.md に記載された要件定義と現在の実装状況を比較し、未実装機能の洗い出しと優先順位付けを実施。

## ギャップ分析結果

### ✅ 実装済み機能

- タスクCRUD (API + UI)
- プロジェクトCRUD
- Top3スコアリング（ルールベース）
- タスク分解 (Planner Agent)
- チャットインターフェース（ストリーミング対応）
- Captureシステム（モデル定義）
- エージェントツール群
- Clean Architecture / Repository Pattern
- **Phase 1: スケジューリング核心 + 依存関係**
  - ✅ 1.1 dependency_ids フィールド追加（Backend + DB + API）
  - ✅ 1.2 タスク分解時の依存関係設定（Planner Agent）
  - ✅ 1.3 カンバンUI（🔒インジケーター、依存関係表示）
  - ✅ 1.4 設定画面（1日の稼働時間設定、LocalStorage保存）
  - ✅ 1.5 タスク詳細モーダル（依存関係設定UI、サブタスク間依存表示）

### ❌ 未実装機能

#### 優先度: 高（ユーザー要望）

1. ~~**タスク依存関係** (§3.1 dependency_ids)~~ ✅ **完了**
   - ~~フィールド未実装~~
   - ~~「AがBより先」が管理できない~~

2. **キャパシティ計算** (§③ Capacity)
   - 1日のバケツ容量考慮なし
   - タスク過多時の提案ができない

3. **Incubatorパターン** (§③ 未確定計画)
   - AI提案が即確定になってしまう
   - Cursor風の承認フローを実装したい

#### 優先度: 中（後回し可能）

4. **Heartbeatアクション実装** (§4.2 自律駆動)
   - 5つのアクション全てがTODO状態

5. **重複検出の自動化** (§① Idempotency)
   - ツールは存在するが自動呼び出しなし

6. **音声/画像処理パイプライン** (§① マルチモーダル入力)
   - モデルは対応、処理実装なし

#### 優先度: 低（将来的な拡張）

7. RAG/ドキュメント管理
8. WorkMemory充実
9. Energy Level最適化
10. フロントエンド音声入力UI

---

## ユーザーの優先順位と理由

### Core Value (最重要)
> 「正確なスケジューリング」と「今日やるべきことの正確な抽出」がコア

理由：
- Heartbeat: 必須だが、タスク管理の精度が先
- 重複検出: 割と呼び出される程度
- 音声/画像: ちょろっと追加で後でもOK

### Incubatorパターンのイメージ
Cursor の承認フローのような体験：

1. **No Interruption**: Brain Dumpの勢いを止めない
   - AI生成タスクは即座に確認を求めず、バックグラウンドで処理
   - 完了時はサマリーをCursor風に説明

2. **Draft Mode**: 生成タスクは `status: DRAFT` で保存

3. **Batch Review**: 任意のタイミングで未承認リストを確認
   - Cursor の Diff のように変更内容（AIの解釈）を表示
   - 個別修正 または 一括承認

---

## 実装計画

### Phase 1: スケジューリング核心 + 依存関係 ✅ 完了

#### 1.1 dependency_ids フィールド追加 ✅
- **Backend**: Task モデルに `dependency_ids: list[str]` 追加
- **DB**: SQLite マイグレーション（JSON型で保存）
- **API**: CRUD対応（POST/PATCH時に依存IDを受け取る）

#### 1.2 Top3ロジック改善 ✅
- **依存関係考慮**: 依存先が未完了 → 候補から除外
- **キャパシティ計算**:
  - 1日の稼働時間（デフォルト8時間）
  - `estimated_minutes` を積算
  - バケツを超えたら「今日に収まらない」検出
- **scheduler_service.py 実装**:
  - `check_schedule_feasibility(tasks, capacity_hours)` メソッド
  - オーバーフロー時の提案生成

#### 1.3 カンバンUI（🔒インジケーター）✅
- **依存ありタスクに🔒表示**:
  - 依存先が未完了 → 🔒 (ロック中)
  - 依存解消 → 🔓 (着手可能)
- **ホバーツールチップ**: 「タスクAを先に完了してください」
- **ゲーミフィケーション**: 視覚的フィードバックで達成感

#### 1.4 設定画面 ✅
- **1日の稼働時間設定**:
  - デフォルト: 8時間
  - ユーザーが編集可能
  - LocalStorage保存

#### 1.5 タスク詳細モーダル ✅
- **依存関係の設定UI**:
  - 他タスクを選択（ドロップダウン）
  - 複数選択可能
- **依存状況の表示**:
  - 「このタスクの前にやること」リスト
  - 「このタスクが終わると着手可能」リスト（逆依存）

#### 追加実装: 画像アップロード機能 ✅
- **Backend**: Base64画像を受け取り、Gemini APIに送信
- **Frontend**: 画像選択・プレビュー・ドラッグ&ドロップ対応
- **モデル**: gemini-3-flash-preview に更新（より多様な相談に対応）

#### Phase 2.3 Step 1-2: プロジェクト拡張 + UI ✅ (2024-12-23完了)

**Backend実装**:
- ✅ [Project モデル拡張](backend/app/models/project.py)（context, priority, goals, key_points）
- ✅ [DB マイグレーション](backend/migrate_projects.py)（SQLite ALTER TABLE）
- ✅ [ProjectORM更新](backend/app/infrastructure/local/database.py)（JSON型でgoals/key_points保存）
- ✅ [ProjectRepository更新](backend/app/infrastructure/local/project_repository.py)（ORM mapping）
- ✅ [モックプロジェクト作成スクリプト](backend/create_mock_projects.py)（UTF-8対応）

**Frontend実装**:
- ✅ [Project型定義更新](frontend/src/api/types.ts)（TypeScript interfaces）
- ✅ [ProjectDetailModal](frontend/src/components/projects/ProjectDetailModal.tsx)（README編集、優先度設定、goals/key_points管理）
- ✅ [ProjectCreateModal](frontend/src/components/projects/ProjectCreateModal.tsx)（新規作成UI）
- ✅ [ProjectsPage](frontend/src/pages/ProjectsPage.tsx)（優先度表示、作成ボタン）
- ✅ 優先度を星（★）で視覚化（1-10スケール）
- ✅ Markdown READMEプレビュー機能（ReactMarkdown + remark-gfm）

**修正したエラー**:
- user_id不一致（test-user → dev_user）
- CORS設定（allow_origin_regex → allow_origins）
- UTF-8エンコーディングエラー（Pythonスクリプトで解決）
- SQLAlchemy text()ラッパー要求

**設計変更**:
- `infer_project`ツール削除（LLMの推論能力で対応）

**モックデータ**:
- ブログ執筆（優先度8）
- 確定申告準備（優先度10）
- 英語学習（優先度5）

#### Phase 2.3 Step 3-4: Agent ツール + Secretary改修 ✅ (2024-12-24完了)

**Agent Tools実装**:
- ✅ [create_project_tool](backend/app/tools/project_tools.py#L121-L142)（プロジェクト作成、KPI自動選定）
- ✅ [list_projects_tool](backend/app/tools/project_tools.py#L167-L181)（プロジェクト一覧取得、priority情報含む）
- ✅ [load_project_context_tool](backend/app/tools/project_tools.py#L220-L237)（詳細コンテキスト読み込み）

**Secretary Agent更新**:
- ✅ [新規ツールをエージェントに登録](backend/app/agents/secretary_agent.py#L59-L73)（list_projects, load_project_context）
- ✅ [システムプロンプト拡張](backend/app/agents/prompts/secretary_prompt.py#L27-L51)（プロジェクト中心の作業フロー）

**プロジェクト中心フロー**:
1. タスク作成時に`list_projects`で一覧確認
2. LLMがプロジェクトを推測（専用ツール不要）
3. ユーザーに確認（「『ブログ執筆』プロジェクトで合っていますか?」）
4. `load_project_context`で詳細読み込み（goals, key_points, README）
5. コンテキストを踏まえてタスク分解・作成
6. `create_task`時に`project_id`を指定

**KPI自動選定**:
- プロジェクト作成時、内容からKPIテンプレートを自動選定
- 営業系 → sales、運用系 → operations、開発系 → sprint など
- カスタムKPIも指定可能

#### Phase 2.3 Step 5: Planner Agent統合 ✅ (2024-12-24完了)

**目的**: タスク分解時にプロジェクトコンテキスト（goals, key_points, README）を活用

**実装内容**:
- ✅ [PlannerService改修](backend/app/services/planner_service.py#L41-L52)（project_repo追加、プロジェクト情報読み込み）
- ✅ [プロンプト構築拡張](backend/app/services/planner_service.py#L115-L167)（プロジェクト目標・ポイントをプロンプトに含める）
- ✅ [breakdown_task_tool更新](backend/app/tools/task_tools.py#L483-L508)（project_repo受け取り、PlannerServiceに渡す）
- ✅ [Secretary Agent更新](backend/app/agents/secretary_agent.py#L73)（breakdown_task_toolにproject_repo渡す）
- ✅ [Planner Agent prompt拡張](backend/app/agents/prompts/planner_prompt.py#L70-L77)（プロジェクトコンテキスト活用セクション追加）
- ✅ 循環インポート解決（planner_serviceでlazy import使用）

**プロジェクト考慮タスク分解の流れ**:
1. ユーザーが「タスクXを分解して」と依頼
2. Secretary Agentが`breakdown_task`を呼び出し
3. PlannerServiceがタスクのproject_idを確認
4. project_idがあれば、project_repoから詳細情報を取得
5. プロンプトにプロジェクト目標・key_points・READMEを含める
6. Planner Agentがプロジェクト全体を考慮した分解を実施
7. 例: SEOブログプロジェクトなら、キーワード選定やメタデータ設定ステップを含める

**技術的改善**:
- 循環インポート問題を解決（`planner_service.py`内で`create_planner_agent`をlazy import）
- `TYPE_CHECKING`を使用して型ヒントのみの依存を分離
- 既存の非プロジェクトタスクにも対応（project_repoがNoneの場合はスキップ）

---

### Phase 2: プロジェクト中心設計 + Focus for Today改善

#### 設計の全体像

Phase 2では、以下の3つの柱を中心に機能を強化します：

1. **Focus for Today 改善**: サブタスク表示の改善と「今日のタスク」計算ロジックの実装
2. **AIスケジューリング**: 依存関係とキャパシティを考慮した今日のタスク決定
3. **プロジェクト中心アーキテクチャ**: AIがプロジェクトコンテキストを活用したタスク分解とスケジューリング

#### 2.1 Focus for Today 改善

**目的**: サブタスクの親タスク情報を表示し、クリック時に親タスク詳細を開く

**現状の問題**:
- Focus for Todayにサブタスクが表示された時、親タスクが分からない
- サブタスクをクリックしても、サブタスク自体の詳細しか見られない

**実装仕様**:

1. **表示形式の変更**:
   ```
   [親タスク名] → サブタスク名
   例: [商品レビュー記事作成] → 競合商品のリサーチ
   ```

2. **クリック動作の変更**:
   - サブタスクをクリック → 親タスクの詳細モーダルを開く
   - モーダル内で該当サブタスクを選択状態にする
   - ユーザーは全体像を把握しながらサブタスクに取り組める

3. **Backend 変更**:
   - `Task` モデルに `parent_id: Optional[str]` フィールド追加（既存）
   - `/tasks` APIレスポンスで親タスク情報を含める（オプション or join）
   - または、フロントエンドで `parent_id` から親タスクを検索

4. **Frontend 変更**:
   - `TaskItem.tsx`: サブタスクの場合、`[親タスク名] → ` プレフィックスを表示
   - `DashboardPage.tsx`: Top3カード内のクリックハンドラーを修正
     - サブタスクの場合: 親タスクIDで `TaskDetailModal` を開く
     - 親タスクの場合: 通常通り
   - `TaskDetailModal.tsx`: 初期選択サブタスクを prop として受け取る

**実装優先度**: 高（ユーザー体験向上）

---

#### 2.2 AIスケジューリングシステム

**目的**: 「今日やるべきタスク」をAIが自動計算し、その中でTop3を強調表示

**現状の問題**:
- Focus for Today は Top3 のみ表示
- 「今日のタスク」という概念が存在しない
- ユーザーは今日何をすべきか全体像を把握できない

**新しい仕様**:

1. **「今日のタスク」の定義**:
   - 依存関係: 依存先が全て完了している
   - キャパシティ: 今日の稼働時間内に完了可能
   - 締切: 今日が締切 or 近い締切のタスク
   - プロジェクト優先度: 重要なプロジェクトのタスク
   - エネルギーバランス: HIGH/MEDIUM/LOW のバランスを考慮

2. **スケジューリングアルゴリズム**:
   ```python
   def calculate_todays_tasks(
       all_tasks: List[Task],
       capacity_hours: float,
       today: date
   ) -> List[Task]:
       # 1. 依存関係でフィルタリング
       available_tasks = [t for t in all_tasks if dependencies_met(t)]

       # 2. 締切で優先順位付け
       urgent_tasks = [t for t in available_tasks if t.due_date <= today + timedelta(days=2)]

       # 3. キャパシティに収まるように選択
       selected_tasks = []
       total_minutes = 0
       capacity_minutes = capacity_hours * 60

       for task in sorted(urgent_tasks, key=priority_score, reverse=True):
           if total_minutes + task.estimated_minutes <= capacity_minutes:
               selected_tasks.append(task)
               total_minutes += task.estimated_minutes

       # 4. エネルギーバランス調整
       selected_tasks = balance_energy_levels(selected_tasks)

       return selected_tasks
   ```

3. **Top3 の位置づけ**:
   - 今日のタスク内で最も重要な3つを強調
   - 既存の Top3 スコアリングロジックを活用
   - UI上で視覚的に区別（例: ゴールドのボーダー）

4. **Backend 実装**:
   - `SchedulerService.calculate_todays_tasks()` メソッド追加
   - `SchedulerService.get_top3_from_todays_tasks()` メソッド追加
   - `/tasks/today` エンドポイント新設:
     ```json
     {
       "today_tasks": [...],
       "top3_ids": ["id1", "id2", "id3"],
       "total_estimated_minutes": 420,
       "capacity_minutes": 480,
       "overflow": false
     }
     ```

5. **Frontend 実装**:
   - `DashboardPage.tsx`: Focus for Today セクションを拡張
   - 「今日のタスク」を全て表示
   - Top3 には特別なスタイル（ゴールド/スターマーク）を適用
   - キャパシティゲージを表示（例: "7時間 / 8時間"）

**実装優先度**: 最高（コア機能）

---

#### 2.3 プロジェクト中心アーキテクチャ

**目的**: AIがプロジェクト全体のコンテキストを理解し、正確なタスク分解とスケジューリングを実施

**設計原則**:
- AIは常にプロジェクト一覧を把握
- タスク作成前に該当プロジェクトを推測・確認
- プロジェクト詳細コンテキストを読み込んでからタスク分解
- スケジューリングもプロジェクト単位で実施

**フロー概要**:
```
1. ユーザー: Brain Dump（「商品レビュー記事書く」）
2. AI: プロジェクト一覧を確認 → 「ブログ執筆」プロジェクトと推測
3. AI: ユーザーに確認（「これは『ブログ執筆』プロジェクトですか?」）
4. ユーザー: 承認
5. AI: プロジェクトREADME/詳細コンテキストを読み込み
6. AI: コンテキスト込みでタスク分解実施
7. AI: プロジェクト優先度も考慮してスケジューリング
```

**データモデル変更**:

1. **Project モデル拡張**:
   ```python
   class Project(BaseModel):
       id: str
       user_id: str
       name: str
       description: str  # 既存: 短い説明

       # 新規フィールド
       context: Optional[str] = None  # 詳細コンテキスト（README的な内容）
       priority: int = Field(default=5, ge=1, le=10)  # プロジェクト優先度
       goals: List[str] = Field(default_factory=list)  # プロジェクトのゴール
       key_points: List[str] = Field(default_factory=list)  # 重要なポイント

       created_at: datetime
       updated_at: datetime
   ```

2. **DB マイグレーション**:
   - `context` TEXT NULL
   - `priority` INTEGER DEFAULT 5
   - `goals` TEXT NULL (JSON array)
   - `key_points` TEXT NULL (JSON array)

**Agent ツール拡張**:

1. **新規ツール: `load_project_context`**:
   ```python
   async def load_project_context(project_id: str) -> dict:
       """プロジェクトの詳細コンテキストを読み込む"""
       project = await project_repo.get_by_id(project_id)
       return {
           "name": project.name,
           "description": project.description,
           "context": project.context,
           "priority": project.priority,
           "goals": project.goals,
           "key_points": project.key_points,
           "active_tasks_count": len(project.tasks),
       }
   ```

2. **既存ツール修正: `list_projects`**:
   - 現在: プロジェクト一覧のみ返す
   - 修正後: 各プロジェクトの簡易情報（name, description, priority）を含める
   - **Note**: プロジェクト推測は LLM の推論能力で対応（専用ツール不要）

**Agent ロジック変更**:

1. **Secretary Agent のシステムプロンプト拡張**:
   ```markdown
   あなたはSecretary Partner AIです。ユーザーのタスク管理をサポートします。

   ## プロジェクト中心の作業フロー

   1. タスク作成依頼を受けたら、まず `list_projects` でプロジェクト一覧を確認
   2. 該当プロジェクトを推測
   3. ユーザーに「このプロジェクトで合っていますか?」と確認
   4. 承認後、`load_project_context` で詳細コンテキストを読み込み
   5. コンテキストを踏まえてタスク分解を実施
   6. `create_task` でタスクを作成
   7. 必要に応じて `schedule_task` でスケジューリング

   ## 重要
   - プロジェクトのgoalsとkey_pointsを常に意識する
   - タスク分解時は、プロジェクト全体の文脈を考慮する
   - 優先度の高いプロジェクトのタスクを優先的にスケジュール
   ```

2. **Planner Agent の修正**:
   - タスク分解時に `project_context` を引数として受け取る
   - コンテキストを考慮した詳細な分解を実施

**Frontend UI 追加**:

1. **プロジェクト詳細ページに README エディター**:
   - プロジェクト作成・編集時に `context` フィールドを編集可能に
   - Markdownエディターで記述
   - プレビュー機能

2. **プロジェクト一覧に優先度表示**:
   - 星マーク（★★★★★）で視覚化
   - ソート機能: 優先度順 / 作成日順 / タスク数順

**API エンドポイント追加**:

1. **PATCH `/projects/{id}/context`**: コンテキスト更新
2. **GET `/projects/{id}/full`**: 全詳細情報取得（タスク含む）

**実装優先度**: 最高（Phase 2の核心）

**段階的実装計画**:
1. **Step 1**: Project モデル拡張 + DB マイグレーション
2. **Step 2**: プロジェクト詳細UI（README エディター）
3. **Step 3**: Agent ツール追加（`load_project_context`, `infer_project`）
4. **Step 4**: Secretary Agent ロジック修正
5. **Step 5**: Planner Agent にコンテキスト統合
6. **Step 6**: スケジューリングにプロジェクト優先度を統合

---

#### Phase 2 実装順序の推奨

1. **Week 1**: 2.3 Step 1-2（Project拡張 + UI）
2. **Week 2**: 2.3 Step 3-4（Agent ツール + Secretary改修）
3. **Week 3**: 2.2（AIスケジューリング実装）
4. **Week 4**: 2.1（Focus for Today改善）
5. **Week 5**: 2.3 Step 5-6（Planner統合 + スケジューリング統合）

**理由**:
- プロジェクトインフラが全ての基盤となる
- AIスケジューリングは Focus for Today の前提
- Focus for Today は最後の仕上げ（UX改善）

---

### Phase 3: Incubatorパターン（Cursor風承認フロー）

#### 2.1 DRAFT ステータス追加
- Task.status に `DRAFT` を追加
- AI生成タスクは `created_by: AGENT` + `status: DRAFT` で保存

#### 2.2 AI生成時のサマリー表示
- **チャットストリーム内で表示**:
  - 「こう解釈しました」メッセージ
  - Diff風のフォーマット:
    ```
    ✨ タスクを作成しました
    📝 タイトル: 確定申告の書類を集める
    📂 プロジェクト: 経理
    ⏱ 所要時間: 15分
    ⚡ エネルギー: LOW (軽い)
    ```

#### 2.3 未承認リストUI
- **新規ページ or モーダル**: 「Pending Review」
- **表示内容**:
  - DRAFT状態のタスク一覧
  - AIの解釈内容を視覚的に表示
- **アクション**:
  - 個別編集ボタン
  - 個別承認ボタン (→ `status: TODO`)
  - 一括承認ボタン
  - 却下ボタン (→ 削除 or `status: REJECTED`)

---

### Phase 3: 可視化強化（将来実装）

#### 3.1 プロジェクトページにガントチャート
- 横軸: 日付
- タスクバー: 所要時間に応じた長さ
- 依存関係: 矢印で表示
- ライブラリ候補: `react-gantt-chart`, `dhtmlx-gantt`

#### 3.2 DAGビュー（依存関係グラフ）
- ノード: タスク
- エッジ: 依存関係（有向グラフ）
- ライブラリ候補: `React Flow`, `D3.js`
- インタラクティブ: ドラッグ＆ズーム

---

### Phase 4: 自律行動（後回し）

#### 4.1 Heartbeatアクション実装
- CHECK_PROGRESS
- ENCOURAGE
- WEEKLY_REVIEW
- DEADLINE_REMINDER
- MORNING_BRIEFING

#### 4.2 音声/画像入力
- 音声入力UI（マイクボタン）
- WhisperProvider統合
- 画像解析パイプライン

---

## 技術仕様メモ

### 依存関係のUI実装案

#### A. シンプル路線（Phase 1で実装）
- タスク詳細モーダルに「ブロック中」「ブロックされている」表示
- クリックで該当タスクに飛べる

#### D. カンバン上でインジケーター（Phase 1で実装）
- 依存があるタスクに🔒アイコン
- ホバーで「タスクAを先に完了してください」
- 完了したら🔓に変わる
- **選定理由**: ゲーミフィケーション感、視覚的、実装が比較的簡単

#### B, C. 高度な可視化（Phase 3で実装）
- ガントチャート
- DAGビュー
- **理由**: 実装コストが高いが、将来的に欲しい機能

---

## 設定項目

### ユーザー設定（Phase 1.4）
- `daily_capacity_hours`: 1日の稼働時間（デフォルト8時間）
- 保存先: 設定画面から編集可能

---

## 次のステップ

Phase 1.1 から着手:
1. Backend: Task モデルに `dependency_ids` 追加
2. DB: マイグレーション実行
3. API: CRUD対応
4. Frontend: TypeScript型定義更新

---

## 参考資料

- spec2.md: 要件定義書
- ギャップ分析結果: エージェントID `a4e9c22` の調査結果
