import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FaPlus } from 'react-icons/fa';
import { AnimatePresence } from 'framer-motion';
import { KanbanBoard } from '../components/tasks/KanbanBoard';
import { TaskDetailModal } from '../components/tasks/TaskDetailModal';
import { TaskFormModal } from '../components/tasks/TaskFormModal';
import { tasksApi } from '../api/tasks';
import type { Task, TaskStatus, TaskCreate, TaskUpdate } from '../api/types';
import './TasksPage.css';

const PAGE_SIZE = 100;
const TEXT = {
  pageLabel: '\u30da\u30fc\u30b8',
  prev: '\u524d\u3078',
  next: '\u6b21\u3078',
  showing: '\u8868\u793a',
  countUnit: '\u4ef6',
};

export function TasksPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;
  const { data: tasks = [], isLoading, error, isFetching } = useQuery({
    queryKey: ['tasks', 'page', page, PAGE_SIZE],
    queryFn: () => tasksApi.getAll({ limit: PAGE_SIZE, offset, includeDone: true }),
    placeholderData: (previousData) => previousData,
  });
  const hasNext = tasks.length === PAGE_SIZE;
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [taskToEdit, setTaskToEdit] = useState<Task | undefined>(undefined);

  const createMutation = useMutation({
    mutationFn: tasksApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['top3'] });
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) =>
      tasksApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['top3'] });
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: tasksApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['top3'] });
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });

  // Fetch subtasks when a task is selected
  const { data: subtasks = [] } = useQuery({
    queryKey: ['subtasks', selectedTask?.id],
    queryFn: () => selectedTask ? tasksApi.getSubtasks(selectedTask.id) : Promise.resolve([]),
    enabled: !!selectedTask,
  });

  const handleUpdateStatus = async (taskId: string, newStatus: TaskStatus) => {
    // Prevent completing a task if it has incomplete dependencies
    if (newStatus === 'DONE') {
      const task = tasks.find(t => t.id === taskId);
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

  const handleTaskClick = (task: Task) => {
    setSelectedTask(task);
  };

  const handleCloseModal = () => {
    setSelectedTask(null);
  };

  const handleOpenCreateForm = () => {
    setTaskToEdit(undefined);
    setIsFormOpen(true);
  };

  const handleCloseForm = () => {
    setIsFormOpen(false);
    setTaskToEdit(undefined);
  };

  const handleSubmitForm = (data: TaskCreate | TaskUpdate) => {
    if (taskToEdit) {
      updateMutation.mutate({ id: taskToEdit.id, data: data as TaskUpdate });
    } else {
      createMutation.mutate(data as TaskCreate);
    }
    handleCloseForm();
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
        <h2 className="page-title">Tasks</h2>
        <div className="header-actions">
          <span className="task-total">{TEXT.showing} {tasks.length}{TEXT.countUnit}</span>
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
          <button className="primary-btn" onClick={handleOpenCreateForm}>
            <FaPlus />
            新規タスク
          </button>
        </div>
      </div>
      <KanbanBoard
        tasks={tasks}
        onUpdateTask={handleUpdateStatus}
        onDeleteTask={(taskId) => deleteMutation.mutate(taskId)}
        onTaskClick={handleTaskClick}
      />

      <AnimatePresence>
        {selectedTask && (
          <TaskDetailModal
            task={selectedTask}
            subtasks={subtasks}
            allTasks={tasks}
            onClose={handleCloseModal}
            onEdit={(task) => {
              setTaskToEdit(task);
              setIsFormOpen(true);
              setSelectedTask(null);
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isFormOpen && (
          <TaskFormModal
            task={taskToEdit}
            allTasks={tasks}
            onClose={handleCloseForm}
            onSubmit={handleSubmitForm}
            isSubmitting={createMutation.isPending || updateMutation.isPending}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
