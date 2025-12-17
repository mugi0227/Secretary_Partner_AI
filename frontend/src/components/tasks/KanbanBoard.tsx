import { useMemo } from 'react';
import type { Task, TaskStatus } from '../../api/types';
import { KanbanColumn } from './KanbanColumn';
import './KanbanBoard.css';

interface KanbanBoardProps {
  tasks: Task[];
  onUpdateTask: (id: string, status: TaskStatus) => void;
  onEditTask?: (task: Task) => void;
  onDeleteTask?: (id: string) => void;
  onTaskClick?: (task: Task) => void;
}

const COLUMNS: { status: TaskStatus; title: string }[] = [
  { status: 'TODO', title: 'To Do' },
  { status: 'IN_PROGRESS', title: 'In Progress' },
  { status: 'WAITING', title: 'Waiting' },
  { status: 'DONE', title: 'Done' },
];

export function KanbanBoard({
  tasks,
  onUpdateTask,
  onEditTask,
  onDeleteTask,
  onTaskClick,
}: KanbanBoardProps) {
  // Group tasks: parent tasks only (no parent_id)
  const parentTasks = useMemo(() => {
    return tasks.filter(task => !task.parent_id);
  }, [tasks]);

  // Create subtasks map for easy lookup
  const subtasksMap = useMemo(() => {
    const map: Record<string, Task[]> = {};
    tasks.forEach((task) => {
      if (task.parent_id) {
        if (!map[task.parent_id]) {
          map[task.parent_id] = [];
        }
        map[task.parent_id].push(task);
      }
    });
    return map;
  }, [tasks]);

  const tasksByStatus = useMemo(() => {
    const grouped: Record<TaskStatus, Task[]> = {
      TODO: [],
      IN_PROGRESS: [],
      WAITING: [],
      DONE: [],
    };

    parentTasks.forEach((task) => {
      grouped[task.status].push(task);
    });

    return grouped;
  }, [parentTasks]);

  const handleDrop = (taskId: string, newStatus: TaskStatus) => {
    onUpdateTask(taskId, newStatus);
  };

  return (
    <div className="kanban-board">
      {COLUMNS.map((column) => (
        <KanbanColumn
          key={column.status}
          status={column.status}
          title={column.title}
          tasks={tasksByStatus[column.status]}
          subtasksMap={subtasksMap}
          onEditTask={onEditTask}
          onDeleteTask={onDeleteTask}
          onTaskClick={onTaskClick}
          onDrop={handleDrop}
        />
      ))}
    </div>
  );
}
