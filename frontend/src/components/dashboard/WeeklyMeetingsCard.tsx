import { useMemo, useRef, useState, useEffect, useCallback } from 'react';
import type { CSSProperties } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { tasksApi } from '../../api/tasks';
import type { Task } from '../../api/types';
import { useCapacitySettings } from '../../hooks/useCapacitySettings';
import { useBlockDragResize } from '../../hooks/useBlockDragResize';
import type { BlockInfo, GhostPosition } from '../../hooks/useBlockDragResize';
import { useTaskModal } from '../../hooks/useTaskModal';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateKey, toDateTime, todayInTimezone, nowInTimezone } from '../../utils/dateTime';
import { DEFAULT_WEEKLY_WORK_HOURS } from '../../utils/capacitySettings';
import { PostponePopover } from './PostponePopover';
import { CreateMeetingModal } from '../meetings/CreateMeetingModal';
import './WeeklyMeetingsCard.css';

const TEXT = {
  title: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb',
  tag: '\u30ab\u30ec\u30f3\u30c0\u30fc',
  empty: 'No meetings this week',
  loading: 'Loading...',
  error: 'Failed to load meetings',
  today: '\u4eca\u65e5',
  thisWeek: '\u4eca\u9031',
  prev: '<',
  next: '>',
  viewWeek: '\u9031\u9593',
  viewWorkdays: '\u7a3c\u50cd\u65e5',
  viewToday: '\u4eca\u65e5',
  recalc: '\u518d\u8a08\u7b97',
  recalculating: '\u518d\u8a08\u7b97\u4e2d...',
  recalcError: '\u518d\u8a08\u7b97\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  planForecast: '\u30d7\u30e9\u30f3\u672a\u751f\u6210',
  planStale: '\u672a\u53cd\u6620\u306e\u5909\u66f4',
  pendingLabel: '\u672a\u53cd\u6620',
  countUnit: '\u4ef6',
  pinnedOverflowTitle: '\u30d4\u30f3\u7559\u3081\u304c\u53ce\u307e\u3089\u306a\u3044\u30bf\u30b9\u30af\u304c\u3042\u308a\u307e\u3059',
  pinnedOverflowAction: '\u660e\u65e5\u306b\u56de\u3059',
  pinnedOverflowError: '\u660e\u65e5\u3078\u79fb\u52d5\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  dependencyAlert: '\u4f9d\u5b58\u30bf\u30b9\u30af\u304c\u5b8c\u4e86\u3057\u3066\u3044\u306a\u3044\u305f\u3081\u5b8c\u4e86\u3067\u304d\u307e\u305b\u3093',
  statusError: '\u30b9\u30c6\u30fc\u30bf\u30b9\u5909\u66f4\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  doTodayError: '\u4eca\u65e5\u3084\u308b\u306e\u8a2d\u5b9a\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
};

const DEFAULT_START_HOUR = 0;
const DEFAULT_END_HOUR = 24;
const MIN_START_HOUR = 0;
const MAX_END_HOUR = 24;
const MIN_HOUR_HEIGHT = 28;
const MAX_HOUR_HEIGHT = 120;
const DEFAULT_HOUR_HEIGHT = MAX_HOUR_HEIGHT;
const HOUR_ZOOM_STEP = 4;
const WARMUP_MINUTES = 15;
const DEFAULT_PLAN_DAYS = 30;

type ViewMode = 'week' | 'workdays' | 'today';

const VIEW_OPTIONS: { id: ViewMode; label: string }[] = [
  { id: 'week', label: TEXT.viewWeek },
  { id: 'workdays', label: TEXT.viewWorkdays },
  { id: 'today', label: TEXT.viewToday },
];

type WeeklyMeetingsCardProps = {
  embedded?: boolean;
  defaultViewMode?: ViewMode;
  onTaskClick?: (taskId: string) => void;
};

const toLocalDateKey = (date: Date, timezone: string) => toDateKey(date, timezone);

const startOfWeek = (date: ReturnType<typeof todayInTimezone>) => {
  const diff = date.weekday - 1;
  return date.minus({ days: diff }).startOf('day');
};

const formatDayLabel = (date: Date, timezone: string) => (
  formatDate(date, { month: 'numeric', day: 'numeric', weekday: 'short' }, timezone)
);

const formatRangeLabel = (start: Date, end: Date, timezone: string) => {
  const startLabel = formatDate(start, { month: 'numeric', day: 'numeric' }, timezone);
  const endLabel = formatDate(end, { month: 'numeric', day: 'numeric' }, timezone);
  return `${startLabel} - ${endLabel}`;
};

type MeetingBlock = {
  id: string;
  taskId: string;
  title: string;
  start: Date;
  end: Date;
  dayKey: string;
  startMinutes: number;
  endMinutes: number;
  lane: number;
  laneCount: number;
  location?: string;
  status: Task['status'];
  kind: 'meeting' | 'auto';
  pinnedDate?: string;
};

type DragHistoryEntry = {
  taskId: string;
  kind: 'meeting' | 'auto';
  before: { dayKey: string; startMinutes: number; endMinutes: number; iso: { start: string; end: string; date: string } };
  after:  { dayKey: string; startMinutes: number; endMinutes: number; iso: { start: string; end: string; date: string } };
};

const MAX_UNDO_HISTORY = 50;

const formatTime = (date: Date, timezone: string) => (
  formatDate(date, { hour: '2-digit', minute: '2-digit' }, timezone)
);

const parseTimeToMinutes = (value: string) => {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes)) return null;
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
};

type TimeInterval = {
  startMinutes: number;
  endMinutes: number;
};

type WorkdayConfig = {
  workWindow: TimeInterval[];
  taskIntervals: TimeInterval[];
  breaks: TimeInterval[];
};

const cloneIntervals = (intervals: TimeInterval[]) => (
  intervals.map(interval => ({ ...interval }))
);

const subtractIntervals = (base: TimeInterval[], remove: TimeInterval[]) => {
  if (remove.length === 0) return base;
  let intervals = base;
  remove.forEach(block => {
    intervals = intervals.flatMap(interval => {
      if (block.endMinutes <= interval.startMinutes || block.startMinutes >= interval.endMinutes) {
        return [interval];
      }
      const next: TimeInterval[] = [];
      if (block.startMinutes > interval.startMinutes) {
        next.push({
          startMinutes: interval.startMinutes,
          endMinutes: Math.min(block.startMinutes, interval.endMinutes),
        });
      }
      if (block.endMinutes < interval.endMinutes) {
        next.push({
          startMinutes: Math.max(block.endMinutes, interval.startMinutes),
          endMinutes: interval.endMinutes,
        });
      }
      return next;
    });
  });
  return intervals.filter(interval => interval.endMinutes > interval.startMinutes);
};

const getNonWorkIntervals = (
  workIntervals: TimeInterval[],
  startBound: number,
  endBound: number,
) => {
  if (endBound <= startBound) return [];
  if (workIntervals.length === 0) {
    return [{ startMinutes: startBound, endMinutes: endBound }];
  }
  return subtractIntervals([{ startMinutes: startBound, endMinutes: endBound }], workIntervals);
};

type LaneComputationBlock = {
  id: string;
  startMinutes: number;
  endMinutes: number;
};

const assignLaneMetadata = <T extends LaneComputationBlock>(
  blocks: T[],
): Array<T & { lane: number; laneCount: number }> => {
  const sorted = [...blocks].sort(
    (a, b) => a.startMinutes - b.startMinutes || a.endMinutes - b.endMinutes || a.id.localeCompare(b.id),
  );

  const groups: number[][] = [];
  let groupEnd = -Infinity;
  let currentGroup: number[] = [];
  sorted.forEach((item, idx) => {
    if (item.startMinutes >= groupEnd && currentGroup.length > 0) {
      groups.push(currentGroup);
      currentGroup = [];
    }
    currentGroup.push(idx);
    groupEnd = Math.max(groupEnd, item.endMinutes);
  });
  if (currentGroup.length > 0) groups.push(currentGroup);

  const lanesResult = new Array<{ lane: number; laneCount: number }>(sorted.length);
  for (const group of groups) {
    const laneEnds: number[] = [];
    for (const idx of group) {
      const item = sorted[idx];
      let laneIndex = laneEnds.findIndex(end => item.startMinutes >= end);
      if (laneIndex === -1) {
        laneIndex = laneEnds.length;
        laneEnds.push(item.endMinutes);
      } else {
        laneEnds[laneIndex] = item.endMinutes;
      }
      lanesResult[idx] = { lane: laneIndex, laneCount: 0 };
    }
    const laneCount = Math.max(1, laneEnds.length);
    for (const idx of group) {
      lanesResult[idx].laneCount = laneCount;
    }
  }

  return sorted.map((item, idx) => ({ ...item, ...lanesResult[idx] }));
};

export function WeeklyMeetingsCard({
  embedded = false,
  defaultViewMode = 'workdays',
  onTaskClick,
}: WeeklyMeetingsCardProps) {
  const queryClient = useQueryClient();
  const timezone = useTimezone();
  const {
    capacityHours,
    bufferHours,
    capacityByWeekday,
    weeklyWorkHours,
    breakAfterTaskMinutes,
  } = useCapacitySettings();
  const [viewMode, setViewMode] = useState<ViewMode>(defaultViewMode);
  const [weekOffset, setWeekOffset] = useState(0);
  const [dayOffset, setDayOffset] = useState(0);
  const [hourHeight, setHourHeight] = useState(DEFAULT_HOUR_HEIGHT);
  const [isSubmitting, setIsSubmitting] = useState<string | null>(null);
  const [localDoneIds, setLocalDoneIds] = useState<Set<string>>(new Set());
  const [doneOverrides, setDoneOverrides] = useState<Record<string, MeetingBlock[]>>({});
  const [dragOverrides, setDragOverrides] = useState<Record<string, MeetingBlock>>({});
  const [isPostponingPinned, setIsPostponingPinned] = useState(false);
  const [undoStack, setUndoStack] = useState<DragHistoryEntry[]>([]);
  const [redoStack, setRedoStack] = useState<DragHistoryEntry[]>([]);
  const isUndoRedoRef = useRef(false);
  const [showCreateMeeting, setShowCreateMeeting] = useState(false);
  const [createMeetingPrefill, setCreateMeetingPrefill] = useState<{
    date?: string;
    startTime?: string;
    endTime?: string;
  } | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const blocksRef = useRef<MeetingBlock[]>([]);

  const today = todayInTimezone(timezone);
  const todayKey = toDateKey(today.toJSDate(), timezone);
  const currentWeekStart = startOfWeek(today);
  const currentWeekStartKey = toDateKey(currentWeekStart.toJSDate(), timezone);
  const weekStart = useMemo(
    () => currentWeekStart.plus({ days: weekOffset * 7 }),
    [currentWeekStartKey, weekOffset],
  );
  const dayStart = useMemo(
    () => today.plus({ days: dayOffset }),
    [dayOffset, todayKey],
  );
  const viewStart = viewMode === 'today' ? dayStart : weekStart;
  const viewDaysCount = viewMode === 'today' ? 1 : viewMode === 'workdays' ? 5 : 7;
  const viewEnd = viewStart.plus({ days: viewDaysCount });
  const viewStartKey = toDateKey(viewStart.toJSDate(), timezone);
  const viewEndKey = toDateKey(viewEnd.toJSDate(), timezone);
  const viewStartDay = viewStart.startOf('day');
  const scheduleStartKey = toDateKey(viewStartDay.toJSDate(), timezone);
  const scheduleDaysCount = viewDaysCount;

  const isCurrentView = viewMode === 'today' ? dayOffset === 0 : weekOffset === 0;
  const goToPrevRange = () => {
    if (viewMode === 'today') {
      setDayOffset(prev => prev - 1);
    } else {
      setWeekOffset(prev => prev - 1);
    }
  };
  const goToNextRange = () => {
    if (viewMode === 'today') {
      setDayOffset(prev => prev + 1);
    } else {
      setWeekOffset(prev => prev + 1);
    }
  };
  const goToCurrentRange = () => {
    if (viewMode === 'today') {
      setDayOffset(0);
    } else {
      setWeekOffset(0);
    }
  };

  const days = useMemo(() => (
    Array.from({ length: viewDaysCount }, (_, index) => {
      return viewStart.plus({ days: index });
    })
  ), [viewStartKey, viewDaysCount]);
  const visibleDayKeys = useMemo(
    () => new Set(days.map(day => toLocalDateKey(day.toJSDate(), timezone))),
    [days, timezone],
  );

  const { data: scheduleData } = useQuery({
    queryKey: [
      'schedule',
      'view',
      viewMode,
      scheduleStartKey,
      scheduleDaysCount,
      capacityHours,
      bufferHours,
      capacityByWeekday,
    ],
    queryFn: () => tasksApi.getSchedule({
      startDate: scheduleStartKey,
      maxDays: scheduleDaysCount,
      capacityHours,
      bufferHours,
      capacityByWeekday,
      filterByAssignee: true,
    }),
    staleTime: Infinity,
    enabled: scheduleDaysCount > 0,
  });

  const { data: meetingTasks = [], isLoading, error, refetch } = useQuery({
    queryKey: ['meetings', 'view', viewMode, viewStartKey, viewDaysCount],
    queryFn: () => tasksApi.getAll({ includeDone: true, onlyMeetings: true }),
    staleTime: 30_000,
  });

  const recalcMutation = useMutation({
    mutationFn: () => tasksApi.recalculateSchedulePlan({
      fromNow: true,
      maxDays: DEFAULT_PLAN_DAYS,
      filterByAssignee: true,
    }),
    onSuccess: () => {
      setLocalDoneIds(new Set());
      setDoneOverrides({});
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
    onError: () => {
      alert(TEXT.recalcError);
    },
  });

  const invalidateAfterChange = (includeSchedule = false) => {
    const keys = [
      ['meetings'], ['tasks'], ['subtasks'], ['top3'], ['today-tasks'],
      ['task-detail'], ['task-assignments'], ['project'],
    ];
    if (includeSchedule) keys.push(['schedule']);
    for (const key of keys) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  // useTaskModal for modal management
  const taskModal = useTaskModal({
    tasks: meetingTasks,
    onRefetch: () => {
      refetch();
      invalidateAfterChange(true);
    },
  });
  const showTitle = !embedded;
  const handleTaskClick = (taskId: string) => {
    if (onTaskClick) {
      onTaskClick(taskId);
      return;
    }
    taskModal.openTaskDetailById(taskId);
  };

  const handleRecalculate = () => {
    if (recalcMutation.isPending) return;
    recalcMutation.mutate();
  };

  const captureDoneBlocks = useCallback((taskId: string) => {
    const blocks = blocksRef.current.filter(block => block.taskId === taskId);
    if (!blocks.length) return false;
    setDoneOverrides(prev => ({ ...prev, [taskId]: blocks.map(block => ({ ...block })) }));
    return true;
  }, []);

  const removeDoneOverride = useCallback((taskId: string) => {
    setDoneOverrides(prev => {
      if (!prev[taskId]) return prev;
      const next = { ...prev };
      delete next[taskId];
      return next;
    });
  }, []);

  const handleToggleComplete = async (taskId: string, currentStatus: Task['status'], e: React.MouseEvent) => {
    e.stopPropagation();
    if (isSubmitting) return;

    if (currentStatus === 'DONE') {
      setIsSubmitting(taskId);
      try {
        setLocalDoneIds(prev => { const next = new Set(prev); next.delete(taskId); return next; });
        await tasksApi.update(taskId, { status: 'TODO' });
        removeDoneOverride(taskId);
        invalidateAfterChange(true);
      } catch {
        alert(TEXT.statusError);
      } finally {
        setIsSubmitting(null);
      }
      return;
    }

    setIsSubmitting(taskId);
    const captured = captureDoneBlocks(taskId);
    try {
      const task = await tasksApi.getById(taskId);
      if (task.dependency_ids && task.dependency_ids.length > 0) {
        const deps = await Promise.all(
          task.dependency_ids.map(depId => tasksApi.getById(depId).catch(() => null))
        );
        const hasPending = deps.some(dep => !dep || dep.status !== 'DONE');
        if (hasPending) {
          alert(TEXT.dependencyAlert);
          if (captured) {
            removeDoneOverride(taskId);
          }
          setIsSubmitting(null);
          return;
        }
      }
      setLocalDoneIds(prev => new Set(prev).add(taskId));
      await tasksApi.update(taskId, { status: 'DONE' });
      invalidateAfterChange(true);
    } catch {
      if (captured) {
        removeDoneOverride(taskId);
      }
      setLocalDoneIds(prev => { const next = new Set(prev); next.delete(taskId); return next; });
      alert(TEXT.statusError);
    } finally {
      setIsSubmitting(null);
    }
  };

  const handleDoToday = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (isSubmitting) return;
    setIsSubmitting(taskId);
    try {
      await tasksApi.doToday(taskId, { pin: true });
      await tasksApi.recalculateSchedulePlan({
        fromNow: true,
        maxDays: DEFAULT_PLAN_DAYS,
        filterByAssignee: true,
      });
      invalidateAfterChange(true);
    } catch {
      alert(TEXT.doTodayError);
    } finally {
      setIsSubmitting(null);
    }
  };

  const handlePostponePinnedOverflow = async () => {
    if (isPostponingPinned || pinnedOverflowTasks.length === 0) return;
    setIsPostponingPinned(true);
    const tomorrowKey = toDateKey(today.plus({ days: 1 }).toJSDate(), timezone);
    try {
      await Promise.all(
        pinnedOverflowTasks.map(task =>
          tasksApi.postpone(task.id, { to_date: tomorrowKey, pin: true })
        )
      );
      invalidateAfterChange(true);
    } catch {
      alert(TEXT.pinnedOverflowError);
    } finally {
      setIsPostponingPinned(false);
    }
  };

  // Clear done-related optimistic state when fresh data arrives
  useEffect(() => {
    setLocalDoneIds(prev => prev.size > 0 ? new Set() : prev);
    setDoneOverrides(prev => Object.keys(prev).length > 0 ? {} : prev);
  }, [meetingTasks, scheduleData]);

  const meetingBlocksFromTasks = useMemo(() => {
    const viewStartDate = viewStart.startOf('day');
    const viewEndDate = viewEnd.startOf('day');

    return meetingTasks
      .filter(task => task.is_fixed_time && task.start_time && task.end_time)
      .map(task => {
        const start = toDateTime(task.start_time as string, timezone);
        const end = toDateTime(task.end_time as string, timezone);
        if (!start.isValid || !end.isValid) return null;
        if (start.toMillis() < viewStartDate.toMillis() || start.toMillis() >= viewEndDate.toMillis()) return null;
        const startMinutes = start.hour * 60 + start.minute;
        const endMinutesRaw = end.hour * 60 + end.minute;
        const endMinutes = Math.max(startMinutes + 15, endMinutesRaw);
        return {
          id: task.id,
          taskId: task.id,
          title: task.title,
          start: start.toJSDate(),
          end: end.toJSDate(),
          dayKey: toLocalDateKey(start.toJSDate(), timezone),
          startMinutes,
          endMinutes,
          lane: 0,
          laneCount: 1,
          location: task.location,
          status: task.status,
          kind: 'meeting',
        } satisfies MeetingBlock;
      })
      .filter(Boolean) as MeetingBlock[];
  }, [meetingTasks, viewStartKey, viewEndKey, timezone]);

  const meetingTaskIds = useMemo(() => new Set(meetingTasks.map(task => task.id)), [meetingTasks]);
  const scheduleTaskMap = useMemo(
    () => new Map((scheduleData?.tasks ?? []).map(task => [task.task_id, task])),
    [scheduleData?.tasks],
  );
  const meetingTaskMap = useMemo(
    () => new Map(meetingTasks.map(task => [task.id, task])),
    [meetingTasks],
  );
  const pendingChanges = scheduleData?.pending_changes ?? [];
  const pendingPreviewItems = pendingChanges.slice(0, 3);
  const pendingExtraCount = pendingChanges.length - pendingPreviewItems.length;
  const planState = scheduleData?.plan_state ?? 'forecast';
  const showPlanNotice = Boolean(scheduleData) && (planState === 'forecast' || (planState === 'stale' && pendingChanges.length > 0));
  const pinnedOverflowTasks = useMemo(() => {
    const overflowIds = scheduleData?.pinned_overflow_task_ids ?? [];
    if (overflowIds.length === 0) return [] as Array<{ id: string; title: string }>;
    return overflowIds
      .map(taskId => {
        const info = scheduleTaskMap.get(taskId);
        return {
          id: taskId,
          title: info?.title ?? '\u30bf\u30b9\u30af',
          pinnedDate: info?.pinned_date,
        };
      })
      .filter(item => item.pinnedDate && toDateKey(item.pinnedDate, timezone) === todayKey)
      .map(({ id, title }) => ({ id, title }));
  }, [scheduleData?.pinned_overflow_task_ids, scheduleTaskMap, timezone, todayKey]);
  const pinnedOverflowPreview = useMemo(() => {
    if (pinnedOverflowTasks.length === 0) return '';
    const labels = pinnedOverflowTasks.slice(0, 3).map(task => task.title);
    const extra = pinnedOverflowTasks.length - labels.length;
    return extra > 0 ? `${labels.join(' / ')} +${extra}${TEXT.countUnit}` : labels.join(' / ');
  }, [pinnedOverflowTasks]);

  const meetingIntervalsByDay = useMemo(() => {
    const grouped = new Map<string, TimeInterval[]>();
    meetingBlocksFromTasks.forEach(meeting => {
      const list = grouped.get(meeting.dayKey) ?? [];
      list.push({ startMinutes: meeting.startMinutes, endMinutes: meeting.endMinutes });
      grouped.set(meeting.dayKey, list);
    });
    return grouped;
  }, [meetingBlocksFromTasks]);

  // Meeting intervals derived from schedule data (independent of meetingTasks query)
  const scheduleMeetingIntervalsByDay = useMemo(() => {
    const grouped = new Map<string, TimeInterval[]>();
    (scheduleData?.tasks ?? []).forEach(task => {
      if (!task.is_fixed_time || !task.start_time || !task.end_time) return;
      const start = toDateTime(task.start_time, timezone);
      const end = toDateTime(task.end_time, timezone);
      if (!start.isValid || !end.isValid) return;
      const dayKey = toLocalDateKey(start.toJSDate(), timezone);
      const startMinutes = start.hour * 60 + start.minute;
      const endMinutes = Math.max(startMinutes + 15, end.hour * 60 + end.minute);
      const list = grouped.get(dayKey) ?? [];
      list.push({ startMinutes, endMinutes });
      grouped.set(dayKey, list);
    });
    return grouped;
  }, [scheduleData?.tasks, timezone]);

  const workdayConfigByDay = useMemo(() => {
    const resolvedWeekly = weeklyWorkHours ?? DEFAULT_WEEKLY_WORK_HOURS;
    const map = new Map<string, WorkdayConfig>();

    days.forEach(day => {
      const weekdayIndex = day.toJSDate().getDay();
      const config = resolvedWeekly[weekdayIndex] ?? DEFAULT_WEEKLY_WORK_HOURS[weekdayIndex];
      if (!config?.enabled) return;
      const startMinutes = parseTimeToMinutes(config.start);
      const endMinutes = parseTimeToMinutes(config.end);
      if (startMinutes == null || endMinutes == null || endMinutes <= startMinutes) return;
      const manualBreaks = (config.breaks ?? [])
        .map(entry => {
          const breakStart = parseTimeToMinutes(entry.start);
          const breakEnd = parseTimeToMinutes(entry.end);
          if (breakStart == null || breakEnd == null || breakEnd <= breakStart) return null;
          const overlapStart = Math.max(startMinutes, breakStart);
          const overlapEnd = Math.min(endMinutes, breakEnd);
          if (overlapEnd <= overlapStart) return null;
          return { startMinutes: overlapStart, endMinutes: overlapEnd };
        })
        .filter(Boolean) as TimeInterval[];
      const workWindow = [{ startMinutes, endMinutes }];
      const withoutManualBreaks = subtractIntervals(workWindow, manualBreaks);
      const warmupBreaks: TimeInterval[] = [];
      if (withoutManualBreaks.length > 0) {
        const first = withoutManualBreaks[0];
        const warmupEnd = Math.min(first.endMinutes, first.startMinutes + WARMUP_MINUTES);
        if (warmupEnd > first.startMinutes) {
          warmupBreaks.push({ startMinutes: first.startMinutes, endMinutes: warmupEnd });
        }
      }
      const withoutWarmup = subtractIntervals(withoutManualBreaks, warmupBreaks);
      const taskIntervals = withoutWarmup;
      map.set(toLocalDateKey(day.toJSDate(), timezone), {
        workWindow,
        taskIntervals,
        breaks: manualBreaks,
      });
    });

    return map;
  }, [days, timezone, weeklyWorkHours]);

  // Current time indicator state (updates every minute)
  const [nowMinutes, setNowMinutes] = useState(() => {
    const now = nowInTimezone(timezone);
    return now.hour * 60 + now.minute;
  });

  useEffect(() => {
    const tick = () => {
      const now = nowInTimezone(timezone);
      setNowMinutes(now.hour * 60 + now.minute);
    };
    const interval = setInterval(tick, 60_000);
    return () => clearInterval(interval);
  }, [timezone]);

  const planBlocks = useMemo(() => {
    if (!scheduleData?.time_blocks?.length) return [] as MeetingBlock[];
    const viewStartDate = viewStart.startOf('day');
    const viewEndDate = viewEnd.startOf('day');

    return scheduleData.time_blocks
      .map((block, index) => {
        const start = toDateTime(block.start, timezone);
        const end = toDateTime(block.end, timezone);
        if (!start.isValid || !end.isValid) return null;
        if (start.toMillis() < viewStartDate.toMillis() || start.toMillis() >= viewEndDate.toMillis()) {
          return null;
        }
        const startMinutes = start.hour * 60 + start.minute;
        const endMinutesRaw = end.hour * 60 + end.minute;
        const endMinutes = Math.max(startMinutes + 5, endMinutesRaw);
        const taskInfo = scheduleTaskMap.get(block.task_id);
        const meetingTask = meetingTaskMap.get(block.task_id);
        const statusValue = block.status ?? taskInfo?.status ?? meetingTask?.status;
        const normalizedStatus = statusValue === 'done' ? 'DONE' : statusValue;
        return {
          id: `${block.task_id}-${index}`,
          taskId: block.task_id,
          title: taskInfo?.title ?? meetingTask?.title ?? '\u30bf\u30b9\u30af',
          start: start.toJSDate(),
          end: end.toJSDate(),
          dayKey: toLocalDateKey(start.toJSDate(), timezone),
          startMinutes,
          endMinutes,
          lane: 0,
          laneCount: 1,
          location: meetingTask?.location,
          status: (normalizedStatus ?? 'TODO') as Task['status'],
          kind: meetingTask ? 'meeting' : (taskInfo?.is_fixed_time ? 'meeting' : block.kind),
          pinnedDate: block.pinned_date ?? taskInfo?.pinned_date ?? undefined,
        } satisfies MeetingBlock;
      })
      .filter(Boolean) as MeetingBlock[];
  }, [scheduleData?.time_blocks, scheduleTaskMap, meetingTaskMap, viewStartKey, viewEndKey, timezone]);

  const hasPlanBlocks = planBlocks.length > 0;

  const autoBlocksFromSchedule = useMemo(() => {
    if (hasPlanBlocks) return [] as MeetingBlock[];
    if (!scheduleData?.days || !scheduleData.tasks) return [] as MeetingBlock[];
    const scheduleDayMap = new Map(
      scheduleData.days.map(day => [toDateKey(day.date, timezone), day])
    );
    const blocks: MeetingBlock[] = [];

    days.forEach(day => {
      const dayKey = toLocalDateKey(day.toJSDate(), timezone);
      const scheduleDay = scheduleDayMap.get(dayKey);
      if (!scheduleDay || scheduleDay.task_allocations.length === 0) return;

      const baseWorkday = workdayConfigByDay.get(dayKey);
      const fallbackInterval: TimeInterval = {
        startMinutes: DEFAULT_START_HOUR * 60,
        endMinutes: DEFAULT_END_HOUR * 60,
      };
      let available = baseWorkday?.taskIntervals.length ? cloneIntervals(baseWorkday.taskIntervals) : [];
      if (available.length === 0) {
        available = [fallbackInterval];
      }

      const meetingIntervalsFromTasks = meetingIntervalsByDay.get(dayKey) ?? [];
      const meetingIntervalsFromSchedule = scheduleMeetingIntervalsByDay.get(dayKey) ?? [];
      const combinedMeetingIntervals = [...meetingIntervalsFromTasks, ...meetingIntervalsFromSchedule];
      available = subtractIntervals(available, combinedMeetingIntervals);

      let segmentIndex = 0;
      scheduleDay.task_allocations.forEach(allocation => {
        if (meetingTaskIds.has(allocation.task_id) || scheduleTaskMap.get(allocation.task_id)?.is_fixed_time) {
          return;
        }
        const taskInfo = scheduleTaskMap.get(allocation.task_id);
        if (!taskInfo) return;
        let remaining = allocation.minutes;
        while (remaining > 0 && available.length > 0) {
          const current = available[0];
          const duration = Math.min(remaining, current.endMinutes - current.startMinutes);
          if (duration <= 0) {
            available.shift();
            continue;
          }
          const startMinutes = current.startMinutes;
          const endMinutes = startMinutes + duration;
          const dayStart = day.startOf('day');
          const startDate = dayStart.plus({ minutes: startMinutes }).toJSDate();
          const endDate = dayStart.plus({ minutes: endMinutes }).toJSDate();
          blocks.push({
            id: `${allocation.task_id}-${segmentIndex}`,
            taskId: allocation.task_id,
            title: taskInfo.title,
            start: startDate,
            end: endDate,
            dayKey,
            startMinutes,
            endMinutes,
            lane: 0,
            laneCount: 1,
            status: ((taskInfo.status ?? '').toUpperCase() === 'DONE' ? 'DONE' : 'TODO') as Task['status'],
            kind: 'auto',
            pinnedDate: taskInfo.pinned_date ?? undefined,
          });
          segmentIndex += 1;
          remaining -= duration;
          const nextStartMinutes = remaining <= 0
            ? endMinutes + breakAfterTaskMinutes
            : endMinutes;
          current.startMinutes = nextStartMinutes;
          if (current.startMinutes >= current.endMinutes) {
            available.shift();
          }
        }
      });
    });

    return blocks;
  }, [
    hasPlanBlocks,
    days,
    meetingIntervalsByDay,
    scheduleMeetingIntervalsByDay,
    scheduleData?.days,
    scheduleData?.tasks,
    timezone,
    workdayConfigByDay,
    meetingTaskIds,
    breakAfterTaskMinutes,
    scheduleTaskMap,
  ]);

  const autoBlocks = useMemo(
    () => (hasPlanBlocks ? planBlocks.filter(block => block.kind === 'auto') : autoBlocksFromSchedule),
    [hasPlanBlocks, planBlocks, autoBlocksFromSchedule],
  );
  const meetingBlocks = useMemo(
    () => (hasPlanBlocks ? planBlocks.filter(block => block.kind === 'meeting') : meetingBlocksFromTasks),
    [hasPlanBlocks, planBlocks, meetingBlocksFromTasks],
  );
  // Keep drag overrides until base data reflects the moved position.
  // This avoids a snapback when unrelated queries resolve first.
  useEffect(() => {
    setDragOverrides(prev => {
      if (Object.keys(prev).length === 0) return prev;
      let changed = false;
      const next: Record<string, MeetingBlock> = {};
      for (const [key, override] of Object.entries(prev)) {
        const source = override.kind === 'meeting' ? meetingBlocks : autoBlocks;
        const synced = source.some(block =>
          block.taskId === override.taskId
          && block.dayKey === override.dayKey
          && block.startMinutes === override.startMinutes
          && block.endMinutes === override.endMinutes
        );
        if (synced) {
          changed = true;
        } else {
          next[key] = override;
        }
      }
      return changed ? next : prev;
    });
  }, [meetingBlocks, autoBlocks]);
  const doneOverrideBlocks = useMemo(() => {
    const overrides = Object.values(doneOverrides).flat();
    if (!overrides.length) {
      return { auto: [] as MeetingBlock[], meeting: [] as MeetingBlock[] };
    }
    const auto: MeetingBlock[] = [];
    const meeting: MeetingBlock[] = [];
    overrides.forEach(block => {
      if (!visibleDayKeys.has(block.dayKey)) return;
      if (block.kind === 'meeting') {
        meeting.push(block);
      } else {
        auto.push(block);
      }
    });
    return { auto, meeting };
  }, [doneOverrides, visibleDayKeys]);
  const dragOverrideBlocks = useMemo(() => {
    const overrides = Object.values(dragOverrides);
    if (!overrides.length) {
      return { auto: [] as MeetingBlock[], meeting: [] as MeetingBlock[] };
    }
    const auto: MeetingBlock[] = [];
    const meeting: MeetingBlock[] = [];
    overrides.forEach(block => {
      if (block.kind === 'meeting') {
        meeting.push(block);
      } else {
        auto.push(block);
      }
    });
    return { auto, meeting };
  }, [dragOverrides]);

  const renderAutoBlocks = useMemo(() => {
    let result = autoBlocks;
    if (doneOverrideBlocks.auto.length) {
      const overrideIds = new Set(doneOverrideBlocks.auto.map(block => block.taskId));
      result = [
        ...result.filter(block => !overrideIds.has(block.taskId)),
        ...doneOverrideBlocks.auto,
      ];
    }
    if (dragOverrideBlocks.auto.length) {
      const overrideIds = new Set(dragOverrideBlocks.auto.map(block => block.id));
      result = [
        ...result.filter(block => !overrideIds.has(block.id)),
        ...dragOverrideBlocks.auto,
      ];
    }
    return result;
  }, [autoBlocks, doneOverrideBlocks.auto, dragOverrideBlocks.auto]);
  const renderMeetingBlocks = useMemo(() => {
    let result = meetingBlocks;
    if (doneOverrideBlocks.meeting.length) {
      const overrideIds = new Set(doneOverrideBlocks.meeting.map(block => block.taskId));
      result = [
        ...result.filter(block => !overrideIds.has(block.taskId)),
        ...doneOverrideBlocks.meeting,
      ];
    }
    if (dragOverrideBlocks.meeting.length) {
      const overrideIds = new Set(dragOverrideBlocks.meeting.map(block => block.id));
      result = [
        ...result.filter(block => !overrideIds.has(block.id)),
        ...dragOverrideBlocks.meeting,
      ];
    }
    return result;
  }, [meetingBlocks, doneOverrideBlocks.meeting, dragOverrideBlocks.meeting]);

  useEffect(() => {
    blocksRef.current = [...renderAutoBlocks, ...renderMeetingBlocks];
  }, [renderAutoBlocks, renderMeetingBlocks]);

  const blocksByDay = useMemo(() => {
    const grouped = new Map<string, MeetingBlock[]>();
    [...renderAutoBlocks, ...renderMeetingBlocks].forEach(block => {
      const list = grouped.get(block.dayKey) ?? [];
      list.push({ ...block });
      grouped.set(block.dayKey, list);
    });

    const results = new Map<string, MeetingBlock[]>();
    grouped.forEach((list, dayKey) => {
      results.set(dayKey, assignLaneMetadata(list));
    });

    return results;
  }, [renderAutoBlocks, renderMeetingBlocks]);

  const timeBounds = useMemo(() => {
    const workdayBounds = Array.from(workdayConfigByDay.values()).reduce<TimeInterval | null>(
      (acc, current) => {
        if (!current.workWindow.length) return acc;
        const minStart = Math.min(...current.workWindow.map(interval => interval.startMinutes));
        const maxEnd = Math.max(...current.workWindow.map(interval => interval.endMinutes));
        if (!acc) return { startMinutes: minStart, endMinutes: maxEnd };
        return {
          startMinutes: Math.min(acc.startMinutes, minStart),
          endMinutes: Math.max(acc.endMinutes, maxEnd),
        };
      },
      null
    );
    const allBlocks = [...renderMeetingBlocks, ...renderAutoBlocks];
    if (!allBlocks.length && !workdayBounds) {
      return { startHour: DEFAULT_START_HOUR, endHour: DEFAULT_END_HOUR };
    }
    const minStart = allBlocks.length
      ? Math.min(...allBlocks.map(block => block.startMinutes))
      : (workdayBounds?.startMinutes ?? DEFAULT_START_HOUR * 60);
    const maxEnd = allBlocks.length
      ? Math.max(...allBlocks.map(block => block.endMinutes))
      : (workdayBounds?.endMinutes ?? DEFAULT_END_HOUR * 60);
    const effectiveMinStart = workdayBounds
      ? Math.min(workdayBounds.startMinutes, minStart)
      : minStart;
    const effectiveMaxEnd = workdayBounds
      ? Math.max(workdayBounds.endMinutes, maxEnd)
      : maxEnd;
    let startHour = Math.min(DEFAULT_START_HOUR, Math.floor(effectiveMinStart / 60));
    let endHour = Math.max(DEFAULT_END_HOUR, Math.ceil(effectiveMaxEnd / 60));
    startHour = Math.max(MIN_START_HOUR, startHour);
    endHour = Math.min(MAX_END_HOUR, Math.max(startHour + 1, endHour));
    return { startHour, endHour };
  }, [renderAutoBlocks, renderMeetingBlocks, workdayConfigByDay]);

  const hourCount = timeBounds.endHour - timeBounds.startHour;
  const hours = useMemo(() => (
    Array.from({ length: hourCount }, (_, index) => timeBounds.startHour + index)
  ), [hourCount, timeBounds.startHour]);

  const rangeLabel = useMemo(() => {
    if (viewMode === 'today') {
      return formatDate(viewStart.toJSDate(), { month: 'numeric', day: 'numeric', weekday: 'short' }, timezone);
    }
    const viewEndDate = viewEnd.minus({ days: 1 });
    return formatRangeLabel(viewStart.toJSDate(), viewEndDate.toJSDate(), timezone);
  }, [viewMode, viewStartKey, viewEndKey, timezone]);
  const gridHeight = hourCount * hourHeight;
  const scheduleHasItems = renderMeetingBlocks.length > 0 || renderAutoBlocks.length > 0;

  const viewIncludestoday = visibleDayKeys.has(todayKey);
  const currentTimeInBounds =
    nowMinutes >= timeBounds.startHour * 60 && nowMinutes < timeBounds.endHour * 60;

  // Compute first workday start minute for non-today views
  const firstWorkdayStartMinutes = useMemo(() => {
    for (const day of days) {
      const dayKey = toLocalDateKey(day.toJSDate(), timezone);
      const config = workdayConfigByDay.get(dayKey);
      if (config?.workWindow.length) {
        return Math.min(...config.workWindow.map(w => w.startMinutes));
      }
    }
    return null;
  }, [days, timezone, workdayConfigByDay]);

  // Auto-scroll to appropriate position based on view
  const hasAutoScrolled = useRef(false);
  const scrollToInitialPosition = useCallback(() => {
    const grid = gridRef.current;
    if (!grid) return;
    const startBound = timeBounds.startHour * 60;
    const viewportHeight = grid.clientHeight;

    if (viewIncludestoday && currentTimeInBounds) {
      // Today is visible: scroll to current time at ~30% from top
      const currentOffset = ((nowMinutes - startBound) / 60) * hourHeight;
      const targetScroll = currentOffset - viewportHeight * 0.3;
      grid.scrollTop = Math.max(0, targetScroll);
    } else if (firstWorkdayStartMinutes != null) {
      // Non-today view: scroll to first workday start at ~10% from top
      const workdayOffset = ((firstWorkdayStartMinutes - startBound) / 60) * hourHeight;
      const targetScroll = workdayOffset - viewportHeight * 0.1;
      grid.scrollTop = Math.max(0, targetScroll);
    }
  }, [viewIncludestoday, currentTimeInBounds, timeBounds.startHour, nowMinutes, hourHeight, firstWorkdayStartMinutes]);

  // Reset scroll flag when view or navigation changes
  useEffect(() => {
    hasAutoScrolled.current = false;
  }, [viewMode, viewStartKey]);

  useEffect(() => {
    if (!hasAutoScrolled.current && scheduleHasItems) {
      // Small delay to ensure DOM is rendered
      requestAnimationFrame(() => {
        scrollToInitialPosition();
        hasAutoScrolled.current = true;
      });
    }
  }, [scheduleHasItems, scrollToInitialPosition]);

  useEffect(() => {
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      const grid = gridRef.current;
      if (!grid || !(event.target instanceof Node) || !grid.contains(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      const direction = event.deltaY > 0 ? -1 : 1;
      setHourHeight(prev => {
        const next = prev + direction * HOUR_ZOOM_STEP;
        return Math.min(MAX_HOUR_HEIGHT, Math.max(MIN_HOUR_HEIGHT, next));
      });
    };
    window.addEventListener('wheel', handleWheel, { passive: false, capture: true });
    return () => window.removeEventListener('wheel', handleWheel, { capture: true });
  }, []);

  // 笏笏 Create Meeting from Calendar 笏笏

  const clickYToTime = useCallback((clientY: number, columnEl: Element): string => {
    const rect = columnEl.getBoundingClientRect();
    const offsetY = clientY - rect.top + (gridRef.current?.scrollTop ?? 0);
    const rawMinutes = timeBounds.startHour * 60 + (offsetY / hourHeight) * 60;
    const snapped = Math.round(rawMinutes / 15) * 15;
    const clamped = Math.max(0, Math.min(23 * 60 + 45, snapped));
    const h = Math.floor(clamped / 60);
    const m = clamped % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  }, [timeBounds.startHour, hourHeight]);

  const handleDayDoubleClick = useCallback((e: React.MouseEvent, dayKey: string) => {
    const target = e.target as HTMLElement;
    if (target.closest('.weekly-meeting-block')) return;

    const column = e.currentTarget as HTMLElement;
    const startTime = clickYToTime(e.clientY, column);
    const startMinutes = parseInt(startTime.split(':')[0]) * 60 + parseInt(startTime.split(':')[1]);
    const endMinutes = Math.min(24 * 60 - 1, startMinutes + 60);
    const endH = Math.floor(endMinutes / 60);
    const endM = endMinutes % 60;
    const endTime = `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`;

    setCreateMeetingPrefill({ date: dayKey, startTime, endTime });
    setShowCreateMeeting(true);
  }, [clickYToTime]);

  // 笏笏 Drag & Resize 笏笏

  /** Shared helper: move a block with optimistic update + API call */
  const executeBlockMove = useCallback(
    async (
      taskId: string,
      kind: 'meeting' | 'auto',
      from: { dayKey: string; startMinutes: number; endMinutes: number },
      to: { dayKey: string; startMinutes: number; endMinutes: number; isoStart: string; isoEnd: string; date: string },
    ) => {
      // Find current block for optimistic update
      const sourceBlock = blocksRef.current.find(
        b => b.taskId === taskId && b.dayKey === from.dayKey,
      );
      const overrideKey = sourceBlock?.id ?? `${taskId}-undo`;
      const toDayDate = days.find(d => toLocalDateKey(d.toJSDate(), timezone) === to.dayKey);
      const toDayStart = toDayDate?.startOf('day');

      if (sourceBlock && toDayStart) {
        setDragOverrides(prev => ({
          ...prev,
          [overrideKey]: {
            ...sourceBlock,
            dayKey: to.dayKey,
            startMinutes: to.startMinutes,
            endMinutes: to.endMinutes,
            start: toDayStart.plus({ minutes: to.startMinutes }).toJSDate(),
            end: toDayStart.plus({ minutes: to.endMinutes }).toJSDate(),
          },
        }));
      }

      const clearOverride = () => {
        setDragOverrides(prev => {
          if (!prev[overrideKey]) return prev;
          const next = { ...prev };
          delete next[overrideKey];
          return next;
        });
      };

      try {
        if (hasPlanBlocks) {
          await tasksApi.moveTimeBlock({
            task_id: taskId,
            original_date: to.date,
            new_start: to.isoStart,
            new_end: to.isoEnd,
          });
        } else if (kind === 'meeting') {
          await tasksApi.update(taskId, { start_time: to.isoStart, end_time: to.isoEnd });
        } else {
          clearOverride();
          return false;
        }
        // Don't clear override here - let the useEffect clear it when new data arrives.
        // This prevents the block from snapping back to the old position
        // during the gap between override removal and refetch completion.
        invalidateAfterChange(true);
        return true;
      } catch {
        clearOverride();
        return false;
      }
    },
    [days, timezone, hasPlanBlocks, invalidateAfterChange],
  );

  const handleBlockDrop = useCallback(
    async (block: BlockInfo, target: GhostPosition) => {
      const dayDate = days.find(d => toLocalDateKey(d.toJSDate(), timezone) === target.dayKey);
      if (!dayDate) return;
      const dayStart = dayDate.startOf('day');
      const newStart = dayStart.plus({ minutes: target.startMinutes }).toISO()!;
      const newEnd = dayStart.plus({ minutes: target.endMinutes }).toISO()!;

      const origDayDate = days.find(d => toLocalDateKey(d.toJSDate(), timezone) === block.dayKey);
      const originalDate = toDateKey(
        origDayDate?.toJSDate() ?? new Date(),
        timezone,
      );
      const origDayStart = origDayDate?.startOf('day');
      const origIsoStart = origDayStart
        ? origDayStart.plus({ minutes: block.startMinutes }).toISO()!
        : '';
      const origIsoEnd = origDayStart
        ? origDayStart.plus({ minutes: block.endMinutes }).toISO()!
        : '';
      const targetDate = toDateKey(dayDate.toJSDate(), timezone);

      const entry: DragHistoryEntry = {
        taskId: block.taskId,
        kind: block.kind,
        before: {
          dayKey: block.dayKey,
          startMinutes: block.startMinutes,
          endMinutes: block.endMinutes,
          iso: { start: origIsoStart, end: origIsoEnd, date: originalDate },
        },
        after: {
          dayKey: target.dayKey,
          startMinutes: target.startMinutes,
          endMinutes: target.endMinutes,
          iso: { start: newStart, end: newEnd, date: targetDate },
        },
      };

      const ok = await executeBlockMove(
        block.taskId,
        block.kind,
        { dayKey: block.dayKey, startMinutes: block.startMinutes, endMinutes: block.endMinutes },
        { dayKey: target.dayKey, startMinutes: target.startMinutes, endMinutes: target.endMinutes, isoStart: newStart, isoEnd: newEnd, date: originalDate },
      );

      if (ok && !isUndoRedoRef.current) {
        setUndoStack(prev => [...prev.slice(-(MAX_UNDO_HISTORY - 1)), entry]);
        setRedoStack([]);
      }
    },
    [days, timezone, executeBlockMove],
  );

  const handleUndo = useCallback(async () => {
    if (undoStack.length === 0) return;
    const entry = undoStack[undoStack.length - 1];
    isUndoRedoRef.current = true;
    try {
      const ok = await executeBlockMove(
        entry.taskId,
        entry.kind,
        { dayKey: entry.after.dayKey, startMinutes: entry.after.startMinutes, endMinutes: entry.after.endMinutes },
        { ...entry.before, isoStart: entry.before.iso.start, isoEnd: entry.before.iso.end, date: entry.after.iso.date },
      );
      if (ok) {
        setUndoStack(prev => prev.slice(0, -1));
        setRedoStack(prev => [...prev, entry]);
      }
    } finally {
      setTimeout(() => { isUndoRedoRef.current = false; }, 100);
    }
  }, [undoStack, executeBlockMove]);

  const handleRedo = useCallback(async () => {
    if (redoStack.length === 0) return;
    const entry = redoStack[redoStack.length - 1];
    isUndoRedoRef.current = true;
    try {
      const ok = await executeBlockMove(
        entry.taskId,
        entry.kind,
        { dayKey: entry.before.dayKey, startMinutes: entry.before.startMinutes, endMinutes: entry.before.endMinutes },
        { ...entry.after, isoStart: entry.after.iso.start, isoEnd: entry.after.iso.end, date: entry.before.iso.date },
      );
      if (ok) {
        setRedoStack(prev => prev.slice(0, -1));
        setUndoStack(prev => [...prev, entry]);
      }
    } finally {
      setTimeout(() => { isUndoRedoRef.current = false; }, 100);
    }
  }, [redoStack, executeBlockMove]);

  // Keyboard shortcuts: Ctrl+Z / Ctrl+Y (Cmd on Mac)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;

      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        handleRedo();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleUndo, handleRedo]);

  const {
    ghost: dragGhost,
    activeBlockId: draggingBlockId,
    isDragging,
    startInteraction,
  } = useBlockDragResize({
    hourHeight,
    startBoundHour: timeBounds.startHour,
    endBoundHour: timeBounds.endHour,
    onDrop: handleBlockDrop,
    onClick: (block) => handleTaskClick(block.taskId),
  });
  const dragPreview = useMemo(() => {
    if (!dragGhost || !draggingBlockId) return null;

    const sourceBlock = [...blocksByDay.values()]
      .flat()
      .find(block => block.id === draggingBlockId)
      ?? renderAutoBlocks.find(block => block.id === draggingBlockId)
      ?? renderMeetingBlocks.find(block => block.id === draggingBlockId);
    if (!sourceBlock) return null;

    const previewByDay = new Map<string, MeetingBlock[]>();
    blocksByDay.forEach((list, key) => {
      previewByDay.set(key, list.map(block => ({ ...block })));
    });

    const targetDayKey = dragGhost.dayKey;
    const ghostId = `${draggingBlockId}__ghost`;
    const targetDayBlocks = (previewByDay.get(targetDayKey) ?? []).filter(
      block => block.id !== draggingBlockId,
    );
    const withGhost = assignLaneMetadata([
      ...targetDayBlocks.map(block => ({
        id: block.id,
        startMinutes: block.startMinutes,
        endMinutes: block.endMinutes,
      })),
      {
        id: ghostId,
        startMinutes: dragGhost.startMinutes,
        endMinutes: dragGhost.endMinutes,
      },
    ]);
    const laneByBlockId = new Map(
      withGhost
        .filter(block => block.id !== ghostId)
        .map(block => [block.id, block] as const),
    );
    const relayoutBlocks = targetDayBlocks.map(block => {
      const lane = laneByBlockId.get(block.id);
      if (!lane) return block;
      return { ...block, lane: lane.lane, laneCount: lane.laneCount };
    });
    if (sourceBlock.dayKey === targetDayKey) {
      const sourceInOriginal = (blocksByDay.get(sourceBlock.dayKey) ?? []).find(
        block => block.id === draggingBlockId,
      );
      if (sourceInOriginal) {
        relayoutBlocks.push(sourceInOriginal);
      }
    }
    previewByDay.set(
      targetDayKey,
      relayoutBlocks.sort(
        (a, b) => a.startMinutes - b.startMinutes || a.lane - b.lane || a.id.localeCompare(b.id),
      ),
    );
    const ghost = withGhost.find(block => block.id === ghostId);
    return {
      blocksByDay: previewByDay,
      ghost: {
        lane: ghost?.lane ?? 0,
        laneCount: ghost?.laneCount ?? 1,
        kind: sourceBlock.kind,
      },
    };
  }, [dragGhost, draggingBlockId, blocksByDay, renderAutoBlocks, renderMeetingBlocks]);

  return (
    <div className={`weekly-meetings-card ${embedded ? 'embedded' : ''}`}>
      <div className="card-header weekly-meetings-header">
        <div className="weekly-meetings-title">
          <div className="weekly-meetings-title-row">
            {showTitle && (
              <div className="weekly-meetings-title-group">
                <h3>{TEXT.title}</h3>
                <span className="tag info">{TEXT.tag}</span>
              </div>
            )}
            <div className="weekly-meetings-view-tabs">
              {VIEW_OPTIONS.map(option => (
                <button
                  key={option.id}
                  type="button"
                  className={`weekly-meetings-view-tab ${viewMode === option.id ? 'active' : ''}`}
                  onClick={() => setViewMode(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="weekly-meetings-nav">
            <button
              type="button"
              className="weekly-meetings-nav-btn"
              onClick={goToPrevRange}
              aria-label={viewMode === 'today' ? 'Previous day' : 'Previous week'}
            >
              {TEXT.prev}
            </button>
            <span className="weekly-meetings-range">{rangeLabel}</span>
            <button
              type="button"
              className="weekly-meetings-nav-btn"
              onClick={goToNextRange}
              aria-label={viewMode === 'today' ? 'Next day' : 'Next week'}
            >
              {TEXT.next}
            </button>
            {!isCurrentView && (
              <button
                type="button"
                className="weekly-meetings-today-btn"
                onClick={goToCurrentRange}
              >
                {viewMode === 'today' ? TEXT.today : TEXT.thisWeek}
              </button>
            )}
            <button
              type="button"
              className="weekly-meetings-reschedule-btn"
              onClick={handleRecalculate}
              disabled={recalcMutation.isPending}
            >
              {recalcMutation.isPending ? TEXT.recalculating : TEXT.recalc}
            </button>
            <button
              type="button"
              className="weekly-meetings-add-btn"
              onClick={() => {
                setCreateMeetingPrefill(null);
                setShowCreateMeeting(true);
              }}
              title="繝溘・繝・ぅ繝ｳ繧ｰ繧剃ｽ懈・"
            >
              +
            </button>
          </div>
        </div>
      </div>

      {showPlanNotice && (
        <div className={`weekly-plan-banner ${planState}`}>
          <div className="weekly-plan-icon">
            {planState === 'forecast' ? '笳・ : '笳・}
          </div>
          <div className="weekly-plan-banner-text">
            <span className="weekly-plan-badge">
              {planState === 'forecast' ? TEXT.planForecast : TEXT.planStale}
            </span>
            {planState === 'stale' && pendingChanges.length > 0 && (
              <span className="weekly-plan-count">
                {pendingChanges.length}{TEXT.countUnit}
              </span>
            )}
            {pendingPreviewItems.length > 0 && (
              <span className="weekly-plan-preview">
                {pendingPreviewItems.map((change, i) => (
                  <span key={change.task_id}>
                    {i > 0 && ' / '}
                    <button
                      type="button"
                      className="weekly-plan-task-link"
                      onClick={(e) => { e.stopPropagation(); onTaskClick?.(change.task_id); }}
                    >
                      {change.title}
                    </button>
                  </span>
                ))}
                {pendingExtraCount > 0 && ` +${pendingExtraCount}${TEXT.countUnit}`}
              </span>
            )}
          </div>
        </div>
      )}

      {pinnedOverflowTasks.length > 0 && (
        <div className="weekly-pinned-overflow">
          <div className="weekly-pinned-overflow-text">
            <span className="weekly-pinned-overflow-title">{TEXT.pinnedOverflowTitle}</span>
            {pinnedOverflowPreview && (
              <span className="weekly-pinned-overflow-preview">{pinnedOverflowPreview}</span>
            )}
          </div>
          <button
            type="button"
            className="weekly-pinned-overflow-btn"
            onClick={handlePostponePinnedOverflow}
            disabled={isPostponingPinned}
          >
            {TEXT.pinnedOverflowAction}
          </button>
        </div>
      )}

      {error && <div className="error-message">{TEXT.error}</div>}
      {isLoading && <div className="loading-state">{TEXT.loading}</div>}
      {!isLoading && !error && !scheduleHasItems && (
        <div className="weekly-meetings-empty">{TEXT.empty}</div>
      )}

      {!isLoading && !error && scheduleHasItems && (
        <div className={`weekly-meetings-grid${isDragging ? ' is-dragging' : ''}`} ref={gridRef}>
          <div className="weekly-meetings-header-row" style={{ '--days': days.length } as CSSProperties}>
            <div className="weekly-meetings-time-header" />
            {days.map(day => {
              const dayKey = toLocalDateKey(day.toJSDate(), timezone);
              const isToday = dayKey === todayKey;
              return (
                <div key={dayKey} className={`weekly-meetings-day-header ${isToday ? 'today' : ''}`}>
                  {formatDayLabel(day.toJSDate(), timezone)}
                </div>
              );
            })}
          </div>
          <div className="weekly-meetings-body" style={{ '--days': days.length, '--hour-height': `${hourHeight}px` } as CSSProperties}>
            <div className="weekly-meetings-time-col">
              {hours.map(hour => (
                <div key={hour} className="weekly-meetings-time-slot">
                  {String(hour).padStart(2, '0')}:00
                </div>
              ))}
            </div>
            {days.map(day => {
              const dayKey = toLocalDateKey(day.toJSDate(), timezone);
              const isToday = dayKey === todayKey;
              const dayBlocks = dragPreview?.blocksByDay.get(dayKey) ?? blocksByDay.get(dayKey) ?? [];
              const workdayConfig = workdayConfigByDay.get(dayKey);
              const startBound = timeBounds.startHour * 60;
              const endBound = timeBounds.endHour * 60;
              const nonWorkIntervals = getNonWorkIntervals(
                workdayConfig?.workWindow ?? [],
                startBound,
                endBound,
              );
              return (
                <div key={dayKey} data-day-key={dayKey} className={`weekly-meetings-day-col ${isToday ? 'today' : ''}${dragGhost?.dayKey === dayKey ? ' drop-target' : ''}`} style={{ height: `${gridHeight}px` }} onDoubleClick={(e) => handleDayDoubleClick(e, dayKey)}>
                  <div className="weekly-workhours-layer">
                    {nonWorkIntervals.map(interval => {
                      const clampedStart = Math.max(startBound, interval.startMinutes);
                      const clampedEnd = Math.min(endBound, interval.endMinutes);
                      if (clampedEnd <= clampedStart) return null;
                        const top = ((clampedStart - startBound) / 60) * hourHeight;
                        const height = Math.max(1, ((clampedEnd - clampedStart) / 60) * hourHeight);
                      return (
                        <div
                          key={`${dayKey}-off-${interval.startMinutes}`}
                          className="weekly-nonwork-block"
                          style={{ top: `${top}px`, height: `${height}px` }}
                        />
                        );
                      })}
                  </div>
                  <div className="weekly-meetings-hour-lines">
                    {hours.map(hour => (
                      <span key={hour} className="weekly-meetings-hour-line" />
                    ))}
                  </div>
                  {isToday && currentTimeInBounds && (
                    <div
                      className="weekly-current-time-line"
                      style={{
                        top: `${((nowMinutes - startBound) / 60) * hourHeight}px`,
                      }}
                    />
                  )}
                  {dayBlocks.map(meeting => {
                    const startBound = timeBounds.startHour * 60;
                    const endBound = timeBounds.endHour * 60;
                    const clampedStart = Math.max(startBound, meeting.startMinutes);
                    const clampedEnd = Math.min(endBound, meeting.endMinutes);
                    const top = ((clampedStart - startBound) / 60) * hourHeight;
                    const height = Math.max(1, ((clampedEnd - clampedStart) / 60) * hourHeight);
                    const width = 100 / meeting.laneCount;
                    const left = width * meeting.lane;
                    const timeLabel = `${formatTime(meeting.start, timezone)} - ${formatTime(meeting.end, timezone)}`;
                    const effectiveStatus = localDoneIds.has(meeting.taskId)
                      ? 'DONE'
                      : meeting.status ?? 'TODO';
                    const isBeingDragged = draggingBlockId === meeting.id;
                    const canDrag = effectiveStatus !== 'DONE';
                    return (
                      <div
                        key={meeting.id}
                        className={`weekly-meeting-block ${meeting.kind === 'auto' ? 'auto-slot' : ''} ${
                          effectiveStatus === 'DONE' ? 'done' : ''
                        }${isBeingDragged ? ' dragging' : ''}`}
                        style={{ top: `${top}px`, height: `${height}px`, left: `${left}%`, width: `${width}%` }}
                        title={`${meeting.title} (${timeLabel})`}
                        role="button"
                        tabIndex={0}
                        onClick={() => { if (!isDragging) handleTaskClick(meeting.taskId); }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            handleTaskClick(meeting.taskId);
                          }
                        }}
                        onPointerDown={canDrag ? (e) => {
                          // Don't start drag from action buttons or resize handle
                          if ((e.target as HTMLElement).closest('.weekly-block-actions, .weekly-block-resize-handle')) return;
                          startInteraction(e, {
                            id: meeting.id,
                            taskId: meeting.taskId,
                            dayKey: meeting.dayKey,
                            startMinutes: meeting.startMinutes,
                            endMinutes: meeting.endMinutes,
                            kind: meeting.kind,
                          }, 'drag');
                        } : undefined}
                      >
                        <div className="weekly-block-actions">
                          <button
                            type="button"
                            className={`weekly-block-check ${effectiveStatus === 'DONE' ? 'checked' : ''}`}
                            onClick={(e) => handleToggleComplete(meeting.taskId, effectiveStatus, e)}
                            disabled={isSubmitting === meeting.taskId}
                            title={effectiveStatus === 'DONE' ? '譛ｪ螳御ｺ・↓謌ｻ縺・ : '螳御ｺ・↓縺吶ｋ'}
                          >
                            {effectiveStatus === 'DONE' ? '笨・ : ''}
                          </button>
                          {meeting.kind === 'auto' && effectiveStatus !== 'DONE' && !isToday && (
                            <button
                              type="button"
                              className="weekly-block-do-today"
                              onClick={(e) => handleDoToday(meeting.taskId, e)}
                              disabled={isSubmitting === meeting.taskId}
                              title="莉頑律繧・ｋ"
                            >
                              竊・
                            </button>
                          )}
                          {meeting.kind === 'auto' && effectiveStatus !== 'DONE' && (
                            <PostponePopover
                              taskId={meeting.taskId}
                              className="weekly-block-postpone"
                              onSuccess={() => invalidateAfterChange()}
                            />
                          )}
                        </div>
                        <div className="weekly-meeting-title">
                          {meeting.title}
                          {meeting.pinnedDate && (
                            <span className="weekly-pin-badge" title={`${meeting.pinnedDate} 縺ｫ蝗ｺ螳壻ｸｭ`}>
                              {(() => { const pinned = toDateTime(`${meeting.pinnedDate}T00:00:00`, timezone); return pinned.isValid ? `PIN ${pinned.month}/${pinned.day}` : `PIN ${meeting.pinnedDate}`; })()}
                            </span>
                          )}
                        </div>
                        <div className="weekly-meeting-time">{timeLabel}</div>
                        {meeting.location && <div className="weekly-meeting-location">{meeting.location}</div>}
                        {canDrag && (
                          <div
                            className="weekly-block-resize-handle"
                            onPointerDown={(e) => {
                              startInteraction(e, {
                                id: meeting.id,
                                taskId: meeting.taskId,
                                dayKey: meeting.dayKey,
                                startMinutes: meeting.startMinutes,
                                endMinutes: meeting.endMinutes,
                                kind: meeting.kind,
                              }, 'resize');
                            }}
                          />
                        )}
                      </div>
                    );
                  })}
                  {/* Ghost block for drag/resize preview */}
                  {dragGhost && dragGhost.dayKey === dayKey && (() => {
                    const ghostTop = ((dragGhost.startMinutes - startBound) / 60) * hourHeight;
                    const ghostHeight = Math.max(1, ((dragGhost.endMinutes - dragGhost.startMinutes) / 60) * hourHeight);
                    const ghostLaneCount = dragPreview?.ghost.laneCount ?? 1;
                    const ghostWidth = 100 / ghostLaneCount;
                    const ghostLeft = ghostWidth * (dragPreview?.ghost.lane ?? 0);
                    return (
                      <div
                        className={`weekly-block-ghost${dragPreview?.ghost.kind === 'auto' ? ' auto-slot' : ''}`}
                        style={{
                          top: `${ghostTop}px`,
                          height: `${ghostHeight}px`,
                          left: `${ghostLeft}%`,
                          width: `${ghostWidth}%`,
                        }}
                      />
                    );
                  })()}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!onTaskClick && taskModal.renderModals()}
      {showCreateMeeting && (
        <CreateMeetingModal
          initialDate={createMeetingPrefill?.date}
          initialStartTime={createMeetingPrefill?.startTime}
          initialEndTime={createMeetingPrefill?.endTime}
          onClose={() => setShowCreateMeeting(false)}
          onCreated={() => {
            setShowCreateMeeting(false);
            invalidateAfterChange(true);
          }}
        />
      )}
    </div>
  );
}
