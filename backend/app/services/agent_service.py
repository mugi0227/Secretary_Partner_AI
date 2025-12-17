"""
Agent Service for running the Secretary Agent with ADK Runner.

This service handles agent execution, tool calling, and response generation.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part

from app.agents.secretary_agent import create_secretary_agent
from app.core.logger import logger
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.capture_repository import ICaptureRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.task_repository import ITaskRepository
from app.models.capture import CaptureCreate
from app.models.chat import ChatRequest, ChatResponse
from app.models.enums import ContentType


# Global cache for runners (keyed by user_id)
# This allows session state to persist across requests
_runner_cache: dict[str, InMemoryRunner] = {}


class AgentService:
    """Service for running the Secretary Agent."""

    APP_NAME = "SecretaryPartnerAI"

    def __init__(
        self,
        llm_provider: ILLMProvider,
        task_repo: ITaskRepository,
        memory_repo: IMemoryRepository,
        agent_task_repo: IAgentTaskRepository,
        capture_repo: ICaptureRepository,
    ):
        """
        Initialize Agent Service.

        Args:
            llm_provider: LLM provider
            task_repo: Task repository
            memory_repo: Memory repository
            agent_task_repo: Agent task repository
            capture_repo: Capture repository
        """
        self._llm_provider = llm_provider
        self._task_repo = task_repo
        self._memory_repo = memory_repo
        self._agent_task_repo = agent_task_repo
        self._capture_repo = capture_repo

    def _get_or_create_runner(self, user_id: str) -> InMemoryRunner:
        """Get cached runner or create a new one for the user."""
        if user_id not in _runner_cache:
            agent = create_secretary_agent(
                llm_provider=self._llm_provider,
                task_repo=self._task_repo,
                memory_repo=self._memory_repo,
                agent_task_repo=self._agent_task_repo,
                user_id=user_id,
            )
            _runner_cache[user_id] = InMemoryRunner(agent=agent, app_name=self.APP_NAME)
        return _runner_cache[user_id]

    async def process_chat(
        self,
        user_id: str,
        request: ChatRequest,
        session_id: str | None = None,
    ) -> ChatResponse:
        """
        Process a chat request with the Secretary Agent.

        Args:
            user_id: User ID
            request: Chat request
            session_id: Optional session ID for conversation continuity

        Returns:
            Chat response with assistant message and related tasks
        """
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid4())

        # Create capture if input provided
        capture_id = None
        text_content = request.text or ""

        if request.text:
            capture = await self._capture_repo.create(
                user_id,
                CaptureCreate(
                    content_type=ContentType.TEXT,
                    raw_text=request.text,
                ),
            )
            capture_id = capture.id
            text_content = request.text

        # Get or create runner (cached per user for session continuity)
        runner = self._get_or_create_runner(user_id)

        # Run agent with user message
        try:
            new_message = Content(role="user", parts=[Part(text=text_content)])

            # Ensure session exists (required by ADK runner)
            existing = await runner.session_service.get_session(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            if existing is None:
                await runner.session_service.create_session(
                    app_name=self.APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )

            assistant_message_parts: list[str] = []
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                if not event.content or not getattr(event.content, "parts", None):
                    continue
                for part in event.content.parts or []:
                    text = getattr(part, "text", None)
                    if text:
                        assistant_message_parts.append(text)

            assistant_message = "".join(assistant_message_parts).strip()
            if not assistant_message:
                assistant_message = "（応答が空でした。もう一度試してみてください）"

            # Extract related tasks from tool calls (if any)
            related_tasks = []
            # TODO: Parse tool call results to extract created/updated task IDs

            return ChatResponse(
                assistant_message=assistant_message,
                related_tasks=related_tasks,
                suggested_actions=[],
                session_id=session_id,
                capture_id=capture_id,
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            return ChatResponse(
                assistant_message=f"申し訳ございません。エラーが発生しました: {str(e)}",
                related_tasks=[],
                suggested_actions=[],
                session_id=session_id,
                capture_id=capture_id,
            )

    async def process_chat_stream(
        self,
        user_id: str,
        request: ChatRequest,
        session_id: str | None = None,
    ):
        """
        Process a chat request with streaming response.

        Yields SSE chunks for tool calls and text generation.

        Args:
            user_id: User ID
            request: Chat request
            session_id: Optional session ID for conversation continuity

        Yields:
            dict: Chunks with chunk_type (tool_start, tool_end, text, done, error)
        """
        # Generate session ID if not provided
        session_id_str = session_id or str(uuid4())

        # Create capture if input provided
        capture_id = None
        text_content = request.text or ""

        if request.text:
            capture = await self._capture_repo.create(
                user_id,
                CaptureCreate(
                    content_type=ContentType.TEXT,
                    raw_text=request.text,
                ),
            )
            capture_id = capture.id
            text_content = request.text

        # Get or create runner
        runner = self._get_or_create_runner(user_id)

        try:
            new_message = Content(role="user", parts=[Part(text=text_content)])

            # Ensure session exists
            existing = await runner.session_service.get_session(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id_str,
            )
            if existing is None:
                await runner.session_service.create_session(
                    app_name=self.APP_NAME,
                    user_id=user_id,
                    session_id=session_id_str,
                )

            # Stream agent execution
            assistant_message_parts: list[str] = []
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id_str,
                new_message=new_message,
            ):
                # Debug: log event structure
                logger.debug(f"Event type: {type(event).__name__}, attrs: {dir(event)}")

                # Handle tool calls - check content.parts for function_call
                if event.content and hasattr(event.content, "parts") and event.content.parts:
                    for part in event.content.parts:
                        # Check for function_call in part
                        func_call = getattr(part, "function_call", None)
                        if func_call:
                            yield {
                                "chunk_type": "tool_start",
                                "tool_name": func_call.name if hasattr(func_call, "name") else "unknown",
                                "tool_args": dict(func_call.args) if hasattr(func_call, "args") else {},
                            }

                        # Check for function_response in part
                        func_response = getattr(part, "function_response", None)
                        if func_response:
                            yield {
                                "chunk_type": "tool_end",
                                "tool_name": func_response.name if hasattr(func_response, "name") else "unknown",
                                "tool_result": str(func_response.response) if hasattr(func_response, "response") else "",
                            }

                        # Handle text content
                        text = getattr(part, "text", None)
                        if text:
                            assistant_message_parts.append(text)
                            # Yield text chunks character-by-character for streaming effect
                            for char in text:
                                yield {
                                    "chunk_type": "text",
                                    "content": char,
                                }

            # Final message
            assistant_message = "".join(assistant_message_parts).strip()
            if not assistant_message:
                assistant_message = "（応答が空でした。もう一度試してみてください）"

            # Send done event
            yield {
                "chunk_type": "done",
                "assistant_message": assistant_message,
                "session_id": session_id_str,
                "capture_id": str(capture_id) if capture_id else None,
            }

        except Exception as e:
            logger.error(f"Agent streaming failed: {e}", exc_info=True)
            yield {
                "chunk_type": "error",
                "content": f"申し訳ございません。エラーが発生しました: {str(e)}",
            }

