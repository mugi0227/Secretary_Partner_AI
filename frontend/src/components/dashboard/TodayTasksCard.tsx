import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence } from 'framer-motion';
import { useTodayTasks } from '../../hooks/useTodayTasks';
import { useTasks } from '../../hooks/useTasks';
import { useCapacitySettings } from '../../hooks/useCapacitySettings';
import { TaskItem } from './TaskItem';
import { TaskDetailModal } from '../tasks/TaskDetailModal';
import { TaskFormModal } from '../tasks/TaskFormModal';
import { tasksApi } from '../../api/tasks';
import type { Task, TaskCreate, TaskUpdate } from '../../api/types';
import './TodayTasksCard.css';

const LOCK_STORAGE_KEY = 'todayTasksLock';

const TEXT = {
  title: '\u4eca\u65e5\u306e\u30bf\u30b9\u30af',
  scheduleTag: '\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb',
  fetchError: '\u4eca\u65e5\u306e\u30bf\u30b9\u30af\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f',
  loading: '\u8aad\u307f\u8fbc\u307f\u4e2d...',
  dependencyAlert: '\u4f9d\u5b58\u30bf\u30b9\u30af\u304c\u5b8c\u4e86\u3057\u3066\u3044\u306a\u3044\u305f\u3081\u5b8c\u4e86\u3067\u304d\u307e\u305b\u3093',
  locked: '\u30ed\u30c3\u30af\u4e2d',
  lock: '\u4eca\u65e5\u306e\u4e88\u5b9a\u3092\u30ed\u30c3\u30af',
  unlock: '\u30ed\u30c3\u30af\u89e3\u9664',
  capacity: '\u7a3c\u50cd\u7387',
  overflow: '\u8d85\u904e',
  empty: '\u4eca\u65e5\u306e\u30bf\u30b9\u30af\u306f\u3042\u308a\u307e\u305b\u3093',
  parentUnknown: '\u89aa\u30bf\u30b9\u30af\u4e0d\u660e',
  parent: '\u89aa',
  allocationLabel: '\u4eca\u65e5\u5206',
  allocationRatio: '\u914d\u5206',
};

const formatMinutes = (minutes: number) => {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours && mins) return `${hours}h ${mins}m`;
  if (hours) return `${hours}h`;
  return `${mins}m`;
};

type TodayTaskGroup = {
  key: string;
  parentId?: string;
  parentTitle?: string | null;
  tasks: Task[];
};

type TodayTasksLock = {
  date: string;
  taskIds: string[];
  allocations?: Record<string, TodayTaskAllocationSnapshot>;
  taskSnapshots?: Record<string, TodayTaskSnapshot>;
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

export function TodayTasksCard() {
  const { data, isLoading, error } = useTodayTasks();
  const { tasks: allTasks, updateTask, createTask, isCreating, isUpdating } = useTasks();
  const { capacityHours } = useCapacitySettings();
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [openedParentTask, setOpenedParentTask] = useState<Task | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [taskToEdit, setTaskToEdit] = useState<Task | undefined>(undefined);
  const [lockInfo, setLockInfo] = useState<TodayTasksLock | null>(null);
  const [dependencyCache, setDependencyCache] = useState<Record<string, Task>>({});

  const parentMap = useMemo(() => {
    const map = new Map<string, Task>();
    allTasks.forEach(task => map.set(task.id, task));
    return map;
  }, [allTasks]);

  const { data: subtasks = [] } = useQuery({
    queryKey: ['subtasks', selectedTask?.id || openedParentTask?.id],
    queryFn: () => {
      const targetId = openedParentTask?.id || selectedTask?.id;
      return targetId ? tasksApi.getSubtasks(targetId) : Promise.resolve([]);
    },
    enabled: !!(selectedTask || openedParentTask),
  });

  const dateLabel = data?.today || new Date().toISOString().slice(0, 10);

  useEffect(() => {
    const raw = localStorage.getItem(LOCK_STORAGE_KEY);
    if (!raw) {
      setLockInfo(null);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as TodayTasksLock;
      if (parsed?.date === dateLabel && Array.isArray(parsed.taskIds)) {
        setLockInfo(parsed);
      } else {
        localStorage.removeItem(LOCK_STORAGE_KEY);
        setLockInfo(null);
      }
    } catch {
      localStorage.removeItem(LOCK_STORAGE_KEY);
      setLockInfo(null);
    }
  }, [dateLabel]);

  const handleTaskClick = (task: Task) => {
    if (task.parent_id) {
      const parent = allTasks.find(t => t.id === task.parent_id);
      if (parent) {
        setOpenedParentTask(parent);
        setSelectedTask(task);
      } else {
        tasksApi.getById(task.parent_id)
          .then(parentTask => {
            setOpenedParentTask(parentTask);
            setSelectedTask(task);
          })
          .catch(err => {
            console.error('Failed to fetch parent task:', err);
            setSelectedTask(task);
          });
      }
    } else {
      setSelectedTask(task);
      setOpenedParentTask(null);
    }
  };

  const handleCloseModal = () => {
    setSelectedTask(null);
    setOpenedParentTask(null);
  };

  const handleCloseForm = () => {
    setIsFormOpen(false);
    setTaskToEdit(undefined);
  };

  const handleSubmitForm = (taskData: TaskCreate | TaskUpdate) => {
    if (taskToEdit) {
      updateTask(taskToEdit.id, taskData as TaskUpdate);
    } else {
      createTask(taskData as TaskCreate);
    }
    handleCloseForm();
  };

  const handleTaskCheck = async (taskId: string) => {
    const localTask = allTasks.find(t => t.id === taskId)
      || effectiveTodayTasks.find(t => t.id === taskId);

    if (localTask?.status === 'DONE') {
      updateTask(taskId, { status: 'TODO' });
      return;
    }

    const task = localTask ?? await tasksApi.getById(taskId).catch(() => null);
    if (!task) return;

    if (task.dependency_ids && task.dependency_ids.length > 0) {
      const missingDeps = task.dependency_ids.filter(depId => !allTasks.find(t => t.id === depId));
      const fetchedDeps = missingDeps.length
        ? await Promise.all(
            missingDeps.map(depId =>
              tasksApi.getById(depId).catch(() => null)
            )
          )
        : [];
      const allDeps = [
        ...task.dependency_ids
          .map(depId => allTasks.find(t => t.id === depId))
          .filter(Boolean),
        ...fetchedDeps.filter(Boolean),
      ] as Task[];

      const hasMissingDependencies = fetchedDeps.some(depTask => !depTask);
      const hasPendingDependencies = hasMissingDependencies
        || allDeps.some(depTask => depTask.status !== 'DONE');

      if (hasPendingDependencies) {
        alert(TEXT.dependencyAlert);
        return;
      }
    }

    updateTask(taskId, { status: 'DONE' });
  };

  const todayTasks = data?.today_tasks ?? [];
  const todayAllocations = data?.today_allocations ?? [];
  const allocatedMinutes = data?.total_estimated_minutes ?? 0;
  const overflowMinutes = data?.overflow_minutes ?? 0;
  const displayCapacityMinutes = Math.max(0, Math.round(capacityHours * 60));

  const allocationMap = useMemo(() => {
    const map = new Map<string, TodayTaskAllocationSnapshot>();
    todayAllocations.forEach(allocation => {
      map.set(allocation.task_id, {
        allocated_minutes: allocation.allocated_minutes,
        total_minutes: allocation.total_minutes,
        ratio: allocation.ratio,
      });
    });
    return map;
  }, [todayAllocations]);

  const lockedAllocationMap = useMemo(() => {
    if (!lockInfo?.allocations) return null;
    const map = new Map<string, TodayTaskAllocationSnapshot>();
    Object.entries(lockInfo.allocations).forEach(([taskId, allocation]) => {
      map.set(taskId, allocation);
    });
    return map;
  }, [lockInfo]);

  const lockedTasks = useMemo(() => {
    if (!lockInfo) return null;
    const map = new Map(allTasks.map(task => [task.id, task]));
    return lockInfo.taskIds.map(taskId => map.get(taskId)).filter(Boolean) as Task[];
  }, [lockInfo, allTasks]);

  const effectiveTodayTasks = lockInfo ? (lockedTasks ?? []) : todayTasks;
  const allocationSource = lockInfo ? lockedAllocationMap : allocationMap;
  const displayAllocatedMinutes = allocationSource && allocationSource.size > 0
    ? effectiveTodayTasks.reduce((sum, task) => {
        const allocation = allocationSource.get(task.id);
        if (allocation) return sum + allocation.allocated_minutes;
        return sum + (task.estimated_minutes ?? 0);
      }, 0)
    : (lockInfo
        ? effectiveTodayTasks.reduce((sum, task) => sum + (task.estimated_minutes ?? 0), 0)
        : allocatedMinutes);
  const capacityPercent = displayCapacityMinutes
    ? Math.min(100, Math.round((displayAllocatedMinutes / displayCapacityMinutes) * 100))
    : 0;
  const top3Ids = new Set(
    lockInfo
      ? effectiveTodayTasks.slice(0, 3).map(task => task.id)
      : (data?.top3_ids ?? [])
  );

  useEffect(() => {
    const knownIds = new Set<string>([
      ...allTasks.map(task => task.id),
      ...Object.keys(dependencyCache),
    ]);
    const missingIds = new Set<string>();
    effectiveTodayTasks.forEach(task => {
      (task.dependency_ids || []).forEach(depId => {
        if (!knownIds.has(depId)) {
          missingIds.add(depId);
        }
      });
    });
    if (missingIds.size === 0) return;
    Promise.all(
      Array.from(missingIds).map(depId =>
        tasksApi.getById(depId).catch(() => null)
      )
    ).then(results => {
      const updates: Record<string, Task> = {};
      results.forEach(task => {
        if (task) updates[task.id] = task;
      });
      if (Object.keys(updates).length) {
        setDependencyCache(prev => ({ ...prev, ...updates }));
      }
    });
  }, [effectiveTodayTasks, allTasks, dependencyCache]);

  const dependencyStatusByTaskId = useMemo(() => {
    const map = new Map<string, { blocked: boolean; reason?: string }>();
    const taskMap = new Map<string, Task>([
      ...allTasks.map(task => [task.id, task]),
      ...Object.values(dependencyCache).map(task => [task.id, task]),
    ]);
    const prefix = '\u4f9d\u5b58: ';
    const missingLabel = '\u4f9d\u5b58\u30bf\u30b9\u30af\u3092\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093';

    effectiveTodayTasks.forEach(task => {
      if (!task.dependency_ids || task.dependency_ids.length === 0) return;
      const blockingTitles: string[] = [];
      let hasMissing = false;
      task.dependency_ids.forEach(depId => {
        const depTask = taskMap.get(depId);
        if (!depTask) {
          hasMissing = true;
          return;
        }
        if (depTask.status !== 'DONE') {
          blockingTitles.push(depTask.title);
        }
      });
      if (hasMissing || blockingTitles.length > 0) {
        const reason = blockingTitles.length > 0
          ? `${prefix}${blockingTitles.join(', ')}`
          : missingLabel;
        map.set(task.id, { blocked: true, reason });
      }
    });
    return map;
  }, [effectiveTodayTasks, allTasks, dependencyCache]);

  const groupedTodayTasks = useMemo(() => {
    const groups: TodayTaskGroup[] = [];
    let current: TodayTaskGroup | null = null;

    effectiveTodayTasks.forEach(task => {
      const parentId = task.parent_id;
      const parentTitle = parentId ? (parentMap.get(parentId)?.title || TEXT.parentUnknown) : null;

      if (parentId && current?.parentId === parentId) {
        current.tasks.push(task);
        return;
      }

      current = {
        key: parentId ? `parent-${parentId}-${groups.length}` : `task-${task.id}`,
        parentId: parentId ?? undefined,
        parentTitle,
        tasks: [task],
      };
      groups.push(current);
    });

    return groups;
  }, [effectiveTodayTasks, parentMap]);

  const isLocked = Boolean(lockInfo);

  const handleToggleLock = () => {
    if (isLocked) {
      localStorage.removeItem(LOCK_STORAGE_KEY);
      setLockInfo(null);
      return;
    }

    const taskIds = todayTasks.map(task => task.id);
    const allocationSnapshot: Record<string, TodayTaskAllocationSnapshot> = {};
    todayAllocations.forEach(allocation => {
      allocationSnapshot[allocation.task_id] = {
        allocated_minutes: allocation.allocated_minutes,
        total_minutes: allocation.total_minutes,
        ratio: allocation.ratio,
      };
    });
    const taskSnapshot: Record<string, TodayTaskSnapshot> = {};
    todayTasks.forEach(task => {
      taskSnapshot[task.id] = {
        title: task.title,
        parent_id: task.parent_id,
        parent_title: task.parent_id
          ? (parentMap.get(task.parent_id)?.title || TEXT.parentUnknown)
          : null,
      };
    });
    const payload: TodayTasksLock = {
      date: dateLabel,
      taskIds,
      allocations: allocationSnapshot,
      taskSnapshots: taskSnapshot,
    };
    localStorage.setItem(LOCK_STORAGE_KEY, JSON.stringify(payload));
    setLockInfo(payload);
  };

  if (error) {
    return (
      <div className="today-tasks-card">
        <div className="card-header">
          <h3>{TEXT.title}</h3>
          <span className="tag info">{TEXT.scheduleTag}</span>
        </div>
        <div className="error-message">{TEXT.fetchError}</div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="today-tasks-card">
        <div className="card-header">
          <h3>{TEXT.title}</h3>
          <span className="tag info">{TEXT.scheduleTag}</span>
        </div>
        <div className="loading-state">{TEXT.loading}</div>
      </div>
    );
  }

  return (
    <div className="today-tasks-card">
      <div className="card-header">
        <div className="today-header">
          <div className="today-title-row">
            <h3>{TEXT.title}</h3>
            {isLocked && <span className="lock-badge">{TEXT.locked}</span>}
          </div>
          <span className="today-date">{dateLabel}</span>
        </div>
        <div className="today-actions">
          <button
            type="button"
            className={`lock-btn ${isLocked ? 'locked' : ''}`}
            onClick={handleToggleLock}
            disabled={!todayTasks.length && !isLocked}
          >
            {isLocked ? TEXT.unlock : TEXT.lock}
          </button>
          <span className={`tag ${data?.overflow ? 'warn' : 'info'}`}>
            {TEXT.capacity} {capacityPercent}%
          </span>
        </div>
      </div>

      <div className="capacity-summary">
        <div className="capacity-bar">
          <div className="capacity-fill" style={{ width: `${capacityPercent}%` }} />
        </div>
        <div className="capacity-meta">
          <span>{formatMinutes(displayAllocatedMinutes)} / {formatMinutes(displayCapacityMinutes)}</span>
          {overflowMinutes > 0 && (
            <span className="capacity-overflow">{TEXT.overflow} {formatMinutes(overflowMinutes)}</span>
          )}
        </div>
      </div>

      <div className="task-list">
        {groupedTodayTasks.length === 0 ? (
          <div className="empty-state">
            <p>{TEXT.empty}</p>
          </div>
        ) : (
          groupedTodayTasks.flatMap(group => {
            const parentLabel = group.parentTitle || TEXT.parentUnknown;
            if (group.parentId && group.tasks.length > 1) {
                return (
                  <div key={group.key} className="today-task-group">
                    <div className="today-task-parent-title">{parentLabel}</div>
                    {group.tasks.map(task => {
                      const isTop3 = top3Ids.has(task.id);
                      const allocation = allocationSource?.get(task.id);
                      const dependencyStatus = dependencyStatusByTaskId.get(task.id);
                      return (
                        <div key={task.id} className={`today-task child ${isTop3 ? 'is-top3' : ''}`}>
                          <TaskItem
                            task={task}
                            onClick={handleTaskClick}
                            onCheck={handleTaskCheck}
                            allowToggleDone
                            isBlocked={dependencyStatus?.blocked}
                            blockedReason={dependencyStatus?.reason}
                          />
                          {allocation && (
                            <div className="today-task-allocation">
                              {TEXT.allocationLabel}: {formatMinutes(allocation.allocated_minutes)} / {formatMinutes(allocation.total_minutes)} ({Math.round(allocation.ratio * 100)}%)
                            </div>
                          )}
                          {isTop3 && <span className="top3-pill">Top 3</span>}
                        </div>
                      );
                    })}
                  </div>
              );
            }

              return group.tasks.map(task => {
                const isTop3 = top3Ids.has(task.id);
                const allocation = allocationSource?.get(task.id);
                const dependencyStatus = dependencyStatusByTaskId.get(task.id);
                return (
                  <div key={task.id} className={`today-task ${isTop3 ? 'is-top3' : ''}`}>
                    <TaskItem
                      task={task}
                      onClick={handleTaskClick}
                      onCheck={handleTaskCheck}
                      allowToggleDone
                      isBlocked={dependencyStatus?.blocked}
                      blockedReason={dependencyStatus?.reason}
                    />
                    {allocation && (
                      <div className="today-task-allocation">
                        {TEXT.allocationLabel}: {formatMinutes(allocation.allocated_minutes)} / {formatMinutes(allocation.total_minutes)} ({Math.round(allocation.ratio * 100)}%)
                      </div>
                    )}
                    {group.parentId && (
                      <div className="today-task-parent">{TEXT.parent}: {parentLabel}</div>
                    )}
                    {isTop3 && <span className="top3-pill">Top 3</span>}
                  </div>
              );
            });
          })
        )}
      </div>

      <AnimatePresence>
        {selectedTask && (
          <TaskDetailModal
            task={openedParentTask || selectedTask}
            subtasks={subtasks}
            allTasks={allTasks}
            initialSubtask={openedParentTask ? selectedTask : null}
            onClose={handleCloseModal}
            onEdit={(task) => {
              setTaskToEdit(task);
              setIsFormOpen(true);
              handleCloseModal();
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isFormOpen && (
          <TaskFormModal
            task={taskToEdit}
            allTasks={allTasks}
            onClose={handleCloseForm}
            onSubmit={handleSubmitForm}
            isSubmitting={isCreating || isUpdating}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
