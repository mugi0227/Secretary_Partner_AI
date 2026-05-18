import { useState, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FaPlus, FaFilter } from 'react-icons/fa';
import { KanbanBoard } from '../components/tasks/KanbanBoard';
import { RecurringTaskList } from '../components/tasks/RecurringTaskList';
import { ViewModeToggle } from '../components/common/ViewModeToggle';
import { getStoredViewMode, setStoredViewMode, type ViewMode } from '../components/common/viewModeStorage';
import { useTaskModal } from '../hooks/useTaskModal';
import { useRecurringTasks } from '../hooks/useRecurringTasks';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { usePageTour } from '../hooks/usePageTour';
import { PageTour } from '../components/onboarding/PageTour';
import { TourHelpButton } from '../components/onboarding/TourHelpButton';
import { tasksApi } from '../api/tasks';
import type { Task, TaskAssignment, TaskStatus, TaskUpdate } from '../api/types';
import './TasksPage.css';

const PAGE_SIZE = 100;
const TEXT = {
  pageLabel: 'ページ',
  prev: '前へ',
  next: '次へ',
  showing: '表示',
  countUnit: '件',
  filterMyTasks: '個人タスクのみ',
  filterAll: '全タスク',
};

export function TasksPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [showPersonalOnly, setShowPersonalOnly] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);
  const [sortBy, setSortBy] = useState<'default' | 'dueDate'>('dueDate');
  const tour = usePageTour('tasks');

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    setStoredViewMode(mode);
  };
  const offset = (page - 1) * PAGE_SIZE;

  const { data: allTasks = [], isLoading, error, isFetching } = useQuery({
    queryKey: ['tasks', 'page', page, PAGE_SIZE, 'exclude-meetings'],
    queryFn: () => tasksApi.getAll({
      limit: PAGE_SIZE,
      offset,
      includeDone: true,
      excludeMeetings: true,
    }),
    placeholderData: (previousData) => previousData,
  });

  // Filter tasks based on showPersonalOnly toggle
  const tasks = useMemo(() => {
    if (!showPersonalOnly) return allTasks;
    return allTasks.filter(task => !task.project_id);
  }, [allTasks, showPersonalOnly]);

  // Count only parent (top-level) tasks for display — matches visible card count
  const visibleTaskCount = useMemo(
    () => tasks.filter(task => !task.parent_id).length,
    [tasks],
  );

  // Pagination is now parent-task based: hasNext when parent count equals PAGE_SIZE
  const parentTaskCount = useMemo(
    () => allTasks.filter(task => !task.parent_id).length,
    [allTasks],
  );
  const hasNext = parentTaskCount === PAGE_SIZE;

  // Use the unified task modal hook
  const taskModal = useTaskModal({
    tasks,
    onRefetch: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const { deleteGeneratedTasks, generateTasks } = useRecurringTasks();
  const { data: currentUser } = useCurrentUser();

  // Fetch assignments for tasks with requires_all_completion
  const allCompletionTaskIds = useMemo(
    () => tasks.filter(t => t.requires_all_completion).map(t => t.id),
    [tasks],
  );
  const { data: taskAssignments = [] } = useQuery<TaskAssignment[]>({
    queryKey: ['task-assignments', 'all-completion', allCompletionTaskIds],
    queryFn: async () => {
      if (allCompletionTaskIds.length === 0) return [];
      const results = await Promise.all(
        allCompletionTaskIds.map(id => tasksApi.listAssignments(id).catch(() => [])),
      );
      return results.flat();
    },
    enabled: allCompletionTaskIds.length > 0,
  });

  const invalidateTaskQueries = () => {
    for (const key of [
      ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['today-plan'], ['schedule'],
      ['task-detail'], ['task-assignments'], ['project'],
    ]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) =>
      tasksApi.update(id, data),
    onSuccess: invalidateTaskQueries,
  });

  const deleteMutation = useMutation({
    mutationFn: tasksApi.delete,
    onSuccess: invalidateTaskQueries,
  });

  const handleCheckCompletion = async (taskId: string) => {
    try {
      await tasksApi.checkCompletion(taskId);
      invalidateTaskQueries();
    } catch {
      alert('確認の切り替えに失敗しました');
    }
  };

  const handleUpdateStatus = async (taskId: string, newStatus: TaskStatus) => {
    // Intercept DONE for requires_all_completion tasks → route to check-completion
    if (newStatus === 'DONE') {
      const task = tasks.find(t => t.id === taskId);
      if (task?.requires_all_completion) {
        handleCheckCompletion(taskId);
        return;
      }
      if (task?.dependency_ids && task.dependency_ids.length > 0) {
        const missingDeps = task.dependency_ids.filter(depId => !tasks.find(t => t.id === depId));
        const fetchedDeps = missingDeps.length
          ? await Promise.all(
            missingDeps.map(depId =>
              tasksApi.getById(depId).catch(() => null)
            )
          )
          : [];
        const allDeps = [
          ...task.dependency_ids
            .map(depId => tasks.find(t => t.id === depId))
            .filter(Boolean),
          ...fetchedDeps.filter(Boolean),
        ] as Task[];

        const hasPendingDependencies = allDeps.some(depTask => depTask.status !== 'DONE');

        if (hasPendingDependencies) {
          alert('このタスクを完了するには、先に依存しているタスクを完了してください。');
          return;
        }
      }
    }
    updateMutation.mutate({ id: taskId, data: { status: newStatus } });
  };

  if (error) {
    return (
      <div className="tasks-page">
        <div className="error-state">
          タスクの取得に失敗しました。バックエンドサーバーが起動しているか確認してください。
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="tasks-page">
        <div className="loading-state">読み込み中...</div>
      </div>
    );
  }

  return (
    <div className="tasks-page">
      <div className="page-header">
        <h2 className="page-title">タスク</h2>
        <div className="header-actions">
          <TourHelpButton onClick={tour.startTour} />
          <button
            type="button"
            className={`filter-toggle-btn ${showPersonalOnly ? 'active' : ''}`}
            onClick={() => setShowPersonalOnly(!showPersonalOnly)}
            title={showPersonalOnly ? TEXT.filterAll : TEXT.filterMyTasks}
          >
            <FaFilter />
            {showPersonalOnly ? TEXT.filterMyTasks : TEXT.filterAll}
          </button>
          <span className="task-total">{TEXT.showing} {visibleTaskCount}{TEXT.countUnit}</span>
          <div className="pagination-controls">
            <button
              type="button"
              className="pagination-btn"
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page <= 1 || isFetching}
            >
              {TEXT.prev}
            </button>
            <span className="pagination-info">{TEXT.pageLabel} {page}</span>
            <button
              type="button"
              className="pagination-btn"
              onClick={() => setPage((prev) => prev + 1)}
              disabled={!hasNext || isFetching}
            >
              {TEXT.next}
            </button>
          </div>
          <ViewModeToggle value={viewMode} onChange={handleViewModeChange} />
          <select
            className="sort-select"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'default' | 'dueDate')}
          >
            <option value="default">デフォルト順</option>
            <option value="dueDate">期限が近い順</option>
          </select>
          <button className="primary-btn" onClick={() => taskModal.openCreateForm()}>
            <FaPlus />
            新規タスク
          </button>
        </div>
      </div>

      <RecurringTaskList />

      <KanbanBoard
        tasks={tasks}
        onUpdateTask={handleUpdateStatus}
        onDeleteTask={(taskId) => deleteMutation.mutate(taskId)}
        onTaskClick={taskModal.openTaskDetail}
        onDeleteGeneratedTasks={deleteGeneratedTasks}
        onGenerateTasks={generateTasks}
        sortBy={sortBy}
        compact={viewMode === 'compact'}
        taskAssignments={taskAssignments}
        currentUserId={currentUser?.id}
        onCheckCompletion={handleCheckCompletion}
      />

      {taskModal.renderModals()}
      <PageTour
        run={tour.run}
        steps={tour.steps}
        stepIndex={tour.stepIndex}
        onCallback={tour.handleCallback}
      />
    </div>
  );
}
