"""
Tasks API endpoints.

CRUD operations for tasks.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    BlockerRepo,
    CurrentUser,
    DailySchedulePlanRepo,
    PostponeRepo,
    ProjectMemberRepo,
    ProjectRepo,
    ScheduleSettingsRepo,
    ScheduleSnapshotRepo,
    TaskAssignmentRepo,
    TaskRepo,
    UserRepo,
    get_user_repository,
)
from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models.collaboration import (
    Blocker,
    BlockerCreate,
    BlockerUpdate,
    TaskAssignment,
    TaskAssignmentCreate,
    TaskAssignmentsCreate,
    TaskAssignmentUpdate,
)
from app.models.enums import CreatedBy, ProjectVisibility, TaskStatus
from app.models.postpone import DoTodayRequest, PostponeEvent, PostponeRequest, PostponeStats
from app.models.schedule import ScheduleResponse, TodayTasksResponse
from app.models.schedule_plan import SchedulePlanResponse, ScheduleTimeBlock, TimeBlockMoveRequest
from app.models.task import CompletionCheckResponse, Task, TaskCreate, TaskUpdate
from app.services.assignee_utils import is_invitation_assignee
from app.services.daily_schedule_plan_service import DEFAULT_PLAN_DAYS, DailySchedulePlanService
from app.services.scheduler_service import SchedulerService
from app.services.task_application_service import TaskApplicationService
from app.utils.datetime_utils import (
    all_day_bounds_to_utc,
    get_user_today,
    normalize_timezone,
)
from app.utils.dependency_validator import DependencyValidator

router = APIRouter()


async def _validate_assignees_are_project_members(
    assignee_ids: list[str],
    task: Task,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_id: str,
) -> None:
    """Validate that all assignee_ids are members of the task's project."""
    if not task.project_id:
        return  # No project = personal task, no member validation needed

    project = await project_repo.get(user_id, task.project_id)
    if not project:
        return

    members = await member_repo.list_by_project(task.project_id)
    valid_ids = {m.member_user_id for m in members}

    invalid = []
    for aid in assignee_ids:
        if is_invitation_assignee(aid):
            continue  # Invitation-based assignees are allowed
        if aid not in valid_ids:
            invalid.append(aid)

    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"以下のユーザーはプロジェクトのメンバーではありません: {', '.join(invalid)}",
        )


def get_scheduler_service() -> SchedulerService:
    """Get SchedulerService instance."""
    return SchedulerService()


def _get_task_application_service(
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: Optional[TaskAssignmentRepo] = None,
    member_repo: Optional[ProjectMemberRepo] = None,
    postpone_repo: Optional[PostponeRepo] = None,
    user_repo: Optional[UserRepo] = None,
) -> TaskApplicationService:
    return TaskApplicationService(
        task_repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        member_repo=member_repo,
        user_repo=user_repo or get_user_repository(),
        postpone_repo=postpone_repo,
    )


def _to_task_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BusinessLogicError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


async def _resolve_user_timezone(
    user_id: str,
    user_repo: Optional[UserRepo] = None,
) -> str:
    repo = user_repo or get_user_repository()
    try:
        user_account = await repo.get(UUID(user_id))
    except (TypeError, ValueError):
        user_account = None
    return normalize_timezone(user_account.timezone if user_account else None)


async def load_plan_windows(
    user: CurrentUser,
    tasks: list[Task],
    project_repo: ProjectRepo,
    snapshot_repo: ScheduleSnapshotRepo,
) -> dict[UUID, tuple[Optional[date], Optional[date]]]:
    if not tasks:
        return {}
    task_ids = {task.id for task in tasks}
    projects = await project_repo.list(user.id, limit=1000)
    planned_windows: dict[UUID, tuple[Optional[date], Optional[date]]] = {}
    for project in projects:
        snapshot = await snapshot_repo.get_active(user.id, project.id)
        if not snapshot:
            continue
        for snapshot_task in snapshot.tasks:
            if snapshot_task.task_id not in task_ids:
                continue
            if snapshot_task.planned_start or snapshot_task.planned_end:
                planned_windows[snapshot_task.task_id] = (
                    snapshot_task.planned_start,
                    snapshot_task.planned_end,
                )
    return planned_windows


async def load_project_priorities(project_repo: ProjectRepo, user_id: str) -> dict[UUID, int]:
    """Load project priorities for scheduling."""
    projects = await project_repo.list(user_id, limit=1000)
    return {project.id: project.priority for project in projects}


async def _get_task_or_404(
    user: CurrentUser, repo: TaskRepo, task_id: UUID, project_repo: ProjectRepo = None
) -> tuple[Task, str]:
    """
    Get task by ID with permission check.
    Returns (task, owner_user_id) where owner_user_id is the project owner's ID.
    For personal tasks, owner_user_id is the user's own ID.
    """
    # First try personal access (Inbox tasks)
    task = await repo.get(user.id, task_id)
    if task:
        if task.project_id and project_repo:
            project = await project_repo.get(user.id, task.project_id)
            if project:
                return task, project.user_id
        else:
            return task, user.id

    # If not found and project_repo is provided, try project-based access
    if project_repo:
        task = await repo.get_by_id(user.id, task_id)
        if task and task.project_id:
            project = await project_repo.get(user.id, task.project_id)
            if project:
                return task, project.user_id  # Return project owner's user_id

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Task {task_id} not found",
    )


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Create a new task."""
    service = _get_task_application_service(repo, project_repo, assignment_repo)
    try:
        result = await service.create_task(user.id, task)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc
    return result.task


@router.get("", response_model=list[Task])
async def list_tasks(
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    include_done: bool = Query(False, description="Include completed tasks"),
    only_meetings: bool = Query(False, description="会議のみ取得"),
    exclude_meetings: bool = Query(False, description="会議を除外"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List tasks with optional filters."""

    async def _fetch_scoped_tasks(
        query_user_id: str,
        query_project_id: Optional[UUID],
    ) -> list[Task]:
        batch_size = max(limit, 200)
        scan_offset = 0
        collected: list[Task] = []
        while True:
            batch = await repo.list(
                query_user_id,
                project_id=query_project_id,
                status=status,
                include_done=include_done,
                limit=batch_size,
                offset=scan_offset,
            )
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < batch_size:
                break
            scan_offset += batch_size
        return collected

    def _apply_meeting_filters(items: list[Task]) -> list[Task]:
        if only_meetings:
            return [task for task in items if task.is_fixed_time]
        if exclude_meetings:
            return [task for task in items if not task.is_fixed_time]
        return items

    # If project_id is specified, check membership and use project owner's user_id
    if project_id:
        project = await project_repo.get(user.id, project_id)
        if project:
            query_user_id = project.user_id  # Use project owner's ID
        else:
            query_user_id = user.id
        tasks = await _fetch_scoped_tasks(query_user_id, project_id)
        tasks = _apply_meeting_filters(tasks)
        # Paginate by parent tasks only, then include their subtasks
        parent_tasks = [t for t in tasks if not t.parent_id]
        paginated_parents = parent_tasks[offset : offset + limit]
        parent_ids = {t.id for t in paginated_parents}
        subtasks = [t for t in tasks if t.parent_id and t.parent_id in parent_ids]
        return paginated_parents + subtasks
    else:
        # Special case: only_meetings - fetch all user's meetings across all projects
        if only_meetings:
            all_tasks = await _fetch_scoped_tasks(user.id, None)
            tasks = _apply_meeting_filters(all_tasks)
            return tasks[offset : offset + limit]
        else:
            # My Tasks mode (No project_id):
            #   - Personal tasks (project_id NULL): all
            #   - PRIVATE project tasks: all (single-user projects)
            #   - TEAM project tasks: only assigned to me

            # 1. Get all tasks owned by this user
            all_user_tasks = await _fetch_scoped_tasks(user.id, None)

            # 2. Get assignments for TEAM project filtering
            assignments = await assignment_repo.list_for_assignee(user.id)
            assigned_task_ids = {a.task_id for a in assignments}

            # 3. Build TEAM project ID set
            projects = await project_repo.list(user.id, limit=1000)
            team_project_ids = {p.id for p in projects if p.visibility == ProjectVisibility.TEAM}

            # 4. Filter: keep personal + PRIVATE project + assigned TEAM project
            def should_include(task: Task) -> bool:
                if not task.project_id:
                    return True  # Personal task
                if task.project_id not in team_project_ids:
                    return True  # PRIVATE project task
                # TEAM project: only if assigned to me
                return task.id in assigned_task_ids

            tasks = [t for t in all_user_tasks if should_include(t)]

            # Also include TEAM project tasks assigned to me but owned by others
            assigned_tasks = await repo.get_many(list(assigned_task_ids))
            existing_ids = {t.id for t in tasks}
            for t in assigned_tasks:
                if t.id in existing_ids:
                    continue
                if status and t.status.value != status:
                    continue
                if not include_done and t.status == TaskStatus.DONE:
                    continue
                tasks.append(t)

            tasks.sort(key=lambda t: t.created_at, reverse=True)
            tasks = _apply_meeting_filters(tasks)

            # Paginate by parent tasks only, then include their subtasks
            parent_tasks = [t for t in tasks if not t.parent_id]
            paginated_parents = parent_tasks[offset : offset + limit]
            parent_ids = {t.id for t in paginated_parents}
            subtasks = [t for t in tasks if t.parent_id and t.parent_id in parent_ids]
            return paginated_parents + subtasks

    return []


@router.get("/schedule", response_model=SchedulePlanResponse)
async def get_task_schedule(
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    snapshot_repo: ScheduleSnapshotRepo,
    user_repo: UserRepo,
    settings_repo: ScheduleSettingsRepo,
    plan_repo: DailySchedulePlanRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    start_date: Optional[date] = Query(None, description="Schedule start date"),
    capacity_hours: Optional[float] = Query(
        None, description="Daily capacity in hours (default: 8)"
    ),
    buffer_hours: Optional[float] = Query(None, description="Daily buffer hours"),
    capacity_by_weekday: Optional[str] = Query(
        None,
        description="JSON array of 7 daily capacity values (Sun..Sat)",
    ),
    max_days: int = Query(DEFAULT_PLAN_DAYS, ge=1, le=365, description="Maximum days to schedule"),
    filter_by_assignee: bool = Query(True, description="Only show tasks assigned to me"),
    apply_plan_constraints: bool = Query(True, description="Apply project plan windows"),
):
    """Build a multi-day schedule for tasks."""
    plan_service = DailySchedulePlanService(
        task_repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        snapshot_repo=snapshot_repo,
        user_repo=user_repo,
        settings_repo=settings_repo,
        plan_repo=plan_repo,
        scheduler_service=scheduler_service,
    )
    return await plan_service.get_plan_or_forecast(
        user_id=user.id,
        start_date=start_date,
        max_days=max_days,
        filter_by_assignee=filter_by_assignee,
        apply_plan_constraints=apply_plan_constraints,
    )


@router.post("/schedule/plan", response_model=SchedulePlanResponse)
async def recalculate_schedule_plan(
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    snapshot_repo: ScheduleSnapshotRepo,
    user_repo: UserRepo,
    settings_repo: ScheduleSettingsRepo,
    plan_repo: DailySchedulePlanRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    start_date: Optional[date] = Query(None, description="Schedule start date"),
    max_days: int = Query(DEFAULT_PLAN_DAYS, ge=1, le=365, description="Maximum days to schedule"),
    from_now: bool = Query(False, description="Recalculate from current time for today"),
    filter_by_assignee: bool = Query(True, description="Only show tasks assigned to me"),
    apply_plan_constraints: bool = Query(True, description="Apply project plan windows"),
):
    plan_service = DailySchedulePlanService(
        task_repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        snapshot_repo=snapshot_repo,
        user_repo=user_repo,
        settings_repo=settings_repo,
        plan_repo=plan_repo,
        scheduler_service=scheduler_service,
    )
    return await plan_service.build_plan(
        user_id=user.id,
        start_date=start_date,
        max_days=max_days,
        from_now=from_now,
        filter_by_assignee=filter_by_assignee,
        apply_plan_constraints=apply_plan_constraints,
    )


@router.patch("/schedule/plan/time-block", response_model=ScheduleTimeBlock)
async def move_time_block(
    body: TimeBlockMoveRequest,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    snapshot_repo: ScheduleSnapshotRepo,
    user_repo: UserRepo,
    settings_repo: ScheduleSettingsRepo,
    plan_repo: DailySchedulePlanRepo,
):
    """Move or resize a single time block within the schedule plan."""
    plan_service = DailySchedulePlanService(
        task_repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        snapshot_repo=snapshot_repo,
        user_repo=user_repo,
        settings_repo=settings_repo,
        plan_repo=plan_repo,
    )
    result = await plan_service.move_time_block(user_id=user.id, request=body)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time block not found in schedule plan",
        )
    return result


@router.get("/today", response_model=TodayTasksResponse)
async def get_today_tasks(
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    snapshot_repo: ScheduleSnapshotRepo,
    user_repo: UserRepo,
    settings_repo: ScheduleSettingsRepo,
    plan_repo: DailySchedulePlanRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    target_date: Optional[date] = Query(None, description="Target date (default: today)"),
    capacity_hours: Optional[float] = Query(
        None, description="Daily capacity in hours (default: 8)"
    ),
    buffer_hours: Optional[float] = Query(None, description="Daily buffer hours"),
    capacity_by_weekday: Optional[str] = Query(
        None,
        description="JSON array of 7 daily capacity values (Sun..Sat)",
    ),
    max_days: int = Query(30, ge=1, le=365, description="Maximum days to schedule"),
    filter_by_assignee: bool = Query(True, description="Only show tasks assigned to me"),
    apply_plan_constraints: bool = Query(True, description="Apply project plan windows"),
):
    """Get today's tasks derived from the schedule."""
    user_timezone = await _resolve_user_timezone(user.id, user_repo)

    plan_service = DailySchedulePlanService(
        task_repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        snapshot_repo=snapshot_repo,
        user_repo=user_repo,
        settings_repo=settings_repo,
        plan_repo=plan_repo,
        scheduler_service=scheduler_service,
    )
    schedule_plan = await plan_service.get_plan_or_forecast(
        user_id=user.id,
        start_date=target_date,
        max_days=1,
        filter_by_assignee=filter_by_assignee,
        apply_plan_constraints=apply_plan_constraints,
    )
    tasks = await repo.list(user.id, include_done=True, limit=1000)
    project_priorities = await load_project_priorities(project_repo, user.id)
    resolved_date = target_date or schedule_plan.start_date or get_user_today(user_timezone)
    return scheduler_service.get_today_tasks(
        ScheduleResponse(
            start_date=schedule_plan.start_date,
            days=schedule_plan.days,
            tasks=schedule_plan.tasks,
            unscheduled_task_ids=schedule_plan.unscheduled_task_ids,
            excluded_tasks=schedule_plan.excluded_tasks,
        ),
        tasks,
        project_priorities=project_priorities,
        today=resolved_date,
        user_timezone=user_timezone,
    )


@router.get("/postpone-stats", response_model=PostponeStats)
async def get_postpone_stats(
    user: CurrentUser,
    postpone_repo: PostponeRepo,
    repo: TaskRepo,
    days: int = Query(7, ge=1, le=90, description="集計期間（日数）"),
):
    """Get aggregate postponement statistics for the user."""
    from datetime import timedelta

    user_timezone = await _resolve_user_timezone(user.id)
    since = get_user_today(user_timezone) - timedelta(days=days)
    events = await postpone_repo.list_by_user(user.id, since=since)

    task_counts: dict[UUID, int] = {}
    for event in events:
        task_counts[event.task_id] = task_counts.get(event.task_id, 0) + 1

    from app.models.postpone import PostponeTaskSummary

    most_postponed = []
    sorted_tasks = sorted(task_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for tid, count in sorted_tasks:
        task = await repo.get_by_id(user.id, tid)
        title = task.title if task else "Unknown"
        most_postponed.append(
            PostponeTaskSummary(task_id=tid, task_title=title, postpone_count=count)
        )

    return PostponeStats(
        total_postpones=len(events),
        unique_tasks=len(task_counts),
        most_postponed=most_postponed,
    )


@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
):
    """Get a task by ID."""
    # First try personal access (Inbox tasks owned by user)
    task = await repo.get(user.id, task_id)
    if task:
        return task

    # Use get_by_id to find task regardless of user_id (covers project tasks)
    task = await repo.get_by_id(user.id, task_id)
    if task:
        # Verify user has access to the task's project
        if task.project_id:
            project = await project_repo.get(user.id, task.project_id)
            if project:
                return task
        else:
            # Personal task found by get_by_id but not by get — shouldn't happen,
            # but return it as a safety net
            return task

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Task {task_id} not found",
    )


@router.patch("/{task_id}", response_model=Task)
async def update_task(
    task_id: UUID,
    update: TaskUpdate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Update a task."""
    service = _get_task_application_service(repo, project_repo, assignment_repo)
    try:
        return await service.update_task(user.id, task_id, update)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc

    # Find task - try personal access first, then project-based
    current_task = await repo.get(user.id, task_id)
    task_owner_user_id = user.id
    task_project_id = None

    if not current_task:
        # Use get_by_id to find task regardless of user_id (covers project tasks)
        current_task = await repo.get_by_id(user.id, task_id)
        if current_task and current_task.project_id:
            # Verify user has access to the task's project
            project = await project_repo.get(user.id, current_task.project_id)
            if project:
                task_project_id = current_task.project_id
                task_owner_user_id = project.user_id
            else:
                current_task = None  # No access
    else:
        task_project_id = current_task.project_id
        if task_project_id:
            project = await project_repo.get(user.id, task_project_id)
            if project:
                task_owner_user_id = project.user_id
            else:
                current_task = None

    if not current_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    if update.is_all_day is True:
        user_timezone = await _resolve_user_timezone(task_owner_user_id)
        reference = (
            update.start_time
            or update.due_date
            or update.start_not_before
            or current_task.start_time
            or current_task.due_date
            or current_task.start_not_before
        )
        start_utc, end_utc = all_day_bounds_to_utc(user_timezone, reference=reference)
        update.start_time = start_utc
        update.end_time = end_utc
        update.is_fixed_time = True

    # Guard: requires_all_completion tasks cannot be directly set to DONE
    if update.status == TaskStatus.DONE and current_task.requires_all_completion:
        owner_user_id = task_project_id and (await project_repo.get(user.id, task_project_id))
        lookup_uid = owner_user_id.user_id if owner_user_id else user.id
        assignments = await assignment_repo.list_by_task(lookup_uid, task_id)
        if len(assignments) > 1:
            all_checked = all(a.status == TaskStatus.DONE for a in assignments)
            if not all_checked:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="全員の確認が完了するまでタスクを完了にできません",
                )

    # Validate dependencies before updating
    if update.dependency_ids is not None or update.parent_id is not None:
        validator = DependencyValidator(repo)

        try:
            new_dependency_ids = (
                update.dependency_ids
                if update.dependency_ids is not None
                else current_task.dependency_ids
            )
            new_parent_id = (
                update.parent_id if update.parent_id is not None else current_task.parent_id
            )

            if new_dependency_ids:
                await validator.validate_dependencies(
                    task_id,
                    new_dependency_ids,
                    task_owner_user_id,
                    new_parent_id,
                    project_id=task_project_id,
                )

            if update.parent_id is not None:
                await validator.validate_parent_child_consistency(
                    task_id,
                    update.parent_id,
                    task_owner_user_id,
                )

        except BusinessLogicError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    try:
        return await repo.update(user.id, task_id, update, project_id=task_project_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
):
    """Delete a task."""
    service = _get_task_application_service(repo, project_repo)
    try:
        deleted = await service.delete_task(user.id, task_id)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return None


@router.get("/{task_id}/subtasks", response_model=list[Task])
async def get_subtasks(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
):
    """Get all subtasks of a parent task."""
    task, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    return await repo.get_subtasks(owner_user_id, task_id, project_id=task.project_id)


def _extract_action_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for prefix in ("- [ ]", "* [ ]", "- TODO", "* TODO", "TODO:"):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
                break
        else:
            continue
        if line and line not in items:
            items.append(line)
    return items


@router.post(
    "/{task_id}/action-items", response_model=list[Task], status_code=status.HTTP_201_CREATED
)
async def create_action_items(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
):
    """Create action item subtasks from meeting notes."""
    task, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    if not task.meeting_notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="meeting_notes is empty",
        )
    action_items = _extract_action_items(task.meeting_notes)
    if not action_items:
        return []

    existing_subtasks = await repo.get_subtasks(
        owner_user_id,
        task_id,
        project_id=task.project_id,
    )
    existing_titles = {subtask.title for subtask in existing_subtasks}
    max_order = max([subtask.order_in_parent or 0 for subtask in existing_subtasks] + [0])

    created_subtasks: list[Task] = []
    for index, title in enumerate(action_items, start=1):
        if title in existing_titles:
            continue
        created = await repo.create(
            owner_user_id,
            TaskCreate(
                title=title,
                project_id=task.project_id,
                phase_id=task.phase_id,
                parent_id=task.id,
                order_in_parent=max_order + index,
                created_by=CreatedBy.AGENT,
            ),
        )
        created_subtasks.append(created)

    return created_subtasks


@router.post("/{task_id}/check-completion", response_model=CompletionCheckResponse)
async def check_completion(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Toggle the current user's completion check on a requires_all_completion task."""
    task, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    if not task.requires_all_completion:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このタスクは全員確認が必要なタスクではありません",
        )

    assignments = await assignment_repo.list_by_task(owner_user_id, task_id)
    my_assignment = next((a for a in assignments if a.assignee_id == user.id), None)
    if not my_assignment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="このタスクにアサインされていません",
        )

    # Toggle my assignment status
    new_status = None if my_assignment.status == TaskStatus.DONE else TaskStatus.DONE
    await assignment_repo.update(
        owner_user_id, my_assignment.id, TaskAssignmentUpdate(status=new_status)
    )

    # Re-fetch and evaluate
    assignments = await assignment_repo.list_by_task(owner_user_id, task_id)
    checked_count = sum(1 for a in assignments if a.status == TaskStatus.DONE)
    total_count = len(assignments)

    # Auto-manage task status
    if total_count > 0 and checked_count == total_count:
        await repo.update(owner_user_id, task_id, TaskUpdate(status=TaskStatus.DONE))
    elif checked_count > 0:
        if task.status != TaskStatus.WAITING:
            await repo.update(owner_user_id, task_id, TaskUpdate(status=TaskStatus.WAITING))
    else:
        # All unchecked — revert to TODO if it was WAITING/DONE from this feature
        if task.status in (TaskStatus.WAITING, TaskStatus.DONE):
            await repo.update(owner_user_id, task_id, TaskUpdate(status=TaskStatus.TODO))

    updated_task = await repo.get(owner_user_id, task_id, project_id=task.project_id)
    return CompletionCheckResponse(
        task=updated_task,
        checked_count=checked_count,
        total_count=total_count,
    )


@router.get("/{task_id}/assignment", response_model=TaskAssignment)
async def get_task_assignment(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Get assignment for a task (returns first assignee)."""
    _, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    assignment = await assignment_repo.get_by_task(owner_user_id, task_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment for task {task_id} not found",
        )
    return assignment


@router.get("/{task_id}/assignments", response_model=list[TaskAssignment])
async def list_task_assignments(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """List all assignments for a task (multiple assignees)."""
    _, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    return await assignment_repo.list_by_task(owner_user_id, task_id)


@router.post(
    "/{task_id}/assignment", response_model=TaskAssignment, status_code=status.HTTP_201_CREATED
)
async def assign_task(
    task_id: UUID,
    assignment: TaskAssignmentCreate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    member_repo: ProjectMemberRepo,
):
    """Assign a task to a member (upsert)."""
    service = _get_task_application_service(repo, project_repo, assignment_repo, member_repo)
    try:
        return await service.assign_task(user.id, task_id, assignment)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc


@router.put("/{task_id}/assignments", response_model=list[TaskAssignment])
async def assign_task_multiple(
    task_id: UUID,
    assignments: TaskAssignmentsCreate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    member_repo: ProjectMemberRepo,
):
    """Assign a task to multiple members. Replaces existing assignments."""
    service = _get_task_application_service(repo, project_repo, assignment_repo, member_repo)
    try:
        return await service.assign_task_multiple(user.id, task_id, assignments)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc


@router.patch("/assignments/{assignment_id}", response_model=TaskAssignment)
async def update_task_assignment(
    assignment_id: UUID,
    update: TaskAssignmentUpdate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Update assignment fields."""
    try:
        service = _get_task_application_service(repo, project_repo, assignment_repo)
        return await service.update_assignment(user.id, assignment_id, update)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc


@router.delete("/{task_id}/assignment", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_task(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Remove assignment from a task."""
    service = _get_task_application_service(repo, project_repo, assignment_repo)
    try:
        deleted = await service.unassign_task(user.id, task_id)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment for task {task_id} not found",
        )


@router.get("/{task_id}/blockers", response_model=list[Blocker])
async def list_task_blockers(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    blocker_repo: BlockerRepo,
):
    """List blockers for a task."""
    _, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    return await blocker_repo.list_by_task(owner_user_id, task_id)


@router.post("/{task_id}/blockers", response_model=Blocker, status_code=status.HTTP_201_CREATED)
async def create_task_blocker(
    task_id: UUID,
    blocker: BlockerCreate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    blocker_repo: BlockerRepo,
):
    """Create a blocker for a task."""
    _, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    return await blocker_repo.create(owner_user_id, task_id, blocker)


@router.patch("/blockers/{blocker_id}", response_model=Blocker)
async def update_task_blocker(
    blocker_id: UUID,
    update: BlockerUpdate,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    blocker_repo: BlockerRepo,
):
    """Update a blocker."""
    # First get the blocker to find the task_id
    blocker = await blocker_repo.get_by_id(blocker_id)
    if not blocker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blocker {blocker_id} not found",
        )

    # Verify project access and get owner_user_id
    _, owner_user_id = await _get_task_or_404(user, repo, blocker.task_id, project_repo)

    try:
        return await blocker_repo.update(owner_user_id, blocker_id, update)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


# ===========================================
# Postpone / Do-Today Endpoints
# ===========================================


@router.post("/{task_id}/postpone", response_model=Task)
async def postpone_task(
    task_id: UUID,
    request: PostponeRequest,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    postpone_repo: PostponeRepo,
    user_repo: UserRepo,
):
    """Postpone a task to a later date."""
    service = _get_task_application_service(
        repo,
        project_repo,
        postpone_repo=postpone_repo,
        user_repo=user_repo,
    )
    try:
        return await service.postpone_task(user.id, task_id, request)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc


@router.post("/{task_id}/do-today", response_model=Task)
async def do_today(
    task_id: UUID,
    request: DoTodayRequest,
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    user_repo: UserRepo,
):
    """Pull a task into today's schedule."""
    service = _get_task_application_service(repo, project_repo, user_repo=user_repo)
    try:
        return await service.do_today(user.id, task_id, request)
    except (BusinessLogicError, NotFoundError) as exc:
        raise _to_task_http_exception(exc) from exc


@router.get("/{task_id}/postpone-history", response_model=list[PostponeEvent])
async def get_postpone_history(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    postpone_repo: PostponeRepo,
    project_repo: ProjectRepo,
):
    """Get postponement history for a specific task."""
    _, owner_user_id = await _get_task_or_404(user, repo, task_id, project_repo)
    return await postpone_repo.list_by_task(owner_user_id, task_id)
