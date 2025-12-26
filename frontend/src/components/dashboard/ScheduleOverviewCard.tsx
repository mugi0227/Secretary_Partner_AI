import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useSchedule } from '../../hooks/useSchedule';
import { useCapacitySettings } from '../../hooks/useCapacitySettings';
import { tasksApi } from '../../api/tasks';
import { FaLock } from 'react-icons/fa6';
import type { Task, TaskScheduleInfo, TaskStatus } from '../../api/types';
import './ScheduleOverviewCard.css';

const HORIZON_OPTIONS = [7, 14, 30];
const LOCK_STORAGE_KEY = 'todayTasksLock';

const TEXT = {
  scheduleTitle: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u5168\u4f53',
  scheduleTag: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb',
  scheduleFetchError: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  loading: '\u8aad\u307f\u8fbc\u307f\u4e2d...',
  recentPrefix: '\u76f4\u8fd1',
  dayUnit: '\u65e5',
  recalculating: '\u518d\u8a08\u7b97\u4e2d...',
  recalc: '\u518d\u8a08\u7b97',
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
  open: '\u958b\u304f',
  close: '\u9589\u3058\u308b',
  locked: '\u4eca\u65e5\u306e\u4e88\u5b9a\u306f\u30ed\u30c3\u30af\u4e2d',
  dependencyAlert: '\u4f9d\u5b58\u30bf\u30b9\u30af\u304c\u5b8c\u4e86\u3057\u3066\u3044\u306a\u3044\u305f\u3081\u5b8c\u4e86\u3067\u304d\u307e\u305b\u3093',
  toggleDone: '\u5b8c\u4e86\u306b\u3059\u308b',
  toggleUndone: '\u672a\u5b8c\u4e86\u306b\u623b\u3059',
  checkMark: '\u2713',
};

const formatMinutes = (minutes: number) => {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours && mins) return `${hours}h ${mins}m`;
  if (hours) return `${hours}h`;
  return `${mins}m`;
};

const toDateKey = (value: Date) =>
  `${value.getFullYear()}-${value.getMonth()}-${value.getDate()}`;

const formatDayLabel = (dateStr: string) => {
  const date = new Date(dateStr);
  return date.toLocaleDateString('ja-JP', {
    month: 'numeric',
    day: 'numeric',
  });
};

const formatWeekday = (dateStr: string) => {
  const date = new Date(dateStr);
  return date.toLocaleDateString('ja-JP', { weekday: 'short' });
};

const getDueTag = (task: TaskScheduleInfo | undefined, day: Date) => {
  if (!task?.due_date) return null;
  const due = new Date(task.due_date);
  const dueDateOnly = new Date(due.getFullYear(), due.getMonth(), due.getDate());
  const dayDateOnly = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  if (toDateKey(due) === toDateKey(day)) return TEXT.dueToday;
  if (dueDateOnly < dayDateOnly) return TEXT.dueOver;
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

export function ScheduleOverviewCard() {
  const [horizon, setHorizon] = useState(14);
  const { data, isLoading, error, refetch, isFetching } = useSchedule(horizon);
  const { capacityHours } = useCapacitySettings();
  const [isExcludedOpen, setIsExcludedOpen] = useState(false);
  const [lockInfo, setLockInfo] = useState<TodayTasksLock | null>(null);
  const [statusOverrides, setStatusOverrides] = useState<Record<string, TaskStatus>>({});
  const [taskDetailsCache, setTaskDetailsCache] = useState<Record<string, Task>>({});
  const queryClient = useQueryClient();

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { status: TaskStatus } }) =>
      tasksApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['top3'] });
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const todayIso = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    const raw = localStorage.getItem(LOCK_STORAGE_KEY);
    if (!raw) {
      setLockInfo(null);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as TodayTasksLock;
      if (parsed?.date === todayIso && Array.isArray(parsed.taskIds)) {
        setLockInfo(parsed);
      } else {
        localStorage.removeItem(LOCK_STORAGE_KEY);
        setLockInfo(null);
      }
    } catch {
      localStorage.removeItem(LOCK_STORAGE_KEY);
      setLockInfo(null);
    }
  }, [todayIso]);

  const scheduleTaskIds = useMemo(() => {
    const ids = new Set<string>();
    data?.days.forEach(day => {
      day.task_allocations.forEach(allocation => {
        ids.add(allocation.task_id);
      });
    });
    lockInfo?.taskIds.forEach(taskId => ids.add(taskId));
    return Array.from(ids);
  }, [data?.days, lockInfo]);

  useEffect(() => {
    const desiredIds = new Set<string>(scheduleTaskIds);
    Object.values(taskDetailsCache).forEach(task => {
      (task.dependency_ids || []).forEach(depId => desiredIds.add(depId));
    });
    const missingIds = Array.from(desiredIds).filter(id => !(id in taskDetailsCache));
    if (missingIds.length === 0) return;
    Promise.all(
      missingIds.map(taskId =>
        tasksApi.getById(taskId).catch(() => null)
      )
    ).then(results => {
      const updates: Record<string, Task> = {};
      results.forEach(task => {
        if (task) updates[task.id] = task;
      });
      if (Object.keys(updates).length) {
        setTaskDetailsCache(prev => ({ ...prev, ...updates }));
      }
    });
  }, [scheduleTaskIds, taskDetailsCache]);

  const taskMap = useMemo(() => {
    const map = new Map<string, TaskScheduleInfo>();
    data?.tasks.forEach(task => map.set(task.task_id, task));
    if (lockInfo?.taskSnapshots) {
      Object.entries(lockInfo.taskSnapshots).forEach(([taskId, snapshot]) => {
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
  }, [data?.tasks, lockInfo]);

  const taskDayCounts = useMemo(() => {
    const counts = new Map<string, number>();
    data?.days.forEach(day => {
      day.task_allocations.forEach(allocation => {
        counts.set(allocation.task_id, (counts.get(allocation.task_id) || 0) + 1);
      });
    });
    return counts;
  }, [data?.days]);

  const unscheduledReasons = useMemo(() => {
    const buckets: Record<string, number> = {};
    (data?.unscheduled_task_ids ?? []).forEach(item => {
      buckets[item.reason] = (buckets[item.reason] || 0) + 1;
    });
    return buckets;
  }, [data?.unscheduled_task_ids]);

  const excludedReasons = useMemo(() => {
    const buckets: Record<string, number> = {};
    (data?.excluded_tasks ?? []).forEach(item => {
      buckets[item.reason] = (buckets[item.reason] || 0) + 1;
    });
    return buckets;
  }, [data?.excluded_tasks]);

  const displayCapacityMinutes = Math.max(0, Math.round(capacityHours * 60));

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
          <h3>{TEXT.scheduleTitle}</h3>
          <span className="tag info">{TEXT.scheduleTag}</span>
        </div>
        <div className="error-message">{TEXT.scheduleFetchError}</div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="schedule-overview-card">
        <div className="card-header">
          <h3>{TEXT.scheduleTitle}</h3>
          <span className="tag info">{TEXT.scheduleTag}</span>
        </div>
        <div className="loading-state">{TEXT.loading}</div>
      </div>
    );
  }

  const days = data?.days ?? [];
  const unscheduledCount = data?.unscheduled_task_ids.length ?? 0;
  const excludedCount = data?.excluded_tasks?.length ?? 0;
  const todayKey = toDateKey(new Date());

  return (
    <div className="schedule-overview-card">
      <div className="card-header schedule-header">
        <div className="schedule-title">
          <div className="schedule-title-row">
            <h3>{TEXT.scheduleTitle}</h3>
            {lockInfo && <span className="schedule-lock-badge">{TEXT.locked}</span>}
          </div>
          <span className="schedule-subtitle">{TEXT.recentPrefix}{horizon}{TEXT.dayUnit}</span>
        </div>
        <div className="schedule-actions">
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
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? TEXT.recalculating : TEXT.recalc}
          </button>
        </div>
      </div>

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

      {unscheduledCount > 0 && (
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

      {excludedCount > 0 && (
        <div className="excluded-section">
          <div className="excluded-header">
            <div className="excluded-title-row">
              <span className="excluded-title">{TEXT.excludedTitle}</span>
              <span className="excluded-count">{excludedCount}{TEXT.countUnit}</span>
            </div>
            <button
              type="button"
              className="excluded-toggle"
              onClick={() => setIsExcludedOpen(prev => !prev)}
            >
              {isExcludedOpen ? TEXT.close : TEXT.open}
            </button>
          </div>
          {isExcludedOpen && (
            <>
              <div className="excluded-reasons">
                {excludedReasons.waiting && (
                  <span className="reason-chip">{TEXT.waiting} {excludedReasons.waiting}{TEXT.countUnit}</span>
                )}
                {excludedReasons.parent_task && (
                  <span className="reason-chip">{TEXT.parentTask} {excludedReasons.parent_task}{TEXT.countUnit}</span>
                )}
              </div>
              <div className="excluded-list">
                {(data?.excluded_tasks ?? []).map(item => (
                  <div key={item.task_id} className="excluded-item">
                    <span className="excluded-item-title">{item.title}</span>
                    {item.parent_title && (
                      <span className="excluded-item-parent">{TEXT.parentLabel}: {item.parent_title}</span>
                    )}
                    <span className="excluded-item-reason">
                      {item.reason === 'waiting' && TEXT.waiting}
                      {item.reason === 'parent_task' && TEXT.parentTask}
                      {!['waiting', 'parent_task'].includes(item.reason) && item.reason}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {days.length === 0 ? (
        <div className="schedule-empty">
          <p>{TEXT.emptySchedule}</p>
        </div>
      ) : (
        <div className="schedule-days">
          {days.map(day => {
            const dayDate = new Date(day.date);
            const dayKey = toDateKey(dayDate);
            const isLockedToday = Boolean(lockInfo && day.date === todayIso);
            const lockedAllocations = isLockedToday && lockInfo?.allocations
              ? lockInfo.taskIds.map(taskId => ({
                  task_id: taskId,
                  minutes: lockInfo.allocations?.[taskId]?.allocated_minutes ?? 0,
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
            const displayCapacity = displayCapacityMinutes || capacity;
            const percent = displayCapacity
              ? Math.min(100, Math.round((allocated / displayCapacity) * 100))
              : 0;
            const isToday = dayKey === todayKey;
            const hasOverflow = effectiveDay.overflow_minutes > 0;
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
                dueTag: getDueTag(info, dayDate),
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
                    <div className="schedule-day-date">{formatDayLabel(day.date)}</div>
                    <div className="schedule-day-weekday">{formatWeekday(day.date)}</div>
                  </div>
                  <div className="schedule-day-meta">
                    <span className="schedule-day-capacity">
                      {formatMinutes(allocated)} / {formatMinutes(displayCapacity)}
                    </span>
                    <span className={`schedule-day-pill ${hasOverflow ? 'warn' : ''}`}>
                      {percent}%
                    </span>
                  </div>
                </div>

                <div className="schedule-day-bar">
                  <div className="schedule-day-fill" style={{ width: `${percent}%` }} />
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
                            {group.items.map(item => (
                            <div
                              key={`${day.date}-${item.allocation.task_id}`}
                              className="schedule-task-row child"
                            >
                              {(() => {
                                const isDone = statusOverrides[item.allocation.task_id] === 'DONE';
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
                              <span className="schedule-task-title">
                                {item.info?.title || TEXT.task}
                                </span>
                                {item.dayCount > 1 && <span className="schedule-task-tag">{TEXT.split}</span>}
                                {item.dueTag && (
                                  <span className="schedule-task-tag warn">{item.dueTag}</span>
                                )}
                              </div>
                            ))}
                          </div>
                        );
                      }

                      return group.items.map(item => (
                        <div key={`${day.date}-${item.allocation.task_id}`} className="schedule-task-row">
                          {(() => {
                            const isDone = statusOverrides[item.allocation.task_id] === 'DONE';
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
                          <span className="schedule-task-title">
                            {item.info?.title || TEXT.task}
                          </span>
                          {group.isParentGroup && (
                            <span className="schedule-task-tag parent">
                              {TEXT.parentLabel}: {group.parentTitle}
                            </span>
                          )}
                          {item.dayCount > 1 && <span className="schedule-task-tag">{TEXT.split}</span>}
                          {item.dueTag && <span className="schedule-task-tag warn">{item.dueTag}</span>}
                        </div>
                      ));
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
