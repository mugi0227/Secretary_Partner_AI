import { useState, useMemo } from 'react';
import { FaRepeat, FaChevronDown, FaChevronRight, FaCheck } from 'react-icons/fa6';
import { FaTrash, FaSyncAlt } from 'react-icons/fa';
import type { Task, TaskStatus } from '../../api/types';
import { formatDate, toDateTime } from '../../utils/dateTime';
import { useTimezone } from '../../hooks/useTimezone';
import './RecurringTaskGroupCard.css';

const STATUS_LABELS: Record<TaskStatus, string> = {
  TODO: 'ToDo',
  IN_PROGRESS: '進行中',
  WAITING: '待ち',
  DONE: '完了',
};

interface RecurringTaskGroupCardProps {
  recurringTaskId: string;
  title: string;
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
  onUpdateTask?: (id: string, status: TaskStatus) => void;
  onDeleteAll?: (recurringTaskId: string) => void;
  onGenerate?: (recurringTaskId: string) => void;
  compact?: boolean;
}

export function RecurringTaskGroupCard({
  recurringTaskId,
  title,
  tasks,
  onTaskClick,
  onUpdateTask,
  onDeleteAll,
  onGenerate,
  compact = false,
}: RecurringTaskGroupCardProps) {
  const timezone = useTimezone();
  const [expanded, setExpanded] = useState(false);

  const statusCounts = useMemo(() => {
    const counts: Record<TaskStatus, number> = { TODO: 0, IN_PROGRESS: 0, WAITING: 0, DONE: 0 };
    tasks.forEach(t => { counts[t.status]++; });
    return counts;
  }, [tasks]);

  const nextDueDate = useMemo(() => {
    const upcoming = tasks
      .filter(t => t.status !== 'DONE' && t.due_date)
      .sort((a, b) => {
        const aMillis = toDateTime(a.due_date!, timezone).toMillis();
        const bMillis = toDateTime(b.due_date!, timezone).toMillis();
        return aMillis - bMillis;
      });
    return upcoming[0]?.due_date ?? null;
  }, [tasks, timezone]);

  const sortedInstances = useMemo(() => {
    return [...tasks].sort((a, b) => {
      if (!a.due_date && !b.due_date) return 0;
      if (!a.due_date) return 1;
      if (!b.due_date) return -1;
      const aMillis = toDateTime(a.due_date, timezone).toMillis();
      const bMillis = toDateTime(b.due_date, timezone).toMillis();
      return aMillis - bMillis;
    });
  }, [tasks, timezone]);

  const totalCount = tasks.length;
  const doneCount = statusCounts.DONE;

  if (compact) {
    return (
      <div className="rtg-card compact" onClick={() => setExpanded(!expanded)}>
        <div className="rtg-compact-header">
          <FaRepeat className="rtg-icon" />
          <span className="rtg-title">{title}</span>
          <span className="rtg-compact-count">{doneCount}/{totalCount}</span>
          {nextDueDate && (
            <span className="rtg-compact-due">
              ~{formatDate(nextDueDate, { month: 'numeric', day: 'numeric' })}
            </span>
          )}
          {onGenerate && (
            <button
              className="rtg-action-btn compact"
              onClick={(e) => { e.stopPropagation(); onGenerate(recurringTaskId); }}
              title="タスクを再生成"
            >
              <FaSyncAlt />
            </button>
          )}
          {onDeleteAll && (
            <button
              className="rtg-delete-all-btn compact"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`「${title}」の生成済みタスク(${totalCount}件)をすべて削除しますか？`)) {
                  onDeleteAll(recurringTaskId);
                }
              }}
              title="生成済みタスクを一括削除"
            >
              <FaTrash />
            </button>
          )}
          {expanded ? <FaChevronDown className="rtg-chevron" /> : <FaChevronRight className="rtg-chevron" />}
        </div>
        {expanded && (
          <div className="rtg-instances">
            {sortedInstances.map(task => (
              <div
                key={task.id}
                className={`rtg-instance-item ${task.status === 'DONE' ? 'done' : ''}`}
                onClick={(e) => { e.stopPropagation(); onTaskClick?.(task); }}
              >
                <span className={`rtg-instance-status ${task.status.toLowerCase().replace('_', '-')}`}>
                  {task.status === 'DONE' ? <FaCheck /> : STATUS_LABELS[task.status]}
                </span>
                {task.due_date && (
                  <span className="rtg-instance-due">{formatDate(task.due_date, { month: 'numeric', day: 'numeric' })}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rtg-card" onClick={() => setExpanded(!expanded)}>
      <div className="rtg-header">
        <FaRepeat className="rtg-icon" />
        <span className="rtg-title">{title}</span>
        {onGenerate && (
          <button
            className="rtg-action-btn"
            onClick={(e) => { e.stopPropagation(); onGenerate(recurringTaskId); }}
            title="タスクを再生成"
          >
            <FaSyncAlt />
          </button>
        )}
        {onDeleteAll && (
          <button
            className="rtg-delete-all-btn"
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`「${title}」の生成済みタスク(${totalCount}件)をすべて削除しますか？`)) {
                onDeleteAll(recurringTaskId);
              }
            }}
            title="生成済みタスクを一括削除"
          >
            <FaTrash />
          </button>
        )}
        {expanded ? <FaChevronDown className="rtg-chevron" /> : <FaChevronRight className="rtg-chevron" />}
      </div>

      <div className="rtg-meta">
        <div className="rtg-status-pills">
          {(['TODO', 'IN_PROGRESS', 'WAITING', 'DONE'] as TaskStatus[]).map(status => {
            const count = statusCounts[status];
            if (count === 0) return null;
            return (
              <span key={status} className={`rtg-status-pill ${status.toLowerCase().replace('_', '-')}`}>
                {STATUS_LABELS[status]} {count}
              </span>
            );
          })}
        </div>
        {nextDueDate && (
          <span className="rtg-next-due">
            次回: {formatDate(nextDueDate, { month: 'numeric', day: 'numeric' })}
          </span>
        )}
      </div>

      {expanded && (
        <div className="rtg-instances">
          {sortedInstances.map(task => (
            <div
              key={task.id}
              className={`rtg-instance-item ${task.status === 'DONE' ? 'done' : ''}`}
              onClick={(e) => { e.stopPropagation(); onTaskClick?.(task); }}
            >
              <span className={`rtg-instance-status ${task.status.toLowerCase().replace('_', '-')}`}>
                {task.status === 'DONE' ? <FaCheck /> : STATUS_LABELS[task.status]}
              </span>
              <span className="rtg-instance-title">{task.due_date ? formatDate(task.due_date, { month: 'numeric', day: 'numeric', weekday: 'short' }) : 'No date'}</span>
              {task.status !== 'DONE' && onUpdateTask && (
                <button
                  className="rtg-instance-complete-btn"
                  onClick={(e) => { e.stopPropagation(); onUpdateTask(task.id, 'DONE'); }}
                  title="完了にする"
                >
                  <FaCheck />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
