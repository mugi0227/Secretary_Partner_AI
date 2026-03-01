import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { FaCalendarDay, FaRedo } from 'react-icons/fa';
import { RecurringMeeting, Task, MeetingAgendaItem } from '../../api/types';
import { tasksApi } from '../../api/tasks';
import { meetingAgendaApi } from '../../api/meetingAgenda';
import { meetingSessionApi } from '../../api/meetingSession';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateTime, nowInTimezone } from '../../utils/dateTime';
import type { MeetingSession, MeetingSessionStatus } from '../../types/session';

interface MeetingStatus {
    hasAgenda: boolean;
    hasSummary: boolean;
    isConducted: boolean;
    sessionId?: string;
    sessionStatus?: MeetingSessionStatus;
}

interface MeetingSidebarProps {
    projectId: string;
    recurringMeetings: RecurringMeeting[];
    selectedTask?: Task | null;
    onSelectTask: (task: Task, date: Date) => void;
    isLoading: boolean;
}

export function MeetingSidebar({
    projectId,
    recurringMeetings,
    selectedTask,
    onSelectTask,
    isLoading
}: MeetingSidebarProps) {
    const timezone = useTimezone();
    // Fetch all meeting Tasks (both recurring and standalone)
    const { data: meetingTasks = [] } = useQuery({
        queryKey: ['meetings', 'project', projectId],
        queryFn: () => tasksApi.getAll({
            includeDone: true,
            onlyMeetings: true,
            projectId: projectId
        }),
        staleTime: 30_000,
    });

    // Create a lookup map for RecurringMeeting by ID
    const recurringMeetingMap = useMemo(() => {
        const map: Record<string, RecurringMeeting> = {};
        recurringMeetings.forEach(m => {
            map[m.id] = m;
        });
        return map;
    }, [recurringMeetings]);

    // All valid meeting tasks (for auto-select and status queries)
    const allMeetingTasks = useMemo(() => {
        return meetingTasks.filter(task => task.is_fixed_time && task.start_time);
    }, [meetingTasks]);

    // Group meeting tasks by recurring_meeting_id
    const { recurringMeetingTasks, standaloneMeetings } = useMemo(() => {
        const recurring: Record<string, { recurringMeeting: RecurringMeeting; tasks: Task[] }> = {};
        const standalone: Task[] = [];

        allMeetingTasks.forEach(task => {
            if (task.recurring_meeting_id) {
                const rmId = task.recurring_meeting_id;
                if (!recurring[rmId]) {
                    const rm = recurringMeetingMap[rmId];
                    if (rm) {
                        recurring[rmId] = { recurringMeeting: rm, tasks: [] };
                    } else {
                        // RecurringMeeting not found (maybe deleted), treat as standalone
                        standalone.push(task);
                        return;
                    }
                }
                recurring[rmId].tasks.push(task);
            } else {
                standalone.push(task);
            }
        });

        // Sort tasks within each recurring meeting group by start_time (newest first)
        Object.values(recurring).forEach(group => {
            group.tasks.sort((a, b) => {
                const aTime = a.start_time ? toDateTime(a.start_time, timezone).toMillis() : 0;
                const bTime = b.start_time ? toDateTime(b.start_time, timezone).toMillis() : 0;
                return bTime - aTime;
            });
        });

        // Sort standalone meetings by start_time (newest first)
        standalone.sort((a, b) => {
            const aTime = a.start_time ? toDateTime(a.start_time, timezone).toMillis() : 0;
            const bTime = b.start_time ? toDateTime(b.start_time, timezone).toMillis() : 0;
            return bTime - aTime;
        });

        return { recurringMeetingTasks: recurring, standaloneMeetings: standalone };
    }, [allMeetingTasks, recurringMeetingMap, timezone]);

    // Auto-select the closest meeting to today when no task is selected
    useEffect(() => {
        if (selectedTask || allMeetingTasks.length === 0) return;

        const nowMillis = Date.now();
        let closestFuture: Task | null = null;
        let closestFutureDiff = Infinity;
        let closestPast: Task | null = null;
        let closestPastDiff = Infinity;

        for (const task of allMeetingTasks) {
            const taskMillis = toDateTime(task.start_time!, timezone).toMillis();
            const diff = taskMillis - nowMillis;

            if (diff >= 0 && diff < closestFutureDiff) {
                closestFuture = task;
                closestFutureDiff = diff;
            } else if (diff < 0 && -diff < closestPastDiff) {
                closestPast = task;
                closestPastDiff = -diff;
            }
        }

        const best = closestPast || closestFuture;
        if (best) {
            onSelectTask(best, toDateTime(best.start_time!, timezone).toJSDate());
        }
    }, [allMeetingTasks, selectedTask, timezone, onSelectTask]);

    // Batch fetch latest sessions for all meeting tasks
    const sessionQueries = useQueries({
        queries: allMeetingTasks.map(task => ({
            queryKey: ['meeting-session', 'task', task.id, 'latest'],
            queryFn: () => meetingSessionApi.getLatestByTask(task.id),
            staleTime: 60_000,
        }))
    });

    // Batch fetch agenda items for all meeting tasks
    const agendaQueries = useQueries({
        queries: allMeetingTasks.map(task => {
            const isRecurring = !!task.recurring_meeting_id;
            const eventDate = toDateTime(task.start_time!, timezone).toISODate() ?? '';
            return {
                queryKey: isRecurring
                    ? ['agenda-items', task.recurring_meeting_id, eventDate]
                    : ['task-agendas', task.id],
                queryFn: () => isRecurring
                    ? meetingAgendaApi.listByMeeting(task.recurring_meeting_id!, eventDate)
                    : meetingAgendaApi.listByTask(task.id),
                staleTime: 60_000,
            };
        })
    });

    // Build status map: taskId -> { hasAgenda, hasSummary, isConducted, sessionId, sessionStatus }
    const statusMap = useMemo(() => {
        const now = nowInTimezone(timezone);
        const map: Record<string, MeetingStatus> = {};

        allMeetingTasks.forEach((task, index) => {
            const session = sessionQueries[index]?.data as MeetingSession | null | undefined;
            const agendaItems = agendaQueries[index]?.data as MeetingAgendaItem[] | undefined;
            // end_time があればそれを基準に、なければ start_time で判定
            const referenceTime = task.end_time || task.start_time!;
            const meetingEnd = toDateTime(referenceTime, timezone);

            map[task.id] = {
                hasAgenda: Array.isArray(agendaItems) && agendaItems.length > 0,
                hasSummary: !!(session?.summary),
                isConducted: session ? session.status === 'COMPLETED' : meetingEnd < now,
                sessionId: session?.id,
                sessionStatus: session?.status,
            };
        });

        return map;
    }, [allMeetingTasks, sessionQueries, agendaQueries, timezone]);

    const queryClient = useQueryClient();
    const [statusDropdownTaskId, setStatusDropdownTaskId] = useState<string | null>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Close dropdown on outside click
    useEffect(() => {
        if (!statusDropdownTaskId) return;
        const handleClick = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setStatusDropdownTaskId(null);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [statusDropdownTaskId]);

    const statusOptions: { value: MeetingSessionStatus; label: string; badgeClass: string }[] = [
        { value: 'PREPARATION', label: '準備中', badgeClass: 'badge-upcoming' },
        { value: 'IN_PROGRESS', label: '会議中', badgeClass: 'badge-in-progress' },
        { value: 'COMPLETED', label: '実施済', badgeClass: 'badge-conducted' },
    ];

    // Mutation: update existing session status
    const updateStatusMutation = useMutation({
        mutationFn: async ({ sessionId, status }: { sessionId: string; status: MeetingSessionStatus }) => {
            return meetingSessionApi.update(sessionId, { status });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['meeting-session'] });
        },
    });

    // Mutation: create session then set status
    const createAndSetStatusMutation = useMutation({
        mutationFn: async ({ taskId, status }: { taskId: string; status: MeetingSessionStatus }) => {
            const session = await meetingSessionApi.create({ task_id: taskId });
            if (status !== 'PREPARATION') {
                return meetingSessionApi.update(session.id, { status });
            }
            return session;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['meeting-session'] });
        },
    });

    const handleStatusChange = useCallback((taskId: string, newStatus: MeetingSessionStatus) => {
        const meetingStatus = statusMap[taskId];
        if (meetingStatus?.sessionId) {
            updateStatusMutation.mutate({ sessionId: meetingStatus.sessionId, status: newStatus });
        } else {
            createAndSetStatusMutation.mutate({ taskId, status: newStatus });
        }
        setStatusDropdownTaskId(null);
    }, [statusMap, updateStatusMutation, createAndSetStatusMutation]);

    const formatDateLabel = (value: string | Date) =>
        formatDate(value, { month: 'numeric', day: 'numeric', weekday: 'short' }, timezone);

    const formatTimeLabel = (value: string | Date) =>
        formatDate(value, { hour: '2-digit', minute: '2-digit' }, timezone);

    const formatTimeDisplay = (task: Task) => {
        if (task.is_all_day) {
            return '終日';
        }
        return formatTimeLabel(task.start_time!);
    };

    const getDisplayStatus = (taskId: string): { label: string; badgeClass: string } => {
        const status = statusMap[taskId];
        if (!status) return { label: '未実施', badgeClass: 'badge-upcoming' };

        if (status.sessionStatus) {
            const option = statusOptions.find(o => o.value === status.sessionStatus);
            if (option) return { label: option.label, badgeClass: option.badgeClass };
        }
        return status.isConducted
            ? { label: '実施済', badgeClass: 'badge-conducted' }
            : { label: '未実施', badgeClass: 'badge-upcoming' };
    };

    const renderStatusBadges = (taskId: string) => {
        const status = statusMap[taskId];
        if (!status) return null;

        const display = getDisplayStatus(taskId);
        const isOpen = statusDropdownTaskId === taskId;

        return (
            <div className="meeting-nav-item-badges">
                <div className="meeting-status-dropdown-wrapper" ref={isOpen ? dropdownRef : undefined}>
                    <span
                        className={`meeting-badge ${display.badgeClass} meeting-badge-clickable`}
                        onClick={(e) => {
                            e.stopPropagation();
                            setStatusDropdownTaskId(isOpen ? null : taskId);
                        }}
                    >
                        {display.label}
                    </span>
                    {isOpen && (
                        <div className="meeting-status-dropdown">
                            {statusOptions.map((option) => (
                                <div
                                    key={option.value}
                                    className={`meeting-status-dropdown-item ${
                                        display.label === option.label ? 'active' : ''
                                    }`}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        handleStatusChange(taskId, option.value);
                                    }}
                                >
                                    <span className={`meeting-badge ${option.badgeClass}`}>
                                        {option.label}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                {status.hasAgenda && (
                    <span className="meeting-badge badge-agenda">アジェンダ</span>
                )}
                {status.hasSummary && (
                    <span className="meeting-badge badge-summary">サマリー</span>
                )}
            </div>
        );
    };

    const hasNoMeetings = Object.keys(recurringMeetingTasks).length === 0 && standaloneMeetings.length === 0;

    if (isLoading) {
        return (
            <div className="meetings-sidebar">
                <div className="meetings-sidebar-header">
                    <h3 className="meetings-sidebar-title">ミーティング一覧</h3>
                </div>
                <div className="meetings-sidebar-content">
                    <div className="p-4 text-gray-500">読み込み中...</div>
                </div>
            </div>
        );
    }

    if (hasNoMeetings) {
        return (
            <div className="meetings-sidebar">
                <div className="meetings-sidebar-header">
                    <h3 className="meetings-sidebar-title">ミーティング一覧</h3>
                </div>
                <div className="meetings-sidebar-content">
                    <div className="p-4 text-gray-500">ミーティングがありません。</div>
                </div>
            </div>
        );
    }

    return (
        <div className="meetings-sidebar">
            <div className="meetings-sidebar-header">
                <h3 className="meetings-sidebar-title">ミーティング一覧</h3>
            </div>
            <div className="meetings-sidebar-content">
                {/* Recurring meeting tasks */}
                {Object.entries(recurringMeetingTasks).map(([rmId, { recurringMeeting, tasks }]) => (
                    <div key={rmId} className="meeting-nav-group">
                        <div className="meeting-nav-title">
                            <FaRedo className="meeting-nav-title-icon" />
                            {recurringMeeting.title}
                        </div>
                        {tasks.map((task) => {
                            const date = toDateTime(task.start_time!, timezone);
                            const isSelected = selectedTask?.id === task.id;
                            return (
                                <div
                                    key={task.id}
                                    className={`meeting-nav-item ${isSelected ? 'active' : ''}`}
                                    onClick={() => onSelectTask(task, date.toJSDate())}
                                >
                                    <div className="meeting-nav-item-content">
                                        <span>{formatDateLabel(task.start_time!)}</span>
                                        <span className="meeting-nav-item-time">{formatTimeDisplay(task)}</span>
                                    </div>
                                    {renderStatusBadges(task.id)}
                                </div>
                            );
                        })}
                    </div>
                ))}

                {/* Standalone meetings */}
                {standaloneMeetings.length > 0 && (
                    <div className="meeting-nav-group">
                        <div className="meeting-nav-title">
                            <FaCalendarDay className="meeting-nav-title-icon" />
                            単発ミーティング
                        </div>
                        {standaloneMeetings.map((task) => {
                            const date = toDateTime(task.start_time!, timezone);
                            const isSelected = selectedTask?.id === task.id;
                            return (
                                <div
                                    key={task.id}
                                    className={`meeting-nav-item ${isSelected ? 'active' : ''}`}
                                    onClick={() => onSelectTask(task, date.toJSDate())}
                                >
                                    <div className="meeting-nav-item-content">
                                        <span>{formatDateLabel(task.start_time!)}</span>
                                        <span className="meeting-nav-item-time">{formatTimeDisplay(task)}</span>
                                    </div>
                                    <div className="meeting-nav-item-title">{task.title}</div>
                                    {renderStatusBadges(task.id)}
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
