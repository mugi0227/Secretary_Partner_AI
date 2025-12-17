import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTasks } from '../hooks/useTasks';
import { KanbanBoard } from '../components/tasks/KanbanBoard';
import { TaskDetailModal } from '../components/tasks/TaskDetailModal';
import { tasksApi } from '../api/tasks';
import type { Task, TaskStatus } from '../api/types';
import './TasksPage.css';

export function TasksPage() {
  const { tasks, isLoading, error, updateTask, deleteTask } = useTasks();
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  // Fetch subtasks when a task is selected
  const { data: subtasks = [] } = useQuery({
    queryKey: ['subtasks', selectedTask?.id],
    queryFn: () => selectedTask ? tasksApi.getSubtasks(selectedTask.id) : Promise.resolve([]),
    enabled: !!selectedTask,
  });

  const handleUpdateStatus = (taskId: string, newStatus: TaskStatus) => {
    updateTask(taskId, { status: newStatus });
  };

  const handleTaskClick = (task: Task) => {
    setSelectedTask(task);
  };

  const handleCloseModal = () => {
    setSelectedTask(null);
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
          <span className="task-total">全{tasks.length}件</span>
        </div>
      </div>
      <KanbanBoard
        tasks={tasks}
        onUpdateTask={handleUpdateStatus}
        onDeleteTask={deleteTask}
        onTaskClick={handleTaskClick}
      />

      {selectedTask && (
        <TaskDetailModal
          task={selectedTask}
          subtasks={subtasks}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}
