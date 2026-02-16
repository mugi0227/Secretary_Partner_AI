"""
Task-related agent tools.

Tools for creating, updating, deleting, and searching tasks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.proposal_repository import IProposalRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.collaboration import TaskAssignmentCreate, TaskAssignmentsCreate
from app.models.enums import CreatedBy, EnergyLevel, Priority
from app.models.proposal import Proposal, ProposalType
from app.models.task import Task, TaskCreate, TaskUpdate, TouchpointStep
from app.services.project_permissions import ProjectAction
from app.services.task_utils import renumber_siblings
from app.tools.approval_tools import create_tool_action_proposal
from app.tools.permissions import require_project_action, require_project_member
from app.utils.datetime_utils import (
    all_day_bounds_to_utc,
    normalize_timezone,
    parse_iso_to_utc_with_user_timezone,
)

# ===========================================
# Tool Input Models
# ===========================================


def _normalize_enum_value(value: object, allowed: set[str]) -> object:
    if value is None:
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in allowed:
            return normalized
        import re

        parts = [part for part in re.split(r"[\s,/|]+", normalized) if part]
        for part in parts:
            if part in allowed:
                return part
        return value
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str):
                normalized = item.strip().upper()
                if normalized in allowed:
                    return normalized
        return value
    return value


class CreateTaskInput(BaseModel):
    """Input for create_task tool."""

    title: str = Field(
        ...,
        description="タスクのタイトル",
        validation_alias="task_title",
        json_schema_extra={"examples": ["買い物リストを作る", "圏論の勉強"]}
    )
    description: Optional[str] = Field(None, description="タスクの詳細説明")
    purpose: Optional[str] = Field(None, max_length=1000, description="なぜやるか（目的）- タスクを行う理由や背景")
    project_id: Optional[str] = Field(None, description="プロジェクトID（UUID文字列）")
    importance: Priority = Field(Priority.MEDIUM, description="重要度 (HIGH/MEDIUM/LOW)")
    urgency: Priority = Field(Priority.MEDIUM, description="緊急度 (HIGH/MEDIUM/LOW)")
    energy_level: EnergyLevel = Field(
        EnergyLevel.MEDIUM, description="必要エネルギー (HIGH=重い, MEDIUM=中程度, LOW=軽い)"
    )
    estimated_minutes: Optional[int] = Field(None, ge=1, description="見積もり時間（分）")
    due_date: Optional[str] = Field(
        None,
        description=(
            "Due datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    start_not_before: Optional[str] = Field(
        None,
        description=(
            "Earliest start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    dependency_ids: list[str] = Field(
        default_factory=list,
        description="このタスクが依存する他のタスクのIDリスト（UUID文字列のリスト）"
    )
    same_day_allowed: bool = Field(True, description="Allow sibling subtasks on the same day")
    min_gap_days: int = Field(0, ge=0, description="Minimum gap days between sibling subtasks")
    touchpoint_count: Optional[int] = Field(None, ge=1, description="Touchpoint count")
    touchpoint_minutes: Optional[int] = Field(None, ge=1, description="Minutes per touchpoint")
    touchpoint_gap_days: int = Field(0, ge=0, description="Minimum gap days between touchpoints")
    touchpoint_steps: list[TouchpointStep] = Field(default_factory=list, description="Touchpoint step guides")
    # Meeting fields (optional, only for fixed-time events)
    is_fixed_time: bool = Field(False, description="会議・固定時間イベントの場合true")
    is_all_day: bool = Field(False, description="終日タスク（休暇・出張など、その日のキャパシティを0にする）")
    start_time: Optional[str] = Field(
        None,
        description=(
            "Start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    end_time: Optional[str] = Field(
        None,
        description=(
            "End datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    location: Optional[str] = Field(None, description="場所（会議用）")
    attendees: list[str] = Field(default_factory=list, description="参加者リスト（会議用）")
    meeting_notes: Optional[str] = Field(None, description="議事録・メモ（会議用）")
    # Subtask fields
    parent_id: Optional[str] = Field(None, description="親タスクID（UUID文字列）- サブタスクとして作成する場合に指定")
    order_in_parent: Optional[int] = Field(None, ge=1, description="親タスク内での順序（1から開始）")
    guide: Optional[str] = Field(
        None,
        max_length=2000,
        description="詳細な進め方ガイド（Markdown形式）- サブタスクの場合に設定推奨。具体的な手順、注意点、完了の判断基準を含める"
    )
    # Assignee field for task creation
    assignee_ids: list[str] = Field(default_factory=list, description="担当者IDリスト（UUID文字列）")

    model_config = {"populate_by_name": True}

    @field_validator("importance", "urgency", mode="before")
    @classmethod
    def _normalize_priority(cls, value: object) -> object:
        return _normalize_enum_value(value, {"HIGH", "MEDIUM", "LOW"})

    @field_validator("energy_level", mode="before")
    @classmethod
    def _normalize_energy_level(cls, value: object) -> object:
        return _normalize_enum_value(value, {"HIGH", "MEDIUM", "LOW"})


class UpdateTaskInput(BaseModel):
    """Input for update_task tool."""

    task_id: str = Field(..., description="タスクID（UUID文字列）")
    title: Optional[str] = Field(None, description="タスクのタイトル")
    description: Optional[str] = Field(None, description="タスクの詳細説明")
    purpose: Optional[str] = Field(None, max_length=1000, description="なぜやるか（目的）- タスクを行う理由や背景")
    project_id: Optional[str] = Field(None, description="プロジェクトID（UUID文字列）")
    phase_id: Optional[str] = Field(None, description="フェーズID（UUID文字列）")
    status: Optional[str] = Field(None, description="ステータス (TODO/IN_PROGRESS/WAITING/DONE)")
    importance: Optional[Priority] = Field(None, description="重要度")
    urgency: Optional[Priority] = Field(None, description="緊急度")
    energy_level: Optional[EnergyLevel] = Field(None, description="必要エネルギー (HIGH/MEDIUM/LOW)")
    estimated_minutes: Optional[int] = Field(None, ge=1, description="見積もり時間（分）")
    due_date: Optional[str] = Field(
        None,
        description=(
            "Due datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    start_not_before: Optional[str] = Field(
        None,
        description=(
            "Earliest start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    parent_id: Optional[str] = Field(None, description="親タスクID（UUID文字列、サブタスク化/解除）")
    order_in_parent: Optional[int] = Field(None, ge=1, description="親タスク内での順序")
    dependency_ids: Optional[list[str]] = Field(None, description="依存タスクIDリスト（UUID文字列）")
    same_day_allowed: Optional[bool] = Field(None, description="Allow sibling subtasks on the same day")
    min_gap_days: Optional[int] = Field(None, ge=0, description="Minimum gap days between sibling subtasks")
    touchpoint_count: Optional[int] = Field(None, ge=1, description="Touchpoint count")
    touchpoint_minutes: Optional[int] = Field(None, ge=1, description="Minutes per touchpoint")
    touchpoint_gap_days: Optional[int] = Field(None, ge=0, description="Minimum gap days between touchpoints")
    touchpoint_steps: Optional[list[TouchpointStep]] = Field(None, description="Touchpoint step guides")
    progress: Optional[int] = Field(None, ge=0, le=100, description="進捗率（0-100%）")
    source_capture_id: Optional[str] = Field(None, description="元Capture ID（UUID文字列）")
    completion_note: Optional[str] = Field(
        None,
        max_length=2000,
        description="メモ（学んだこと、気づき、作業記録など。いつでも記入可能。Achievement生成に活用）"
    )
    guide: Optional[str] = Field(
        None,
        max_length=2000,
        description="詳細な進め方ガイド（Markdown形式）- サブタスクの場合に設定推奨"
    )
    # Meeting fields
    is_fixed_time: Optional[bool] = Field(None, description="会議・固定時間イベントの場合true")
    is_all_day: Optional[bool] = Field(None, description="終日タスク（休暇・出張など、その日のキャパシティを0にする）")
    start_time: Optional[str] = Field(
        None,
        description=(
            "Start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    end_time: Optional[str] = Field(
        None,
        description=(
            "End datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    location: Optional[str] = Field(None, description="場所（会議用）")
    attendees: Optional[list[str]] = Field(None, description="参加者リスト（会議用）")
    meeting_notes: Optional[str] = Field(None, description="議事録・メモ（会議用）")

    @field_validator("importance", "urgency", mode="before")
    @classmethod
    def _normalize_priority(cls, value: object) -> object:
        return _normalize_enum_value(value, {"HIGH", "MEDIUM", "LOW"})

    @field_validator("energy_level", mode="before")
    @classmethod
    def _normalize_energy_level(cls, value: object) -> object:
        return _normalize_enum_value(value, {"HIGH", "MEDIUM", "LOW"})


class DeleteTaskInput(BaseModel):
    """Input for delete_task tool."""

    task_id: str = Field(..., description="タスクID（UUID文字列）")


class SearchSimilarTasksInput(BaseModel):
    """Input for search_similar_tasks tool."""

    task_title: str = Field(
        ...,
        description="検索するタスクタイトル",
        json_schema_extra={"examples": ["買い物リストを作る", "圏論の勉強"]}
    )
    project_id: Optional[str] = Field(
        None,
        description="プロジェクトID（指定時はそのプロジェクト内のみ検索）"
    )


class CreateMeetingInput(BaseModel):
    """Input for create_meeting tool."""

    title: str = Field(..., description="会議タイトル")
    start_time: str = Field(
        ...,
        description=(
            "Start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    end_time: str = Field(
        ...,
        description=(
            "End datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    location: Optional[str] = Field(None, description="場所（オンライン/会議室名）")
    attendees: list[str] = Field(default_factory=list, description="参加者リスト")
    description: Optional[str] = Field(None, description="会議の目的・議題")
    meeting_notes: Optional[str] = Field(None, description="議事録・メモ")
    project_id: Optional[str] = Field(None, description="プロジェクトID（UUID文字列）")
    recurring_meeting_id: Optional[str] = Field(None, description="定例会議ID（定例から生成する場合）")


class GetTaskInput(BaseModel):
    """Input for get_task tool."""

    task_id: str = Field(..., description="タスクID（UUID文字列）")


class ListTasksInput(BaseModel):
    """Input for list_tasks tool."""

    project_id: Optional[str] = Field(
        None,
        description="プロジェクトID（指定時はそのプロジェクト内のみ取得）"
    )
    status_filter: Optional[list[str]] = Field(
        None,
        description="ステータスフィルタ（例: ['TODO', 'IN_PROGRESS']）。指定なしで全ステータス取得"
    )
    limit: int = Field(
        50,
        ge=1,
        le=100,
        description="取得件数上限（デフォルト: 50、最大: 100）"
    )




class AssignTaskInput(BaseModel):
    """Input for assign_task tool."""

    task_id: str = Field(..., description="Task ID")
    assignee_id: Optional[str] = Field(None, description="Assignee ID (single)")
    assignee_ids: list[str] = Field(
        default_factory=list,
        description="Assignee ID list (multiple)",
    )




class ListTaskAssignmentsInput(BaseModel):
    # Input for list_task_assignments tool.

    task_id: str = Field(..., description="Task ID")


class ListProjectAssignmentsInput(BaseModel):
    # Input for list_project_assignments tool.

    project_id: str = Field(..., description="Project ID")


# ===========================================
# Tool Functions
# ===========================================



async def list_task_assignments(
    user_id: str,
    assignment_repo: ITaskAssignmentRepository,
    task_repo: ITaskRepository,
    input_data: ListTaskAssignmentsInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    # List assignments for a task.
    task_id = UUID(input_data.task_id)
    _, owner_id, _, error = await _resolve_task_access(
        user_id,
        task_id,
        task_repo,
        project_repo,
        member_repo,
    )
    if error:
        return error
    assignments = await assignment_repo.list_by_task(owner_id or user_id, task_id)
    return {
        "assignments": [assignment.model_dump(mode="json") for assignment in assignments],
        "count": len(assignments),
    }


async def list_project_assignments(
    user_id: str,
    assignment_repo: ITaskAssignmentRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: ListProjectAssignmentsInput,
) -> dict:
    # List assignments for a project.
    try:
        project_id = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}

    access = await require_project_action(
        user_id,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.ASSIGNMENT_READ,
    )
    if isinstance(access, dict):
        return access

    assignments = await assignment_repo.list_by_project(access.owner_id, project_id)
    return {
        "assignments": [assignment.model_dump(mode="json") for assignment in assignments],
        "count": len(assignments),
    }


def _normalize_meeting_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _within_minutes(left: datetime, right: datetime, minutes: int) -> bool:
    left_norm = _normalize_datetime(left)
    right_norm = _normalize_datetime(right)
    delta_seconds = abs((left_norm - right_norm).total_seconds())
    return delta_seconds <= minutes * 60


async def _resolve_user_timezone(
    user_id: str,
    user_repo: Optional[IUserRepository],
) -> str:
    if user_repo is None:
        return normalize_timezone(None)
    try:
        user = await user_repo.get(UUID(user_id))
    except (ValueError, TypeError):
        user = None
    return normalize_timezone(user.timezone if user else None)


async def _resolve_task_access(
    user_id: str,
    task_id: UUID,
    task_repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
) -> tuple[Optional[Task], Optional[str], Optional[UUID], Optional[dict]]:
    task = await task_repo.get(user_id, task_id)
    if task:
        if task.project_id:
            if not project_repo or not member_repo:
                return None, None, None, {"error": "Project access check unavailable"}
            access = await require_project_member(
                user_id,
                task.project_id,
                project_repo,
                member_repo,
            )
            if isinstance(access, dict):
                return None, None, None, access
            return task, access.owner_id, task.project_id, None
        return task, user_id, task.project_id, None

    if not project_repo or not member_repo:
        return None, None, None, {"error": "Project access check unavailable"}

    projects = await project_repo.list(user_id, limit=1000)
    for project in projects:
        task = await task_repo.get(user_id, task_id, project_id=project.id)
        if task:
            access = await require_project_member(
                user_id,
                project.id,
                project_repo,
                member_repo,
            )
            if isinstance(access, dict):
                return None, None, None, access
            return task, access.owner_id, project.id, None

    return None, None, None, {"error": "Task not found"}


async def _resolve_project_access(
    user_id: str,
    project_id_raw: Optional[str],
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
) -> tuple[Optional[UUID], Optional[str], Optional[dict]]:
    if not project_id_raw or not project_id_raw.strip():
        return None, user_id, None
    try:
        project_id = UUID(project_id_raw)
    except (ValueError, AttributeError):
        return None, None, {"error": f"Invalid project ID format: {project_id_raw}"}
    if not project_repo or not member_repo:
        return None, None, {"error": "Project access check unavailable"}
    access = await require_project_member(user_id, project_id, project_repo, member_repo)
    if isinstance(access, dict):
        return None, None, access
    return project_id, access.owner_id, None


async def _find_existing_meeting(
    repo: ITaskRepository,
    user_id: str,
    start_time: datetime,
    end_time: datetime,
    title: str,
    project_id: UUID | None,
) -> Task | None:
    normalized = _normalize_meeting_title(title)
    tasks = await repo.list(user_id, project_id=project_id, include_done=True, limit=1000)
    for task in tasks:
        if not task.is_fixed_time or not task.start_time or not task.end_time:
            continue
        if not _within_minutes(task.start_time, start_time, 30):
            continue
        if not _within_minutes(task.end_time, end_time, 30):
            continue
        if _normalize_meeting_title(task.title) == normalized:
            return task
    return None


async def propose_task(
    user_id: str,
    session_id: str,
    proposal_repo: IProposalRepository,
    task_repo: ITaskRepository,
    input_data: CreateTaskInput,
    description: str = "",
    auto_approve: bool = False,
    assignment_repo: Optional[ITaskAssignmentRepository] = None,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    """
    Propose a task for user approval, or auto-approve if configured.

    Args:
        user_id: User ID
        session_id: Chat session ID
        proposal_repo: Proposal repository
        task_repo: Task repository (for auto-approval)
        input_data: Task creation data
        description: AI-generated description of why this task is being proposed
        auto_approve: If True, automatically approve and create the task
        assignment_repo: Task assignment repository (optional, for assigning task on creation)

    Returns:
        If auto_approve=False: Proposal response with proposal_id
        If auto_approve=True: Created task info with task_id
    """
    # If no description provided, generate a simple one
    if not description:
        description = f"タスク「{input_data.title}」を作成します。"

    if input_data.project_id:
        _, _, access_error = await _resolve_project_access(
            user_id,
            input_data.project_id,
            project_repo,
            member_repo,
        )
        if access_error:
            return access_error


    # Auto-approve mode: create task immediately
    if auto_approve:
        created_task = await create_task(
            user_id=user_id,
            repo=task_repo,
            input_data=input_data,
            assignment_repo=assignment_repo,
            project_repo=project_repo,
            member_repo=member_repo,
            user_repo=user_repo,
        )
        return {
            "auto_approved": True,
            "task_id": created_task.get("id"),
            "assignments": created_task.get("assignments"),
            "description": description,
        }

    # Proposal mode: create proposal and return for user approval
    # Try to parse user_id as UUID, fallback to generating a new one for dev mode
    user_id_raw = None
    try:
        parsed_user_id = UUID(user_id)
    except (ValueError, AttributeError):
        # For dev mode where user_id might be "dev_user", use a consistent UUID
        import hashlib
        user_id_raw = user_id
        parsed_user_id = UUID(bytes=hashlib.md5(user_id.encode()).digest())

    proposal = Proposal(
        user_id=parsed_user_id,
        user_id_raw=user_id_raw,
        session_id=session_id,
        proposal_type=ProposalType.CREATE_TASK,
        payload=input_data.model_dump(mode="json"),
        description=description,
    )

    created_proposal = await proposal_repo.create(proposal)

    # Return pending_approval status to signal AI to wait for user approval
    return {
        "status": "pending_approval",
        "proposal_id": str(created_proposal.id),
        "proposal_type": ProposalType.CREATE_TASK.value,
        "description": description,
        "message": "ユーザーの承諾待ちです。承諾されるまで「完了しました」とは言わないでください。",
    }


async def create_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: CreateTaskInput,
    assignment_repo: Optional[ITaskAssignmentRepository] = None,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    """
    Create a new task.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task creation data
        assignment_repo: Task assignment repository (optional, for assigning task on creation)

    Returns:
        Created task as dict
    """
    project_id, owner_id, access_error = await _resolve_project_access(
        user_id,
        input_data.project_id,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    # Parse parent_id if provided
    parent_id = None
    if input_data.parent_id:
        try:
            parent_id = UUID(input_data.parent_id)
        except ValueError:
            pass  # Invalid UUID format, ignore

    if parent_id:
        parent_task, parent_owner_id, parent_project_id, parent_error = await _resolve_task_access(
            user_id,
            parent_id,
            repo,
            project_repo,
            member_repo,
        )
        if parent_error:
            return parent_error
        if not parent_task or not parent_owner_id:
            return {"error": f"Parent task {parent_id} not found"}

        owner_id = parent_owner_id
        if project_id is None:
            project_id = parent_project_id
        elif project_id != parent_project_id:
            return {
                "error": "parent_id and project_id mismatch",
            }

    timezone_name = await _resolve_user_timezone(owner_id or user_id, user_repo)

    # Parse due_date if provided
    due_date = None
    if input_data.due_date:
        try:
            due_date = parse_iso_to_utc_with_user_timezone(input_data.due_date, timezone_name)
        except ValueError:
            pass  # Invalid date format, ignore

    # Parse start_not_before if provided
    start_not_before = None
    if input_data.start_not_before:
        try:
            start_not_before = parse_iso_to_utc_with_user_timezone(
                input_data.start_not_before,
                timezone_name,
            )
        except ValueError:
            pass  # Invalid date format, ignore

    # Parse dependency_ids if provided
    dependency_ids = []
    for dep_id_str in input_data.dependency_ids:
        try:
            dependency_ids.append(UUID(dep_id_str))
        except (ValueError, AttributeError):
            # Invalid UUID format, skip this dependency
            pass

    order_in_parent = input_data.order_in_parent
    order_provided = order_in_parent is not None
    siblings = []
    if parent_id:
        try:
            siblings = await repo.get_subtasks(owner_id, parent_id, project_id=project_id)
        except Exception:
            siblings = []

        if order_in_parent is None and siblings:
            max_order = max((sibling.order_in_parent or 0) for sibling in siblings)
            if max_order > 0:
                order_in_parent = max_order + 1
            else:
                order_in_parent = len(siblings) + 1

    # Shift existing siblings when inserting at a specific position
    if parent_id and order_provided and order_in_parent is not None:
        for sibling in siblings:
            if sibling.order_in_parent is not None and sibling.order_in_parent >= order_in_parent:
                await repo.update(
                    owner_id, sibling.id,
                    TaskUpdate(order_in_parent=sibling.order_in_parent + 1),
                    project_id=project_id,
                )

    # Parse meeting times if is_fixed_time
    start_time = None
    end_time = None
    if input_data.is_fixed_time and input_data.start_time and input_data.end_time:
        try:
            start_time = parse_iso_to_utc_with_user_timezone(input_data.start_time, timezone_name)
            end_time = parse_iso_to_utc_with_user_timezone(input_data.end_time, timezone_name)
        except ValueError:
            pass  # Invalid date format, ignore

    is_fixed_time = input_data.is_fixed_time
    if input_data.is_all_day:
        timezone_name = await _resolve_user_timezone(owner_id, user_repo)
        reference = start_time or due_date or start_not_before
        start_time, end_time = all_day_bounds_to_utc(timezone_name, reference=reference)
        is_fixed_time = True

    if is_fixed_time and start_time and end_time:
        existing = await _find_existing_meeting(
            repo,
            owner_id,
            start_time,
            end_time,
            input_data.title,
            project_id,
        )
        if existing:
            return existing.model_dump(mode="json")

    task_data = TaskCreate(
        title=input_data.title,
        description=input_data.description,
        purpose=input_data.purpose,
        project_id=project_id,
        importance=input_data.importance,
        urgency=input_data.urgency,
        energy_level=input_data.energy_level,
        estimated_minutes=input_data.estimated_minutes,
        due_date=due_date,
        start_not_before=start_not_before,
        dependency_ids=dependency_ids,
        same_day_allowed=input_data.same_day_allowed,
        min_gap_days=input_data.min_gap_days,
        touchpoint_count=input_data.touchpoint_count,
        touchpoint_minutes=input_data.touchpoint_minutes,
        touchpoint_gap_days=input_data.touchpoint_gap_days,
        touchpoint_steps=input_data.touchpoint_steps,
        created_by=CreatedBy.AGENT,
        # Subtask fields
        parent_id=parent_id,
        order_in_parent=order_in_parent,
        guide=input_data.guide,
        # Meeting fields
        is_fixed_time=is_fixed_time,
        is_all_day=input_data.is_all_day,
        start_time=start_time,
        end_time=end_time,
        location=input_data.location,
        attendees=input_data.attendees,
        meeting_notes=input_data.meeting_notes,
    )

    task = await repo.create(owner_id, task_data)
    result = task.model_dump(mode="json")  # Serialize UUIDs to strings

    assigned = []
    # Assign task to members if assignee_ids provided
    if input_data.assignee_ids and assignment_repo:
        # Resolve assignee IDs: AI may provide member record IDs instead of member_user_id
        resolved_ids = list(input_data.assignee_ids)
        if project_id and member_repo:
            try:
                members = await member_repo.list_by_project(project_id)
                user_id_set = {m.member_user_id for m in members}
                record_to_user = {str(m.id): m.member_user_id for m in members}
                resolved_ids = []
                for aid in input_data.assignee_ids:
                    if not aid or not aid.strip():
                        continue
                    aid = aid.strip()
                    if aid in user_id_set:
                        resolved_ids.append(aid)
                    elif aid in record_to_user:
                        resolved_ids.append(record_to_user[aid])
                    else:
                        import logging
                        logging.getLogger(__name__).warning(
                            "Skipping unknown assignee_id %s (not a member of project %s)", aid, project_id,
                        )
            except Exception:
                pass  # Fall back to using original IDs

        for assignee_id in resolved_ids:
            if assignee_id and assignee_id.strip():
                try:
                    assignment = await assignment_repo.assign(
                        owner_id,
                        task.id,
                        TaskAssignmentCreate(assignee_id=assignee_id),
                    )
                    assigned.append(assignment.model_dump(mode="json"))
                except Exception:
                    pass

    if not assigned and assignment_repo and parent_id and not input_data.assignee_ids:
        parent_assignments = await assignment_repo.list_by_task(owner_id, parent_id)
        if not parent_assignments and project_id:
            project_assignments = await assignment_repo.list_by_project(owner_id, project_id)
            parent_assignments = [
                assignment for assignment in project_assignments if assignment.task_id == parent_id
            ]
        for assignment in parent_assignments:
            if assignment.assignee_id:
                created = await assignment_repo.assign(
                    owner_id,
                    task.id,
                    TaskAssignmentCreate(assignee_id=assignment.assignee_id),
                )
                assigned.append(created.model_dump(mode="json"))

    # Auto-assign to the requester (current user) for project tasks
    if not assigned and assignment_repo and project_id and member_repo:
        try:
            members = await member_repo.list_by_project(project_id)
            member_ids = {m.member_user_id for m in members}
            if user_id in member_ids:
                created = await assignment_repo.assign(
                    owner_id,
                    task.id,
                    TaskAssignmentCreate(assignee_id=user_id),
                )
                assigned.append(created.model_dump(mode="json"))
            elif len(members) == 1:
                created = await assignment_repo.assign(
                    owner_id,
                    task.id,
                    TaskAssignmentCreate(assignee_id=members[0].member_user_id),
                )
                assigned.append(created.model_dump(mode="json"))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Auto-assign failed: %s", exc, exc_info=True)

    if assigned:
        result["assignments"] = assigned

    return result


async def update_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: UpdateTaskInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    """
    Update an existing task.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task update data

    Returns:
        Updated task as dict
    """
    task_id = UUID(input_data.task_id)

    current_task, owner_id, current_project_id, access_error = await _resolve_task_access(
        user_id,
        task_id,
        repo,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    # Parse project_id if provided
    target_project_id = None
    if input_data.project_id:
        try:
            target_project_id = UUID(input_data.project_id)
        except ValueError:
            return {"error": f"Invalid project ID format: {input_data.project_id}"}

    if target_project_id and target_project_id != current_project_id:
        if not project_repo or not member_repo:
            return {"error": "Project access check unavailable"}
        access = await require_project_member(
            user_id,
            target_project_id,
            project_repo,
            member_repo,
        )
        if isinstance(access, dict):
            return access

    # Parse phase_id if provided
    phase_id = None
    if input_data.phase_id:
        try:
            phase_id = UUID(input_data.phase_id)
        except ValueError:
            pass  # Invalid UUID format, ignore

    # Parse parent_id if provided
    parent_id = None
    if input_data.parent_id:
        try:
            parent_id = UUID(input_data.parent_id)
        except ValueError:
            pass  # Invalid UUID format, ignore

    # Parse source_capture_id if provided
    source_capture_id = None
    if input_data.source_capture_id:
        try:
            source_capture_id = UUID(input_data.source_capture_id)
        except ValueError:
            pass  # Invalid UUID format, ignore

    # Parse dependency_ids if provided
    dependency_ids = None
    if input_data.dependency_ids is not None:
        dependency_ids = []
        for dep_id_str in input_data.dependency_ids:
            try:
                dependency_ids.append(UUID(dep_id_str))
            except (ValueError, AttributeError):
                pass  # Invalid UUID format, skip this dependency

    timezone_name = await _resolve_user_timezone(owner_id or user_id, user_repo)

    # Parse due_date if provided
    due_date = None
    if input_data.due_date:
        try:
            due_date = parse_iso_to_utc_with_user_timezone(input_data.due_date, timezone_name)
        except ValueError:
            pass  # Invalid date format, ignore

    # Parse start_not_before if provided
    start_not_before = None
    if input_data.start_not_before:
        try:
            start_not_before = parse_iso_to_utc_with_user_timezone(
                input_data.start_not_before,
                timezone_name,
            )
        except ValueError:
            pass  # Invalid date format, ignore

    # Parse meeting times if provided
    start_time = None
    end_time = None
    if input_data.start_time:
        try:
            start_time = parse_iso_to_utc_with_user_timezone(input_data.start_time, timezone_name)
        except ValueError:
            pass  # Invalid date format, ignore
    if input_data.end_time:
        try:
            end_time = parse_iso_to_utc_with_user_timezone(input_data.end_time, timezone_name)
        except ValueError:
            pass  # Invalid date format, ignore

    is_fixed_time = input_data.is_fixed_time
    if input_data.is_all_day is True:
        reference = (
            start_time
            or due_date
            or start_not_before
            or (current_task.start_time if current_task else None)
            or (current_task.due_date if current_task else None)
            or (current_task.start_not_before if current_task else None)
        )
        start_time, end_time = all_day_bounds_to_utc(timezone_name, reference=reference)
        is_fixed_time = True

    update_data = TaskUpdate(
        title=input_data.title,
        description=input_data.description,
        purpose=input_data.purpose,
        project_id=target_project_id,
        phase_id=phase_id,
        status=input_data.status,
        importance=input_data.importance,
        urgency=input_data.urgency,
        energy_level=input_data.energy_level,
        estimated_minutes=input_data.estimated_minutes,
        due_date=due_date,
        start_not_before=start_not_before,
        parent_id=parent_id,
        order_in_parent=input_data.order_in_parent,
        dependency_ids=dependency_ids,
        same_day_allowed=input_data.same_day_allowed,
        min_gap_days=input_data.min_gap_days,
        progress=input_data.progress,
        source_capture_id=source_capture_id,
        completion_note=input_data.completion_note,
        guide=input_data.guide,
        touchpoint_count=input_data.touchpoint_count,
        touchpoint_minutes=input_data.touchpoint_minutes,
        touchpoint_gap_days=input_data.touchpoint_gap_days,
        touchpoint_steps=input_data.touchpoint_steps,
        # Meeting fields
        is_fixed_time=is_fixed_time,
        is_all_day=input_data.is_all_day,
        start_time=start_time,
        end_time=end_time,
        location=input_data.location,
        attendees=input_data.attendees,
        meeting_notes=input_data.meeting_notes,
    )

    task = await repo.update(owner_id, task_id, update_data, project_id=current_project_id)
    return task.model_dump(mode="json")  # Serialize UUIDs to strings


async def delete_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: DeleteTaskInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    """
    Delete a task.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task deletion data

    Returns:
        Deletion result
    """
    task_id = UUID(input_data.task_id)
    task, owner_id, project_id, access_error = await _resolve_task_access(
        user_id,
        task_id,
        repo,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    parent_id = task.parent_id if task else None
    deleted = await repo.delete(owner_id, task_id, project_id=project_id)

    if deleted and parent_id:
        await renumber_siblings(repo, owner_id, parent_id, project_id)

    return {
        "success": deleted,
        "task_id": input_data.task_id,
        "message": "Task deleted successfully" if deleted else "Task not found",
    }


async def get_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: GetTaskInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    """
    Get a single task by ID.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task ID

    Returns:
        Task details including meeting_notes
    """
    task_id = UUID(input_data.task_id)
    task, _, _, access_error = await _resolve_task_access(
        user_id,
        task_id,
        repo,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    if not task:
        return {"error": "Task not found", "task_id": input_data.task_id}

    return {
        "task": task.model_dump(mode="json"),
    }


async def list_tasks(
    user_id: str,
    repo: ITaskRepository,
    input_data: ListTasksInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    """
    List tasks with optional filters.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: List parameters

    Returns:
        List of tasks matching the filters
    """
    project_id, owner_id, access_error = await _resolve_project_access(
        user_id,
        input_data.project_id,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    # Get tasks - we'll filter by status in Python since repo.list doesn't support multiple statuses
    all_tasks = await repo.list(
        owner_id,
        project_id=project_id,
        parent_id=None,  # Only root tasks (not subtasks)
    )

    # Filter by status if specified
    if input_data.status_filter:
        status_set = set(s.upper() for s in input_data.status_filter)
        filtered_tasks = [t for t in all_tasks if t.status.value in status_set]
    else:
        filtered_tasks = all_tasks

    # Apply limit
    limited_tasks = filtered_tasks[:input_data.limit]

    return {
        "tasks": [task.model_dump(mode="json") for task in limited_tasks],
        "count": len(limited_tasks),
        "total_matching": len(filtered_tasks),
    }




def _normalize_assignee_ids(input_data: AssignTaskInput) -> list[str]:
    values: list[str] = []
    if input_data.assignee_ids:
        values.extend([value for value in input_data.assignee_ids if value])
    if input_data.assignee_id:
        values.append(input_data.assignee_id)
    seen = set()
    normalized: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _extract_assignment_ids(result: dict) -> list[str]:
    if not isinstance(result, dict):
        return []
    if isinstance(result.get("id"), str):
        return [result["id"]]
    assignments = result.get("assignments")
    if isinstance(assignments, list):
        return [item.get("id") for item in assignments if isinstance(item, dict) and item.get("id")]
    return []


async def assign_task(
    user_id: str,
    assignment_repo: ITaskAssignmentRepository,
    task_repo: ITaskRepository,
    input_data: AssignTaskInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    # Assign a task to one or more members.
    task_id = UUID(input_data.task_id)
    _, owner_id, _, access_error = await _resolve_task_access(
        user_id,
        task_id,
        task_repo,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error
    assignee_ids = _normalize_assignee_ids(input_data)
    if not assignee_ids:
        raise ValueError("assignee_id or assignee_ids is required")

    if len(assignee_ids) == 1:
        assignment = await assignment_repo.assign(
            owner_id,
            task_id,
            TaskAssignmentCreate(assignee_id=assignee_ids[0]),
        )
        return assignment.model_dump(mode="json")

    assignments = await assignment_repo.assign_multiple(
        owner_id,
        task_id,
        TaskAssignmentsCreate(assignee_ids=assignee_ids),
    )
    return {
        "assignments": [assignment.model_dump(mode="json") for assignment in assignments],
        "count": len(assignments),
    }


async def propose_task_assignment(
    user_id: str,
    session_id: str,
    proposal_repo: IProposalRepository,
    assignment_repo: ITaskAssignmentRepository,
    task_repo: ITaskRepository,
    input_data: AssignTaskInput,
    description: str = "",
    auto_approve: bool = False,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    # Propose a task assignment for user approval, or auto-approve if configured.
    if not description:
        description = "Assign task owners."

    task_id = UUID(input_data.task_id)
    _, _, _, access_error = await _resolve_task_access(
        user_id,
        task_id,
        task_repo,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    assignee_ids = _normalize_assignee_ids(input_data)
    if not assignee_ids:
        raise ValueError("assignee_id or assignee_ids is required")

    payload = input_data.model_dump(mode="json")
    payload["assignee_ids"] = assignee_ids
    payload.pop("assignee_id", None)

    if auto_approve:
        result = await assign_task(
            user_id=user_id,
            assignment_repo=assignment_repo,
            task_repo=task_repo,
            input_data=input_data,
            project_repo=project_repo,
            member_repo=member_repo,
        )
        return {
            "auto_approved": True,
            "assignment_ids": _extract_assignment_ids(result),
            "description": description,
        }

    user_id_raw = None
    try:
        parsed_user_id = UUID(user_id)
    except (ValueError, AttributeError):
        import hashlib

        user_id_raw = user_id
        parsed_user_id = UUID(bytes=hashlib.md5(user_id.encode()).digest())

    proposal = Proposal(
        user_id=parsed_user_id,
        user_id_raw=user_id_raw,
        session_id=session_id,
        proposal_type=ProposalType.ASSIGN_TASK,
        payload=payload,
        description=description,
    )

    created_proposal = await proposal_repo.create(proposal)

    # Return pending_approval status to signal AI to wait for user approval
    return {
        "status": "pending_approval",
        "proposal_id": str(created_proposal.id),
        "proposal_type": ProposalType.ASSIGN_TASK.value,
        "description": description,
        "message": "ユーザーの承諾待ちです。承諾されるまで「完了しました」とは言わないでください。",
    }


async def create_meeting(
    user_id: str,
    repo: ITaskRepository,
    input_data: CreateMeetingInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    """
    Create a meeting task with fixed time.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Meeting creation data

    Returns:
        Created meeting task as dict
    """
    project_id, owner_id, access_error = await _resolve_project_access(
        user_id,
        input_data.project_id,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    timezone_name = await _resolve_user_timezone(owner_id or user_id, user_repo)
    # Naive ISO input is treated as user's local time.
    start_dt = parse_iso_to_utc_with_user_timezone(input_data.start_time, timezone_name)
    end_dt = parse_iso_to_utc_with_user_timezone(input_data.end_time, timezone_name)

    # Validate time range
    if end_dt <= start_dt:
        raise ValueError("終了時刻は開始時刻より後である必要があります")

    # Calculate duration
    duration_minutes = int((end_dt - start_dt).total_seconds() / 60)

    existing = await _find_existing_meeting(
        repo,
        owner_id,
        start_dt,
        end_dt,
        input_data.title,
        project_id,
    )
    if existing:
        return existing.model_dump(mode="json")

    # Parse recurring_meeting_id if provided
    recurring_meeting_id = UUID(input_data.recurring_meeting_id) if input_data.recurring_meeting_id else None

    task_data = TaskCreate(
        title=input_data.title,
        description=input_data.description,
        start_time=start_dt,
        end_time=end_dt,
        is_fixed_time=True,
        estimated_minutes=duration_minutes,
        location=input_data.location,
        attendees=input_data.attendees,
        meeting_notes=input_data.meeting_notes,
        project_id=project_id,
        recurring_meeting_id=recurring_meeting_id,
        importance=Priority.HIGH,  # 会議は重要度HIGH（変更不可）
        urgency=Priority.HIGH,      # 緊急度HIGH（リスケ不可）
        energy_level=EnergyLevel.LOW,  # 受動的参加
        created_by=CreatedBy.AGENT,
    )

    task = await repo.create(owner_id, task_data)
    return task.model_dump(mode="json")


async def search_similar_tasks(
    user_id: str,
    repo: ITaskRepository,
    input_data: SearchSimilarTasksInput,
    project_repo: Optional[IProjectRepository] = None,
    member_repo: Optional[IProjectMemberRepository] = None,
) -> dict:
    """
    Search for similar tasks to avoid duplicates.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Search parameters

    Returns:
        List of similar tasks with similarity scores
    """
    settings = get_settings()

    project_id, owner_id, access_error = await _resolve_project_access(
        user_id,
        input_data.project_id,
        project_repo,
        member_repo,
    )
    if access_error:
        return access_error

    similar = await repo.find_similar(
        owner_id,
        title=input_data.task_title,
        project_id=project_id,
        threshold=settings.SIMILARITY_THRESHOLD,
        limit=5,
    )

    return {
        "similar_tasks": [
            {
                "task": task.task.model_dump(mode="json"),
                "similarity_score": task.similarity_score,
            }
            for task in similar
        ],
        "count": len(similar),
    }


# ===========================================
# ADK Tool Definitions
# ===========================================


def propose_task_tool(
    proposal_repo: IProposalRepository,
    task_repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    session_id: str,
    auto_approve: bool = False,
    assignment_repo: Optional[ITaskAssignmentRepository] = None,
) -> FunctionTool:
    """Create ADK tool for proposing/creating tasks (with auto-approve option)."""
    async def _tool(input_data: dict) -> dict:
        """propose_task: Propose or create a task based on approval settings.

        Parameters:
            title (str): Task title
            description (str, optional): Task description
            purpose (str, optional): なぜやるか（目的）- タスクを行う理由や背景
            project_id (str, optional): Project ID
            importance (str, optional): Priority
            urgency (str, optional): Urgency
            energy_level (str, optional): Energy level
            estimated_minutes (int, optional): Estimated minutes
            due_date (str, optional): Due date (ISO)
            start_not_before (str, optional): Earliest start datetime (ISO)
            dependency_ids (list[str], optional): Dependency task IDs
            is_fixed_time (bool, optional): Fixed-time meeting flag
            is_all_day (bool, optional): All-day task (vacation, business trip etc). Sets capacity to 0 for the day
            start_time (str, optional): Start time (ISO, not required if is_all_day=true)
            end_time (str, optional): End time (ISO, not required if is_all_day=true)
            location (str, optional): Location
            attendees (list[str], optional): Attendees
            meeting_notes (str, optional): Meeting notes
            assignee_ids (list[str], optional): Assignee IDs (auto-assign on creation)
            proposal_description (str, optional): Proposal description

        Returns:
            dict: Task info or proposal id
        """
        # Extract proposal_description if provided
        proposal_desc = input_data.pop("proposal_description", "")
        return await propose_task(
            user_id, session_id, proposal_repo, task_repo,
            CreateTaskInput(**input_data), proposal_desc, auto_approve,
            assignment_repo, project_repo, member_repo
        )

    _tool.__name__ = "propose_task"
    return FunctionTool(func=_tool)




def propose_task_assignment_tool(
    proposal_repo: IProposalRepository,
    assignment_repo: ITaskAssignmentRepository,
    task_repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    session_id: str,
    auto_approve: bool = False,
) -> FunctionTool:
    """Create ADK tool for proposing/assigning task owners (with auto-approve)."""
    async def _tool(input_data: dict) -> dict:
        """propose_task_assignment: assign task owners with optional approval."""
        proposal_desc = input_data.pop("proposal_description", "")
        return await propose_task_assignment(
            user_id,
            session_id,
            proposal_repo,
            assignment_repo,
            task_repo,
            AssignTaskInput(**input_data),
            proposal_desc,
            auto_approve,
            project_repo,
            member_repo,
        )

    _tool.__name__ = "propose_task_assignment"
    return FunctionTool(func=_tool)


def assign_task_tool(
    assignment_repo: ITaskAssignmentRepository,
    task_repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for assigning tasks."""
    async def _tool(input_data: dict) -> dict:
        """assign_task: タスクの担当者を設定します、E

        Parameters:
            task_id (str): Task ID
            assignee_id (str, optional): Assignee ID (single)
            assignee_ids (list[str], optional): Assignee IDs (multiple)
            proposal_description (str, optional): Proposal description

        Returns:
            dict: Assignment result or proposal payload
        """
        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await propose_task_assignment(
                user_id,
                session_id,
                proposal_repo,
                assignment_repo,
                task_repo,
                AssignTaskInput(**payload),
                proposal_desc,
                False,
                project_repo,
                member_repo,
            )
        return await assign_task(
            user_id,
            assignment_repo,
            task_repo,
            AssignTaskInput(**payload),
            project_repo,
            member_repo,
        )

    _tool.__name__ = "assign_task"
    return FunctionTool(func=_tool)


def create_task_tool(
    repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    assignment_repo: Optional[ITaskAssignmentRepository] = None,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for creating tasks."""
    async def _tool(input_data: dict) -> dict:
        """create_task: 新しいタスクを作成します。作成前にsearch_similar_tasksで重複チェック推奨。

        **⚠️ 依存関係の設定（重要）**:
        タスク作成時には、以下の手順で依存関係を判断してください：
        1. list_tasks で同じプロジェクト内の未完了タスク（TODO/IN_PROGRESS）を取得
        2. 新しいタスクが既存タスクの完了を前提とする場合、dependency_ids に設定
        3. 例: 「確定申告書を提出する」を作る場合 → 「領収書を整理する」が未完了なら依存関係を設定
        4. 並行実行可能なタスク（関係ないタスク）には依存関係を設定しない

        Parameters:
            title (str): タスクのタイトル（必須）※task_titleでも可
            description (str, optional): タスクの詳細説明
            purpose (str, optional): なぜやるか（目的）- タスクを行う理由や背景。ユーザーから聞き出して設定すると優先度判断に役立つ
            project_id (str, optional): プロジェクトID
            importance (str, optional): 重要度 (HIGH/MEDIUM/LOW)、デフォルト: MEDIUM
            urgency (str, optional): 緊急度 (HIGH/MEDIUM/LOW)、デフォルト: MEDIUM
            energy_level (str, optional): 必要エネルギー (HIGH/LOW)、デフォルト: LOW
            estimated_minutes (int, optional): 見積もり時間（分）
            due_date (str, optional): 期限（ISO形式）
            start_not_before (str, optional): 着手可能日時（ISO形式）
            parent_id (str, optional): 親タスクID（UUID文字列）- サブタスクとして作成する場合に必須
            order_in_parent (int, optional): 親タスク内での順序（1から開始）- サブタスクの場合に推奨
            guide (str, optional): サブタスクの進め方ガイド（Markdown）
            dependency_ids (list[str], optional): このタスクが依存する他のタスクのIDリスト（UUID文字列）
            same_day_allowed (bool, optional): ?????????????????????????? true
            min_gap_days (int, optional): ????????????????????????? 0
            touchpoint_count (int, optional): ??????????????????? estimated_minutes ???????????
            touchpoint_minutes (int, optional): ????????????estimated_minutes ?????
            touchpoint_gap_days (int, optional): ??????????????????????? 0
            touchpoint_steps (list[TouchpointStep], optional): ??????????????summary/details?
            is_fixed_time (bool, optional): 会議・固定時間イベントの場合true
            is_all_day (bool, optional): 終日タスク（休暇・出張など）。trueの場合、その日のキャパシティを0にする
            start_time (str, optional): 開始時刻（ISO形式、is_fixed_time=trueの場合必須、is_all_day=trueの場合不要）
            end_time (str, optional): 終了時刻（ISO形式、is_fixed_time=trueの場合必須、is_all_day=trueの場合不要）
            location (str, optional): 場所（会議用）
            attendees (list[str], optional): 参加者リスト（会議用）
            meeting_notes (str, optional): 議事録・メモ（会議用）
            assignee_ids (list[str], optional): 担当者IDリスト（UUID文字列）

        Returns:
            dict: 作成されたタスク情報（assignmentsフィールドに担当者割り当て情報を含む）
        """
        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await propose_task(
                user_id,
                session_id,
                proposal_repo,
                repo,
                CreateTaskInput(**payload),
                proposal_desc,
                False,
                assignment_repo,
                project_repo,
                member_repo,
                user_repo,
            )
        return await create_task(
            user_id,
            repo,
            CreateTaskInput(**payload),
            assignment_repo,
            project_repo,
            member_repo,
            user_repo,
        )

    _tool.__name__ = "create_task"
    return FunctionTool(func=_tool)


def update_task_tool(
    repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for updating tasks."""
    async def _tool(input_data: dict) -> dict:
        """update_task: 既存のタスクを更新します（タイトル、説明、ステータス、進捗率、日付等）。

        Parameters:
            task_id (str): タスクID（UUID文字列、必須）
            title (str, optional): タスクのタイトル
            description (str, optional): タスクの詳細説明
            purpose (str, optional): なぜやるか（目的）- タスクを行う理由や背景
            project_id (str, optional): プロジェクトID（UUID文字列、タスクを別プロジェクトに移動）
            phase_id (str, optional): フェーズID（UUID文字列、プロジェクト内での分類）
            status (str, optional): ステータス (TODO/IN_PROGRESS/WAITING/DONE)
            importance (str, optional): 重要度 (HIGH/MEDIUM/LOW)
            urgency (str, optional): 緊急度 (HIGH/MEDIUM/LOW)
            energy_level (str, optional): 必要エネルギー (HIGH/MEDIUM/LOW)
            estimated_minutes (int, optional): 見積もり時間（分、1-480）
            due_date (str, optional): 期限（ISO形式: YYYY-MM-DDTHH:MM:SS）
            start_not_before (str, optional): 着手可能日時（ISO形式: YYYY-MM-DDTHH:MM:SS）
            parent_id (str, optional): 親タスクID（UUID文字列、サブタスク化/解除）
            order_in_parent (int, optional): 親タスク内での順序（1から始まる整数）
            dependency_ids (list[str], optional): 依存タスクIDリスト（UUID文字列のリスト）
            same_day_allowed (bool, optional): ?????????????????????????? true
            min_gap_days (int, optional): ????????????????????????? 0
            touchpoint_count (int, optional): ??????????????????? estimated_minutes ???????????
            touchpoint_minutes (int, optional): ????????????estimated_minutes ?????
            touchpoint_gap_days (int, optional): ??????????????????????? 0
            touchpoint_steps (list[TouchpointStep], optional): ??????????????summary/details?
            progress (int, optional): 進捗率（0-100%）。タスクの完成度を設定
            source_capture_id (str, optional): 元Capture ID（UUID文字列）
            is_fixed_time (bool, optional): 会議・固定時間イベントの場合true
            is_all_day (bool, optional): 終日タスク（休暇・出張など）。trueの場合、その日のキャパシティを0にする
            start_time (str, optional): 開始時刻（ISO形式）
            end_time (str, optional): 終了時刻（ISO形式）
            location (str, optional): 場所（会議用）
            attendees (list[str], optional): 参加者リスト（会議用）
            meeting_notes (str, optional): 議事録・メモ（会議用）
            completion_note (str, optional): メモ（学んだこと、気づき、作業記録など。いつでも記入可能。Achievement生成にも活用される）

        Returns:
            dict: 更新されたタスク情報
        """
        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "update_task",
                payload,
                proposal_desc,
            )
        return await update_task(
            user_id,
            repo,
            UpdateTaskInput(**payload),
            project_repo,
            member_repo,
            user_repo,
        )

    _tool.__name__ = "update_task"
    return FunctionTool(func=_tool)


def delete_task_tool(
    repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for deleting tasks."""
    async def _tool(input_data: dict) -> dict:
        """delete_task: タスクを削除します。

        Parameters:
            task_id (str): 削除するタスクのID（UUID文字列、必須）

        Returns:
            dict: 削除結果 (success, task_id, message)
        """
        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "delete_task",
                payload,
                proposal_desc,
            )
        return await delete_task(
            user_id,
            repo,
            DeleteTaskInput(**payload),
            project_repo,
            member_repo,
        )

    _tool.__name__ = "delete_task"
    return FunctionTool(func=_tool)


def search_similar_tasks_tool(
    repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for searching similar tasks."""
    async def _tool(input_data: dict) -> dict:
        """search_similar_tasks: 類似タスクを検索して重複をチェックします。

        Parameters:
            task_title (str): 検索するタスクのタイトル（必須）
            project_id (str, optional): プロジェクトID（指定時はそのプロジェクト内のみ検索）

        Returns:
            dict: 類似タスクのリストとスコア
        """
        return await search_similar_tasks(
            user_id,
            repo,
            SearchSimilarTasksInput(**input_data),
            project_repo,
            member_repo,
        )

    _tool.__name__ = "search_similar_tasks"
    return FunctionTool(func=_tool)


def list_tasks_tool(
    repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for listing tasks."""
    async def _tool(input_data: dict) -> dict:
        """list_tasks: タスク一覧を取得します（依存関係判断に利用）。

        Parameters:
            project_id (str, optional): プロジェクトID（指定時はそのプロジェクト内のみ取得）
            status_filter (list[str], optional): ステータスフィルタ（例: ["TODO", "IN_PROGRESS"]）
            limit (int, optional): 取得件数上限（デフォルト: 50、最大: 100）

        Returns:
            dict: タスク一覧（各タスクにはid, title, description, status, dependency_ids等を含む）
        """
        return await list_tasks(
            user_id,
            repo,
            ListTasksInput(**input_data),
            project_repo,
            member_repo,
        )

    _tool.__name__ = "list_tasks"
    return FunctionTool(func=_tool)


def get_task_tool(
    repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for getting a single task."""
    async def _tool(input_data: dict) -> dict:
        """get_task: タスクの詳細を取得します（meeting_notesを含む）。

        Parameters:
            task_id (str): タスクID（UUID文字列）

        Returns:
            dict: タスクの詳細情報（id, title, description, status, meeting_notes等を含む）
        """
        return await get_task(
            user_id,
            repo,
            GetTaskInput(**input_data),
            project_repo,
            member_repo,
        )

    _tool.__name__ = "get_task"
    return FunctionTool(func=_tool)


def list_task_assignments_tool(
    assignment_repo: ITaskAssignmentRepository,
    task_repo: ITaskRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
) -> FunctionTool:
    # Create ADK tool for listing task assignments.
    async def _tool(input_data: dict) -> dict:
        # list_task_assignments: List assignments for a task by task ID.
        return await list_task_assignments(
            user_id,
            assignment_repo,
            task_repo,
            ListTaskAssignmentsInput(**input_data),
            project_repo,
            member_repo,
        )

    _tool.__name__ = "list_task_assignments"
    return FunctionTool(func=_tool)


def list_project_assignments_tool(
    assignment_repo: ITaskAssignmentRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
) -> FunctionTool:
    # Create ADK tool for listing project assignments.
    async def _tool(input_data: dict) -> dict:
        # list_project_assignments: List assignments for a project by project ID.
        return await list_project_assignments(
            user_id,
            assignment_repo,
            project_repo,
            member_repo,
            ListProjectAssignmentsInput(**input_data),
        )

    _tool.__name__ = "list_project_assignments"
    return FunctionTool(func=_tool)


def create_meeting_tool(
    repo: ITaskRepository,
    proposal_repo: IProposalRepository,
    project_repo: Optional[IProjectRepository],
    member_repo: Optional[IProjectMemberRepository],
    user_id: str,
    session_id: str,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for creating meetings."""
    async def _tool(input_data: dict) -> dict:
        """create_meeting: Register a fixed-time meeting event.

        Use ONLY for actual meetings/appointments with other people (attendees exist).
        Do NOT use for tasks that merely have a time-based deadline.
        Examples of correct use: team meetings, client calls, interviews, seminars.
        Examples of INCORRECT use: "submit report by 14:00", "finish review by 15:00".
        For time-based deadlines, use create_task with due_date instead.

        Parameters:
            title (str): Meeting title
            start_time (str): Start time (ISO, interpreted in user timezone when offset is omitted)
            end_time (str): End time (ISO, interpreted in user timezone when offset is omitted)
            location (str, optional): Location
            attendees (list[str], optional): Attendees
            description (str, optional): Agenda / description
            meeting_notes (str, optional): Notes
            project_id (str, optional): Project ID

        Returns:
            dict: Meeting task info or proposal id
        """
        meeting_input = CreateMeetingInput(**input_data)
        project_id, owner_id, access_error = await _resolve_project_access(
            user_id,
            meeting_input.project_id,
            project_repo,
            member_repo,
        )
        if access_error:
            return access_error

        timezone_name = await _resolve_user_timezone(owner_id or user_id, user_repo)
        start_dt = parse_iso_to_utc_with_user_timezone(meeting_input.start_time, timezone_name)
        end_dt = parse_iso_to_utc_with_user_timezone(meeting_input.end_time, timezone_name)
        if end_dt <= start_dt:
            raise ValueError("End time must be after start time.")

        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)

        existing = await _find_existing_meeting(
            repo,
            owner_id,
            start_dt,
            end_dt,
            meeting_input.title,
            project_id,
        )
        if existing:
            return existing.model_dump(mode="json")

        task_input = CreateTaskInput(
            title=meeting_input.title,
            description=meeting_input.description,
            project_id=meeting_input.project_id,
            importance=Priority.HIGH,
            urgency=Priority.HIGH,
            energy_level=EnergyLevel.LOW,
            estimated_minutes=duration_minutes,
            is_fixed_time=True,
            start_time=meeting_input.start_time,
            end_time=meeting_input.end_time,
            location=meeting_input.location,
            attendees=meeting_input.attendees,
            meeting_notes=meeting_input.meeting_notes,
        )
        proposal_desc = f'Meeting "{meeting_input.title}" will be added to your schedule.'
        if auto_approve:
            return await create_task(
                user_id,
                repo,
                task_input,
                None,
                project_repo,
                member_repo,
                user_repo,
            )
        return await propose_task(
            user_id,
            session_id,
            proposal_repo,
            repo,
            task_input,
            proposal_desc,
            False,
            None,
            project_repo,
            member_repo,
            user_repo,
        )

    _tool.__name__ = "create_meeting"
    return FunctionTool(func=_tool)
