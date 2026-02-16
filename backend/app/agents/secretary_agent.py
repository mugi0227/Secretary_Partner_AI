"""
Main Secretary Agent implementation using Google ADK.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from google.adk import Agent

from app.agents.prompts.secretary_core_prompt import SECRETARY_CORE_PROMPT
from app.agents.prompts.secretary_skill_prompts import format_profile_skill_prompts
from app.agents.runtime_router import build_secretary_runtime_routing
from app.core.logger import logger
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.checkin_repository import ICheckinRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.meeting_agenda_repository import IMeetingAgendaRepository
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.milestone_repository import IMilestoneRepository
from app.interfaces.phase_repository import IPhaseRepository
from app.interfaces.project_invitation_repository import IProjectInvitationRepository
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.proposal_repository import IProposalRepository
from app.interfaces.recurring_meeting_repository import IRecurringMeetingRepository
from app.interfaces.recurring_task_repository import IRecurringTaskRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.services.work_memory_service import (
    format_loaded_work_memories_for_prompt,
    format_work_memory_index_for_prompt,
    get_work_memory_by_id,
    get_work_memory_index,
    select_relevant_work_memories,
)
from app.utils.datetime_utils import normalize_timezone, now_utc
from app.tools import (
    add_agenda_item_tool,
    add_to_memory_tool,
    apply_schedule_request_tool,
    ask_user_questions_tool,
    assign_task_tool,
    create_checkin_tool,
    create_meeting_tool,
    create_milestone_tool,
    create_phase_tool,
    create_project_summary_tool,
    create_project_tool,
    create_recurring_task_tool,
    create_task_tool,
    create_work_memory_tool,
    delete_agenda_item_tool,
    delete_milestone_tool,
    delete_phase_tool,
    delete_recurring_task_tool,
    delete_task_tool,
    fetch_meeting_context_tool,
    get_current_datetime_tool,
    get_phase_tool,
    get_task_tool,
    invite_project_member_tool,
    list_agenda_items_tool,
    list_checkins_tool,
    list_kpi_templates_tool,
    list_milestones_tool,
    list_phases_tool,
    list_project_assignments_tool,
    list_project_invitations_tool,
    list_project_members_tool,
    list_projects_tool,
    list_recurring_meetings_tool,
    list_recurring_tasks_tool,
    list_task_assignments_tool,
    list_tasks_tool,
    list_work_memory_index_tool,
    load_project_context_tool,
    load_work_memory_tool,
    refresh_user_profile_tool,
    register_browser_work_memory_tool,
    reorder_agenda_items_tool,
    run_browser_task_tool,
    run_hybrid_rpa_tool,
    schedule_agent_task_tool,
    search_memories_tool,
    search_similar_tasks_tool,
    search_work_memory_tool,
    update_agenda_item_tool,
    update_milestone_tool,
    update_phase_tool,
    update_project_tool,
    update_recurring_task_tool,
    update_task_tool,
)

_TOOL_HELP: dict[str, str] = {
    "get_current_datetime": "日時基準が必要なとき",
    "ask_user_questions": "不足情報を確認したいとき",
    "create_task": "新しいタスクを作りたいとき",
    "update_task": "既存タスクを修正したいとき",
    "delete_task": "不要タスクを消したいとき",
    "search_similar_tasks": "重複や類似を確認したいとき",
    "list_tasks": "タスク全体を見たいとき",
    "get_task": "特定タスクの詳細を見たいとき",
    "assign_task": "担当を割り当てたいとき",
    "list_task_assignments": "担当状況を確認したいとき",
    "list_project_assignments": "プロジェクト全体の担当を見たいとき",
    "create_project": "新規プロジェクトを作りたいとき",
    "update_project": "プロジェクト情報を更新したいとき",
    "list_projects": "プロジェクト一覧を確認したいとき",
    "list_project_members": "メンバー構成を確認したいとき",
    "list_project_invitations": "招待状況を確認したいとき",
    "load_project_context": "プロジェクト背景を読みたいとき",
    "invite_project_member": "メンバーを招待したいとき",
    "create_project_summary": "進捗要約を作りたいとき",
    "list_kpi_templates": "KPI雛形を選びたいとき",
    "list_phases": "フェーズ構成を確認したいとき",
    "get_phase": "フェーズ詳細を確認したいとき",
    "create_phase": "フェーズを追加したいとき",
    "update_phase": "フェーズ内容を更新したいとき",
    "delete_phase": "フェーズを削除したいとき",
    "list_milestones": "マイルストーン一覧を見たいとき",
    "create_milestone": "マイルストーンを追加したいとき",
    "update_milestone": "マイルストーンを更新したいとき",
    "delete_milestone": "マイルストーンを削除したいとき",
    "add_agenda_item": "議題を追加したいとき",
    "update_agenda_item": "議題を更新したいとき",
    "delete_agenda_item": "議題を削除したいとき",
    "list_agenda_items": "議題一覧を確認したいとき",
    "reorder_agenda_items": "議題順を並べ替えたいとき",
    "fetch_meeting_context": "会議前提をまとめて取得したいとき",
    "list_recurring_meetings": "定例会議の設定を確認したいとき",
    "create_checkin": "チェックインを記録したいとき",
    "list_checkins": "チェックイン履歴を見たいとき",
    "create_recurring_task": "定期タスクを作りたいとき",
    "list_recurring_tasks": "定期タスク一覧を見たいとき",
    "update_recurring_task": "定期タスク設定を更新したいとき",
    "delete_recurring_task": "定期タスクを止めたいとき",
    "search_memories": "保存メモを検索したいとき",
    "search_work_memory": "業務メモを絞って探したいとき",
    "create_work_memory": "手順を仕事メモリとして保存したいとき",
    "load_work_memory": "特定の仕事メモリの詳細を読みたいとき",
    "list_work_memory_index": "仕事メモリ一覧をざっと見たいとき",
    "add_to_memory": "知見をメモ保存したいとき",
    "refresh_user_profile": "プロフィール記憶を更新したいとき",
    "schedule_agent_task": "将来実行を予約したいとき",
    "apply_schedule_request": "今日の予定を整理したいとき",
    "run_browser_task": "Web操作を自動実行したいとき",
    "run_hybrid_rpa": "複雑なRPAを実行したいとき",
    "register_browser_work_memory": "ブラウザ操作を再利用化したいとき",
    "create_meeting": "会議予定タスクを作りたいとき",
}

_TOOL_CATALOG_SECTIONS: dict[str, tuple[str, ...]] = {
    "Task": (
        "create_task",
        "update_task",
        "delete_task",
        "search_similar_tasks",
        "list_tasks",
        "get_task",
        "assign_task",
    ),
    "Project": (
        "create_project",
        "update_project",
        "list_projects",
        "list_project_members",
        "list_project_invitations",
        "load_project_context",
        "invite_project_member",
        "create_project_summary",
    ),
    "Phase": (
        "list_phases",
        "get_phase",
        "create_phase",
        "update_phase",
        "delete_phase",
        "list_milestones",
        "create_milestone",
        "update_milestone",
        "delete_milestone",
    ),
    "Meeting": (
        "add_agenda_item",
        "update_agenda_item",
        "delete_agenda_item",
        "list_agenda_items",
        "reorder_agenda_items",
        "fetch_meeting_context",
        "list_recurring_meetings",
        "create_checkin",
        "list_checkins",
    ),
    "Memory/WorkMemory": (
        "search_memories",
        "search_work_memory",
        "create_work_memory",
        "load_work_memory",
        "list_work_memory_index",
        "add_to_memory",
        "refresh_user_profile",
    ),
    "Schedule": (
        "schedule_agent_task",
        "apply_schedule_request",
        "create_recurring_task",
        "list_recurring_tasks",
        "update_recurring_task",
        "delete_recurring_task",
    ),
    "Browser": (
        "run_browser_task",
        "run_hybrid_rpa",
        "register_browser_work_memory",
    ),
}


async def _resolve_user_timezone(user_id: str, user_repo: IUserRepository | None) -> str:
    if user_repo is None:
        return normalize_timezone(None)
    try:
        user = await user_repo.get(UUID(user_id))
    except (ValueError, TypeError):
        user = None
    return normalize_timezone(user.timezone if user else None)


def get_current_datetime_section(user_timezone: str) -> str:
    resolved_timezone = normalize_timezone(user_timezone)
    now = now_utc().astimezone(ZoneInfo(resolved_timezone))
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = weekday_names[now.weekday()]
    return (
        "## Current DateTime\n"
        f"{now.year:04d}-{now.month:02d}-{now.day:02d} "
        f"{now.hour:02d}:{now.minute:02d} {resolved_timezone} ({weekday})"
    )


def _filter_tools_by_name(tools: list[Any], allowed_tool_names: frozenset[str]) -> list[Any]:
    filtered = [tool for tool in tools if getattr(tool, "name", "") in allowed_tool_names]
    if filtered:
        return filtered
    fallback_names = {"get_current_datetime", "ask_user_questions"}
    return [tool for tool in tools if getattr(tool, "name", "") in fallback_names]


def _format_tools_for_prompt(
    enabled_tool_names: list[str],
    include_catalog: bool,
) -> str:
    lines = ["## Enabled Tools (This Turn)"]
    lines.append("- 下の用途一覧を見て選び、詳細仕様は実行時のツール定義で確認する。")
    for name in enabled_tool_names:
        desc = _TOOL_HELP.get(name, "利用可能")
        lines.append(f"- `{name}`: 使うとき -> {desc}")

    if not include_catalog:
        return "\n".join(lines)

    lines.append("")
    lines.append("## Tool Catalog (All)")
    lines.append("質問が能力確認の場合は、この一覧をベースに回答する。")
    for section, names in _TOOL_CATALOG_SECTIONS.items():
        lines.append(f"- {section}: " + ", ".join(f"`{name}`" for name in names))
    return "\n".join(lines)


async def build_system_prompt_with_work_memory(
    user_id: str,
    memory_repo: IMemoryRepository,
    user_message: str | None,
    profiles: tuple[str, ...],
    enabled_tool_names: list[str],
    include_tool_catalog: bool,
    user_repo: IUserRepository | None = None,
) -> str:
    user_timezone = await _resolve_user_timezone(user_id, user_repo)
    datetime_section = get_current_datetime_section(user_timezone)
    profile_skill_section = format_profile_skill_prompts(profiles)

    work_memories = await get_work_memory_index(user_id, memory_repo, limit=30)
    work_memory_index_section = format_work_memory_index_for_prompt(work_memories, max_items=8)

    selected = select_relevant_work_memories(work_memories, user_message or "", limit=2)
    loaded_work_memories = []
    for item in selected:
        full_memory = await get_work_memory_by_id(user_id, memory_repo, item.id)
        if full_memory:
            loaded_work_memories.append(full_memory)
    loaded_work_memory_section = format_loaded_work_memories_for_prompt(
        loaded_work_memories,
        max_chars_per_work_memory=600,
    )
    tools_section = _format_tools_for_prompt(
        enabled_tool_names=enabled_tool_names,
        include_catalog=include_tool_catalog,
    )

    sections = [
        datetime_section,
        SECRETARY_CORE_PROMPT,
        tools_section,
        profile_skill_section,
        work_memory_index_section,
        loaded_work_memory_section,
    ]
    return "\n\n".join(section for section in sections if section)


def _resolve_runtime_routing_options(
    routing_context: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    if not isinstance(routing_context, dict):
        return False, None

    raw_mode = (
        routing_context.get("extension_agent_mode")
        or routing_context.get("agent_mode")
    )
    normalized_mode = str(raw_mode or "").strip().lower().replace("-", "_")
    if normalized_mode in {"browser", "browser_agent"}:
        return True, "browser"
    return False, None


async def create_secretary_agent(
    llm_provider: ILLMProvider,
    task_repo: ITaskRepository,
    project_repo: IProjectRepository,
    phase_repo: IPhaseRepository,
    milestone_repo: IMilestoneRepository,
    project_member_repo: IProjectMemberRepository,
    project_invitation_repo: IProjectInvitationRepository,
    task_assignment_repo: ITaskAssignmentRepository,
    memory_repo: IMemoryRepository,
    agent_task_repo: IAgentTaskRepository,
    meeting_agenda_repo: IMeetingAgendaRepository,
    recurring_meeting_repo: IRecurringMeetingRepository,
    recurring_task_repo: IRecurringTaskRepository,
    checkin_repo: ICheckinRepository,
    user_id: str,
    proposal_repo: IProposalRepository,
    session_id: str,
    auto_approve: bool = True,
    user_repo: IUserRepository | None = None,
    user_message: str | None = None,
    routing_context: dict[str, Any] | None = None,
) -> Agent:
    allow_browser, forced_profile = _resolve_runtime_routing_options(routing_context)
    routing = build_secretary_runtime_routing(
        user_message,
        allow_browser=allow_browser,
        forced_profile=forced_profile,
    )
    model = llm_provider.get_model()

    task_creation_tool = create_task_tool(
        task_repo,
        project_repo,
        project_member_repo,
        user_id,
        proposal_repo=proposal_repo,
        session_id=session_id,
        auto_approve=auto_approve,
        assignment_repo=task_assignment_repo,
        user_repo=user_repo,
    )
    task_assignment_tool = assign_task_tool(
        task_assignment_repo,
        task_repo,
        project_repo,
        project_member_repo,
        user_id,
        proposal_repo=proposal_repo,
        session_id=session_id,
        auto_approve=auto_approve,
    )
    project_creation_tool = create_project_tool(
        project_repo,
        project_member_repo,
        llm_provider,
        user_id,
        proposal_repo=proposal_repo,
        session_id=session_id,
        auto_approve=auto_approve,
    )
    work_memory_creation_tool = create_work_memory_tool(
        memory_repo,
        user_id,
        proposal_repo=proposal_repo,
        session_id=session_id,
        auto_approve=auto_approve,
    )

    all_tools = [
        get_current_datetime_tool(),
        task_creation_tool,
        task_assignment_tool,
        create_meeting_tool(
            task_repo,
            proposal_repo,
            project_repo,
            project_member_repo,
            user_id,
            session_id,
            auto_approve=auto_approve,
        ),
        list_kpi_templates_tool(),
        project_creation_tool,
        work_memory_creation_tool,
        list_projects_tool(project_repo, user_id),
        list_project_members_tool(project_repo, project_member_repo, user_id),
        list_project_invitations_tool(project_repo, project_member_repo, project_invitation_repo, user_id),
        load_project_context_tool(project_repo, project_member_repo, user_id),
        create_project_summary_tool(
            project_repo,
            task_repo,
            memory_repo,
            llm_provider,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        update_project_tool(
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        invite_project_member_tool(
            project_invitation_repo,
            project_member_repo,
            project_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        update_task_tool(
            task_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
            user_repo=user_repo,
        ),
        delete_task_tool(
            task_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        search_similar_tasks_tool(task_repo, project_repo, project_member_repo, user_id),
        list_tasks_tool(task_repo, project_repo, project_member_repo, user_id),
        get_task_tool(task_repo, project_repo, project_member_repo, user_id),
        list_task_assignments_tool(
            task_assignment_repo,
            task_repo,
            project_repo,
            project_member_repo,
            user_id,
        ),
        list_project_assignments_tool(
            task_assignment_repo,
            project_repo,
            project_member_repo,
            user_id,
        ),
        search_memories_tool(memory_repo, user_id),
        search_work_memory_tool(memory_repo, user_id),
        add_to_memory_tool(
            memory_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        refresh_user_profile_tool(
            memory_repo,
            llm_provider,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        schedule_agent_task_tool(
            agent_task_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        apply_schedule_request_tool(
            task_repo,
            task_assignment_repo,
            project_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
            user_repo=user_repo,
        ),
        list_phases_tool(phase_repo, project_repo, project_member_repo, user_id),
        get_phase_tool(phase_repo, project_repo, project_member_repo, user_id),
        update_phase_tool(
            phase_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        create_phase_tool(
            phase_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        delete_phase_tool(
            phase_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        create_milestone_tool(
            milestone_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        update_milestone_tool(
            milestone_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        delete_milestone_tool(
            milestone_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        list_milestones_tool(
            milestone_repo,
            phase_repo,
            project_repo,
            project_member_repo,
            user_id,
        ),
        add_agenda_item_tool(
            meeting_agenda_repo,
            project_repo,
            project_member_repo,
            recurring_meeting_repo,
            task_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        update_agenda_item_tool(
            meeting_agenda_repo,
            project_repo,
            project_member_repo,
            recurring_meeting_repo,
            task_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        delete_agenda_item_tool(
            meeting_agenda_repo,
            project_repo,
            project_member_repo,
            recurring_meeting_repo,
            task_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        list_agenda_items_tool(
            meeting_agenda_repo,
            project_repo,
            project_member_repo,
            recurring_meeting_repo,
            task_repo,
            user_id,
        ),
        reorder_agenda_items_tool(
            meeting_agenda_repo,
            project_repo,
            project_member_repo,
            recurring_meeting_repo,
            task_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        fetch_meeting_context_tool(
            checkin_repo,
            task_repo,
            meeting_agenda_repo,
            project_repo,
            recurring_meeting_repo,
            project_member_repo,
            user_id,
            user_repo=user_repo,
        ),
        list_recurring_meetings_tool(recurring_meeting_repo, project_repo, project_member_repo, user_id),
        create_checkin_tool(
            checkin_repo,
            project_repo,
            project_member_repo,
            user_id,
            proposal_repo=proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
        ),
        list_checkins_tool(
            checkin_repo,
            project_repo,
            project_member_repo,
            user_id,
        ),
        create_recurring_task_tool(recurring_task_repo, task_repo, user_id),
        list_recurring_tasks_tool(recurring_task_repo, user_id),
        update_recurring_task_tool(recurring_task_repo, user_id),
        delete_recurring_task_tool(recurring_task_repo, user_id),
        load_work_memory_tool(memory_repo, user_id),
        list_work_memory_index_tool(memory_repo, user_id),
        run_browser_task_tool(),
        run_hybrid_rpa_tool(),
        register_browser_work_memory_tool(),
        ask_user_questions_tool(),
    ]

    tools = _filter_tools_by_name(all_tools, routing.tool_names)
    enabled_tool_names = [getattr(tool, "name", "") for tool in tools if getattr(tool, "name", "")]
    system_prompt = await build_system_prompt_with_work_memory(
        user_id=user_id,
        memory_repo=memory_repo,
        user_message=user_message,
        profiles=routing.profiles,
        enabled_tool_names=enabled_tool_names,
        include_tool_catalog="capability" in routing.profiles,
        user_repo=user_repo,
    )
    logger.info(
        "secretary_runtime profiles=%s tools=%s",
        ",".join(routing.profiles),
        ",".join(getattr(tool, "name", "") for tool in tools),
    )

    return Agent(
        name="secretary",
        model=model,
        instruction=system_prompt,
        tools=tools,
    )
