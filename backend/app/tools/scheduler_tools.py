"""
Scheduler-related agent tools.

Tools for scheduling autonomous agent actions.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.postpone_repository import IPostponeRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.proposal_repository import IProposalRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.agent_task import AgentTaskCreate, AgentTaskPayload
from app.models.enums import ActionType, ProjectVisibility, TaskStatus
from app.models.task import Task, TaskUpdate
from app.services.task_utils import is_parent_task
from app.tools.approval_tools import create_tool_action_proposal
from app.utils.datetime_utils import get_user_today, normalize_timezone, now_utc, user_date_to_utc

# ===========================================
# Tool Input Models
# ===========================================


class ScheduleAgentTaskInput(BaseModel):
    """Input for schedule_agent_task tool."""

    action_type: ActionType = Field(..., description="アクションタイプ")
    execute_at: str = Field(..., description="実行時刻（ISO形式: YYYY-MM-DDTHH:MM:SS）")
    target_task_id: Optional[str] = Field(None, description="対象タスクID（UUID文字列）")
    message_tone: str = Field("neutral", description="メッセージのトーン (gentle/neutral/firm)")
    custom_message: Optional[str] = Field(None, description="カスタムメッセージ")
    metadata: dict[str, Any] = Field(default_factory=dict, description="追加メタデータ")


class ApplyScheduleRequestInput(BaseModel):
    """Input for apply_schedule_request tool."""

    request: str = Field(..., min_length=1, max_length=1000, description="Schedule preference request")
    focus_keywords: list[str] = Field(default_factory=list, description="Keywords to prioritize")
    avoid_keywords: list[str] = Field(default_factory=list, description="Keywords to deprioritize")
    max_focus_tasks: int = Field(3, ge=1, le=20, description="Maximum tasks to prioritize for today")
    project_id: Optional[str] = Field(None, description="Optional project scope")
    pin: bool = Field(True, description="Pin selected tasks to today")
    unpin_avoided_today: bool = Field(False, description="Unpin today's tasks matching avoid keywords")


# ===========================================
# Tool Functions
# ===========================================


def get_current_datetime() -> dict:
    """
    Get current date and time.

    Returns:
        Current datetime information in various formats
    """
    now = now_utc()
    return {
        "current_datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "weekday_ja": ["月", "火", "水", "木", "金", "土", "日"][now.weekday()],
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute,
        "timestamp": now.timestamp(),
    }


async def schedule_agent_task(
    user_id: str,
    repo: IAgentTaskRepository,
    input_data: ScheduleAgentTaskInput,
) -> dict:
    """
    Schedule an autonomous agent action.

    Args:
        user_id: User ID
        repo: Agent task repository
        input_data: Schedule parameters

    Returns:
        Created agent task as dict
    """
    # Parse execute_at
    try:
        trigger_time = datetime.fromisoformat(
            input_data.execute_at.replace("Z", "+00:00")
        )
    except ValueError:
        raise ValueError(f"Invalid date format: {input_data.execute_at}")

    # Parse target_task_id if provided
    target_task_id = UUID(input_data.target_task_id) if input_data.target_task_id else None

    payload = AgentTaskPayload(
        target_task_id=target_task_id,
        message_tone=input_data.message_tone,
        custom_message=input_data.custom_message,
        metadata=input_data.metadata,
    )

    task_data = AgentTaskCreate(
        trigger_time=trigger_time,
        action_type=input_data.action_type,
        payload=payload,
    )

    task = await repo.create(user_id, task_data)
    return task.model_dump(mode="json")  # Serialize UUIDs to strings


def _normalize_keywords(values: list[str]) -> list[str]:
    keywords: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized:
            continue
        if normalized not in keywords:
            keywords.append(normalized)
    return keywords


def _derive_keywords_from_request(request: str) -> list[str]:
    tokens = [
        token.strip().lower()
        for token in re.split(r"[,\s、。!！?？]+", request)
        if token and len(token.strip()) >= 2
    ]
    if tokens:
        return list(dict.fromkeys(tokens))[:6]
    trimmed = request.strip().lower()
    return [trimmed] if trimmed else []


def _task_search_text(task: Task) -> str:
    parts = [task.title]
    if task.description:
        parts.append(task.description)
    if task.purpose:
        parts.append(task.purpose)
    return " ".join(parts).lower()


def _match_score(text: str, keywords: list[str]) -> int:
    score = 0
    for keyword in keywords:
        if keyword in text:
            score += 1
    return score


def _sort_due_date(value: Optional[datetime]) -> float:
    if value is None:
        return float("inf")
    return value.timestamp()


async def _resolve_user_timezone(
    user_id: str,
    user_repo: Optional[IUserRepository],
) -> str:
    if user_repo is None:
        return normalize_timezone(None)
    try:
        user = await user_repo.get(UUID(user_id))
    except (TypeError, ValueError):
        return normalize_timezone(None)
    return normalize_timezone(user.timezone if user else None)


async def _list_owned_tasks(
    user_id: str,
    task_repo: ITaskRepository,
    *,
    include_done: bool,
) -> list[Task]:
    batch_size = 500
    hard_limit = 5000
    offset = 0
    tasks: list[Task] = []
    while len(tasks) < hard_limit:
        batch = await task_repo.list(
            user_id=user_id,
            include_done=include_done,
            limit=batch_size,
            offset=offset,
        )
        if not batch:
            break
        tasks.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size
    return tasks[:hard_limit]


async def _load_assigned_tasks(
    task_repo: ITaskRepository,
    task_ids: set[UUID],
) -> list[Task]:
    if not task_ids:
        return []
    get_many = getattr(task_repo, "get_many", None)
    if not callable(get_many):
        return []
    result = await get_many(list(task_ids))
    if not isinstance(result, list):
        return []
    return [task for task in result if isinstance(task, Task)]


async def apply_schedule_request(
    user_id: str,
    task_repo: ITaskRepository,
    assignment_repo: ITaskAssignmentRepository,
    project_repo: IProjectRepository,
    input_data: ApplyScheduleRequestInput,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    timezone = await _resolve_user_timezone(user_id, user_repo)
    today = get_user_today(timezone)
    today_datetime = user_date_to_utc(today, timezone)

    focus_keywords = _normalize_keywords(input_data.focus_keywords)
    if not focus_keywords:
        focus_keywords = _derive_keywords_from_request(input_data.request)
    avoid_keywords = _normalize_keywords(input_data.avoid_keywords)

    owned_tasks = await _list_owned_tasks(user_id, task_repo, include_done=True)
    assignments = await assignment_repo.list_for_assignee(user_id)
    assigned_task_ids = {assignment.task_id for assignment in assignments}
    assigned_tasks = await _load_assigned_tasks(task_repo, assigned_task_ids)
    projects = await project_repo.list(user_id, limit=1000)
    team_project_ids = {
        project.id for project in projects if project.visibility == ProjectVisibility.TEAM
    }

    def should_include(task: Task) -> bool:
        if not task.project_id:
            return True
        if task.project_id not in team_project_ids:
            return True
        return task.id in assigned_task_ids

    merged_by_id: dict[UUID, Task] = {}
    for task in owned_tasks:
        if should_include(task):
            merged_by_id[task.id] = task
    for task in assigned_tasks:
        if task.id not in merged_by_id and should_include(task):
            merged_by_id[task.id] = task

    scoped_tasks = list(merged_by_id.values())

    if input_data.project_id:
        try:
            project_id = UUID(input_data.project_id)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid project_id: {input_data.project_id}")
        scoped_tasks = [task for task in scoped_tasks if task.project_id == project_id]

    candidate_tasks = [
        task
        for task in scoped_tasks
        if task.status != TaskStatus.DONE
        and (task.status != TaskStatus.WAITING or task.requires_all_completion)
        and not task.is_fixed_time
        and not is_parent_task(task, scoped_tasks)
    ]

    scored: list[tuple[Task, int]] = []
    for task in candidate_tasks:
        text = _task_search_text(task)
        focus_score = _match_score(text, focus_keywords)
        avoid_score = _match_score(text, avoid_keywords)
        if focus_score <= 0:
            continue
        if avoid_score > 0 and avoid_score >= focus_score:
            continue
        score = focus_score * 10 - avoid_score * 5
        scored.append((task, score))

    scored.sort(
        key=lambda item: (
            -item[1],
            _sort_due_date(item[0].due_date),
            item[0].created_at.timestamp(),
        )
    )
    selected = scored[: input_data.max_focus_tasks]
    selected_ids = {task.id for task, _score in selected}

    updated_task_ids: list[str] = []
    unchanged_task_ids: list[str] = []
    for task, _score in selected:
        update_fields: dict[str, Any] = {}
        if input_data.pin and (task.pinned_date is None or task.pinned_date.date() != today):
            update_fields["pinned_date"] = today_datetime
        if task.start_not_before and task.start_not_before.date() > today:
            update_fields["start_not_before"] = today_datetime

        if not update_fields:
            unchanged_task_ids.append(str(task.id))
            continue

        await task_repo.update(
            user_id=user_id,
            task_id=task.id,
            update=TaskUpdate(**update_fields),
            project_id=task.project_id,
        )
        updated_task_ids.append(str(task.id))

    unpinned_task_ids: list[str] = []
    if input_data.unpin_avoided_today and avoid_keywords:
        for task in scoped_tasks:
            if task.id in selected_ids:
                continue
            if not task.pinned_date or task.pinned_date.date() != today:
                continue
            if _match_score(_task_search_text(task), avoid_keywords) <= 0:
                continue
            await task_repo.update(
                user_id=user_id,
                task_id=task.id,
                update=TaskUpdate(pinned_date=None),
                project_id=task.project_id,
            )
            unpinned_task_ids.append(str(task.id))

    status = "applied" if selected else "no_match"
    return {
        "status": status,
        "request": input_data.request,
        "timezone": timezone,
        "today": today.isoformat(),
        "focus_keywords": focus_keywords,
        "avoid_keywords": avoid_keywords,
        "selected_count": len(selected),
        "updated_count": len(updated_task_ids),
        "selected_tasks": [
            {"task_id": str(task.id), "title": task.title, "score": score}
            for task, score in selected
        ],
        "updated_task_ids": updated_task_ids,
        "unchanged_task_ids": unchanged_task_ids,
        "unpinned_task_ids": unpinned_task_ids,
    }


# ===========================================
# ADK Tool Definitions
# ===========================================


def get_current_datetime_tool() -> FunctionTool:
    """Create ADK tool for getting current datetime."""
    def _tool() -> dict:
        """get_current_datetime: 現在の日時を取得します。

        Parameters:
            なし

        Returns:
            dict: 現在の日時情報（ISO形式、日付、時刻、曜日、年月日時分など）
        """
        return get_current_datetime()

    _tool.__name__ = "get_current_datetime"
    return FunctionTool(func=_tool)


def schedule_agent_task_tool(
    repo: IAgentTaskRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for scheduling agent tasks."""
    async def _tool(input_data: dict) -> dict:
        """schedule_agent_task: 自律行動（リマインド等）をスケジュールします。

        Parameters:
            action_type (str): アクションタイプ（REMINDER/FOLLOWUP/MOTIVATE等、必須）
            execute_at (str): 実行時刻（ISO形式: YYYY-MM-DDTHH:MM:SS、必須）
            target_task_id (str, optional): 対象タスクID（UUID文字列）
            message_tone (str, optional): メッセージのトーン (gentle/neutral/firm)、デフォルト: neutral
            custom_message (str, optional): カスタムメッセージ
            metadata (dict, optional): 追加メタデータ

        Returns:
            dict: 作成されたエージェントタスク情報
        """
        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "schedule_agent_task",
                payload,
                proposal_desc,
            )
        return await schedule_agent_task(user_id, repo, ScheduleAgentTaskInput(**payload))

    _tool.__name__ = "schedule_agent_task"
    return FunctionTool(func=_tool)


def apply_schedule_request_tool(
    task_repo: ITaskRepository,
    assignment_repo: ITaskAssignmentRepository,
    project_repo: IProjectRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for applying natural-language schedule requests."""

    async def _tool(input_data: dict) -> dict:
        """apply_schedule_request: schedule preference request to reprioritize today's work.

        Parameters:
            request (str): user's schedule preference in natural language
            focus_keywords (list[str], optional): keywords to prioritize
            avoid_keywords (list[str], optional): keywords to deprioritize
            max_focus_tasks (int, optional): max tasks to pull into today (default 3)
            project_id (str, optional): limit scope to one project
            pin (bool, optional): pin selected tasks to today (default true)
            unpin_avoided_today (bool, optional): unpin today's tasks matching avoid keywords
            proposal_description (str, optional): user-facing approval text

        Returns:
            dict: applied result or pending approval payload
        """
        payload = dict(input_data)
        proposal_desc = str(payload.pop("proposal_description", "") or "")

        if proposal_repo and session_id and not auto_approve:
            if not proposal_desc:
                request = str(payload.get("request", "") or "").strip()
                proposal_desc = f"予定の優先度を調整します: {request[:80]}"
            return await create_tool_action_proposal(
                user_id=user_id,
                session_id=session_id,
                proposal_repo=proposal_repo,
                tool_name="apply_schedule_request",
                args=payload,
                description=proposal_desc,
            )

        return await apply_schedule_request(
            user_id=user_id,
            task_repo=task_repo,
            assignment_repo=assignment_repo,
            project_repo=project_repo,
            input_data=ApplyScheduleRequestInput(**payload),
            user_repo=user_repo,
        )

    _tool.__name__ = "apply_schedule_request"
    return FunctionTool(func=_tool)


# ===========================================
# Postpone History Tools
# ===========================================


async def get_task_postpone_history(
    user_id: str,
    task_id: str,
    postpone_repo: IPostponeRepository,
    task_repo: ITaskRepository,
) -> dict:
    """Get postpone history for a specific task."""
    from uuid import UUID as _UUID

    tid = _UUID(task_id)
    task = await task_repo.get_by_id(user_id, tid)
    events = await postpone_repo.list_by_task(user_id, tid)
    return {
        "task_id": task_id,
        "task_title": task.title if task else "不明",
        "postpone_count": len(events),
        "events": [
            {
                "from_date": e.from_date.isoformat(),
                "to_date": e.to_date.isoformat(),
                "reason": e.reason,
                "pinned": e.pinned,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


async def get_postpone_stats(
    user_id: str,
    postpone_repo: IPostponeRepository,
    task_repo: ITaskRepository,
    days: int = 7,
) -> dict:
    """Get aggregate postponement statistics."""
    from datetime import timedelta
    from uuid import UUID as _UUID

    since = get_user_today(normalize_timezone(None)) - timedelta(days=days)
    events = await postpone_repo.list_by_user(user_id, since=since)

    task_counts: dict[str, int] = {}
    for event in events:
        key = str(event.task_id)
        task_counts[key] = task_counts.get(key, 0) + 1

    most_postponed = []
    sorted_tasks = sorted(task_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for tid_str, count in sorted_tasks:
        task = await task_repo.get_by_id(user_id, _UUID(tid_str))
        most_postponed.append({
            "task_id": tid_str,
            "task_title": task.title if task else "不明",
            "postpone_count": count,
        })

    return {
        "period_days": days,
        "total_postpones": len(events),
        "unique_tasks": len(task_counts),
        "most_postponed": most_postponed,
    }


def get_task_postpone_history_tool(
    postpone_repo: IPostponeRepository,
    task_repo: ITaskRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for getting task postpone history."""
    async def _tool(input_data: dict) -> dict:
        """get_task_postpone_history: 特定タスクの延期履歴を取得します。

        Parameters:
            task_id (str): 対象タスクID（UUID文字列、必須）

        Returns:
            dict: タスクの延期履歴（回数、各イベントの詳細）
        """
        task_id = input_data.get("task_id", "")
        return await get_task_postpone_history(
            user_id, task_id, postpone_repo, task_repo
        )

    _tool.__name__ = "get_task_postpone_history"
    return FunctionTool(func=_tool)


def get_postpone_stats_tool(
    postpone_repo: IPostponeRepository,
    task_repo: ITaskRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for getting postpone statistics."""
    async def _tool(input_data: dict) -> dict:
        """get_postpone_stats: 期間内の延期統計を取得します。

        Parameters:
            days (int, optional): 集計期間（日数）、デフォルト: 7

        Returns:
            dict: 延期統計（総回数、ユニークタスク数、最多延期タスクTop5）
        """
        days = input_data.get("days", 7)
        return await get_postpone_stats(
            user_id, postpone_repo, task_repo, days=days
        )

    _tool.__name__ = "get_postpone_stats"
    return FunctionTool(func=_tool)

