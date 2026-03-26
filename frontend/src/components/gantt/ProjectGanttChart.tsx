/**
 * ProjectGanttChart - カスタムプロジェクトガントチャート
 *
 * 機能:
 * - フェーズ → マイルストーン → タスクの階層表示
 * - バッファの可視化（フェーズ単位）
 * - 依存関係の矢印表示
 * - ドラッグ&ドロップでバー移動
 * - 日/週/月表示モード
 * - 月ヘッダー表示
 */

import React, { useMemo, useState, useCallback, useRef, useEffect, useLayoutEffect } from 'react';
import type { CSSProperties } from 'react';
import { DateTime } from 'luxon';
import { FaChevronDown, FaChevronRight, FaExpand, FaCompress, FaPlus, FaLink, FaUnlink, FaSort, FaTrash, FaMagic, FaCalendarDay } from 'react-icons/fa';
import { FaUser } from 'react-icons/fa6';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
  DragOverEvent,
  useDroppable,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type {
  Task,
  Phase,
  Milestone,
  TaskUpdate,
  LightningLineResponse,
} from '../../api/types';
import { lightningLineApi } from '../../api/lightningLine';
import { useTimezone } from '../../hooks/useTimezone';
import { toDateKey, toDateTime, todayInTimezone } from '../../utils/dateTime';
import './ProjectGanttChart.css';

// ============================================
// Types
// ============================================

type ViewMode = 'day' | 'week' | 'month';
type BufferStatus = 'healthy' | 'warning' | 'critical';

interface ProjectGanttChartProps {
  projectId?: string;
  tasks: Task[];
  phases: Phase[];
  milestones: Milestone[];
  assigneeByTaskId?: Record<string, string>;
  onTaskUpdate?: (taskId: string, updates: { start_not_before?: string; due_date?: string }) => void;
  onPhaseUpdate?: (phaseId: string, updates: { start_date?: string; end_date?: string }) => void;
  onMilestoneUpdate?: (milestoneId: string, updates: { due_date?: string }) => void;
  onTaskClick?: (taskId: string) => void;
  onMilestoneClick?: (milestoneId: string) => void;
  onTaskCreate?: (phaseId?: string) => void;
  onSubtaskCreate?: (parentTaskId: string) => void;
  onGenerateSubtasks?: (parentTaskId: string, taskTitle: string) => void;
  onDeleteTask?: (taskId: string) => void;
  onBatchTaskUpdate?: (updates: Array<{ taskId: string; updates: Partial<TaskUpdate> }>) => void;
  onDependencyUpdate?: (taskId: string, newDependencyIds: string[]) => void;
  onMilestoneLink?: (taskId: string, milestoneId: string | null) => void;
  onDeleteMilestone?: (milestoneId: string) => void;
  onGenerateMilestoneTasks?: (milestoneId: string, milestoneTitle: string) => void;
  onPhaseCreate?: (name: string) => void;
  className?: string;
}

interface GanttBar {
  startIndex: number;
  endIndex: number;
  progress: number;
  status: string;
}

interface GanttRow {
  type: 'phase' | 'milestone' | 'task' | 'buffer' | 'subtask';
  id: string;
  title: string;
  depth: number;
  phaseId?: string;
  bar?: GanttBar;
  bufferStatus?: BufferStatus;
  bufferPercentage?: number;
  bufferType?: 'ccpm' | 'fixed';
  milestoneDate?: DateTime;
  dependencyIds?: string[];
  isExpanded?: boolean;
  childCount?: number;
  linkedMilestoneId?: string;  // For tasks linked to milestones
  linkedMilestoneDateIndex?: number;  // Date index of the linked milestone (for visual marker)
  hasNoDate?: boolean;  // For undated items
  parentTaskId?: string;  // For subtasks
  subtaskCount?: number;  // Number of subtasks for a parent task
  assigneeName?: string;  // Display name of the assignee
  dueDateStr?: string;    // Raw due_date for deadline status calculation
  startNotBeforeStr?: string;  // Raw start_not_before for date display
}

interface MonthHeader {
  label: string;
  startIndex: number;
  span: number;
}

// Undo/Redo History Entry
interface HistoryEntry {
  type: 'task-date' | 'phase-date' | 'milestone-date' | 'batch-task-date';
  timestamp: number;
  // For single item updates
  itemId?: string;
  before?: { start?: string; end?: string };
  after?: { start?: string; end?: string };
  // For batch updates (dependency cascade)
  batchUpdates?: Array<{
    taskId: string;
    before: { start_not_before?: string; due_date?: string };
    after: { start_not_before?: string; due_date?: string };
  }>;
}

// ============================================
// Helpers
// ============================================

const formatMonthYear = (date: DateTime): string => {
  return date.setLocale('ja-JP').toLocaleString({ year: 'numeric', month: 'long' });
};

const formatDayLabel = (date: DateTime): string => {
  return date.day.toString();
};

const formatWeekday = (date: DateTime): string => {
  return date.setLocale('ja-JP').toLocaleString({ weekday: 'short' });
};

const isWeekend = (date: DateTime): boolean => {
  return date.weekday === 6 || date.weekday === 7;
};

const isToday = (date: DateTime, today: DateTime): boolean => {
  return date.hasSame(today, 'day');
};

const getBufferStatusColor = (status: BufferStatus): string => {
  switch (status) {
    case 'critical': return '#ef4444';
    case 'warning': return '#f59e0b';
    default: return '#10b981';
  }
};

/** Format date string to short M/d format (e.g. "1/15") */
const formatShortDate = (dateStr?: string): string => {
  if (!dateStr) return '?';
  const dt = DateTime.fromISO(dateStr);
  return dt.isValid ? dt.toFormat('M/d') : '?';
};

/** Calculate deadline status for a task based on due_date relative to today */
const getDeadlineStatus = (dueDateStr: string | undefined, status: string, today: DateTime, timezone: string): 'overdue' | 'approaching' | null => {
  if (!dueDateStr || status === 'DONE') return null;
  const dueDate = toDateTime(dueDateStr, timezone).startOf('day');
  if (!dueDate.isValid) return null;
  const todayStart = today.startOf('day');
  const diffDays = dueDate.diff(todayStart, 'days').days;
  if (diffDays < 0) return 'overdue';
  if (diffDays <= 3) return 'approaching';
  return null;
};

const generateDateRange = (startDate: DateTime, days: number): DateTime[] => {
  const result: DateTime[] = [];
  let current = startDate.startOf('day');
  for (let i = 0; i < days; i++) {
    result.push(current);
    current = current.plus({ days: 1 });
  }
  return result;
};

// ============================================
// Droppable + Sortable Milestone Row Component
// ============================================

interface DroppableMilestoneRowProps {
  row: GanttRow;
  isDropTarget: boolean;
  onMilestoneClick?: (milestoneId: string) => void;
  onRequestDeleteMilestone?: (milestoneId: string, milestoneTitle: string) => void;
  onGenerateMilestoneTasks?: (milestoneId: string, milestoneTitle: string) => void;
}

const DroppableMilestoneRow: React.FC<DroppableMilestoneRowProps> = ({
  row,
  isDropTarget,
  onMilestoneClick,
  onRequestDeleteMilestone,
  onGenerateMilestoneTasks,
}) => {
  // Popover positioning state
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});
  const titleRef = useRef<HTMLSpanElement>(null);

  const handleTitleMouseEnter = () => {
    if (titleRef.current) {
      const rect = titleRef.current.getBoundingClientRect();
      setPopoverStyle({
        left: `${rect.left}px`,
        top: `${rect.bottom + 6}px`,
      });
    }
  };

  // Use droppable for accepting tasks
  const { setNodeRef: setDroppableRef, isOver } = useDroppable({
    id: `milestone-drop-${row.id}`,
    data: { type: 'milestone', milestoneId: row.id },
  });

  // Use sortable for reordering milestones
  const {
    attributes,
    listeners,
    setNodeRef: setSortableRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: row.id,
  });

  // Combine refs
  const setNodeRef = useCallback((node: HTMLElement | null) => {
    setDroppableRef(node);
    setSortableRef(node);
  }, [setDroppableRef, setSortableRef]);

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    '--depth': row.depth,
  } as CSSProperties;

  const classNames = [
    'pgantt-sidebar-row',
    'milestone',
    `depth-${row.depth}`,
    'draggable',
    'clickable',
    isOver || isDropTarget ? 'drop-target' : '',
    isDragging ? 'dragging' : '',
    row.hasNoDate ? 'no-date' : '',
  ].filter(Boolean).join(' ');

  const handleClick = () => {
    if (!isDragging && onMilestoneClick) {
      onMilestoneClick(row.id);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={classNames}
      onClick={handleClick}
      {...attributes}
      {...listeners}
    >
      <span className="pgantt-milestone-icon">◆</span>
      <span
        ref={titleRef}
        className="pgantt-row-title"
        onMouseEnter={handleTitleMouseEnter}
      >
        {row.title}
        <span className="pgantt-row-title-popover" style={popoverStyle}>{row.title}</span>
      </span>
      <div className="pgantt-milestone-actions">
        {onGenerateMilestoneTasks && (
          <button
            className="pgantt-action-btn pgantt-generate-btn"
            onClick={(e) => {
              e.stopPropagation();
              onGenerateMilestoneTasks(row.id, row.title);
            }}
            title="タスクをAI生成"
          >
            <FaMagic size={10} />
          </button>
        )}
        {onRequestDeleteMilestone && (
          <button
            className="pgantt-action-btn pgantt-delete-btn"
            onClick={(e) => {
              e.stopPropagation();
              onRequestDeleteMilestone(row.id, row.title);
            }}
            title="マイルストーンを削除"
          >
            <FaTrash size={10} />
          </button>
        )}
      </div>
    </div>
  );
};

// ============================================
// Sortable Row Component
// ============================================

interface SortableSidebarRowProps {
  row: GanttRow;
  isLinkMode: boolean;
  linkSourceTask: string | null;
  deadlineStatus?: 'overdue' | 'approaching' | null;
  onTogglePhase: (phaseId: string) => void;
  onToggleTask: (taskId: string) => void;
  onLinkModeClick: (taskId: string) => void;
  onTaskClick?: (taskId: string) => void;
  onTaskCreate?: (phaseId?: string) => void;
  onSubtaskCreate?: (parentTaskId: string) => void;
  onGenerateSubtasks?: (parentTaskId: string, taskTitle: string) => void;
  onRequestDeleteTask?: (taskId: string, taskTitle: string) => void;
  onMilestoneUnlink?: (taskId: string) => void;
  isDragDisabled: boolean;
  isDropTarget?: boolean;  // For milestone drop target highlighting
}

const SortableSidebarRow: React.FC<SortableSidebarRowProps> = ({
  row,
  isLinkMode,
  linkSourceTask,
  deadlineStatus,
  onTogglePhase,
  onToggleTask,
  onLinkModeClick,
  onTaskClick,
  onTaskCreate,
  onSubtaskCreate,
  onGenerateSubtasks,
  onRequestDeleteTask,
  onMilestoneUnlink,
  isDragDisabled,
  isDropTarget,
}) => {
  // Popover positioning state
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});
  const titleRef = useRef<HTMLSpanElement>(null);

  const handleTitleMouseEnter = () => {
    if (titleRef.current) {
      const rect = titleRef.current.getBoundingClientRect();
      setPopoverStyle({
        left: `${rect.left}px`,
        top: `${rect.bottom + 6}px`,
      });
    }
  };

  // Tasks, subtasks, and milestones are draggable for reordering
  const isDraggableType = row.type === 'task' || row.type === 'subtask' || row.type === 'milestone';
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: row.id,
    disabled: isDragDisabled || !isDraggableType,
  });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    '--depth': row.depth,
  } as CSSProperties;

  const handleClick = () => {
    if (row.type === 'phase') {
      onTogglePhase(row.id);
    } else if ((row.type === 'task' || row.type === 'subtask') && isLinkMode) {
      onLinkModeClick(row.id);
    } else if ((row.type === 'task' || row.type === 'subtask') && onTaskClick) {
      onTaskClick(row.id);
    }
  };

  const handleToggleSubtasks = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleTask(row.id);
  };

  // Tasks, subtasks, and milestones are fully draggable (not just via handle)
  // In link mode, disable task drag to allow clicks for linking
  const canDrag = isDraggableType && !isDragDisabled && !((row.type === 'task' || row.type === 'subtask') && isLinkMode);
  const dragProps = canDrag ? { ...attributes, ...listeners } : {};

  const hasSubtasks = row.subtaskCount !== undefined && row.subtaskCount > 0;

  const classNames = [
    'pgantt-sidebar-row',
    row.type,
    `depth-${row.depth}`,
    (row.type === 'task' || row.type === 'subtask') ? 'clickable' : '',
    isDraggableType ? 'draggable' : '',
    row.linkedMilestoneId ? 'milestone-linked' : '',
    isLinkMode && linkSourceTask === row.id ? 'link-source' : '',
    isDragging ? 'dragging' : '',
    isDropTarget ? 'drop-target' : '',
    row.hasNoDate ? 'no-date' : '',
    row.parentTaskId ? 'is-subtask' : '',
    deadlineStatus === 'overdue' ? 'deadline-overdue' : '',
    deadlineStatus === 'approaching' ? 'deadline-approaching' : '',
    row.bar?.status === 'DONE' ? 'status-done' : '',
  ].filter(Boolean).join(' ');

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={classNames}
      onClick={handleClick}
      {...dragProps}
    >
      {row.type === 'phase' && (
        <span className="pgantt-toggle">
          {row.isExpanded ? <FaChevronDown size={10} /> : <FaChevronRight size={10} />}
        </span>
      )}
      {row.type === 'task' && hasSubtasks && (
        <button className="pgantt-toggle pgantt-task-toggle" onClick={handleToggleSubtasks} title={row.isExpanded ? 'サブタスクを閉じる' : 'サブタスクを開く'}>
          {row.isExpanded ? <FaChevronDown size={10} /> : <FaChevronRight size={10} />}
        </button>
      )}
      {row.type === 'task' && !hasSubtasks && (
        <span className="pgantt-task-toggle-spacer" />
      )}
      {row.type === 'subtask' && <span className="pgantt-subtask-icon">└</span>}
      {row.type === 'milestone' && <span className="pgantt-milestone-icon">◆</span>}
      {row.linkedMilestoneId && <span className="pgantt-linked-icon">└</span>}
      {(row.type === 'task' || row.type === 'subtask') && row.bar?.status && (
        <span className={`pgantt-status-dot ${row.bar.status.toLowerCase().replace('_', '-')}`} title={
          row.bar.status === 'DONE' ? '完了' :
          row.bar.status === 'IN_PROGRESS' ? '進行中' :
          row.bar.status === 'WAITING' ? '待機中' : '未着手'
        } />
      )}
      <div className="pgantt-row-info">
        <span
          ref={titleRef}
          className="pgantt-row-title"
          onMouseEnter={handleTitleMouseEnter}
        >
          {row.title}
          <span className="pgantt-row-title-popover" style={popoverStyle}>{row.title}</span>
        </span>
        {(row.type === 'task' || row.type === 'subtask') && (row.startNotBeforeStr || row.dueDateStr) && (
          <span className="pgantt-row-dates">
            {formatShortDate(row.startNotBeforeStr)}〜{formatShortDate(row.dueDateStr)}
          </span>
        )}
      </div>
      {(row.type === 'task' || row.type === 'subtask') && row.assigneeName && (
        <span className="pgantt-assignee-badge" title={row.assigneeName}>
          <FaUser size={8} />
          <span>{row.assigneeName}</span>
        </span>
      )}
      {hasSubtasks && (
        <span className="pgantt-subtask-count">{row.subtaskCount}</span>
      )}
      {row.childCount !== undefined && row.childCount > 0 && (
        <span className="pgantt-child-count">{row.childCount}</span>
      )}
      {row.type === 'phase' && onTaskCreate && (
        <button
          className="pgantt-add-task-btn"
          onClick={(e) => {
            e.stopPropagation();
            onTaskCreate(row.id === 'unassigned' ? undefined : row.id);
          }}
          title="タスクを追加"
        >
          <FaPlus size={10} />
        </button>
      )}
      {(row.type === 'task' || row.type === 'subtask') && (
        <div className="pgantt-task-actions">
          {row.type === 'task' && onSubtaskCreate && (
            <button
              className="pgantt-action-btn pgantt-subtask-create-btn"
              onClick={(e) => {
                e.stopPropagation();
                onSubtaskCreate(row.id);
              }}
              title="サブタスクを作成"
            >
              <FaPlus size={10} />
            </button>
          )}
          {row.type === 'task' && onGenerateSubtasks && (
            <button
              className="pgantt-action-btn pgantt-generate-btn"
              onClick={(e) => {
                e.stopPropagation();
                onGenerateSubtasks(row.id, row.title);
              }}
              title="サブタスクをAI生成"
            >
              <FaMagic size={10} />
            </button>
          )}
          {row.linkedMilestoneId && onMilestoneUnlink && (
            <button
              className="pgantt-action-btn pgantt-unlink-btn"
              onClick={(e) => {
                e.stopPropagation();
                onMilestoneUnlink(row.id);
              }}
              title="マイルストーンから外す"
            >
              <FaUnlink size={10} />
            </button>
          )}
          {onRequestDeleteTask && (
            <button
              className="pgantt-action-btn pgantt-delete-btn"
              onClick={(e) => {
                e.stopPropagation();
                onRequestDeleteTask(row.id, row.title);
              }}
              title={row.type === 'subtask' ? 'サブタスクを削除' : 'タスクを削除'}
            >
              <FaTrash size={10} />
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================
// Component
// ============================================

export const ProjectGanttChart: React.FC<ProjectGanttChartProps> = ({
  projectId,
  tasks,
  phases,
  milestones,
  assigneeByTaskId = {},
  onTaskUpdate,
  onPhaseUpdate,
  onMilestoneUpdate,
  onTaskClick,
  onMilestoneClick,
  onTaskCreate,
  onSubtaskCreate,
  onGenerateSubtasks,
  onDeleteTask,
  onBatchTaskUpdate,
  onDependencyUpdate,
  onMilestoneLink,
  onDeleteMilestone,
  onGenerateMilestoneTasks,
  onPhaseCreate,
  className,
}) => {
  const timezone = useTimezone();
  const today = useMemo(() => todayInTimezone(timezone), [timezone]);
  const [viewMode, setViewMode] = useState<ViewMode>('day');
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(() => new Set(phases.map(p => p.id)));
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [showTaskList, setShowTaskList] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [isAddingPhase, setIsAddingPhase] = useState(false);
  const [newPhaseName, setNewPhaseName] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sidebarResizeRef = useRef<{ startX: number; startWidth: number } | null>(null);

  // Phase 3: Task reordering state (frontend-only session state)
  const [taskOrderMap, setTaskOrderMap] = useState<Map<string, number>>(new Map());
  // Milestone reordering state (frontend-only session state)
  const [milestoneOrderMap, setMilestoneOrderMap] = useState<Map<string, number>>(new Map());

  // Phase 5: Link mode state
  const [isLinkMode, setIsLinkMode] = useState<boolean>(false);
  const [linkSourceTask, setLinkSourceTask] = useState<string | null>(null);

  // Phase 6: Milestone drop target state
  const [dropTargetMilestone, setDropTargetMilestone] = useState<string | null>(null);

  // Dependency deletion confirmation state
  const [pendingDeleteArrow, setPendingDeleteArrow] = useState<{ fromId: string; toId: string; x: number; y: number } | null>(null);

  // Task deletion confirmation state
  const [pendingDeleteTask, setPendingDeleteTask] = useState<{ id: string; title: string } | null>(null);

  // Milestone deletion confirmation state
  const [pendingDeleteMilestone, setPendingDeleteMilestone] = useState<{ id: string; title: string } | null>(null);

  // Lightning line state
  const [showLightningLine, setShowLightningLine] = useState(false);
  const [lightningData, setLightningData] = useState<LightningLineResponse | null>(null);
  const [lightningError, setLightningError] = useState<string | null>(null);

  // Scroll position management - prevent unwanted scrolls on state changes
  const initialScrollDoneRef = useRef(false);
  const prevViewModeRef = useRef<ViewMode>(viewMode);
  const prevDayWidthRef = useRef<number>(viewMode === 'day' ? 40 : viewMode === 'week' ? 16 : 6);

  // Middle mouse button pan scroll state
  const panStateRef = useRef<{
    isPanning: boolean;
    startX: number;
    scrollLeft: number;
  } | null>(null);

  // Undo/Redo history stacks
  const [historyStack, setHistoryStack] = useState<HistoryEntry[]>([]);
  const [futureStack, setFutureStack] = useState<HistoryEntry[]>([]);
  const isUndoRedoRef = useRef(false); // Flag to prevent recording during undo/redo

  // Dnd-kit sensors for sidebar reordering
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px drag before activating
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const [dragState, setDragState] = useState<{
    rowId: string;
    type: 'move' | 'resize-start' | 'resize-end';
    startX: number;
    originalStart: number;
    originalEnd: number;
    previewStart: number;
    previewEnd: number;
    // Dependent tasks preview (taskId -> { startDelta, endDelta })
    dependentPreviews: Map<string, { originalStart: number; originalEnd: number; previewStart: number; previewEnd: number }>;
    // Ctrl key held: cascade dependencies and move dependent tasks together
    cascadeDependencies: boolean;
  } | null>(null);

  const parseDate = useCallback(
    (dateStr: string | undefined): DateTime | null => {
      if (!dateStr) return null;
      const parsed = toDateTime(dateStr, timezone).startOf('day');
      return parsed.isValid ? parsed : null;
    },
    [timezone],
  );

  // 日付範囲の計算（前後3ヶ月 = 約180日）
  const dateRange = useMemo(() => {
    const allDates: DateTime[] = [];

    // フェーズの日付
    phases.forEach(p => {
      const start = parseDate(p.start_date);
      const end = parseDate(p.end_date);
      if (start) allDates.push(start);
      if (end) allDates.push(end);
    });

    // マイルストーンの日付
    milestones.forEach(m => {
      const due = parseDate(m.due_date);
      if (due) allDates.push(due);
    });

    // タスクの日付
    tasks.forEach(t => {
      const due = parseDate(t.due_date);
      const start = parseDate(t.start_not_before);
      if (due) allDates.push(due);
      if (start) allDates.push(start);
    });

    if (allDates.length === 0) {
      allDates.push(today);
    }

    const minMillis = Math.min(...allDates.map(d => d.toMillis()));
    const maxMillis = Math.max(...allDates.map(d => d.toMillis()));
    const minDate = DateTime.fromMillis(minMillis, { zone: timezone }).startOf('day');
    const maxDate = DateTime.fromMillis(maxMillis, { zone: timezone }).startOf('day');

    // 前後に余裕を持たせる（前1ヶ月、後2ヶ月）
    const rangeStart = minDate.minus({ days: 30 });
    const rangeEnd = maxDate.plus({ days: 60 });

    const days = Math.ceil(rangeEnd.diff(rangeStart, 'days').days) + 1;
    return generateDateRange(rangeStart, Math.max(days, 90));
  }, [phases, milestones, tasks, parseDate, timezone, today]);

  // 月ヘッダーの計算
  const monthHeaders = useMemo((): MonthHeader[] => {
    const headers: MonthHeader[] = [];
    let currentMonthKey = '';
    let startIndex = 0;

    dateRange.forEach((date, index) => {
      const monthKey = `${date.year}-${date.month}`;

      if (monthKey !== currentMonthKey) {
        if (currentMonthKey) {
          headers.push({
            label: formatMonthYear(dateRange[startIndex].startOf('month')),
            startIndex,
            span: index - startIndex,
          });
        }
        currentMonthKey = monthKey;
        startIndex = index;
      }
    });

    // ????????E????????????
    if (currentMonthKey) {
      headers.push({
        label: formatMonthYear(dateRange[startIndex].startOf('month')),
        startIndex,
        span: dateRange.length - startIndex,
      });
    }

    return headers;
  }, [dateRange]);

  // 日付→インデックスのマップ
  const dateIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    dateRange.forEach((date, index) => {
      const dateKey = date.toISODate();
      if (dateKey) {
        map.set(dateKey, index);
      }
    });
    return map;
  }, [dateRange]);

  // 日付文字列からインデックスを取得
  const getDateIndex = useCallback((dateStr: string | undefined): number => {
    if (!dateStr) return -1;
    const normalized = toDateKey(dateStr, timezone);
    return dateIndexMap.get(normalized) ?? -1;
  }, [dateIndexMap, timezone]);

  // Phase 4: Helper to find all dependent tasks recursively
  const findAllDependentTasks = useCallback((taskId: string, allTasks: Task[]): Task[] => {
    const dependents: Task[] = [];
    const visited = new Set<string>();

    const findDeps = (id: string) => {
      for (const task of allTasks) {
        if (task.dependency_ids?.includes(id) && !visited.has(task.id)) {
          visited.add(task.id);
          dependents.push(task);
          findDeps(task.id); // Recursively find dependents of dependents
        }
      }
    };

    findDeps(taskId);
    return dependents;
  }, []);

  // タスクをフェーズでグループ化
  const tasksByPhase = useMemo(() => {
    const map = new Map<string, Task[]>();
    tasks.forEach(t => {
      const phaseId = t.phase_id || 'unassigned';
      const list = map.get(phaseId) || [];
      list.push(t);
      map.set(phaseId, list);
    });
    return map;
  }, [tasks]);


  // マイルストーンをフェーズでグループ化
  const milestonesByPhase = useMemo(() => {
    const map = new Map<string, Milestone[]>();
    milestones.forEach(m => {
      const list = map.get(m.phase_id) || [];
      list.push(m);
      map.set(m.phase_id, list);
    });
    return map;
  }, [milestones]);

  // 行データの構築
  const rows = useMemo((): GanttRow[] => {
    const result: GanttRow[] = [];

    // フェーズ順にソート
    const sortedPhases = [...phases].sort((a, b) => a.order_in_project - b.order_in_project);

    sortedPhases.forEach(phase => {
      const isExpanded = expandedPhases.has(phase.id);
      const phaseTasks = tasksByPhase.get(phase.id) || [];
      const phaseMilestones = milestonesByPhase.get(phase.id) || [];

      // フェーズの日付範囲を計算
      let startIndex = -1;
      let endIndex = -1;

      if (phase.start_date && phase.end_date) {
        startIndex = getDateIndex(phase.start_date);
        endIndex = getDateIndex(phase.end_date);
      }

      // タスクとマイルストーンから推定（フェーズ日付がない場合）
      if (startIndex === -1 || endIndex === -1) {
        const indices: number[] = [];
        phaseTasks.forEach(t => {
          const si = getDateIndex(t.start_not_before);
          const ei = getDateIndex(t.due_date);
          if (si >= 0) indices.push(si);
          if (ei >= 0) indices.push(ei);
        });
        phaseMilestones.forEach(m => {
          const mi = getDateIndex(m.due_date);
          if (mi >= 0) indices.push(mi);
        });
        if (indices.length > 0) {
          startIndex = Math.min(...indices);
          endIndex = Math.max(...indices);
        } else {
          // デフォルト: 今日から2週間
          const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
          startIndex = todayIdx;
          endIndex = todayIdx + 14;
        }
      }

      // 進捗計算
      const completedTasks = phaseTasks.filter(t => t.status === 'DONE').length;
      const progress = phaseTasks.length > 0 ? (completedTasks / phaseTasks.length) * 100 : 0;

      // フェーズ行
      result.push({
        type: 'phase',
        id: phase.id,
        title: phase.name,
        depth: 0,
        phaseId: phase.id,
        bar: { startIndex, endIndex, progress, status: 'phase' },
        isExpanded,
        childCount: phaseTasks.filter(t => !t.parent_id).length + phaseMilestones.length,
      });

      if (isExpanded) {
        // マイルストーン（ソート済み - カスタム順があれば優先、なければ期限順）
        const sortedMilestones = [...phaseMilestones].sort((a, b) => {
          const orderA = milestoneOrderMap.get(a.id);
          const orderB = milestoneOrderMap.get(b.id);

          // If both have custom order, use it
          if (orderA !== undefined && orderB !== undefined) {
            return orderA - orderB;
          }
          // If neither has custom order, sort by due_date
          if (orderA === undefined && orderB === undefined) {
            const dateA = parseDate(a.due_date)?.toMillis() ?? Infinity;
            const dateB = parseDate(b.due_date)?.toMillis() ?? Infinity;
            return dateA - dateB;
          }
          // Milestones with custom order come first
          return orderA !== undefined ? -1 : 1;
        });

        // 親タスク（サブタスクを持つか、親がないタスク）
        const parentTasks = phaseTasks.filter(t => !t.parent_id);

        // Phase 3 & 6: Sort tasks by custom order (taskOrderMap), fallback to due_date/start_not_before
        const sortedTasks = [...parentTasks].sort((a, b) => {
          const orderA = taskOrderMap.get(a.id);
          const orderB = taskOrderMap.get(b.id);

          // If both have custom order, use it
          if (orderA !== undefined && orderB !== undefined) {
            return orderA - orderB;
          }
          // If neither has custom order, sort by due_date (fallback to start_not_before)
          if (orderA === undefined && orderB === undefined) {
            const dateA = parseDate(a.due_date || a.start_not_before)?.toMillis() ?? Infinity;
            const dateB = parseDate(b.due_date || b.start_not_before)?.toMillis() ?? Infinity;
            return dateA - dateB;
          }
          // Tasks with custom order come first
          return orderA !== undefined ? -1 : 1;
        });

        // Phase 6: Separate tasks linked to milestones
        const tasksLinkedToMilestones = new Map<string, Task[]>();
        const unlinkedTasks: Task[] = [];
        sortedTasks.forEach(task => {
          if (task.milestone_id) {
            const list = tasksLinkedToMilestones.get(task.milestone_id) || [];
            list.push(task);
            tasksLinkedToMilestones.set(task.milestone_id, list);
          } else {
            unlinkedTasks.push(task);
          }
        });

        // Add milestones with their linked tasks
        sortedMilestones.forEach(milestone => {
          const idx = getDateIndex(milestone.due_date);
          const hasNoDate = !milestone.due_date;
          // For undated milestones, show at today's position
          const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
          const displayIdx = hasNoDate ? todayIdx : idx;

          // Always add milestone to rows (sidebar), even if date is out of range
          result.push({
            type: 'milestone',
            id: milestone.id,
            title: milestone.title,
            depth: 1,
            phaseId: phase.id,
            // bar is set for both dated and undated milestones
            bar: displayIdx >= 0
              ? { startIndex: displayIdx, endIndex: displayIdx, progress: milestone.status === 'COMPLETED' ? 100 : 0, status: 'milestone' }
              : undefined,
            milestoneDate: parseDate(milestone.due_date) || undefined,
            hasNoDate,
          });

          // Add tasks linked to this milestone (indented)
          const linkedTasks = tasksLinkedToMilestones.get(milestone.id) || [];
          linkedTasks.forEach(task => {
            const estimatedMinutes = task.estimated_minutes || 60;
            const startDateStr = task.start_not_before || task.created_at;
            let taskStartIndex = getDateIndex(startDateStr);
            let taskEndIndex = getDateIndex(task.due_date);
            const hasNoDate = !task.due_date && !task.start_not_before;

            // For undated tasks, show at today's position
            if (hasNoDate) {
              const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
              taskStartIndex = todayIdx;
              taskEndIndex = todayIdx + 1;
            } else {
              if (taskStartIndex < 0 && taskEndIndex >= 0) {
                const estimatedDays = Math.max(1, Math.ceil(estimatedMinutes / (8 * 60)));
                taskStartIndex = Math.max(0, taskEndIndex - estimatedDays + 1);
              }
              if (taskEndIndex < 0) {
                taskEndIndex = taskStartIndex >= 0 ? taskStartIndex + 1 : -1;
              }
              if (taskStartIndex < 0) taskStartIndex = taskEndIndex;
              if (taskStartIndex < 0 || taskEndIndex < 0) return;
            }

            const subtasks = tasks.filter(t => t.parent_id === task.id);
            const isTaskExpanded = expandedTasks.has(task.id);

            result.push({
              type: 'task',
              id: task.id,
              title: task.title,
              depth: 1, // Same level as unlinked tasks (milestone relationship shown via icon/border)
              phaseId: phase.id,
              bar: {
                startIndex: Math.min(taskStartIndex, taskEndIndex),
                endIndex: Math.max(taskStartIndex, taskEndIndex),
                progress: task.progress ?? (task.status === 'DONE' ? 100 : 0),
                status: task.status,
              },
              dependencyIds: task.dependency_ids,
              subtaskCount: subtasks.length > 0 ? subtasks.length : undefined,
              linkedMilestoneId: milestone.id,
              linkedMilestoneDateIndex: displayIdx >= 0 ? displayIdx : undefined,
              hasNoDate,
              isExpanded: isTaskExpanded,
            });

            // Add subtasks if parent is expanded
            if (isTaskExpanded && subtasks.length > 0) {
              subtasks
                .sort((a, b) => (a.order_in_parent ?? 0) - (b.order_in_parent ?? 0))
                .forEach(subtask => {
                  const subStartStr = subtask.start_not_before || subtask.created_at;
                  let subStartIndex = getDateIndex(subStartStr);
                  let subEndIndex = getDateIndex(subtask.due_date);
                  const subHasNoDate = !subtask.due_date && !subtask.start_not_before;

                  if (subHasNoDate) {
                    const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
                    subStartIndex = todayIdx;
                    subEndIndex = todayIdx + 1;
                  } else {
                    if (subStartIndex < 0 && subEndIndex >= 0) {
                      const estDays = Math.max(1, Math.ceil((subtask.estimated_minutes || 60) / (8 * 60)));
                      subStartIndex = Math.max(0, subEndIndex - estDays + 1);
                    }
                    if (subEndIndex < 0) subEndIndex = subStartIndex >= 0 ? subStartIndex + 1 : -1;
                    if (subStartIndex < 0) subStartIndex = subEndIndex;
                    if (subStartIndex < 0 || subEndIndex < 0) return;
                  }

                  result.push({
                    type: 'subtask',
                    id: subtask.id,
                    title: subtask.title,
                    depth: 2,
                    phaseId: phase.id,
                    parentTaskId: task.id,
                    bar: {
                      startIndex: Math.min(subStartIndex, subEndIndex),
                      endIndex: Math.max(subStartIndex, subEndIndex),
                      progress: subtask.progress ?? (subtask.status === 'DONE' ? 100 : 0),
                      status: subtask.status,
                    },
                    dependencyIds: subtask.dependency_ids,
                    hasNoDate: subHasNoDate,
                  });
                });
            }
          });
        });

        // Add unlinked tasks
        unlinkedTasks.forEach(task => {
            const estimatedMinutes = task.estimated_minutes || 60;

            // 着手日（start_not_before）または作成日（created_at）から期限（due_date）を表示
            const startDateStr = task.start_not_before || task.created_at;
            let taskStartIndex = getDateIndex(startDateStr);
            let taskEndIndex = getDateIndex(task.due_date);
            const hasNoDate = !task.due_date && !task.start_not_before;

            // For undated tasks, show at today's position
            if (hasNoDate) {
              const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
              taskStartIndex = todayIdx;
              taskEndIndex = todayIdx + 1;
            } else {
              // 開始日がなく期限がある場合、見積時間から逆算
              if (taskStartIndex < 0 && taskEndIndex >= 0) {
                const estimatedDays = Math.max(1, Math.ceil(estimatedMinutes / (8 * 60)));
                taskStartIndex = Math.max(0, taskEndIndex - estimatedDays + 1);
              }

              // 期限がない場合、開始日+1
              if (taskEndIndex < 0) {
                taskEndIndex = taskStartIndex >= 0 ? taskStartIndex + 1 : -1;
              }

              if (taskStartIndex < 0) taskStartIndex = taskEndIndex;

              if (taskStartIndex < 0 || taskEndIndex < 0) return;
            }

            const subtasks = tasks.filter(t => t.parent_id === task.id);
            const hasSubtasks = subtasks.length > 0;
            const isTaskExpanded = expandedTasks.has(task.id);

            result.push({
              type: 'task',
              id: task.id,
              title: task.title,
              depth: 1,
              phaseId: phase.id,
              bar: {
                startIndex: Math.min(taskStartIndex, taskEndIndex),
                endIndex: Math.max(taskStartIndex, taskEndIndex),
                progress: task.progress ?? (task.status === 'DONE' ? 100 : 0),
                status: task.status,
              },
              dependencyIds: task.dependency_ids,
              subtaskCount: hasSubtasks ? subtasks.length : undefined,
              hasNoDate,
              isExpanded: isTaskExpanded,
            });

            // Add subtasks if parent is expanded
            if (isTaskExpanded && subtasks.length > 0) {
              subtasks
                .sort((a, b) => (a.order_in_parent ?? 0) - (b.order_in_parent ?? 0))
                .forEach(subtask => {
                  const subStartStr = subtask.start_not_before || subtask.created_at;
                  let subStartIndex = getDateIndex(subStartStr);
                  let subEndIndex = getDateIndex(subtask.due_date);
                  const subHasNoDate = !subtask.due_date && !subtask.start_not_before;

                  if (subHasNoDate) {
                    const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
                    subStartIndex = todayIdx;
                    subEndIndex = todayIdx + 1;
                  } else {
                    if (subStartIndex < 0 && subEndIndex >= 0) {
                      const estDays = Math.max(1, Math.ceil((subtask.estimated_minutes || 60) / (8 * 60)));
                      subStartIndex = Math.max(0, subEndIndex - estDays + 1);
                    }
                    if (subEndIndex < 0) subEndIndex = subStartIndex >= 0 ? subStartIndex + 1 : -1;
                    if (subStartIndex < 0) subStartIndex = subEndIndex;
                    if (subStartIndex < 0 || subEndIndex < 0) return;
                  }

                  result.push({
                    type: 'subtask',
                    id: subtask.id,
                    title: subtask.title,
                    depth: 2,
                    phaseId: phase.id,
                    parentTaskId: task.id,
                    bar: {
                      startIndex: Math.min(subStartIndex, subEndIndex),
                      endIndex: Math.max(subStartIndex, subEndIndex),
                      progress: subtask.progress ?? (subtask.status === 'DONE' ? 100 : 0),
                      status: subtask.status,
                    },
                    dependencyIds: subtask.dependency_ids,
                    hasNoDate: subHasNoDate,
                  });
                });
            }
          });
      }
    });

    // 未割当タスク
    const unassignedTasks = tasks.filter(t => !t.phase_id && !t.parent_id);
    if (unassignedTasks.length > 0) {
      const isExpanded = expandedPhases.has('unassigned');

      // 未割当タスクの日付範囲
      const indices: number[] = [];
      unassignedTasks.forEach(t => {
        const si = getDateIndex(t.start_not_before);
        const ei = getDateIndex(t.due_date);
        if (si >= 0) indices.push(si);
        if (ei >= 0) indices.push(ei);
      });
      const minIdx = indices.length > 0 ? Math.min(...indices) : 0;
      const maxIdx = indices.length > 0 ? Math.max(...indices) : dateRange.length - 1;

      result.push({
        type: 'phase',
        id: 'unassigned',
        title: '📋 未割当タスク',
        depth: 0,
        bar: { startIndex: minIdx, endIndex: maxIdx, progress: 0, status: 'unassigned' },
        isExpanded,
        childCount: unassignedTasks.length,
      });

      if (isExpanded) {
        // Sort unassigned tasks by taskOrderMap, fallback to due_date/start_not_before
        const sortedUnassignedTasks = [...unassignedTasks].sort((a, b) => {
          const orderA = taskOrderMap.get(a.id);
          const orderB = taskOrderMap.get(b.id);

          if (orderA !== undefined && orderB !== undefined) {
            return orderA - orderB;
          }
          if (orderA === undefined && orderB === undefined) {
            const dateA = parseDate(a.due_date || a.start_not_before)?.toMillis() ?? Infinity;
            const dateB = parseDate(b.due_date || b.start_not_before)?.toMillis() ?? Infinity;
            return dateA - dateB;
          }
          return orderA !== undefined ? -1 : 1;
        });

        sortedUnassignedTasks.forEach(task => {
          let taskStartIndex = getDateIndex(task.start_not_before);
          let taskEndIndex = getDateIndex(task.due_date);
          const hasNoDate = !task.due_date && !task.start_not_before;

          // For undated tasks, show at today's position
          if (hasNoDate) {
            const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
            taskStartIndex = todayIdx;
            taskEndIndex = todayIdx + 1;
          } else {
            if (taskStartIndex < 0 && taskEndIndex >= 0) {
              const estimatedDays = Math.max(1, Math.ceil((task.estimated_minutes || 60) / (8 * 60)));
              taskStartIndex = Math.max(0, taskEndIndex - estimatedDays + 1);
            }
            if (taskEndIndex < 0 && taskStartIndex >= 0) {
              taskEndIndex = taskStartIndex + 1;
            }
            if (taskStartIndex < 0) taskStartIndex = 0;
            if (taskEndIndex < 0) taskEndIndex = 1;
          }

          // Find subtasks for unassigned tasks
          const subtasks = tasks.filter(t => t.parent_id === task.id);
          const isTaskExpanded = expandedTasks.has(task.id);

          result.push({
            type: 'task',
            id: task.id,
            title: task.title,
            depth: 1,
            phaseId: 'unassigned',  // Set phaseId for drag-and-drop
            bar: {
              startIndex: Math.min(taskStartIndex, taskEndIndex),
              endIndex: Math.max(taskStartIndex, taskEndIndex),
              progress: task.progress ?? (task.status === 'DONE' ? 100 : 0),
              status: task.status,
            },
            dependencyIds: task.dependency_ids,
            hasNoDate,
            subtaskCount: subtasks.length > 0 ? subtasks.length : undefined,
            isExpanded: isTaskExpanded,
          });

          // Add subtasks if parent is expanded
          if (isTaskExpanded && subtasks.length > 0) {
            subtasks
              .sort((a, b) => (a.order_in_parent ?? 0) - (b.order_in_parent ?? 0))
              .forEach(subtask => {
                const subStartStr = subtask.start_not_before || subtask.created_at;
                let subStartIndex = getDateIndex(subStartStr);
                let subEndIndex = getDateIndex(subtask.due_date);
                const subHasNoDate = !subtask.due_date && !subtask.start_not_before;

                if (subHasNoDate) {
                  const todayIdx = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
                  subStartIndex = todayIdx;
                  subEndIndex = todayIdx + 1;
                } else {
                  if (subStartIndex < 0 && subEndIndex >= 0) {
                    const estDays = Math.max(1, Math.ceil((subtask.estimated_minutes || 60) / (8 * 60)));
                    subStartIndex = Math.max(0, subEndIndex - estDays + 1);
                  }
                  if (subEndIndex < 0) subEndIndex = subStartIndex >= 0 ? subStartIndex + 1 : -1;
                  if (subStartIndex < 0) subStartIndex = subEndIndex;
                  if (subStartIndex < 0 || subEndIndex < 0) return;
                }

                result.push({
                  type: 'subtask',
                  id: subtask.id,
                  title: subtask.title,
                  depth: 2,
                  phaseId: 'unassigned',
                  parentTaskId: task.id,
                  bar: {
                    startIndex: Math.min(subStartIndex, subEndIndex),
                    endIndex: Math.max(subStartIndex, subEndIndex),
                    progress: subtask.progress ?? (subtask.status === 'DONE' ? 100 : 0),
                    status: subtask.status,
                  },
                  dependencyIds: subtask.dependency_ids,
                  hasNoDate: subHasNoDate,
                });
              });
          }
        });
      }
    }

    // Post-process: add assigneeName, dueDateStr, startNotBeforeStr to task/subtask rows
    const taskMap = new Map(tasks.map(t => [t.id, t]));
    result.forEach(row => {
      if (row.type === 'task' || row.type === 'subtask') {
        row.assigneeName = assigneeByTaskId[row.id];
        const task = taskMap.get(row.id);
        if (task) {
          row.dueDateStr = task.due_date;
          row.startNotBeforeStr = task.start_not_before;
        }
      }
    });

    return result;
  }, [phases, tasks, milestones, expandedPhases, expandedTasks, tasksByPhase, milestonesByPhase, dateRange, getDateIndex, dateIndexMap, taskOrderMap, milestoneOrderMap, parseDate, today, assigneeByTaskId]);

  // 依存関係の矢印データ
  const dependencyArrows = useMemo(() => {
    const arrows: { fromId: string; toId: string; fromIndex: number; toIndex: number; fromRow: number; toRow: number }[] = [];
    const rowIndexMap = new Map<string, number>();
    rows.forEach((row, index) => rowIndexMap.set(row.id, index));

    rows.forEach((row, rowIndex) => {
      if ((row.type === 'task' || row.type === 'subtask') && row.dependencyIds && row.bar) {
        const currentBar = row.bar;
        row.dependencyIds.forEach(depId => {
          const depRowIndex = rowIndexMap.get(depId);
          const depRow = rows.find(r => r.id === depId);
          if (depRowIndex !== undefined && depRow?.bar) {
            arrows.push({
              fromId: depId,
              toId: row.id,
              fromIndex: depRow.bar.endIndex,
              toIndex: currentBar.startIndex,
              fromRow: depRowIndex,
              toRow: rowIndex,
            });
          }
        });
      }
    });

    return arrows;
  }, [rows]);

  // 1日あたりの幅（ビューモードに応じて変化）
  const dayWidth = useMemo(() => {
    return viewMode === 'day' ? 40 : viewMode === 'week' ? 16 : 6;
  }, [viewMode]);

  const taskRowIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    rows.forEach((row, index) => {
      if (row.type === 'task' || row.type === 'subtask') {
        map.set(row.id, index);
      }
    });
    return map;
  }, [rows]);

  const todayIndex = useMemo(() => {
    return dateIndexMap.get(today.toISODate() ?? '') ?? 0;
  }, [dateIndexMap, today]);

  const lightningPolylinePoints = useMemo(() => {
    if (!showLightningLine || !lightningData?.points?.length) {
      return '';
    }

    const maxIndex = Math.max(dateRange.length - 1, 0);
    const plotted = lightningData.points
      .map((point) => {
        const rowIndex = taskRowIndexMap.get(point.row_key);
        if (rowIndex === undefined) {
          return null;
        }

        const xIndex = Math.max(0, Math.min(todayIndex + point.deviation_days, maxIndex));
        const x = xIndex * dayWidth + dayWidth / 2;
        const y = rowIndex * 44 + 22;
        return { x, y, rowIndex };
      })
      .filter((point): point is { x: number; y: number; rowIndex: number } => point !== null)
      .sort((a, b) => a.rowIndex - b.rowIndex);

    return plotted.map((point) => `${point.x},${point.y}`).join(' ');
  }, [showLightningLine, lightningData, taskRowIndexMap, todayIndex, dateRange.length, dayWidth]);

  // Deadline status map for task/subtask rows
  const deadlineStatusMap = useMemo(() => {
    const map = new Map<string, 'overdue' | 'approaching' | null>();
    rows.forEach(row => {
      if ((row.type === 'task' || row.type === 'subtask') && row.dueDateStr) {
        map.set(row.id, getDeadlineStatus(row.dueDateStr, row.bar?.status || '', today, timezone));
      }
    });
    return map;
  }, [rows, today, timezone]);

  useEffect(() => {
    if (!showLightningLine || !projectId) {
      setLightningData(null);
      setLightningError(null);
      return;
    }

    let isCancelled = false;
    const fetchLightningLine = async () => {
      try {
        const data = await lightningLineApi.get(projectId);
        if (!isCancelled) {
          setLightningData(data);
          setLightningError(null);
        }
      } catch (error) {
        console.error('Failed to fetch lightning line:', error);
        if (!isCancelled) {
          setLightningData(null);
          setLightningError('イナズマ線データの取得に失敗しました');
        }
      }
    };

    fetchLightningLine();
    return () => {
      isCancelled = true;
    };
  }, [showLightningLine, projectId, tasks]);

  // Scroll to today's position
  const scrollToToday = useCallback(() => {
    if (!scrollRef.current) return;
    const currentDayWidth = viewMode === 'day' ? 40 : viewMode === 'week' ? 16 : 6;
    const todayIndex = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
    const containerWidth = scrollRef.current.clientWidth;
    const scrollPosition = Math.max(0, todayIndex * currentDayWidth - containerWidth / 3);
    scrollRef.current.scrollTo({ left: scrollPosition, behavior: 'smooth' });
  }, [viewMode, dateIndexMap, today]);

  // History management for Undo/Redo
  const pushToHistory = useCallback((entry: HistoryEntry) => {
    if (isUndoRedoRef.current) return; // Don't record during undo/redo
    setHistoryStack(prev => [...prev.slice(-49), entry]); // Keep last 50 entries
    setFutureStack([]); // Clear redo stack on new action
  }, []);

  const handleUndo = useCallback(() => {
    if (historyStack.length === 0) return;

    const entry = historyStack[historyStack.length - 1];
    isUndoRedoRef.current = true;

    try {
      if (entry.type === 'task-date' && entry.itemId && entry.before && onTaskUpdate) {
        onTaskUpdate(entry.itemId, {
          start_not_before: entry.before.start,
          due_date: entry.before.end,
        });
      } else if (entry.type === 'phase-date' && entry.itemId && entry.before && onPhaseUpdate) {
        onPhaseUpdate(entry.itemId, {
          start_date: entry.before.start,
          end_date: entry.before.end,
        });
      } else if (entry.type === 'milestone-date' && entry.itemId && entry.before && onMilestoneUpdate) {
        onMilestoneUpdate(entry.itemId, {
          due_date: entry.before.start,
        });
      } else if (entry.type === 'batch-task-date' && entry.batchUpdates && onBatchTaskUpdate) {
        const undoUpdates = entry.batchUpdates.map(u => ({
          taskId: u.taskId,
          updates: {
            start_not_before: u.before.start_not_before,
            due_date: u.before.due_date,
          },
        }));
        onBatchTaskUpdate(undoUpdates);
      }

      setHistoryStack(prev => prev.slice(0, -1));
      setFutureStack(prev => [...prev, entry]);
    } finally {
      // Reset flag after a short delay to allow state updates
      setTimeout(() => { isUndoRedoRef.current = false; }, 100);
    }
  }, [historyStack, onTaskUpdate, onPhaseUpdate, onMilestoneUpdate, onBatchTaskUpdate]);

  const handleRedo = useCallback(() => {
    if (futureStack.length === 0) return;

    const entry = futureStack[futureStack.length - 1];
    isUndoRedoRef.current = true;

    try {
      if (entry.type === 'task-date' && entry.itemId && entry.after && onTaskUpdate) {
        onTaskUpdate(entry.itemId, {
          start_not_before: entry.after.start,
          due_date: entry.after.end,
        });
      } else if (entry.type === 'phase-date' && entry.itemId && entry.after && onPhaseUpdate) {
        onPhaseUpdate(entry.itemId, {
          start_date: entry.after.start,
          end_date: entry.after.end,
        });
      } else if (entry.type === 'milestone-date' && entry.itemId && entry.after && onMilestoneUpdate) {
        onMilestoneUpdate(entry.itemId, {
          due_date: entry.after.start,
        });
      } else if (entry.type === 'batch-task-date' && entry.batchUpdates && onBatchTaskUpdate) {
        const redoUpdates = entry.batchUpdates.map(u => ({
          taskId: u.taskId,
          updates: {
            start_not_before: u.after.start_not_before,
            due_date: u.after.due_date,
          },
        }));
        onBatchTaskUpdate(redoUpdates);
      }

      setFutureStack(prev => prev.slice(0, -1));
      setHistoryStack(prev => [...prev, entry]);
    } finally {
      setTimeout(() => { isUndoRedoRef.current = false; }, 100);
    }
  }, [futureStack, onTaskUpdate, onPhaseUpdate, onMilestoneUpdate, onBatchTaskUpdate]);

  // Keyboard shortcuts for Undo/Redo
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Check if focus is inside an input, textarea, or contenteditable
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        handleRedo();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleUndo, handleRedo]);

  // フェーズ展開/折りたたみ
  const togglePhase = useCallback((phaseId: string) => {
    setExpandedPhases(prev => {
      const next = new Set(prev);
      if (next.has(phaseId)) {
        next.delete(phaseId);
      } else {
        next.add(phaseId);
      }
      return next;
    });
  }, []);

  // タスク（サブタスク表示）展開/折りたたみ
  const toggleTask = useCallback((taskId: string) => {
    setExpandedTasks(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    const allIds = new Set(phases.map(p => p.id));
    if (tasks.some(t => !t.phase_id)) allIds.add('unassigned');
    setExpandedPhases(allIds);
  }, [phases, tasks]);

  const collapseAll = useCallback(() => {
    setExpandedPhases(new Set());
  }, []);

  // Phase 3: Sort tasks by due date (one-time action)
  // Sorts tasks within each phase by due_date (milestone-linked tasks grouped under their milestone)
  const sortTasksByDueDate = useCallback(() => {
    const newOrderMap = new Map<string, number>();
    let globalIndex = 0;

    // Sort by due_date helper (fallback to start_not_before if no due_date)
    const sortByDue = (a: Task, b: Task) => {
      // Use due_date first, then start_not_before as fallback
      const dateStrA = a.due_date || a.start_not_before;
      const dateStrB = b.due_date || b.start_not_before;
      const dateA = dateStrA ? toDateTime(dateStrA, timezone).toMillis() : Infinity;
      const dateB = dateStrB ? toDateTime(dateStrB, timezone).toMillis() : Infinity;
      return dateA - dateB;
    };

    // Process each phase
    const sortedPhases = [...phases].sort((a, b) => a.order_in_project - b.order_in_project);

    sortedPhases.forEach(phase => {
      const phaseTasks = (tasksByPhase.get(phase.id) || []).filter(t => !t.parent_id);
      const phaseMilestones = milestonesByPhase.get(phase.id) || [];

      // Group tasks by milestone_id
      const tasksByMilestone = new Map<string, Task[]>();
      const unlinkedTasks: Task[] = [];

      phaseTasks.forEach(task => {
        if (task.milestone_id) {
          const list = tasksByMilestone.get(task.milestone_id) || [];
          list.push(task);
          tasksByMilestone.set(task.milestone_id, list);
        } else {
          unlinkedTasks.push(task);
        }
      });

      // Sort milestones by due_date
      const sortedMilestones = [...phaseMilestones].sort((a, b) => {
        const dateA = a.due_date ? toDateTime(a.due_date, timezone).toMillis() : Infinity;
        const dateB = b.due_date ? toDateTime(b.due_date, timezone).toMillis() : Infinity;
        return dateA - dateB;
      });

      // Add tasks grouped under milestones (sorted by due_date within each milestone)
      sortedMilestones.forEach(milestone => {
        const tasksInMilestone = tasksByMilestone.get(milestone.id) || [];
        tasksInMilestone.sort(sortByDue);
        tasksInMilestone.forEach(task => {
          newOrderMap.set(task.id, globalIndex++);
        });
      });

      // Add unlinked tasks (sorted by due_date)
      unlinkedTasks.sort(sortByDue);
      unlinkedTasks.forEach(task => {
        newOrderMap.set(task.id, globalIndex++);
      });
    });

    // Handle unassigned tasks
    const unassignedTasks = tasks.filter(t => !t.phase_id && !t.parent_id);
    unassignedTasks.sort(sortByDue);
    unassignedTasks.forEach(task => {
      newOrderMap.set(task.id, globalIndex++);
    });

    setTaskOrderMap(newOrderMap);
  }, [tasks, phases, tasksByPhase, milestonesByPhase, milestones, timezone]);

  // Handle sidebar drag over for milestone highlighting
  const handleSidebarDragOver = useCallback((event: DragOverEvent) => {
    const { over } = event;
    if (over && String(over.id).startsWith('milestone-drop-')) {
      const milestoneId = (over.data.current as { milestoneId?: string })?.milestoneId;
      setDropTargetMilestone(milestoneId || null);
    } else {
      setDropTargetMilestone(null);
    }
  }, []);

  // Handle sidebar drag end for task/milestone reordering or milestone linking
  const handleSidebarDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;

    // Clear drop target
    setDropTargetMilestone(null);

    if (!over || active.id === over.id) return;

    // Check if dropping on a milestone (task -> milestone linking)
    if (String(over.id).startsWith('milestone-drop-')) {
      const milestoneId = (over.data.current as { milestoneId?: string })?.milestoneId;
      if (milestoneId && onMilestoneLink) {
        onMilestoneLink(active.id as string, milestoneId);
      }
      return;
    }

    // Determine if the dragged item is a task or milestone
    const activeRow = rows.find(r => r.id === active.id);
    const overRow = rows.find(r => r.id === over.id);

    if (!activeRow || !overRow) return;

    // Handle milestone reordering (milestone -> milestone, same phase only)
    if (activeRow.type === 'milestone' && overRow.type === 'milestone') {
      // Only allow reordering within the same phase
      if (activeRow.phaseId !== overRow.phaseId) return;

      const milestoneRows = rows.filter(r => r.type === 'milestone');
      const milestoneIds = milestoneRows.map(r => r.id);

      const oldIndex = milestoneIds.indexOf(active.id as string);
      const newIndex = milestoneIds.indexOf(over.id as string);

      if (oldIndex === -1 || newIndex === -1) return;

      // Reorder the array
      const reorderedIds = arrayMove(milestoneIds, oldIndex, newIndex);

      // Update the milestone order map (preserving existing orders)
      const newOrderMap = new Map<string, number>(milestoneOrderMap);
      reorderedIds.forEach((id, index) => {
        newOrderMap.set(id, index);
      });
      setMilestoneOrderMap(newOrderMap);
      return;
    }

    // Handle task reordering (task -> task, same phase only)
    if (activeRow.type === 'task' && overRow.type === 'task') {
      // Only allow reordering within the same phase
      if (activeRow.phaseId !== overRow.phaseId) return;

      // Get all task rows and their current order
      const taskRows = rows.filter(r => r.type === 'task');
      const taskIds = taskRows.map(r => r.id);

      const oldIndex = taskIds.indexOf(active.id as string);
      const newIndex = taskIds.indexOf(over.id as string);

      if (oldIndex === -1 || newIndex === -1) return;

      // Reorder the array
      const reorderedIds = arrayMove(taskIds, oldIndex, newIndex);

      // Update the task order map (preserving existing orders and adding new ones)
      const newOrderMap = new Map<string, number>(taskOrderMap);
      reorderedIds.forEach((id, index) => {
        newOrderMap.set(id, index);
      });
      setTaskOrderMap(newOrderMap);
    }
  }, [rows, onMilestoneLink, taskOrderMap, milestoneOrderMap]);

  // Phase 5: Handle link mode task click
  const handleLinkModeClick = useCallback((taskId: string) => {
    if (!isLinkMode) return;

    if (!linkSourceTask) {
      // First click - select source
      setLinkSourceTask(taskId);
    } else if (linkSourceTask !== taskId) {
      // Second click - create dependency (source -> target)
      const targetTask = tasks.find(t => t.id === taskId);
      if (targetTask && onDependencyUpdate) {
        const newDependencies = [...(targetTask.dependency_ids || [])];
        if (!newDependencies.includes(linkSourceTask)) {
          newDependencies.push(linkSourceTask);
          onDependencyUpdate(taskId, newDependencies);
        }
      }
      setLinkSourceTask(null);
    }
  }, [isLinkMode, linkSourceTask, tasks, onDependencyUpdate]);

  // 今日の位置にスクロール (初回マウント時のみ)
  // viewMode変更時は相対位置を維持
  useEffect(() => {
    if (!scrollRef.current) return;

    const currentDayWidth = viewMode === 'day' ? 40 : viewMode === 'week' ? 16 : 6;

    if (!initialScrollDoneRef.current) {
      // Initial scroll to today - center today in roughly the left third of the viewport
      const todayIndex = dateIndexMap.get(today.toISODate() ?? '') ?? 0;
      const containerWidth = scrollRef.current.clientWidth;
      const scrollPosition = Math.max(0, todayIndex * currentDayWidth - containerWidth / 3);
      scrollRef.current.scrollLeft = scrollPosition;
      initialScrollDoneRef.current = true;
    } else if (prevViewModeRef.current !== viewMode) {
      // viewMode changed - maintain relative scroll position
      const prevDayWidth = prevDayWidthRef.current;
      const currentScrollLeft = scrollRef.current.scrollLeft;
      // Convert current position to day index (roughly)
      const dayIndex = currentScrollLeft / prevDayWidth;
      // Apply same day index with new day width
      scrollRef.current.scrollLeft = dayIndex * currentDayWidth;
    }

    prevViewModeRef.current = viewMode;
    prevDayWidthRef.current = currentDayWidth;
  }, [dateIndexMap, viewMode, today]);

  // ドラッグ状態をrefで保持（最新の値にアクセスするため）
  const dragStateRef = useRef(dragState);
  useLayoutEffect(() => {
    dragStateRef.current = dragState;
  }, [dragState]);

  // ドラッグ中のイベントハンドラをrefで保持
  const handleMouseMoveRef = useRef<((e: MouseEvent) => void) | null>(null);
  const handleMouseUpRef = useRef<((e: MouseEvent) => void) | null>(null);

  // Middle mouse button pan scroll handlers
  const handleTimelineMouseDown = useCallback((e: React.MouseEvent) => {
    // Only handle middle mouse button (button === 1)
    if (e.button !== 1) return;

    e.preventDefault();

    if (scrollRef.current) {
      panStateRef.current = {
        isPanning: true,
        startX: e.clientX,
        scrollLeft: scrollRef.current.scrollLeft,
      };
      scrollRef.current.style.cursor = 'grabbing';
    }
  }, []);

  // Effect to handle pan scroll mouse events
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!panStateRef.current?.isPanning || !scrollRef.current) return;

      const deltaX = e.clientX - panStateRef.current.startX;
      scrollRef.current.scrollLeft = panStateRef.current.scrollLeft - deltaX;
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (e.button === 1 && panStateRef.current?.isPanning && scrollRef.current) {
        panStateRef.current = null;
        scrollRef.current.style.cursor = '';
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Sidebar resize handlers
  const handleSidebarResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    sidebarResizeRef.current = {
      startX: e.clientX,
      startWidth: sidebarWidth,
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [sidebarWidth]);

  useEffect(() => {
    const handleResizeMove = (e: MouseEvent) => {
      if (!sidebarResizeRef.current) return;
      const delta = e.clientX - sidebarResizeRef.current.startX;
      const newWidth = Math.max(160, Math.min(600, sidebarResizeRef.current.startWidth + delta));
      setSidebarWidth(newWidth);
    };

    const handleResizeEnd = () => {
      if (sidebarResizeRef.current) {
        sidebarResizeRef.current = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    document.addEventListener('mousemove', handleResizeMove);
    document.addEventListener('mouseup', handleResizeEnd);

    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
    };
  }, []);

  // ドラッグ開始
  const handleDragStart = useCallback((
    e: React.MouseEvent,
    rowId: string,
    type: 'move' | 'resize-start' | 'resize-end',
    bar: GanttBar
  ) => {
    // Only handle left mouse button (button === 0)
    if (e.button !== 0) return;

    e.preventDefault();
    e.stopPropagation();

    // Check if Ctrl key is held - if so, cascade to dependent tasks
    const cascadeDependencies = e.ctrlKey || e.metaKey;

    // Find dependent tasks and their original positions for preview
    // Only if Ctrl IS held (cascade mode)
    const dependentPreviews = new Map<string, { originalStart: number; originalEnd: number; previewStart: number; previewEnd: number }>();
    if (type === 'move' && cascadeDependencies) {
      const dependentTasks = findAllDependentTasks(rowId, tasks);
      dependentTasks.forEach(depTask => {
        const depRow = rows.find(r => r.id === depTask.id);
        if (depRow?.bar) {
          dependentPreviews.set(depTask.id, {
            originalStart: depRow.bar.startIndex,
            originalEnd: depRow.bar.endIndex,
            previewStart: depRow.bar.startIndex,
            previewEnd: depRow.bar.endIndex,
          });
        }
      });
    }

    const initialState = {
      rowId,
      type,
      startX: e.clientX,
      originalStart: bar.startIndex,
      originalEnd: bar.endIndex,
      previewStart: bar.startIndex,
      previewEnd: bar.endIndex,
      dependentPreviews,
      cascadeDependencies,
    };

    setDragState(initialState);
    dragStateRef.current = initialState;

    // ドラッグ中のハンドラを定義
    const handleMouseMove = (moveEvent: MouseEvent) => {
      const currentState = dragStateRef.current;
      if (!currentState) return;

      const currentDayWidth = viewMode === 'day' ? 40 : viewMode === 'week' ? 16 : 6;
      const deltaX = moveEvent.clientX - currentState.startX;
      const deltaDays = Math.round(deltaX / currentDayWidth);

      let newStart = currentState.originalStart;
      let newEnd = currentState.originalEnd;

      if (currentState.type === 'move') {
        newStart += deltaDays;
        newEnd += deltaDays;
      } else if (currentState.type === 'resize-start') {
        newStart += deltaDays;
        if (newStart > currentState.originalEnd) newStart = currentState.originalEnd;
      } else if (currentState.type === 'resize-end') {
        newEnd += deltaDays;
        if (newEnd < currentState.originalStart) newEnd = currentState.originalStart;
      }

      // 範囲内に収める
      const maxIndex = dateRange.length - 1;
      newStart = Math.max(0, Math.min(newStart, maxIndex));
      newEnd = Math.max(0, Math.min(newEnd, maxIndex));

      // Note: Milestone linking is handled only via sidebar drag-and-drop (dnd-kit),
      // not via timeline bar dragging

      // Update dependent task previews (only if cascading dependencies with Ctrl)
      const newDependentPreviews = new Map(currentState.dependentPreviews);
      if (currentState.type === 'move' && deltaDays !== 0 && currentState.cascadeDependencies) {
        currentState.dependentPreviews.forEach((preview, taskId) => {
          newDependentPreviews.set(taskId, {
            ...preview,
            previewStart: Math.max(0, Math.min(preview.originalStart + deltaDays, maxIndex)),
            previewEnd: Math.max(0, Math.min(preview.originalEnd + deltaDays, maxIndex)),
          });
        });
      }

      // プレビュー位置を更新
      const newState = {
        ...currentState,
        previewStart: newStart,
        previewEnd: newEnd,
        dependentPreviews: newDependentPreviews,
      };
      setDragState(newState);
      dragStateRef.current = newState;
    };

    const handleMouseUp = (upEvent: MouseEvent) => {
      const currentState = dragStateRef.current;
      if (!currentState) {
        cleanup();
        return;
      }

      const currentDayWidth = viewMode === 'day' ? 40 : viewMode === 'week' ? 16 : 6;
      const deltaX = upEvent.clientX - currentState.startX;
      const deltaDays = Math.round(deltaX / currentDayWidth);

      const row = rows.find(r => r.id === currentState.rowId);

      if (deltaDays !== 0) {
        // ドラッグが発生した場合は日付を更新
        if (row) {
          let newStart = currentState.originalStart;
          let newEnd = currentState.originalEnd;

          if (currentState.type === 'move') {
            newStart += deltaDays;
            newEnd += deltaDays;
          } else if (currentState.type === 'resize-start') {
            newStart += deltaDays;
          } else if (currentState.type === 'resize-end') {
            newEnd += deltaDays;
          }

          // 日付に変換
          const maxIndex = dateRange.length - 1;
          const startDate = dateRange[Math.max(0, Math.min(newStart, maxIndex))]?.toISODate();
          const endDate = dateRange[Math.max(0, Math.min(newEnd, maxIndex))]?.toISODate();

          if (startDate && endDate) {
            if (row.type === 'task' || row.type === 'subtask') {
              // Get original task data for history
              const task = tasks.find(t => t.id === row.id);
              const originalStartDate = dateRange[currentState.originalStart]?.toISODate();
              const originalEndDate = dateRange[currentState.originalEnd]?.toISODate();

              // Phase 4: Dependency cascade - cascade to dependents in both directions
              // Only cascade if Ctrl key IS held (cascadeDependencies === true)
              if (currentState.type === 'move' && onBatchTaskUpdate && currentState.cascadeDependencies) {
                const dependentTasks = findAllDependentTasks(row.id, tasks);
                if (dependentTasks.length > 0) {
                  // Batch update: main task + all dependents
                  const updates: Array<{ taskId: string; updates: Partial<TaskUpdate> }> = [
                    { taskId: row.id, updates: { start_not_before: startDate, due_date: endDate } }
                  ];
                  // Build history entry for batch update
                  const historyBatch: Array<{
                    taskId: string;
                    before: { start_not_before?: string; due_date?: string };
                    after: { start_not_before?: string; due_date?: string };
                  }> = [{
                    taskId: row.id,
                    before: { start_not_before: task?.start_not_before, due_date: task?.due_date },
                    after: { start_not_before: startDate, due_date: endDate },
                  }];

                  dependentTasks.forEach(depTask => {
                    const depStartStr = depTask.start_not_before || depTask.created_at;
                    const depStart = parseDate(depStartStr);
                    const depEnd = parseDate(depTask.due_date);
                    if (depStart && depEnd) {
                      const newDepStart = depStart.plus({ days: deltaDays }).toISODate();
                      const newDepEnd = depEnd.plus({ days: deltaDays }).toISODate();
                      if (newDepStart && newDepEnd) {
                        updates.push({
                          taskId: depTask.id,
                          updates: { start_not_before: newDepStart, due_date: newDepEnd }
                        });
                        historyBatch.push({
                          taskId: depTask.id,
                          before: { start_not_before: depTask.start_not_before, due_date: depTask.due_date },
                          after: { start_not_before: newDepStart, due_date: newDepEnd },
                        });
                      }
                    }
                  });

                  // Record to history before updating
                  pushToHistory({
                    type: 'batch-task-date',
                    timestamp: Date.now(),
                    batchUpdates: historyBatch,
                  });
                  onBatchTaskUpdate(updates);
                } else if (onTaskUpdate) {
                  // No dependents, just update the task
                  pushToHistory({
                    type: 'task-date',
                    timestamp: Date.now(),
                    itemId: row.id,
                    before: { start: originalStartDate ?? undefined, end: originalEndDate ?? undefined },
                    after: { start: startDate, end: endDate },
                  });
                  onTaskUpdate(row.id, { start_not_before: startDate, due_date: endDate });
                }
              } else if (onTaskUpdate) {
                // Resizing or no batch handler, just update the task
                pushToHistory({
                  type: 'task-date',
                  timestamp: Date.now(),
                  itemId: row.id,
                  before: { start: originalStartDate ?? undefined, end: originalEndDate ?? undefined },
                  after: { start: startDate, end: endDate },
                });
                onTaskUpdate(row.id, { start_not_before: startDate, due_date: endDate });
              }
            } else if (row.type === 'phase' && onPhaseUpdate) {
              const phase = phases.find(p => p.id === row.id);
              pushToHistory({
                type: 'phase-date',
                timestamp: Date.now(),
                itemId: row.id,
                before: { start: phase?.start_date, end: phase?.end_date },
                after: { start: startDate, end: endDate },
              });
              onPhaseUpdate(row.id, { start_date: startDate, end_date: endDate });
            } else if (row.type === 'milestone' && onMilestoneUpdate) {
              const milestone = milestones.find(m => m.id === row.id);
              pushToHistory({
                type: 'milestone-date',
                timestamp: Date.now(),
                itemId: row.id,
                before: { start: milestone?.due_date, end: milestone?.due_date },
                after: { start: startDate, end: startDate },
              });
              // Milestones only have a due_date (same as startDate for milestone)
              onMilestoneUpdate(row.id, { due_date: startDate });
            }
          }
        }
      } else {
        // ドラッグが発生しなかった場合はクリックとして扱う
        // ただし、5px以上動いていたらドラッグ意図とみなしてクリックしない
        const absMovement = Math.abs(deltaX);
        const isClick = absMovement < 5;

        if (isClick && (row?.type === 'task' || row?.type === 'subtask') && currentState.type === 'move') {
          if (isLinkMode) {
            // Link mode: handle linking
            handleLinkModeClick(row.id);
          }
          // バーのクリックではモーダルを開かない（サイドバーのみで開く）
        }
      }

      cleanup();
    };

    const cleanup = () => {
      if (handleMouseMoveRef.current) {
        document.removeEventListener('mousemove', handleMouseMoveRef.current);
        handleMouseMoveRef.current = null;
      }
      if (handleMouseUpRef.current) {
        document.removeEventListener('mouseup', handleMouseUpRef.current);
        handleMouseUpRef.current = null;
      }
      setDragState(null);
      dragStateRef.current = null;
      setDropTargetMilestone(null);  // Phase 6: Clear drop target
    };

    // イベントリスナーを登録
    handleMouseMoveRef.current = handleMouseMove;
    handleMouseUpRef.current = handleMouseUp;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [viewMode, dateRange, rows, onTaskUpdate, onPhaseUpdate, onMilestoneUpdate, onTaskClick, onBatchTaskUpdate, findAllDependentTasks, tasks, phases, milestones, parseDate, isLinkMode, handleLinkModeClick, pushToHistory]);

  // コンポーネントのアンマウント時にクリーンアップ
  useEffect(() => {
    return () => {
      if (handleMouseMoveRef.current) {
        document.removeEventListener('mousemove', handleMouseMoveRef.current);
      }
      if (handleMouseUpRef.current) {
        document.removeEventListener('mouseup', handleMouseUpRef.current);
      }
    };
  }, []);

  // Close delete confirmation with Escape key
  useEffect(() => {
    if (!pendingDeleteArrow) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPendingDeleteArrow(null);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [pendingDeleteArrow]);

  // Close task delete confirmation with Escape key
  useEffect(() => {
    if (!pendingDeleteTask) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPendingDeleteTask(null);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [pendingDeleteTask]);

  // バーのクラス名
  const getBarClass = (row: GanttRow, bar: GanttBar): string => {
    const classes = ['pgantt-bar'];
    if (row.type === 'phase') classes.push('phase');
    if (row.type === 'milestone') classes.push('milestone');
    if (row.type === 'task') classes.push('task');
    if (row.type === 'subtask') classes.push('subtask');
    if (row.type === 'buffer') classes.push('buffer');
    if (bar.status === 'DONE') classes.push('done');
    if (bar.status === 'IN_PROGRESS') classes.push('in-progress');
    if (row.bufferStatus) classes.push(row.bufferStatus);
    if (row.bufferType) classes.push(row.bufferType);
    // Phase 5: Link mode source highlighting
    if (isLinkMode && (row.type === 'task' || row.type === 'subtask') && linkSourceTask === row.id) {
      classes.push('link-source');
    }
    // Phase 6: Milestone drop target highlighting
    if (row.type === 'milestone' && dropTargetMilestone === row.id) {
      classes.push('drop-target');
    }
    // Phase 6: Milestone-linked task styling
    if (row.linkedMilestoneId) {
      classes.push('milestone-linked');
    }
    // Undated item styling
    if (row.hasNoDate) {
      classes.push('no-date');
    }
    // Deadline status styling
    const dlStatus = deadlineStatusMap.get(row.id);
    if (dlStatus === 'overdue') classes.push('deadline-overdue');
    if (dlStatus === 'approaching') classes.push('deadline-approaching');
    return classes.join(' ');
  };

  const totalPhases = phases.length + (tasks.some(t => !t.phase_id) ? 1 : 0);

  if (rows.length === 0) {
    return (
      <div className="pgantt-empty">
        <p>表示するフェーズがありません</p>
        <p className="text-sm">フェーズを作成してタスクを割り当ててください</p>
      </div>
    );
  }

  return (
    <>
    <div
      ref={containerRef}
      className={`pgantt-container ${className || ''} ${isLinkMode ? 'link-mode' : ''} ${linkSourceTask ? 'has-source' : ''}`}
      style={{ '--day-width': `${dayWidth}px` } as CSSProperties}
    >
      {/* コントロール */}
      <div className="pgantt-controls">
        <div className="pgantt-controls-left">
          <label className="pgantt-checkbox">
            <input
              type="checkbox"
              checked={showTaskList}
              onChange={(e) => setShowTaskList(e.target.checked)}
            />
            <span>リスト</span>
          </label>
          <div className="pgantt-expand-buttons">
            <button onClick={expandAll} title="全て展開">
              <FaExpand size={10} />
              <span>展開</span>
            </button>
            <button onClick={collapseAll} title="全て折りたたみ">
              <FaCompress size={10} />
              <span>折畳</span>
            </button>
            <span className="pgantt-expand-count">{expandedPhases.size}/{totalPhases}</span>
          </div>
          {/* Phase 3: Sort button (one-time action) */}
          <button
            className="pgantt-sort-btn"
            onClick={sortTasksByDueDate}
            title="期限順にソート（マイルストーン内で期限順）"
          >
            <FaSort size={10} />
            <span>ソート</span>
          </button>
          {onPhaseCreate && (
            <button
              className="pgantt-sort-btn"
              onClick={() => setIsAddingPhase(true)}
              title="フェーズを追加"
            >
              <FaPlus size={10} />
              <span>フェーズ</span>
            </button>
          )}
          {/* Phase 5: Link mode button */}
          {onDependencyUpdate && (
            <div className="pgantt-link-mode-container">
              <button
                className={`pgantt-link-btn ${isLinkMode ? 'active' : ''}`}
                onClick={() => {
                  setIsLinkMode(prev => !prev);
                  setLinkSourceTask(null);
                  setPendingDeleteArrow(null);
                }}
                title="依存関係リンクモード"
              >
                <FaLink size={10} />
                <span>リンク</span>
              </button>
              {isLinkMode && (
                <span className="pgantt-link-hint">
                  {linkSourceTask
                    ? '② 依存先（後に実行）を選択'
                    : '① 先に完了するタスクを選択'}
                </span>
              )}
            </div>
          )}
          {/* Keyboard shortcuts hint */}
          <div className="pgantt-shortcuts-hint">
            <span className="pgantt-shortcut-badge">?</span>
            <div className="pgantt-shortcuts-tooltip">
              <div className="pgantt-shortcut-item"><kbd>Ctrl</kbd>+<kbd>Z</kbd> 元に戻す</div>
              <div className="pgantt-shortcut-item"><kbd>Ctrl</kbd>+<kbd>Y</kbd> やり直し</div>
              <div className="pgantt-shortcut-item"><kbd>Ctrl</kbd>+ドラッグ 依存タスクも一緒に移動</div>
              <div className="pgantt-shortcut-item">中央ボタン+ドラッグ 横スクロール</div>
            </div>
          </div>
        </div>
        <div className="pgantt-controls-right">
          {projectId && (
            <button
              className={`pgantt-lightning-btn ${showLightningLine ? 'active' : ''}`}
              onClick={() => setShowLightningLine(prev => !prev)}
              title="イナズマ線の表示切り替え"
            >
              <span>イナズマ線</span>
            </button>
          )}
          {showLightningLine && lightningError && (
            <span className="pgantt-lightning-error">{lightningError}</span>
          )}
          <button
            className="pgantt-today-btn"
            onClick={scrollToToday}
            title="今日の位置にスクロール"
          >
            <FaCalendarDay size={10} />
            <span>今日</span>
          </button>
          <div className="pgantt-view-modes">
            <button className={viewMode === 'day' ? 'active' : ''} onClick={() => setViewMode('day')}>日</button>
            <button className={viewMode === 'week' ? 'active' : ''} onClick={() => setViewMode('week')}>週</button>
            <button className={viewMode === 'month' ? 'active' : ''} onClick={() => setViewMode('month')}>月</button>
          </div>
        </div>
      </div>

      {/* メインエリア */}
      <div className="pgantt-main">
        {/* 左サイドバー（タスクリスト） */}
        {showTaskList && (
          <div className="pgantt-sidebar" style={{ width: sidebarWidth, minWidth: sidebarWidth }}>
            <div className="pgantt-sidebar-header">タスク</div>
            <div className="pgantt-sidebar-body">
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragOver={handleSidebarDragOver}
                onDragEnd={handleSidebarDragEnd}
              >
                <SortableContext
                  items={rows.filter(r => r.type === 'task' || r.type === 'subtask' || r.type === 'milestone').map(r => r.id)}
                  strategy={verticalListSortingStrategy}
                >
                  {rows.map((row) => (
                    row.type === 'milestone' ? (
                      <DroppableMilestoneRow
                        key={`sidebar-milestone-${row.id}`}
                        row={row}
                        isDropTarget={dropTargetMilestone === row.id}
                        onMilestoneClick={onMilestoneClick}
                        onRequestDeleteMilestone={onDeleteMilestone ? (id, title) => setPendingDeleteMilestone({ id, title }) : undefined}
                        onGenerateMilestoneTasks={onGenerateMilestoneTasks}
                      />
                    ) : (
                      <SortableSidebarRow
                        key={`sidebar-${row.type}-${row.id}`}
                        row={row}
                        isLinkMode={isLinkMode}
                        linkSourceTask={linkSourceTask}
                        deadlineStatus={deadlineStatusMap.get(row.id) ?? null}
                        onTogglePhase={togglePhase}
                        onToggleTask={toggleTask}
                        onLinkModeClick={handleLinkModeClick}
                        onTaskClick={onTaskClick}
                        onTaskCreate={onTaskCreate}
                        onSubtaskCreate={onSubtaskCreate}
                        onGenerateSubtasks={onGenerateSubtasks}
                        onRequestDeleteTask={onDeleteTask ? (id, title) => setPendingDeleteTask({ id, title }) : undefined}
                        onMilestoneUnlink={onMilestoneLink ? (taskId) => onMilestoneLink(taskId, null) : undefined}
                        isDragDisabled={false}
                        isDropTarget={false}
                      />
                    )
                  ))}
                </SortableContext>
              </DndContext>
              {isAddingPhase && onPhaseCreate && (
                <div className="pgantt-add-phase-form">
                  <input
                    className="pgantt-add-phase-input"
                    type="text"
                    value={newPhaseName}
                    onChange={(e) => setNewPhaseName(e.target.value)}
                    placeholder="フェーズ名を入力..."
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newPhaseName.trim()) {
                        onPhaseCreate(newPhaseName.trim());
                        setNewPhaseName('');
                        setIsAddingPhase(false);
                      }
                      if (e.key === 'Escape') {
                        setNewPhaseName('');
                        setIsAddingPhase(false);
                      }
                    }}
                  />
                  <button
                    className="pgantt-add-phase-submit"
                    onClick={() => {
                      if (newPhaseName.trim()) {
                        onPhaseCreate(newPhaseName.trim());
                        setNewPhaseName('');
                        setIsAddingPhase(false);
                      }
                    }}
                    disabled={!newPhaseName.trim()}
                  >
                    <FaPlus size={10} />
                  </button>
                  <button
                    className="pgantt-add-phase-cancel"
                    onClick={() => { setNewPhaseName(''); setIsAddingPhase(false); }}
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>
            <div
              className="pgantt-sidebar-resize-handle"
              onMouseDown={handleSidebarResizeStart}
            />
          </div>
        )}

        {/* タイムライン */}
        <div
          className="pgantt-timeline"
          ref={scrollRef}
          onMouseDown={handleTimelineMouseDown}
        >
          {/* 月ヘッダー */}
          <div className="pgantt-month-header" style={{ width: `${dateRange.length * dayWidth}px` }}>
            {monthHeaders.map((month, idx) => (
              <div
                key={`month-${idx}`}
                className="pgantt-month-cell"
                style={{
                  left: `${month.startIndex * dayWidth}px`,
                  width: `${month.span * dayWidth}px`,
                }}
              >
                {month.label}
              </div>
            ))}
          </div>

          {/* 日付ヘッダー */}
          <div className="pgantt-day-header" style={{ width: `${dateRange.length * dayWidth}px` }}>
            {dateRange.map((date, index) => {
              const showLabel = viewMode === 'day' ||
                (viewMode === 'week' && date.weekday === 1) ||
                (viewMode === 'month' && date.day === 1);

              return (
                <div
                  key={`day-${index}`}
                  className={`pgantt-day-cell ${isWeekend(date) ? 'weekend' : ''} ${isToday(date, today) ? 'today' : ''}`}
                  style={{ width: `${dayWidth}px` }}
                >
                  {showLabel && viewMode === 'day' && (
                    <>
                      <span className="pgantt-day-num">{formatDayLabel(date)}</span>
                      <span className="pgantt-day-weekday">{formatWeekday(date)}</span>
                    </>
                  )}
                  {showLabel && viewMode === 'week' && (
                    <span className="pgantt-day-num">{formatDayLabel(date)}</span>
                  )}
                </div>
              );
            })}
          </div>

          {/* 行エリア */}
          <div className="pgantt-rows" style={{ width: `${dateRange.length * dayWidth}px` }}>
            {/* グリッド背景 */}
            <div className="pgantt-grid">
              {dateRange.map((date, index) => (
                <div
                  key={`grid-${index}`}
                  className={`pgantt-grid-cell ${isWeekend(date) ? 'weekend' : ''} ${isToday(date, today) ? 'today' : ''}`}
                  style={{ left: `${index * dayWidth}px`, width: `${dayWidth}px` }}
                />
              ))}
            </div>

            {/* 依存関係の矢印 */}
            <svg
              className="pgantt-arrows"
              style={{ width: `${dateRange.length * dayWidth}px`, height: `${rows.length * 44}px` }}
            >
              <defs>
                <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                  <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
                </marker>
                <marker id="arrowhead-danger" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                  <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
                </marker>
              </defs>
              {showLightningLine && lightningPolylinePoints && (
                <polyline
                  points={lightningPolylinePoints}
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  className="pgantt-lightning-line"
                />
              )}
              {dependencyArrows.map((arrow, index) => {
                const rowHeight = 44;

                // Check if source or target is being dragged/previewed
                let fromIndex = arrow.fromIndex;
                let toIndex = arrow.toIndex;
                let isAnimating = false;

                // If source task (fromId) is the main dragged task
                if (dragState?.rowId === arrow.fromId) {
                  fromIndex = dragState.previewEnd; // Arrow starts from end of bar
                  isAnimating = true;
                }
                // If source task is a dependent being previewed
                const fromPreview = dragState?.dependentPreviews?.get(arrow.fromId);
                if (fromPreview) {
                  fromIndex = fromPreview.previewEnd;
                  isAnimating = true;
                }

                // If target task (toId) is the main dragged task
                if (dragState?.rowId === arrow.toId) {
                  toIndex = dragState.previewStart; // Arrow ends at start of bar
                  isAnimating = true;
                }
                // If target task is a dependent being previewed
                const toPreview = dragState?.dependentPreviews?.get(arrow.toId);
                if (toPreview) {
                  toIndex = toPreview.previewStart;
                  isAnimating = true;
                }

                const x1 = (fromIndex + 1) * dayWidth;
                const y1 = arrow.fromRow * rowHeight + rowHeight / 2;
                const x2 = toIndex * dayWidth;
                const y2 = arrow.toRow * rowHeight + rowHeight / 2;
                const midX = (x1 + x2) / 2;

                const pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;

                // Handle arrow click to remove dependency (only in link mode)
                const handleArrowClick = (e: React.MouseEvent) => {
                  e.stopPropagation();
                  if (!onDependencyUpdate || !isLinkMode) return;

                  // Show modern confirmation popup
                  setPendingDeleteArrow({
                    fromId: arrow.fromId,
                    toId: arrow.toId,
                    x: (x1 + x2) / 2,
                    y: (y1 + y2) / 2,
                  });
                };

                const isClickable = onDependencyUpdate && isLinkMode;

                return (
                  <path
                    key={`arrow-${index}`}
                    d={pathD}
                    className={`pgantt-arrow-path${isAnimating ? ' animating' : ''}${isClickable ? ' clickable' : ''}`}
                    markerEnd="url(#arrowhead)"
                    onClick={isClickable ? handleArrowClick : undefined}
                  />
                );
              })}
            </svg>

            {/* バー */}
            {rows.map((row, rowIndex) => (
              <div
                key={`row-${row.type}-${row.id}`}
                className={`pgantt-bar-row ${row.type}${row.linkedMilestoneDateIndex !== undefined ? ' has-milestone-marker' : ''}`}
                style={{ top: `${rowIndex * 44}px` }}
              >
                {/* Milestone deadline marker for linked tasks - faded diamond */}
                {row.linkedMilestoneDateIndex !== undefined && row.bar && (
                  <span
                    className="pgantt-milestone-marker"
                    style={{ left: `${row.linkedMilestoneDateIndex * dayWidth + dayWidth / 2}px` }}
                    title="マイルストーン期限"
                  >
                    ◆
                  </span>
                )}
                {row.bar && row.bar.startIndex >= 0 && (() => {
                  // ドラッグ中の行はプレビュー位置を使用
                  const isDragging = dragState?.rowId === row.id;
                  // Check if this is a dependent task being previewed
                  const dependentPreview = dragState?.dependentPreviews?.get(row.id);
                  const isDependentDragging = !!dependentPreview;

                  let barStart = row.bar.startIndex;
                  let barEnd = row.bar.endIndex;
                  if (isDragging) {
                    barStart = dragState.previewStart;
                    barEnd = dragState.previewEnd;
                  } else if (isDependentDragging) {
                    barStart = dependentPreview.previewStart;
                    barEnd = dependentPreview.previewEnd;
                  }
                  const startDate = dateRange[barStart];
                  const endDate = dateRange[barEnd];

                  return (
                    <div
                      className={`${getBarClass(row, row.bar)}${isDragging ? ' dragging' : ''}${isDependentDragging ? ' dependent-dragging' : ''}`}
                      style={{
                        left: `${barStart * dayWidth + 2}px`,
                        width: `${Math.max((barEnd - barStart + 1) * dayWidth - 4, 8)}px`,
                        '--progress': `${row.bar.progress}%`,
                        '--buffer-color': row.bufferStatus ? getBufferStatusColor(row.bufferStatus) : undefined,
                      } as CSSProperties}
                      onMouseDown={(e) => {
                        if (row.type === 'task' || row.type === 'subtask' || row.type === 'phase' || row.type === 'milestone') {
                          handleDragStart(e, row.id, 'move', row.bar!);
                        }
                      }}
                      title={`${row.title}${row.bar.progress > 0 ? ` (${Math.round(row.bar.progress)}%)` : ''}`}
                    >
                      {row.type === 'milestone' && <span className="pgantt-bar-milestone">◆</span>}
                      {row.bar.progress > 0 && row.bar.progress < 100 && row.type !== 'milestone' && (
                        <div className="pgantt-bar-progress" />
                      )}
                      {(row.type === 'task' || row.type === 'subtask' || row.type === 'phase') && !row.hasNoDate && (
                        <>
                          <div
                            className="pgantt-resize-handle start"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              handleDragStart(e, row.id, 'resize-start', row.bar!);
                            }}
                          />
                          <div
                            className="pgantt-resize-handle end"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              handleDragStart(e, row.id, 'resize-end', row.bar!);
                            }}
                          />
                        </>
                      )}
                      {/* ドラッグ中の日付プレビュー */}
                      {isDragging && startDate && endDate && (
                        <div className="pgantt-drag-preview">
                          <span className="pgantt-drag-date start">
                            {startDate.toFormat('M/d')}
                          </span>
                          <span className="pgantt-drag-date end">
                            {endDate.toFormat('M/d')}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>

    {/* 依存関係削除確認モーダル */}
    {pendingDeleteArrow && (
      <div className="pgantt-modal-overlay" onClick={() => setPendingDeleteArrow(null)}>
        <div className="pgantt-modal" onClick={(e) => e.stopPropagation()}>
          <p>この依存関係を削除しますか？</p>
          <div className="pgantt-modal-buttons">
            <button
              className="cancel"
              onClick={() => setPendingDeleteArrow(null)}
            >
              キャンセル
            </button>
            <button
              className="delete"
              onClick={() => {
                if (onDependencyUpdate) {
                  const targetTask = tasks.find(t => t.id === pendingDeleteArrow.toId);
                  if (targetTask) {
                    const newDependencies = (targetTask.dependency_ids || []).filter(
                      id => id !== pendingDeleteArrow.fromId
                    );
                    onDependencyUpdate(pendingDeleteArrow.toId, newDependencies);
                  }
                }
                setPendingDeleteArrow(null);
              }}
            >
              削除
            </button>
          </div>
        </div>
      </div>
    )}

    {/* タスク削除確認モーダル */}
    {pendingDeleteTask && (
      <div className="pgantt-modal-overlay" onClick={() => setPendingDeleteTask(null)}>
        <div className="pgantt-modal pgantt-modal-delete-task" onClick={(e) => e.stopPropagation()}>
          <div className="pgantt-modal-icon">
            <FaTrash />
          </div>
          <p className="pgantt-modal-title">タスクを削除</p>
          <p className="pgantt-modal-message">「{pendingDeleteTask.title}」を削除しますか？</p>
          <p className="pgantt-modal-warning">この操作は取り消せません</p>
          <div className="pgantt-modal-buttons">
            <button
              className="cancel"
              onClick={() => setPendingDeleteTask(null)}
            >
              キャンセル
            </button>
            <button
              className="delete"
              onClick={() => {
                if (onDeleteTask) {
                  onDeleteTask(pendingDeleteTask.id);
                }
                setPendingDeleteTask(null);
              }}
            >
              削除する
            </button>
          </div>
        </div>
      </div>
    )}

    {/* Milestone delete confirmation modal */}
    {pendingDeleteMilestone && (
      <div className="pgantt-modal-overlay" onClick={() => setPendingDeleteMilestone(null)}>
        <div className="pgantt-modal" onClick={(e) => e.stopPropagation()}>
          <div className="pgantt-modal-header">
            <h3>マイルストーンの削除</h3>
          </div>
          <p className="pgantt-modal-message">「{pendingDeleteMilestone.title}」を削除しますか？</p>
          <p className="pgantt-modal-warning">紐づいているタスクはマイルストーンから外れます。</p>
          <div className="pgantt-modal-actions">
            <button
              className="cancel"
              onClick={() => setPendingDeleteMilestone(null)}
            >
              キャンセル
            </button>
            <button
              className="delete"
              onClick={() => {
                if (onDeleteMilestone) {
                  onDeleteMilestone(pendingDeleteMilestone.id);
                }
                setPendingDeleteMilestone(null);
              }}
            >
              削除する
            </button>
          </div>
        </div>
      </div>
    )}
  </>
  );
};
