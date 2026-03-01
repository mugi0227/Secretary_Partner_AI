import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FaMagic, FaPlay, FaMapMarkerAlt, FaUsers, FaInfoCircle, FaExpand, FaUndo, FaChevronDown, FaChevronUp, FaHistory, FaTrash, FaClock, FaClipboardList, FaLightbulb, FaCheckCircle } from 'react-icons/fa';
import { meetingAgendaApi } from '../../api/meetingAgenda';
import { meetingSessionApi } from '../../api/meetingSession';
import { projectsApi } from '../../api/projects';
import type { RecurringMeeting, Task, TaskUpdate } from '../../api/types';
import type { DraftCardData } from '../chat/DraftCard';
import { EditableSection } from '../common/EditableSection';
import { EditableDateTime } from '../common/EditableDateTime';
import {
    useLatestSessionByTask,
    useCreateSession,
    useUpdateSession,
    useStartSession,
    useEndSession,
    useReopenSession,
    useResetToPreparation,
} from '../../hooks/useMeetingSession';
import { useMeetingTimer } from '../../contexts/MeetingTimerContext';
import type { MeetingSessionStatus } from '../../types/session';
import { MeetingCompleted } from './MeetingCompleted';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateKey, todayInTimezone } from '../../utils/dateTime';
import { AgendaList } from '../agenda';
import './MeetingInProgress.css';

interface MeetingMainContentProps {
    projectId: string;
    selectedDate: Date | null;
    selectedMeeting: RecurringMeeting | null;
    selectedTask?: Task | null;
    onUpdateTask?: (taskId: string, update: TaskUpdate) => Promise<void>;
    onDeleteTask?: (taskId: string) => Promise<void>;
}

export function MeetingMainContent({
    projectId,
    selectedDate,
    selectedMeeting,
    selectedTask,
    onUpdateTask,
    onDeleteTask,
}: MeetingMainContentProps) {
    const timezone = useTimezone();
    // Either recurring meeting or standalone task (meeting)
    const hasMeeting = !!(selectedMeeting || selectedTask);
    const meetingTitle = selectedMeeting?.title || selectedTask?.title || '';
    const isAllDay = selectedTask?.is_all_day || false;
    const meetingStartTime = isAllDay
        ? '終日'
        : (selectedMeeting?.start_time || (selectedTask?.start_time ? formatDate(selectedTask.start_time, { hour: '2-digit', minute: '2-digit' }, timezone) : ''));
    const meetingEndTime = isAllDay
        ? null
        : (selectedTask?.end_time ? formatDate(selectedTask.end_time, { hour: '2-digit', minute: '2-digit' }, timezone) : null);

    // Editable: whether this task can be edited inline
    const canEdit = !!onUpdateTask && !!selectedTask;

    const handleFieldUpdate = async (field: keyof TaskUpdate, value: unknown) => {
        if (!onUpdateTask || !selectedTask) return;
        await onUpdateTask(selectedTask.id, { [field]: value } as TaskUpdate);
    };

    const handleDelete = async () => {
        if (!onDeleteTask || !selectedTask) return;
        if (!window.confirm('このミーティングを削除しますか？')) return;
        await onDeleteTask(selectedTask.id);
    };

    // Fetch project members for assignee selection
    const { data: members = [] } = useQuery({
        queryKey: ['project-members', projectId],
        queryFn: () => projectsApi.listMembers(projectId),
        enabled: !!projectId,
    });

    const memberOptions = useMemo(() =>
        members.map((member: { member_user_id: string; member_display_name?: string }) => ({
            id: member.member_user_id,
            label: member.member_display_name || member.member_user_id,
        })),
        [members]
    );

    // Collapsible state for meeting info section (default open when editable)
    const [isInfoCollapsed, setIsInfoCollapsed] = useState(!canEdit);

    const getDateStr = (date: Date) => toDateKey(date, timezone);

    const dateStr = selectedDate ? getDateStr(selectedDate) : '';

    // For recurring meetings: query by recurring_meeting_id (meeting_id column)
    const recurringMeetingId = selectedTask?.recurring_meeting_id;
    const { data: meetingAgendaItems = [] } = useQuery({
        queryKey: ['agenda-items', recurringMeetingId, dateStr],
        queryFn: () => meetingAgendaApi.listByMeeting(recurringMeetingId!, dateStr),
        enabled: !!recurringMeetingId && !!selectedDate,
    });

    // For standalone meetings: query by task_id
    const taskId = selectedTask?.id;
    const isStandalone = selectedTask && !selectedTask.recurring_meeting_id;
    const { data: taskAgendaItems = [] } = useQuery({
        queryKey: ['task-agendas', taskId],
        queryFn: () => meetingAgendaApi.listByTask(taskId!),
        enabled: !!isStandalone && !!taskId,
    });

    // Use meeting-based agenda for recurring, task-based for standalone
    const agendaItems = recurringMeetingId ? meetingAgendaItems : taskAgendaItems;

    // Fetch meeting session
    const { data: session, refetch: refetchSession, isFetching: isSessionFetching } = useLatestSessionByTask(taskId);

    // Session mutations
    const createSessionMutation = useCreateSession();
    const startSessionMutation = useStartSession(taskId);
    const endSessionMutation = useEndSession(taskId);
    const reopenSessionMutation = useReopenSession(taskId);
    const resetToPreparationMutation = useResetToPreparation(taskId);
    const updateSessionMutation = useUpdateSession(taskId);

    // Status dropdown state
    const [showStatusDropdown, setShowStatusDropdown] = useState(false);
    const statusDropdownRef = useRef<HTMLDivElement>(null);

    // Close dropdown on outside click
    useEffect(() => {
        if (!showStatusDropdown) return;
        const handleClick = (e: MouseEvent) => {
            if (statusDropdownRef.current && !statusDropdownRef.current.contains(e.target as Node)) {
                setShowStatusDropdown(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [showStatusDropdown]);

    const mainStatusOptions: { value: MeetingSessionStatus; label: string; modeClass: string }[] = [
        { value: 'PREPARATION', label: '準備中', modeClass: 'status-preparation' },
        { value: 'IN_PROGRESS', label: 'ミーティング中', modeClass: 'status-meeting' },
        { value: 'COMPLETED', label: '終了', modeClass: 'status-archive' },
    ];

    const handleMainStatusChange = useCallback(async (newStatus: MeetingSessionStatus) => {
        setShowStatusDropdown(false);
        if (session) {
            updateSessionMutation.mutate({ sessionId: session.id, data: { status: newStatus } });
        } else if (taskId) {
            const created = await createSessionMutation.mutateAsync({ task_id: taskId });
            if (newStatus !== 'PREPARATION') {
                updateSessionMutation.mutate({ sessionId: created.id, data: { status: newStatus } });
            }
        }
    }, [session, taskId, updateSessionMutation, createSessionMutation]);

    // Past sessions for recurring meetings (議事録履歴)
    const { data: pastSessions = [] } = useQuery({
        queryKey: ['meeting-sessions', 'recurring', recurringMeetingId],
        queryFn: () => meetingSessionApi.listByRecurringMeeting(recurringMeetingId!),
        enabled: !!recurringMeetingId,
    });

    // Previous session summary (前回の決定事項)
    const previousSession = useMemo(() => {
        if (!pastSessions.length || !session) return pastSessions.length ? pastSessions[0] : null;
        // Find the most recent session that is NOT the current one
        return pastSessions.find(s => s.id !== session.id) ?? null;
    }, [pastSessions, session]);

    // State for past sessions panel visibility
    const [showPastSessions, setShowPastSessions] = useState(false);

    // Global timer context
    const meetingTimer = useMeetingTimer();

    // Determine mode based on session status and date
    const mode = useMemo((): 'PREPARATION' | 'MEETING' | 'ARCHIVE' => {
        if (!hasMeeting || !selectedDate) {
            return 'PREPARATION';
        }

        // If there's an active session, use its status
        if (session) {
            const statusMap: Record<MeetingSessionStatus, 'PREPARATION' | 'MEETING' | 'ARCHIVE'> = {
                'PREPARATION': 'PREPARATION',
                'IN_PROGRESS': 'MEETING',
                'COMPLETED': 'ARCHIVE',
            };
            return statusMap[session.status] || 'PREPARATION';
        }

        // Otherwise, determine by date
        const todayStr = todayInTimezone(timezone).toISODate() ?? '';
        const selectedDateStr = getDateStr(selectedDate);

        if (selectedDateStr < todayStr) {
            return 'ARCHIVE';
        }
        return 'PREPARATION';
    }, [hasMeeting, selectedDate, session, timezone]);

    // Auto-refetch session when task changes
    useEffect(() => {
        if (taskId) {
            refetchSession();
        }
    }, [taskId, refetchSession]);

    // Sync global timer with session state
    useEffect(() => {
        // Don't do anything while session is loading - keep current timer state
        if (isSessionFetching) {
            return;
        }

        if (session && session.status === 'IN_PROGRESS' && selectedDate && taskId) {
            const dateStr = formatDate(
                selectedDate,
                { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' },
                timezone,
            );
            // Start or update global timer
            if (!meetingTimer.session || meetingTimer.session.id !== session.id) {
                meetingTimer.startTimer(session, agendaItems, meetingTitle, dateStr, taskId, projectId);
            } else {
                meetingTimer.updateSession(session);
                // Also update agenda items if they've changed
                if (JSON.stringify(meetingTimer.agendaItems) !== JSON.stringify(agendaItems)) {
                    meetingTimer.updateAgendaItems(agendaItems);
                }
            }
        } else if (session?.status === 'COMPLETED') {
            // Only stop timer when meeting is explicitly COMPLETED
            if (meetingTimer.session) {
                meetingTimer.stopTimer();
            }
        }
        // Note: Don't stop timer when session is null/undefined - the timer context persists across pages
    }, [session, agendaItems, meetingTitle, selectedDate, taskId, projectId, isSessionFetching, timezone]);

    const handleGenerateDraft = async () => {
        if (!hasMeeting || !selectedDate) return;

        const formattedDate = formatDate(
            selectedDate,
            { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' },
            timezone,
        );

        const title = selectedTask?.title || selectedMeeting?.title || '';

        // For recurring meetings, use meeting_id (recurring_meeting_id)
        // For standalone meetings, use task_id
        const meetingIdForAgent = selectedTask?.recurring_meeting_id;
        const taskIdForAgent = selectedTask?.id;

        // Build the ID reference for the prompt
        const idRef = meetingIdForAgent
            ? `meeting_id: ${meetingIdForAgent}`
            : `task_id: ${taskIdForAgent}`;

        const draftCard: DraftCardData = {
            type: 'agenda',
            title: 'アジェンダ作成',
            info: [
                { label: 'ミーティング', value: title },
                { label: '開催日', value: formattedDate },
            ],
            placeholder: '例: 前回の積み残し議題を優先して',
            promptTemplate: `ミーティング「${title}」(${idRef}) のアジェンダを作成して。
プロジェクトID: ${projectId}
開催日: ${formattedDate}
{checkin_context}

【出力形式】
1. まず「📋 Check-in要約」として、メンバーからのCheck-in内容（ブロッカー、相談事項、依頼など）を簡潔に箇条書きで要約してください。
2. 次に「📝 アジェンダ案」として、Check-in内容を踏まえたミーティングアジェンダを提案してください。

追加の指示:
{instruction}`,
            checkinOptions: {
                enabled: true,
            },
        };

        const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
        window.dispatchEvent(event);
    };

    const handleStartMeeting = async () => {
        if (!taskId) return;

        try {
            // Create session if it doesn't exist
            if (!session) {
                const newSession = await createSessionMutation.mutateAsync({ task_id: taskId });
                // Start the session
                await startSessionMutation.mutateAsync(newSession.id);
            } else if (session.status === 'PREPARATION') {
                // Start existing session
                await startSessionMutation.mutateAsync(session.id);
            } else if (session.status === 'IN_PROGRESS') {
                // Session already in progress, just show modal
            }
            meetingTimer.showModal();
        } catch (error) {
            console.error('Failed to start meeting:', error);
        }
    };

    const handleResumeModal = () => {
        meetingTimer.showModal();
    };

    const handleReopenSession = async () => {
        if (!session) return;
        try {
            await reopenSessionMutation.mutateAsync(session.id);
            meetingTimer.showModal();
        } catch (error) {
            console.error('Failed to reopen session:', error);
        }
    };

    const handleAddTranscriptForPast = async () => {
        if (!taskId) return;
        try {
            const newSession = await createSessionMutation.mutateAsync({ task_id: taskId });
            await endSessionMutation.mutateAsync(newSession.id);
            await refetchSession();
        } catch (error) {
            console.error('Failed to create session for past meeting:', error);
        }
    };

    const handleResetToPreparation = async () => {
        if (!session) return;
        if (!window.confirm('会議を開始前の状態に戻しますか？\n議事録やサマリーは保持されます。')) return;
        try {
            // Stop timer if running
            if (meetingTimer.session?.id === session.id) {
                meetingTimer.stopTimer();
            }
            await resetToPreparationMutation.mutateAsync(session.id);
        } catch (error) {
            console.error('Failed to reset to preparation:', error);
        }
    };

    if (!selectedDate || !hasMeeting) {
        return (
            <div className="meetings-main justify-center items-center">
                <div className="empty-state">
                    <p>左側のリストからミーティングを選択してください。</p>
                </div>
            </div>
        );
    }

    return (
        <div className="meetings-main">
            <div className="meetings-main-header">
                <div className="meeting-header-info">
                    <h2>
                        {formatDate(
                            selectedDate,
                            { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' },
                            timezone,
                        )}
                    </h2>
                    <div className="meeting-header-meta">
                        {canEdit ? (
                            <EditableSection
                                value={meetingTitle}
                                onSave={async (v) => handleFieldUpdate('title', v)}
                                placeholder="タイトルを入力"
                                className="meeting-title-editable"
                            />
                        ) : (
                            <span>{meetingTitle}</span>
                        )}
                        {meetingStartTime && (
                            <span>
                                {meetingStartTime}
                                {meetingEndTime ? `~${meetingEndTime}` : '~'}
                            </span>
                        )}
                    </div>
                </div>
                <div className="meeting-header-actions">
                    <div className="main-status-dropdown-wrapper" ref={statusDropdownRef}>
                        <div
                            className={`meeting-status-badge meeting-status-badge-clickable ${mode === 'MEETING' ? 'status-meeting' : mode === 'ARCHIVE' ? 'status-archive' : 'status-preparation'}`}
                            onClick={() => setShowStatusDropdown(!showStatusDropdown)}
                        >
                            {mode === 'MEETING' ? 'ミーティング中' : mode === 'ARCHIVE' ? '終了' : '準備中'}
                        </div>
                        {showStatusDropdown && (
                            <div className="main-status-dropdown">
                                {mainStatusOptions.map((option) => (
                                    <div
                                        key={option.value}
                                        className={`main-status-dropdown-item ${
                                            session?.status === option.value ? 'active' : ''
                                        }`}
                                        onClick={() => handleMainStatusChange(option.value)}
                                    >
                                        <span className={`meeting-status-badge ${option.modeClass}`}>
                                            {option.label}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    {canEdit && onDeleteTask && (
                        <button
                            className="meeting-delete-btn"
                            onClick={handleDelete}
                            title="ミーティングを削除"
                        >
                            <FaTrash />
                        </button>
                    )}
                </div>
            </div>

            {/* Meeting info section (location, attendees, description) - collapsible */}
            {(() => {
                const location = selectedTask?.location || selectedMeeting?.location;
                const attendees = selectedTask?.attendees?.length ? selectedTask.attendees : selectedMeeting?.attendees;
                const description = selectedTask?.description;
                const hasInfo = location || (attendees && attendees.length > 0) || description || canEdit;

                if (!hasInfo) return null;

                return (
                    <div className={`meeting-info-section ${isInfoCollapsed ? 'collapsed' : ''}`}>
                        <button
                            className="meeting-info-toggle"
                            onClick={() => setIsInfoCollapsed(!isInfoCollapsed)}
                        >
                            <FaInfoCircle className="meeting-info-icon" />
                            <span>会議情報</span>
                            {isInfoCollapsed ? <FaChevronDown /> : <FaChevronUp />}
                        </button>
                        {!isInfoCollapsed && (
                            <div className="meeting-info-content">
                                {/* Start/End time - editable */}
                                {canEdit && (
                                    <div className="meeting-info-item meeting-info-time-row">
                                        <FaClock className="meeting-info-icon" />
                                        <EditableDateTime
                                            value={selectedTask?.start_time}
                                            onSave={async (v) => handleFieldUpdate('start_time', v)}
                                            placeholder="開始時刻"
                                            timezone={timezone}
                                            showTime
                                        />
                                        <span className="meeting-info-time-separator">〜</span>
                                        <EditableDateTime
                                            value={selectedTask?.end_time}
                                            onSave={async (v) => handleFieldUpdate('end_time', v)}
                                            placeholder="終了時刻"
                                            timezone={timezone}
                                            showTime
                                        />
                                    </div>
                                )}
                                {/* Location */}
                                <div className="meeting-info-item">
                                    <FaMapMarkerAlt className="meeting-info-icon" />
                                    {canEdit ? (
                                        <EditableSection
                                            value={location || ''}
                                            onSave={async (v) => handleFieldUpdate('location', v || null)}
                                            placeholder="場所を入力"
                                        />
                                    ) : (
                                        location && <span>{location}</span>
                                    )}
                                </div>
                                {/* Attendees */}
                                <div className="meeting-info-item">
                                    <FaUsers className="meeting-info-icon" />
                                    {canEdit ? (
                                        <EditableSection
                                            value={attendees?.join(', ') || ''}
                                            onSave={async (v) => {
                                                const arr = v.split(',').map(s => s.trim()).filter(Boolean);
                                                await handleFieldUpdate('attendees', arr);
                                            }}
                                            placeholder="参加者（カンマ区切り）"
                                        />
                                    ) : (
                                        attendees && attendees.length > 0 && <span>{attendees.join(', ')}</span>
                                    )}
                                </div>
                                {/* Description */}
                                <div className="meeting-info-item meeting-info-description">
                                    {canEdit ? (
                                        <EditableSection
                                            value={description || ''}
                                            onSave={async (v) => handleFieldUpdate('description', v || null)}
                                            placeholder="説明を入力"
                                            multiline
                                        />
                                    ) : (
                                        description && <span>{description}</span>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                );
            })()}

            <div className="meetings-main-scroll">
                {(mode === 'PREPARATION' || mode === 'ARCHIVE') && (
                    <div className="agenda-section">
                        {mode === 'PREPARATION' && (
                            <div className="agenda-actions">
                                <button className="btn-ai-generate" onClick={handleGenerateDraft}>
                                    <FaMagic /> AIでドラフト作成
                                </button>
                                {agendaItems.length > 0 && (
                                    <button
                                        className="btn-start-meeting"
                                        onClick={handleStartMeeting}
                                        disabled={createSessionMutation.isPending || startSessionMutation.isPending}
                                    >
                                        <FaPlay /> 会議を開始
                                    </button>
                                )}
                            </div>
                        )}

                        {mode === 'ARCHIVE' && session && session.status === 'COMPLETED' && (
                            <div className="agenda-actions">
                                <button
                                    className="btn-reset-to-preparation"
                                    onClick={handleResetToPreparation}
                                    disabled={resetToPreparationMutation.isPending}
                                >
                                    <FaHistory /> 開始前に戻す
                                </button>
                                <button
                                    className="btn-reopen-meeting"
                                    onClick={handleReopenSession}
                                    disabled={reopenSessionMutation.isPending}
                                >
                                    <FaUndo /> 会議をやり直す
                                </button>
                            </div>
                        )}

                        {/* 過去の会議でセッションがない場合: 議事録を追加ボタン */}
                        {mode === 'ARCHIVE' && !session && (
                            <div className="agenda-actions">
                                <button
                                    className="btn-add-transcript"
                                    onClick={handleAddTranscriptForPast}
                                    disabled={createSessionMutation.isPending || endSessionMutation.isPending}
                                >
                                    <FaClipboardList /> 議事録を追加
                                </button>
                            </div>
                        )}

                        <AgendaList
                            meetingId={recurringMeetingId}
                            taskId={isStandalone ? taskId : undefined}
                            eventDate={dateStr}
                            readonly={mode === 'ARCHIVE'}
                        />
                    </div>
                )}

                {/* Post-meeting summary section for ARCHIVE mode */}
                {mode === 'ARCHIVE' && session && session.status === 'COMPLETED' && (
                    <MeetingCompleted
                        session={session}
                        projectId={projectId}
                        memberOptions={memberOptions}
                    />
                )}

                {/* 前回の決定事項・議事録履歴 (PREPARATION/ARCHIVE mode) */}
                {(mode === 'PREPARATION' || mode === 'ARCHIVE') && previousSession && (
                    <PreviousSessionSummary
                        session={previousSession}
                        timezone={timezone}
                    />
                )}

                {/* 過去の議事録一覧 (定例会議のみ) */}
                {(mode === 'PREPARATION' || mode === 'ARCHIVE') && pastSessions.length > 0 && (
                    <div className="past-sessions-section">
                        <button
                            className="past-sessions-toggle"
                            onClick={() => setShowPastSessions(!showPastSessions)}
                        >
                            <FaHistory />
                            <span>過去の議事録 ({pastSessions.length}件)</span>
                            {showPastSessions ? <FaChevronUp /> : <FaChevronDown />}
                        </button>
                        {showPastSessions && (
                            <div className="past-sessions-list">
                                {pastSessions.map((ps) => (
                                    <PastSessionCard
                                        key={ps.id}
                                        session={ps}
                                        isCurrentSession={session?.id === ps.id}
                                        timezone={timezone}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Minimized meeting bar - show when meeting is in progress but modal is closed */}
                {mode === 'MEETING' && session && !meetingTimer.isModalVisible && (
                    <div className="meeting-minimized-bar">
                        <div className="meeting-minimized-info">
                            <span className="meeting-minimized-status">
                                <span className="pulse-dot"></span>
                                会議中
                            </span>
                            <span className="meeting-minimized-agenda">
                                議題 {(session.current_agenda_index ?? 0) + 1}/{agendaItems.length}
                                <span className="meeting-minimized-agenda-title">
                                    {agendaItems[session.current_agenda_index ?? 0]?.title || '---'}
                                </span>
                            </span>
                        </div>
                        <div className="meeting-minimized-actions">
                            <button
                                className="btn-minimized resume"
                                onClick={handleResumeModal}
                                title="会議画面を開く"
                            >
                                <FaExpand /> 会議画面を開く
                            </button>
                        </div>
                    </div>
                )}
                {/* Modal is now rendered globally via GlobalMeetingModal */}
            </div>
        </div>
    );
}

// --- Helper Components ---

interface MeetingSessionSummaryData {
    overall_summary?: string;
    agenda_discussions?: Array<{ title: string; summary: string }>;
    decisions?: Array<{ content: string; rationale?: string }>;
}

function parseSummaryJson(summaryJson: string | null | undefined): MeetingSessionSummaryData | null {
    if (!summaryJson) return null;
    try {
        return JSON.parse(summaryJson) as MeetingSessionSummaryData;
    } catch {
        return null;
    }
}

/** 前回の決定事項を表示するコンポーネント */
function PreviousSessionSummary({ session, timezone }: { session: { summary?: string | null; ended_at?: string | null; created_at?: string | null; transcript?: string | null }; timezone: string }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const summaryData = useMemo(() => parseSummaryJson(session.summary), [session.summary]);

    if (!summaryData && !session.transcript) return null;

    const dateLabel = session.ended_at
        ? formatDate(session.ended_at, { month: 'short', day: 'numeric' }, timezone)
        : session.created_at
            ? formatDate(session.created_at, { month: 'short', day: 'numeric' }, timezone)
            : '';

    return (
        <div className="previous-session-section">
            <button
                className="previous-session-toggle"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <FaLightbulb className="previous-session-icon" />
                <span>前回の決定事項・サマリー {dateLabel && `(${dateLabel})`}</span>
                {isExpanded ? <FaChevronUp /> : <FaChevronDown />}
            </button>
            {isExpanded && (
                <div className="previous-session-content">
                    {summaryData?.overall_summary && (
                        <div className="previous-summary-block">
                            <h5>サマリー</h5>
                            <p>{summaryData.overall_summary}</p>
                        </div>
                    )}
                    {summaryData?.decisions && summaryData.decisions.length > 0 && (
                        <div className="previous-decisions-block">
                            <h5><FaCheckCircle /> 決定事項</h5>
                            <ul>
                                {summaryData.decisions.map((d, i) => (
                                    <li key={i}>
                                        <span className="decision-content">{d.content}</span>
                                        {d.rationale && <span className="decision-rationale">（{d.rationale}）</span>}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {!summaryData && session.transcript && (
                        <div className="previous-summary-block">
                            <h5>議事録</h5>
                            <pre className="previous-transcript">{session.transcript}</pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/** 過去のセッションカード */
function PastSessionCard({ session, isCurrentSession, timezone }: {
    session: { id: string; summary?: string | null; ended_at?: string | null; created_at?: string | null; transcript?: string | null; status: string };
    isCurrentSession: boolean;
    timezone: string;
}) {
    const [isExpanded, setIsExpanded] = useState(false);
    const summaryData = useMemo(() => parseSummaryJson(session.summary), [session.summary]);

    const dateLabel = session.ended_at
        ? formatDate(session.ended_at, { year: 'numeric', month: 'short', day: 'numeric' }, timezone)
        : session.created_at
            ? formatDate(session.created_at, { year: 'numeric', month: 'short', day: 'numeric' }, timezone)
            : '';

    return (
        <div className={`past-session-card ${isCurrentSession ? 'current' : ''}`}>
            <button
                className="past-session-header"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <span className="past-session-date">{dateLabel}</span>
                {isCurrentSession && <span className="past-session-current-badge">今回</span>}
                {summaryData ? (
                    <span className="past-session-has-summary">サマリーあり</span>
                ) : session.transcript ? (
                    <span className="past-session-has-transcript">議事録あり</span>
                ) : null}
                {isExpanded ? <FaChevronUp /> : <FaChevronDown />}
            </button>
            {isExpanded && (
                <div className="past-session-body">
                    {summaryData?.overall_summary && (
                        <div className="past-session-summary">
                            <strong>サマリー:</strong> {summaryData.overall_summary}
                        </div>
                    )}
                    {summaryData?.decisions && summaryData.decisions.length > 0 && (
                        <div className="past-session-decisions">
                            <strong>決定事項:</strong>
                            <ul>
                                {summaryData.decisions.map((d, i) => (
                                    <li key={i}>{d.content}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {session.transcript && (
                        <details className="past-session-transcript-details">
                            <summary>議事録を表示</summary>
                            <pre>{session.transcript}</pre>
                        </details>
                    )}
                    {!summaryData && !session.transcript && (
                        <p className="past-session-empty">内容がありません</p>
                    )}
                </div>
            )}
        </div>
    );
}
