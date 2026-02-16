import { useMemo } from 'react';
import type { Task, TaskAssignment, TaskStatus } from '../../api/types';
import { KanbanColumn } from './KanbanColumn';
import { sortTasksByStepNumber } from '../../utils/taskSort';
import { toDateTime, todayInTimezone } from '../../utils/dateTime';
import { useTimezone } from '../../hooks/useTimezone';
import './KanbanBoard.css';

export type KanbanItem =
  | { type: 'task'; task: Task }
  | { type: 'recurring-group'; recurringTaskId: string; title: string; tasks: Task[] };

const STATUS_PRIORITY: TaskStatus[] = ['IN_PROGRESS', 'TODO', 'WAITING', 'DONE'];

function getPrimaryStatus(tasks: Task[]): TaskStatus {
  const statusSet = new Set(tasks.map(t => t.status));
  return STATUS_PRIORITY.find(s => statusSet.has(s)) ?? 'TODO';
}

interface KanbanBoardProps {
  tasks: Task[];
  onUpdateTask: (id: string, status: TaskStatus) => void;
  onEditTask?: (task: Task) => void;
  onDeleteTask?: (id: string) => void;
  onTaskClick?: (task: Task) => void;
  assigneeByTaskId?: Record<string, string>;
  assignedMemberIdsByTaskId?: Record<string, string[]>;
  memberOptions?: { id: string; label: string }[];
  onAssignMultiple?: (taskId: string, memberUserIds: string[]) => void;
  sortBy?: 'default' | 'dueDate';
  // Selection mode
  selectionMode?: boolean;
  selectedTaskIds?: Set<string>;
  onSelectTask?: (taskId: string) => void;
  onDragSelectedStart?: () => void;
  // Single task drag (for phase move)
  onSingleDragStart?: (taskId: string) => void;
  // View mode
  compact?: boolean;
  // Multi-member completion
  taskAssignments?: TaskAssignment[];
  currentUserId?: string;
  onCheckCompletion?: (taskId: string) => void;
  onDeleteGeneratedTasks?: (recurringTaskId: string) => void;
  onGenerateTasks?: (recurringTaskId: string) => void;
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
  assigneeByTaskId,
  assignedMemberIdsByTaskId,
  memberOptions,
  onAssignMultiple,
  sortBy = 'default',
  selectionMode = false,
  selectedTaskIds,
  onSelectTask,
  onDragSelectedStart,
  onSingleDragStart,
  compact = false,
  taskAssignments,
  currentUserId,
  onCheckCompletion,
  onDeleteGeneratedTasks,
  onGenerateTasks,
}: KanbanBoardProps) {
  const timezone = useTimezone();

  // Group tasks: parent tasks only (no parent_id)
  const parentTasks = useMemo(() => {
    return tasks.filter(task => !task.parent_id);
  }, [tasks]);

  // Create subtasks map for easy lookup, sorted by step number
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
    // Sort subtasks by step number [1], [2], [3], etc.
    Object.keys(map).forEach((parentId) => {
      map[parentId] = sortTasksByStepNumber(map[parentId]);
    });
    return map;
  }, [tasks]);

  // Separate regular tasks from recurring task groups
  const { regularTasks, recurringGroups } = useMemo(() => {
    const regular: Task[] = [];
    const groupMap = new Map<string, Task[]>();

    parentTasks.forEach(task => {
      if (task.recurring_task_id) {
        const existing = groupMap.get(task.recurring_task_id) || [];
        existing.push(task);
        groupMap.set(task.recurring_task_id, existing);
      } else {
        regular.push(task);
      }
    });

    // Single-instance groups are treated as regular tasks
    const groups: { recurringTaskId: string; title: string; tasks: Task[] }[] = [];
    groupMap.forEach((groupTasks, recurringTaskId) => {
      if (groupTasks.length === 1) {
        regular.push(groupTasks[0]);
      } else {
        groups.push({ recurringTaskId, title: groupTasks[0].title, tasks: groupTasks });
      }
    });

    return { regularTasks: regular, recurringGroups: groups };
  }, [parentTasks]);

  const itemsByStatus = useMemo(() => {
    const grouped: Record<TaskStatus, KanbanItem[]> = {
      TODO: [],
      IN_PROGRESS: [],
      WAITING: [],
      DONE: [],
    };

    // Add regular tasks
    regularTasks.forEach((task) => {
      grouped[task.status].push({ type: 'task', task });
    });

    // Add recurring groups at their primary status column
    recurringGroups.forEach(group => {
      const status = getPrimaryStatus(group.tasks);
      grouped[status].push({
        type: 'recurring-group',
        recurringTaskId: group.recurringTaskId,
        title: group.title,
        tasks: group.tasks,
      });
    });

    if (sortBy === 'dueDate') {
      const toMillis = (value: string | undefined) => {
        if (!value) return Infinity;
        const dt = toDateTime(value, timezone);
        return dt.isValid ? dt.toMillis() : Infinity;
      };

      const todayMs = todayInTimezone(timezone).toMillis();
      const isActionable = (t: Task) =>
        !t.start_not_before || toMillis(t.start_not_before) <= todayMs;

      const getItemSortKey = (item: KanbanItem) => {
        if (item.type === 'task') return item.task;
        // For groups, use the earliest non-DONE task
        const upcoming = item.tasks
          .filter(t => t.status !== 'DONE')
          .sort((a, b) => {
            if (!a.due_date) return 1;
            if (!b.due_date) return -1;
            return toMillis(a.due_date) - toMillis(b.due_date);
          });
        return upcoming[0] ?? item.tasks[0];
      };

      const smartSort = (a: KanbanItem, b: KanbanItem) => {
        const aTask = getItemSortKey(a);
        const bTask = getItemSortKey(b);
        const aOk = isActionable(aTask);
        const bOk = isActionable(bTask);
        if (aOk !== bOk) return aOk ? -1 : 1;
        if (!aOk && !bOk) {
          return toMillis(aTask.start_not_before) - toMillis(bTask.start_not_before);
        }
        if (!aTask.due_date && !bTask.due_date) return 0;
        if (!aTask.due_date) return 1;
        if (!bTask.due_date) return -1;
        return toMillis(aTask.due_date) - toMillis(bTask.due_date);
      };
      (Object.keys(grouped) as TaskStatus[]).forEach((status) => {
        grouped[status].sort(smartSort);
      });
    }

    return grouped;
  }, [regularTasks, recurringGroups, sortBy, timezone]);

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
          items={itemsByStatus[column.status]}
          allTasks={tasks}
          subtasksMap={subtasksMap}
          assigneeByTaskId={assigneeByTaskId}
          assignedMemberIdsByTaskId={assignedMemberIdsByTaskId}
          memberOptions={memberOptions}
          onAssignMultiple={onAssignMultiple}
          onEditTask={onEditTask}
          onDeleteTask={onDeleteTask}
          onTaskClick={onTaskClick}
          onUpdateTask={onUpdateTask}
          onDrop={handleDrop}
          selectionMode={selectionMode}
          selectedTaskIds={selectedTaskIds}
          onSelectTask={onSelectTask}
          onDragSelectedStart={onDragSelectedStart}
          onSingleDragStart={onSingleDragStart}
          compact={compact}
          taskAssignments={taskAssignments}
          currentUserId={currentUserId}
          onCheckCompletion={onCheckCompletion}
          onDeleteGeneratedTasks={onDeleteGeneratedTasks}
          onGenerateTasks={onGenerateTasks}
        />
      ))}
    </div>
  );
}
