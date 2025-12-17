# Secretary Partner AI - 追加機能実装計画

## 現状（実装済み）

### Frontend
- Dashboard（AgentCard, Top3Card, WeeklyProgress）
- Tasks（Kanban Board）
- Projects（一覧表示）
- Chat Widget（ストリーミング対応）
- テーマ切り替え

### Backend API
- Tasks CRUD（GET/POST/PATCH/DELETE）
- Projects CRUD
- Chat（POST /api/chat）
- Top3（GET /api/today/top3）
- Heartbeat（POST /api/heartbeat）

---

## 追加実装タスク（優先度順）

### 1. タスク手動作成UI [最優先]

**目的**: チャット以外でもタスクを直接作成・編集できるようにする

**実装内容**:
- `TaskFormModal.tsx` - タスク作成/編集モーダル
- TasksPageに「+新規タスク」ボタン追加
- Top3Cardから編集モーダルへの導線

**フィールド**:
- title（必須）
- description
- importance（HIGH/MEDIUM/LOW）
- urgency（HIGH/MEDIUM/LOW）
- energy_level（HIGH/LOW）- AIが判断、手動変更可
- estimated_minutes
- due_date
- project_id

**API**: 既存の `POST /api/tasks`, `PATCH /api/tasks/:id` を利用

---

### 2. Achievement Summary（成果サマリー）ページ [高優先]

**目的**: 半期ごとの成果を振り返り、上司との面談でアピールできるレポートを生成

**期間区分**:
- 上期: 4月〜9月末
- 下期: 10月〜3月末

**実装内容**:
- `AchievementPage.tsx` - 新規ページ
- Sidebarに「Achievement」メニュー追加
- 期間選択UI（上期/下期 + 年度）
- 完了タスクの集計・カテゴリ分類
- AI要約生成（オプション）

**表示項目**:
- 完了タスク数
- プロジェクト別成果
- 主要な達成事項（DONEタスクから抽出）
- 成長ポイント（任意入力 or AI提案）

**バックエンド追加**:
- `GET /api/achievements/summary?start_date=&end_date=` - 期間内の完了タスク集計
- または既存の `GET /api/tasks?status=DONE&start=&end=` を拡張

---

### 3. Settings（設定）ページ [中優先]

**目的**: ユーザー設定を管理

**実装内容**:
- `SettingsPage.tsx` - 新規ページ
- Sidebarの設定ボタンにリンク

**設定項目**:
- テーマ（Light/Dark）- 既存機能を移動
- 通知設定（Quiet Hours）
- 表示言語（日本語/英語）- 将来対応
- ユーザー名

**ストレージ**: LocalStorage（MVP）、将来的にバックエンドAPI

---

### 4. WeeklyProgress 実データ連携 [中優先]

**目的**: 現在ダミーデータの週次進捗を実データに

**実装内容**:
- `useWeeklyProgress.ts` hook作成
- 週間の完了タスク数を集計
- 目標設定機能（オプション）

**バックエンド追加**:
- `GET /api/stats/weekly` - 週間統計API
  - 日別完了タスク数
  - 今週の合計

---

### 5. 朝のブリーフィング機能 [低優先]

**目的**: AgentCardの「朝のブリーフィング」ボタンを機能化

**実装内容**:
- ボタンクリックでAIが今日の概要を説明
- Chat APIを利用（特別なプロンプト送信）
- モーダルまたはChat Widgetで表示

**フロー**:
1. ボタンクリック
2. `POST /api/chat` に `mode: "briefing"` 送信
3. AIが今日のTop3タスク、予定、アドバイスを返す

---

## 実装順序

```
1. AgentCardメッセージ更新（即座に）✅
2. タスク手動作成UI（TaskFormModal）
3. Achievement Summaryページ
4. Settingsページ
5. WeeklyProgress実データ
6. 朝のブリーフィング
```

---

## Critical Files

### 修正対象
- `frontend/src/components/dashboard/AgentCard.tsx` - メッセージ変更
- `frontend/src/components/layout/Sidebar.tsx` - Achievement/Settingsリンク追加
- `frontend/src/App.tsx` - 新規ルート追加

### 新規作成
- `frontend/src/components/tasks/TaskFormModal.tsx`
- `frontend/src/components/tasks/TaskFormModal.css`
- `frontend/src/pages/AchievementPage.tsx`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/hooks/useWeeklyProgress.ts`

### バックエンド追加（必要に応じて）
- `backend/app/api/stats.py` - 統計API
- `backend/app/api/achievements.py` - 成果API
