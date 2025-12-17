"""
Planner Agent implementation.

Specializes in breaking down large tasks into micro-steps.
Can be called as a sub-agent from the main Secretary Agent.
"""

from __future__ import annotations

from google.adk import Agent

from app.agents.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.task_repository import ITaskRepository
from app.tools.memory_tools import search_work_memory_tool


def create_planner_agent(
    llm_provider: ILLMProvider,
    task_repo: ITaskRepository,
    memory_repo: IMemoryRepository,
    user_id: str,
) -> Agent:
    """
    Create the Planner Agent for task breakdown.

    Args:
        llm_provider: LLM provider instance
        task_repo: Task repository (for creating subtasks)
        memory_repo: Memory repository (for WorkMemory search)
        user_id: User ID

    Returns:
        Configured ADK Agent instance
    """
    model = llm_provider.get_model()

    # Planner only needs WorkMemory search tool
    tools = [
        search_work_memory_tool(memory_repo, user_id),
    ]

    agent = Agent(
        name="planner",
        model=model,
        instruction=PLANNER_SYSTEM_PROMPT,
        tools=tools,
    )

    return agent

