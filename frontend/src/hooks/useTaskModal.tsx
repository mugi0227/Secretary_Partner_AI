import { useState, useMemo, useCallback, ReactNode } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { TaskDetailModal } from '../components/tasks/TaskDetailModal';
import { tasksApi } from '../api/tasks';
import type { Task, TaskCreate, TaskUpdate, TaskAssignment } from '../api/types';

interface MemberOption {
  id: string;
  label: string;
}

interface UseTaskModalOptions {
  /** タスク一覧（親コンポーネントから渡す） */
  tasks: Task[];
  /** タスク更新関数 */
  onUpdateTask?: (taskId: string, data: TaskUpdate) => Promise<void>;
  /** タスク作成関数 */
  onCreateTask?: (data: TaskCreate) => Promise<void>;
  /** タスク削除関数 */
  onDeleteTask?: (taskId: string) => Promise<void>;
  /** データ再取得関数 */
  onRefetch?: () => void;
  /** プロジェクト名（表示用） */
  projectName?: string;
  /** フェーズ名取得関数 */
  getPhaseName?: (phaseId: string | undefined) => string | undefined;
  /** 新規タスクのデフォルトデータ */
  defaultTaskData?: Partial<TaskCreate>;
  /** 担当者選択肢 */
  memberOptions?: MemberOption[];
  /** タスクアサイン情報 */
  taskAssignments?: TaskAssignment[];
  /** 担当者変更ハンドラ */
  onAssigneeChange?: (taskId: string, memberIds: string[]) => void;
}

interface TaskModalState {
  /** 選択中のタスクID */
  selectedTaskId: string | null;
  /** 親タスクID（サブタスクを開いた場合） */
  openedParentTaskId: string | null;
  /** タスク作成中か */
  isCreating: boolean;
}

interface TaskModalActions {
  /** タスクをクリックして詳細モーダルを開く */
  openTaskDetail: (task: Task) => void;
  /** タスクIDから詳細モーダルを開く（キャッシュになければ取得） */
  openTaskDetailById: (taskId: string) => Promise<void>;
  /** 詳細モーダルを閉じる */
  closeTaskDetail: () => void;
  /** 編集フォームを開く */
  openEditForm: (task: Task) => void;
  /** 新規作成フォームを開く */
  openCreateForm: (initialData?: Partial<TaskCreate>) => void;
  /** サブタスク作成フォームを開く */
  openCreateSubtaskForm: (parentTaskId: string) => void;
  /** フォームモーダルを閉じる */
  closeForm: () => void;
}

interface UseTaskModalReturn extends TaskModalActions {
  /** 現在の状態 */
  state: TaskModalState;
  /** モーダルをレンダリングするコンポーネント */
  renderModals: () => ReactNode;
  /** 選択中のタスク（解決済み） */
  selectedTask: Task | null;
  /** 親タスク（解決済み） */
  openedParentTask: Task | null;
}

/**
 * タスクモーダルの状態管理とレンダリングを統一するカスタムフック
 */
export function useTaskModal(options: UseTaskModalOptions): UseTaskModalReturn {
  const {
    tasks,
    onUpdateTask,
    onCreateTask,
    onDeleteTask,
    onRefetch,
    projectName,
    getPhaseName,
    defaultTaskData,
    memberOptions = [],
    taskAssignments = [],
    onAssigneeChange,
  } = options;

  const queryClient = useQueryClient();

  // State
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [openedParentTaskId, setOpenedParentTaskId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [taskCache, setTaskCache] = useState<Record<string, Task>>({});
  // Track task IDs created via openCreateForm/openCreateSubtaskForm to detect "empty close"
  const [freshlyCreatedTaskIds, setFreshlyCreatedTaskIds] = useState<Set<string>>(new Set());

  const invalidateTaskQueries = () => {
    for (const key of [
      ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['schedule'],
      ['task-detail'], ['task-assignments'], ['project'], ['meetings'], ['member-child-tasks'],
    ]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
    onRefetch?.();
  };

  // Mutations for inline updates
  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: TaskUpdate }): Promise<void> => {
      if (onUpdateTask) {
        await onUpdateTask(id, data);
      } else {
        await tasksApi.update(id, data);
      }
    },
    onSuccess: (_data, variables) => {
      // User edited this task, so it's no longer "freshly created with defaults"
      setFreshlyCreatedTaskIds(prev => {
        const next = new Set(prev);
        next.delete(variables.id);
        return next;
      });
      invalidateTaskQueries();
    },
  });

  const createMutation = useMutation({
    mutationFn: async (data: TaskCreate): Promise<Task> => {
      const created = await tasksApi.create(data);
      if (onCreateTask) {
        await onCreateTask(data);
      }
      return created;
    },
    onSuccess: invalidateTaskQueries,
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) =>
      onDeleteTask ? onDeleteTask(taskId) : tasksApi.delete(taskId),
    onSuccess: invalidateTaskQueries,
  });

  // Task lookup combining cache and tasks list
  const taskLookup = useMemo(() => {
    const map = new Map<string, Task>();
    Object.values(taskCache).forEach(task => map.set(task.id, task));
    tasks.forEach(task => map.set(task.id, task));
    return map;
  }, [taskCache, tasks]);

  const selectedTask = selectedTaskId ? taskLookup.get(selectedTaskId) ?? null : null;
  const openedParentTask = openedParentTaskId ? taskLookup.get(openedParentTaskId) ?? null : null;

  // Fetch subtasks when a task is selected
  const displayedTaskId = openedParentTask?.id || selectedTask?.id;
  const { data: subtasks = [] } = useQuery({
    queryKey: ['subtasks', displayedTaskId],
    queryFn: () => displayedTaskId ? tasksApi.getSubtasks(displayedTaskId) : Promise.resolve([]),
    enabled: !!displayedTaskId,
  });

  // Actions
  const openTaskDetail = useCallback((task: Task) => {
    if (task.parent_id) {
      const parent = taskLookup.get(task.parent_id) ?? null;
      if (parent) {
        setOpenedParentTaskId(parent.id);
        setSelectedTaskId(task.id);
      } else {
        // Parent not in cache, try to fetch
        tasksApi.getById(task.parent_id).then(parentTask => {
          if (parentTask) {
            setTaskCache(prev => ({ ...prev, [parentTask.id]: parentTask }));
            setOpenedParentTaskId(parentTask.id);
            setSelectedTaskId(task.id);
          }
        }).catch(() => {
          // Fallback: just open the subtask
          setSelectedTaskId(task.id);
          setOpenedParentTaskId(null);
        });
      }
    } else {
      setSelectedTaskId(task.id);
      setOpenedParentTaskId(null);
    }
  }, [taskLookup]);

  const openTaskDetailById = useCallback(async (taskId: string) => {
    const task = taskLookup.get(taskId);
    if (task) {
      openTaskDetail(task);
      return;
    }
    // Fetch from API
    const fetched = await tasksApi.getById(taskId).catch(() => null);
    if (fetched) {
      setTaskCache(prev => ({ ...prev, [fetched.id]: fetched }));
      openTaskDetail(fetched);
    }
  }, [taskLookup, openTaskDetail]);

  const closeTaskDetail = useCallback(() => {
    // If the closed task was freshly created and never edited, delete it
    if (selectedTaskId && freshlyCreatedTaskIds.has(selectedTaskId)) {
      deleteMutation.mutate(selectedTaskId);
      setFreshlyCreatedTaskIds(prev => {
        const next = new Set(prev);
        next.delete(selectedTaskId);
        return next;
      });
    }
    setSelectedTaskId(null);
    setOpenedParentTaskId(null);
  }, [selectedTaskId, freshlyCreatedTaskIds, deleteMutation]);

  // openEditForm is no longer needed - inline editing handles this
  const openEditForm = useCallback((_task: Task) => {
    // No-op: inline editing is now used instead of form modal
    console.log('[useTaskModal] openEditForm called but inline editing is now used');
  }, []);

  // Create a new task and open it in the detail modal for inline editing
  const openCreateForm = useCallback(async (initialData?: Partial<TaskCreate>) => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      const taskData: TaskCreate = {
        title: '新規タスク',
        importance: 'MEDIUM',
        urgency: 'MEDIUM',
        energy_level: 'LOW',
        ...defaultTaskData,
        ...initialData,
      };
      const created = await createMutation.mutateAsync(taskData);
      // Add to cache and open detail modal
      setTaskCache(prev => ({ ...prev, [created.id]: created }));
      setFreshlyCreatedTaskIds(prev => new Set(prev).add(created.id));
      setSelectedTaskId(created.id);
      setOpenedParentTaskId(null);
    } catch (error) {
      console.error('Failed to create task:', error);
    } finally {
      setIsCreating(false);
    }
  }, [defaultTaskData, createMutation, isCreating]);

  // Create a subtask and optionally open parent modal with subtask selected
  // - title: optional title for the subtask (used for inline creation)
  // - openModal: if true, opens parent modal with subtask detail panel (default: true)
  const openCreateSubtaskForm = useCallback(async (parentTaskId: string, title?: string, openModal: boolean = true) => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      const taskData: TaskCreate = {
        title: title || '新規サブタスク',
        importance: 'MEDIUM',
        urgency: 'MEDIUM',
        energy_level: 'LOW',
        parent_id: parentTaskId,
        ...defaultTaskData,
      };
      const created = await createMutation.mutateAsync(taskData);
      // Add to cache
      setTaskCache(prev => ({ ...prev, [created.id]: created }));
      setFreshlyCreatedTaskIds(prev => new Set(prev).add(created.id));
      // Refresh subtasks query
      queryClient.invalidateQueries({ queryKey: ['subtasks', parentTaskId] });

      // If openModal is true, open parent task modal with subtask selected
      if (openModal) {
        // Fetch parent task if not in cache
        let parent = taskLookup.get(parentTaskId);
        if (!parent) {
          const fetched = await tasksApi.getById(parentTaskId).catch(() => null);
          if (fetched) {
            setTaskCache(prev => ({ ...prev, [fetched.id]: fetched }));
            parent = fetched;
          }
        }
        if (parent) {
          setOpenedParentTaskId(parentTaskId);
          setSelectedTaskId(created.id);
        }
      }
    } catch (error) {
      console.error('Failed to create subtask:', error);
      throw error;
    } finally {
      setIsCreating(false);
    }
  }, [defaultTaskData, createMutation, isCreating, queryClient, taskLookup]);

  // closeForm is no longer needed
  const closeForm = useCallback(() => {
    // No-op: form modal is no longer used
  }, []);

  // Handlers for TaskDetailModal
  const handleTaskCheck = useCallback(async (taskId: string) => {
    const task = taskLookup.get(taskId) || subtasks.find(t => t.id === taskId);
    if (!task) return;

    const newStatus = task.status === 'DONE' ? 'TODO' : 'DONE';

    // Check dependencies if marking as done
    if (newStatus === 'DONE' && task.dependency_ids && task.dependency_ids.length > 0) {
      const allDeps = await Promise.all(
        task.dependency_ids.map(depId =>
          taskLookup.get(depId) ||
          subtasks.find(t => t.id === depId) ||
          tasksApi.getById(depId).catch(() => null)
        )
      );

      const hasPendingDependencies = allDeps.some(depTask => depTask && depTask.status !== 'DONE');

      if (hasPendingDependencies) {
        alert('このタスクを完了するには、先に依存しているタスクを完了してください。');
        return;
      }
    }

    updateMutation.mutate({ id: taskId, data: { status: newStatus } });
  }, [taskLookup, subtasks, updateMutation]);

  const handleCheckCompletion = useCallback(async (taskId: string) => {
    try {
      const result = await tasksApi.checkCompletion(taskId);
      setTaskCache(prev => ({ ...prev, [result.task.id]: result.task }));
      invalidateTaskQueries();
    } catch {
      alert('確認の切り替えに失敗しました');
    }
  }, []);

  const handleDelete = useCallback(async (task: Task) => {
    if (window.confirm(`${task.title} を削除してもよろしいですか？`)) {
      await deleteMutation.mutateAsync(task.id);
      closeTaskDetail();
    }
  }, [deleteMutation, closeTaskDetail]);

  // Render function for modals
  const renderModals = useCallback((): ReactNode => {
    const displayedTask = openedParentTask || selectedTask;
    const phaseName = displayedTask?.phase_id && getPhaseName
      ? getPhaseName(displayedTask.phase_id)
      : undefined;

    return (
      <AnimatePresence>
        {selectedTask && displayedTask && (
          <TaskDetailModal
            task={displayedTask}
            subtasks={subtasks}
            allTasks={tasks}
            initialSubtask={openedParentTask ? selectedTask : null}
            projectName={projectName}
            phaseName={phaseName}
            onClose={closeTaskDetail}
            onDelete={handleDelete}
            onTaskCheck={handleTaskCheck}
            onProgressChange={(taskId, progress) => {
              updateMutation.mutate({ id: taskId, data: { progress } });
            }}
            onStatusChange={(taskId, status) => {
              updateMutation.mutate({ id: taskId, data: { status: status as TaskUpdate['status'] } });
            }}
            onUpdateTask={async (taskId, updates) => {
              await updateMutation.mutateAsync({ id: taskId, data: updates });
            }}
            onCreateSubtask={openCreateSubtaskForm}
            onActionItemsCreated={invalidateTaskQueries}
            memberOptions={memberOptions}
            taskAssignments={taskAssignments}
            onAssigneeChange={onAssigneeChange}
            onCheckCompletion={handleCheckCompletion}
          />
        )}
      </AnimatePresence>
    );
  }, [
    selectedTask,
    openedParentTask,
    subtasks,
    tasks,
    projectName,
    getPhaseName,
    closeTaskDetail,
    handleDelete,
    handleTaskCheck,
    updateMutation,
    openCreateSubtaskForm,
    queryClient,
    onRefetch,
    memberOptions,
    taskAssignments,
    onAssigneeChange,
    handleCheckCompletion,
  ]);

  return {
    state: {
      selectedTaskId,
      openedParentTaskId,
      isCreating,
    },
    selectedTask,
    openedParentTask,
    openTaskDetail,
    openTaskDetailById,
    closeTaskDetail,
    openEditForm,
    openCreateForm,
    openCreateSubtaskForm,
    closeForm,
    renderModals,
  };
}
