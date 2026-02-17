"""
Project-related agent tools.

Tools for creating projects.
"""

from __future__ import annotations

from typing import Optional

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.project_invitation_repository import IProjectInvitationRepository
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.proposal_repository import IProposalRepository
from app.models.collaboration import ProjectMemberCreate
from app.models.enums import ProjectRole
from app.models.project import ProjectCreate, ProjectUpdate
from app.models.project_kpi import ProjectKpiConfig, ProjectKpiMetric
from app.models.proposal import Proposal, ProposalType
from app.services.assignee_utils import make_invitation_assignee_id
from app.services.kpi_templates import get_kpi_templates
from app.services.llm_utils import generate_text
from app.services.project_permissions import ProjectAction
from app.tools.approval_tools import create_tool_action_proposal
from app.tools.permissions import require_project_action


class ProjectKpiMetricInput(BaseModel):
    """Input for KPI metric definition."""

    key: str = Field(..., description="KPI識別キー（英数字・スネークケース推奨）")
    label: str = Field(..., description="KPI表示名")
    description: Optional[str] = Field(None, description="KPIの説明")
    unit: Optional[str] = Field(None, description="単位（例: %, count, h）")
    target: Optional[float] = Field(None, description="目標値")
    current: Optional[float] = Field(None, description="現在値")
    direction: Optional[str] = Field("neutral", description="良くなる方向（up/down/neutral）")
    source: Optional[str] = Field(None, description="データソース（tasks/manual）")


class CreateProjectInput(BaseModel):
    """Input for create_project tool."""

    name: str = Field(..., description="プロジェクト名")
    description: Optional[str] = Field(None, description="概要")
    context: Optional[str] = Field(None, description="README/詳細コンテキスト")
    priority: int = Field(5, ge=1, le=10, description="優先度 (1-10)")
    goals: list[str] = Field(default_factory=list, description="ゴール一覧")
    key_points: list[str] = Field(default_factory=list, description="重要ポイント一覧")
    parent_project_id: Optional[str] = Field(
        None, description="親プロジェクトID（UUID）。指定すると子プロジェクトとして作成",
    )
    kpi_strategy: Optional[str] = Field(
        "custom",
        description="KPI選定戦略（template/custom）。AI選定は内部で処理。",
    )
    kpi_template_id: Optional[str] = Field(None, description="KPIテンプレートID")
    kpi_metrics: list[ProjectKpiMetricInput] = Field(
        default_factory=list,
        description="KPIメトリクス（テンプレ未使用時）",
    )


class UpdateProjectInput(BaseModel):
    """Input for update_project tool."""

    project_id: str = Field(..., description="プロジェクトID（UUID）")
    name: Optional[str] = Field(None, description="プロジェクト名")
    description: Optional[str] = Field(None, description="概要")
    priority: Optional[int] = Field(None, ge=1, le=10, description="優先度 (1-10)")
    status: Optional[str] = Field(None, description="ステータス (ACTIVE/COMPLETED/ARCHIVED)")
    context_summary: Optional[str] = Field(None, description="コンテキストサマリー")
    context: Optional[str] = Field(None, description="README/詳細コンテキスト")
    goals: Optional[list[str]] = Field(None, description="ゴール一覧")
    key_points: Optional[list[str]] = Field(None, description="重要ポイント一覧")
    parent_project_id: Optional[str] = Field(
        None,
        description="親プロジェクトID（UUID）。指定するとこのプロジェクトを子として紐付け。空文字で切り離し",
    )
    kpi_template_id: Optional[str] = Field(None, description="KPIテンプレートID")
    kpi_metrics: Optional[list[ProjectKpiMetricInput]] = Field(
        None,
        description="KPIメトリクス（指定時はカスタムとして扱う）",
    )


def _select_template_id(input_data: CreateProjectInput) -> str:
    """Pick a KPI template based on project context."""
    text_parts = [
        input_data.name,
        input_data.description or "",
        " ".join(input_data.goals or []),
        " ".join(input_data.key_points or []),
    ]
    text = " ".join(text_parts).lower()

    if any(keyword in text for keyword in ["営業", "商談", "売上", "受注", "パイプライン", "sales"]):
        return "sales"
    if any(keyword in text for keyword in ["運用", "サポート", "障害", "インシデント", "sla", "ops"]):
        return "operations"
    if any(keyword in text for keyword in ["研究", "調査", "探索", "リサーチ", "poc", "research"]):
        return "research"
    if any(keyword in text for keyword in ["開発", "スプリント", "実装", "リリース", "dev"]):
        return "sprint"
    if any(keyword in text for keyword in ["納期", "締切", "期限", "デリバリー", "deadline", "delivery"]):
        return "delivery"

    return "delivery"


def _normalize_source(value: Optional[str]) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"tasks", "task"}:
        return "tasks"
    if normalized in {"manual", "human"}:
        return "manual"
    return None


def _normalize_direction(value: Optional[str]) -> str:
    if not value:
        return "neutral"
    normalized = value.strip().lower()
    if normalized in {"up", "increase", "higher"}:
        return "up"
    if normalized in {"down", "decrease", "lower"}:
        return "down"
    return "neutral"


def _build_selection_prompt(input_data: CreateProjectInput) -> str:
    templates = get_kpi_templates()
    template_lines = []
    for template in templates:
        metric_lines = []
        for metric in template.metrics:
            metric_lines.append(f"- {metric.key}: {metric.label} ({metric.description or '説明なし'})")
        template_lines.append(
            "\n".join(
                [
                    f"テンプレートID: {template.id}",
                    f"名前: {template.name}",
                    f"説明: {template.description}",
                    "指標:",
                    *metric_lines,
                ]
            )
        )

    description = input_data.description or ""
    goals = " / ".join(input_data.goals or [])
    key_points = " / ".join(input_data.key_points or [])

    return f"""次のプロジェクトに最適なKPIを選定してください。
テンプレートに合致する場合は template を選び、template_id を指定してください。
どのテンプレートにも合わない場合は custom を選び、metrics を具体的に作成してください。

## プロジェクト情報
- 名称: {input_data.name}
- 概要: {description}
- ゴール: {goals}
- 重要ポイント: {key_points}

## KPIテンプレート一覧
{chr(10).join(template_lines)}

## 出力ルール
- JSONで出力
- strategy は template または custom
- template の場合、template_id を必須
- custom の場合、metrics を1-5個作成
- metrics の source は tasks または manual
- direction は up/down/neutral
"""


def _select_kpis_via_llm(
    llm_provider: ILLMProvider,
    input_data: CreateProjectInput,
) -> dict:
    """Use LLM to select KPI template or custom metrics."""
    prompt = _build_selection_prompt(input_data)
    schema = {
        "type": "OBJECT",
        "properties": {
            "strategy": {"type": "STRING", "enum": ["template", "custom"]},
            "template_id": {"type": "STRING"},
            "metrics": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING"},
                        "label": {"type": "STRING"},
                        "description": {"type": "STRING"},
                        "unit": {"type": "STRING"},
                        "target": {"type": "NUMBER"},
                        "current": {"type": "NUMBER"},
                        "direction": {"type": "STRING", "enum": ["up", "down", "neutral"]},
                        "source": {"type": "STRING", "enum": ["tasks", "manual"]},
                    },
                    "required": ["key", "label"],
                },
            },
        },
        "required": ["strategy"],
    }
    response_text = generate_text(
        llm_provider,
        prompt,
        temperature=0.2,
        max_output_tokens=400,
        response_schema=schema,
        response_mime_type="application/json",
    )
    if not response_text:
        return {}
    try:
        import json

        return json.loads(response_text)
    except Exception:
        return {}


async def propose_project(
    user_id: str,
    session_id: str,
    proposal_repo: IProposalRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository | None,
    llm_provider: ILLMProvider,
    input_data: CreateProjectInput,
    description: str = "",
    auto_approve: bool = False,
) -> dict:
    """
    Propose a project for user approval, or auto-approve if configured.

    Args:
        user_id: User ID
        session_id: Chat session ID
        proposal_repo: Proposal repository
        project_repo: Project repository (for auto-approval)
        member_repo: Project member repository (for owner membership)
        llm_provider: LLM provider (for auto-approval)
        input_data: Project creation data
        description: AI-generated description of why this project is being proposed
        auto_approve: If True, automatically approve and create the project

    Returns:
        If auto_approve=False: Proposal response with proposal_id
        If auto_approve=True: Created project info with project_id
    """
    from uuid import UUID

    # If no description provided, generate a simple one
    if not description:
        description = f"プロジェクト「{input_data.name}」を作成します。"

    # Auto-approve mode: create project immediately
    if auto_approve:
        created_project = await create_project(
            user_id=user_id,
            repo=project_repo,
            member_repo=member_repo,
            llm_provider=llm_provider,
            input_data=input_data,
        )
        return {
            "auto_approved": True,
            "project_id": created_project.get("id"),
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
        proposal_type=ProposalType.CREATE_PROJECT,
        payload=input_data.model_dump(mode="json"),
        description=description,
    )

    created_proposal = await proposal_repo.create(proposal)

    # Return pending_approval status to signal AI to wait for user approval
    return {
        "status": "pending_approval",
        "proposal_id": str(created_proposal.id),
        "proposal_type": ProposalType.CREATE_PROJECT.value,
        "description": description,
        "message": "ユーザーの承諾待ちです。承諾されるまで「完了しました」とは言わないでください。",
    }


async def create_project(
    user_id: str,
    repo: IProjectRepository,
    member_repo: IProjectMemberRepository | None,
    llm_provider: ILLMProvider,
    input_data: CreateProjectInput,
) -> dict:
    """Create a new project."""
    metrics: list[ProjectKpiMetric] = []
    template_id = input_data.kpi_template_id

    if input_data.kpi_metrics:
        metrics = [ProjectKpiMetric(**metric.model_dump()) for metric in input_data.kpi_metrics]
        strategy = "custom"
    elif input_data.kpi_template_id:
        template_id = input_data.kpi_template_id
        template = next(
            (item for item in get_kpi_templates() if item.id == template_id),
            None,
        )
        if template:
            metrics = [metric.model_copy() for metric in template.metrics]
        strategy = "template"
    else:
        selection = _select_kpis_via_llm(llm_provider, input_data)
        strategy = selection.get("strategy") if isinstance(selection, dict) else None
        selection_template_id = selection.get("template_id") if isinstance(selection, dict) else None
        selection_metrics = selection.get("metrics") if isinstance(selection, dict) else None

        if strategy == "custom" and selection_metrics:
            metrics = []
            for metric in selection_metrics:
                if not metric.get("key") or not metric.get("label"):
                    continue
                metrics.append(
                    ProjectKpiMetric(
                        key=metric.get("key"),
                        label=metric.get("label"),
                        description=metric.get("description"),
                        unit=metric.get("unit"),
                        target=metric.get("target"),
                        current=metric.get("current"),
                        direction=_normalize_direction(metric.get("direction")),
                        source=_normalize_source(metric.get("source")) or "manual",
                    )
                )
            template_id = None
        else:
            template_id = selection_template_id or _select_template_id(input_data)
            template = next(
                (item for item in get_kpi_templates() if item.id == template_id),
                None,
            )
            if template:
                metrics = [metric.model_copy() for metric in template.metrics]
            strategy = "template"

    kpi_config = ProjectKpiConfig(
        strategy=strategy or "template",
        template_id=template_id,
        metrics=metrics,
    )

    from uuid import UUID as _UUID

    project_data = ProjectCreate(
        name=input_data.name,
        description=input_data.description,
        context=input_data.context,
        priority=input_data.priority,
        goals=input_data.goals,
        key_points=input_data.key_points,
        parent_project_id=_UUID(input_data.parent_project_id) if input_data.parent_project_id else None,
        kpi_config=kpi_config,
    )

    project = await repo.create(user_id, project_data)
    if member_repo:
        await member_repo.create(
            user_id,
            project.id,
            ProjectMemberCreate(member_user_id=user_id, role=ProjectRole.OWNER),
        )
    return project.model_dump(mode="json")


def propose_project_tool(
    proposal_repo: IProposalRepository,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    llm_provider: ILLMProvider,
    user_id: str,
    session_id: str,
    auto_approve: bool = False,
) -> FunctionTool:
    """Create ADK tool for proposing/creating projects (with auto-approve option)."""
    async def _tool(input_data: dict) -> dict:
        """propose_project: 新しいプロジェクトを作成します。

        Parameters:
            name (str): プロジェクト名（必須）
            description (str, optional): 概要
            context (str, optional): README/詳細コンテキスト
            priority (int, optional): 優先度 (1-10)
            goals (list[str], optional): ゴール一覧
            key_points (list[str], optional): 重要ポイント一覧
            kpi_strategy (str, optional): KPI選定戦略（template/custom）
            kpi_template_id (str, optional): KPIテンプレートID
            kpi_metrics (list, optional): KPIメトリクス（テンプレ未使用時）
            proposal_description (str, optional): 提案の説明文（なぜこのプロジェクトを作成するか）

        Returns:
            dict: プロジェクトID、説明文、または提案ID（auto_approveの設定による）
        """
        # Debug: Log input_data type
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"propose_project called with input_data type: {type(input_data)}, value: {input_data}")

        # Extract proposal_description if provided
        if not isinstance(input_data, dict):
            logger.error(f"Expected dict but got {type(input_data)}: {input_data}")
            raise TypeError(f"input_data must be dict, got {type(input_data)}")
        proposal_desc = input_data.pop("proposal_description", "")
        return await propose_project(
            user_id, session_id, proposal_repo, project_repo, member_repo, llm_provider,
            CreateProjectInput(**input_data), proposal_desc, auto_approve
        )

    _tool.__name__ = "propose_project"
    return FunctionTool(func=_tool)


def create_project_tool(
    repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    llm_provider: ILLMProvider,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for creating projects."""
    async def _tool(input_data: dict) -> dict:
        """create_project: 新しいプロジェクトを作成します。

        Parameters:
            name (str): プロジェクト名（必須）
            description (str, optional): 概要
            context (str, optional): README/詳細コンテキスト
            priority (int, optional): 優先度 (1-10)
            goals (list[str], optional): ゴール一覧
            key_points (list[str], optional): 重要ポイント一覧
            parent_project_id (str, optional): 親プロジェクトID（UUID）。指定すると子プロジェクトとして作成
            kpi_strategy (str, optional): KPI選定戦略（template/custom）※AI選定は内部で処理
            kpi_template_id (str, optional): KPIテンプレートID
            kpi_metrics (list, optional): KPIメトリクス（テンプレ未使用時）

        Returns:
            dict: 作成されたプロジェクト情報
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"create_project called with input_data type: {type(input_data)}, value: {input_data}")

        if not isinstance(input_data, dict):
            logger.error(f"Expected dict but got {type(input_data)}: {input_data}")
            return {"error": f"input_data must be dict, got {type(input_data)}: {input_data}"}

        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await propose_project(
                user_id,
                session_id,
                proposal_repo,
                repo,
                member_repo,
                llm_provider,
                CreateProjectInput(**payload),
                proposal_desc,
                False,
            )
        return await create_project(
            user_id,
            repo,
            member_repo,
            llm_provider,
            CreateProjectInput(**payload),
        )

    _tool.__name__ = "create_project"
    return FunctionTool(func=_tool)


async def update_project(
    user_id: str,
    repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: UpdateProjectInput,
) -> dict:
    """Update a project."""
    from uuid import UUID

    try:
        project_id = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}
    access = await require_project_action(
        user_id,
        project_id,
        repo,
        member_repo,
        ProjectAction.PROJECT_UPDATE,
    )
    if isinstance(access, dict):
        return access
    update_fields: dict = {}

    if input_data.name is not None:
        update_fields["name"] = input_data.name
    if input_data.description is not None:
        update_fields["description"] = input_data.description
    if input_data.priority is not None:
        update_fields["priority"] = input_data.priority
    if input_data.status is not None:
        update_fields["status"] = input_data.status
    if input_data.context_summary is not None:
        update_fields["context_summary"] = input_data.context_summary
    if input_data.context is not None:
        update_fields["context"] = input_data.context
    if input_data.goals is not None:
        update_fields["goals"] = input_data.goals
    if input_data.key_points is not None:
        update_fields["key_points"] = input_data.key_points
    if input_data.parent_project_id is not None:
        if input_data.parent_project_id == "":
            update_fields["parent_project_id"] = None  # Detach
        else:
            update_fields["parent_project_id"] = UUID(input_data.parent_project_id)

    if input_data.kpi_metrics is not None or input_data.kpi_template_id is not None:
        if input_data.kpi_metrics is not None:
            metrics = [
                ProjectKpiMetric(**metric.model_dump())
                for metric in input_data.kpi_metrics
            ]
            kpi_config = ProjectKpiConfig(
                strategy="custom",
                template_id=None,
                metrics=metrics,
            )
        else:
            template_id = input_data.kpi_template_id
            template = next(
                (item for item in get_kpi_templates() if item.id == template_id),
                None,
            )
            metrics = [metric.model_copy() for metric in template.metrics] if template else []
            kpi_config = ProjectKpiConfig(
                strategy="template",
                template_id=template_id,
                metrics=metrics,
            )
        update_fields["kpi_config"] = kpi_config

    update_model = ProjectUpdate(**update_fields)
    project = await repo.update(access.owner_id, project_id, update_model)
    return project.model_dump(mode="json")


def update_project_tool(
    repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for updating projects."""
    async def _tool(input_data: dict) -> dict:
        """update_project: 既存プロジェクトを更新します。

        Parameters:
            project_id (str): プロジェクトID（UUID）
            name (str, optional): プロジェクト名
            description (str, optional): 概要
            priority (int, optional): 優先度 (1-10)
            status (str, optional): ステータス (ACTIVE/COMPLETED/ARCHIVED)
            context_summary (str, optional): コンテキストサマリー
            context (str, optional): README/詳細コンテキスト
            goals (list[str], optional): ゴール一覧
            key_points (list[str], optional): 重要ポイント一覧
            parent_project_id (str, optional): 親プロジェクトID。指定すると子として紐付け。空文字で切り離し
            kpi_template_id (str, optional): KPIテンプレートID
            kpi_metrics (list, optional): KPIメトリクス（指定時はカスタムとして扱う）

        Returns:
            dict: 更新されたプロジェクト情報
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"update_project called with input_data type: {type(input_data)}, value: {input_data}")

        if not isinstance(input_data, dict):
            logger.error(f"Expected dict but got {type(input_data)}: {input_data}")
            return {"error": f"input_data must be dict, got {type(input_data)}: {input_data}"}

        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "update_project",
                payload,
                proposal_desc,
            )
        return await update_project(user_id, repo, member_repo, UpdateProjectInput(**payload))

    _tool.__name__ = "update_project"
    return FunctionTool(func=_tool)


async def list_kpi_templates() -> dict:
    """List KPI templates."""
    templates = get_kpi_templates()
    return {
        "templates": [template.model_dump(mode="json") for template in templates],
        "count": len(templates),
    }


def list_kpi_templates_tool() -> FunctionTool:
    """Create ADK tool for listing KPI templates."""
    async def _tool(input_data: dict) -> dict:
        """list_kpi_templates: KPIテンプレート一覧を取得します。

        Returns:
            dict: templates (list), count (int)
        """
        return await list_kpi_templates()

    _tool.__name__ = "list_kpi_templates"
    return FunctionTool(func=_tool)


async def list_projects(
    user_id: str,
    repo: IProjectRepository,
) -> dict:
    """List all projects with priority information."""
    projects = await repo.list(user_id)

    # Return simplified project info for context
    project_list = [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "priority": p.priority,
            "status": p.status,
        }
        for p in projects
    ]

    return {"projects": project_list, "total": len(project_list)}


def list_projects_tool(repo: IProjectRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for listing projects."""
    async def _tool(input_data: dict) -> dict:
        """list_projects: プロジェクト一覧を取得します。

        各プロジェクトの基本情報（名前、説明、優先度）を取得できます。
        詳細なコンテキストが必要な場合は load_project_context を使用してください。

        Returns:
            dict: プロジェクト一覧（projects: list, total: int）
        """
        return await list_projects(user_id, repo)

    _tool.__name__ = "list_projects"
    return FunctionTool(func=_tool)



class ListProjectMembersInput(BaseModel):
    # Input for list_project_members tool.

    project_id: str = Field(..., description="Project ID")


async def list_project_members(
    user_id: str,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: ListProjectMembersInput,
) -> dict:
    # List members for a project.
    from uuid import UUID

    try:
        project_id = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}
    access = await require_project_action(
        user_id,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.MEMBER_READ,
    )
    if isinstance(access, dict):
        return access
    members = await member_repo.list(access.owner_id, project_id)
    return {
        "members": [member.model_dump(mode="json") for member in members],
        "count": len(members),
    }


def list_project_members_tool(
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for listing project members."""
    async def _tool(input_data: dict) -> dict:
        """list_project_members: List project members by project ID."""
        import logging
        logger = logging.getLogger(__name__)

        if not isinstance(input_data, dict):
            logger.error(f"list_project_members: Expected dict but got {type(input_data)}: {input_data}")
            return {"error": f"input_data must be dict, got {type(input_data)}: {input_data}"}

        return await list_project_members(
            user_id,
            project_repo,
            member_repo,
            ListProjectMembersInput(**input_data),
        )

    _tool.__name__ = "list_project_members"
    return FunctionTool(func=_tool)



class ListProjectInvitationsInput(BaseModel):
    # Input for list_project_invitations tool.

    project_id: str = Field(..., description="Project ID")


async def list_project_invitations(
    user_id: str,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    invitation_repo: IProjectInvitationRepository,
    input_data: ListProjectInvitationsInput,
) -> dict:
    # List invitations for a project.
    from uuid import UUID

    try:
        project_id = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}

    access = await require_project_action(
        user_id,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.INVITATION_READ,
    )
    if isinstance(access, dict):
        return access

    invitations = await invitation_repo.list_by_project(access.owner_id, project_id)
    result = []
    for invitation in invitations:
        data = invitation.model_dump(mode="json")
        if data.get("status") != "PENDING":
            continue
        invitation_id = data.get("id")
        if invitation_id:
            data["assignee_id"] = make_invitation_assignee_id(invitation_id)
        result.append(data)

    return {
        "invitations": result,
        "count": len(result),
    }


def list_project_invitations_tool(
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    invitation_repo: IProjectInvitationRepository,
    user_id: str,
) -> FunctionTool:
    # Create ADK tool for listing project invitations.
    async def _tool(input_data: dict) -> dict:
        # list_project_invitations: List project invitations by project ID.
        import logging
        logger = logging.getLogger(__name__)

        if not isinstance(input_data, dict):
            logger.error(f"list_project_invitations: Expected dict but got {type(input_data)}: {input_data}")
            return {"error": f"input_data must be dict, got {type(input_data)}: {input_data}"}

        return await list_project_invitations(
            user_id,
            project_repo,
            member_repo,
            invitation_repo,
            ListProjectInvitationsInput(**input_data),
        )

    _tool.__name__ = "list_project_invitations"
    return FunctionTool(func=_tool)


class LoadProjectContextInput(BaseModel):
    """Input for load_project_context tool."""

    project_id: str = Field(..., description="プロジェクトID")


async def load_project_context(
    user_id: str,
    repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    input_data: LoadProjectContextInput,
) -> dict:
    """Load detailed project context."""
    from uuid import UUID

    try:
        project_uuid = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}

    access = await require_project_action(
        user_id,
        project_uuid,
        repo,
        member_repo,
        ProjectAction.PROJECT_READ,
    )
    if isinstance(access, dict):
        return access
    project = await repo.get(access.owner_id, project_uuid)

    if not project:
        return {"error": f"Project not found: {input_data.project_id}"}

    # Get task count
    # Note: We don't have direct access to task_repo here, so we'll return the basic info
    # In a real implementation, you might want to pass task_repo as well

    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "context": project.context,
        "priority": project.priority,
        "goals": project.goals,
        "key_points": project.key_points,
        "kpi_config": project.kpi_config.model_dump(mode="json") if project.kpi_config else None,
        "status": project.status,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def load_project_context_tool(
    repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for loading project context."""
    async def _tool(input_data: dict) -> dict:
        """load_project_context: プロジェクトの詳細コンテキストを読み込みます。

        プロジェクトのREADME、ゴール、重要ポイント、KPI設定などの
        詳細情報を取得します。タスク分解前に必ず呼び出してください。

        Parameters:
            project_id (str): プロジェクトID（必須）

        Returns:
            dict: プロジェクトの詳細情報
        """
        import logging
        logger = logging.getLogger(__name__)

        if not isinstance(input_data, dict):
            logger.error(f"load_project_context: Expected dict but got {type(input_data)}: {input_data}")
            return {"error": f"input_data must be dict, got {type(input_data)}: {input_data}"}

        return await load_project_context(user_id, repo, member_repo, LoadProjectContextInput(**input_data))

    _tool.__name__ = "load_project_context"
    return FunctionTool(func=_tool)


class InviteProjectMemberInput(BaseModel):
    """Input for invite_project_member tool."""

    project_id: str = Field(..., description="プロジェクトID")
    email: str = Field(..., description="招待するメンバーのメールアドレス")
    role: str = Field("MEMBER", description="ロール (OWNER/ADMIN/MEMBER)")


async def invite_project_member(
    user_id: str,
    invitation_repo: IProjectInvitationRepository,
    member_repo: IProjectMemberRepository,
    project_repo: IProjectRepository,
    input_data: InviteProjectMemberInput,
) -> dict:
    """Invite a member to a project."""
    from uuid import UUID

    from app.models.collaboration import ProjectInvitationCreate
    from app.models.enums import ProjectRole

    try:
        project_id = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}

    access = await require_project_action(
        user_id,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.INVITATION_MANAGE,
    )
    if isinstance(access, dict):
        return access

    # Validate role
    try:
        role = ProjectRole[input_data.role.upper()]
    except KeyError:
        return {"error": f"Invalid role: {input_data.role}. Must be OWNER, ADMIN, or MEMBER"}

    # Check if invitation already exists
    existing = await invitation_repo.get_pending_by_email(project_id, input_data.email)
    if existing:
        return {"error": f"Invitation already exists for {input_data.email}"}

    # Create invitation
    invitation_data = ProjectInvitationCreate(
        email=input_data.email,
        role=role,
    )

    invitation = await invitation_repo.create(access.owner_id, project_id, user_id, invitation_data)
    return invitation.model_dump(mode="json")


def invite_project_member_tool(
    invitation_repo: IProjectInvitationRepository,
    member_repo: IProjectMemberRepository,
    project_repo: IProjectRepository,
    user_id: str,
    proposal_repo: Optional[IProposalRepository] = None,
    session_id: Optional[str] = None,
    auto_approve: bool = True,
) -> FunctionTool:
    """Create ADK tool for inviting project members."""

    async def _tool(input_data: dict) -> dict:
        """invite_project_member: プロジェクトにメンバーを招待します。

        指定されたメールアドレスにプロジェクト招待を送信します。
        招待されたユーザーは、招待を承諾するとプロジェクトメンバーになれます。
        招待にはプロジェクトのOWNERまたはADMIN権限が必要です。

        Parameters:
            project_id (str): 招待先のプロジェクトID（UUID形式、必須）
            email (str): 招待するメンバーのメールアドレス（必須）
            role (str, optional): メンバーのロール。以下のいずれか:
                - "OWNER": オーナー（プロジェクトの完全な管理権限）
                - "ADMIN": 管理者（メンバー管理を含む管理権限）
                - "MEMBER": メンバー（通常の参加権限、デフォルト）

        Returns:
            dict: {
                "id": "招待ID",
                "project_id": "プロジェクトID",
                "email": "招待メールアドレス",
                "role": "ロール",
                "status": "PENDING",
                "invited_by": "招待者ID",
                "token": "招待トークン（オプション）",
                "expires_at": "有効期限（ISO形式）",
                "created_at": "作成日時",
                "updated_at": "更新日時"
            }

            エラー時: {"error": "エラーメッセージ"}
                - 無効なプロジェクトID形式
                - 無効なロール値
                - 既に招待が存在する
                - 権限不足（OWNERまたはADMINでない）
                - 既にメンバーである

        Example:
            # メンバーとして招待
            {"project_id": "123e4567-e89b-12d3-a456-426614174000", "email": "user@example.com"}

            # 管理者として招待
            {"project_id": "123e4567-...", "email": "admin@example.com", "role": "ADMIN"}
        """
        import logging
        logger = logging.getLogger(__name__)

        if not isinstance(input_data, dict):
            logger.error(f"invite_project_member: Expected dict but got {type(input_data)}: {input_data}")
            return {"error": f"input_data must be dict, got {type(input_data)}: {input_data}"}

        payload = dict(input_data)
        proposal_desc = payload.pop("proposal_description", "")
        if proposal_repo and session_id and not auto_approve:
            return await create_tool_action_proposal(
                user_id,
                session_id,
                proposal_repo,
                "invite_project_member",
                payload,
                proposal_desc,
            )
        return await invite_project_member(
            user_id,
            invitation_repo,
            member_repo,
            project_repo,
            InviteProjectMemberInput(**payload),
        )

    _tool.__name__ = "invite_project_member"
    return FunctionTool(func=_tool)
