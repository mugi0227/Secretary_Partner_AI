# Brain Dump Partner - 進化版要件定義書 (Spec 3.0)

## 1. プロジェクト概要 & 進化の方向性

### 1.1 Core Philosophy (不変の真理)
*   **Zero Friction Input:** 入力コストはゼロでなければならない。「叫ぶ」「撮る」「ただ見ているだけ」でタスクが収集される。
*   **Autonomous Secretary:** Userは「管理」をしない。AIが収集・整理し、Userは「実行」と「承認」だけを行う。
*   **Transparent Partner:** AIはUserの行動（ブラウザ操作）を透明に把握し、言われる前に察して準備する。

### 1.2 新たな構成要素: "The Eye" (Chrome Extension)
Webアプリ単体では実現できない「ユーザーのコンテキスト把握」を担う、最大のセンサー。
従来の「待ち受け型」から「介入型」への進化の鍵となる。

---

## 2. システムアーキテクチャ (Expanded)

```
[ User's Brain ] <--> [ Chrome Extension (The Eye) ] <--> [ Web App (The Brain/Body) ]
```

### 2.1 The Eye (Chrome Extension)
*   **役割:** 視覚・文脈の収集。
*   **Level 1: Snapshot (Manual Trigger)**
    *   機能: ユーザー操作（ショートカット/ボタン）で現在ページのスクショ・URL・選択テキストを送信。
    *   用途: 「これ覚えておいて」の爆速化。
*   **Level 2: Context Awareness (Passive)**
    *   機能: 特定ドメイン（Gmail, Calendar, GitHub）の閲覧を検知し、メタデータ（誰からのメールか、何日の予定か）を抽出。
    *   用途: 裏側での「関連タスク検索」「スケジュール空き枠確認」。
*   **Level 3: Interceptor (Active)**
    *   機能: 会議字幕(Teams)やチャットログをリアルタイムで監視し、タスク候補を検出。
    *   用途: 「今の発言、タスクにしますか？」という能動的提案。

### 2.2 The Brain (Backend API & Agents)
*   **Capture API:** 拡張機能からの入力を受け取る単一の入り口。
*   **Multimodal Analysis:** 画像(Gemini Pro Vision)とテキスト(Gemini Flash)を使い分け、コストと精度のバランスを取る。
*   **Secretary Agent:** 収集された情報を、「タスク」にするか「記憶(Memory)」にするか「無視」するかを判断する。

### 2.3 The Body (Frontend Web App)
*   **Notification/Inbox:** 拡張機能から飛んできた「提案」をユーザーが確認する場所。
*   **Auto-Fill:** 既存の `TaskFormModal` に、拡張機能で解析したデータを注入する仕組み。

---

## 3. 機能要件詳細

### 3.1 収集フェーズ (Capture)
*   **Input Types:**
    *   `TEXT`: 思考の掃き出し。
    *   `IMAGE`: スクリーンショット、ホワイトボードの写真。
    *   `PAGE_CONTEXT (New)`: URL, DOM構造, 選択範囲。
*   **Process:**
    1.  Rawデータを受け取る。
    2.  LLMが解析し、構造化データ（JSON）に変換。
    3.  既存タスクとの重複チェック (Dedup)。

### 3.2 提案フェーズ (Propose) - New!
ユーザーがいきなり「タスク登録」まですると心理的ハードルが高い。
一度「提案（Draft）」としてプールし、ワンクリックで確定させる。

*   **Draft Task:**
    *   「メールからタスクを検出しました: 『来週の資料作成』」
    *   アクション: [承認して登録] [修正して登録] [破棄]

### 3.3 実行支援フェーズ (Engage)
*   **Context Injection:**
    *   タスク実行時、「元ネタ」となったURLやスクショを即座に表示。
    *   「あのメールどこだっけ？」をなくす。

---

## 4. データモデル拡張案

### 4.1 Update: Capture
```python
class Capture(BaseModel):
    id: UUID
    content_type: ContentType # TEXT, IMAGE, PAGE_CONTEXT
    source_url: Optional[str] # 取得元URL
    page_title: Optional[str] # ページタイトル
    screenshot_url: Optional[str] # Cloud Storage URL
    dom_content: Optional[str] # ページの主要テキスト
    processed: bool
    detected_tasks: list[DraftTask] # AIが検出したタスク候補
```

### 4.2 New: DraftTask
ユーザーの承認待ち状態のタスク候補。
```python
class DraftTask(BaseModel):
    title: str
    description: str
    source_capture_id: UUID
    confidence_score: float # AIの自信あり度 (0.0-1.0)
```
