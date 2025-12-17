import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTop3 } from '../../hooks/useTop3';
import { useTasks } from '../../hooks/useTasks';
import { TaskItem } from './TaskItem';
import { TaskDetailModal } from '../tasks/TaskDetailModal';
import { tasksApi } from '../../api/tasks';
import type { Task } from '../../api/types';
import './Top3Card.css';

export function Top3Card() {
  const { data: tasks, isLoading, error } = useTop3();
  const { updateTask } = useTasks();
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [removingTaskIds, setRemovingTaskIds] = useState<Set<string>>(new Set());
  const [pendingDoneTasks, setPendingDoneTasks] = useState<Map<string, Task>>(new Map());

  // Fetch subtasks when a task is selected
  const { data: subtasks = [] } = useQuery({
    queryKey: ['subtasks', selectedTask?.id],
    queryFn: () => selectedTask ? tasksApi.getSubtasks(selectedTask.id) : Promise.resolve([]),
    enabled: !!selectedTask,
  });

  const handleTaskClick = (task: Task) => {
    setSelectedTask(task);
  };

  const handleCloseModal = () => {
    setSelectedTask(null);
  };

  const handleTaskCheck = (taskId: string) => {
    // クリックしたタスクをローカルステートに保存（tasksが更新されても表示し続けるため）
    const taskToKeep = tasks?.find(t => t.id === taskId);
    if (taskToKeep) {
      setPendingDoneTasks(prev => new Map(prev).set(taskId, { ...taskToKeep, status: 'DONE' }));
    }

    updateTask(taskId, { status: 'DONE' });

    // チェックアニメーション開始から1.5秒後にカード削除アニメーションを開始
    setTimeout(() => {
      // removingTaskIds に追加してフェードアウトアニメーション開始
      setRemovingTaskIds(prev => new Set(prev).add(taskId));

      // フェードアウトアニメーション完了後（0.6秒）にDOMから削除
      setTimeout(() => {
        // pendingDoneTasks から削除
        setPendingDoneTasks(prev => {
          const newMap = new Map(prev);
          newMap.delete(taskId);
          return newMap;
        });

        // removingTaskIds からも削除
        setRemovingTaskIds(prev => {
          const newSet = new Set(prev);
          newSet.delete(taskId);
          return newSet;
        });
      }, 600);
    }, 1500);
  };

  if (error) {
    return (
      <div className="top3-card">
        <div className="card-header">
          <h3>Focus for Today</h3>
          <span className="tag high-priority">Top 3</span>
        </div>
        <div className="error-message">
          タスクの取得に失敗しました。バックエンドサーバーが起動しているか確認してください。
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="top3-card">
        <div className="card-header">
          <h3>Focus for Today</h3>
          <span className="tag high-priority">Top 3</span>
        </div>
        <div className="loading-state">読み込み中...</div>
      </div>
    );
  }

  // pendingDoneTasksに含まれるタスクも表示リストに追加
  const allTasks = [...(tasks || [])];
  pendingDoneTasks.forEach((task, taskId) => {
    if (!allTasks.find(t => t.id === taskId)) {
      allTasks.push(task);
    }
  });

  // removingでないタスクの数をカウント（空状態の判定用）
  const activeTaskCount = allTasks.filter(task => !removingTaskIds.has(task.id)).length;
  const isEmpty = activeTaskCount === 0 && removingTaskIds.size === 0;

  return (
    <div className="top3-card">
      <div className="card-header">
        <h3>Focus for Today</h3>
        <span className="tag high-priority">Top 3</span>
      </div>

      <div className="task-list">
        {isEmpty ? (
          <div className="empty-state">
            <p>🎉 タスクがありません！</p>
            <p className="empty-hint">新しいタスクを追加するか、チャットで話しかけてみましょう</p>
          </div>
        ) : (
          allTasks.map((task) => (
            <TaskItem
              key={task.id}
              task={task}
              onClick={handleTaskClick}
              onCheck={handleTaskCheck}
              isRemoving={removingTaskIds.has(task.id)}
            />
          ))
        )}
      </div>

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
