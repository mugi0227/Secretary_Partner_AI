"""
Agent Service for running the Secretary Agent with ADK Runner.

This service handles agent execution, tool calling, and response generation.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
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
from app.interfaces.speech_provider import ISpeechToTextProvider
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.capture import CaptureCreate
from app.models.chat import ChatRequest, ChatResponse, PendingQuestion, PendingQuestions
from app.models.enums import ContentType, ToolApprovalMode
from app.utils.datetime_utils import ensure_utc

# Global cache for runners (keyed by user_id + session_id + model + routing_mode)
# This allows session state to persist across requests
_runner_cache: dict[tuple[str, str, str, str], tuple[InMemoryRunner, bool]] = {}
_session_index: dict[str, dict[str, dict[str, Any]]] = {}


class AgentService:
    """Service for running the Secretary Agent."""

    APP_NAME = "nagi"
    HISTORY_SEED_LIMIT = 200
    PDF_TEXT_MAX_PAGES = 30
    PDF_TEXT_MAX_CHARS = 20000
    PDF_TEXT_MIN_CHARS = 240
    PDF_IMAGE_MAX_PAGES = 6
    PDF_IMAGE_RENDER_DPI = 130
    PDF_IMAGE_JPEG_QUALITY = 80
    PDF_IMAGE_MAX_TOTAL_BYTES = 8 * 1024 * 1024

    def __init__(
        self,
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
        capture_repo: ICaptureRepository,
        chat_repo: IChatSessionRepository,
        proposal_repo: IProposalRepository,
        checkin_repo: ICheckinRepository,
        recurring_meeting_repo: IRecurringMeetingRepository,
        recurring_task_repo: IRecurringTaskRepository,
        speech_provider: ISpeechToTextProvider | None = None,
        user_repo: IUserRepository | None = None,
    ):
        """
        Initialize Agent Service.

        Args:
            llm_provider: LLM provider
            task_repo: Task repository
            project_repo: Project repository
            project_member_repo: Project member repository
            project_invitation_repo: Project invitation repository
            task_assignment_repo: Task assignment repository
            memory_repo: Memory repository
            agent_task_repo: Agent task repository
            capture_repo: Capture repository
            chat_repo: Chat session repository
            proposal_repo: Proposal repository
            checkin_repo: Check-in repository
            user_repo: User repository (for resolving display names)
        """
        self._llm_provider = llm_provider
        self._task_repo = task_repo
        self._project_repo = project_repo
        self._phase_repo = phase_repo
        self._milestone_repo = milestone_repo
        self._project_member_repo = project_member_repo
        self._project_invitation_repo = project_invitation_repo
        self._task_assignment_repo = task_assignment_repo
        self._memory_repo = memory_repo
        self._agent_task_repo = agent_task_repo
        self._meeting_agenda_repo = meeting_agenda_repo
        self._capture_repo = capture_repo
        self._chat_repo = chat_repo
        self._proposal_repo = proposal_repo
        self._checkin_repo = checkin_repo
        self._recurring_meeting_repo = recurring_meeting_repo
        self._recurring_task_repo = recurring_task_repo
        self._speech_provider = speech_provider
        self._user_repo = user_repo

    def _resolve_llm_provider(self, model_id: str | None) -> ILLMProvider:
        """Resolve the effective LLM provider, optionally overriding the model."""
        if not model_id:
            return self._llm_provider
        return self._llm_provider.with_model(model_id)

    async def _get_or_create_runner(
        self,
        user_id: str,
        session_id: str,
        auto_approve: bool = True,
        allow_auto_approve_mismatch: bool = False,
        model_id: str | None = None,
        routing_message: str | None = None,
        routing_context: dict[str, Any] | None = None,
    ) -> InMemoryRunner:
        """Get cached runner or create a new one for the user.

        Note: All tools are now proposal-based, but auto_approve determines
        whether proposals are automatically approved or require user confirmation.
        """
        routing_mode = ""
        if isinstance(routing_context, dict):
            routing_mode = str(routing_context.get("extension_agent_mode") or "").strip().lower()
        use_cache = not (routing_message or "").strip() and not routing_mode
        effective_model_key = model_id or "default"
        cache_key = (user_id, session_id, effective_model_key, routing_mode or "default")

        if use_cache:
            cached = _runner_cache.get(cache_key)
            if cached:
                runner, cached_auto_approve = cached
                if cached_auto_approve == auto_approve or allow_auto_approve_mismatch:
                    return runner

        effective_provider = self._resolve_llm_provider(model_id)
        agent = await create_secretary_agent(
            llm_provider=effective_provider,
            task_repo=self._task_repo,
            project_repo=self._project_repo,
            phase_repo=self._phase_repo,
            milestone_repo=self._milestone_repo,
            project_member_repo=self._project_member_repo,
            project_invitation_repo=self._project_invitation_repo,
            task_assignment_repo=self._task_assignment_repo,
            memory_repo=self._memory_repo,
            agent_task_repo=self._agent_task_repo,
            meeting_agenda_repo=self._meeting_agenda_repo,
            recurring_meeting_repo=self._recurring_meeting_repo,
            recurring_task_repo=self._recurring_task_repo,
            checkin_repo=self._checkin_repo,
            user_id=user_id,
            proposal_repo=self._proposal_repo,
            session_id=session_id,
            auto_approve=auto_approve,
            user_repo=self._user_repo,
            user_message=routing_message,
            routing_context=routing_context,
        )

        runner = InMemoryRunner(agent=agent, app_name=self.APP_NAME)
        if use_cache:
            _runner_cache[cache_key] = (runner, auto_approve)
        return runner

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

    def _resolve_auto_approve(self, request: ChatRequest) -> bool:
        if request.approval_mode:
            return request.approval_mode == ToolApprovalMode.AUTO
        return not request.proposal_mode

    def _get_user_message_text(self, request: ChatRequest) -> str:
        """Get a storable user message text."""
        if request.text:
            return request.text
        if request.audio_base64 or request.audio_url:
            return "[Voice input]"
        if request.image_base64 or request.image_url:
            return "[Image attached]"
        if request.file_base64 or request.file_url:
            file_name = (request.file_name or "").strip()
            return f"[File attached: {file_name}]" if file_name else "[File attached]"
        return ""

    async def _ensure_session(
        self,
        runner: InMemoryRunner,
        user_id: str,
        session_id: str,
    ):
        """Ensure session exists in the runner session service."""
        existing = await runner.session_service.get_session(
            app_name=self.APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if existing is None:
            return await runner.session_service.create_session(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        return existing

    async def _hydrate_session_history(
        self,
        runner: InMemoryRunner,
        user_id: str,
        session_id: str,
    ) -> None:
        """Seed ADK session history from persisted chat messages after restart."""
        if not self._chat_repo:
            return

        try:
            session = await runner.session_service.get_session(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            if session and getattr(session, "events", None):
                if session.events:
                    return

            if session is None:
                session = await runner.session_service.create_session(
                    app_name=self.APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )

            stored_messages = await self._chat_repo.list_messages(
                user_id=user_id,
                session_id=session_id,
                limit=self.HISTORY_SEED_LIMIT,
            )
            if not stored_messages:
                return

            from google.adk.events.event import Event
            from google.genai.types import Content, Part

            agent_name = getattr(getattr(runner, "agent", None), "name", None) or "assistant"
            for idx, msg in enumerate(stored_messages):
                if msg.role not in {"user", "assistant"}:
                    continue
                content_text = msg.content or ""
                if not content_text.strip():
                    continue
                author = "user" if msg.role == "user" else agent_name
                role = "user" if msg.role == "user" else "model"
                event = Event(
                    author=author,
                    invocation_id=f"history:{session_id}:{idx}",
                    content=Content(role=role, parts=[Part(text=content_text)]),
                )
                await runner.session_service.append_event(session, event)
        except Exception as exc:
            logger.warning(f"Failed to hydrate session history for {session_id}: {exc}")

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
        runner = await self._get_or_create_runner(
            user_id,
            session_id="system",
            auto_approve=True,
            allow_auto_approve_mismatch=True,
        )
        if self._chat_repo:
            stored_sessions = await self._chat_repo.list_sessions(user_id=user_id)
            if stored_sessions:
                result = []
                for session in stored_sessions:
                    entry = {
                        "session_id": session.session_id,
                        "title": session.title or "New Chat",
                        "updated_at": ensure_utc(session.updated_at).isoformat() if session.updated_at else None,
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
        runner = await self._get_or_create_runner(
            user_id,
            session_id=session_id,
            auto_approve=True,
            allow_auto_approve_mismatch=True,
        )
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
                            "created_at": ensure_utc(msg.created_at).isoformat() if msg.created_at else None,
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
                "created_at": ensure_utc(msg.created_at).isoformat() if hasattr(msg, "created_at") and msg.created_at else None
            })
        return result

    async def _analyze_image_if_available(
        self,
        image_bytes: bytes,
        mime_type: str,
        user_text: str | None,
    ) -> str:
        """
        Analyze image using vision model if configured.

        Only works when LLM_PROVIDER=litellm and LITELLM_VISION_MODEL is set.

        Args:
            image_bytes: Raw image bytes
            mime_type: MIME type of the image
            user_text: User's text prompt (for context)

        Returns:
            Vision model's description of the image, or empty string if not available
        """
        # Check if LiteLLMProvider with vision model is being used
        from app.infrastructure.local.litellm_provider import LiteLLMProvider

        if not isinstance(self._llm_provider, LiteLLMProvider):
            return ""

        if not self._llm_provider.has_vision_model():
            return ""

        # Build prompt for vision model
        prompt = "この画像の内容を詳しく説明してください。"
        if user_text:
            prompt = f"ユーザーのメッセージ: {user_text}\n\n上記を踏まえて、この画像の内容を詳しく説明してください。タスクやメモとして重要な情報があれば、それも含めてください。"

        return await self._llm_provider.analyze_image(image_bytes, mime_type, prompt)

    async def _read_file_bytes_from_url(
        self,
        file_url: str,
    ) -> tuple[bytes | None, str | None, str | None]:
        """
        Read file bytes from storage/file/http URL.

        Returns:
            (bytes, mime_type, error_message)
        """
        import mimetypes

        settings = get_settings()
        storage_prefix = f"{settings.BASE_URL}/storage/"

        file_path = None
        if file_url.startswith(storage_prefix):
            relative_path = file_url[len(storage_prefix):]
            abs_storage_path = Path(settings.STORAGE_BASE_PATH).absolute()
            file_path = abs_storage_path / relative_path
        elif file_url.startswith("file://"):
            local_path_str = file_url[7:]
            if local_path_str.startswith("/") and len(local_path_str) > 2 and local_path_str[2] == ":":
                local_path_str = local_path_str[1:]
            file_path = Path(local_path_str)
        elif not file_url.startswith(("http://", "https://")):
            candidate_path = Path(file_url)
            if candidate_path.is_absolute():
                file_path = candidate_path

        if file_path:
            try:
                if not file_path.exists():
                    return None, None, f"File not found: {file_path}"
                file_bytes = file_path.read_bytes()
                mime_type, _ = mimetypes.guess_type(str(file_path))
                return file_bytes, mime_type or "application/octet-stream", None
            except Exception as e:
                return None, None, f"Failed to read file: {e}"

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(file_url)
                if resp.status_code != 200:
                    return None, None, f"Failed to fetch file: HTTP {resp.status_code}"
                mime_type = resp.headers.get("content-type", "").split(";")[0].strip()
                return resp.content, (mime_type or "application/octet-stream"), None
        except Exception as e:
            return None, None, f"Failed to fetch file: {e}"

    def _decode_data_url(
        self,
        data_url: str,
        fallback_mime_type: str = "application/octet-stream",
    ) -> tuple[bytes | None, str]:
        import base64

        if not data_url:
            return None, fallback_mime_type

        raw = data_url.strip()
        mime_type = fallback_mime_type
        encoded = raw

        if raw.startswith("data:"):
            if "," not in raw:
                return None, fallback_mime_type
            header, encoded_part = raw.split(",", 1)
            encoded = encoded_part

            metadata = header[5:]  # strip "data:"
            segments = [segment.strip() for segment in metadata.split(";") if segment.strip()]
            if segments:
                mime_candidate = segments[0].lower()
                if "/" in mime_candidate:
                    mime_type = mime_candidate
            is_base64 = any(segment.lower() == "base64" for segment in segments[1:])
            if not is_base64:
                return None, mime_type

        try:
            return base64.b64decode(encoded), mime_type
        except Exception:
            return None, mime_type

    def _normalize_speech_language(self, language_hint: str | None) -> str:
        raw = (language_hint or "").strip()
        if not raw:
            return "ja-JP"

        normalized = raw.replace("_", "-")
        lower = normalized.lower()
        language_map = {
            "ja": "ja-JP",
            "en": "en-US",
            "ko": "ko-KR",
            "zh": "zh-CN",
            "fr": "fr-FR",
            "de": "de-DE",
            "es": "es-ES",
            "it": "it-IT",
            "pt": "pt-BR",
        }
        return language_map.get(lower, normalized)

    async def _transcribe_request_audio(
        self,
        request: ChatRequest,
    ) -> str | None:
        if not request.audio_base64 and not request.audio_url:
            return None
        if not self._speech_provider:
            logger.warning("Audio input received but speech provider is not configured")
            return None

        mime_hint = (request.audio_mime_type or "audio/webm").strip().lower()
        audio_bytes: bytes | None = None
        mime_type = mime_hint

        if request.audio_base64:
            audio_bytes, parsed_mime_type = self._decode_data_url(request.audio_base64, mime_hint)
            mime_type = parsed_mime_type or mime_hint
        elif request.audio_url:
            loaded_bytes, loaded_mime_type, load_error = await self._read_file_bytes_from_url(request.audio_url)
            if load_error:
                logger.warning(f"Failed to load audio_url for transcription: {load_error}")
                return None
            audio_bytes = loaded_bytes
            if loaded_mime_type:
                mime_type = loaded_mime_type

        if not audio_bytes:
            logger.warning("Audio transcription skipped because decoded audio bytes are empty")
            return None

        language = self._normalize_speech_language(request.audio_language)
        try:
            transcript = await self._speech_provider.transcribe_bytes(
                audio_bytes=audio_bytes,
                content_type=mime_type,
                language=language,
            )
        except Exception as e:
            logger.warning(f"Audio transcription failed: {e}")
            return None

        transcript = (transcript or "").strip()
        return transcript or None

    async def _extract_pdf_text_layer(
        self,
        pdf_bytes: bytes,
    ) -> tuple[str, dict[str, Any]]:
        """
        Extract PDF text layer and evaluate if it's sufficient.

        Returns:
            (text, metadata)
            metadata keys: status, reason, page_count, extracted_chars
        """
        import re
        from io import BytesIO

        if not pdf_bytes:
            return "", {
                "status": "insufficient",
                "reason": "empty_pdf_bytes",
                "page_count": 0,
                "extracted_chars": 0,
            }

        try:
            from pypdf import PdfReader
        except Exception:
            return "", {
                "status": "insufficient",
                "reason": "pypdf_not_available",
                "page_count": 0,
                "extracted_chars": 0,
            }

        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            page_count = len(reader.pages)
            limited_pages = reader.pages[: self.PDF_TEXT_MAX_PAGES]
            chunks: list[str] = []

            for idx, page in enumerate(limited_pages):
                page_text = ""
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""

                page_text = page_text.strip()
                if not page_text:
                    continue
                chunks.append(f"[Page {idx + 1}]\n{page_text}")

            text = "\n\n".join(chunks)
            if len(text) > self.PDF_TEXT_MAX_CHARS:
                text = text[: self.PDF_TEXT_MAX_CHARS]

            non_ws_chars = len(re.sub(r"\s+", "", text))
            if non_ws_chars >= self.PDF_TEXT_MIN_CHARS:
                return text, {
                    "status": "sufficient",
                    "reason": "ok",
                    "page_count": page_count,
                    "extracted_chars": non_ws_chars,
                }

            reason = "text_too_short_or_scanned_pdf"
            if not text:
                reason = "no_text_layer"

            return text, {
                "status": "insufficient",
                "reason": reason,
                "page_count": page_count,
                "extracted_chars": non_ws_chars,
            }
        except Exception as e:
            logger.warning(f"PDF text extraction failed: {e}")
            return "", {
                "status": "insufficient",
                "reason": "pdf_parse_failed",
                "page_count": 0,
                "extracted_chars": 0,
            }

    async def _render_pdf_pages_as_images(
        self,
        pdf_bytes: bytes,
    ) -> tuple[list[tuple[int, bytes, str]], dict[str, Any]]:
        """
        Render PDF pages into compressed JPEG images for OCR fallback.

        Returns:
            (rendered_pages, metadata)
            rendered_pages: [(page_number_1based, image_bytes, mime_type), ...]
            metadata keys: status, reason, page_count, rendered_pages, total_image_bytes, truncated
        """
        if not pdf_bytes:
            return [], {
                "status": "failed",
                "reason": "empty_pdf_bytes",
                "page_count": 0,
                "rendered_pages": 0,
                "total_image_bytes": 0,
                "truncated": False,
            }

        try:
            import fitz  # type: ignore
        except Exception:
            return [], {
                "status": "failed",
                "reason": "pymupdf_not_available",
                "page_count": 0,
                "rendered_pages": 0,
                "total_image_bytes": 0,
                "truncated": False,
            }

        rendered: list[tuple[int, bytes, str]] = []
        total_image_bytes = 0
        truncated = False
        page_count = 0

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = doc.page_count
            max_pages = min(page_count, self.PDF_IMAGE_MAX_PAGES)
            scale = max(self.PDF_IMAGE_RENDER_DPI / 72.0, 0.1)
            matrix = fitz.Matrix(scale, scale)

            for page_index in range(max_pages):
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                image_bytes = pix.tobytes("jpeg", jpg_quality=self.PDF_IMAGE_JPEG_QUALITY)
                if not image_bytes:
                    continue

                if total_image_bytes + len(image_bytes) > self.PDF_IMAGE_MAX_TOTAL_BYTES:
                    truncated = True
                    break

                rendered.append((page_index + 1, image_bytes, "image/jpeg"))
                total_image_bytes += len(image_bytes)

            if page_count > max_pages:
                truncated = True

            doc.close()
        except Exception as e:
            logger.warning(f"PDF page rendering failed: {e}")
            return [], {
                "status": "failed",
                "reason": "pdf_render_failed",
                "page_count": page_count,
                "rendered_pages": 0,
                "total_image_bytes": 0,
                "truncated": False,
            }

        return rendered, {
            "status": "ok" if rendered else "failed",
            "reason": "ok" if rendered else "no_rendered_pages",
            "page_count": page_count,
            "rendered_pages": len(rendered),
            "total_image_bytes": total_image_bytes,
            "truncated": truncated,
        }

    async def _construct_user_message(
        self,
        request: ChatRequest,
        audio_transcription: str | None = None,
    ) -> Content:
        """Construct multimodal user message.

        If LITELLM_VISION_MODEL is configured and image is present,
        the image is sent to the vision model first, and its description
        is added to the message instead of the raw image.
        """
        parts = []

        # Inject project context if provided from project detail page
        if request.context and request.context.get("project_id"):
            project_id = request.context["project_id"]
            project_name = request.context.get("project_name", "Unknown")
            context_preamble = (
                f"[自動コンテキスト] ユーザーは現在プロジェクト「{project_name}」"
                f"（ID: {project_id}）を閲覧中です。"
                f"このプロジェクトに関連する作業として扱ってください。"
                f"ただし、ユーザーの発言が明らかにこのプロジェクトと無関係な場合は、"
                f"プロジェクトスコープを無視して構いません。"
            )
            parts.append(Part(text=context_preamble))

        if request.text:
            parts.append(Part(text=request.text))
        if audio_transcription:
            if request.text:
                parts.append(Part(text=f"[音声文字起こし]\n{audio_transcription}"))
            else:
                parts.append(Part(text=audio_transcription))
        elif request.audio_base64 or request.audio_url:
            parts.append(Part(text="[音声入力がありましたが文字起こしできませんでした]"))

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

                    # Check if we should use separate vision model
                    vision_description = await self._analyze_image_if_available(
                        image_bytes, mime_type, request.text
                    )

                    if vision_description:
                        # Use vision model's description instead of raw image
                        parts.append(Part(text=f"\n\n[画像の内容（Vision Model解析結果）]\n{vision_description}"))
                        logger.info("Used vision model for image analysis")
                    else:
                        # Send raw image to main model
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

                        # Check if we should use separate vision model
                        vision_description = await self._analyze_image_if_available(
                            image_bytes, mime_type, request.text
                        )

                        if vision_description:
                            parts.append(Part(text=f"\n\n[画像の内容（Vision Model解析結果）]\n{vision_description}"))
                            logger.info("Used vision model for local image analysis")
                        else:
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

                            # Check if we should use separate vision model
                            vision_description = await self._analyze_image_if_available(
                                image_bytes, mime_type, request.text
                            )

                            if vision_description:
                                parts.append(Part(text=f"\n\n[画像の内容（Vision Model解析結果）]\n{vision_description}"))
                                logger.info("Used vision model for external image analysis")
                            else:
                                parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))
                                logger.info(f"Fetched external image via HTTP: {request.image_url}")
                        else:
                            logger.warning(f"Failed to fetch image: Status {resp.status_code}")
                            parts.append(Part(text=f"[Failed to fetch image: {resp.status_code}]"))
                except Exception as e:
                    logger.warning(f"Failed to fetch image from {request.image_url}: {e}")
                    parts.append(Part(text=f"[Image loading failed: {str(e)}]"))

        if request.file_base64 or request.file_url:
            import base64
            import re
            from urllib.parse import urlparse

            file_bytes = None
            file_mime_type = (request.file_mime_type or "").strip().lower()
            file_name = (request.file_name or "").strip()
            if not file_name and request.file_url:
                try:
                    parsed = urlparse(request.file_url)
                    candidate_name = Path(parsed.path).name
                    if candidate_name:
                        file_name = candidate_name
                except Exception:
                    file_name = file_name or ""

            if request.file_base64:
                encoded = ""
                match = re.match(r"data:([^;]+);base64,(.+)", request.file_base64)
                if match:
                    parsed_mime_type = match.group(1).strip().lower()
                    encoded = match.group(2)
                    if parsed_mime_type and not file_mime_type:
                        file_mime_type = parsed_mime_type
                else:
                    encoded = request.file_base64

                try:
                    file_bytes = base64.b64decode(encoded)
                except Exception as e:
                    logger.warning(f"Failed to decode file attachment: {e}")
                    parts.append(Part(text=f"[File decoding failed: {e}]"))

            elif request.file_url:
                loaded_bytes, loaded_mime_type, load_error = await self._read_file_bytes_from_url(
                    request.file_url
                )
                if load_error:
                    logger.warning(f"Failed to load file from URL: {load_error}")
                    parts.append(Part(text=f"[File loading failed: {load_error}]"))
                else:
                    file_bytes = loaded_bytes
                    if loaded_mime_type and not file_mime_type:
                        file_mime_type = loaded_mime_type

            if file_bytes:
                file_mime_type = (
                    (file_mime_type.split(";")[0].strip().lower())
                    if file_mime_type
                    else "application/octet-stream"
                )
                is_pdf = (
                    file_mime_type == "application/pdf"
                    or file_name.lower().endswith(".pdf")
                )

                if file_mime_type.startswith("image/"):
                    vision_description = await self._analyze_image_if_available(
                        file_bytes, file_mime_type, request.text
                    )
                    if vision_description:
                        parts.append(Part(text=f"\n\n[Image analysis]\n{vision_description}"))
                    else:
                        parts.append(Part.from_bytes(data=file_bytes, mime_type=file_mime_type))
                elif is_pdf:
                    extracted_text, pdf_meta = await self._extract_pdf_text_layer(file_bytes)
                    status = str(pdf_meta.get("status") or "insufficient")
                    reason = str(pdf_meta.get("reason") or "unknown")
                    page_count = int(pdf_meta.get("page_count") or 0)
                    extracted_chars = int(pdf_meta.get("extracted_chars") or 0)

                    if status == "sufficient" and extracted_text:
                        header = (
                            "[PDF text extraction]\n"
                            f"file_name: {file_name or 'attached.pdf'}\n"
                            f"page_count: {page_count}\n"
                            f"extracted_chars: {extracted_chars}\n"
                            "Use the extracted text below as the primary source."
                        )
                        parts.append(Part(text=header))
                        parts.append(Part(text=f"[PDF extracted text]\n{extracted_text}"))
                    else:
                        rendered_pages, render_meta = await self._render_pdf_pages_as_images(file_bytes)
                        rendered_count = int(render_meta.get("rendered_pages") or 0)
                        rendered_bytes = int(render_meta.get("total_image_bytes") or 0)
                        render_reason = str(render_meta.get("reason") or "unknown")
                        truncated = bool(render_meta.get("truncated"))

                        fallback_header = (
                            "[PDF text extraction: INSUFFICIENT]\n"
                            f"file_name: {file_name or 'attached.pdf'}\n"
                            f"page_count: {page_count}\n"
                            f"extracted_chars: {extracted_chars}\n"
                            f"text_reason: {reason}\n"
                            f"auto_image_fallback_pages: {rendered_count}\n"
                            f"auto_image_fallback_bytes: {rendered_bytes}\n"
                            f"auto_image_fallback_truncated: {truncated}\n"
                            "Use the following rendered PDF page images as OCR source.\n"
                            "Do not fabricate invoice fields."
                        )
                        parts.append(Part(text=fallback_header))
                        if extracted_text:
                            parts.append(Part(text=f"[PDF partial extracted text]\n{extracted_text}"))

                        if rendered_pages:
                            for page_no, image_bytes, image_mime in rendered_pages:
                                parts.append(Part(text=f"[PDF page image]\npage: {page_no}"))
                                parts.append(Part.from_bytes(data=image_bytes, mime_type=image_mime))
                        else:
                            parts.append(
                                Part(
                                    text=(
                                        "[PDF image fallback failed]\n"
                                        f"reason: {render_reason}\n"
                                        "Unable to render page images from this PDF."
                                    )
                                )
                            )
                else:
                    try:
                        parts.append(Part.from_bytes(data=file_bytes, mime_type=file_mime_type))
                        if file_name:
                            parts.append(Part(text=f"[Attached file: {file_name} ({file_mime_type})]"))
                    except Exception as e:
                        logger.warning(f"Failed to attach file bytes ({file_mime_type}): {e}")
                        fallback_name = file_name or "attached-file"
                        parts.append(Part(text=f"[Attached file: {fallback_name} ({file_mime_type})]"))

        return Content(role="user", parts=parts)

    @staticmethod
    def _normalize_tool_response(raw_response: Any) -> dict[str, Any] | None:
        if raw_response is None:
            return None
        if isinstance(raw_response, dict):
            return raw_response
        if isinstance(raw_response, Mapping):
            try:
                parsed_mapping = dict(raw_response)
            except Exception:
                parsed_mapping = None
            if isinstance(parsed_mapping, dict):
                return parsed_mapping
        if isinstance(raw_response, str):
            raw = raw_response.strip()
            if not raw:
                return None
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    literal = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    return None
                return literal if isinstance(literal, dict) else None
            return parsed if isinstance(parsed, dict) else None
        if hasattr(raw_response, "to_dict"):
            try:
                parsed = raw_response.to_dict()
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        if hasattr(raw_response, "model_dump"):
            try:
                parsed = raw_response.model_dump(mode="json")
            except Exception:
                parsed = raw_response.model_dump()
            return parsed if isinstance(parsed, dict) else None
        return None

    @staticmethod
    def _extract_pending_questions_payload(raw_response: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(raw_response, dict):
            return None

        stack: list[dict[str, Any]] = [raw_response]
        seen: set[int] = set()
        while stack:
            current = stack.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)

            status = current.get("status")
            questions = current.get("questions")
            if status == "awaiting_response" and isinstance(questions, list):
                return current

            nested_keys = ("result", "response", "data", "output", "tool_result")
            for key in nested_keys:
                nested = current.get(key)
                if isinstance(nested, dict):
                    stack.append(nested)

            for value in current.values():
                if isinstance(value, dict):
                    stack.append(value)
        return None

    @classmethod
    def _parse_pending_questions(
        cls, raw_response: dict[str, Any] | None
    ) -> PendingQuestions | None:
        payload = cls._extract_pending_questions_payload(raw_response)
        if not payload:
            return None
        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            return None

        questions: list[PendingQuestion] = []
        for index, raw_question in enumerate(raw_questions):
            if not isinstance(raw_question, dict):
                continue

            question_text_raw = raw_question.get("question")
            if not isinstance(question_text_raw, str):
                continue
            question_text = question_text_raw.strip()
            if not question_text:
                continue

            question_id_raw = raw_question.get("id")
            question_id = str(question_id_raw).strip() if question_id_raw is not None else ""
            if not question_id:
                question_id = f"q_{index + 1}"

            raw_options = raw_question.get("options")
            options = (
                [option.strip() for option in raw_options if isinstance(option, str) and option.strip()]
                if isinstance(raw_options, list)
                else []
            )

            placeholder_raw = raw_question.get("placeholder")
            placeholder = (
                placeholder_raw.strip()
                if isinstance(placeholder_raw, str) and placeholder_raw.strip()
                else None
            )

            questions.append(
                PendingQuestion(
                    id=question_id,
                    question=question_text,
                    options=options,
                    allow_multiple=bool(raw_question.get("allow_multiple", False)),
                    placeholder=placeholder,
                )
            )

        if not questions:
            return None

        context_raw = payload.get("context")
        context = context_raw.strip() if isinstance(context_raw, str) and context_raw.strip() else None
        return PendingQuestions(questions=questions, context=context)

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

        audio_transcription = await self._transcribe_request_audio(request)

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
        elif audio_transcription:
            capture = await self._capture_repo.create(
                user_id,
                CaptureCreate(
                    content_type=ContentType.AUDIO,
                    transcription=audio_transcription,
                ),
            )
            capture_id = capture.id

        user_message_text = request.text or audio_transcription or self._get_user_message_text(request)

        runner = await self._get_or_create_runner(
            user_id,
            session_id=session_id,
            auto_approve=self._resolve_auto_approve(request),
            model_id=request.model,
            routing_message=user_message_text,
            routing_context=request.context,
        )

        # Run agent with user message
        try:
            await self._ensure_session(runner, user_id, session_id)
            await self._hydrate_session_history(runner, user_id, session_id)

            if user_message_text:
                await self._record_message(
                    user_id=user_id,
                    session_id=session_id,
                    role="user",
                    content=user_message_text,
                    title=title,
                )
            new_message = await self._construct_user_message(
                request=request,
                audio_transcription=audio_transcription,
            )

            assistant_message_parts: list[str] = []
            pending_questions: PendingQuestions | None = None
            total_input_tokens = 0
            total_output_tokens = 0
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                if hasattr(event, "usage_metadata") and event.usage_metadata:
                    total_input_tokens += event.usage_metadata.prompt_token_count or 0
                    total_output_tokens += event.usage_metadata.candidates_token_count or 0
                if not event.content or not getattr(event.content, "parts", None):
                    continue
                for part in event.content.parts or []:
                    text = getattr(part, "text", None)
                    if text:
                        assistant_message_parts.append(text)
                    func_response = getattr(part, "function_response", None)
                    if not func_response:
                        continue
                    raw_response = (
                        func_response.response if hasattr(func_response, "response") else None
                    )
                    parsed_response = self._normalize_tool_response(raw_response)
                    parsed_pending_questions = self._parse_pending_questions(parsed_response)
                    if parsed_pending_questions:
                        pending_questions = parsed_pending_questions

            assistant_message = "".join(assistant_message_parts).strip()
            if not assistant_message:
                if pending_questions:
                    assistant_message = "I have follow-up questions. Please answer them to continue."
                else:
                    assistant_message = "（応答が空でした。もう一度試してみてください）"

            await self._record_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=assistant_message,
            )

            usage = None
            if total_input_tokens > 0 or total_output_tokens > 0:
                from app.models.chat import TokenUsage
                from app.services.cost_utils import calculate_cost

                model_id = self._resolve_llm_provider(request.model).get_model_id()
                usage = TokenUsage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_tokens=total_input_tokens + total_output_tokens,
                    cost_usd=calculate_cost(model_id, total_input_tokens, total_output_tokens),
                    model=model_id,
                )

            return ChatResponse(
                assistant_message=assistant_message,
                related_tasks=[],
                suggested_actions=[],
                session_id=session_id,
                capture_id=capture_id,
                pending_questions=pending_questions,
                usage=usage,
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
        audio_transcription = await self._transcribe_request_audio(request)

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
        elif audio_transcription:
            capture = await self._capture_repo.create(
                user_id,
                CaptureCreate(
                    content_type=ContentType.AUDIO,
                    transcription=audio_transcription,
                ),
            )
            capture_id = capture.id

        user_message_text = request.text or audio_transcription or self._get_user_message_text(request)

        runner = await self._get_or_create_runner(
            user_id,
            session_id=session_id_str,
            auto_approve=self._resolve_auto_approve(request),
            model_id=request.model,
            routing_message=user_message_text,
            routing_context=request.context,
        )

        try:
            await self._ensure_session(runner, user_id, session_id_str)
            await self._hydrate_session_history(runner, user_id, session_id_str)

            if user_message_text:
                await self._record_message(
                    user_id=user_id,
                    session_id=session_id_str,
                    role="user",
                    content=user_message_text,
                    title=title,
                )
            new_message = await self._construct_user_message(
                request=request,
                audio_transcription=audio_transcription,
            )

            # Stream agent execution
            assistant_message_parts: list[str] = []
            total_input_tokens = 0
            total_output_tokens = 0
            # FIFO queue per tool name to correlate tool_start with tool_end
            _pending_tool_ids: dict[str, list[str]] = {}
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id_str,
                new_message=new_message,
            ):
                # Accumulate token usage from each event
                if hasattr(event, "usage_metadata") and event.usage_metadata:
                    total_input_tokens += event.usage_metadata.prompt_token_count or 0
                    total_output_tokens += event.usage_metadata.candidates_token_count or 0

                # ... (Tool handling logic remains same as original) ...

                # Check for function_call in part
                if event.content and hasattr(event.content, "parts") and event.content.parts:
                    for part in event.content.parts:
                        func_call = getattr(part, "function_call", None)
                        if func_call:
                            tool_call_id = str(uuid4())
                            fc_name = func_call.name if hasattr(func_call, "name") else "unknown"
                            _pending_tool_ids.setdefault(fc_name, []).append(tool_call_id)
                            yield {
                                "chunk_type": "tool_start",
                                "tool_name": fc_name,
                                "tool_call_id": tool_call_id,
                                "tool_args": dict(func_call.args) if hasattr(func_call, "args") else {},
                            }

                        func_response = getattr(part, "function_response", None)
                        if func_response:
                            tool_name = func_response.name if hasattr(func_response, "name") else "unknown"
                            raw_response = func_response.response if hasattr(func_response, "response") else None
                            tool_result_str = ""
                            result = None

                            # Pop the matching tool_call_id from the FIFO queue
                            pending = _pending_tool_ids.get(tool_name, [])
                            resp_tool_call_id = pending.pop(0) if pending else None

                            if raw_response is not None:
                                if isinstance(raw_response, str):
                                    tool_result_str = raw_response
                                    if raw_response:
                                        try:
                                            result = json.loads(raw_response)
                                        except json.JSONDecodeError:
                                            try:
                                                import ast

                                                parsed = ast.literal_eval(raw_response)
                                                result = parsed if isinstance(parsed, dict) else None
                                            except (ValueError, SyntaxError):
                                                result = None
                                else:
                                    if isinstance(raw_response, dict):
                                        result = raw_response
                                    elif hasattr(raw_response, "model_dump"):
                                        try:
                                            result = raw_response.model_dump(mode="json")
                                        except Exception:
                                            result = raw_response.model_dump()
                                    try:
                                        tool_result_str = json.dumps(raw_response, ensure_ascii=False)
                                    except TypeError:
                                        tool_result_str = str(raw_response)

                            # Check if the tool returned an error
                            is_tool_error = False
                            error_message = None
                            if isinstance(result, dict) and result.get("error"):
                                is_tool_error = True
                                error_message = result["error"]
                            elif isinstance(raw_response, dict) and raw_response.get("error"):
                                is_tool_error = True
                                error_message = raw_response["error"]

                            if is_tool_error:
                                yield {
                                    "chunk_type": "tool_error",
                                    "tool_name": tool_name,
                                    "tool_call_id": resp_tool_call_id,
                                    "error_message": error_message,
                                }
                            else:
                                yield {
                                    "chunk_type": "tool_end",
                                    "tool_name": tool_name,
                                    "tool_call_id": resp_tool_call_id,
                                    "tool_result": tool_result_str,
                                }

                            # Send proposal chunk whenever a tool returns a proposal payload
                            if isinstance(result, dict) and "proposal_id" in result:
                                proposal_id = result.get("proposal_id")
                                proposal_type = result.get("proposal_type")
                                if proposal_type is not None and hasattr(proposal_type, "value"):
                                    proposal_type = proposal_type.value
                                yield {
                                    "chunk_type": "proposal",
                                    "proposal_id": str(proposal_id) if proposal_id is not None else None,
                                    "proposal_type": proposal_type,
                                    "description": result.get("description", ""),
                                    "payload": result.get("payload", {}),
                                }

                            # Send questions chunk when ask_user_questions tool is called
                            if isinstance(result, dict) and result.get("status") == "awaiting_response":
                                questions = result.get("questions", [])
                                if questions:
                                    yield {
                                        "chunk_type": "questions",
                                        "questions": questions,
                                        "context": result.get("context"),
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

            usage_data = None
            if total_input_tokens > 0 or total_output_tokens > 0:
                from app.services.cost_utils import calculate_cost

                model_id = self._resolve_llm_provider(request.model).get_model_id()
                usage_data = {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "total_tokens": total_input_tokens + total_output_tokens,
                    "cost_usd": calculate_cost(model_id, total_input_tokens, total_output_tokens),
                    "model": model_id,
                }

            yield {
                "chunk_type": "done",
                "assistant_message": assistant_message,
                "session_id": session_id_str,
                "capture_id": str(capture_id) if capture_id else None,
                "usage": usage_data,
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
        import json

        from app.agents.prompts.secretary_core_prompt import SECRETARY_CORE_PROMPT

        capture = await self._capture_repo.get(user_id, capture_id)
        if not capture:
            raise ValueError(f"Capture {capture_id} not found")

        # Construct prompt embedding the Secretary Persona
        # We perform a "stateless" execution here using the same model and system prompt
        # to ensure consistency without managing a full session state for this one-off analysis.

        system_instruction = SECRETARY_CORE_PROMPT

        prompt_text = "Analyze the following captured content and extract a Task.\n"
        prompt_text += (
            "Output MUST be a valid JSON object with 'title', 'description', 'importance', "
            "'urgency', 'estimated_minutes', 'due_date' (if found), and 'start_not_before' (if found).\n"
        )
        text_payload = ""
        image_bytes = None
        mime_type = "image/jpeg"
        parts = [Part(text=prompt_text)]

        # Add capture content
        if capture.content_type == ContentType.TEXT:
            try:
                data = json.loads(capture.raw_text)
                if isinstance(data, dict):
                    text_payload = f"Metadata: {json.dumps(data, indent=2)}"
                else:
                    text_payload = f"Text Content:\n{capture.raw_text}"
            except Exception:
                text_payload = f"Text Content:\n{capture.raw_text}"
            parts.append(Part(text=text_payload))

        elif capture.content_type == ContentType.IMAGE and capture.content_url:
            import mimetypes

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
                        text_payload = f"Image URL: {capture.content_url} (File not found)"
                except Exception as e:
                    logger.warning(f"Failed to read image file {image_path}: {e}")
                    text_payload = f"Image URL: {capture.content_url} (Failed to load)"
            else:
                import httpx
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(capture.content_url)
                        if resp.status_code == 200:
                            image_bytes = resp.content
                            mime_type = resp.headers.get("content-type", "image/jpeg")
                        else:
                            text_payload = f"Image URL: {capture.content_url} (Could not load)"
                except Exception as e:
                    logger.warning(f"Failed to fetch image for analysis: {e}")
                    text_payload = f"Image URL: {capture.content_url} (Failed to load)"

            if text_payload:
                parts.append(Part(text=text_payload))

            if image_bytes:
                parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))

        # Schema for structured output
        schema = {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Concise task title"},
                "description": {"type": "STRING", "description": "Detailed description or URL"},
                "importance": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "urgency": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "estimated_minutes": {"type": "INTEGER"},
                "due_date": {"type": "STRING", "description": "ISO 8601 format (YYYY-MM-DDTHH:MM:SS)"},
                "start_not_before": {
                    "type": "STRING",
                    "description": "ISO 8601 format (YYYY-MM-DDTHH:MM:SS)",
                },
            },
            "required": ["title", "importance"]
        }

        try:
            settings = getattr(self._llm_provider, "_settings", None)
            if settings and getattr(settings, "LLM_PROVIDER", None) == "litellm":
                import base64

                import litellm

                from app.infrastructure.local.litellm_provider import LiteLLMProvider

                if not isinstance(self._llm_provider, LiteLLMProvider):
                    raise ValueError("LiteLLM provider is not configured correctly.")

                schema_text = json.dumps(schema, ensure_ascii=False)
                full_prompt = prompt_text
                if text_payload:
                    full_prompt = f"{full_prompt}\n\n{text_payload}"
                full_prompt = f"{full_prompt}\n\nReturn JSON only. Schema:\n{schema_text}"

                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})

                if image_bytes:
                    image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                    content = [
                        {"type": "text", "text": full_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]
                    messages.append({"role": "user", "content": content})
                else:
                    messages.append({"role": "user", "content": full_prompt})

                kwargs: dict = {
                    "model": self._llm_provider.get_model_id(),
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 600,
                }
                if self._llm_provider.get_api_base():
                    kwargs["api_base"] = self._llm_provider.get_api_base()
                if self._llm_provider.get_api_key():
                    kwargs["api_key"] = self._llm_provider.get_api_key()

                response = litellm.completion(**kwargs)
                text = response.choices[0].message.content if response.choices else ""
                if text:
                    return json.loads(text)
                return {"title": "Failed to analyze", "description": "Empty response"}

            from google import genai
            from google.genai.types import GenerateContentConfig

            api_key = self._llm_provider._settings.GOOGLE_API_KEY
            client = genai.Client(api_key=api_key)
            model_name = self._llm_provider.get_model()
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
