import { useCallback, useEffect, useMemo, useState } from 'react';
import { FaCheckSquare, FaPlus, FaRegSquare } from 'react-icons/fa';
import { phasesApi } from '../../api/phases';
import { tasksApi } from '../../api/tasks';
import type {
  PhaseWithTaskCount,
  Task,
  TaskAssignment,
  TaskStatus,
} from '../../api/types';
import { ViewModeToggle } from '../common/ViewModeToggle';
import { getStoredViewMode, setStoredViewMode, type ViewMode } from '../common/viewModeStorage';
import { KanbanBoard } from '../tasks/KanbanBoard';
import { PhaseExplorerSidebar } from './PhaseExplorerSidebar';
import './ProjectTasksView.css';

interface ProjectTasksViewProps {
  projectId: string;
  tasks: Task[];
  onUpdateTask: (id: string, status: TaskStatus) => void;
  onTaskClick: (task: Task) => void;
  onDeleteTask?: (id: string) => void;
  assigneeByTaskId: Record<string, string>;
  assignedMemberIdsByTaskId: Record<string, string[]>;
  memberOptions: { id: string; label: string }[];
  onAssignMultiple: (taskId: string, memberUserIds: string[]) => Promise<void>;
  onRefreshTasks?: () => void;
  onCreateTask?: (phaseId: string | null) => void;
  onDeleteGeneratedTasks?: (recurringTaskId: string) => void;
  onGenerateTasks?: (recurringTaskId: string) => void;
  // Multi-member completion
  taskAssignments?: TaskAssignment[];
  currentUserId?: string;
  onCheckCompletion?: (taskId: string) => void;
}

export function ProjectTasksView({
  projectId,
  tasks,
  onUpdateTask,
  onTaskClick,
  onDeleteTask,
  assigneeByTaskId,
  assignedMemberIdsByTaskId,
  memberOptions,
  onAssignMultiple,
  onRefreshTasks,
  onCreateTask,
  onDeleteGeneratedTasks,
  onGenerateTasks,
  taskAssignments,
  currentUserId,
  onCheckCompletion,
}: ProjectTasksViewProps) {
  const [phases, setPhases] = useState<PhaseWithTaskCount[]>([]);
  const [isPhasesLoading, setIsPhasesLoading] = useState(false);
  const [sortBy, setSortBy] = useState<'default' | 'dueDate'>('dueDate');
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    setStoredViewMode(mode);
  };

  // Phase explorer state
  const [selectedPhaseId, setSelectedPhaseId] = useState<string | null>(null); // null = unassigned
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());
  const [isDraggingTasks, setIsDraggingTasks] = useState(false);
  const [dragOverPhaseId, setDragOverPhaseId] = useState<string | null>(null);
  const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null); // For single task drag

  const fetchPhases = useCallback(async () => {
    setIsPhasesLoading(true);
    try {
      const data = await phasesApi.listByProject(projectId);
      setPhases(data);
      return data;
    } catch (error) {
      console.error('Failed to fetch phases:', error);
      return [];
    } finally {
      setIsPhasesLoading(false);
    }
  }, [projectId]);

  // On initial load, select the current (ACTIVE) phase if available
  useEffect(() => {
    const initPhases = async () => {
      const phasesData = await fetchPhases();
      // Find the first ACTIVE phase (sorted by order_in_project)
      const activePhases = phasesData
        .filter(p => p.status === 'ACTIVE')
        .sort((a, b) => a.order_in_project - b.order_in_project);
      if (activePhases.length > 0) {
        setSelectedPhaseId(activePhases[0].id);
      }
    };
    initPhases();
  }, [fetchPhases]);

  // Filter tasks by selected phase
  const filteredTasks = useMemo(() => {
    if (selectedPhaseId === null) {
      // Unassigned tasks
      return tasks.filter(t => !t.phase_id);
    }
    return tasks.filter(t => t.phase_id === selectedPhaseId);
  }, [tasks, selectedPhaseId]);

  // Selection handlers
  const handleSelectTask = (taskId: string) => {
    setSelectedTaskIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  const handleToggleSelectionMode = () => {
    if (selectionMode) {
      // Exiting selection mode - clear selections
      setSelectedTaskIds(new Set());
    }
    setSelectionMode(!selectionMode);
  };

  const handleDragSelectedStart = () => {
    if (selectedTaskIds.size > 0) {
      setIsDraggingTasks(true);
    }
  };

  const handleMoveTasksToPhase = async (targetPhaseId: string | null) => {
    if (selectedTaskIds.size === 0) return;

    try {
      // Move all selected tasks to target phase
      await Promise.all(
        Array.from(selectedTaskIds).map(taskId =>
          tasksApi.update(taskId, { phase_id: targetPhaseId ?? undefined })
        )
      );

      // Refresh data
      onRefreshTasks?.();
      await fetchPhases();

      // Clear selection
      setSelectedTaskIds(new Set());
      setIsDraggingTasks(false);
    } catch (error) {
      console.error('Failed to move tasks:', error);
      alert('タスクの移動に失敗しました。');
    }
  };

  // Single task drag to phase
  const handleMoveSingleTaskToPhase = async (taskId: string, targetPhaseId: string | null) => {
    try {
      await tasksApi.update(taskId, { phase_id: targetPhaseId ?? undefined });

      // Refresh data
      onRefreshTasks?.();
      await fetchPhases();

      // Clear dragging state
      setDraggingTaskId(null);
    } catch (error) {
      console.error('Failed to move task:', error);
      alert('タスクの移動に失敗しました。');
    }
  };

  const handleSingleDragStart = (taskId: string) => {
    setDraggingTaskId(taskId);
  };

  const handleDragOverPhase = (phaseId: string | null) => {
    setDragOverPhaseId(phaseId);
  };

  // Clear dragging state when drag ends
  useEffect(() => {
    const handleDragEnd = () => {
      setIsDraggingTasks(false);
      setDragOverPhaseId(null);
      setDraggingTaskId(null);
    };

    window.addEventListener('dragend', handleDragEnd);
    return () => window.removeEventListener('dragend', handleDragEnd);
  }, []);

  return (
    <div className="project-tasks-view-container">
      {/* Left Sidebar - Phase Explorer */}
      <PhaseExplorerSidebar
        phases={phases}
        tasks={tasks}
        selectedPhaseId={selectedPhaseId}
        onSelectPhase={setSelectedPhaseId}
        selectedTaskIds={selectedTaskIds}
        onMoveTasksToPhase={handleMoveTasksToPhase}
        isDraggingTasks={isDraggingTasks}
        onDragOverPhase={handleDragOverPhase}
        dragOverPhaseId={dragOverPhaseId}
        draggingTaskId={draggingTaskId}
        onMoveSingleTaskToPhase={handleMoveSingleTaskToPhase}
      />

      {/* Main Content - Kanban Board */}
      <div className="project-tasks-main">
        {/* Toolbar */}
        <div className="project-tasks-toolbar">
          <div className="toolbar-left">
            {onCreateTask && (
              <button
                className="create-task-btn"
                onClick={() => onCreateTask(selectedPhaseId)}
                title="タスクを追加"
              >
                <FaPlus />
                <span>タスク追加</span>
              </button>
            )}
            <button
              className={`selection-mode-btn ${selectionMode ? 'active' : ''}`}
              onClick={handleToggleSelectionMode}
              title={selectionMode ? '選択モードを終了' : '選択モードを開始'}
            >
              {selectionMode ? <FaCheckSquare /> : <FaRegSquare />}
              <span>選択モード</span>
            </button>
            {selectionMode && selectedTaskIds.size > 0 && (
              <span className="selection-count-badge">
                {selectedTaskIds.size}件選択中
              </span>
            )}
          </div>
          <div className="toolbar-right">
            <ViewModeToggle value={viewMode} onChange={handleViewModeChange} />
            <select
              className="sort-select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'default' | 'dueDate')}
            >
              <option value="default">デフォルト順</option>
              <option value="dueDate">期限が近い順</option>
            </select>
          </div>
        </div>

        {/* Loading state */}
        {isPhasesLoading ? (
          <div className="loading-message">読み込み中...</div>
        ) : (
          <div className="kanban-wrapper">
            <KanbanBoard
              tasks={filteredTasks}
              onUpdateTask={onUpdateTask}
              onTaskClick={onTaskClick}
              onDeleteTask={onDeleteTask}
              assigneeByTaskId={assigneeByTaskId}
              assignedMemberIdsByTaskId={assignedMemberIdsByTaskId}
              memberOptions={memberOptions}
              onAssignMultiple={onAssignMultiple}
              sortBy={sortBy}
              selectionMode={selectionMode}
              selectedTaskIds={selectedTaskIds}
              onSelectTask={handleSelectTask}
              onDragSelectedStart={handleDragSelectedStart}
              onSingleDragStart={handleSingleDragStart}
              compact={viewMode === 'compact'}
              onDeleteGeneratedTasks={onDeleteGeneratedTasks}
              onGenerateTasks={onGenerateTasks}
              taskAssignments={taskAssignments}
              currentUserId={currentUserId}
              onCheckCompletion={onCheckCompletion}
            />
          </div>
        )}
      </div>
    </div>
  );
}
