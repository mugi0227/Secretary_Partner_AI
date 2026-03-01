# 現行バックエンドへの Priority 仕様フィードバック

## 1. この文書の目的

この文書は、`nagi-mobile` 側で整理した Priority 設計を、現行の `Secretary_Partner_AI` バックエンドへどうフィードバックするかをまとめたものである。

ここで言う Priority とは、単なる `Top3` の並び替えではなく、

- 何が今日の `Must-do` なのか
- 何が `Could-do` として勧められるのか
- なぜその判定になったのか

を説明可能な形で返す仕組みを指す。

## 2. 結論

現行バックエンドは、優先度判定の土台としてはかなり良い。

特に次の3つは再利用価値が高い。

- `slack_engine.py`
  - チェーン全体の危険度と実効締切の考え方
- `scheduler_service.py`
  - 今日の可処分時間、会議差し引き、依存関係を踏まえた配分
- `task_heartbeat_service.py`
  - 悪化の検知と通知の考え方

一方で、ユーザーに返す最終出力はまだ弱い。

弱い点は主に次の3つである。

- `Top3` という最終表現に圧縮しすぎている
- 「なぜそれが上位なのか」の説明がない
- 「今日やるべき」と「今日やるとよい」が明確に分かれていない

したがって、現行バックエンドに対する基本方針は次の通りとする。

- 判定基盤は活かす
- 最終出力モデルを作り直す
- `Must-do / Could-do / reason / feasibility` を返せるようにする

## 3. 現行ロジックの評価

### 3.1 良い点

#### `slack_engine` は危険度判定の核として筋が良い

- タスク単体ではなくチェーン全体で危険度を見ている
- `effective_deadline` の発想がある
- `available_minutes / required_minutes` で危険度を計算している

これは `chain_at_risk_today` の判定基盤としてそのまま活かせる。

#### `scheduler_service` は「今日できる量」を真面目に見ている

- 会議や固定予定を差し引いている
- 容量超過を検知している
- 依存関係とピン留めを見ている

これは `feasibility_status` の計算基盤として使いやすい。

#### `task_heartbeat_service` は悪化監視の思想が良い

- 放置や危険度の悪化を通知対象として扱っている
- Today 表示と別レイヤーで危険を検知する発想がある

これは `warning_code` や `staleness` 系の signal に接続できる。

### 3.2 弱い点

#### `Top3` が強すぎる

現行では、最終的に `top3_ids` へ落として返す構造が強い。

これだと、

- `Must-do` が 4 件以上ある日
- 今日はまだ危険ではないが着手した方がよいタスク
- やれない blocked task ではなく blocker を上げるべき状況

を表現しづらい。

#### explanation layer がない

ユーザーは「なぜこれなのか」が分からないと信頼しづらい。

必要なのは数値スコアだけではなく、次のような説明である。

- 今日は期限
- 3 日放置されている
- 後続の締切が近い
- 今日の通常工数では重い

#### 実行可能性の表現がない

「今日やるべき」と「今日の通常工数で収まる」は別である。

そのため、優先度の出力には次が必要である。

- `fits_today`
- `stretched_today`
- `not_feasible_today`

## 4. フィードバックとして入れたい Priority モデル

### 4.1 共通 signal layer

まず、優先度の土台となる signal を共通化する。

最低限必要なのは次の項目である。

- `importance`
- `urgency`
- `due_date`
- `pinned_date`
- `remaining_minutes`
- `available_minutes_today`
- `effective_deadline`
- `slack_ratio`
- `is_blocked`
- `dependency_ids`

将来的に追加したいものは次である。

- `context_score`
- `postponement_count`
- `staleness_score`

### 4.2 Must-do

`Must-do` は score 上位ではなく、条件ベースで判定する。

v1 の単独条件は次でよい。

1. `overdue`
2. `due_today`
3. `pinned_today`
4. `chain_at_risk_today`

`chain_at_risk_today` の v1 条件は次を推奨する。

- actionable である
- 実効締切が存在する
- `slack_ratio < 1.2`

加えて blocked task については、次の方針を入れる。

- blocked task 自身は直接 Must-do にしない
- 代わりに blocker を先に Must-do に昇格させる
- blocked task は follow-up として見せる

### 4.3 Could-do

`Could-do` は `Must-do` の弱い版ではなく、別フローで選ぶ。

考え方は次である。

- Must-do ではない
- blocked ではない
- 今日やると前進しやすい

`Could-do` の score は新設が必要である。

v1 の候補式は次でよい。

```text
could_do_score =
  0.20 * importance_score +
  0.15 * urgency_score +
  0.20 * future_risk_reduction_score +
  0.20 * startability_score +
  0.15 * fit_today_score +
  0.10 * context_score
```

ここで言う `future_risk_reduction_score` は、将来の危険を減らせるかを見る指標であり、`due_soon` と `slack_attention` の組み合わせで表現できる。

### 4.4 reason layer

各 item には explanation を返す。

最低限必要なのは次である。

- `reason_codes`
- `primary_reason`
- `secondary_reason`

reason code の v1 候補:

- `overdue`
- `due_today`
- `pinned_today`
- `chain_at_risk`
- `blocks_near_deadline`
- `blocked_by`
- `large_for_today`
- `good_to_start_today`
- `small_enough_for_today`
- `reduces_future_risk`

### 4.5 feasibility layer

優先度と別軸で、今日の実行可能性を返す。

- `fits_today`
- `stretched_today`
- `not_feasible_today`

考え方は次である。

- `Must-do + fits_today`
  - 今日やるべきで、通常工数でも進めやすい
- `Must-do + stretched_today`
  - 今日やるべきだが、そのままでは重い
- `Must-do + not_feasible_today`
  - 今日やるべきだが、そのままでは厳しいため、分解や支援依頼が必要

## 5. 現行バックエンドで残すもの / 変えるもの

### 5.1 残すもの

- `slack_engine` の危険度計算
- `scheduler_service` の容量計算
- `task_heartbeat_service` の悪化検知

### 5.2 作り直すもの

- `top3_ids` を最終成果物として返す考え方
- score のみで終わる出力
- blocked task をそのまま候補に出す動き

### 5.3 新設するもの

- `priority_signal_service`
  - signal 集約
- `must_do_classifier`
  - 条件ベース判定
- `could_do_ranker`
  - score ベース推薦
- `priority_explainer`
  - reason 生成
- `mobile_priority_service` または同等の集約層
  - API 返却形状の構築

## 6. 現行 API への反映イメージ

現行 API を壊さずに進めるなら、段階的には次がよい。

### Phase 1. 内部 signal の整備

まず既存の `slack_ratio`、`effective_deadline`、`remaining_minutes`、`available_minutes_today` を整理する。

### Phase 2. 専用 response model の追加

`/today/top3` を直接拡張するより、優先度専用の返却形状を作る方が安全である。

候補:

- `/mobile/today-priority`
- `/today/priority`

### Phase 3. Must-do 導入

次を返せるようにする。

- `must_do[]`
- `could_do[]`
- `later_count`
- `warnings[]`

### Phase 4. reason / feasibility 導入

各 item に次を付ける。

- `reason_codes`
- `primary_reason`
- `secondary_reason`
- `feasibility_status`
- `suggested_actions`

## 7. 実装順の提案

1. `slack_ratio`, `effective_deadline`, `available_minutes_today` を返せる状態を安定化する
2. `Must-do` の条件分類を追加する
3. blocker promotion を追加する
4. `feasibility_status` を導入する
5. `Could-do` score を追加する
6. reason layer を追加する
7. モバイル向け response を追加する

## 8. 補足

このフィードバックの要点は単純である。

- 現行ロジックは捨てるべきではない
- しかし `Top3` を最終成果物にするのは弱い
- 今必要なのは、判定基盤の作り直しではなく、出力モデルの作り直しである

優先度を「何位か」ではなく、

- 今日やる責任があるか
- 今日やると前進しやすいか
- なぜそう言えるか

まで返せるようにすると、現行アプリでも体験がかなり改善しやすい。
