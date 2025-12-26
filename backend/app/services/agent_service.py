"""
Agent Service for running the Secretary Agent with ADK Runner.

This service handles agent execution, tool calling, and response generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part

from app.agents.secretary_agent import create_secretary_agent
from app.core.config import get_settings
from app.core.logger import logger
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.capture_repository import ICaptureRepository
from app.interfaces.chat_session_repository import IChatSessionRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.task_repository import ITaskRepository
from app.models.capture import CaptureCreate
from app.models.chat import ChatRequest, ChatResponse
from app.models.enums import ContentType


# Global cache for runners (keyed by user_id)
# This allows session state to persist across requests
_runner_cache: dict[str, InMemoryRunner] = {}
_session_index: dict[str, dict[str, dict[str, Any]]] = {}


class AgentService:
    """Service for running the Secretary Agent."""

    APP_NAME = "SecretaryPartnerAI"

    def __init__(
        self,
        llm_provider: ILLMProvider,
        task_repo: ITaskRepository,
        project_repo: IProjectRepository,
        memory_repo: IMemoryRepository,
        agent_task_repo: IAgentTaskRepository,
        capture_repo: ICaptureRepository,
        chat_repo: IChatSessionRepository,
    ):
        """
        Initialize Agent Service.

        Args:
            llm_provider: LLM provider
            task_repo: Task repository
            project_repo: Project repository
            memory_repo: Memory repository
            agent_task_repo: Agent task repository
            capture_repo: Capture repository
            chat_repo: Chat session repository
        """
        self._llm_provider = llm_provider
        self._task_repo = task_repo
        self._project_repo = project_repo
        self._memory_repo = memory_repo
        self._agent_task_repo = agent_task_repo
        self._capture_repo = capture_repo
        self._chat_repo = chat_repo

    def _get_or_create_runner(self, user_id: str) -> InMemoryRunner:
        """Get cached runner or create a new one for the user."""
        if user_id not in _runner_cache:
            agent = create_secretary_agent(
                llm_provider=self._llm_provider,
                task_repo=self._task_repo,
                project_repo=self._project_repo,
                memory_repo=self._memory_repo,
                agent_task_repo=self._agent_task_repo,
                user_id=user_id,
            )
            _runner_cache[user_id] = InMemoryRunner(agent=agent, app_name=self.APP_NAME)
        return _runner_cache[user_id]

    def _touch_session_index(self, user_id: str, session_id: str, title: str | None = None) -> None:
        """Track session metadata for list/history fallback when ADK APIs are unavailable."""
        user_sessions = _session_index.setdefault(user_id, {})
        entry = user_sessions.get(session_id)
        updated_at = datetime.now(timezone.utc).isoformat()
        if entry:
            entry["updated_at"] = updated_at
            if title:
                entry["title"] = title
            return
        user_sessions[session_id] = {
            "session_id": session_id,
            "title": title or "New Chat",
            "updated_at": updated_at,
        }

    def _derive_session_title(self, text: str | None) -> str | None:
        """Derive a session title from user text."""
        if not text:
            return None
        cleaned = text.strip()
        if not cleaned:
            return None
        max_len = 50
        return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")

    def _get_user_message_text(self, request: ChatRequest) -> str:
        """Get a storable user message text."""
        if request.text:
            return request.text
        if request.image_base64 or request.image_url:
            return "[Image attached]"
        return ""

    async def _record_session(self, user_id: str, session_id: str, title: str | None = None) -> None:
        """Record session metadata in persistent storage and fallback index."""
        self._touch_session_index(user_id, session_id, title=title)
        if self._chat_repo:
            await self._chat_repo.touch_session(user_id, session_id, title=title)

    async def _record_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        title: str | None = None,
    ) -> None:
        """Record a message in persistent storage."""
        self._touch_session_index(user_id, session_id, title=title)
        if self._chat_repo:
            await self._chat_repo.add_message(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                title=title,
            )

    def _normalize_session_record(self, session: Any) -> tuple[str | None, Any | None]:
        """Normalize session record across ADK versions."""
        if isinstance(session, dict):
            return session.get("session_id") or session.get("id"), session.get("updated_at")
        if hasattr(session, "session_id"):
            return session.session_id, getattr(session, "updated_at", None)
        if isinstance(session, (tuple, list)):
            session_id = None
            updated_at = None
            for item in session:
                if hasattr(item, "session_id"):
                    session_id = item.session_id
                    if getattr(item, "updated_at", None):
                        updated_at = item.updated_at
                    break
            if not session_id and session:
                first = session[0]
                if isinstance(first, str):
                    session_id = first
                elif isinstance(first, dict):
                    session_id = first.get("session_id") or first.get("id")
                    updated_at = first.get("updated_at") or updated_at
            if not updated_at:
                for item in session:
                    if hasattr(item, "isoformat"):
                        updated_at = item
                        break
                    if isinstance(item, str) and "T" in item:
                        updated_at = item
                        break
            return session_id, updated_at
        return None, None

    async def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """List active sessions for the user."""
        runner = self._get_or_create_runner(user_id)
        if self._chat_repo:
            stored_sessions = await self._chat_repo.list_sessions(user_id=user_id)
            if stored_sessions:
                result = []
                for session in stored_sessions:
                    entry = {
                        "session_id": session.session_id,
                        "title": session.title or "New Chat",
                        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
                    }
                    result.append(entry)
                    self._touch_session_index(user_id, session.session_id, title=session.title)
                return result
        sessions = []
        if hasattr(runner.session_service, "list_sessions"):
            try:
                sessions = await runner.session_service.list_sessions(
                    app_name=self.APP_NAME,
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning(f"Failed to list sessions via ADK: {e}")

        result = []
        if sessions:
            for session in sessions:
                session_id, updated_at_raw = self._normalize_session_record(session)
                if not session_id:
                    continue
                title = "New Chat"
                try:
                    messages = await runner.session_service.get_messages(
                        app_name=self.APP_NAME,
                        user_id=user_id,
                        session_id=session_id,
                    )
                except Exception:
                    messages = []

                if messages:
                    for msg in messages:
                        if msg.role == "user" and msg.parts:
                            for part in msg.parts:
                                if hasattr(part, "text") and part.text:
                                    title = part.text[:50] + ("..." if len(part.text) > 50 else "")
                                    break
                            if title != "New Chat":
                                break

                if isinstance(updated_at_raw, str):
                    updated_at = updated_at_raw
                elif updated_at_raw:
                    updated_at = updated_at_raw.isoformat()
                else:
                    updated_at = None
                entry = {
                    "session_id": session_id,
                    "title": title,
                    "updated_at": updated_at,
                }
                result.append(entry)
                self._touch_session_index(user_id, session_id, title=title)

            return sorted(result, key=lambda x: x.get("updated_at") or "", reverse=True)

        fallback_sessions = list(_session_index.get(user_id, {}).values())
        return sorted(fallback_sessions, key=lambda x: x.get("updated_at") or "", reverse=True)

    async def get_session_messages(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        """Get all messages for a specific session."""
        runner = self._get_or_create_runner(user_id)
        if self._chat_repo:
            stored_messages = await self._chat_repo.list_messages(
                user_id=user_id,
                session_id=session_id,
            )
            if stored_messages:
                result = []
                for msg in stored_messages:
                    result.append(
                        {
                            "role": msg.role,
                            "content": msg.content,
                            "created_at": msg.created_at.isoformat() if msg.created_at else None,
                        }
                    )
                return result
        if not hasattr(runner.session_service, "get_messages"):
            return []

        try:
            messages = await runner.session_service.get_messages(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception as e:
            logger.warning(f"Failed to load messages for session {session_id}: {e}")
            return []
        
        result = []
        for msg in messages:
            content = ""
            for part in msg.parts or []:
                if hasattr(part, "text") and part.text:
                    content += part.text
                
            result.append({
                "role": msg.role,
                "content": content,
                "created_at": msg.created_at.isoformat() if hasattr(msg, "created_at") else None
            })
        return result
    async def _construct_user_message(self, request: ChatRequest) -> Content:
        """Construct multimodal user message."""
        parts = []
        if request.text:
            parts.append(Part(text=request.text))

        # Handle Base64 image (priority over image_url)
        if request.image_base64:
            import base64
            import re

            # Extract mime type and base64 data from data URL
            # Format: data:image/png;base64,iVBORw0KGgo...
            match = re.match(r'data:([^;]+);base64,(.+)', request.image_base64)
            if match:
                mime_type = match.group(1)
                base64_data = match.group(2)
                try:
                    image_bytes = base64.b64decode(base64_data)
                    parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))
                    logger.info(f"Added Base64 image to message: {mime_type}, {len(image_bytes)} bytes")
                except Exception as e:
                    logger.error(f"Failed to decode Base64 image: {e}")
                    parts.append(Part(text=f"[Image decoding failed: {str(e)}]"))
            else:
                logger.warning(f"Invalid Base64 data URL format: {request.image_base64[:100]}")
                parts.append(Part(text="[Invalid image format]"))

        elif request.image_url:
            # Check if it's a local storage URL that we can read directly
            settings = get_settings()
            storage_prefix = f"{settings.BASE_URL}/storage/"
            
            image_path = None
            if request.image_url.startswith(storage_prefix):
                # Resolve to local file path
                relative_path = request.image_url[len(storage_prefix):]
                abs_storage_path = Path(settings.STORAGE_BASE_PATH).absolute()
                image_path = abs_storage_path / relative_path
            elif request.image_url.startswith("file://"):
                # Robust fallback for file:// URLs
                local_path_str = request.image_url[7:]
                # Handle file:///C:/... (remove leading slash if it exists before drive letter)
                if local_path_str.startswith("/") and len(local_path_str) > 2 and local_path_str[2] == ":":
                    local_path_str = local_path_str[1:]
                image_path = Path(local_path_str)
                logger.info(f"Handling file:// URL by mapping to local path: {image_path}")
            elif not request.image_url.startswith(("http://", "https://")):
                candidate_path = Path(request.image_url)
                if candidate_path.is_absolute():
                    image_path = candidate_path
                    logger.info(f"Handling absolute path by mapping to local path: {image_path}")

            if image_path:
                try:
                    if image_path.exists():
                        image_bytes = image_path.read_bytes()
                        import mimetypes
                        mime_type, _ = mimetypes.guess_type(str(image_path))
                        mime_type = mime_type or "image/jpeg"
                        parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))
                        logger.info(f"Loaded image successfully: {image_path} ({len(image_bytes)} bytes)")
                    else:
                        logger.warning(f"Image file not found: {image_path}")
                        parts.append(Part(text=f"[Image file not found: {image_path}]"))
                except Exception as e:
                    logger.error(f"Failed to read image file {image_path}: {e}")
                    parts.append(Part(text=f"[Error reading image file: {str(e)}]"))
            else:
                # External URL, fetch via HTTP
                import httpx
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(request.image_url)
                        if resp.status_code == 200:
                            image_bytes = resp.content
                            mime_type = resp.headers.get("content-type", "image/jpeg")
                            parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))
                            logger.info(f"Fetched external image via HTTP: {request.image_url}")
                        else:
                            logger.warning(f"Failed to fetch image: Status {resp.status_code}")
                            parts.append(Part(text=f"[Failed to fetch image: {resp.status_code}]"))
                except Exception as e:
                    logger.warning(f"Failed to fetch image from {request.image_url}: {e}")
                    parts.append(Part(text=f"[Image loading failed: {str(e)}]"))

        return Content(role="user", parts=parts)

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
        title = self._derive_session_title(request.text)
        await self._record_session(user_id, session_id, title=title)

        # Create capture if input provided (Text only for now as auto-capture)
        capture_id = None
        if request.text:
            capture = await self._capture_repo.create(
                user_id,
                CaptureCreate(
                    content_type=ContentType.TEXT,
                    raw_text=request.text,
                ),
            )
            capture_id = capture.id

        # Get or create runner
        runner = self._get_or_create_runner(user_id)

        # Run agent with user message
        try:
            user_message_text = self._get_user_message_text(request)
            if user_message_text:
                await self._record_message(
                    user_id=user_id,
                    session_id=session_id,
                    role="user",
                    content=user_message_text,
                    title=title,
                )
            new_message = await self._construct_user_message(request)

            # Ensure session exists
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

            await self._record_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=assistant_message,
            )

            return ChatResponse(
                assistant_message=assistant_message,
                related_tasks=[],
                suggested_actions=[],
                session_id=session_id,
                capture_id=capture_id,
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            await self._record_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=f"Error: {str(e)}",
            )
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
        """
        # Generate session ID if not provided
        session_id_str = session_id or str(uuid4())
        title = self._derive_session_title(request.text)
        await self._record_session(user_id, session_id_str, title=title)

        # Create capture if input provided
        capture_id = None
        if request.text:
            capture = await self._capture_repo.create(
                user_id,
                CaptureCreate(
                    content_type=ContentType.TEXT,
                    raw_text=request.text,
                ),
            )
            capture_id = capture.id

        # Get or create runner
        runner = self._get_or_create_runner(user_id)

        try:
            user_message_text = self._get_user_message_text(request)
            if user_message_text:
                await self._record_message(
                    user_id=user_id,
                    session_id=session_id_str,
                    role="user",
                    content=user_message_text,
                    title=title,
                )
            new_message = await self._construct_user_message(request)

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
                # ... (Tool handling logic remains same as original) ...
                
                # Check for function_call in part
                if event.content and hasattr(event.content, "parts") and event.content.parts:
                    for part in event.content.parts:
                        func_call = getattr(part, "function_call", None)
                        if func_call:
                            yield {
                                "chunk_type": "tool_start",
                                "tool_name": func_call.name if hasattr(func_call, "name") else "unknown",
                                "tool_args": dict(func_call.args) if hasattr(func_call, "args") else {},
                            }

                        func_response = getattr(part, "function_response", None)
                        if func_response:
                            yield {
                                "chunk_type": "tool_end",
                                "tool_name": func_response.name if hasattr(func_response, "name") else "unknown",
                                "tool_result": str(func_response.response) if hasattr(func_response, "response") else "",
                            }

                        text = getattr(part, "text", None)
                        if text:
                            assistant_message_parts.append(text)
                            for char in text:
                                yield {
                                    "chunk_type": "text",
                                    "content": char,
                                }

            # Final message
            assistant_message = "".join(assistant_message_parts).strip()
            if not assistant_message:
                assistant_message = "（応答が空でした。もう一度試してみてください）"

            await self._record_message(
                user_id=user_id,
                session_id=session_id_str,
                role="assistant",
                content=assistant_message,
            )

            yield {
                "chunk_type": "done",
                "assistant_message": assistant_message,
                "session_id": session_id_str,
                "capture_id": str(capture_id) if capture_id else None,
            }

        except Exception as e:
            logger.error(f"Agent streaming failed: {e}", exc_info=True)
            await self._record_message(
                user_id=user_id,
                session_id=session_id_str,
                role="assistant",
                content=f"Error: {str(e)}",
            )
            yield {
                "chunk_type": "error",
                "content": f"申し訳ございません。エラーが発生しました: {str(e)}",
            }

    async def analyze_capture(
        self,
        user_id: str,
        capture_id: str,
    ) -> dict[str, Any]:
        """
        Analyze a capture using the Secretary Agent persona.
        """
        from google import genai
        from google.genai.types import GenerateContentConfig
        import json
        from app.agents.prompts.secretary_prompt import SECRETARY_SYSTEM_PROMPT

        capture = await self._capture_repo.get(user_id, capture_id)
        if not capture:
            raise ValueError(f"Capture {capture_id} not found")

        # Construct prompt embedding the Secretary Persona
        # We perform a "stateless" execution here using the same model and system prompt
        # to ensure consistency without managing a full session state for this one-off analysis.
        
        system_instruction = SECRETARY_SYSTEM_PROMPT
        
        prompt_text = "Analyze the following captured content and extract a Task.\n"
        prompt_text += "Output MUST be a valid JSON object with 'title', 'description', 'importance', 'urgency', 'estimated_minutes', and 'due_date' (if found).\n"
        
        parts = [Part(text=prompt_text)]

        # Add capture content
        if capture.content_type == ContentType.TEXT:
            try:
                data = json.loads(capture.raw_text)
                if isinstance(data, dict):
                    parts.append(Part(text=f"Metadata: {json.dumps(data, indent=2)}"))
                else:
                    parts.append(Part(text=f"Text Content:\n{capture.raw_text}"))
            except:
                parts.append(Part(text=f"Text Content:\n{capture.raw_text}"))

        elif capture.content_type == ContentType.IMAGE and capture.content_url:
            import mimetypes

            image_bytes = None
            mime_type = "image/jpeg"
            image_path = None
            settings = get_settings()
            storage_prefix = f"{settings.BASE_URL}/storage/"

            if capture.content_url.startswith(storage_prefix):
                relative_path = capture.content_url[len(storage_prefix):]
                abs_storage_path = Path(settings.STORAGE_BASE_PATH).absolute()
                image_path = abs_storage_path / relative_path
            elif capture.content_url.startswith("file://"):
                local_path_str = capture.content_url[7:]
                if local_path_str.startswith("/") and len(local_path_str) > 2 and local_path_str[2] == ":":
                    local_path_str = local_path_str[1:]
                image_path = Path(local_path_str)
            elif not capture.content_url.startswith(("http://", "https://")):
                candidate_path = Path(capture.content_url)
                if candidate_path.is_absolute():
                    image_path = candidate_path

            if image_path:
                try:
                    if image_path.exists():
                        image_bytes = image_path.read_bytes()
                        mime_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
                    else:
                        parts.append(Part(text=f"Image URL: {capture.content_url} (File not found)"))
                except Exception as e:
                    logger.warning(f"Failed to read image file {image_path}: {e}")
                    parts.append(Part(text=f"Image URL: {capture.content_url} (Failed to load)"))
            else:
                import httpx
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(capture.content_url)
                        if resp.status_code == 200:
                            image_bytes = resp.content
                            mime_type = resp.headers.get("content-type", "image/jpeg")
                        else:
                            parts.append(Part(text=f"Image URL: {capture.content_url} (Could not load)"))
                except Exception as e:
                    logger.warning(f"Failed to fetch image for analysis: {e}")
                    parts.append(Part(text=f"Image URL: {capture.content_url} (Failed to load)"))

            if image_bytes:
                parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))
        
        # Initialize Client provided by the settings
        api_key = self._llm_provider._settings.GOOGLE_API_KEY
        client = genai.Client(api_key=api_key)
        model_name = self._llm_provider.get_model()

        # Schema for structured output
        schema = {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Concise task title"},
                "description": {"type": "STRING", "description": "Detailed description or URL"},
                "importance": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "urgency": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "estimated_minutes": {"type": "INTEGER"},
                "due_date": {"type": "STRING", "description": "ISO 8601 format (YYYY-MM-DDTHH:MM:SS)"}
            },
            "required": ["title", "importance"]
        }

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[Content(role="user", parts=parts)],
                config=GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    system_instruction=system_instruction # Use Secretary Prompt
                )
            )
            
            if response.text:
                return json.loads(response.text)
            return {"title": "Failed to analyze", "description": "Empty response"}

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {
                "title": "Analysis Error",
                "description": f"Could not analyze capture: {str(e)}",
                "importance": "MEDIUM"
            }
