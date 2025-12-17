"""
Main Secretary Agent implementation using Google ADK.

This is the primary agent that handles user interactions and orchestrates tasks.
"""

from __future__ import annotations

from google.adk import Agent

from app.agents.prompts.secretary_prompt import SECRETARY_SYSTEM_PROMPT
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.llm_provider import ILLMProvider
from app.tools import (
    create_task_tool,
    update_task_tool,
    delete_task_tool,
    search_similar_tasks_tool,
    breakdown_task_tool,
    search_work_memory_tool,
    add_to_memory_tool,
    get_current_datetime_tool,
    schedule_agent_task_tool,
)


def create_secretary_agent(
    llm_provider: ILLMProvider,
    task_repo: ITaskRepository,
    memory_repo: IMemoryRepository,
    agent_task_repo: IAgentTaskRepository,
    user_id: str,
) -> Agent:
    """
    Create the main Secretary Agent with all tools.

    Args:
        llm_provider: LLM provider instance
        task_repo: Task repository
        memory_repo: Memory repository
        agent_task_repo: Agent task repository
        user_id: User ID

    Returns:
        Configured ADK Agent instance
    """
    # Get model from provider
    model = llm_provider.get_model()

    # Create tools
    tools = [
        get_current_datetime_tool(),
        create_task_tool(task_repo, user_id),
        update_task_tool(task_repo, user_id),
        delete_task_tool(task_repo, user_id),
        search_similar_tasks_tool(task_repo, user_id),
        breakdown_task_tool(task_repo, memory_repo, llm_provider, user_id),
        search_work_memory_tool(memory_repo, user_id),
        add_to_memory_tool(memory_repo, user_id),
        schedule_agent_task_tool(agent_task_repo, user_id),
    ]

    # Create agent
    agent = Agent(
        name="secretary",
        model=model,
        instruction=SECRETARY_SYSTEM_PROMPT,
        tools=tools,
    )

    return agent

