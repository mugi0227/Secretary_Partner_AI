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
    LOW = Light task that can be done in spare moments
    """

    HIGH = "HIGH"
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


class ChatMode(str, Enum):
    """Chat mode."""

    DUMP = "dump"  # 脳内ダンプモード（タスク化促進）
    CONSULT = "consult"  # 相談モード
    BREAKDOWN = "breakdown"  # タスク分解依頼
