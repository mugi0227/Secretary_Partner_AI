"""
Phase-related agent tools.

Tools for managing phases and milestones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.milestone_repository import IMilestoneRepository
from app.interfaces.phase_repository import IPhaseRepository
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.proposal_repository import IProposalRepository
from app.interfaces.user_repository import IUserRepository
from app.models.milestone import MilestoneCreate
from app.models.phase import PhaseCreate
from app.services.project_permissions import ProjectAction
from app.tools.approval_tools import create_tool_action_proposal
from app.tools.permissions import require_project_action, require_project_member
from app.utils.datetime_utils import normalize_timezone, parse_iso_to_utc_with_user_timezone


def _parse_optional_datetime(
    value: Optional[str],
    user_timezone: Optional[str] = None,
) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parse_iso_to_utc_with_user_timezone(value, user_timezone)
    except ValueError:
        return None


async def _resolve_user_timezone(
    user_id: str,
    user_repo: Optional[IUserRepository],
) -> str:
    if user_repo is None:
        return normalize_timezone(None)
    try:
        user = await user_repo.get(UUID(user_id))
    except (TypeError, ValueError):
        user = None
    return normalize_timezone(user.timezone if user else None)


async def apply_phase_plan(
    user_id: str,
    project_id: UUID,
    phase_repo: IPhaseRepository,
    milestone_repo: IMilestoneRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    phases: list[dict],
    create_milestones: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    created_phase_ids: list[str] = []
    created_milestone_ids: list[str] = []

    access = await require_project_action(
        user_id,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.PHASE_MANAGE,
    )
    if isinstance(access, dict):
        return access

    timezone_name = await _resolve_user_timezone(access.owner_id, user_repo)

    existing_phases = await phase_repo.list_by_project(access.owner_id, project_id)
    next_order = len(existing_phases) + 1

    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = phase.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        description = phase.get("description")
        start_date = _parse_optional_datetime(phase.get("start_date"), timezone_name)
        end_date = _parse_optional_datetime(phase.get("end_date"), timezone_name)

        phase_create = PhaseCreate(
            project_id=project_id,
            name=name.strip(),
            description=description if isinstance(description, str) else None,
            order_in_project=next_order,
            start_date=start_date,
            end_date=end_date,
        )
        created_phase = await phase_repo.create(access.owner_id, phase_create)
        created_phase_ids.append(str(created_phase.id))
        next_order += 1

        if not create_milestones:
            continue

        milestones = phase.get("milestones", [])
        if not isinstance(milestones, list):
            continue

        for index, milestone in enumerate(milestones, start=1):
            if not isinstance(milestone, dict):
                continue
            title = milestone.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            milestone_description = milestone.get("description")
            due_date = _parse_optional_datetime(milestone.get("due_date"), timezone_name)
            milestone_create = MilestoneCreate(
                project_id=project_id,
                phase_id=created_phase.id,
                title=title.strip(),
                description=(
                    milestone_description if isinstance(milestone_description, str) else None
                ),
                order_in_phase=index,
                due_date=due_date,
            )
            created_milestone = await milestone_repo.create(access.owner_id, milestone_create)
            created_milestone_ids.append(str(created_milestone.id))

    return {
        "created_phase_ids": created_phase_ids,
        "created_milestone_ids": created_milestone_ids,
    }


class ListPhasesInput(BaseModel):
    """Input for list_phases tool."""

    project_id: str = Field(..., description="プロジェクトID")


class GetPhaseInput(BaseModel):
    """Input for get_phase tool."""

    phase_id: str = Field(..., description="フェーズID")


class UpdatePhaseInput(BaseModel):
    """Input for update_phase tool."""

    phase_id: str = Field(..., description="フェーズID")
    name: Optional[str] = Field(None, description="フェーズ名")
    description: Optional[str] = Field(None, description="フェーズの説明")
    status: Optional[str] = Field(None, description="ステータス (ACTIVE/COMPLETED/ARCHIVED)")
    order_in_project: Optional[int] = Field(None, ge=1, description="プロジェクト内での順序")
    start_date: Optional[str] = Field(
        None,
        description=(
            "Planned start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    end_date: Optional[str] = Field(
        None,
        description=(
            "Planned end datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )


async def list_phases(
    user_id: str,
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: ListPhasesInput,
) -> dict:
    """List phases for a project."""
    try:
        project_id = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}

    access = await require_project_action(
        user_id,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.PHASE_MANAGE,
    )
    if isinstance(access, dict):
        return access

    phases = await phase_repo.list_by_project(access.owner_id, project_id)
    return {
        "phases": [phase.model_dump(mode="json") for phase in phases],
        "count": len(phases),
    }


def list_phases_tool(
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for listing phases."""

    async def _tool(input_data: dict) -> dict:
        """list_phases: 指定されたプロジェクトのフェーズ一覧を取得します。

        このツールは、プロジェクト内のすべてのフェーズを順序付きで取得し、
        各フェーズのタスク統計情報（総数、完了数、進行中数）も含めて返します。
        フェーズの概要を把握したい場合や、フェーズごとの進捗状況を確認したい場合に使用してください。

        Parameters:
            project_id (str): プロジェクトID（UUID形式、必須）

        Returns:
            dict: {
                "phases": [
                    {
                        "id": "フェーズID",
                        "name": "フェーズ名",
                        "description": "説明",
                        "project_id": "プロジェクトID",
                        "order_in_project": 順序番号,
                        "status": "ACTIVE/COMPLETED/ARCHIVED",
                        "start_date": "開始日（ISO形式）",
                        "end_date": "終了日（ISO形式）",
                        "total_tasks": 総タスク数,
                        "completed_tasks": 完了タスク数,
                        "in_progress_tasks": 進行中タスク数,
                        "created_at": "作成日時",
                        "updated_at": "更新日時"
                    }
                ],
                "count": フェーズ数
            }
        """
        return await list_phases(
            user_id,
            phase_repo,
            project_repo,
            member_repo,
            ListPhasesInput(**input_data),
        )

    _tool.__name__ = "list_phases"
    return FunctionTool(func=_tool)


async def get_phase(
    user_id: str,
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: GetPhaseInput,
) -> dict:
    """Get detailed phase information."""
    try:
        phase_id = UUID(input_data.phase_id)
    except ValueError:
        return {"error": f"Invalid phase ID format: {input_data.phase_id}"}

    project_id = await phase_repo.get_project_id(phase_id)
    owner_id = user_id
    if project_id:
        access = await require_project_member(user_id, project_id, project_repo, member_repo)
        if isinstance(access, dict):
            return access
        owner_id = access.owner_id

    phase = await phase_repo.get_by_id(owner_id, phase_id, project_id=project_id)
    if not phase:
        return {"error": f"Phase not found: {input_data.phase_id}"}

    return phase.model_dump(mode="json")


def get_phase_tool(
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for getting phase details."""

    async def _tool(input_data: dict) -> dict:
        """get_phase: フェーズの詳細情報を取得します。

        特定のフェーズの詳細情報を取得します。フェーズIDを指定して、
        そのフェーズの名前、説明、ステータス、日付などの情報を確認できます。
        フェーズを編集する前に現在の状態を確認したい場合などに使用してください。

        Parameters:
            phase_id (str): フェーズID（UUID形式、必須）

        Returns:
            dict: {
                "id": "フェーズID",
                "name": "フェーズ名",
                "description": "フェーズの説明",
                "project_id": "所属プロジェクトID",
                "user_id": "所有者ユーザーID",
                "order_in_project": プロジェクト内での順序,
                "status": "ACTIVE/COMPLETED/ARCHIVED",
                "start_date": "開始予定日（ISO形式）",
                "end_date": "終了予定日（ISO形式）",
                "created_at": "作成日時",
                "updated_at": "更新日時"
            }

            エラー時: {"error": "エラーメッセージ"}
        """
        return await get_phase(
            user_id,
            phase_repo,
            project_repo,
            member_repo,
            GetPhaseInput(**input_data),
        )

    _tool.__name__ = "get_phase"
    return FunctionTool(func=_tool)


async def update_phase(
    user_id: str,
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: UpdatePhaseInput,
    user_repo: Optional[IUserRepository] = None,
) -> dict:
    """Update phase information."""
    from app.models.enums import PhaseStatus
    from app.models.phase import PhaseUpdate

    try:
        phase_id = UUID(input_data.phase_id)
    except ValueError:
        return {"error": f"Invalid phase ID format: {input_data.phase_id}"}

    project_id = await phase_repo.get_project_id(phase_id)
    owner_id = user_id
    if project_id:
        access = await require_project_action(
            user_id,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.PHASE_MANAGE,
        )
        if isinstance(access, dict):
            return access
        owner_id = access.owner_id

    timezone_name = await _resolve_user_timezone(owner_id, user_repo)

    update_fields: dict = {}

    if input_data.name is not None:
        update_fields["name"] = input_data.name
    if input_data.description is not None:
        update_fields["description"] = input_data.description
    if input_data.status is not None:
        try:
            update_fields["status"] = PhaseStatus[input_data.status.upper()]
        except KeyError:
            return {"error": f"Invalid status: {input_data.status}. Must be ACTIVE, COMPLETED, or ARCHIVED"}
    if input_data.order_in_project is not None:
        update_fields["order_in_project"] = input_data.order_in_project
    if input_data.start_date is not None:
        update_fields["start_date"] = _parse_optional_datetime(input_data.start_date, timezone_name)
    if input_data.end_date is not None:
        update_fields["end_date"] = _parse_optional_datetime(input_data.end_date, timezone_name)

    if not update_fields:
        return {"error": "No fields to update"}

    update_model = PhaseUpdate(**update_fields)
    phase = await phase_repo.update(owner_id, phase_id, update_model, project_id=project_id)
    return phase.model_dump(mode="json")


def update_phase_tool(
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for updating phases."""

    async def _tool(input_data: dict) -> dict:
        """update_phase: 既存フェーズの情報を更新します。

        フェーズの名前、説明、ステータス、順序、日付などを更新できます。
        更新したいフィールドのみを指定してください（指定しないフィールドは変更されません）。
        フェーズの状態を変更したり、スケジュールを調整したりする場合に使用します。

        Parameters:
            phase_id (str): 更新対象のフェーズID（UUID形式、必須）
            name (str, optional): フェーズ名（最大200文字）
            description (str, optional): フェーズの説明（最大2000文字）
            status (str, optional): ステータス。以下のいずれか:
                - "ACTIVE": アクティブ（進行中）
                - "COMPLETED": 完了
                - "ARCHIVED": アーカイブ済み
            order_in_project (int, optional): プロジェクト内での順序（1以上の整数）
            start_date (str, optional): 開始予定日（ISO 8601形式、例: "2026-01-15T09:00:00Z"）
            end_date (str, optional): 終了予定日（ISO 8601形式、例: "2026-02-15T18:00:00Z"）

        Returns:
            dict: 更新されたフェーズの完全な情報（get_phaseと同じ形式）

            エラー時: {"error": "エラーメッセージ"}
                - 無効なフェーズID形式
                - フェーズが見つからない
                - 無効なステータス値
                - 更新するフィールドが指定されていない

        Example:
            # ステータスを完了に変更
            {"phase_id": "123e4567-e89b-12d3-a456-426614174000", "status": "COMPLETED"}

            # 名前と説明を更新
            {"phase_id": "123e4567-...", "name": "新しいフェーズ名", "description": "更新された説明"}
        """
        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "update_phase",
                payload,
                proposal_desc,
            )
        return await update_phase(
            user_id,
            phase_repo,
            project_repo,
            member_repo,
            UpdatePhaseInput(**payload),
            user_repo=user_repo,
        )

    _tool.__name__ = "update_phase"
    return FunctionTool(func=_tool)


# =============================================================================
# Simple CRUD Tools (No AI)
# =============================================================================


class CreatePhaseInput(BaseModel):
    """Input for create_phase tool."""

    project_id: str = Field(..., description="プロジェクトID")
    name: str = Field(..., description="フェーズ名")
    description: Optional[str] = Field(None, description="フェーズの説明")
    order_in_project: Optional[int] = Field(None, ge=1, description="プロジェクト内での順序")
    start_date: Optional[str] = Field(
        None,
        description=(
            "Planned start datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    end_date: Optional[str] = Field(
        None,
        description=(
            "Planned end datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )


class DeletePhaseInput(BaseModel):
    """Input for delete_phase tool."""

    phase_id: str = Field(..., description="フェーズID")


class CreateMilestoneInput(BaseModel):
    """Input for create_milestone tool."""

    project_id: str = Field(..., description="プロジェクトID")
    phase_id: str = Field(..., description="フェーズID")
    title: str = Field(..., description="マイルストーン名")
    description: Optional[str] = Field(None, description="マイルストーンの説明")
    order_in_phase: Optional[int] = Field(None, ge=1, description="フェーズ内での順序")
    due_date: Optional[str] = Field(
        None,
        description=(
            "Due datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )


class UpdateMilestoneInput(BaseModel):
    """Input for update_milestone tool."""

    milestone_id: str = Field(..., description="マイルストーンID")
    title: Optional[str] = Field(None, description="マイルストーン名")
    description: Optional[str] = Field(None, description="マイルストーンの説明")
    order_in_phase: Optional[int] = Field(None, ge=1, description="フェーズ内での順序")
    due_date: Optional[str] = Field(
        None,
        description=(
            "Due datetime in ISO 8601. If timezone offset is omitted, interpreted as user's local timezone."
        ),
    )
    is_completed: Optional[bool] = Field(None, description="完了フラグ")


class DeleteMilestoneInput(BaseModel):
    """Input for delete_milestone tool."""

    milestone_id: str = Field(..., description="マイルストーンID")


class ListMilestonesInput(BaseModel):
    """Input for list_milestones tool."""

    project_id: Optional[str] = Field(None, description="プロジェクトID（project_idまたはphase_idのいずれか必須）")
    phase_id: Optional[str] = Field(None, description="フェーズID（project_idまたはphase_idのいずれか必須）")


def list_milestones_tool(
    milestone_repo: IMilestoneRepository,
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for listing milestones."""

    async def _tool(input_data: dict) -> dict:
        """list_milestones: マイルストーン一覧を取得します。

        プロジェクトまたはフェーズに属するマイルストーンの一覧を取得します。
        各マイルストーンのタイトル、説明、期限、ステータスなどの情報を確認できます。

        Parameters:
            project_id (str, optional): プロジェクトID（UUID形式）
            phase_id (str, optional): フェーズID（UUID形式）
            ※ project_id または phase_id のいずれかを指定してください

        Returns:
            dict: {
                "milestones": [
                    {
                        "id": "マイルストーンID",
                        "title": "マイルストーンタイトル",
                        "description": "説明",
                        "project_id": "プロジェクトID",
                        "phase_id": "フェーズID",
                        "order_in_phase": フェーズ内の順序,
                        "status": "ACTIVE/COMPLETED",
                        "due_date": "期限日（ISO形式）",
                        "created_at": "作成日時",
                        "updated_at": "更新日時"
                    }
                ],
                "count": マイルストーン数
            }
        """
        payload = ListMilestonesInput(**input_data)

        if not payload.project_id and not payload.phase_id:
            return {"error": "project_id または phase_id のいずれかを指定してください"}

        milestones = []
        if payload.phase_id:
            try:
                phase_id = UUID(payload.phase_id)
            except ValueError:
                return {"error": f"Invalid phase ID format: {payload.phase_id}"}
            project_id = await phase_repo.get_project_id(phase_id)
            if not project_id:
                return {"error": f"Phase not found: {payload.phase_id}"}
            access = await require_project_action(
                user_id,
                project_id,
                project_repo,
                member_repo,
                ProjectAction.MILESTONE_MANAGE,
            )
            if isinstance(access, dict):
                return access
            milestones = await milestone_repo.list_by_phase(access.owner_id, phase_id)
        elif payload.project_id:
            try:
                project_id = UUID(payload.project_id)
            except ValueError:
                return {"error": f"Invalid project ID format: {payload.project_id}"}
            access = await require_project_action(
                user_id,
                project_id,
                project_repo,
                member_repo,
                ProjectAction.MILESTONE_MANAGE,
            )
            if isinstance(access, dict):
                return access
            milestones = await milestone_repo.list_by_project(access.owner_id, project_id)

        return {
            "milestones": [m.model_dump(mode="json") for m in milestones],
            "count": len(milestones),
        }

    _tool.__name__ = "list_milestones"
    return FunctionTool(func=_tool)


def create_phase_tool(
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for simple phase creation (no AI)."""

    async def _tool(input_data: dict) -> dict:
        """create_phase: 新しいフェーズを作成します（AI不使用）。

        プロジェクトに新しいフェーズを追加します。
        AI生成ではなく、指定された情報でそのままフェーズを作成します。

        Parameters:
            project_id (str): プロジェクトID（UUID形式、必須）
            name (str): フェーズ名（必須）
            description (str, optional): フェーズの説明
            order_in_project (int, optional): プロジェクト内での順序（1以上）
            start_date (str, optional): 開始予定日（ISO形式）
            end_date (str, optional): 終了予定日（ISO形式）

        Returns:
            dict: 作成されたフェーズの情報
        """
        payload_dict = dict(input_data)
        proposal_desc = payload_dict.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "create_phase",
                payload_dict,
                proposal_desc,
            )
        payload = CreatePhaseInput(**payload_dict)

        try:
            project_id = UUID(payload.project_id)
        except ValueError:
            return {"error": f"Invalid project ID format: {payload.project_id}"}

        access = await require_project_action(
            user_id,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.PHASE_MANAGE,
        )
        if isinstance(access, dict):
            return access

        timezone_name = await _resolve_user_timezone(access.owner_id, user_repo)

        # Get max order if not specified
        order = payload.order_in_project
        if order is None:
            existing_phases = await phase_repo.list_by_project(access.owner_id, project_id)
            order = len(existing_phases) + 1

        phase_create = PhaseCreate(
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            order_in_project=order,
            start_date=_parse_optional_datetime(payload.start_date, timezone_name),
            end_date=_parse_optional_datetime(payload.end_date, timezone_name),
        )

        created_phase = await phase_repo.create(access.owner_id, phase_create)
        return created_phase.model_dump(mode="json")

    _tool.__name__ = "create_phase"
    return FunctionTool(func=_tool)


def delete_phase_tool(
    phase_repo: IPhaseRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for phase deletion."""

    async def _tool(input_data: dict) -> dict:
        """delete_phase: フェーズを削除します。

        指定されたフェーズを削除します。
        注意: 関連するタスクやマイルストーンも影響を受ける可能性があります。

        Parameters:
            phase_id (str): フェーズID（UUID形式、必須）

        Returns:
            dict: {"success": True, "deleted_phase_id": "..."} または {"error": "..."}
        """
        payload_dict = dict(input_data)
        proposal_desc = payload_dict.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "delete_phase",
                payload_dict,
                proposal_desc,
            )
        payload = DeletePhaseInput(**payload_dict)

        try:
            phase_id = UUID(payload.phase_id)
        except ValueError:
            return {"error": f"Invalid phase ID format: {payload.phase_id}"}

        project_id = await phase_repo.get_project_id(phase_id)
        owner_id = user_id
        if project_id:
            access = await require_project_action(
                user_id,
                project_id,
                project_repo,
                member_repo,
                ProjectAction.PHASE_MANAGE,
            )
            if isinstance(access, dict):
                return access
            owner_id = access.owner_id

        success = await phase_repo.delete(owner_id, phase_id, project_id=project_id)
        if success:
            return {"success": True, "deleted_phase_id": payload.phase_id}
        return {"error": f"Phase not found or could not be deleted: {payload.phase_id}"}

    _tool.__name__ = "delete_phase"
    return FunctionTool(func=_tool)


def create_milestone_tool(
    milestone_repo: IMilestoneRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for simple milestone creation (no AI)."""

    async def _tool(input_data: dict) -> dict:
        """create_milestone: 新しいマイルストーンを作成します（AI不使用）。

        フェーズに新しいマイルストーンを追加します。

        Parameters:
            project_id (str): プロジェクトID（UUID形式、必須）
            phase_id (str): フェーズID（UUID形式、必須）
            title (str): マイルストーン名（必須）
            description (str, optional): マイルストーンの説明
            order_in_phase (int, optional): フェーズ内での順序（1以上）
            due_date (str, optional): 期限日（ISO形式）

        Returns:
            dict: 作成されたマイルストーンの情報
        """
        payload_dict = dict(input_data)
        proposal_desc = payload_dict.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "create_milestone",
                payload_dict,
                proposal_desc,
            )
        payload = CreateMilestoneInput(**payload_dict)

        try:
            project_id = UUID(payload.project_id)
            phase_id = UUID(payload.phase_id)
        except ValueError as e:
            return {"error": f"Invalid ID format: {e}"}

        access = await require_project_action(
            user_id,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.MILESTONE_MANAGE,
        )
        if isinstance(access, dict):
            return access

        timezone_name = await _resolve_user_timezone(access.owner_id, user_repo)

        # Get max order if not specified
        order = payload.order_in_phase
        if order is None:
            existing_milestones = await milestone_repo.list_by_phase(access.owner_id, phase_id)
            order = len(existing_milestones) + 1

        milestone_create = MilestoneCreate(
            project_id=project_id,
            phase_id=phase_id,
            title=payload.title,
            description=payload.description,
            order_in_phase=order,
            due_date=_parse_optional_datetime(payload.due_date, timezone_name),
        )

        created_milestone = await milestone_repo.create(access.owner_id, milestone_create)
        return created_milestone.model_dump(mode="json")

    _tool.__name__ = "create_milestone"
    return FunctionTool(func=_tool)


def update_milestone_tool(
    milestone_repo: IMilestoneRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
    user_repo: Optional[IUserRepository] = None,
) -> FunctionTool:
    """Create ADK tool for milestone update."""

    async def _tool(input_data: dict) -> dict:
        """update_milestone: マイルストーンを更新します。

        既存のマイルストーンの情報を更新します。

        Parameters:
            milestone_id (str): マイルストーンID（UUID形式、必須）
            title (str, optional): マイルストーン名
            description (str, optional): マイルストーンの説明
            order_in_phase (int, optional): フェーズ内での順序
            due_date (str, optional): 期限日（ISO形式）
            is_completed (bool, optional): 完了フラグ

        Returns:
            dict: 更新されたマイルストーンの情報
        """
        from app.models.milestone import MilestoneUpdate

        payload_dict = dict(input_data)
        proposal_desc = payload_dict.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "update_milestone",
                payload_dict,
                proposal_desc,
            )
        payload = UpdateMilestoneInput(**payload_dict)

        try:
            milestone_id = UUID(payload.milestone_id)
        except ValueError:
            return {"error": f"Invalid milestone ID format: {payload.milestone_id}"}

        project_id = await milestone_repo.get_project_id(milestone_id)
        owner_id = user_id
        if project_id:
            access = await require_project_action(
                user_id,
                project_id,
                project_repo,
                member_repo,
                ProjectAction.MILESTONE_MANAGE,
            )
            if isinstance(access, dict):
                return access
            owner_id = access.owner_id

        timezone_name = await _resolve_user_timezone(owner_id, user_repo)

        update_fields: dict = {}
        if payload.title is not None:
            update_fields["title"] = payload.title
        if payload.description is not None:
            update_fields["description"] = payload.description
        if payload.order_in_phase is not None:
            update_fields["order_in_phase"] = payload.order_in_phase
        if payload.due_date is not None:
            update_fields["due_date"] = _parse_optional_datetime(payload.due_date, timezone_name)
        if payload.is_completed is not None:
            update_fields["is_completed"] = payload.is_completed

        if not update_fields:
            return {"error": "No fields to update"}

        update_model = MilestoneUpdate(**update_fields)
        updated_milestone = await milestone_repo.update(owner_id, milestone_id, project_id, update_model)
        if not updated_milestone:
            return {"error": f"Milestone not found: {payload.milestone_id}"}
        return updated_milestone.model_dump(mode="json")

    _tool.__name__ = "update_milestone"
    return FunctionTool(func=_tool)


def delete_milestone_tool(
    milestone_repo: IMilestoneRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for milestone deletion."""

    async def _tool(input_data: dict) -> dict:
        """delete_milestone: マイルストーンを削除します。

        指定されたマイルストーンを削除します。

        Parameters:
            milestone_id (str): マイルストーンID（UUID形式、必須）

        Returns:
            dict: {"success": True, "deleted_milestone_id": "..."} または {"error": "..."}
        """
        payload_dict = dict(input_data)
        proposal_desc = payload_dict.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "delete_milestone",
                payload_dict,
                proposal_desc,
            )
        payload = DeleteMilestoneInput(**payload_dict)

        try:
            milestone_id = UUID(payload.milestone_id)
        except ValueError:
            return {"error": f"Invalid milestone ID format: {payload.milestone_id}"}

        project_id = await milestone_repo.get_project_id(milestone_id)
        owner_id = user_id
        if project_id:
            access = await require_project_action(
                user_id,
                project_id,
                project_repo,
                member_repo,
                ProjectAction.MILESTONE_MANAGE,
            )
            if isinstance(access, dict):
                return access
            owner_id = access.owner_id

        success = await milestone_repo.delete(owner_id, milestone_id, project_id)
        if success:
            return {"success": True, "deleted_milestone_id": payload.milestone_id}
        return {"error": f"Milestone not found or could not be deleted: {payload.milestone_id}"}

    _tool.__name__ = "delete_milestone"
    return FunctionTool(func=_tool)
