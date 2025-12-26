"""
KPI template catalog.
"""

from app.models.project_kpi import ProjectKpiTemplate, ProjectKpiMetric


_TEMPLATES: list[ProjectKpiTemplate] = [
    ProjectKpiTemplate(
        id="delivery",
        name="納期重視 / デリバリー",
        description="期限が明確な納期重視のプロジェクト向け。",
        category="delivery",
        metrics=[
            ProjectKpiMetric(
                key="completion_rate",
                label="完了率",
                description="完了タスク / 総タスク",
                unit="%",
                direction="up",
                source="tasks",
            ),
            ProjectKpiMetric(
                key="overdue_tasks",
                label="期限超過タスク",
                description="期限を過ぎたタスク数",
                unit="count",
                direction="down",
                source="tasks",
            ),
            ProjectKpiMetric(
                key="remaining_hours",
                label="残作業時間",
                description="残りの見積もり時間合計",
                unit="h",
                direction="down",
                source="tasks",
            ),
        ],
    ),
    ProjectKpiTemplate(
        id="sprint",
        name="スプリント / 開発",
        description="週次など一定のリズムで進める開発向け。",
        category="development",
        metrics=[
            ProjectKpiMetric(
                key="weekly_throughput",
                label="週次スループット",
                description="週に完了したタスク数",
                unit="count",
                direction="up",
                source="tasks",
            ),
            ProjectKpiMetric(
                key="wip_count",
                label="進行中タスク数",
                description="現在進行中のタスク数",
                unit="count",
                direction="down",
                source="tasks",
            ),
            ProjectKpiMetric(
                key="blocked_tasks",
                label="ブロック中タスク",
                description="依存待ちのタスク数",
                unit="count",
                direction="down",
                source="tasks",
            ),
        ],
    ),
    ProjectKpiTemplate(
        id="operations",
        name="運用 / サポート",
        description="運用・サポートの継続業務向け。",
        category="operations",
        metrics=[
            ProjectKpiMetric(
                key="sla_breaches",
                label="SLA違反数",
                description="SLAを超過した件数",
                unit="count",
                direction="down",
                source="manual",
            ),
            ProjectKpiMetric(
                key="avg_resolution_time",
                label="平均解決時間",
                description="解決にかかった平均時間",
                unit="hours",
                direction="down",
                source="manual",
            ),
            ProjectKpiMetric(
                key="backlog_count",
                label="バックログ数",
                description="未処理のバックログ件数",
                unit="count",
                direction="down",
                source="tasks",
            ),
        ],
    ),
    ProjectKpiTemplate(
        id="research",
        name="リサーチ / 探索",
        description="探索・調査が中心のプロジェクト向け。",
        category="research",
        metrics=[
            ProjectKpiMetric(
                key="milestone_completion",
                label="マイルストーン達成率",
                description="達成済み / 総マイルストーン",
                unit="%",
                direction="up",
                source="manual",
            ),
            ProjectKpiMetric(
                key="review_cycles",
                label="レビュー回数",
                description="レビューの反復回数",
                unit="count",
                direction="down",
                source="manual",
            ),
            ProjectKpiMetric(
                key="cycle_time",
                label="サイクルタイム",
                description="開始から示唆獲得までの時間",
                unit="days",
                direction="down",
                source="manual",
            ),
        ],
    ),
    ProjectKpiTemplate(
        id="sales",
        name="営業 / パイプライン",
        description="案件管理・進捗が中心の営業向け。",
        category="sales",
        metrics=[
            ProjectKpiMetric(
                key="stage_velocity",
                label="ステージ速度",
                description="各ステージの平均日数",
                unit="days",
                direction="down",
                source="manual",
            ),
            ProjectKpiMetric(
                key="proposal_rate",
                label="提案完了率",
                description="送付済み / 必要提案件数",
                unit="%",
                direction="up",
                source="manual",
            ),
            ProjectKpiMetric(
                key="win_rate",
                label="成約率",
                description="成約 / 総案件数",
                unit="%",
                direction="up",
                source="manual",
            ),
        ],
    ),
]


def get_kpi_templates() -> list[ProjectKpiTemplate]:
    """Return KPI templates."""
    return _TEMPLATES
