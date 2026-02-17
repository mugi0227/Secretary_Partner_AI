"""
Dependency injection for API endpoints.

This module provides FastAPI dependencies that inject the correct
infrastructure implementations based on environment configuration.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.interfaces.achievement_repository import IAchievementRepository
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.auth_provider import IAuthProvider, User
from app.interfaces.blocker_repository import IBlockerRepository
from app.interfaces.capture_repository import ICaptureRepository
from app.interfaces.chat_session_repository import IChatSessionRepository
from app.interfaces.checkin_repository import ICheckinRepository
from app.interfaces.heartbeat_event_repository import IHeartbeatEventRepository
from app.interfaces.heartbeat_settings_repository import IHeartbeatSettingsRepository
from app.interfaces.issue_comment_repository import IIssueCommentRepository
from app.interfaces.issue_repository import IIssueRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.meeting_agenda_repository import IMeetingAgendaRepository
from app.interfaces.meeting_session_repository import IMeetingSessionRepository
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.milestone_repository import IMilestoneRepository
from app.interfaces.notification_repository import INotificationRepository
from app.interfaces.phase_repository import IPhaseRepository
from app.interfaces.postpone_repository import IPostponeRepository
from app.interfaces.project_achievement_repository import IProjectAchievementRepository
from app.interfaces.project_invitation_repository import IProjectInvitationRepository
from app.interfaces.project_link_request_repository import IProjectLinkRequestRepository
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.proposal_repository import IProposalRepository
from app.interfaces.recurring_meeting_repository import IRecurringMeetingRepository
from app.interfaces.recurring_task_repository import IRecurringTaskRepository
from app.interfaces.schedule_plan_repository import IDailySchedulePlanRepository
from app.interfaces.schedule_settings_repository import IScheduleSettingsRepository
from app.interfaces.schedule_snapshot_repository import IScheduleSnapshotRepository
from app.interfaces.speech_provider import ISpeechToTextProvider
from app.interfaces.storage_provider import IStorageProvider
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository

# ===========================================
# Repository Dependencies
# ===========================================


@lru_cache()
def get_task_repository() -> ITaskRepository:
    """Get task repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        # TODO: Implement Firestore repository
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.task_repository import SqliteTaskRepository
        return SqliteTaskRepository()


@lru_cache()
def get_project_repository() -> IProjectRepository:
    """Get project repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.project_repository import SqliteProjectRepository
        return SqliteProjectRepository()


@lru_cache()
def get_phase_repository() -> IPhaseRepository:
    """Get phase repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.phase_repository import SqlitePhaseRepository
        return SqlitePhaseRepository()


@lru_cache()
def get_milestone_repository() -> IMilestoneRepository:
    """Get milestone repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.milestone_repository import SqliteMilestoneRepository
        return SqliteMilestoneRepository()


@lru_cache()
def get_agent_task_repository() -> IAgentTaskRepository:
    """Get agent task repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.agent_task_repository import SqliteAgentTaskRepository
        return SqliteAgentTaskRepository()


@lru_cache()
def get_memory_repository() -> IMemoryRepository:
    """Get memory repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.memory_repository import SqliteMemoryRepository
        return SqliteMemoryRepository()


@lru_cache()
def get_capture_repository() -> ICaptureRepository:
    """Get capture repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.capture_repository import SqliteCaptureRepository
        return SqliteCaptureRepository()


@lru_cache()
def get_chat_session_repository() -> IChatSessionRepository:
    """Get chat session repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Chat session repository not implemented for GCP")
    else:
        from app.infrastructure.local.chat_session_repository import SqliteChatSessionRepository
        return SqliteChatSessionRepository()


@lru_cache()
def get_proposal_repository() -> IProposalRepository:
    """Get proposal repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Proposal repository not implemented for GCP")
    else:
        from app.infrastructure.local.proposal_repository import InMemoryProposalRepository
        return InMemoryProposalRepository()


@lru_cache()
def get_user_repository() -> IUserRepository:
    """Get user repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("User repository not implemented for GCP")
    else:
        from app.infrastructure.local.user_repository import SqliteUserRepository
        return SqliteUserRepository()


@lru_cache()
def get_project_member_repository() -> IProjectMemberRepository:
    """Get project member repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Project member repository not implemented for GCP")
    else:
        from app.infrastructure.local.project_member_repository import SqliteProjectMemberRepository
        return SqliteProjectMemberRepository()


@lru_cache()
def get_project_link_request_repository() -> IProjectLinkRequestRepository:
    """Get project link request repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Project link request repository not implemented for GCP")
    else:
        from app.infrastructure.local.project_link_request_repository import (
            SqliteProjectLinkRequestRepository,
        )
        return SqliteProjectLinkRequestRepository()


@lru_cache()
def get_project_invitation_repository() -> IProjectInvitationRepository:
    """Get project invitation repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Project invitation repository not implemented for GCP")
    else:
        from app.infrastructure.local.project_invitation_repository import (
            SqliteProjectInvitationRepository,
        )
        return SqliteProjectInvitationRepository()


@lru_cache()
def get_task_assignment_repository() -> ITaskAssignmentRepository:
    """Get task assignment repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Task assignment repository not implemented for GCP")
    else:
        from app.infrastructure.local.task_assignment_repository import (
            SqliteTaskAssignmentRepository,
        )
        return SqliteTaskAssignmentRepository()


@lru_cache()
def get_checkin_repository() -> ICheckinRepository:
    """Get check-in repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Check-in repository not implemented for GCP")
    else:
        from app.infrastructure.local.checkin_repository import SqliteCheckinRepository
        return SqliteCheckinRepository()


@lru_cache()
def get_blocker_repository() -> IBlockerRepository:
    """Get blocker repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Blocker repository not implemented for GCP")
    else:
        from app.infrastructure.local.blocker_repository import SqliteBlockerRepository
        return SqliteBlockerRepository()


@lru_cache()
def get_postpone_repository() -> IPostponeRepository:
    """Get postpone repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Postpone repository not implemented for GCP")
    else:
        from app.infrastructure.local.postpone_repository import SqlitePostponeRepository
        return SqlitePostponeRepository()


@lru_cache()
def get_recurring_meeting_repository() -> IRecurringMeetingRepository:
    """Get recurring meeting repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Recurring meeting repository not implemented for GCP")
    else:
        from app.infrastructure.local.recurring_meeting_repository import (
            SqliteRecurringMeetingRepository,
        )
        return SqliteRecurringMeetingRepository()


@lru_cache()
def get_recurring_task_repository() -> IRecurringTaskRepository:
    """Get recurring task repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Recurring task repository not implemented for GCP")
    else:
        from app.infrastructure.local.recurring_task_repository import SqliteRecurringTaskRepository
        return SqliteRecurringTaskRepository()


@lru_cache()
def get_schedule_snapshot_repository() -> IScheduleSnapshotRepository:
    """Get schedule snapshot repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Schedule snapshot repository not implemented for GCP")
    else:
        from app.infrastructure.local.schedule_snapshot_repository import (
            SqliteScheduleSnapshotRepository,
        )
        return SqliteScheduleSnapshotRepository()


@lru_cache()
def get_schedule_settings_repository() -> IScheduleSettingsRepository:
    """Get schedule settings repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Schedule settings repository not implemented for GCP")
    else:
        from app.infrastructure.local.schedule_settings_repository import (
            SqliteScheduleSettingsRepository,
        )
        return SqliteScheduleSettingsRepository()


@lru_cache()
def get_daily_schedule_plan_repository() -> IDailySchedulePlanRepository:
    """Get daily schedule plan repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Daily schedule plan repository not implemented for GCP")
    else:
        from app.infrastructure.local.schedule_plan_repository import (
            SqliteDailySchedulePlanRepository,
        )
        return SqliteDailySchedulePlanRepository()


@lru_cache()
def get_meeting_agenda_repository() -> IMeetingAgendaRepository:
    """Get meeting agenda repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Meeting agenda repository not implemented for GCP")
    else:
        from app.infrastructure.local.meeting_agenda_repository import SqliteMeetingAgendaRepository
        return SqliteMeetingAgendaRepository()


@lru_cache()
def get_meeting_session_repository() -> IMeetingSessionRepository:
    """Get meeting session repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Meeting session repository not implemented for GCP")
    else:
        from app.infrastructure.local.meeting_session_repository import (
            SqliteMeetingSessionRepository,
        )
        return SqliteMeetingSessionRepository()


@lru_cache()
def get_issue_repository() -> IIssueRepository:
    """Get issue repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Issue repository not implemented for GCP")
    else:
        from app.infrastructure.local.issue_repository import SqliteIssueRepository
        return SqliteIssueRepository()


@lru_cache()
def get_achievement_repository() -> IAchievementRepository:
    """Get achievement repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Achievement repository not implemented for GCP")
    else:
        from app.infrastructure.local.achievement_repository import SqliteAchievementRepository
        return SqliteAchievementRepository()


@lru_cache()
def get_project_achievement_repository() -> IProjectAchievementRepository:
    """Get project achievement repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Project achievement repository not implemented for GCP")
    else:
        from app.infrastructure.local.project_achievement_repository import (
            SqliteProjectAchievementRepository,
        )
        return SqliteProjectAchievementRepository()


@lru_cache()
def get_issue_comment_repository() -> IIssueCommentRepository:
    """Get issue comment repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Issue comment repository not implemented for GCP")
    else:
        from app.infrastructure.local.issue_comment_repository import SqliteIssueCommentRepository
        return SqliteIssueCommentRepository()


@lru_cache()
def get_notification_repository() -> INotificationRepository:
    """Get notification repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Notification repository not implemented for GCP")
    else:
        from app.infrastructure.local.notification_repository import SqliteNotificationRepository
        return SqliteNotificationRepository()


@lru_cache()
def get_heartbeat_settings_repository() -> IHeartbeatSettingsRepository:
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Heartbeat settings repository not implemented for GCP")
    from app.infrastructure.local.heartbeat_settings_repository import (
        SqliteHeartbeatSettingsRepository,
    )
    return SqliteHeartbeatSettingsRepository()


@lru_cache()
def get_heartbeat_event_repository() -> IHeartbeatEventRepository:
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Heartbeat event repository not implemented for GCP")
    from app.infrastructure.local.heartbeat_event_repository import (
        SqliteHeartbeatEventRepository,
    )
    return SqliteHeartbeatEventRepository()


# ===========================================
# Provider Dependencies
# ===========================================


@lru_cache()
def get_llm_provider() -> ILLMProvider:
    """
    Get LLM provider instance based on LLM_PROVIDER setting.

    Supports:
    - gemini-api: Gemini API (API Key, works in local/gcp)
    - vertex-ai: Vertex AI (GCP only, service account)
    - litellm: LiteLLM (Bedrock, OpenAI, etc. with optional custom endpoint)
    """
    settings = get_settings()

    if settings.LLM_PROVIDER == "gemini-api":
        from app.infrastructure.local.gemini_api_provider import GeminiAPIProvider
        return GeminiAPIProvider(settings.GEMINI_MODEL)

    elif settings.LLM_PROVIDER == "vertex-ai":
        if not settings.is_gcp:
            raise ValueError(
                "Vertex AI provider requires ENVIRONMENT=gcp. "
                "Use gemini-api or litellm for local development."
            )
        from app.infrastructure.gcp.gemini_provider import VertexAIProvider
        return VertexAIProvider(settings.GEMINI_MODEL)

    elif settings.LLM_PROVIDER == "litellm":
        from app.infrastructure.local.litellm_provider import LiteLLMProvider
        return LiteLLMProvider(settings.LITELLM_MODEL)

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")


@lru_cache()
def get_auth_provider() -> IAuthProvider:
    """Get auth provider instance."""
    settings = get_settings()
    if settings.AUTH_PROVIDER == "oidc":
        from app.infrastructure.auth.oidc_auth import OidcAuthProvider

        return OidcAuthProvider(settings, get_user_repository())
    if settings.AUTH_PROVIDER == "local":
        from app.infrastructure.auth.local_auth import LocalAuthProvider

        return LocalAuthProvider(settings, get_user_repository())

    from app.infrastructure.local.mock_auth import MockAuthProvider
    return MockAuthProvider(enabled=True)


@lru_cache()
def get_storage_provider() -> IStorageProvider:
    """Get storage provider instance."""
    settings = get_settings()
    if settings.is_gcp:
        # TODO: Implement GCS provider
        raise NotImplementedError("Google Cloud Storage not implemented yet")
    else:
        from app.infrastructure.local.storage_provider import LocalStorageProvider
        return LocalStorageProvider(settings.STORAGE_BASE_PATH)


@lru_cache()
def get_speech_provider() -> ISpeechToTextProvider:
    """Get speech-to-text provider instance."""
    settings = get_settings()
    if settings.SPEECH_PROVIDER == "google-stt-v2":
        from app.infrastructure.gcp.speech_v2_provider import GoogleSpeechV2Provider

        project_id = (settings.GOOGLE_CLOUD_PROJECT or "").strip() or None
        return GoogleSpeechV2Provider(
            project_id=project_id,
            location=settings.STT_V2_LOCATION,
            model=settings.STT_V2_MODEL,
            default_language=settings.STT_V2_LANGUAGE,
        )

    if settings.SPEECH_PROVIDER == "amazon-transcribe":
        from app.infrastructure.aws.transcribe_provider import AmazonTranscribeProvider

        return AmazonTranscribeProvider(
            region_name=settings.AWS_REGION,
            bucket_name=settings.AWS_TRANSCRIBE_S3_BUCKET,
            key_prefix=settings.AWS_TRANSCRIBE_S3_PREFIX,
            default_language=settings.AWS_TRANSCRIBE_LANGUAGE,
            poll_interval_seconds=settings.AWS_TRANSCRIBE_POLL_SECONDS,
            timeout_seconds=settings.AWS_TRANSCRIBE_TIMEOUT_SECONDS,
        )

    from app.infrastructure.local.whisper_provider import WhisperProvider

    return WhisperProvider(settings.WHISPER_MODEL_SIZE)


# ===========================================
# User Authentication
# ===========================================


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    auth_provider: IAuthProvider = Depends(get_auth_provider),
) -> User:
    """
    Get current authenticated user.

    In local mode, returns a mock user.
    In GCP mode, validates Firebase token.
    """
    if not auth_provider.is_enabled():
        # Mock user for development
        user = User(id="dev_user", email="dev@example.com", display_name="Developer")
        request.state.user = user
        return user

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    try:
        user = await auth_provider.verify_token(token)
        request.state.user = user
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


# ===========================================
# Type Aliases for Dependency Injection
# ===========================================

TaskRepo = Annotated[ITaskRepository, Depends(get_task_repository)]
ProjectRepo = Annotated[IProjectRepository, Depends(get_project_repository)]
PhaseRepo = Annotated[IPhaseRepository, Depends(get_phase_repository)]
MilestoneRepo = Annotated[IMilestoneRepository, Depends(get_milestone_repository)]
ProposalRepo = Annotated[IProposalRepository, Depends(get_proposal_repository)]
AgentTaskRepo = Annotated[IAgentTaskRepository, Depends(get_agent_task_repository)]
MemoryRepo = Annotated[IMemoryRepository, Depends(get_memory_repository)]
CaptureRepo = Annotated[ICaptureRepository, Depends(get_capture_repository)]
ChatRepo = Annotated[IChatSessionRepository, Depends(get_chat_session_repository)]
ProjectMemberRepo = Annotated[IProjectMemberRepository, Depends(get_project_member_repository)]
ProjectLinkRequestRepo = Annotated[
    IProjectLinkRequestRepository, Depends(get_project_link_request_repository)
]
TaskAssignmentRepo = Annotated[ITaskAssignmentRepository, Depends(get_task_assignment_repository)]
CheckinRepo = Annotated[ICheckinRepository, Depends(get_checkin_repository)]
BlockerRepo = Annotated[IBlockerRepository, Depends(get_blocker_repository)]
PostponeRepo = Annotated[IPostponeRepository, Depends(get_postpone_repository)]
RecurringMeetingRepo = Annotated[IRecurringMeetingRepository, Depends(get_recurring_meeting_repository)]
RecurringTaskRepo = Annotated[IRecurringTaskRepository, Depends(get_recurring_task_repository)]
MeetingAgendaRepo = Annotated[IMeetingAgendaRepository, Depends(get_meeting_agenda_repository)]
MeetingSessionRepo = Annotated[IMeetingSessionRepository, Depends(get_meeting_session_repository)]
UserRepo = Annotated[IUserRepository, Depends(get_user_repository)]
ProjectInvitationRepo = Annotated[
    IProjectInvitationRepository, Depends(get_project_invitation_repository)
]
LLMProvider = Annotated[ILLMProvider, Depends(get_llm_provider)]
StorageProvider = Annotated[IStorageProvider, Depends(get_storage_provider)]
SpeechProvider = Annotated[ISpeechToTextProvider, Depends(get_speech_provider)]
ScheduleSnapshotRepo = Annotated[IScheduleSnapshotRepository, Depends(get_schedule_snapshot_repository)]
ScheduleSettingsRepo = Annotated[IScheduleSettingsRepository, Depends(get_schedule_settings_repository)]
DailySchedulePlanRepo = Annotated[IDailySchedulePlanRepository, Depends(get_daily_schedule_plan_repository)]
IssueRepo = Annotated[IIssueRepository, Depends(get_issue_repository)]
IssueCommentRepo = Annotated[IIssueCommentRepository, Depends(get_issue_comment_repository)]
AchievementRepo = Annotated[IAchievementRepository, Depends(get_achievement_repository)]
ProjectAchievementRepo = Annotated[IProjectAchievementRepository, Depends(get_project_achievement_repository)]
NotificationRepo = Annotated[INotificationRepository, Depends(get_notification_repository)]
HeartbeatSettingsRepo = Annotated[
    IHeartbeatSettingsRepository, Depends(get_heartbeat_settings_repository)
]
HeartbeatEventRepo = Annotated[
    IHeartbeatEventRepository, Depends(get_heartbeat_event_repository)
]
CurrentUser = Annotated[User, Depends(get_current_user)]
