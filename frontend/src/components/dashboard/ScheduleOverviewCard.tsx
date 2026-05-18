import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useSchedule } from '../../hooks/useSchedule';
import { useCapacitySettings } from '../../hooks/useCapacitySettings';
import { useProjects } from '../../hooks/useProjects';
import { tasksApi } from '../../api/tasks';
import { FaLock } from 'react-icons/fa6';
import { FaCalendarAlt, FaList, FaChartBar } from 'react-icons/fa';
import type { Task, TaskScheduleInfo, TaskStatus } from '../../api/types';
import { GanttChartView } from './GanttChartView';
import { WeeklyMeetingsCard } from './WeeklyMeetingsCard';
import { userStorage } from '../../utils/userStorage';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateKey, toDateTime, todayInTimezone } from '../../utils/dateTime';
import './ScheduleOverviewCard.css';

const HORIZON_OPTIONS = [7, 14, 30];
const DEFAULT_PLAN_DAYS = 30;
const LOCK_STORAGE_KEY = 'todayTasksLock';

const TEXT = {
  scheduleTitle: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb',
  scheduleTag: '\u5168\u4f53',
  scheduleFetchError: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  loading: '\u8aad\u307f\u8fbc\u307f\u4e2d...',
  recentPrefix: '\u76f4\u8fd1',
  dayUnit: '\u65e5',
  recalculating: '\u518d\u8a08\u7b97\u4e2d...',
  recalc: '\u518d\u8a08\u7b97',
  recalcError: '\u518d\u8a08\u7b97\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  summaryDays: '\u8868\u793a\u65e5\u6570',
  summaryUnscheduled: '\u672a\u5272\u5f53',
  summaryExcluded: '\u9664\u5916',
  countUnit: '\u4ef6',
  dependencyUnresolved: '\u4f9d\u5b58\u672a\u5b8c\u4e86',
  dependencyMissing: '\u4f9d\u5b58\u4e0d\u6574\u5408',
  maxDays: '\u65e5\u6570\u4e0a\u9650',
  dependencyCycle: '\u4f9d\u5b58\u5faa\u74b0',
  unscheduled: '\u672a\u5272\u5f53',
  excludedTitle: '\u9664\u5916\u30bf\u30b9\u30af',
  waiting: '\u5f85\u6a5f\u4e2d',
  parentTask: '\u89aa\u30bf\u30b9\u30af',
  emptySchedule: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u304c\u3042\u308a\u307e\u305b\u3093',
  todayEmpty: '\u30bf\u30b9\u30af\u306a\u3057',
  split: '\u5206\u5272',
  task: '\u30bf\u30b9\u30af',
  dueToday: '\u4eca\u65e5\u7de0\u5207',
  dueOver: '\u671f\u9650\u8d85\u904e',
  parentUnknown: '\u89aa\u30bf\u30b9\u30af\u4e0d\u660e',
  parentLabel: '\u89aa',
  locked: '\u4eca\u65e5\u306e\u4e88\u5b9a\u306f\u30ed\u30c3\u30af\u4e2d',
  dependencyAlert: '\u4f9d\u5b58\u30bf\u30b9\u30af\u304c\u5b8c\u4e86\u3057\u3066\u3044\u306a\u3044\u305f\u3081\u5b8c\u4e86\u3067\u304d\u307e\u305b\u3093',
  toggleDone: '\u5b8c\u4e86\u306b\u3059\u308b',
  toggleUndone: '\u672a\u5b8c\u4e86\u306b\u623b\u3059',
  checkMark: '\u2713',
  viewList: '\u30ea\u30b9\u30c8\u30d3\u30e5\u30fc',
  viewGantt: '\u30ac\u30f3\u30c8\u30c1\u30e3\u30fc\u30c8',
  viewCalendar: '\u30ab\u30ec\u30f3\u30c0\u30fc',
  planForecast: '\u30d7\u30e9\u30f3\u672a\u751f\u6210',
  planStale: '\u672a\u53cd\u6620\u306e\u5909\u66f4',
  pendingLabel: '\u672a\u53cd\u6620',
};

const formatMinutes = (minutes: number) => {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours && mins) return `${hours}h ${mins}m`;
  if (hours) return `${hours}h`;
  return `${mins}m`;
};

const formatDayLabel = (dateStr: string, timezone: string) => {
  return formatDate(dateStr, { month: 'numeric', day: 'numeric' }, timezone);
};

const formatWeekday = (dateStr: string, timezone: string) => {
  return formatDate(dateStr, { weekday: 'short' }, timezone);
};

const getDueTag =(task: TaskScheduleInfo | undefined, day: Date, timezone: string) => {
  if (!task?.due_date) return null;
  const due = toDateTime(task.due_date, timezone);
  const dayDate = toDateTime(day, timezone).startOf('day');
  if (!due.isValid || !dayDate.isValid) return null;
  if (toDateKey(due.toJSDate(), timezone) === toDateKey(day, timezone)) {
    return TEXT.dueToday;
  }
  if (due.startOf('day').toMillis() < dayDate.toMillis()) return TEXT.dueOver;
  return null;
};

type ScheduleGroupItem = {
  allocation: { task_id: string; minutes: number };
  info: TaskScheduleInfo | undefined;
  dayCount: number;
  dueTag: string | null;
};

type ScheduleGroup = {
  key: string;
  parentTitle?: string;
  isParentGroup: boolean;
  items: ScheduleGroupItem[];
};

type TodayTaskAllocationSnapshot = {
  allocated_minutes: number;
  total_minutes: number;
  ratio: number;
};

type TodayTaskSnapshot = {
  title: string;
  parent_id?: string;
  parent_title?: string | null;
};

type TodayTasksLock = {
  date: string;
  taskIds: string[];
  allocations?: Record<string, TodayTaskAllocationSnapshot>;
  taskSnapshots?: Record<string, TodayTaskSnapshot>;
};

interface ScheduleOverviewCardProps {
  projectId?: string;
  projectTasks?: Task[];
  title?: string;
  tag?: string;
  onTaskClick?: (taskId: string) => void;
  defaultViewMode?: 'list' | 'gantt' | 'calendar';
}

type ViewMode = 'list' | 'gantt' | 'calendar';

export function ScheduleOverviewCard({
  projectId,
  projectTasks,
  title,
  tag,
  onTaskClick,
  defaultViewMode,
}: ScheduleOverviewCardProps) {
  const timezone = useTimezone();
  const [horizon, setHorizon] = useState(14);
  const [viewMode, setViewMode] = useState<ViewMode>(defaultViewMode ?? 'calendar');
  const { data, isLoading, error } = useSchedule(horizon);
  const { getCapacityForDate } = useCapacitySettings();
  const { projects } = useProjects();
  const [isExcludedOpen, setIsExcludedOpen] = useState(false);
  const displayTitle = title ?? TEXT.scheduleTitle;
  const displayTag = tag ?? TEXT.scheduleTag;
  const isCalendarView = viewMode === 'calendar';
  const todayIso = toDateKey(todayInTimezone(timezone).toJSDate(), timezone);
  const lockInfo = useMemo(() => {
    const raw = userStorage.get(LOCK_STORAGE_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as TodayTasksLock;
      if (parsed?.date === todayIso && Array.isArray(parsed.taskIds)) {
        return parsed;
      }
    } catch {
      return null;
    }
    return null;
  }, [todayIso]);
  const [statusOverrides, setStatusOverrides] = useState<Record<string, TaskStatus>>({});
  const [taskDetailsCache, setTaskDetailsCache] = useState<Record<string, Task>>({});
  const failedTaskIds = useRef<Set<string>>(new Set());
  const queryClient = useQueryClient();

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { status: TaskStatus } }) =>
      tasksApi.update(id, data),
    onSuccess: () => {
      for (const key of [
        ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['today-plan'], ['schedule'],
        ['task-detail'], ['task-assignments'], ['project'], ['meetings'], ['member-child-tasks'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  const recalcMutation = useMutation({
    mutationFn: () => tasksApi.recalculateSchedulePlan({
      fromNow: true,
      maxDays: DEFAULT_PLAN_DAYS,
      filterByAssignee: true,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
    onError: () => {
      alert(TEXT.recalcError);
    },
  });
  const isRecalculating = recalcMutation.isPending;

  useEffect(() => {
    if (lockInfo) return;
    const raw = userStorage.get(LOCK_STORAGE_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as TodayTasksLock;
      if (parsed?.date !== todayIso || !Array.isArray(parsed.taskIds)) {
        userStorage.remove(LOCK_STORAGE_KEY);
      }
    } catch {
      userStorage.remove(LOCK_STORAGE_KEY);
    }
  }, [lockInfo, todayIso]);

  const projectTaskIdSet = useMemo(
    () => new Set((projectTasks ?? []).map(task => task.id)),
    [projectTasks]
  );

  const filteredTasks = useMemo(() => {
    if (!projectId) return data?.tasks ?? [];
    return (data?.tasks ?? []).filter(task => task.project_id === projectId);
  }, [data?.tasks, projectId]);

  const allowedTaskIds = useMemo(
    () => new Set(filteredTasks.map(task => task.task_id)),
    [filteredTasks]
  );

  const filteredUnscheduled = useMemo(() => {
    if (!projectId) return data?.unscheduled_task_ids ?? [];
    return (data?.unscheduled_task_ids ?? []).filter(item => allowedTaskIds.has(item.task_id));
  }, [data?.unscheduled_task_ids, projectId, allowedTaskIds]);

  const filteredExcluded = useMemo(() => {
    if (!projectId) return data?.excluded_tasks ?? [];
    const base = data?.excluded_tasks ?? [];
    if (projectTaskIdSet.size > 0) {
      return base.filter(item => projectTaskIdSet.has(item.task_id));
    }
    return base.filter(item => allowedTaskIds.has(item.task_id));
  }, [data?.excluded_tasks, projectId, projectTaskIdSet, allowedTaskIds]);

  const filteredDays = useMemo(() => {
    if (!projectId) return data?.days ?? [];
    return (data?.days ?? []).map(day => {
      const task_allocations = day.task_allocations.filter(allocation => allowedTaskIds.has(allocation.task_id));
      const allocatedMinutes = task_allocations.reduce((sum, allocation) => sum + allocation.minutes, 0);
      const meetingMinutes = task_allocations.reduce((sum, allocation) => {
        const details = taskDetailsCache[allocation.task_id];
        return details?.is_fixed_time ? sum + allocation.minutes : sum;
      }, 0);
      const overflowMinutes = Math.max(0, allocatedMinutes - day.capacity_minutes);
      const availableMinutes = Math.max(0, day.capacity_minutes - allocatedMinutes);
      return {
        ...day,
        task_allocations,
        allocated_minutes: allocatedMinutes,
        overflow_minutes: overflowMinutes,
        meeting_minutes: meetingMinutes,
        available_minutes: availableMinutes,
      };
    });
  }, [data?.days, projectId, allowedTaskIds, taskDetailsCache]);

  const scheduleData = useMemo(() => {
    if (!data || !projectId) return data;
    return {
      ...data,
      tasks: filteredTasks,
      days: filteredDays,
      unscheduled_task_ids: filteredUnscheduled,
      excluded_tasks: filteredExcluded,
    };
  }, [data, projectId, filteredTasks, filteredDays, filteredUnscheduled, filteredExcluded]);
  const pendingChanges = scheduleData?.pending_changes ?? [];
  const pendingPreviewItems = pendingChanges.slice(0, 3);
  const pendingExtraCount = pendingChanges.length - pendingPreviewItems.length;
  const planState = scheduleData?.plan_state ?? 'forecast';
  const showPlanNotice = !isCalendarView && Boolean(scheduleData) && (planState === 'forecast' || (planState === 'stale' && pendingChanges.length > 0));

  const activeLockInfo = useMemo(() => {
    if (!lockInfo) return null;
    if (!projectId) return lockInfo;
    const allowedIds = projectTaskIdSet.size > 0 ? projectTaskIdSet : allowedTaskIds;
    if (allowedIds.size === 0) return null;
    const taskIds = lockInfo.taskIds.filter(taskId => allowedIds.has(taskId));
    if (taskIds.length === 0) return null;
    const allocations = lockInfo.allocations
      ? Object.fromEntries(
          Object.entries(lockInfo.allocations).filter(([taskId]) => allowedIds.has(taskId))
        )
      : undefined;
    const taskSnapshots = lockInfo.taskSnapshots
      ? Object.fromEntries(
          Object.entries(lockInfo.taskSnapshots).filter(([taskId]) => allowedIds.has(taskId))
        )
      : undefined;
    return {
      ...lockInfo,
      taskIds,
      allocations,
      taskSnapshots,
    };
  }, [lockInfo, projectId, projectTaskIdSet, allowedTaskIds]);

  const scheduleTaskIds = useMemo(() => {
    const ids = new Set<string>();
    scheduleData?.days.forEach(day => {
      day.task_allocations.forEach(allocation => {
        ids.add(allocation.task_id);
      });
    });
    activeLockInfo?.taskIds.forEach(taskId => ids.add(taskId));
    return Array.from(ids);
  }, [scheduleData?.days, activeLockInfo]);

  useEffect(() => {
    const desiredIds = new Set<string>(scheduleTaskIds);
    scheduleData?.tasks?.forEach(task => {
      if (task.parent_id) {
        desiredIds.add(task.parent_id);
      }
    });
    Object.values(taskDetailsCache).forEach(task => {
      (task.dependency_ids || []).forEach(depId => desiredIds.add(depId));
      if (task.parent_id) {
        desiredIds.add(task.parent_id);
      }
    });
    const missingIds = Array.from(desiredIds).filter(
      id => !(id in taskDetailsCache) && !failedTaskIds.current.has(id)
    );
    if (missingIds.length === 0) return;
    Promise.all(
      missingIds.map(taskId =>
        tasksApi.getById(taskId).catch(() => null)
      )
    ).then(results => {
      const updates: Record<string, Task> = {};
      results.forEach((task, index) => {
        if (task) {
          updates[task.id] = task;
        } else {
          // Record failed IDs to avoid infinite retry loops
          failedTaskIds.current.add(missingIds[index]);
        }
      });
      if (Object.keys(updates).length) {
        setTaskDetailsCache(prev => ({ ...prev, ...updates }));
      }
    });
  }, [scheduleTaskIds, scheduleData?.tasks, taskDetailsCache]);

  const taskMap = useMemo(() => {
    const map = new Map<string, TaskScheduleInfo>();
    scheduleData?.tasks.forEach(task => map.set(task.task_id, task));
    if (activeLockInfo?.taskSnapshots) {
      Object.entries(activeLockInfo.taskSnapshots).forEach(([taskId, snapshot]) => {
        if (!map.has(taskId)) {
          map.set(taskId, {
            task_id: taskId,
            title: snapshot.title,
            parent_id: snapshot.parent_id,
            parent_title: snapshot.parent_title ?? undefined,
            total_minutes: 0,
            priority_score: 0,
          });
        }
      });
    }
    return map;
  }, [scheduleData?.tasks, activeLockInfo]);

  const projectNameById = useMemo(() => {
    const map: Record<string, string> = {};
    projects.forEach(project => {
      map[project.id] = project.name;
    });
    return map;
  }, [projects]);

  const taskDayCounts = useMemo(() => {
    const counts = new Map<string, number>();
    scheduleData?.days.forEach(day => {
      day.task_allocations.forEach(allocation => {
        counts.set(allocation.task_id, (counts.get(allocation.task_id) || 0) + 1);
      });
    });
    return counts;
  }, [scheduleData?.days]);

  const unscheduledReasons = useMemo(() => {
    const buckets: Record<string, number> = {};
    (scheduleData?.unscheduled_task_ids ?? []).forEach(item => {
      buckets[item.reason] = (buckets[item.reason] || 0) + 1;
    });
    return buckets;
  }, [scheduleData?.unscheduled_task_ids]);

  const dependencyStatusByTaskId = useMemo(() => {
    const map = new Map<string, { blocked: boolean; reason?: string }>();
    const prefix = '\u4f9d\u5b58: ';
    const missingLabel = '\u4f9d\u5b58\u30bf\u30b9\u30af\u3092\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093';

    scheduleTaskIds.forEach(taskId => {
      const task = taskDetailsCache[taskId];
      if (!task?.dependency_ids || task.dependency_ids.length === 0) return;
      const blockingTitles: string[] = [];
      let hasMissing = false;
      task.dependency_ids.forEach(depId => {
        const depTask = taskDetailsCache[depId];
        if (!depTask) {
          hasMissing = true;
          return;
        }
        const depStatus = statusOverrides[depId] ?? depTask.status;
        if (depStatus !== 'DONE') {
          blockingTitles.push(depTask.title);
        }
      });
      if (hasMissing || blockingTitles.length > 0) {
        const reason = blockingTitles.length > 0
          ? `${prefix}${blockingTitles.join(', ')}`
          : missingLabel;
        map.set(taskId, { blocked: true, reason });
      }
    });
    return map;
  }, [scheduleTaskIds, taskDetailsCache, statusOverrides]);

  const getEffectiveStatus = (taskId: string, fallback?: TaskScheduleInfo) => {
    return statusOverrides[taskId]
      ?? taskDetailsCache[taskId]?.status
      ?? fallback?.status;
  };

  const handleTaskClick = (taskId: string) => {
    onTaskClick?.(taskId);
  };

  const handleDoToday = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await tasksApi.doToday(taskId, { pin: true });
      for (const key of [
        ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['today-plan'], ['schedule'],
        ['task-detail'], ['task-assignments'], ['project'], ['meetings'], ['member-child-tasks'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    } catch {
      alert('今日やるの設定に失敗しました');
    }
  };

  const handleToggleStatus = async (taskId: string) => {
    const task = await tasksApi.getById(taskId).catch(() => null);
    if (!task) return;

    if (task.status === 'DONE') {
      setStatusOverrides(prev => ({ ...prev, [taskId]: 'TODO' }));
      updateMutation.mutate({ id: taskId, data: { status: 'TODO' } });
      return;
    }

    if (task.dependency_ids && task.dependency_ids.length > 0) {
      const fetchedDeps = await Promise.all(
        task.dependency_ids.map(depId =>
          tasksApi.getById(depId).catch(() => null)
        )
      );
      const hasPendingDependencies = fetchedDeps.some(
        depTask => !depTask || depTask.status !== 'DONE'
      );
      if (hasPendingDependencies) {
        alert(TEXT.dependencyAlert);
        return;
      }
    }

    setStatusOverrides(prev => ({ ...prev, [taskId]: 'DONE' }));
    updateMutation.mutate({ id: taskId, data: { status: 'DONE' } });
  };

  if (error) {
    return (
      <div className="schedule-overview-card">
        <div className="card-header">
          <h3>{displayTitle}</h3>
          <span className="tag info">{displayTag}</span>
        </div>
        <div className="error-message">{TEXT.scheduleFetchError}</div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="schedule-overview-card">
        <div className="card-header">
          <h3>{displayTitle}</h3>
          <span className="tag info">{displayTag}</span>
        </div>
        <div className="loading-state">{TEXT.loading}</div>
      </div>
    );
  }

  const days = scheduleData?.days ?? [];
  const unscheduledCount = scheduleData?.unscheduled_task_ids.length ?? 0;
  const excludedCount = scheduleData?.excluded_tasks?.length ?? 0;
  const todayKey = toDateKey(todayInTimezone(timezone).toJSDate(), timezone);

  return (
    <div className="schedule-overview-card">
      <div className="card-header schedule-header">
        <div className="schedule-title">
          <div className="schedule-title-row">
            <h3>{displayTitle}</h3>
            {activeLockInfo && <span className="schedule-lock-badge">{TEXT.locked}</span>}
          </div>
          {!isCalendarView && (
            <span className="schedule-subtitle">{TEXT.recentPrefix}{horizon}{TEXT.dayUnit}</span>
          )}
        </div>
        <div className="schedule-actions">
          <div className="view-mode-tabs">
            <button
              className={`view-mode-tab ${viewMode === 'calendar' ? 'active' : ''}`}
              onClick={() => setViewMode('calendar')}
              type="button"
              title={TEXT.viewCalendar}
            >
              <FaCalendarAlt />
            </button>
            <button
              className={`view-mode-tab ${viewMode === 'list' ? 'active' : ''}`}
              onClick={() => setViewMode('list')}
              type="button"
              title={TEXT.viewList}
            >
              <FaList />
            </button>
            <button
              className={`view-mode-tab ${viewMode === 'gantt' ? 'active' : ''}`}
              onClick={() => setViewMode('gantt')}
              type="button"
              title={TEXT.viewGantt}
            >
              <FaChartBar />
            </button>
          </div>
          {!isCalendarView && (
            <>
              <div className="range-tabs">
                {HORIZON_OPTIONS.map(option => (
                  <button
                    key={option}
                    className={`range-tab ${horizon === option ? 'active' : ''}`}
                    onClick={() => setHorizon(option)}
                    type="button"
                  >
                    {option}{TEXT.dayUnit}
                  </button>
                ))}
              </div>
              <button
                className="refresh-btn"
                type="button"
                onClick={() => recalcMutation.mutate()}
                disabled={isRecalculating}
              >
                {isRecalculating ? TEXT.recalculating : TEXT.recalc}
              </button>
            </>
          )}
        </div>
      </div>

      {showPlanNotice && (
        <div className={`schedule-plan-banner ${planState}`}>
          <div className="schedule-plan-icon">
            {planState === 'forecast' ? '○' : '●'}
          </div>
          <div className="schedule-plan-text">
            <span className="schedule-plan-badge">
              {planState === 'forecast' ? TEXT.planForecast : TEXT.planStale}
            </span>
            {planState === 'stale' && pendingChanges.length > 0 && (
              <span className="schedule-plan-count">
                {pendingChanges.length}{TEXT.countUnit}
              </span>
            )}
            {pendingPreviewItems.length > 0 && (
              <span className="schedule-plan-preview">
                {pendingPreviewItems.map((change, i) => (
                  <span key={change.task_id}>
                    {i > 0 && ' / '}
                    <button
                      type="button"
                      className="schedule-plan-task-link"
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

      {!isCalendarView && (
        <div className="schedule-summary">
          <div className="summary-item">
            <span className="summary-label">{TEXT.summaryDays}</span>
            <span className="summary-value">{days.length}{TEXT.dayUnit}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">{TEXT.summaryUnscheduled}</span>
            <span className={`summary-value ${unscheduledCount > 0 ? 'warn' : ''}`}>
              {unscheduledCount}{TEXT.countUnit}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">{TEXT.summaryExcluded}</span>
            <span className={`summary-value ${excludedCount > 0 ? 'warn' : ''}`}>
              {excludedCount}{TEXT.countUnit}
            </span>
          </div>
        </div>
      )}

      {!isCalendarView && unscheduledCount > 0 && (
        <div className="unscheduled-reasons">
          {unscheduledReasons.dependency_unresolved && (
            <span className="reason-chip">{TEXT.dependencyUnresolved} {unscheduledReasons.dependency_unresolved}{TEXT.countUnit}</span>
          )}
          {unscheduledReasons.dependency_missing && (
            <span className="reason-chip warn">{TEXT.dependencyMissing} {unscheduledReasons.dependency_missing}{TEXT.countUnit}</span>
          )}
          {unscheduledReasons.max_days_exceeded && (
            <span className="reason-chip warn">{TEXT.maxDays} {unscheduledReasons.max_days_exceeded}{TEXT.countUnit}</span>
          )}
          {unscheduledReasons.dependency_cycle && (
            <span className="reason-chip warn">{TEXT.dependencyCycle} {unscheduledReasons.dependency_cycle}{TEXT.countUnit}</span>
          )}
          {unscheduledReasons.unscheduled && (
            <span className="reason-chip">{TEXT.unscheduled} {unscheduledReasons.unscheduled}{TEXT.countUnit}</span>
          )}
        </div>
      )}

      {!isCalendarView && excludedCount > 0 && (
        <div className="excluded-inline">
          <button
            type="button"
            className="excluded-inline-toggle"
            onClick={() => setIsExcludedOpen(prev => !prev)}
          >
            <span className="excluded-inline-label">{TEXT.excludedTitle}</span>
            <span className="excluded-inline-count">{excludedCount}{TEXT.countUnit}</span>
            <span className="excluded-inline-chevron">{isExcludedOpen ? '▾' : '▸'}</span>
          </button>
          {isExcludedOpen && (
            <div className="excluded-compact-list">
              {(scheduleData?.excluded_tasks ?? []).map(item => (
                <div key={item.task_id} className="excluded-compact-item">
                  <span className="excluded-compact-title">{item.title}</span>
                  <span className="excluded-compact-reason">
                    {item.reason === 'waiting' && TEXT.waiting}
                    {item.reason === 'parent_task' && TEXT.parentTask}
                    {!['waiting', 'parent_task'].includes(item.reason) && item.reason}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {isCalendarView ? (
        <div className="schedule-calendar-view">
          <WeeklyMeetingsCard
            embedded
            defaultViewMode="today"
            onTaskClick={onTaskClick}
          />
        </div>
      ) : days.length === 0 ? (
        <div className="schedule-empty">
          <p>{TEXT.emptySchedule}</p>
        </div>
      ) : viewMode === 'gantt' ? (
        <GanttChartView
          days={days}
          tasks={scheduleData?.tasks ?? []}
          taskDetailsCache={taskDetailsCache}
          statusOverrides={statusOverrides}
          projectNameById={projectNameById}
          getCapacityForDate={getCapacityForDate}
          onTaskClick={handleTaskClick}
        />
      ) : (
        <div className="schedule-days">
          {days.map(day => {
            const dayDate = toDateTime(day.date, timezone);
            const dayKey = toDateKey(dayDate.toJSDate(), timezone);
            const isLockedToday = Boolean(activeLockInfo && day.date === todayIso);
            const lockedAllocations = isLockedToday && activeLockInfo?.allocations
              ? activeLockInfo.taskIds.map(taskId => ({
                  task_id: taskId,
                  minutes: activeLockInfo.allocations?.[taskId]?.allocated_minutes ?? 0,
                }))
              : null;
            const lockedAllocatedMinutes = lockedAllocations
              ? lockedAllocations.reduce((sum, item) => sum + item.minutes, 0)
              : null;
            const effectiveDay = isLockedToday && lockedAllocations
              ? {
                  ...day,
                  task_allocations: lockedAllocations,
                  allocated_minutes: lockedAllocatedMinutes ?? day.allocated_minutes,
                  overflow_minutes: Math.max(
                    0,
                    (lockedAllocatedMinutes ?? day.allocated_minutes) - day.capacity_minutes
                  ),
                }
              : day;
            const allocated = effectiveDay.allocated_minutes;
            const capacity = effectiveDay.capacity_minutes;
            const baseCapacityMinutes = Math.max(
              0,
              Math.round(getCapacityForDate(dayDate.toJSDate()) * 60)
            );
            const displayCapacity = baseCapacityMinutes || capacity;
            const meetingMinutes = effectiveDay.meeting_minutes ?? 0;
            const taskMinutes = Math.max(0, allocated - meetingMinutes);
            const totalCommittedMinutes = taskMinutes + meetingMinutes;
            const meetingMinutesWithin = Math.min(meetingMinutes, displayCapacity);
            const taskMinutesWithin = Math.min(
              taskMinutes,
              Math.max(0, displayCapacity - meetingMinutesWithin),
            );
            const taskPercent = displayCapacity
              ? Math.min(100, Math.round((taskMinutesWithin / displayCapacity) * 100))
              : 0;
            const meetingPercent = displayCapacity
              ? Math.min(100, Math.round((meetingMinutesWithin / displayCapacity) * 100))
              : 0;
            const percent = displayCapacity
              ? Math.min(100, Math.round((totalCommittedMinutes / displayCapacity) * 100))
              : 0;
            const isToday = dayKey === todayKey;
            const hasOverflow = totalCommittedMinutes > displayCapacity || effectiveDay.overflow_minutes > 0;
            const capacityLabel = meetingMinutes > 0
              ? `タスク${formatMinutes(taskMinutes)} + 会議${formatMinutes(meetingMinutes)} / ${formatMinutes(displayCapacity)}`
              : `${formatMinutes(taskMinutes)} / ${formatMinutes(displayCapacity)}`;
            const dayGroups = new Map<string, ScheduleGroup>();

            effectiveDay.task_allocations.forEach(allocation => {
              const info = taskMap.get(allocation.task_id);
              const hasParent = Boolean(info?.parent_id);
              const groupKey = hasParent
                ? `parent-${info?.parent_id}`
                : `task-${allocation.task_id}`;
              if (!dayGroups.has(groupKey)) {
                dayGroups.set(groupKey, {
                  key: groupKey,
                  parentTitle: hasParent ? (info?.parent_title || TEXT.parentUnknown) : undefined,
                  isParentGroup: hasParent,
                  items: [],
                });
              }
              const group = dayGroups.get(groupKey);
              if (!group) return;
              group.items.push({
                allocation,
                info,
                dayCount: taskDayCounts.get(allocation.task_id) || 1,
                dueTag: getDueTag(info, dayDate.toJSDate(), timezone),
              });
            });

            const groups = Array.from(dayGroups.values());

            return (
              <div
                key={day.date}
                className={`schedule-day ${isToday ? 'is-today' : ''} ${hasOverflow ? 'is-overflow' : ''}`}
              >
                <div className="schedule-day-header">
                  <div>
                    <div className="schedule-day-date">{formatDayLabel(day.date, timezone)}</div>
                    <div className="schedule-day-weekday">{formatWeekday(day.date, timezone)}</div>
                  </div>
                  <div className="schedule-day-meta">
                    <span className="schedule-day-capacity">
                      {capacityLabel}
                    </span>
                    <span className={`schedule-day-pill ${hasOverflow ? 'warn' : ''}`}>
                      {percent}%
                    </span>
                  </div>
                </div>

                <div className="schedule-day-bar">
                  <div
                    className={`schedule-day-fill-task ${hasOverflow ? 'overflow' : ''}`}
                    style={{ width: `${taskPercent}%` }}
                  />
                  {meetingPercent > 0 && (
                    <div
                      className="schedule-day-fill-meeting"
                      style={{ width: `${meetingPercent}%` }}
                    />
                  )}
                </div>


                <div className="schedule-day-tasks">
                  {groups.length === 0 ? (
                    <div className="schedule-day-empty">{TEXT.todayEmpty}</div>
                  ) : (
                    groups.flatMap(group => {
                      if (group.isParentGroup && group.items.length > 1) {
                        return (
                          <div key={group.key} className="schedule-task-group">
                            <div className="schedule-parent-title">{group.parentTitle}</div>
                            {group.items.map(item => {
                              const taskDetail = taskDetailsCache[item.allocation.task_id];
                              const isMeeting = taskDetail?.is_fixed_time;
                              return (
                            <div
                              key={`${day.date}-${item.allocation.task_id}`}
                              className={`schedule-task-row child ${isMeeting ? 'meeting' : ''} ${onTaskClick ? 'clickable' : ''}`}
                              onClick={onTaskClick ? () => handleTaskClick(item.allocation.task_id) : undefined}
                            >
                              {isMeeting && (
                                <span className="schedule-task-meeting-icon">
                                  <FaCalendarAlt />
                                </span>
                              )}
                              {(() => {
                                const isDone = getEffectiveStatus(
                                  item.allocation.task_id,
                                  item.info
                                ) === 'DONE';
                                return (
                                  <button
                                    type="button"
                                    className={`schedule-task-check ${isDone ? 'done' : ''}`}
                                    aria-label={isDone ? TEXT.toggleUndone : TEXT.toggleDone}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      handleToggleStatus(item.allocation.task_id);
                                    }}
                                  >
                                    {isDone ? TEXT.checkMark : ''}
                                  </button>
                                );
                              })()}
                              {(() => {
                                const dependencyStatus = dependencyStatusByTaskId.get(item.allocation.task_id);
                                if (!dependencyStatus?.blocked) return null;
                                return (
                                  <span
                                    className="schedule-task-lock"
                                    title={dependencyStatus.reason ?? TEXT.dependencyAlert}
                                  >
                                    <FaLock />
                                  </span>
                                );
                              })()}
                              <span className="schedule-task-time">
                                {formatMinutes(item.allocation.minutes)}
                              </span>
                              <div className="schedule-task-content">
                                <span className="schedule-task-title">
                                  {item.info?.title || TEXT.task}
                                  {isMeeting && taskDetail?.start_time && (
                                    <span className="meeting-time-inline">
                                      {' '}(
                                        {formatDate(
                                          taskDetail.start_time,
                                          { hour: '2-digit', minute: '2-digit', hour12: false },
                                          timezone,
                                        )}
                                      )
                                    </span>
                                  )}
                                </span>
                              </div>
                            {item.dayCount > 1 && <span className="schedule-task-tag">{TEXT.split}</span>}
                              {item.dueTag && (
                                <span className="schedule-task-tag warn">{item.dueTag}</span>
                              )}
                            {!isToday && !isMeeting && getEffectiveStatus(
                              item.allocation.task_id,
                              item.info
                            ) !== 'DONE' && (
                              <button
                                type="button"
                                className="do-today-btn"
                                onClick={(e) => handleDoToday(item.allocation.task_id, e)}
                              >
                                今日やる
                              </button>
                            )}
                          </div>
                        );
                            })}
                          </div>
                        );
                      }

                      return group.items.map(item => {
                        const taskDetail = taskDetailsCache[item.allocation.task_id];
                        const isMeeting = taskDetail?.is_fixed_time;
                        return (
                        <div
                          key={`${day.date}-${item.allocation.task_id}`}
                          className={`schedule-task-row ${isMeeting ? 'meeting' : ''} ${onTaskClick ? 'clickable' : ''}`}
                          onClick={onTaskClick ? () => handleTaskClick(item.allocation.task_id) : undefined}
                        >
                          {isMeeting && (
                            <span className="schedule-task-meeting-icon">
                              <FaCalendarAlt />
                            </span>
                          )}
                          {(() => {
                            const isDone = getEffectiveStatus(
                              item.allocation.task_id,
                              item.info
                            ) === 'DONE';
                            return (
                              <button
                                type="button"
                                className={`schedule-task-check ${isDone ? 'done' : ''}`}
                                aria-label={isDone ? TEXT.toggleUndone : TEXT.toggleDone}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleToggleStatus(item.allocation.task_id);
                                }}
                              >
                                {isDone ? TEXT.checkMark : ''}
                              </button>
                            );
                          })()}
                          {(() => {
                            const dependencyStatus = dependencyStatusByTaskId.get(item.allocation.task_id);
                            if (!dependencyStatus?.blocked) return null;
                            return (
                              <span
                                className="schedule-task-lock"
                                title={dependencyStatus.reason ?? TEXT.dependencyAlert}
                              >
                                <FaLock />
                              </span>
                            );
                          })()}
                          <span className="schedule-task-time">
                            {formatMinutes(item.allocation.minutes)}
                          </span>
                          <div className="schedule-task-content">
                            <span className="schedule-task-title">
                              {item.info?.title || TEXT.task}
                              {isMeeting && taskDetail?.start_time && (
                                <span className="meeting-time-inline">
                                  {' '}(
                                        {formatDate(
                                          taskDetail.start_time,
                                          { hour: '2-digit', minute: '2-digit', hour12: false },
                                          timezone,
                                        )}
                                      )
                                </span>
                              )}
                            </span>
                            {group.isParentGroup && (
                              <span className="schedule-task-parent-hint">{group.parentTitle}</span>
                            )}
                          </div>
                          {item.dayCount > 1 && <span className="schedule-task-tag">{TEXT.split}</span>}
                          {item.dueTag && <span className="schedule-task-tag warn">{item.dueTag}</span>}
                          {!isToday && !isMeeting && getEffectiveStatus(
                            item.allocation.task_id,
                            item.info
                          ) !== 'DONE' && (
                            <button
                              type="button"
                              className="do-today-btn"
                              onClick={(e) => handleDoToday(item.allocation.task_id, e)}
                            >
                              今日やる
                            </button>
                          )}
                        </div>
                        );
                      });
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
