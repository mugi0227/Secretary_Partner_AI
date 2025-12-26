"""
Project-related agent tools.

Tools for creating projects.
"""

from __future__ import annotations

from typing import Optional

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.project_repository import IProjectRepository
from app.models.project import ProjectCreate, ProjectUpdate
from app.models.project_kpi import ProjectKpiConfig, ProjectKpiMetric
from app.services.kpi_templates import get_kpi_templates


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
    priority: int = Field(5, ge=1, le=10, description="優先度 (1-10)")
    goals: list[str] = Field(default_factory=list, description="ゴール一覧")
    key_points: list[str] = Field(default_factory=list, description="重要ポイント一覧")
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
    settings = getattr(llm_provider, "_settings", None)
    api_key = getattr(settings, "GOOGLE_API_KEY", None)
    if not api_key:
        return {}

    try:
        from google import genai
        from google.genai.types import Content, Part, GenerateContentConfig
    except Exception:
        return {}

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

    client = genai.Client(api_key=api_key)
    model_name = llm_provider.get_model()
    response = client.models.generate_content(
        model=model_name,
        contents=[Content(role="user", parts=[Part(text=prompt)])],
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    if not response.text:
        return {}
    try:
        import json

        return json.loads(response.text)
    except Exception:
        return {}


async def create_project(
    user_id: str,
    repo: IProjectRepository,
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

    project_data = ProjectCreate(
        name=input_data.name,
        description=input_data.description,
        priority=input_data.priority,
        goals=input_data.goals,
        key_points=input_data.key_points,
        kpi_config=kpi_config,
    )

    project = await repo.create(user_id, project_data)
    return project.model_dump(mode="json")


def create_project_tool(
    repo: IProjectRepository,
    llm_provider: ILLMProvider,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for creating projects."""
    async def _tool(input_data: dict) -> dict:
        """create_project: 新しいプロジェクトを作成します。

        Parameters:
            name (str): プロジェクト名（必須）
            description (str, optional): 概要
            priority (int, optional): 優先度 (1-10)
            goals (list[str], optional): ゴール一覧
            key_points (list[str], optional): 重要ポイント一覧
            kpi_strategy (str, optional): KPI選定戦略（template/custom）※AI選定は内部で処理
            kpi_template_id (str, optional): KPIテンプレートID
            kpi_metrics (list, optional): KPIメトリクス（テンプレ未使用時）

        Returns:
            dict: 作成されたプロジェクト情報
        """
        return await create_project(
            user_id,
            repo,
            llm_provider,
            CreateProjectInput(**input_data),
        )

    _tool.__name__ = "create_project"
    return FunctionTool(func=_tool)


async def update_project(
    user_id: str,
    repo: IProjectRepository,
    input_data: UpdateProjectInput,
) -> dict:
    """Update a project."""
    from uuid import UUID

    project_id = UUID(input_data.project_id)
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
    project = await repo.update(user_id, project_id, update_model)
    return project.model_dump(mode="json")


def update_project_tool(repo: IProjectRepository, user_id: str) -> FunctionTool:
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
            kpi_template_id (str, optional): KPIテンプレートID
            kpi_metrics (list, optional): KPIメトリクス（指定時はカスタムとして扱う）

        Returns:
            dict: 更新されたプロジェクト情報
        """
        return await update_project(user_id, repo, UpdateProjectInput(**input_data))

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


class LoadProjectContextInput(BaseModel):
    """Input for load_project_context tool."""

    project_id: str = Field(..., description="プロジェクトID")


async def load_project_context(
    user_id: str,
    repo: IProjectRepository,
    input_data: LoadProjectContextInput,
) -> dict:
    """Load detailed project context."""
    from uuid import UUID

    try:
        project_uuid = UUID(input_data.project_id)
    except ValueError:
        return {"error": f"Invalid project ID format: {input_data.project_id}"}

    project = await repo.get(user_id, project_uuid)

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


def load_project_context_tool(repo: IProjectRepository, user_id: str) -> FunctionTool:
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
        return await load_project_context(user_id, repo, LoadProjectContextInput(**input_data))

    _tool.__name__ = "load_project_context"
    return FunctionTool(func=_tool)
