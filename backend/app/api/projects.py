"""
Projects API endpoints.

CRUD operations for projects.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    BlockerRepo,
    CheckinRepo,
    CurrentUser,
    EmailProvider,
    LLMProvider,
    MemoryRepo,
    NotificationRepo,
    ProjectInvitationRepo,
    ProjectLinkRequestRepo,
    ProjectMemberRepo,
    ProjectRepo,
    TaskAssignmentRepo,
    TaskRepo,
    UserRepo,
)
from app.api.permissions import require_project_action, require_project_member
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.child_project_views import (
    ChildProjectTaskSummary,
    MemberChildTasksSummary,
    MemberProjectTask,
)
from app.models.collaboration import (
    Blocker,
    Checkin,
    CheckinAgendaItems,
    CheckinCreate,
    CheckinCreateV2,
    CheckinSummary,
    CheckinSummaryRequest,
    CheckinSummarySave,
    CheckinUpdateV2,
    CheckinV2,
    ProjectInvitation,
    ProjectInvitationCreate,
    ProjectInvitationUpdate,
    ProjectMember,
    ProjectMemberCreate,
    ProjectMemberUpdate,
    TaskAssignment,
)
from app.models.enums import (
    CheckinType,
    InvitationStatus,
    MemoryScope,
    MemoryType,
    ProjectRole,
    ProjectVisibility,
)
from app.models.lightning_line import LightningLineResponse
from app.models.memory import Memory, MemoryCreate
from app.models.project import Project, ProjectCreate, ProjectUpdate, ProjectWithTaskCount
from app.models.project_kpi import ProjectKpiTemplate
from app.models.project_link import (
    InviteParentMemberRequest,
    ProjectLinkRequest,
    ProjectLinkRequestCreate,
)
from app.models.task import Task, TaskUpdate
from app.services import notification_service as notify
from app.services.kpi_calculator import apply_project_kpis
from app.services.kpi_templates import get_kpi_templates
from app.services.lightning_line_service import LightningLineService
from app.services.llm_utils import generate_text, generate_text_with_status
from app.services.project_permissions import ProjectAction
from app.utils.datetime_utils import ensure_utc, now_utc

router = APIRouter()


def _compact_text(value: str) -> str:
    return " ".join(value.strip().split())


def _truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _summarize_checkin(llm_provider: LLMProvider, raw_text: str) -> str | None:
    compacted = _compact_text(raw_text)
    if not compacted:
        return None

    prompt = (
        "Summarize this check-in in 2-3 short sentences. "
        "Keep it concise and action-focused.\n\n"
        f"{compacted}"
    )
    summary_text = generate_text(
        llm_provider,
        prompt,
        temperature=0.2,
        max_output_tokens=200,
    )
    summary = _compact_text(summary_text or "")
    if summary:
        return _truncate_text(summary, 2000)
    return _truncate_text(compacted, 280)


def _format_checkin_for_summary(checkin: Checkin, max_length: int = 500) -> str:
    text = _compact_text(checkin.raw_text)
    if not text:
        text = "(empty)"
    text = _truncate_text(text, max_length)
    checkin_type = getattr(checkin.checkin_type, "value", checkin.checkin_type)
    return f"- {checkin.checkin_date.isoformat()} {checkin.member_user_id} ({checkin_type}): {text}"


def _format_checkin_fallback(checkin: Checkin, max_length: int = 200) -> str:
    text = _truncate_text(_compact_text(checkin.raw_text), max_length)
    return f"- {checkin.checkin_date.isoformat()} {checkin.member_user_id}: {text}"


def _fallback_checkin_summary(
    checkins: list[Checkin],
    start_date: Optional[date],
    end_date: Optional[date],
) -> str:
    period_label = f"{start_date or '...'} to {end_date or '...'}"
    lines = [f"Check-ins ({period_label})", ""]
    for checkin in checkins[:20]:
        text = _truncate_text(_compact_text(checkin.raw_text), 200)
        lines.append(f"- {checkin.checkin_date.isoformat()} {checkin.member_user_id}: {text}")
    remaining = len(checkins) - min(len(checkins), 20)
    if remaining > 0:
        lines.append(f"- ...and {remaining} more")
    return "\n".join(lines).strip()


def _looks_like_summary(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if any(marker in cleaned for marker in ("- ", "•", "・", "* ")):
        return True
    if "\n" in cleaned:
        return True
    return len(cleaned) >= 80


def _summarize_checkins(
    llm_provider: LLMProvider,
    checkins: list[Checkin],
    start_date: Optional[date],
    end_date: Optional[date],
    weekly_context: Optional[str] = None,
) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    if not checkins:
        return "", None, None, None, None

    period_label = f"{start_date or '...'} to {end_date or '...'}"
    prompt_lines = [
        "You are summarizing project check-ins for a recurring meeting.",
        "Summarize in 5-10 bullet points with clear, actionable phrasing.",
        "Focus on progress, blockers, decisions, risks, and next actions.",
        "Write in the same language as the check-ins.",
        "If you cannot summarize, list the check-ins as bullet points.",
        f"Period: {period_label}",
        f"Total check-ins: {len(checkins)}",
        "",
        "Check-ins:",
    ]
    checkin_lines = [_format_checkin_for_summary(checkin) for checkin in checkins]
    prompt_lines.extend(checkin_lines)
    if weekly_context:
        prompt_lines.extend(["", "Weekly snapshot:", _truncate_text(weekly_context, 1500)])
    prompt = "\n".join(prompt_lines)
    summary, error_code, error_detail = generate_text_with_status(
        llm_provider,
        prompt,
        temperature=0.2,
        max_output_tokens=6000,
    )
    debug_prompt = _truncate_text(prompt, 800)
    debug_output = _truncate_text(summary, 800) if summary else None
    if summary and _looks_like_summary(summary):
        return _truncate_text(summary, 5000), None, None, debug_prompt, debug_output

    retriable_errors = {"genai_empty_response", "litellm_empty_response"}
    if not error_code or error_code in retriable_errors:
        fallback_lines = [_format_checkin_fallback(checkin) for checkin in checkins]
        strict_prompt_lines = [
            "Task: Summarize the check-ins below.",
            "Output rules:",
            "- Output ONLY bullet points (5-10 lines).",
            "- Each line must start with '- ' and be at least 12 characters.",
            "- Mention concrete content from the check-ins.",
            "- Do not include introductions or the period line.",
            "- Use the same language as the check-ins.",
            "",
            "If you cannot follow the rules, output the Fallback list exactly as provided.",
            "",
            "Check-ins:",
            *checkin_lines,
            "",
            "Weekly snapshot:",
            _truncate_text(weekly_context or "", 1500) or "(none)",
            "",
            "Fallback list:",
            *fallback_lines,
        ]
        strict_prompt = "\n".join(strict_prompt_lines)
        summary, error_code, error_detail = generate_text_with_status(
            llm_provider,
            strict_prompt,
            temperature=0.2,
            max_output_tokens=6000,
        )
        debug_prompt = _truncate_text(strict_prompt, 800)
        debug_output = _truncate_text(summary, 800) if summary else None
        if summary and _looks_like_summary(summary):
            return _truncate_text(summary, 5000), None, None, debug_prompt, debug_output

    if not error_code:
        error_code = "llm_response_unusable"
    return _fallback_checkin_summary(checkins, start_date, end_date), error_code, error_detail, debug_prompt, debug_output


def _build_checkin_summary_response(
    project_id: UUID,
    checkins: list[Checkin],
    start_date: Optional[date],
    end_date: Optional[date],
    weekly_context: Optional[str],
    llm_provider: LLMProvider,
) -> CheckinSummary:
    if not checkins:
        return CheckinSummary(
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
            checkin_count=0,
            summary_text=None,
            summary_error=None,
            summary_error_detail=None,
            summary_debug_prompt=None,
            summary_debug_output=None,
        )

    summary_text, summary_error, summary_error_detail, debug_prompt, debug_output = _summarize_checkins(
        llm_provider,
        checkins[:50],
        start_date,
        end_date,
        weekly_context=weekly_context,
    )
    summary_text = summary_text.strip() or None
    settings = get_settings()
    return CheckinSummary(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        checkin_count=len(checkins),
        summary_text=summary_text,
        summary_error=summary_error,
        summary_error_detail=summary_error_detail,
        summary_debug_prompt=debug_prompt if settings.DEBUG else None,
        summary_debug_output=debug_output if settings.DEBUG else None,
    )


async def _validate_parent_project(
    repo: ProjectRepo,
    user_id: str,
    project_id: Optional[UUID],
    parent_project_id: UUID,
):
    """Validate parent project assignment.

    Checks: self-reference, existence, circular reference.
    """
    if project_id and parent_project_id == project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="自分自身を親プロジェクトに設定できません",
        )

    parent = await repo.get_by_id(parent_project_id)
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"親プロジェクト {parent_project_id} が見つかりません",
        )

    # Circular reference check: walk up ancestors of parent
    if project_id:
        current_id = parent.parent_project_id
        visited: set[UUID] = set()
        while current_id:
            if current_id == project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="循環参照が検出されました。この紐付けはできません",
                )
            if current_id in visited:
                break
            visited.add(current_id)
            ancestor = await repo.get_by_id(current_id)
            if not ancestor:
                break
            current_id = ancestor.parent_project_id

    return parent


async def _enrich_owner_names(
    projects: list[ProjectWithTaskCount],
    user_repo: UserRepo,
) -> None:
    """Populate owner_display_name on project list."""
    owner_names: dict[str, Optional[str]] = {}
    for proj in projects:
        uid = proj.user_id
        if uid not in owner_names:
            u = await user_repo.get(UUID(uid))
            owner_names[uid] = (u.display_name or u.username or u.email) if u else None
        proj.owner_display_name = owner_names.get(uid)


async def _enrich_link_requests(
    requests: list[ProjectLinkRequest],
    repo: ProjectRepo,
) -> list[ProjectLinkRequest]:
    """Populate child/parent project names on link requests."""
    project_names: dict[str, str] = {}
    for req in requests:
        for pid in (str(req.child_project_id), str(req.parent_project_id)):
            if pid not in project_names:
                proj = await repo.get_by_id(UUID(pid))
                project_names[pid] = proj.name if proj else None
        req.child_project_name = project_names.get(str(req.child_project_id))
        req.parent_project_name = project_names.get(str(req.parent_project_id))
    return requests


@router.get("/kpi-templates", response_model=list[ProjectKpiTemplate])
async def list_kpi_templates(user: CurrentUser):
    """List KPI templates."""
    return get_kpi_templates()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Create a new project."""
    if project.parent_project_id:
        await _validate_parent_project(repo, user.id, None, project.parent_project_id)

    created_project = await repo.create(user.id, project)

    # Add creator as OWNER member
    await member_repo.create(
        user.id,
        created_project.id,
        ProjectMemberCreate(member_user_id=user.id, role=ProjectRole.OWNER),
    )

    return created_project


@router.get("/{project_id}", response_model=ProjectWithTaskCount)
async def get_project(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
):
    """Get a project by ID with task counts and descendant aggregation."""
    access = await require_project_member(user, project_id, repo, member_repo)

    project = await repo.get_with_task_count(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Compute aggregated stats from descendants
    try:
        descendants = await repo.list_descendants_with_task_count(
            access.owner_id, project_id,
        )
        project.child_project_count = sum(
            1 for d in descendants if d.parent_project_id == project_id
        )
        project.aggregated_total_tasks = project.total_tasks + sum(
            d.total_tasks for d in descendants
        )
        project.aggregated_completed_tasks = project.completed_tasks + sum(
            d.completed_tasks for d in descendants
        )
        project.aggregated_in_progress_tasks = project.in_progress_tasks + sum(
            d.in_progress_tasks for d in descendants
        )
        project.aggregated_unassigned_tasks = project.unassigned_tasks + sum(
            d.unassigned_tasks for d in descendants
        )
    except Exception:
        pass  # If descendants fail, return project without aggregation

    return await apply_project_kpis(access.owner_id, project, task_repo)


@router.get("", response_model=list[ProjectWithTaskCount])
async def list_projects(
    user: CurrentUser,
    repo: ProjectRepo,
    task_repo: TaskRepo,
    status: Optional[str] = Query(None, description="Filter by status"),
    top_level_only: bool = Query(False, description="トップレベルプロジェクトのみ取得"),
):
    """List projects with task counts."""
    projects = await repo.list_with_task_count(
        user.id, status=status, top_level_only=top_level_only,
    )
    return [await apply_project_kpis(user.id, project, task_repo) for project in projects]


@router.get("/{project_id}/lightning-line", response_model=LightningLineResponse)
async def get_project_lightning_line(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
    reference_date: Optional[date] = Query(None, description="Reference date (YYYY-MM-DD)"),
):
    """Get lightning line points for project tasks."""
    access = await require_project_member(user, project_id, repo, member_repo)
    service = LightningLineService(task_repo)
    return await service.calculate(
        user_id=access.owner_id,
        project_id=project_id,
        reference_date=reference_date,
    )


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: UUID,
    update: ProjectUpdate,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Update a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.PROJECT_UPDATE,
    )
    owner_id = access.owner_id

    # Validate parent_project_id if being set
    update_fields = update.model_dump(exclude_unset=True)
    if "parent_project_id" in update_fields and update.parent_project_id is not None:
        parent = await _validate_parent_project(
            repo, user.id, project_id, update.parent_project_id,
        )
        # Only parent project owner can directly set parent_project_id
        parent_members = await member_repo.list_by_project(parent.id)
        is_parent_owner = parent.user_id == user.id or any(
            m.member_user_id == user.id and m.role == ProjectRole.OWNER
            for m in parent_members
        )
        if not is_parent_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="親プロジェクトのオーナーのみが直接紐付けできます。紐付けリクエストを送信してください。",
            )

    try:
        result = await repo.update(owner_id, project_id, update)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # TEAM → PRIVATE: remove non-owner members
    if update.visibility == ProjectVisibility.PRIVATE and access.project.visibility != ProjectVisibility.PRIVATE:
        await member_repo.delete_non_owner_members(project_id, owner_id)

    return result


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Delete a project. Only OWNER or ADMIN can delete.

    Child projects are automatically detached (parent_project_id set to null).
    """
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.PROJECT_DELETE,
    )
    owner_id = access.owner_id

    # Detach direct children before deleting
    children = await repo.list_children_with_task_count(owner_id, project_id)
    for child in children:
        try:
            await repo.update(
                child.user_id, child.id,
                ProjectUpdate(parent_project_id=None),
            )
        except Exception:
            pass  # Best-effort detach

    deleted = await repo.delete(owner_id, project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )


@router.get("/{project_id}/members", response_model=list[ProjectMember])
async def list_project_members(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
):
    """List members for a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.MEMBER_READ,
    )
    owner_id = access.owner_id

    members = await member_repo.list(owner_id, project_id)
    if owner_id == user.id and not any(m.member_user_id == user.id for m in members):
        await member_repo.create(
            owner_id,
            project_id,
            ProjectMemberCreate(member_user_id=user.id, role=ProjectRole.OWNER),
        )
        members = await member_repo.list(owner_id, project_id)
    for member in members:
        user_account = None
        try:
            member_uuid = UUID(member.member_user_id)
            user_account = await user_repo.get(member_uuid)
        except Exception:
            if "@" in member.member_user_id:
                user_account = await user_repo.get_by_email(member.member_user_id)
            if not user_account:
                user_account = await user_repo.get_by_username(member.member_user_id)

        # 表示名の優先順: display_name(姓名から構築) → username
        # email は使わない（プライバシー配慮）、フロントエンドで member_user_id がフォールバック
        display_name = None
        if user_account:
            display_name = user_account.display_name or user_account.username
            if user_account.first_name:
                member.member_first_name = user_account.first_name
            if user_account.last_name:
                member.member_last_name = user_account.last_name
        if not display_name and member.member_user_id == user.id:
            display_name = user.display_name
        if display_name:
            member.member_display_name = display_name
    return members


@router.post("/{project_id}/members", response_model=ProjectMember, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: UUID,
    member: ProjectMemberCreate,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
):
    """Add a member to a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.MEMBER_MANAGE,
    )
    owner_id = access.owner_id

    if access.project.visibility == ProjectVisibility.PRIVATE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="個人プロジェクトにはメンバーを追加できません。チームプロジェクトに変更してください。",
        )

    # Validate that the member user exists
    try:
        member_uuid = UUID(member.member_user_id)
        existing_user = await user_repo.get(member_uuid)
    except ValueError:
        existing_user = None

    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {member.member_user_id} not found",
        )

    return await member_repo.create(owner_id, project_id, member)


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMember)
async def update_project_member(
    project_id: UUID,
    member_id: UUID,
    update: ProjectMemberUpdate,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Update a project member.

    Any member can update their own capacity_hours.
    Role changes and other updates require MEMBER_MANAGE (ADMIN/OWNER).
    """
    access = await require_project_member(
        user,
        project_id,
        repo,
        member_repo,
    )
    owner_id = access.owner_id
    existing = await member_repo.get(owner_id, member_id)
    if not existing or existing.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project member {member_id} not found",
        )

    update_fields = update.model_dump(exclude_unset=True)
    is_self = existing.member_user_id == user.id
    is_capacity_only = set(update_fields.keys()) <= {"capacity_hours"}

    if not (is_self and is_capacity_only):
        from app.services.project_permissions import ensure_project_action
        try:
            ensure_project_action(access, ProjectAction.MEMBER_MANAGE)
        except ForbiddenError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc

    return await member_repo.update(owner_id, member_id, update)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_member(
    project_id: UUID,
    member_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Remove a member from a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.MEMBER_MANAGE,
    )
    owner_id = access.owner_id
    existing = await member_repo.get(owner_id, member_id)
    if not existing or existing.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project member {member_id} not found",
        )
    deleted = await member_repo.delete(owner_id, member_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project member {member_id} not found",
        )


@router.get("/{project_id}/invitations", response_model=list[ProjectInvitation])
async def list_project_invitations(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    invitation_repo: ProjectInvitationRepo,
    member_repo: ProjectMemberRepo,
):
    """List invitations for a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.INVITATION_READ,
    )
    owner_id = access.owner_id
    return await invitation_repo.list_by_project(owner_id, project_id)


@router.post("/{project_id}/invitations", response_model=ProjectInvitation, status_code=status.HTTP_201_CREATED)
async def create_project_invitation(
    project_id: UUID,
    invitation: ProjectInvitationCreate,
    user: CurrentUser,
    repo: ProjectRepo,
    invitation_repo: ProjectInvitationRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
):
    """Create a project invitation (or add member if user exists)."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.INVITATION_MANAGE,
    )
    project = access.project

    if project.visibility == ProjectVisibility.PRIVATE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="個人プロジェクトにはメンバーを招待できません。チームプロジェクトに変更してください。",
        )

    normalized_email = _normalize_email(invitation.email)
    existing_invitation = await invitation_repo.get_by_email(project_id, normalized_email)

    existing_user = await user_repo.get_by_email(normalized_email)
    member_user_id = str(existing_user.id) if existing_user else None

    # Handle existing invitation based on status
    if existing_invitation:
        if existing_invitation.status == InvitationStatus.ACCEPTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An invitation for {normalized_email} has already been accepted",
            )
        elif existing_invitation.status == InvitationStatus.PENDING:
            # If user exists, auto-accept the pending invitation
            if member_user_id:
                members = await member_repo.list(project.user_id, project_id)
                if not any(m.member_user_id == member_user_id for m in members):
                    await member_repo.create(
                        project.user_id,
                        project_id,
                        ProjectMemberCreate(member_user_id=member_user_id, role=invitation.role),
                    )
                return await invitation_repo.mark_accepted(existing_invitation.id, member_user_id)
            return existing_invitation
        else:
            # EXPIRED or REVOKED: reinvite
            reinvited = await invitation_repo.reinvite(existing_invitation.id, user.id)
            if member_user_id:
                members = await member_repo.list(project.user_id, project_id)
                if not any(m.member_user_id == member_user_id for m in members):
                    await member_repo.create(
                        project.user_id,
                        project_id,
                        ProjectMemberCreate(member_user_id=member_user_id, role=invitation.role),
                    )
                return await invitation_repo.mark_accepted(reinvited.id, member_user_id)
            return reinvited

    # No existing invitation: create new one
    created = await invitation_repo.create(
        project.user_id,
        project_id,
        invited_by=user.id,
        data=ProjectInvitationCreate(email=normalized_email, role=invitation.role),
    )

    if member_user_id:
        members = await member_repo.list(project.user_id, project_id)
        if not any(m.member_user_id == member_user_id for m in members):
            await member_repo.create(
                project.user_id,
                project_id,
                ProjectMemberCreate(member_user_id=member_user_id, role=invitation.role),
            )
        return await invitation_repo.mark_accepted(created.id, member_user_id)

    return created


@router.patch("/{project_id}/invitations/{invitation_id}", response_model=ProjectInvitation)
async def update_project_invitation(
    project_id: UUID,
    invitation_id: UUID,
    update: ProjectInvitationUpdate,
    user: CurrentUser,
    repo: ProjectRepo,
    invitation_repo: ProjectInvitationRepo,
    member_repo: ProjectMemberRepo,
):
    """Update invitation status."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.INVITATION_MANAGE,
    )
    owner_id = access.owner_id
    if update.status not in {InvitationStatus.REVOKED, InvitationStatus.EXPIRED}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only REVOKED or EXPIRED status updates are allowed",
        )
    return await invitation_repo.update(owner_id, invitation_id, update)


@router.post("/invitations/{token}/accept", response_model=ProjectInvitation)
async def accept_project_invitation(
    token: str,
    user: CurrentUser,
    invitation_repo: ProjectInvitationRepo,
    member_repo: ProjectMemberRepo,
    assignment_repo: TaskAssignmentRepo,
):
    """Accept an invitation using a token."""
    invitation = await invitation_repo.get_by_token(token)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is not pending",
        )
    expires_at = ensure_utc(invitation.expires_at)
    if expires_at and expires_at < now_utc():
        await invitation_repo.update(
            invitation.user_id,
            invitation.id,
            ProjectInvitationUpdate(status=InvitationStatus.EXPIRED),
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invitation expired",
        )
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required to accept invitation",
        )
    if _normalize_email(user.email) != _normalize_email(invitation.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email does not match invitation",
        )

    members = await member_repo.list(invitation.user_id, invitation.project_id)
    if not any(m.member_user_id == user.id for m in members):
        await member_repo.create(
            invitation.user_id,
            invitation.project_id,
            ProjectMemberCreate(member_user_id=user.id, role=invitation.role),
        )

    # Convert any tasks assigned to this invitation to the new user
    from app.services.assignee_utils import make_invitation_assignee_id

    invitation_assignee_id = make_invitation_assignee_id(str(invitation.id))
    await assignment_repo.convert_invitation_to_user(
        invitation.user_id,
        invitation_assignee_id,
        user.id,
    )

    return await invitation_repo.mark_accepted(invitation.id, user.id)


@router.get("/{project_id}/assignments", response_model=list[TaskAssignment])
async def list_project_assignments(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    member_repo: ProjectMemberRepo,
):
    """List task assignments for a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.ASSIGNMENT_READ,
    )
    owner_id = access.owner_id
    return await assignment_repo.list_by_project(owner_id, project_id)


@router.get("/{project_id}/blockers", response_model=list[Blocker])
async def list_project_blockers(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    blocker_repo: BlockerRepo,
    member_repo: ProjectMemberRepo,
):
    """List blockers for a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.BLOCKER_READ,
    )
    owner_id = access.owner_id
    return await blocker_repo.list_by_project(owner_id, project_id)


@router.get("/{project_id}/checkins", response_model=list[Checkin])
async def list_project_checkins(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
    member_user_id: Optional[str] = Query(None, description="Filter by member user ID"),
    start_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive)"),
):
    """List check-ins for a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_READ,
    )
    owner_id = access.owner_id
    return await checkin_repo.list(
        owner_id,
        project_id,
        member_user_id=member_user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{project_id}/checkins/summary", response_model=CheckinSummary)
async def summarize_project_checkins(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    llm_provider: LLMProvider,
    member_repo: ProjectMemberRepo,
    member_user_id: Optional[str] = Query(None, description="Filter by member user ID"),
    start_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive)"),
    checkin_type: Optional[CheckinType] = Query(None, description="Filter by check-in type"),
):
    """Summarize check-ins for a project within a date range."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_READ,
    )
    owner_id = access.owner_id
    checkins = await checkin_repo.list(
        owner_id,
        project_id,
        member_user_id=member_user_id,
        start_date=start_date,
        end_date=end_date,
    )
    if checkin_type is not None:
        checkins = [checkin for checkin in checkins if checkin.checkin_type == checkin_type]
    return _build_checkin_summary_response(
        project_id=project_id,
        checkins=checkins,
        start_date=start_date,
        end_date=end_date,
        weekly_context=None,
        llm_provider=llm_provider,
    )


@router.post("/{project_id}/checkins/summary", response_model=CheckinSummary)
async def summarize_project_checkins_post(
    project_id: UUID,
    payload: CheckinSummaryRequest,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    llm_provider: LLMProvider,
    member_repo: ProjectMemberRepo,
):
    """Summarize check-ins with optional weekly context."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_READ,
    )
    owner_id = access.owner_id
    checkins = await checkin_repo.list(
        owner_id,
        project_id,
        member_user_id=payload.member_user_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    if payload.checkin_type is not None:
        checkins = [checkin for checkin in checkins if checkin.checkin_type == payload.checkin_type]
    return _build_checkin_summary_response(
        project_id=project_id,
        checkins=checkins,
        start_date=payload.start_date,
        end_date=payload.end_date,
        weekly_context=payload.weekly_context,
        llm_provider=llm_provider,
    )


@router.post("/{project_id}/checkins/summary/save", response_model=Memory)
async def save_project_checkin_summary(
    project_id: UUID,
    payload: CheckinSummarySave,
    user: CurrentUser,
    repo: ProjectRepo,
    memory_repo: MemoryRepo,
    member_repo: ProjectMemberRepo,
):
    """Save a check-in summary as project memory."""
    await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_WRITE,
    )
    tags = [
        "checkin_summary",
        f"count:{payload.checkin_count}",
    ]
    if payload.start_date or payload.end_date:
        tags.append(f"range:{payload.start_date or '...'}..{payload.end_date or '...'}")
    memory = await memory_repo.create(
        user.id,
        MemoryCreate(
            content=payload.summary_text,
            scope=MemoryScope.PROJECT,
            memory_type=MemoryType.FACT,
            project_id=project_id,
            tags=tags,
            source="agent",
        ),
    )
    return memory


@router.post("/{project_id}/checkins", response_model=Checkin, status_code=status.HTTP_201_CREATED)
async def create_project_checkin(
    project_id: UUID,
    checkin: CheckinCreate,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
):
    """Create a new check-in for a project."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_WRITE,
    )
    if access.role == ProjectRole.MEMBER and checkin.member_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Members can only create check-ins for themselves",
        )
    owner_id = access.owner_id
    return await checkin_repo.create(owner_id, project_id, checkin)


# =============================================================================
# V2 Check-in Endpoints (Structured)
# =============================================================================


@router.post(
    "/{project_id}/checkins/v2",
    response_model=CheckinV2,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_checkin_v2(
    project_id: UUID,
    checkin: CheckinCreateV2,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
    notification_repo: NotificationRepo,
    email_provider: EmailProvider,
    user_repo: UserRepo,
):
    """Create a structured check-in (V2)."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_WRITE,
    )
    if access.role == ProjectRole.MEMBER and checkin.member_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Members can only create check-ins for themselves",
        )
    owner_id = access.owner_id
    result = await checkin_repo.create_v2(owner_id, project_id, checkin)

    # Notify project members (in-app + email)
    members = await member_repo.list_by_project(project_id)
    member_ids = {m.member_user_id for m in members}
    member_ids.add(access.owner_id)
    await notify.notify_checkin_change(
        notification_repo, project_id, access.project.name,
        user.id, user.display_name or "", member_ids, is_update=False,
        email_provider=email_provider,
        user_repo=user_repo,
        members=members,
        checkin=checkin,
    )
    return result


@router.get("/{project_id}/checkins/v2", response_model=list[CheckinV2])
async def list_project_checkins_v2(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
    member_user_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """List structured check-ins (V2)."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_READ,
    )
    owner_id = access.owner_id
    return await checkin_repo.list_v2(
        owner_id,
        project_id,
        member_user_id=member_user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.patch("/{project_id}/checkins/v2/{checkin_id}", response_model=CheckinV2)
async def update_project_checkin_v2(
    project_id: UUID,
    checkin_id: UUID,
    checkin_update: CheckinUpdateV2,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
    notification_repo: NotificationRepo,
    email_provider: EmailProvider,
    user_repo: UserRepo,
):
    """Update a structured check-in (V2). Only the creator can update."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_WRITE,
    )

    # Get existing checkin to verify ownership
    existing = await checkin_repo.get_v2(checkin_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found",
        )
    if existing.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found in project {project_id}",
        )
    if access.role == ProjectRole.MEMBER and existing.member_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Members can only update their own check-ins",
        )

    result = await checkin_repo.update_v2(checkin_id, checkin_update)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found",
        )

    # Notify project members (in-app + email)
    members = await member_repo.list_by_project(project_id)
    member_ids = {m.member_user_id for m in members}
    member_ids.add(access.owner_id)
    await notify.notify_checkin_change(
        notification_repo, project_id, access.project.name,
        user.id, user.display_name or "", member_ids, is_update=True,
        email_provider=email_provider,
        user_repo=user_repo,
        members=members,
        checkin=result,
    )
    return result


@router.delete("/{project_id}/checkins/v2/{checkin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_checkin_v2(
    project_id: UUID,
    checkin_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
):
    """Delete a structured check-in (V2). Only the creator can delete."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_WRITE,
    )

    # Get existing checkin to verify ownership
    existing = await checkin_repo.get_v2(checkin_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found",
        )
    if existing.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found in project {project_id}",
        )
    if access.role == ProjectRole.MEMBER and existing.member_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Members can only delete their own check-ins",
        )

    deleted = await checkin_repo.delete_v2(checkin_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found",
        )


@router.get("/{project_id}/checkins/agenda-items", response_model=CheckinAgendaItems)
async def get_project_checkin_agenda_items(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    checkin_repo: CheckinRepo,
    member_repo: ProjectMemberRepo,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """Get check-in items grouped by category for meeting agenda generation."""
    access = await require_project_action(
        user,
        project_id,
        repo,
        member_repo,
        ProjectAction.CHECKIN_READ,
    )
    owner_id = access.owner_id
    return await checkin_repo.get_agenda_items(
        owner_id,
        project_id,
        start_date=start_date,
        end_date=end_date,
    )


# =============================================================================
# Child / Descendant Project Endpoints
# =============================================================================


@router.get("/{project_id}/children", response_model=list[ProjectWithTaskCount])
async def list_child_projects(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
):
    """List direct child projects with task counts and owner names."""
    await require_project_member(user, project_id, repo, member_repo)
    children = await repo.list_children_with_task_count(user.id, project_id)
    await _enrich_owner_names(children, user_repo)
    return children


@router.get("/{project_id}/descendants", response_model=list[ProjectWithTaskCount])
async def list_descendant_projects(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """List all descendant projects (recursive) with task counts."""
    await require_project_member(user, project_id, repo, member_repo)
    return await repo.list_descendants_with_task_count(user.id, project_id)


@router.get(
    "/{project_id}/children/{child_project_id}/tasks",
    response_model=list[ChildProjectTaskSummary],
)
async def list_child_project_tasks(
    project_id: UUID,
    child_project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
    assignment_repo: TaskAssignmentRepo,
    user_repo: UserRepo,
):
    """List task summaries for a child project (read-only for parent members)."""
    await require_project_member(user, project_id, repo, member_repo)

    child = await repo.get_by_id(child_project_id)
    if not child or str(child.parent_project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="子プロジェクトが見つかりません",
        )

    tasks = await task_repo.list(
        child.user_id, project_id=child_project_id, include_done=True,
    )
    assignments = await assignment_repo.list_by_project(child.user_id, child_project_id)
    assignment_map: dict[str, list[str]] = {}
    user_names: dict[str, str] = {}
    for a in assignments:
        tid = str(a.task_id)
        aid = a.assignee_id
        if aid not in user_names:
            u = await user_repo.get(UUID(aid)) if not aid.startswith("inv:") else None
            user_names[aid] = (u.display_name or u.username or aid) if u else aid
        assignment_map.setdefault(tid, []).append(user_names[aid])

    return [
        ChildProjectTaskSummary(
            id=t.id,
            title=t.title,
            status=t.status,
            assignee_names=assignment_map.get(str(t.id), []),
            due_date=t.due_date,
            parent_id=t.parent_id,
        )
        for t in tasks
    ]


@router.get(
    "/{project_id}/member-child-tasks",
    response_model=list[MemberChildTasksSummary],
)
async def list_member_tasks_across_children(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
    assignment_repo: TaskAssignmentRepo,
    user_repo: UserRepo,
):
    """Get tasks grouped by member across all child projects."""
    await require_project_member(user, project_id, repo, member_repo)
    children = await repo.list_children_with_task_count(user.id, project_id)

    member_map: dict[str, MemberChildTasksSummary] = {}
    user_names: dict[str, str] = {}

    for child in children:
        tasks = await task_repo.list(
            child.user_id, project_id=child.id, include_done=True,
        )
        assignments = await assignment_repo.list_by_project(child.user_id, child.id)
        task_assignments: dict[str, list[str]] = {}
        for a in assignments:
            task_assignments.setdefault(str(a.task_id), []).append(a.assignee_id)

        for task in tasks:
            assignee_ids = task_assignments.get(str(task.id), [])
            if not assignee_ids:
                continue
            for aid in assignee_ids:
                if aid not in user_names:
                    u = await user_repo.get(UUID(aid)) if not aid.startswith("inv:") else None
                    user_names[aid] = (u.display_name or u.username or aid) if u else aid
                if aid not in member_map:
                    member_map[aid] = MemberChildTasksSummary(
                        member_user_id=aid,
                        member_display_name=user_names[aid],
                        tasks_by_project=[],
                    )
                member_map[aid].tasks_by_project.append(
                    MemberProjectTask(
                        child_project_id=child.id,
                        child_project_name=child.name,
                        task_id=task.id,
                        task_title=task.title,
                        task_status=task.status,
                        due_date=task.due_date,
                        parent_id=task.parent_id,
                        completed_at=task.completed_at,
                    )
                )

    return list(member_map.values())


@router.patch(
    "/{project_id}/member-child-tasks/{task_id}",
    response_model=Task,
)
async def update_member_child_task(
    project_id: UUID,
    task_id: UUID,
    update: TaskUpdate,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
):
    await require_project_member(user, project_id, repo, member_repo)
    children = await repo.list_children_with_task_count(user.id, project_id)

    for child in children:
        task = await task_repo.get(child.user_id, task_id, project_id=child.id)
        if not task:
            continue
        return await task_repo.update(
            child.user_id,
            task_id,
            update,
            project_id=child.id,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Task {task_id} not found in child projects of project {project_id}",
    )


# =============================================================================
# Project Link Request Endpoints
# =============================================================================


@router.post(
    "/{project_id}/link-requests",
    response_model=ProjectLinkRequest,
    status_code=status.HTTP_201_CREATED,
)
async def create_link_request(
    project_id: UUID,
    data: ProjectLinkRequestCreate,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    link_request_repo: ProjectLinkRequestRepo,
    notification_repo: NotificationRepo,
):
    """Create a link request to attach a child project to this parent project.

    Both parent and child project owners must approve.
    If the requester is an owner of one or both sides, that side is auto-approved.
    """
    if data.parent_project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="parent_project_id must match the URL project ID",
        )

    # Validate parent project
    parent = await _validate_parent_project(
        repo, user.id, data.child_project_id, data.parent_project_id,
    )

    # Check that child project exists and user has access
    child = await repo.get(user.id, data.child_project_id)
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"子プロジェクト {data.child_project_id} が見つかりません",
        )

    # Determine if requester is parent/child owner
    parent_members = await member_repo.list_by_project(project_id)
    is_parent_owner = parent.user_id == user.id or any(
        m.member_user_id == user.id and m.role == ProjectRole.OWNER
        for m in parent_members
    )
    child_members = await member_repo.list_by_project(data.child_project_id)
    is_child_owner = child.user_id == user.id or any(
        m.member_user_id == user.id and m.role == ProjectRole.OWNER
        for m in child_members
    )

    # Create link request
    link_request = await link_request_repo.create(data, requested_by=user.id)

    # Auto-approve requester's side(s)
    if is_parent_owner:
        link_request = await link_request_repo.approve_side(link_request.id, "parent")
    if is_child_owner:
        link_request = await link_request_repo.approve_side(link_request.id, "child")

    # If both approved, perform the actual linking
    if link_request.parent_approved and link_request.child_approved:
        await repo.update(child.user_id, child.id, ProjectUpdate(parent_project_id=project_id))
        for mid in data.member_ids_to_add:
            try:
                if not any(m.member_user_id == mid for m in parent_members):
                    await member_repo.create(
                        parent.user_id, project_id,
                        ProjectMemberCreate(member_user_id=mid, role=ProjectRole.MEMBER),
                    )
            except Exception:
                pass
    else:
        # Notify the owner(s) who still need to approve
        display_name = user.display_name or ""
        if not is_parent_owner:
            await notify.notify_project_link_request(
                notification_repo,
                parent_project_id=parent.id,
                parent_project_name=parent.name,
                child_project_name=child.name,
                requester_display_name=display_name,
                owner_user_id=parent.user_id,
            )
        if not is_child_owner:
            await notify.notify_child_project_link_request(
                notification_repo,
                child_project_id=child.id,
                child_project_name=child.name,
                parent_project_name=parent.name,
                requester_display_name=display_name,
                child_owner_user_id=child.user_id,
            )

    return link_request


@router.get("/{project_id}/link-requests", response_model=list[ProjectLinkRequest])
async def list_link_requests(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    link_request_repo: ProjectLinkRequestRepo,
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
):
    """List link requests for a parent project."""
    await require_project_member(user, project_id, repo, member_repo)
    requests = await link_request_repo.list_by_parent(project_id, status=request_status)
    return await _enrich_link_requests(requests, repo)


@router.get("/{project_id}/incoming-link-requests", response_model=list[ProjectLinkRequest])
async def list_incoming_link_requests(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    link_request_repo: ProjectLinkRequestRepo,
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
):
    """List link requests where this project is the child."""
    await require_project_member(user, project_id, repo, member_repo)
    requests = await link_request_repo.list_by_child(project_id, status=request_status)
    return await _enrich_link_requests(requests, repo)


@router.post("/{project_id}/link-requests/{request_id}/approve", response_model=ProjectLinkRequest)
async def approve_link_request(
    project_id: UUID,
    request_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    link_request_repo: ProjectLinkRequestRepo,
    notification_repo: NotificationRepo,
):
    """Approve a link request. Parent or child project OWNER can approve their side."""
    link_request = await link_request_repo.get(request_id)
    if not link_request or link_request.parent_project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="紐付けリクエストが見つかりません",
        )
    if link_request.status.value != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このリクエストは既に処理されています",
        )

    # Check which side(s) the user owns
    parent_members = await member_repo.list_by_project(project_id)
    parent_project = await repo.get_by_id(project_id)
    is_parent_owner = (parent_project and parent_project.user_id == user.id) or any(
        m.member_user_id == user.id and m.role == ProjectRole.OWNER
        for m in parent_members
    )

    child = await repo.get_by_id(link_request.child_project_id)
    child_members = await member_repo.list_by_project(link_request.child_project_id)
    is_child_owner = (child and child.user_id == user.id) or any(
        m.member_user_id == user.id and m.role == ProjectRole.OWNER
        for m in child_members
    )

    if not is_parent_owner and not is_child_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="親または子プロジェクトのオーナーのみが承認できます",
        )

    # Approve the side(s) the user owns
    if is_parent_owner and not link_request.parent_approved:
        link_request = await link_request_repo.approve_side(request_id, "parent")
    if is_child_owner and not link_request.child_approved:
        link_request = await link_request_repo.approve_side(request_id, "child")

    # If both sides are now approved, perform the actual linking
    if link_request.parent_approved and link_request.child_approved:
        if child:
            await repo.update(
                child.user_id, child.id,
                ProjectUpdate(parent_project_id=project_id),
            )
        # Add selected members to parent project
        for member_id in link_request.member_ids_to_add:
            try:
                if not any(m.member_user_id == member_id for m in parent_members):
                    await member_repo.create(
                        parent_project.user_id if parent_project else user.id,
                        project_id,
                        ProjectMemberCreate(member_user_id=member_id, role=ProjectRole.MEMBER),
                    )
            except Exception:
                pass

        # Notify requester
        if child and parent_project:
            await notify.notify_project_link_approved(
                notification_repo,
                child_project_id=child.id,
                parent_project_name=parent_project.name,
                child_project_name=child.name,
                requester_user_id=link_request.requested_by,
            )

    return link_request


@router.post("/{project_id}/link-requests/{request_id}/reject", response_model=ProjectLinkRequest)
async def reject_link_request(
    project_id: UUID,
    request_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    link_request_repo: ProjectLinkRequestRepo,
    notification_repo: NotificationRepo,
):
    """Reject a link request. Parent or child project OWNER can reject."""
    link_request = await link_request_repo.get(request_id)
    if not link_request or link_request.parent_project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="紐付けリクエストが見つかりません",
        )
    if link_request.status.value != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このリクエストは既に処理されています",
        )

    # Check that user is parent or child owner
    parent_members = await member_repo.list_by_project(project_id)
    parent_project = await repo.get_by_id(project_id)
    is_parent_owner = (parent_project and parent_project.user_id == user.id) or any(
        m.member_user_id == user.id and m.role == ProjectRole.OWNER
        for m in parent_members
    )

    child = await repo.get_by_id(link_request.child_project_id)
    child_members = await member_repo.list_by_project(link_request.child_project_id)
    is_child_owner = (child and child.user_id == user.id) or any(
        m.member_user_id == user.id and m.role == ProjectRole.OWNER
        for m in child_members
    )

    if not is_parent_owner and not is_child_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="親または子プロジェクトのオーナーのみが却下できます",
        )

    rejected = await link_request_repo.reject(request_id)

    # Notify requester
    if child and parent_project:
        await notify.notify_project_link_rejected(
            notification_repo,
            child_project_id=child.id,
            parent_project_name=parent_project.name,
            child_project_name=child.name,
            requester_user_id=link_request.requested_by,
        )

    return rejected


@router.post("/{project_id}/invite-from-parent", response_model=ProjectMember)
async def invite_from_parent(
    project_id: UUID,
    body: InviteParentMemberRequest,
    user: CurrentUser,
    repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
):
    """Invite a parent project member to this child project with a specified role."""
    # Verify the user can manage members on this child project
    access = await require_project_action(
        user, project_id, repo, member_repo, ProjectAction.MEMBER_MANAGE,
    )

    # Find parent project
    child_project = access.project
    if not child_project.parent_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このプロジェクトには親プロジェクトがありません",
        )

    # Verify target user is a member of the parent project
    parent_project = await repo.get_by_id(child_project.parent_project_id)
    if not parent_project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="親プロジェクトが見つかりません",
        )

    is_parent_member = parent_project.user_id == body.member_user_id
    if not is_parent_member:
        parent_members = await member_repo.list_by_project(child_project.parent_project_id)
        is_parent_member = any(
            m.member_user_id == body.member_user_id for m in parent_members
        )

    if not is_parent_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="対象ユーザーは親プロジェクトのメンバーではありません",
        )

    # Check if already a direct member of this child project
    existing = await member_repo.get_by_project_and_member_user_id(
        project_id, body.member_user_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このユーザーは既にメンバーです",
        )

    # Don't allow inviting the child project owner (they already have full access)
    if child_project.user_id == body.member_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このユーザーはプロジェクトオーナーです",
        )

    # VIEWER role is not valid for direct membership
    if body.role == ProjectRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VIEWERロールでの直接メンバー追加はできません",
        )

    member_create = ProjectMemberCreate(
        member_user_id=body.member_user_id,
        role=body.role,
    )
    return await member_repo.create(access.owner_id, project_id, member_create)
