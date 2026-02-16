from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError

from app.core.logger import logger
from app.interfaces.heartbeat_event_repository import IHeartbeatEventRepository
from app.interfaces.heartbeat_settings_repository import IHeartbeatSettingsRepository
from app.interfaces.chat_session_repository import IChatSessionRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.enums import Priority, TaskStatus
from app.models.heartbeat import (
    HeartbeatEventCreate,
    HeartbeatIntensity,
    HeartbeatSeverity,
    HeartbeatSettings,
    HeartbeatSettingsUpdate,
)
from app.models.project import Project
from app.models.task import Task
from app.services.llm_utils import generate_text
from app.services.task_utils import get_effective_estimated_minutes, is_parent_task
from app.utils.datetime_utils import UTC, ensure_utc, normalize_timezone, now_utc

HEARTBEAT_SESSION_PREFIX = "heartbeat-"
LLM_MESSAGE_MAX_LENGTH = 900
LLM_MAX_RETRIES = 3
LLM_TEMPERATURE = 0.4


class HeartbeatLLMMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=LLM_MESSAGE_MAX_LENGTH)


@dataclass(frozen=True)
class HeartbeatRiskItem:
    task: Task
    risk_score: float
    severity: HeartbeatSeverity
    days_remaining: Optional[int]
    required_days: Optional[int]
    slack_days: Optional[int]
    estimated_minutes: int
    estimate_missing: bool


class TaskHeartbeatService:
    def __init__(
        self,
        task_repo: ITaskRepository,
        chat_repo: IChatSessionRepository,
        settings_repo: IHeartbeatSettingsRepository,
        event_repo: IHeartbeatEventRepository,
        user_repo: IUserRepository,
        project_repo: Optional[IProjectRepository] = None,
        llm_provider: Optional[ILLMProvider] = None,
        task_assignment_repo: Optional[ITaskAssignmentRepository] = None,
    ):
        self._task_repo = task_repo
        self._chat_repo = chat_repo
        self._settings_repo = settings_repo
        self._event_repo = event_repo
        self._user_repo = user_repo
        self._project_repo = project_repo
        self._llm_provider = llm_provider
        self._task_assignment_repo = task_assignment_repo

    async def run(self, user_id: str, now: Optional[datetime] = None) -> dict:
        now_utc_value = ensure_utc(now) or now_utc()
        settings = await self._get_or_create_settings(user_id)
        if not settings.enabled:
            return {"status": "disabled", "evaluated": 0, "notified": 0}

        timezone = await self._get_timezone(user_id)
        local_now = now_utc_value.astimezone(ZoneInfo(timezone))
        if not self._is_within_window(
            local_now.time(),
            settings.notification_window_start,
            settings.notification_window_end,
        ):
            return {"status": "outside_window", "evaluated": 0, "notified": 0}

        tasks = await self._get_tasks_for_user(user_id)
        candidate_tasks = self._filter_candidates(tasks)
        if not candidate_tasks:
            return {"status": "no_tasks", "evaluated": 0, "notified": 0}

        risk_items = self._score_tasks(candidate_tasks, settings, timezone, now_utc_value)
        if not risk_items:
            return {"status": "no_risks", "evaluated": 0, "notified": 0}

        cooldown_since = now_utc_value - timedelta(hours=settings.cooldown_hours_per_task)
        recent_events = await self._event_repo.list_by_user_since(user_id, cooldown_since)
        recent_task_ids = {event.task_id for event in recent_events if event.task_id}
        eligible_items = [item for item in risk_items if item.task.id not in recent_task_ids]
        eligible_items = [item for item in eligible_items if item.severity != HeartbeatSeverity.LOW]
        if not eligible_items:
            return {
                "status": "cooldown",
                "evaluated": len(risk_items),
                "notified": 0,
            }

        start_of_day = self._start_of_day_utc(local_now)
        sent_today = await self._event_repo.count_by_user_since(user_id, start_of_day)
        remaining = max(0, settings.notification_limit_per_day - sent_today)
        if remaining <= 0:
            return {
                "status": "limit_reached",
                "evaluated": len(risk_items),
                "notified": 0,
                "sent_today": sent_today,
                "limit": settings.notification_limit_per_day,
            }

        eligible_items = self._sort_risks(eligible_items)
        selected = eligible_items[:remaining]
        notified = 0

        for item in selected:
            session_id = self._build_session_id(now_utc_value)
            project = await self._get_project_for_task(user_id, item.task)
            message = self._build_chat_message(
                item,
                timezone,
                now_utc_value,
                settings.daily_capacity_per_task_minutes,
                settings.heartbeat_intensity,
                project,
            )
            chat_message = await self._chat_repo.add_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=message,
                title=self._build_session_title(item, timezone),
            )
            await self._event_repo.create(
                HeartbeatEventCreate(
                    user_id=user_id,
                    task_id=item.task.id,
                    severity=item.severity,
                    risk_score=item.risk_score,
                    notification_id=None,
                    metadata=self._build_metadata(item, timezone, session_id, chat_message.id),
                    is_read=False,
                )
            )
            notified += 1

        return {
            "status": "success",
            "evaluated": len(risk_items),
            "notified": notified,
            "sent_today": sent_today + notified,
            "limit": settings.notification_limit_per_day,
        }

    async def get_status(self, user_id: str, now: Optional[datetime] = None) -> dict:
        now_utc_value = ensure_utc(now) or now_utc()
        settings = await self._get_or_create_settings(user_id)
        timezone = await self._get_timezone(user_id)
        local_now = now_utc_value.astimezone(ZoneInfo(timezone))

        tasks = await self._get_tasks_for_user(user_id)
        candidate_tasks = self._filter_candidates(tasks)
        risk_items = self._score_tasks(candidate_tasks, settings, timezone, now_utc_value)
        risk_items = self._sort_risks(risk_items)

        start_of_day = self._start_of_day_utc(local_now)
        sent_today = await self._event_repo.count_by_user_since(user_id, start_of_day)

        return {
            "evaluated": len(risk_items),
            "risk_level": self._risk_level(risk_items),
            "top_risks": risk_items[:10],
            "evaluated_at": now_utc_value,
            "sent_today": sent_today,
            "limit": settings.notification_limit_per_day,
        }

    async def _get_or_create_settings(self, user_id: str) -> HeartbeatSettings:
        settings = await self._settings_repo.get(user_id)
        if settings:
            return settings
        return await self._settings_repo.upsert(user_id, HeartbeatSettingsUpdate())

    async def _get_timezone(self, user_id: str) -> str:
        try:
            user = await self._user_repo.get(UUID(user_id))
        except ValueError:
            user = None
        return normalize_timezone(user.timezone if user else None)

    async def _get_tasks_for_user(self, user_id: str) -> list[Task]:
        tasks = await self._task_repo.list(
            user_id=user_id,
            include_done=False,
            limit=1000,
        )
        if not self._task_assignment_repo:
            return tasks

        assignments_all = await self._task_assignment_repo.list_all_for_user(user_id)
        assignees_by_task: dict[UUID, set[str]] = {}
        for assignment in assignments_all:
            assignees_by_task.setdefault(assignment.task_id, set()).add(assignment.assignee_id)

        owned_tasks = [
            task
            for task in tasks
            if task.id not in assignees_by_task or user_id in assignees_by_task[task.id]
        ]

        assignments_for_me = await self._task_assignment_repo.list_for_assignee(user_id)
        assigned_ids = [assignment.task_id for assignment in assignments_for_me]
        assigned_tasks: list[Task] = []
        if assigned_ids:
            get_many = getattr(self._task_repo, "get_many", None)
            if callable(get_many):
                assigned_tasks = await get_many(assigned_ids)
            else:
                for task_id in assigned_ids:
                    task = await self._task_repo.get(user_id, task_id)
                    if task:
                        assigned_tasks.append(task)

        task_map = {task.id: task for task in owned_tasks}
        for task in assigned_tasks:
            task_map[task.id] = task
        return list(task_map.values())

    async def _get_project_for_task(self, user_id: str, task: Task) -> Optional[Project]:
        if not self._project_repo or not task.project_id:
            return None
        try:
            return await self._project_repo.get(user_id, task.project_id)
        except Exception as exc:
            logger.warning(f"Failed to fetch project for task {task.id}: {exc}")
        return None

    def _filter_candidates(self, tasks: list[Task]) -> list[Task]:
        if not tasks:
            return []
        task_map = {task.id: task for task in tasks}
        filtered: list[Task] = []
        for task in tasks:
            if task.status in {TaskStatus.DONE, TaskStatus.WAITING}:
                continue
            if task.is_fixed_time:
                continue
            if self._is_same_day_task(task):
                continue
            if is_parent_task(task, tasks):
                continue
            if self._is_blocked(task, task_map):
                continue
            filtered.append(task)
        return filtered

    @staticmethod
    def _is_same_day_task(task: Task) -> bool:
        """着手可能日と期限が同日のタスクはリスク監視対象外"""
        if not task.start_not_before or not task.due_date:
            return False
        start = ensure_utc(task.start_not_before)
        due = ensure_utc(task.due_date)
        if start is None or due is None:
            return False
        return start.date() == due.date()

    def _is_blocked(self, task: Task, task_map: dict[UUID, Task]) -> bool:
        if not task.dependency_ids:
            return False
        for dep_id in task.dependency_ids:
            dep_task = task_map.get(dep_id)
            if dep_task and dep_task.status != TaskStatus.DONE:
                return True
        return False

    def _score_tasks(
        self,
        tasks: list[Task],
        settings: HeartbeatSettings,
        user_timezone: str,
        now: datetime,
    ) -> list[HeartbeatRiskItem]:
        if not tasks:
            return []
        importance_scores = {
            Priority.HIGH: 16,
            Priority.MEDIUM: 8,
            Priority.LOW: 4,
        }

        risk_items: list[HeartbeatRiskItem] = []
        local_now = now.astimezone(ZoneInfo(user_timezone))
        today = local_now.date()

        for task in tasks:
            raw_estimated_minutes = get_effective_estimated_minutes(task, tasks)
            estimate_missing = raw_estimated_minutes <= 0
            estimated_minutes = (
                raw_estimated_minutes
                if raw_estimated_minutes > 0
                else settings.daily_capacity_per_task_minutes
            )

            required_days = max(
                1,
                int(math.ceil(estimated_minutes / settings.daily_capacity_per_task_minutes)),
            )

            days_remaining = self._calculate_days_remaining(task, today, user_timezone)
            slack_days = None
            if days_remaining is not None:
                # +1 because the due date itself is an available working day
                slack_days = (days_remaining + 1) - required_days

            time_pressure = self._time_pressure_score(slack_days)
            staleness_score = self._staleness_score(task, now)
            importance_score = importance_scores.get(task.importance, 4)
            uncertainty_score = 12 if estimate_missing else 0
            overdue_penalty = 10 if days_remaining is not None and days_remaining < 0 else 0

            risk_score = (
                importance_score
                + time_pressure
                + staleness_score
                + uncertainty_score
                + overdue_penalty
            )

            severity = self._severity_from_slack(slack_days, risk_score)

            risk_items.append(
                HeartbeatRiskItem(
                    task=task,
                    risk_score=risk_score,
                    severity=severity,
                    days_remaining=days_remaining,
                    required_days=required_days if days_remaining is not None else None,
                    slack_days=slack_days,
                    estimated_minutes=estimated_minutes,
                    estimate_missing=estimate_missing,
                )
            )

        return risk_items

    def _calculate_days_remaining(self, task: Task, today, user_timezone: str) -> Optional[int]:
        if not task.due_date:
            return None
        due_date = ensure_utc(task.due_date)
        if due_date is None:
            return None
        due_local = due_date.astimezone(ZoneInfo(user_timezone)).date()
        effective_start = today
        if task.start_not_before:
            start_local = ensure_utc(task.start_not_before)
            if start_local:
                start_date = start_local.astimezone(ZoneInfo(user_timezone)).date()
                if start_date > effective_start:
                    effective_start = start_date
        return (due_local - effective_start).days

    def _time_pressure_score(self, slack_days: Optional[int]) -> int:
        if slack_days is None:
            return 0
        if slack_days <= -1:
            return 40
        if slack_days == 0:
            return 35
        if slack_days == 1:
            return 28
        if slack_days == 2:
            return 20
        if slack_days == 3:
            return 12
        return 6

    def _staleness_score(self, task: Task, now: datetime) -> int:
        updated_at = ensure_utc(task.updated_at)
        if not updated_at:
            return 0
        days_since = (now - updated_at).days
        if days_since >= 14:
            return 20
        if days_since >= 7:
            return 12
        if days_since >= 3:
            return 6
        return 0

    def _severity_from_slack(
        self,
        slack_days: Optional[int],
        risk_score: float,
    ) -> HeartbeatSeverity:
        if slack_days is not None:
            if slack_days < 0:
                return HeartbeatSeverity.CRITICAL
            if slack_days <= 1:
                return HeartbeatSeverity.HIGH
            if slack_days <= 3:
                return HeartbeatSeverity.MEDIUM
            return HeartbeatSeverity.LOW
        if risk_score >= 50:
            return HeartbeatSeverity.HIGH
        if risk_score >= 30:
            return HeartbeatSeverity.MEDIUM
        return HeartbeatSeverity.LOW

    def _sort_risks(self, items: list[HeartbeatRiskItem]) -> list[HeartbeatRiskItem]:
        severity_weight = {
            HeartbeatSeverity.CRITICAL: 3,
            HeartbeatSeverity.HIGH: 2,
            HeartbeatSeverity.MEDIUM: 1,
            HeartbeatSeverity.LOW: 0,
        }
        return sorted(
            items,
            key=lambda item: (
                -severity_weight.get(item.severity, 0),
                -item.risk_score,
                ensure_utc(item.task.due_date) or datetime.max.replace(tzinfo=UTC),
            ),
        )

    def _risk_level(self, items: list[HeartbeatRiskItem]) -> str:
        if not items:
            return "low"
        top = items[0].severity
        if top in {HeartbeatSeverity.CRITICAL, HeartbeatSeverity.HIGH}:
            return "high"
        if top == HeartbeatSeverity.MEDIUM:
            return "medium"
        return "low"

    def _build_chat_message(
        self,
        item: HeartbeatRiskItem,
        user_timezone: str,
        now: datetime,
        daily_capacity_minutes: int,
        intensity: HeartbeatIntensity,
        project: Optional[Project],
    ) -> str:
        reasons = self._build_reason_lines(item, now, daily_capacity_minutes)
        status_lines = self._build_status_lines(item, user_timezone)
        task_context = self._build_task_context(item.task)
        project_context = self._build_project_context(project)

        llm_message = self._generate_llm_message(
            item=item,
            user_timezone=user_timezone,
            reasons=reasons,
            status_lines=status_lines,
            task_context=task_context,
            project=project,
            project_context=project_context,
            intensity=intensity,
        )
        if llm_message:
            return llm_message

        return self._build_fallback_message(
            item=item,
            user_timezone=user_timezone,
            now=now,
            daily_capacity_minutes=daily_capacity_minutes,
            project=project,
            reasons=reasons,
            status_lines=status_lines,
            task_context=task_context,
        )

    def _build_fallback_message(
        self,
        item: HeartbeatRiskItem,
        user_timezone: str,
        now: datetime,
        daily_capacity_minutes: int,
        project: Optional[Project],
        reasons: Optional[list[str]] = None,
        status_lines: Optional[list[str]] = None,
        task_context: Optional[str] = None,
    ) -> str:
        intro = f"「{item.task.title}」について、少し気になったので声をかけています。"

        if reasons is None:
            reasons = self._build_reason_lines(item, now, daily_capacity_minutes)
        if status_lines is None:
            status_lines = self._build_status_lines(item, user_timezone)
        if task_context is None:
            task_context = self._build_task_context(item.task)

        project_summary = self._build_project_summary(project)

        closing = (
            "もし今の状況や次の一手が分かれば教えてください。"
            "必要なら分割や期限調整も一緒に考えます。"
        )

        lines = [intro]
        if project_summary:
            lines.append(f"プロジェクト: {project_summary}")
        if task_context:
            lines.append(f"メモ: {task_context}")
        if reasons:
            lines.append("気になった理由:")
            lines.extend([f"- {reason}" for reason in reasons])
        if status_lines:
            lines.append("目安:")
            lines.extend([f"- {line}" for line in status_lines])
        lines.append(closing)
        message = "\n".join(lines)
        return self._ensure_task_link(message, item.task.id)

    def _build_status_lines(self, item: HeartbeatRiskItem, user_timezone: str) -> list[str]:
        due_date = item.task.due_date
        due_text = None
        if due_date:
            due_local = ensure_utc(due_date).astimezone(ZoneInfo(user_timezone))
            due_text = due_local.strftime("%m/%d")

        status_lines = []
        if item.days_remaining is not None:
            if item.days_remaining < 0:
                status_lines.append(f"期限は {abs(item.days_remaining)}日前に過ぎています")
            elif item.days_remaining == 0:
                status_lines.append("期限は今日です")
            else:
                status_lines.append(f"期限まであと {item.days_remaining}日")
        if item.required_days is not None:
            status_lines.append(f"必要日数の目安 {item.required_days}日")
        if item.slack_days is not None:
            if item.slack_days < 0:
                status_lines.append(f"必要日数が {abs(item.slack_days)}日足りない見込み")
            else:
                status_lines.append(f"余裕 {item.slack_days}日")
        if item.estimated_minutes > 0:
            status_lines.append(f"見積り {item.estimated_minutes}分")
        if item.task.progress is not None and 0 < item.task.progress < 100:
            status_lines.append(f"進捗 {item.task.progress}%")
        if due_text:
            status_lines.append(f"期限 {due_text}")
        return status_lines

    def _build_reason_lines(
        self,
        item: HeartbeatRiskItem,
        now: datetime,
        daily_capacity_minutes: int,
    ) -> list[str]:
        reasons: list[str] = []
        if item.slack_days is not None:
            if item.slack_days < 0:
                reasons.append("期限までの時間に対して必要日数が足りなさそうです")
            elif item.slack_days <= 1:
                reasons.append("期限に対して余裕が少なめです")
        else:
            reasons.append("期限が未設定なので、重要度や更新間隔から確認しています")

        updated_at = ensure_utc(item.task.updated_at)
        if updated_at:
            days_since = (now - updated_at).days
            if days_since >= 7:
                reasons.append(f"更新が {days_since}日ほど空いています")

        if item.estimate_missing:
            reasons.append(f"見積りが未設定なので、1日{daily_capacity_minutes}分で仮に計算しました")

        if item.task.importance == Priority.HIGH:
            reasons.append("重要度が高めに設定されています")

        if not reasons:
            reasons.append("念のため進捗を確認しています")
        return reasons[:3]

    def _build_task_context(self, task: Task) -> Optional[str]:
        parts = []
        if task.purpose:
            parts.append(task.purpose.strip())
        if task.description:
            parts.append(task.description.strip())
        if not parts:
            return None
        text = " / ".join([part for part in parts if part])
        text = " ".join(text.split())
        return self._truncate_text(text, 120)

    def _build_project_summary(self, project: Optional[Project]) -> Optional[str]:
        if not project:
            return None
        name = project.name.strip() if project.name else ""
        detail_source = project.context_summary or project.description
        detail = self._truncate_text(detail_source, 120) if detail_source else None
        if detail and name:
            return f"{name} / {detail}"
        if detail:
            return detail
        return name or None

    def _build_project_context(self, project: Optional[Project]) -> Optional[str]:
        if not project:
            return None
        lines = []
        if project.name:
            lines.append(f"プロジェクト名: {project.name.strip()}")
        if project.description:
            lines.append(f"概要: {self._truncate_text(project.description, 160)}")
        if project.context_summary:
            lines.append(f"文脈: {self._truncate_text(project.context_summary, 200)}")
        if project.goals:
            goals = [self._truncate_text(goal, 60) for goal in project.goals[:3]]
            lines.append(f"ゴール: {', '.join(goals)}")
        if project.key_points:
            points = [self._truncate_text(point, 60) for point in project.key_points[:3]]
            lines.append(f"重要ポイント: {', '.join(points)}")
        if not lines:
            return None
        return "\n".join(lines)

    def _truncate_text(self, text: str, limit: int) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        if limit <= 1:
            return cleaned[:limit]
        return f"{cleaned[: limit - 1]}…"

    def _intensity_note(self, intensity: HeartbeatIntensity) -> str:
        if isinstance(intensity, HeartbeatIntensity):
            key = intensity.value
        else:
            key = str(intensity or HeartbeatIntensity.STANDARD.value)
        mapping = {
            "gentle": "とてもやさしく、安心感を優先するトーン",
            "standard": "やさしく落ち着いたトーン",
            "firm": "丁寧だが少し背中を押すトーン",
        }
        return mapping.get(key, mapping["standard"])

    def _build_llm_prompt(
        self,
        item: HeartbeatRiskItem,
        user_timezone: str,
        reasons: list[str],
        status_lines: list[str],
        task_context: Optional[str],
        project_context: Optional[str],
        intensity: HeartbeatIntensity,
        project: Optional[Project],
    ) -> str:
        task_title = " ".join(item.task.title.split()) if item.task.title else ""
        due_text = "期限なし"
        if item.task.due_date:
            due_local = ensure_utc(item.task.due_date).astimezone(ZoneInfo(user_timezone))
            due_text = due_local.strftime("%m/%d")

        importance = (
            item.task.importance.value
            if hasattr(item.task.importance, "value")
            else str(item.task.importance)
        )
        progress_text = (
            f"{item.task.progress}%"
            if item.task.progress is not None
            else "未設定"
        )
        tone = self._intensity_note(intensity)

        lines = [
            "あなたはタスク管理AIの秘書です。",
            "ユーザーが安心して目の前の作業に集中できるよう、やさしくフォローします。",
            "次のルールに従ってメッセージを作成してください。",
            f"- トーン: {tone}",
            "- 日本語で、丁寧でやさしい表現にする",
            "- 「進捗どうですか」という表現は使わない",
            "- 【Heartbeat】などの見出しは付けない",
            "- 気になった理由の文を最低1つ、そのまま本文に入れる",
            "- タスク名を本文に含める",
        ]
        if project and project.name:
            lines.append("- プロジェクト名を本文に含める")
        lines.extend(
            [
                f"- 最後に [タスクを開く](task://{item.task.id}) を1回だけ入れる",
                "- 2〜5文程度",
                "",
                "## タスク情報",
                f"タイトル: {task_title}",
                f"メモ: {task_context or 'なし'}",
                f"重要度: {importance}",
                f"進捗: {progress_text}",
                f"期限: {due_text}",
                f"見積り: {item.estimated_minutes}分",
            ]
        )
        if status_lines:
            lines.append("目安:")
            lines.extend([f"- {line}" for line in status_lines])
        lines.extend(
            [
                "",
                "## 気になった理由（本文に最低1つ入れる）",
            ]
        )
        if reasons:
            lines.extend([f"- {reason}" for reason in reasons])
        else:
            lines.append("- 理由なし")
        lines.extend(
            [
                "",
                "## プロジェクト文脈",
                project_context or "なし",
                "",
                '出力は JSON のみ: {"message": "..."}',
            ]
        )
        return "\n".join(lines)

    def _generate_llm_message(
        self,
        item: HeartbeatRiskItem,
        user_timezone: str,
        reasons: list[str],
        status_lines: list[str],
        task_context: Optional[str],
        project: Optional[Project],
        project_context: Optional[str],
        intensity: HeartbeatIntensity,
    ) -> Optional[str]:
        if not self._llm_provider:
            return None

        prompt = self._build_llm_prompt(
            item=item,
            user_timezone=user_timezone,
            reasons=reasons,
            status_lines=status_lines,
            task_context=task_context,
            project_context=project_context,
            intensity=intensity,
            project=project,
        )
        response_schema = HeartbeatLLMMessage.model_json_schema()

        last_error: Optional[ValidationError] = None
        for attempt in range(LLM_MAX_RETRIES):
            output = generate_text(
                llm_provider=self._llm_provider,
                prompt=prompt,
                temperature=LLM_TEMPERATURE,
                max_output_tokens=600,
                response_schema=response_schema,
                response_mime_type="application/json",
            )
            if not output:
                return None
            try:
                return self._parse_llm_message(output, reasons, item, project)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    f"Heartbeat LLM validation failed (attempt {attempt + 1}): {exc}"
                )
                prompt = self._build_retry_prompt(prompt, exc)

        if last_error:
            logger.warning(f"Heartbeat LLM failed after {LLM_MAX_RETRIES} attempts")
        return None

    def _parse_llm_message(
        self,
        raw_output: str,
        reasons: list[str],
        item: HeartbeatRiskItem,
        project: Optional[Project],
    ) -> str:
        json_str = self._extract_json(raw_output)
        if not json_str:
            raise ValidationError.from_exception_data(
                "HeartbeatLLMMessage",
                [{"type": "value_error", "msg": "No JSON found in output"}],
            )

        message_data = HeartbeatLLMMessage.model_validate_json(json_str)
        message = message_data.message.strip()
        message = message.replace("【Heartbeat】", "").strip()
        self._validate_llm_message(message, reasons, item, project)
        return self._ensure_task_link(message, item.task.id)

    def _validate_llm_message(
        self,
        message: str,
        reasons: list[str],
        item: HeartbeatRiskItem,
        project: Optional[Project],
    ) -> None:
        task_title = " ".join(item.task.title.split()) if item.task.title else ""
        project_name = project.name.strip() if project and project.name else ""
        if not message:
            raise ValidationError.from_exception_data(
                "HeartbeatLLMMessage",
                [{"type": "value_error", "msg": "Empty message"}],
            )
        if re.search(r"進捗\s*どうですか", message):
            raise ValidationError.from_exception_data(
                "HeartbeatLLMMessage",
                [{"type": "value_error", "msg": "Contains forbidden phrase"}],
            )
        if reasons and not any(reason in message for reason in reasons):
            raise ValidationError.from_exception_data(
                "HeartbeatLLMMessage",
                [{"type": "value_error", "msg": "Missing reason sentence"}],
            )
        if task_title and task_title not in message:
            raise ValidationError.from_exception_data(
                "HeartbeatLLMMessage",
                [{"type": "value_error", "msg": "Missing task title"}],
            )
        if project_name and project_name not in message:
            raise ValidationError.from_exception_data(
                "HeartbeatLLMMessage",
                [{"type": "value_error", "msg": "Missing project name"}],
            )

    def _extract_json(self, raw_output: str) -> Optional[str]:
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_output)
        if json_match:
            return json_match.group(1).strip()
        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        if json_match:
            return json_match.group(0).strip()
        return None

    def _build_retry_prompt(self, prompt: str, error: Exception) -> str:
        return (
            "前回の出力にエラーがありました。修正してください。\n\n"
            f"エラー: {error}\n\n"
            f"{prompt}"
        )

    def _ensure_task_link(self, message: str, task_id: UUID) -> str:
        link = f"[タスクを開く](task://{task_id})"
        if f"(task://{task_id})" in message:
            return message
        if "task://" in message:
            replaced = re.sub(r"\[[^\]]+\]\(task://[^\)]+\)", link, message, count=1)
            if f"(task://{task_id})" in replaced:
                return replaced
        stripped = message.rstrip()
        if not stripped:
            return link
        return f"{stripped}\n{link}"

    def _build_session_id(self, now: datetime) -> str:
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        return f"{HEARTBEAT_SESSION_PREFIX}{timestamp}-{uuid4().hex[:8]}"

    def _build_session_title(self, item: HeartbeatRiskItem, user_timezone: str) -> str:
        due_date = item.task.due_date
        if due_date:
            due_local = ensure_utc(due_date).astimezone(ZoneInfo(user_timezone))
            title = f"Heartbeat {due_local.strftime('%m/%d')} - {item.task.title}"
        else:
            title = f"Heartbeat - {item.task.title}"
        return title if len(title) <= 200 else f"{title[:197]}..."

    def _build_metadata(
        self,
        item: HeartbeatRiskItem,
        user_timezone: str,
        session_id: str,
        message_id: UUID,
    ) -> dict:
        due_date = item.task.due_date
        due_local = None
        if due_date:
            due_local = ensure_utc(due_date).astimezone(ZoneInfo(user_timezone)).isoformat()
        return {
            "days_remaining": item.days_remaining,
            "required_days": item.required_days,
            "slack_days": item.slack_days,
            "due_date_local": due_local,
            "chat_session_id": session_id,
            "chat_message_id": str(message_id),
        }

    def _start_of_day_utc(self, local_now: datetime) -> datetime:
        local_midnight = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        return local_midnight.astimezone(UTC)

    def _parse_time(self, value: str) -> time:
        hour, minute = map(int, value.split(":"))
        return time(hour, minute)

    def _is_within_window(self, current: time, start_str: str, end_str: str) -> bool:
        start = self._parse_time(start_str)
        end = self._parse_time(end_str)
        if start <= end:
            return start <= current < end
        return current >= start or current < end
