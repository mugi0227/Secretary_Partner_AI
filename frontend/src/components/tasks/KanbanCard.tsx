import { type DateTime } from 'luxon';
import { useCallback, useMemo } from 'react';
import { FaCalendarAlt, FaCheckCircle, FaCircle } from 'react-icons/fa';
import { FaBatteryFull, FaBatteryQuarter, FaClock, FaFire, FaHourglass, FaLeaf, FaListCheck, FaLock, FaLockOpen, FaPen, FaRepeat, FaTrash, FaUser } from 'react-icons/fa6';
import type { Task, TaskAssignment, TaskStatus } from '../../api/types';
import type { DraftCardData } from '../chat/DraftCard';
import { AssigneeSelect } from '../common/AssigneeSelect';
import { StepNumber } from '../common/StepNumber';
import { CompletionChecklist } from './CompletionChecklist';
import './KanbanCard.css';
import { MeetingBadge } from './MeetingBadge';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateTime, todayInTimezone } from '../../utils/dateTime';

interface KanbanCardProps {
  task: Task;
  subtasks?: Task[];
  allTasks?: Task[];
  assigneeName?: string;
  memberOptions?: { id: string; label: string }[];
  assignedMemberIds?: string[];
  onAssignMultiple?: (taskId: string, memberUserIds: string[]) => void;
  onEdit?: (task: Task) => void;
  onDelete?: (id: string) => void;
  onClick?: (task: Task) => void;
  onUpdateTask?: (id: string, status: TaskStatus) => void;
  // Multi-member completion
  taskAssignments?: TaskAssignment[];
  currentUserId?: string;
  onCheckCompletion?: (taskId: string) => void;
  // Selection mode
  selectionMode?: boolean;
  isSelected?: boolean;
  onSelect?: (taskId: string) => void;
  // View mode
  compact?: boolean;
}

export function KanbanCard({
  task,
  subtasks = [],
  allTasks = [],
  assigneeName,
  memberOptions,
  assignedMemberIds = [],
  onAssignMultiple,
  onEdit,
  onDelete,
  onClick,
  onUpdateTask,
  taskAssignments,
  currentUserId,
  onCheckCompletion,
  selectionMode = false,
  isSelected = false,
  onSelect,
  compact = false,
}: KanbanCardProps) {
  const timezone = useTimezone();
  const getPriorityIcon = (level: string) => {
    switch (level) {
      case 'HIGH':
        return <FaFire />;
      case 'MEDIUM':
        return <FaClock />;
      case 'LOW':
        return <FaLeaf />;
      default:
        return <FaLeaf />;
    }
  };

  const getEnergyIcon = (level: string) => {
    return level === 'HIGH' ? <FaBatteryFull /> : <FaBatteryQuarter />;
  };

  const formatShortDate = useCallback((value?: string | DateTime | null) => {
    if (!value) return null;
    if (typeof value === 'string') {
      return formatDate(value, { month: 'numeric', day: 'numeric' }, timezone);
    }
    return value.isValid
      ? value.setLocale('ja-JP').toLocaleString({ month: 'numeric', day: 'numeric' })
      : null;
  }, [timezone]);

  const handleCardClick = () => {
    if (selectionMode && onSelect) {
      onSelect(task.id);
      return;
    }
    if (onClick) {
      onClick(task);
    }
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onSelect) {
      onSelect(task.id);
    }
  };

  const handleActionClick = (e: React.MouseEvent, action: () => void) => {
    e.stopPropagation();
    action();
  };

  const completedSubtasks = subtasks.filter(st => st.status === 'DONE').length;
  const totalSubtasks = subtasks.length;
  const isDone = task.status === 'DONE';

  // Multi-member completion
  const isAllCompletionTask = task.requires_all_completion && taskAssignments && taskAssignments.length > 1;
  const handleDoneClick = () => {
    if (isAllCompletionTask && onCheckCompletion) {
      onCheckCompletion(task.id);
    } else if (onUpdateTask) {
      onUpdateTask(task.id, 'DONE');
    }
  };

  // Deadline status: overdue or approaching
  const deadlineStatus = useMemo(() => {
    if (!task.due_date || isDone) return null;
    const today = todayInTimezone(timezone);
    const dueDate = toDateTime(task.due_date, timezone).startOf('day');
    if (!dueDate.isValid) return null;
    const diffDays = dueDate.diff(today.startOf('day'), 'days').days;
    if (diffDays < 0) return 'overdue' as const;
    if (diffDays <= 3) return 'approaching' as const;
    return null;
  }, [task.due_date, isDone, timezone]);

  const taskLookup = useMemo(() => {
    return new Map(allTasks.map(t => [t.id, t]));
  }, [allTasks]);

  const effectiveStartNotBefore = useMemo(() => {
    const dateMillis: number[] = [];
    if (task.start_not_before) {
      const parsed = toDateTime(task.start_not_before, timezone).startOf('day');
      if (parsed.isValid) {
        dateMillis.push(parsed.toMillis());
      }
    }
    let parentId = task.parent_id;
    const seen = new Set<string>();
    while (parentId && !seen.has(parentId)) {
      seen.add(parentId);
      const parent = taskLookup.get(parentId);
      if (!parent) break;
      if (parent.start_not_before) {
        const parsed = toDateTime(parent.start_not_before, timezone).startOf('day');
        if (parsed.isValid) {
          dateMillis.push(parsed.toMillis());
        }
      }
      parentId = parent.parent_id;
    }
    if (dateMillis.length === 0) return null;
    return toDateTime(new Date(Math.max(...dateMillis)), timezone);
  }, [task.start_not_before, task.parent_id, taskLookup, timezone]);

  // Combined date range display: "1/15〜1/31"
  const dateRangeDisplay = useMemo(() => {
    const startDate = !task.is_fixed_time && effectiveStartNotBefore
      ? formatShortDate(effectiveStartNotBefore)
      : null;
    const endDate = task.due_date
      ? formatShortDate(task.due_date)
      : null;

    if (!startDate && !endDate) return null;

    const overdueSuffix = deadlineStatus === 'overdue' ? ' 超過' : '';

    if (startDate && endDate) return `${startDate}〜${endDate}${overdueSuffix}`;
    if (endDate) return `〜${endDate}${overdueSuffix}`;
    if (startDate) return `${startDate}〜`;
    return null;
  }, [task.is_fixed_time, effectiveStartNotBefore, task.due_date, deadlineStatus, formatShortDate]);

  const handleBreakdown = () => {
    const draftCard: DraftCardData = {
      type: 'subtask',
      title: 'サブタスク分解',
      info: [
        { label: 'タスク', value: task.title },
        { label: 'タスクID', value: task.id },
        ...(task.estimated_minutes ? [{ label: '見積もり', value: `${Math.round(task.estimated_minutes / 60)}時間` }] : []),
      ],
      placeholder: '例: テスト作成も含めて',
      promptTemplate: `タスク「${task.title}」をサブタスクに分解して。

親タスクID: ${task.id}
※サブタスク作成時は必ずparent_idに上記IDを指定してね

追加の指示があれば以下に記入:
{instruction}`,
    };
    const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
    window.dispatchEvent(event);
  };

  // Check if task is blocked by dependencies
  const dependencyStatus = useMemo(() => {
    if (!task.dependency_ids || task.dependency_ids.length === 0) {
      return { isBlocked: false, blockingTasks: [] };
    }

    const blockingTasks: Task[] = [];

    for (const depId of task.dependency_ids) {
      const depTask = taskLookup.get(depId);
      if (depTask && depTask.status !== 'DONE') {
        blockingTasks.push(depTask);
      }
    }

    return {
      isBlocked: blockingTasks.length > 0,
      blockingTasks,
    };
  }, [task.dependency_ids, taskLookup]);


  // Done tasks show a compact view
  if (isDone) {
    return (
      <div
        className={`kanban-card done-compact ${isSelected ? 'selected' : ''} ${selectionMode ? 'selection-mode' : ''}`}
        draggable
        onClick={handleCardClick}
        style={{ cursor: onClick || selectionMode ? 'pointer' : 'default' }}
      >
        {selectionMode && (
          <div className="card-selection-checkbox" onClick={handleCheckboxClick}>
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => {}}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}
        <div className="card-header-row">
          <FaCheckCircle style={{ color: 'var(--accent-green)', flexShrink: 0, fontSize: '0.875rem' }} />
          <h4 className="card-title">{task.title}</h4>
          <div className="card-actions">
            {onEdit && (
              <button
                className="card-action-btn"
                onClick={(e) => handleActionClick(e, () => onEdit(task))}
                title="Edit"
              >
                <FaPen />
              </button>
            )}
            {onDelete && (
              <button
                className="card-action-btn delete"
                onClick={(e) => handleActionClick(e, () => onDelete(task.id))}
                title="Delete"
              >
                <FaTrash />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Compact view for non-done tasks
  if (compact) {
    return (
      <div
        className={`kanban-card compact ${dependencyStatus.isBlocked ? 'blocked' : ''} ${isSelected ? 'selected' : ''} ${selectionMode ? 'selection-mode' : ''} ${deadlineStatus ? `deadline-${deadlineStatus}` : ''}`}
        draggable
        onClick={handleCardClick}
        style={{ cursor: onClick || selectionMode ? 'pointer' : 'default' }}
        title={
          dependencyStatus.isBlocked
            ? `ブロック中: ${dependencyStatus.blockingTasks.map(t => t.title).join(', ')}を先に完了してください`
            : undefined
        }
      >
        {selectionMode && (
          <div className="card-selection-checkbox" onClick={handleCheckboxClick}>
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => {}}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}
        <div className="compact-row-1">
          <span className={`compact-priority-dot urgency-${task.urgency.toLowerCase()}`} />
          {dependencyStatus.isBlocked && (
            <FaLock className="compact-lock-icon" />
          )}
          <span className="compact-title">{task.title}</span>
          {totalSubtasks > 0 && (
            <span className="compact-subtask-badge">
              <FaCheckCircle className="compact-subtask-icon" />
              {completedSubtasks}/{totalSubtasks}
            </span>
          )}
          <div className="card-actions">
            {(onUpdateTask || (isAllCompletionTask && onCheckCompletion)) && (
              <button
                className="card-action-btn check"
                onClick={(e) => handleActionClick(e, handleDoneClick)}
                title={isAllCompletionTask ? '確認する' : '完了にする'}
              >
                <FaCircle />
              </button>
            )}
            {onEdit && (
              <button
                className="card-action-btn"
                onClick={(e) => handleActionClick(e, () => onEdit(task))}
                title="Edit"
              >
                <FaPen />
              </button>
            )}
          </div>
        </div>
        <div className="compact-row-2">
          {isAllCompletionTask && (
            <CompletionChecklist
              assignments={taskAssignments}
              memberOptions={memberOptions || []}
              currentUserId={currentUserId}
              onCheck={onCheckCompletion}
              taskId={task.id}
              compact
            />
          )}
          {assigneeName && (
            <span className="compact-assignee">
              <FaUser className="compact-meta-icon" />
              {assigneeName}
            </span>
          )}
          {dateRangeDisplay && (
            <span className={`compact-date-range ${deadlineStatus ? `deadline-${deadlineStatus}` : ''}`}>
              <FaCalendarAlt className="compact-meta-icon" />
              {dateRangeDisplay}
            </span>
          )}
          {task.is_fixed_time && (
            <MeetingBadge task={task} showDetails={false} />
          )}
          {task.recurring_task_id && (
            <span className="compact-recurring-badge" title="定期タスク">
              <FaRepeat className="compact-meta-icon" />
            </span>
          )}
        </div>
      </div>
    );
  }

  // Normal (full) view
  return (
    <div
      className={`kanban-card ${dependencyStatus.isBlocked ? 'blocked' : ''} ${isSelected ? 'selected' : ''} ${selectionMode ? 'selection-mode' : ''} ${deadlineStatus ? `deadline-${deadlineStatus}` : ''}`}
      draggable
      onClick={handleCardClick}
      style={{ cursor: onClick || selectionMode ? 'pointer' : 'default' }}
      title={
        dependencyStatus.isBlocked
          ? `ブロック中: ${dependencyStatus.blockingTasks.map(t => t.title).join(', ')}を先に完了してください`
          : undefined
      }
    >
      {selectionMode && (
        <div className="card-selection-checkbox" onClick={handleCheckboxClick}>
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => {}}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
      <div className="card-header-row">
        {dependencyStatus.isBlocked ? (
          <div className="dependency-indicator locked" title="依存タスクが未完了">
            <FaLock />
          </div>
        ) : task.dependency_ids && task.dependency_ids.length > 0 ? (
          <div className="dependency-indicator unlocked" title="依存タスク完了済み">
            <FaLockOpen />
          </div>
        ) : null}
        <h4 className="card-title">{task.title}</h4>
        <div className="card-actions">
          {(onUpdateTask || (isAllCompletionTask && onCheckCompletion)) && (
            <button
              className={`card-action-btn check ${isDone ? 'done' : ''}`}
              onClick={(e) => handleActionClick(e, handleDoneClick)}
              title={isDone ? '完了済み' : isAllCompletionTask ? '確認する' : '完了にする'}
              aria-pressed={isDone}
              disabled={isDone}
            >
              {isDone ? <FaCheckCircle /> : <FaCircle />}
            </button>
          )}
          {onEdit && (
            <button
              className="card-action-btn"
              onClick={(e) => handleActionClick(e, () => onEdit(task))}
              title="Edit"
            >
              <FaPen />
            </button>
          )}
          {onDelete && (
            <button
              className="card-action-btn delete"
              onClick={(e) => handleActionClick(e, () => onDelete(task.id))}
              title="Delete"
            >
              <FaTrash />
            </button>
          )}
        </div>
      </div>

      {task.description && (
        <p className="card-description">{task.description}</p>
      )}

      {/* Meeting Badge */}
      {task.is_fixed_time && (
        <MeetingBadge task={task} showDetails={true} />
      )}

      <div className="card-meta">
        {isAllCompletionTask && (
          <CompletionChecklist
            assignments={taskAssignments}
            memberOptions={memberOptions || []}
            currentUserId={currentUserId}
            onCheck={onCheckCompletion}
            taskId={task.id}
            compact
          />
        )}
        {task.recurring_task_id && (
          <span className="meta-badge recurring" title="定期タスク">
            <FaRepeat />
            <span>定期</span>
          </span>
        )}
        {assigneeName && (
          <span className="meta-badge assignee" title="担当者">
            <FaUser />
            <span>{assigneeName}</span>
          </span>
        )}
        {dateRangeDisplay && (
          <span className={`meta-badge date-range ${deadlineStatus ? `deadline-${deadlineStatus}` : ''}`} title={deadlineStatus === 'overdue' ? '期限超過' : deadlineStatus === 'approaching' ? '期限間近' : '期間'}>
            <FaCalendarAlt />
            <span>{dateRangeDisplay}</span>
          </span>
        )}
        <span
          className={`meta-badge urgency-${task.urgency.toLowerCase()}`}
        >
          {getPriorityIcon(task.urgency)}
          <span>{task.urgency}</span>
        </span>
        <span
          className={`meta-badge energy-${task.energy_level.toLowerCase()}`}
        >
          {getEnergyIcon(task.energy_level)}
          <span>{task.energy_level}</span>
        </span>
      </div>

      <button
        type="button"
        className="breakdown-btn"
        onClick={(e) => handleActionClick(e, handleBreakdown)}
      >
        <FaListCheck />
        <span>AIで分解</span>
      </button>

      {memberOptions && memberOptions.length > 0 && onAssignMultiple && (
        <div className="card-assignee-row">
          <AssigneeSelect
            taskId={task.id}
            selectedIds={assignedMemberIds}
            options={memberOptions}
            onChange={onAssignMultiple}
            compact
          />
        </div>
      )}

      {/* Subtasks Summary */}
      {totalSubtasks > 0 && (
        <div className="subtasks-summary">
          <div className="subtasks-progress">
            <div className="subtasks-label">
              <FaCheckCircle className="subtasks-icon" />
              <span>{completedSubtasks}/{totalSubtasks} サブタスク完了</span>
            </div>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${(completedSubtasks / totalSubtasks) * 100}%` }}
              />
            </div>
          </div>
          <ul className="subtasks-mini-list">
            {subtasks.slice(0, 3).map((subtask) => {
              const stepNumber = subtask.order_in_parent;
              return (
                <li key={subtask.id} className="subtask-mini-item">
                  {subtask.status === 'DONE' ? (
                    <FaCheckCircle className="subtask-mini-icon done" />
                  ) : (
                    <FaCircle className="subtask-mini-icon" />
                  )}
                  {stepNumber != null && (
                    <StepNumber stepNumber={stepNumber} className="small" />
                  )}
                  <span className={subtask.status === 'DONE' ? 'subtask-mini-text done' : 'subtask-mini-text'}>
                    {subtask.title}
                  </span>
                </li>
              );
            })}
            {totalSubtasks > 3 && (
              <li className="subtasks-more">他 {totalSubtasks - 3} 件</li>
            )}
          </ul>
        </div>
      )}

      {task.estimated_minutes && (
        <div className="card-footer">
          <FaHourglass />
          <span className="estimate-time">{task.estimated_minutes}分</span>
        </div>
      )}
    </div>
  );
}
