"""
Enum definitions for the application.

These enums are used across models and provide type-safe status/priority values.
"""

from enum import Enum


class TaskStatus(str, Enum):
    """Task status."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    DONE = "DONE"


class Priority(str, Enum):
    """Priority level for importance and urgency."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EnergyLevel(str, Enum):
    """
    Energy level required for a task.

    HIGH = Heavy task requiring focus and concentration
    MEDIUM = Moderate task requiring some focus
    LOW = Light task that can be done in spare moments
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CreatedBy(str, Enum):
    """Who created the task."""

    USER = "USER"
    AGENT = "AGENT"


class ProjectStatus(str, Enum):
    """Project status."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class ProjectVisibility(str, Enum):
    """Project visibility/privacy setting."""

    PRIVATE = "PRIVATE"  # 個人プロジェクト（自分のみ）
    TEAM = "TEAM"  # チームプロジェクト（メンバー招待可能）


class PhaseStatus(str, Enum):
    """Phase status."""

    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class MilestoneStatus(str, Enum):
    """Milestone status."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class ProjectRole(str, Enum):
    """Role of a member within a project."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class BlockerStatus(str, Enum):
    """Status for task blockers."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class CheckinType(str, Enum):
    """Type of check-in entry."""

    WEEKLY = "weekly"
    ISSUE = "issue"
    GENERAL = "general"


class CheckinItemCategory(str, Enum):
    """Category of structured check-in item."""

    BLOCKER = "blocker"  # 進捗が止まっていること
    DISCUSSION = "discussion"  # 相談したいこと
    UPDATE = "update"  # 進捗報告
    REQUEST = "request"  # 助けてほしいこと


class CheckinItemUrgency(str, Enum):
    """Urgency level of check-in item."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CheckinMood(str, Enum):
    """Mood/condition of member."""

    GOOD = "good"  # 順調
    OKAY = "okay"  # まあまあ
    STRUGGLING = "struggling"  # 厳しい


class InvitationStatus(str, Enum):
    """Status for project invitations."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ActionType(str, Enum):
    """Agent autonomous action types."""

    CHECK_PROGRESS = "CHECK_PROGRESS"  # タスク進捗確認
    ENCOURAGE = "ENCOURAGE"  # 励まし・声かけ
    WEEKLY_REVIEW = "WEEKLY_REVIEW"  # 週次レビュー
    DEADLINE_REMINDER = "DEADLINE_REMINDER"  # 締め切りリマインド
    MORNING_BRIEFING = "MORNING_BRIEFING"  # 朝のブリーフィング


class AgentTaskStatus(str, Enum):
    """Agent task status."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SNOOZED = "SNOOZED"
    FAILED = "FAILED"


class ContentType(str, Enum):
    """Capture content type."""

    TEXT = "TEXT"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"


class MemoryScope(str, Enum):
    """Memory scope."""

    USER = "USER"  # ユーザー個人の記憶
    PROJECT = "PROJECT"  # プロジェクト固有の記憶
    WORK = "WORK"  # 汎用的な仕事の手順・ルール


class MemoryType(str, Enum):
    """Memory type within scope."""

    # UserMemory types
    FACT = "FACT"  # 事実 (子供がいる、等)
    PREFERENCE = "PREFERENCE"  # 好み (朝型、等)
    PATTERN = "PATTERN"  # 傾向 (締め切り直前まで動かない、等)

    # WorkMemory types
    RULE = "RULE"  # 手順・禁則事項


class ToolApprovalMode(str, Enum):
    """Tool approval mode for chat."""

    MANUAL = "manual"
    AUTO = "auto"


class ChatMode(str, Enum):
    """Chat mode."""

    DUMP = "dump"  # 脳内ダンプモード（タスク化促進）
    CONSULT = "consult"  # 相談モード
    BREAKDOWN = "breakdown"  # タスク分解依頼


class MeetingSessionStatus(str, Enum):
    """Meeting session status."""

    PREPARATION = "PREPARATION"  # 準備中（デフォルト）
    IN_PROGRESS = "IN_PROGRESS"  # 会議中
    COMPLETED = "COMPLETED"  # 完了


class IssueStatus(str, Enum):
    """Issue status for feature requests and bug reports."""

    OPEN = "OPEN"  # 投稿直後
    UNDER_REVIEW = "UNDER_REVIEW"  # 検討中
    PLANNED = "PLANNED"  # 対応予定
    IN_PROGRESS = "IN_PROGRESS"  # 対応中
    COMPLETED = "COMPLETED"  # 完了
    WONT_FIX = "WONT_FIX"  # 対応しない


class IssueCategory(str, Enum):
    """Issue category."""

    FEATURE_REQUEST = "FEATURE_REQUEST"  # 機能要望
    BUG_REPORT = "BUG_REPORT"  # バグ報告
    IMPROVEMENT = "IMPROVEMENT"  # 改善提案
    QUESTION = "QUESTION"  # 質問


class GenerationType(str, Enum):
    """Achievement generation type."""

    AUTO = "AUTO"  # 週次自動生成
    MANUAL = "MANUAL"  # 手動生成


class RecurringTaskFrequency(str, Enum):
    """Supported recurrence frequencies for tasks."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    BIMONTHLY = "bimonthly"
    CUSTOM = "custom"  # every N days
