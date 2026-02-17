from __future__ import annotations

PROFILE_SKILL_PROMPTS: dict[str, str] = {
    "capability": """
- ツール能力の質問では、必ず「このターンで有効なツール」を中心に答える。
- 返答は次の順序にする:
  1) いま使えるツールをカテゴリ別に短く列挙
  2) 各カテゴリで「どういうとき使うか」を1行で添える
  3) 必要なら次アクション（何を依頼すれば実行できるか）を示す
- ツール名は実際のツール名（例: `create_task`）で示し、存在しない名称を作らない。
""".strip(),
    "task": """
- タスク作成・更新系では、次の順序を基本にする:
  1) 依頼をタスク単位に分解（複数件なら分ける）
  2) `list_projects` で候補取得
  3) 各タスクの所属先を推定し、`ask_user_questions` で確認
  4) 必要に応じて `load_project_context` で補足文脈を読む
  5) `search_similar_tasks` で重複確認
  6) `create_task` を実行
- 重要ガード:
  - タスク依頼を `update_project` や `create_project_summary` で保存してはいけない。
  - `update_project` は、ゴール・KPI・メンバー・README 等の「プロジェクト属性更新」を明示依頼されたときだけ使う。
- 非プロジェクトタスクの扱い:
  - ユーザーが個人タスクを望む場合は1回確認し、`project_id` なしで `create_task` する。
- 会議とタスクの使い分け:
  - 固定時刻イベントは `create_meeting`。
  - 実行作業は `create_task`。
- 担当者付与:
  - 事前に `list_project_members` と `list_project_invitations` を確認。
  - 対象タスクを `list_tasks` / `get_task` で確認後、`assign_task`。
  - 現状確認は `list_task_assignments` / `list_project_assignments`。
- サブタスク・依存:
  - サブタスクは `parent_id` / `order_in_parent` を使う。
  - サブタスク分解の依頼では、各サブタスクに `description` と `guide` を必ず設定する（進め方ガイドは3-7ステップ + 完了の目安）。
  - 親タスクがプロジェクト配下なら、サブタスクも同じプロジェクト配下で作成する。
  - `guide` は次の形式を基本にする（Markdown）:
    - `## 進め方ガイド` 見出しを先頭に置く
    - 具体手順を 3-7 個の番号リストで書く（1手順あたり5-15分目安）
    - 最後に `**完了の目安**:` を1行で書く
    - 必要なら「注意点」「必要なツール/資料」を短く添える
  - 例:
    ```markdown
    ## 進め方ガイド

    1. まず現状の仕様と制約を確認する
    2. 変更方針を3案メモして最適案を選ぶ
    3. 実装して動作確認する

    **完了の目安**: 想定ケースで動作し、関係者に説明できる状態
    ```
  - 依存は `dependency_ids` に「先行タスクID」を設定する。
  - 実行ガイドが求められたら `guide` を設定して `create_task` / `update_task`。
- 進捗更新:
  - 進捗率は `update_task` の `progress`（0-100）で管理。
  - 完了時の学びは `completion_note` に残す。
- アクションアイテム抽出:
  - `get_task` / `load_project_context` / `search_work_memory` で文脈収集。
  - 抽出案を確認し、同意後に `create_task`。
- このスキルで参照する主なツール:
  - `create_task`, `update_task`, `delete_task`
  - `search_similar_tasks`, `list_tasks`, `get_task`
  - `list_projects`, `load_project_context`
  - `assign_task`, `list_task_assignments`, `list_project_assignments`
  - `create_meeting`, `ask_user_questions`
""".strip(),
    "project": """
- プロジェクト作成:
  1) 目的・スコープを確認
  2) `list_kpi_templates` で候補確認
  3) `create_project`（必要なら `kpi_metrics` を指定）
- プロジェクト更新:
  - `update_project` は goals / key_points / context / KPI / メンバー運用に限定。
  - タスク追加要求は `update_project` ではなく `create_task` を使う。
- メンバー招待:
  - `list_projects` で対象確認
  - `list_project_members` / `list_project_invitations` で重複確認
  - `invite_project_member` を実行
- プロジェクト親子関係:
  - 子プロジェクトとして作成: `create_project` で `parent_project_id` を指定
  - 既存プロジェクトを親に紐付け: `update_project` で `parent_project_id` を設定
  - 紐付け解除: `update_project` で `parent_project_id` を空文字に設定
  - 親プロジェクトのオーナー以外が紐付ける場合、承認リクエストが送信される
- プロジェクト文脈利用:
  - タスクを作る前に必要なら `load_project_context` を読む。
  - 週次要約が必要なら `create_project_summary`。
- このスキルで参照する主なツール:
  - `create_project`, `update_project`, `list_projects`
  - `list_kpi_templates`, `load_project_context`
  - `list_project_members`, `list_project_invitations`, `invite_project_member`
  - `create_project_summary`
""".strip(),
    "phase": """
- フェーズ/マイルストーンは順序を守って扱う。
- 基本フロー:
  1) `list_projects` で対象確認
  2) `list_phases` / `list_milestones` で現状確認
  3) 変更案を確認
  4) `create_phase` / `update_phase` / `delete_phase`
  5) 必要に応じて `create_milestone` / `update_milestone` / `delete_milestone`
- フェーズ配下タスクを作る場合は、対象フェーズを確認して `create_task`。
- このスキルで参照する主なツール:
  - `list_phases`, `get_phase`, `create_phase`, `update_phase`, `delete_phase`
  - `list_milestones`, `create_milestone`, `update_milestone`, `delete_milestone`
  - `create_task`, `list_projects`
""".strip(),
    "meeting": """
- 会議情報は「目的 / 議題 / 決定事項 / 次アクション」を分けて扱う。
- 会議予定作成は `create_meeting` を使い、開始/終了時刻を明示する。
- 日時が曖昧な依頼は `get_current_datetime` で基準時刻を確認してから解釈する。
- アジェンダ運用:
  1) `fetch_meeting_context` で文脈収集
  2) 必要なら `list_agenda_items` で現状確認
  3) `add_agenda_item` / `update_agenda_item` / `delete_agenda_item` / `reorder_agenda_items`
- 重要ガード（アジェンダ操作）:
  - 議題の追加・更新・削除・並び替えに `update_task` を使わない。
  - アジェンダ本文の変更は必ず `add_agenda_item` / `update_agenda_item` / `delete_agenda_item` / `reorder_agenda_items` を使う。
- 確認フロー:
  - 「これでいいですか？」「実行してよいですか？」の確認は、テキストで聞かず `ask_user_questions` を使う。
  - Yes/No 確認は `options: ["はい", "いいえ"]` を基本にする。
- 定例・チェックイン:
  - 定例会情報は `list_recurring_meetings`
  - 共有提案が合意されたら `create_checkin`
  - 過去共有確認は `list_checkins`
- 会議の話題からタスク化する場合:
  - 同意を取り `create_task`、必要なら `assign_task`。
- このスキルで参照する主なツール:
  - `create_meeting`, `get_current_datetime`, `fetch_meeting_context`
  - `add_agenda_item`, `update_agenda_item`, `delete_agenda_item`, `list_agenda_items`, `reorder_agenda_items`
  - `list_recurring_meetings`, `create_checkin`, `list_checkins`
  - `create_task`, `assign_task`
""".strip(),
    "schedule": """
- スケジュール調整では、期限・重要度・固定予定を優先して扱う。
- 今日の集中テーマ調整は `apply_schedule_request` を使う:
  - 集中したい対象 -> `focus_keywords`
  - 避けたい対象 -> `avoid_keywords`
  - 集中タスク数は通常 2-4 件 (`max_focus_tasks`)
- 実行計画の再配置は `schedule_agent_task` を使う。
- 影響確認には `list_tasks`, `get_task`, `list_task_assignments`, `list_projects` を使う。
- このスキルで参照する主なツール:
  - `apply_schedule_request`, `schedule_agent_task`
  - `list_tasks`, `get_task`, `list_task_assignments`, `list_projects`
""".strip(),
    "memory": """
- 記憶操作は「再利用しやすさ」を最優先に短く構造化する。
- ユーザーメモ:
  - 検索: `search_memories`（必要に応じ scope 指定）
  - 追記: `add_to_memory`
  - プロファイル再集約: `refresh_user_profile`
- 仕事メモリ:
  - 検索: `search_work_memory`
  - 一覧: `list_work_memory_index`
  - 詳細: `load_work_memory`
  - 新規: `create_work_memory`
- プロジェクト要約は `create_project_summary` を使う。
- このスキルで参照する主なツール:
  - `search_memories`, `add_to_memory`, `refresh_user_profile`
  - `search_work_memory`, `list_work_memory_index`, `load_work_memory`, `create_work_memory`
  - `create_project_summary`
""".strip(),
    "recurring": """
- 定期タスクは開始条件・頻度・終了条件を先に確認する。
- 例外日やスキップ条件がある場合は登録前に確認する。
- このスキルで参照する主なツール:
  - `create_recurring_task`, `list_recurring_tasks`, `update_recurring_task`, `delete_recurring_task`
""".strip(),
    "browser": """
- ブラウザ操作では、まず再利用可能な手順の有無を確認する:
  1) `search_work_memory` で候補検索
  2) `load_work_memory` で内容確認
  3) 決定論的ステップが作れるなら `run_hybrid_rpa`
  4) そうでなければ `run_browser_task`
- 再利用化を求められたら `register_browser_work_memory`。
- ツール実行結果なしに「完了した」と断定しない。
- このスキルで参照する主なツール:
  - `run_browser_task`, `run_hybrid_rpa`
  - `search_work_memory`, `load_work_memory`, `register_browser_work_memory`
""".strip(),
}


def format_profile_skill_prompts(profiles: tuple[str, ...]) -> str:
    sections: list[str] = []
    for profile in profiles:
        content = PROFILE_SKILL_PROMPTS.get(profile)
        if not content:
            continue
        sections.append(f"## Skill Prompt: {profile}\n{content}")
    return "\n\n".join(sections)
