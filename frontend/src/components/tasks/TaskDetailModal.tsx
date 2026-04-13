import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import {
  FaArrowLeft,
  FaCodeBranch,
  FaEdit,
  FaLayerGroup,
  FaLock,
  FaLockOpen,
  FaMagic,
  FaProjectDiagram,
  FaTimes,
  FaTrash,
  FaUser,
} from 'react-icons/fa';
import {
  HiOutlineBookOpen,
  HiOutlineCalendar,
  HiOutlineCheckCircle,
  HiOutlineClock,
  HiOutlineFire,
  HiOutlineLightningBolt,
  HiOutlineLocationMarker,
  HiOutlinePencilAlt,
  HiOutlineUserGroup
} from 'react-icons/hi';
import {
  HiFire,
} from 'react-icons/hi2';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import { phasesApi } from '../../api/phases';
import { projectsApi, getProject } from '../../api/projects';
import { tasksApi } from '../../api/tasks';
import type { Phase, Project, Task, TaskAssignment } from '../../api/types';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate } from '../../utils/dateTime';
import type { DraftCardData } from '../chat/DraftCard';
import type { TaskUpdate } from '../../api/types';
import { AgendaList } from '../agenda';
import { AssigneeSelect } from '../common/AssigneeSelect';
import { EditableDateTime } from '../common/EditableDateTime';
import { EditableDependencies } from '../common/EditableDependencies';
import { EditableSection } from '../common/EditableSection';
import { EditableSegment } from '../common/EditableSegment';
import { EditableSelect } from '../common/EditableSelect';
import { StepNumber } from '../common/StepNumber';
import { CompletionChecklist } from './CompletionChecklist';
import './TaskDetailModal.css';

interface MemberOption {
  id: string;
  label: string;
}

interface TaskDetailModalProps {
  task: Task;
  subtasks?: Task[];
  allTasks?: Task[];
  initialSubtask?: Task | null;
  projectName?: string;
  phaseName?: string;
  onClose: () => void;
  onEdit?: (task: Task) => void;
  onDelete?: (task: Task) => void;
  onProgressChange?: (taskId: string, progress: number) => void;
  onTaskCheck?: (taskId: string) => void;
  onActionItemsCreated?: () => void;
  onStatusChange?: (taskId: string, status: string) => void;
  onCreateSubtask?: (parentTaskId: string, title?: string, openModal?: boolean) => void;
  onUpdateTask?: (taskId: string, updates: TaskUpdate) => Promise<void>;
  // Assignee props (optional for backward compatibility)
  memberOptions?: MemberOption[];
  taskAssignments?: TaskAssignment[];
  onAssigneeChange?: (taskId: string, memberIds: string[]) => void;
  // Multi-member completion
  currentUserId?: string;
  onCheckCompletion?: (taskId: string) => void;
}

function extractGuide(description?: string | null, guide?: string | null): { mainDescription: string; guide: string } {
  const normalizedGuide = guide?.trim() || '';
  if (normalizedGuide) {
    return { mainDescription: description?.trim() || '', guide: normalizedGuide };
  }
  if (!description) return { mainDescription: '', guide: '' };

  const guideSeparator = '---\n\n## 進め方ガイド';
  const guideStartOnly = '## 進め方ガイド';

  const separatorIndex = description.indexOf(guideSeparator);
  if (separatorIndex !== -1) {
    return {
      mainDescription: description.substring(0, separatorIndex).trim(),
      guide: description.substring(separatorIndex + guideSeparator.length).trim(),
    };
  }

  if (description.startsWith(guideStartOnly)) {
    return {
      mainDescription: '',
      guide: description.substring(guideStartOnly.length).trim(),
    };
  }

  return { mainDescription: description, guide: '' };
}

export function TaskDetailModal({
  task,
  subtasks = [],
  allTasks = [],
  initialSubtask = null,
  projectName,
  phaseName,
  onClose,
  onEdit,
  onDelete,
  onProgressChange,
  onTaskCheck,
  onActionItemsCreated: _onActionItemsCreated,
  onStatusChange,
  onCreateSubtask,
  onUpdateTask,
  memberOptions = [],
  taskAssignments = [],
  onAssigneeChange,
  currentUserId,
  onCheckCompletion,
}: TaskDetailModalProps) {
  const timezone = useTimezone();
  const { data: currentUser } = useCurrentUser();
  const queryClient = useQueryClient();
  const [selectedSubtask, setSelectedSubtask] = useState<Task | null>(initialSubtask);
  const [localProgress, setLocalProgress] = useState<number>(task.progress ?? 0);
  const [localStatus, setLocalStatus] = useState<string>(task.status);
  const [localSubtasks, setLocalSubtasks] = useState<Task[]>(subtasks);
  const [localSubtaskProgress, setLocalSubtaskProgress] = useState<number>(0);
  const [fetchedProject, setFetchedProject] = useState<Project | null>(null);
  const [fetchedPhase, setFetchedPhase] = useState<Phase | null>(null);

  // Inline subtask creation state
  const [newSubtaskTitle, setNewSubtaskTitle] = useState('');
  const [isCreatingSubtask, setIsCreatingSubtask] = useState(false);

  // Local task state for optimistic updates
  const [localTask, setLocalTask] = useState<Task>(task);

  // Sync local task with prop changes
  useEffect(() => {
    setLocalTask(task);
  }, [task]);

  // Sync subtask progress when selected subtask changes
  useEffect(() => {
    setLocalSubtaskProgress(selectedSubtask?.progress ?? 0);
  }, [selectedSubtask]);

  // Handler for inline field updates
  const handleFieldUpdate = async (field: keyof TaskUpdate, value: unknown) => {
    if (!onUpdateTask) return;
    // Optimistic update
    setLocalTask(prev => ({ ...prev, [field]: value }));
    try {
      await onUpdateTask(task.id, { [field]: value } as TaskUpdate);
    } catch (error) {
      // Revert on error
      setLocalTask(task);
      console.error('Failed to update task:', error);
    }
  };

  const handleDoToday = async () => {
    try {
      await tasksApi.doToday(task.id, { pin: true });
      await tasksApi.recalculateSchedulePlan({
        fromNow: true,
        filterByAssignee: true,
      });
      for (const key of [
        ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['schedule'],
        ['task-detail'], ['task-assignments'], ['project'], ['member-child-tasks'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    } catch {
      alert('今日やるの設定に失敗しました');
    }
  };

  // Handler for subtask inline field updates
  const handleSubtaskFieldUpdate = async (subtaskId: string, field: keyof TaskUpdate, value: unknown) => {
    if (!onUpdateTask) return;
    // Optimistic update for selectedSubtask
    setSelectedSubtask(prev => prev ? { ...prev, [field]: value } : prev);
    // Also update localSubtasks
    setLocalSubtasks(prev => prev.map(st => st.id === subtaskId ? { ...st, [field]: value } : st));
    try {
      await onUpdateTask(subtaskId, { [field]: value } as TaskUpdate);
    } catch (error) {
      // Revert on error
      const original = subtasks.find(st => st.id === subtaskId);
      if (original) {
        setSelectedSubtask(original);
        setLocalSubtasks(subtasks);
      }
      console.error('Failed to update subtask:', error);
    }
  };

  // Fetch project and phase info if not provided via props
  useEffect(() => {
    let isActive = true;
    const fetchProjectAndPhase = async () => {
      // Fetch project if we have project_id but no projectName prop
      if (task.project_id && !projectName) {
        try {
          const proj = await getProject(task.project_id);
          if (isActive && proj) {
            setFetchedProject(proj);
          }
        } catch (err) {
          console.error('Failed to fetch project:', err);
        }
      }
      // Fetch phase if we have phase_id but no phaseName prop
      if (task.phase_id && !phaseName) {
        try {
          const phase = await phasesApi.getById(task.phase_id);
          if (isActive && phase) {
            setFetchedPhase(phase);
          }
        } catch (err) {
          console.error('Failed to fetch phase:', err);
        }
      }
    };
    fetchProjectAndPhase();
    return () => { isActive = false; };
  }, [task.project_id, task.phase_id, projectName, phaseName]);

  // Determine effective project/phase names (props take precedence)
  const effectiveProjectName = projectName || fetchedProject?.name;
  const effectivePhaseName = phaseName || fetchedPhase?.name;

  // Fetch projects list for inline editing
  const { data: projectsList = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.getAll(),
    enabled: !!onUpdateTask, // Only fetch when inline editing is enabled
    staleTime: 5 * 60 * 1000, // 5 minutes cache
  });

  // Fetch phases for selected project
  const { data: phasesList = [] } = useQuery({
    queryKey: ['phases', localTask.project_id],
    queryFn: () => localTask.project_id ? phasesApi.listByProject(localTask.project_id) : Promise.resolve([]),
    enabled: !!onUpdateTask && !!localTask.project_id,
    staleTime: 5 * 60 * 1000,
  });

  // Project options for EditableSelect
  const projectOptions = useMemo(() => {
    return projectsList.map(p => ({
      value: p.id,
      label: p.name,
    }));
  }, [projectsList]);

  // Phase options for EditableSelect
  const phaseOptions = useMemo(() => {
    return phasesList.map(p => ({
      value: p.id,
      label: p.name,
    }));
  }, [phasesList]);

  useEffect(() => {
    setLocalProgress(task.progress ?? 0);
    setLocalStatus(task.status);
  }, [task.id, task.progress, task.status]);

  useEffect(() => {
    setLocalSubtasks(subtasks);
  }, [subtasks]);

  // Check if parent task is completed (subtasks of completed tasks should stay DONE)
  const parentTask = task.parent_id ? allTasks.find(t => t.id === task.parent_id) : null;
  const isParentCompleted = parentTask?.status === 'DONE';

  const sortedSubtasks = useMemo(() => {
    return [...localSubtasks].sort((a, b) => {
      const aOrder = a.order_in_parent ?? Number.POSITIVE_INFINITY;
      const bOrder = b.order_in_parent ?? Number.POSITIVE_INFINITY;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return a.title.localeCompare(b.title);
    });
  }, [localSubtasks]);

  const stepNumberBySubtaskId = useMemo(() => {
    const map = new Map<string, number>();
    sortedSubtasks.forEach((subtask) => {
      if (subtask.order_in_parent != null) {
        map.set(subtask.id, subtask.order_in_parent);
      }
    });
    return map;
  }, [sortedSubtasks]);

  const dependencies = useMemo(() => {
    if (!task.dependency_ids || task.dependency_ids.length === 0) return [];
    return task.dependency_ids
      .map(depId => allTasks.find(t => t.id === depId))
      .filter((t): t is Task => t !== undefined);
  }, [task, allTasks]);

  const effectiveEstimatedMinutes = useMemo(() => {
    if (sortedSubtasks.length > 0) {
      return sortedSubtasks.reduce((sum, subtask) => sum + (subtask.estimated_minutes || 0), 0);
    }
    return task.estimated_minutes || 0;
  }, [task.estimated_minutes, sortedSubtasks]);

  const getPriorityIcon = (level: string) => {
    switch (level) {
      case 'HIGH': return <HiFire className="priority-icon-high" />;
      case 'MEDIUM': return <HiOutlineFire className="priority-icon-medium" />;
      case 'LOW': return <HiOutlineClock className="priority-icon-low" />;
      default: return <HiOutlineFire />;
    }
  };

  const getEnergyIcon = (level: string) => {
    return level === 'HIGH' ? <HiOutlineLightningBolt className="energy-icon-high" /> : <HiOutlineClock className="energy-icon-low" />;
  };

  const resolveCompletedByName = (userId?: string) => {
    if (!userId) return '不明';
    if (currentUser?.id === userId) return '自分';
    const member = memberOptions.find(m => m.id === userId);
    return member?.label ?? '不明';
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      TODO: '未着手',
      IN_PROGRESS: '進行中',
      WAITING: '待機中',
      DONE: '完了',
    };
    return labels[status] || status;
  };

  const formatDateValue = (dateStr?: string) => {
    if (!dateStr) return null;
    return formatDate(dateStr, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }, timezone);
  };

  const formatMeetingTime = (start?: string, end?: string) => {
    if (!start || !end) return null;
    const startLabel = formatDate(start, {
      month: 'numeric',
      day: 'numeric',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }, timezone);
    const endLabel = formatDate(end, {
      hour: '2-digit',
      minute: '2-digit',
    }, timezone);
    return `${startLabel} - ${endLabel}`;
  };

  const selectedGuide = selectedSubtask
    ? extractGuide(selectedSubtask.description, selectedSubtask.guide)
    : null;
  const taskDescription = extractGuide(localTask.description, localTask.guide);
  const selectedSubtaskStepNumber = selectedSubtask ? stepNumberBySubtaskId.get(selectedSubtask.id) : undefined;
  const isMeeting = localTask.is_fixed_time && localTask.start_time && localTask.end_time;
  const meetingTimeLabel = formatMeetingTime(localTask.start_time, localTask.end_time);

  // Helper to check if a subtask is locked (dependencies not complete)
  const isSubtaskLocked = (subtask: Task): boolean => {
    if (!subtask.dependency_ids || subtask.dependency_ids.length === 0) return false;
    return subtask.dependency_ids.some(depId => {
      // First check localSubtasks (for optimistic updates), then allTasks
      const localTask = localSubtasks.find(t => t.id === depId);
      if (localTask) return localTask.status !== 'DONE';
      const task = allTasks.find(t => t.id === depId);
      return task ? task.status !== 'DONE' : false;
    });
  };

  const handleSubtaskCheck = (subtaskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();

    // Find the subtask and check if it's locked
    const subtask = localSubtasks.find(s => s.id === subtaskId);
    if (!subtask) return;

    // Don't allow checking locked subtasks (unless unchecking)
    if (subtask.status !== 'DONE' && isSubtaskLocked(subtask)) {
      console.log('[TaskDetailModal] Subtask is locked, cannot check:', subtaskId);
      return;
    }

    console.log('[TaskDetailModal] Subtask check:', subtaskId);

    // Optimistic update: toggle subtask status in local state
    setLocalSubtasks(prev =>
      prev.map(s => {
        if (s.id === subtaskId) {
          const newStatus = s.status === 'DONE' ? 'TODO' : 'DONE';
          return { ...s, status: newStatus };
        }
        return s;
      })
    );

    // Update selectedSubtask if it matches
    if (selectedSubtask?.id === subtaskId) {
      setSelectedSubtask(prev => {
        if (!prev) return prev;
        const newStatus = prev.status === 'DONE' ? 'TODO' : 'DONE';
        return { ...prev, status: newStatus };
      });
    }

    if (onTaskCheck) {
      onTaskCheck(subtaskId);
    } else {
      console.warn('[TaskDetailModal] onTaskCheck is not provided');
    }
  };

  const handleCreateActionItems = () => {
    if (!task.meeting_notes) return;
    const draftCard: DraftCardData = {
      type: 'actionItem',
      title: 'アクションアイテム生成',
      info: [
        { label: 'タスク', value: task.title },
        { label: 'タスクID', value: task.id },
      ],
      placeholder: '例: 優先度順に並べて',
      promptTemplate: `タスク「${task.title}」(ID: ${task.id}) の会議ノートからアクションアイテムを作成して。

追加の指示があれば以下に記入:
{instruction}`,
    };
    const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
    window.dispatchEvent(event);
    onClose();
  };

  const handleEnrichTask = () => {
    // Build a summary of what's already filled in and what's missing
    const filledFields: string[] = [];
    const emptyFields: string[] = [];

    if (localTask.description) filledFields.push('説明');
    else emptyFields.push('説明');

    if (localTask.purpose) filledFields.push('目的');
    else emptyFields.push('目的（なぜやるか）');

    if (localTask.guide) filledFields.push('進め方ガイド');
    else emptyFields.push('進め方ガイド');

    if (localTask.estimated_minutes) filledFields.push(`見積時間(${localTask.estimated_minutes}分)`);
    else emptyFields.push('見積時間');

    if (localTask.due_date) filledFields.push('期限');
    else emptyFields.push('期限');

    filledFields.push(`重要度: ${localTask.importance}`, `緊急度: ${localTask.urgency}`, `エネルギー: ${localTask.energy_level}`);

    const currentAssignees = taskAssignments
      .filter(a => a.task_id === task.id)
      .map(a => memberOptions.find(m => m.id === a.assignee_id)?.label)
      .filter(Boolean);
    if (currentAssignees.length > 0) filledFields.push(`担当者: ${currentAssignees.join(', ')}`);
    else emptyFields.push('担当者');

    const infoRows = [
      { label: 'タスク', value: localTask.title },
      { label: 'タスクID', value: task.id },
    ];
    if (effectiveProjectName) infoRows.push({ label: 'プロジェクト', value: effectiveProjectName });
    if (effectivePhaseName) infoRows.push({ label: 'フェーズ', value: effectivePhaseName });

    const filledSummary = filledFields.length > 0 ? `\n記入済み: ${filledFields.join(', ')}` : '';
    const emptySummary = emptyFields.length > 0 ? `\n未記入: ${emptyFields.join(', ')}` : '';

    const draftCard: DraftCardData = {
      type: 'enrich',
      title: 'タスクの記入補助',
      info: infoRows,
      placeholder: '例: 説明と目的を重点的に、見積時間は30分くらいで',
      promptTemplate: `タスク「${localTask.title}」(ID: ${task.id}) の内容を肉付けして。

get_taskでタスクの現在情報を取得した上で、未記入のフィールドを中心にupdate_taskで補完して。
担当者が未設定の場合は、プロジェクトメンバーから適切な人を推測してassign_taskで割り当てて。
${filledSummary}${emptySummary}

追加の指示があれば以下に記入:
{instruction}`,
    };
    const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
    window.dispatchEvent(event);
    onClose();
  };

  const handleBreakdownTask = () => {
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
※サブタスク作成時は必ずparent_idに上記IDを指定して
※各サブタスクに description（何をするか・完了条件）と guide（進め方3-7ステップ）も入れて
${task.project_id ? `※親と同じ project_id（${task.project_id}）で作成して` : ''}
※guide は次の型で書いて
## 進め方ガイド
1. ...
2. ...
3. ...
**完了の目安**: ...

追加の指示があれば以下に記入:
{instruction}`,
    };
    const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
    window.dispatchEvent(event);
    onClose();
  };

  return (
    <motion.div
      className="modal-overlay"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        layout
        className={`modal-container ${selectedSubtask ? 'split-view' : ''}`}
        onClick={(e) => e.stopPropagation()}
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 10 }}
        transition={{
          type: "spring",
          damping: 35,
          stiffness: 400,
          mass: 1,
          layout: { duration: 0.45, ease: [0.16, 1, 0.3, 1] }
        }}
      >
        <motion.div layout className="modal-content side-layout-modal">
          <div className="modal-header">
            <div className="title-area">
              {isMeeting && <span className="meeting-tag">MEETING</span>}
              {onUpdateTask ? (
                <EditableSection
                  value={localTask.title}
                  onSave={async (newValue) => handleFieldUpdate('title', newValue)}
                  placeholder="タスク名を入力"
                  className="editable-title"
                />
              ) : (
                <h2>{localTask.title}</h2>
              )}
            </div>
            <div className="modal-header-actions">
              {localTask.status !== 'DONE' && !localTask.is_fixed_time && (
                <button
                  className="do-today-header-btn"
                  onClick={handleDoToday}
                  title="今日やる"
                >
                  <HiOutlineCalendar />
                  <span>今日やる</span>
                </button>
              )}
              <button
                className="enrich-btn"
                onClick={handleEnrichTask}
                title="AIで記入補助"
              >
                <FaMagic />
              </button>
              {/* 編集ボタンはインライン編集が無い場合のみ表示 */}
              {onEdit && !onUpdateTask && (
                <button className="edit-btn" onClick={() => onEdit(task)} title="編集">
                  <FaEdit />
                </button>
              )}
              {onDelete && (
                <button className="delete-btn" onClick={() => onDelete(task)} title="削除">
                  <FaTrash />
                </button>
              )}
              <button className="close-btn" onClick={onClose}>
                <FaTimes />
              </button>
            </div>
          </div>

          <div className="modal-body-wrapper">
            {/* Main Area */}
            <div className="modal-main-area">
              {/* 説明セクション */}
              {(taskDescription.mainDescription || onUpdateTask) && (
                <div className="detail-section">
                  <h3 className="section-label">説明</h3>
                  {onUpdateTask ? (
                    <EditableSection
                      value={localTask.description}
                      onSave={async (newValue) => handleFieldUpdate('description', newValue)}
                      placeholder="説明を入力（Markdown対応）"
                      multiline
                      markdown
                      renderView={(value) => (
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                          {value}
                        </ReactMarkdown>
                      )}
                    />
                  ) : (
                    <div className="description-container">
                      <div className="description-text markdown-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                          {taskDescription.mainDescription}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 進め方ガイドセクション */}
              {(taskDescription.guide || onUpdateTask) && (
                <div className="detail-section">
                  <h3 className="section-label"><HiOutlineBookOpen /> 進め方ガイド</h3>
                  {onUpdateTask ? (
                    <EditableSection
                      value={localTask.guide}
                      onSave={async (newValue) => handleFieldUpdate('guide', newValue)}
                      placeholder="進め方ガイドを入力（Markdown対応）"
                      multiline
                      markdown
                      renderView={(value) => (
                        <div className="task-guide markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {value}
                          </ReactMarkdown>
                        </div>
                      )}
                    />
                  ) : taskDescription.guide ? (
                    <div className="task-guide markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {taskDescription.guide}
                      </ReactMarkdown>
                    </div>
                  ) : null}
                </div>
              )}

              {/* 目的セクション */}
              {(localTask.purpose || onUpdateTask) && (
                <div className="detail-section">
                  <h3 className="section-label">なぜやるか（目的）</h3>
                  {onUpdateTask ? (
                    <EditableSection
                      value={localTask.purpose}
                      onSave={async (newValue) => handleFieldUpdate('purpose', newValue)}
                      placeholder="目的を入力"
                      multiline
                      minRows={2}
                    />
                  ) : (
                    <div className="purpose-container">
                      <p className="purpose-text">{localTask.purpose}</p>
                    </div>
                  )}
                </div>
              )}

              {/* メモセクション */}
              {(localTask.completion_note || onUpdateTask) && (
                <div className="detail-section completion-note-section">
                  <h3 className="section-label">
                    <HiOutlinePencilAlt className="section-icon" /> メモ
                  </h3>
                  {onUpdateTask ? (
                    <EditableSection
                      value={localTask.completion_note}
                      onSave={async (newValue) => handleFieldUpdate('completion_note', newValue)}
                      placeholder="メモを入力"
                      multiline
                      markdown
                      renderView={(value) => (
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                          {value}
                        </ReactMarkdown>
                      )}
                    />
                  ) : (
                    <div className="completion-note-container markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {localTask.completion_note || ''}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}

              {isMeeting && (
                <>
                  <div className="detail-section meeting-section">
                    <div className="section-header-with-icon">
                      <HiOutlineCalendar />
                      <h3>会議情報</h3>
                    </div>
                    <div className="meeting-meta-box">
                      <div className="meeting-meta-grid">
                        <div className="meta-info-item">
                          <HiOutlineClock />
                          {onUpdateTask ? (
                            <div className="meeting-time-edit">
                              <EditableDateTime
                                value={localTask.start_time}
                                onSave={async (newValue) => handleFieldUpdate('start_time', newValue)}
                                placeholder="開始時刻"
                                timezone={timezone}
                                showTime
                              />
                              <span className="time-separator">〜</span>
                              <EditableDateTime
                                value={localTask.end_time}
                                onSave={async (newValue) => handleFieldUpdate('end_time', newValue)}
                                placeholder="終了時刻"
                                timezone={timezone}
                                showTime
                              />
                            </div>
                          ) : (
                            <span>{meetingTimeLabel}</span>
                          )}
                        </div>
                        {(localTask.location || onUpdateTask) && (
                          <div className="meta-info-item">
                            <HiOutlineLocationMarker />
                            {onUpdateTask ? (
                              <EditableSection
                                value={localTask.location}
                                onSave={async (newValue) => handleFieldUpdate('location', newValue)}
                                placeholder="場所を入力"
                                className="editable-location"
                              />
                            ) : (
                              <span>{localTask.location}</span>
                            )}
                          </div>
                        )}
                        {(localTask.attendees?.length > 0 || onUpdateTask) && (
                          <div className="meta-info-item">
                            <HiOutlineUserGroup />
                            {onUpdateTask ? (
                              <EditableSection
                                value={localTask.attendees?.join(', ') || ''}
                                onSave={async (newValue) => {
                                  const attendees = newValue
                                    .split(',')
                                    .map(s => s.trim())
                                    .filter(s => s.length > 0);
                                  await handleFieldUpdate('attendees', attendees);
                                }}
                                placeholder="参加者（カンマ区切り）"
                                className="editable-attendees"
                              />
                            ) : (
                              <span>{localTask.attendees?.join(', ')}</span>
                            )}
                          </div>
                        )}
                      </div>
                      <h4 className="meeting-notes-label">議事録</h4>
                      {onUpdateTask ? (
                        <EditableSection
                          value={localTask.meeting_notes}
                          onSave={async (newValue) => handleFieldUpdate('meeting_notes', newValue)}
                          placeholder="議事録を入力（Markdown対応）"
                          multiline
                          markdown
                          minRows={5}
                          renderView={(value) => (
                            <div className="meeting-notes-content markdown-content">
                              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                                {value}
                              </ReactMarkdown>
                            </div>
                          )}
                        />
                      ) : localTask.meeting_notes ? (
                        <div className="meeting-notes-content markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {localTask.meeting_notes}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <p className="empty-hint">議事録はまだありません。</p>
                      )}
                      <div className="meeting-actions">
                        <button
                          type="button"
                          className="premium-action-btn"
                          onClick={handleCreateActionItems}
                          disabled={!localTask.meeting_notes}
                        >
                          アクションアイテムを生成
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Agenda Section */}
                  <div className="detail-section agenda-section">
                    <AgendaList
                      meetingId={localTask.recurring_meeting_id || undefined}
                      taskId={localTask.recurring_meeting_id ? undefined : task.id}
                      eventDate={localTask.start_time ? localTask.start_time.split('T')[0] : undefined}
                    />
                  </div>
                </>
              )}

              {/* Subtasks Section - 常時表示 */}
              <div className="detail-section subtasks-section">
                <div className="section-header-row">
                  <h3 className="section-label">サブタスク ({sortedSubtasks.length})</h3>
                  <button
                    type="button"
                    className="breakdown-btn"
                    onClick={handleBreakdownTask}
                    title="AIでサブタスク分解"
                  >
                    <FaCodeBranch />
                    <span>AIで分解</span>
                  </button>
                </div>
                <ul className="subtasks-list">
                  {sortedSubtasks.map((subtask) => {

                    const { guide } = extractGuide(subtask.description, subtask.guide);
                    const hasGuide = guide.length > 0;
                    const stepNumber = stepNumberBySubtaskId.get(subtask.id);
                    const isLocked = isSubtaskLocked(subtask);

                    // Get assignee names for this subtask
                    const subtaskAssigneeIds = taskAssignments
                      .filter(a => a.task_id === subtask.id)
                      .map(a => a.assignee_id);
                    const subtaskAssigneeNames = subtaskAssigneeIds
                      .map(id => memberOptions.find(m => m.id === id)?.label)
                      .filter(Boolean) as string[];

                    return (
                      <li
                        key={subtask.id}
                        className={`subtask-item ${hasGuide ? 'has-guide' : ''} ${selectedSubtask?.id === subtask.id ? 'selected' : ''}`}
                        onClick={() => setSelectedSubtask(subtask)}
                      >
                        <div
                          className={`subtask-check-wrapper ${subtask.status === 'DONE' ? 'checked' : ''}`}
                          onClick={(e) => handleSubtaskCheck(subtask.id, e)}
                        >
                          {subtask.status === 'DONE' && <HiOutlineCheckCircle />}
                        </div>
                        {isLocked && <FaLock className="subtask-lock" />}
                        {stepNumber != null && <StepNumber stepNumber={stepNumber} className="small" />}
                        <span className={`subtask-title ${subtask.status === 'DONE' ? 'done' : ''}`}>
                          {subtask.title}
                        </span>
                        {hasGuide && <HiOutlineBookOpen className="guide-indicator" />}
                        {subtaskAssigneeNames.length > 0 && (
                          <span className="subtask-assignee-inline" title={subtaskAssigneeNames.join(', ')}>
                            <FaUser />
                            {subtaskAssigneeNames.length <= 2
                              ? subtaskAssigneeNames.join(', ')
                              : `${subtaskAssigneeNames[0]} +${subtaskAssigneeNames.length - 1}`}
                          </span>
                        )}
                        {subtask.estimated_minutes && <span className="subtask-duration">{subtask.estimated_minutes}分</span>}
                      </li>
                    );
                  })}
                  {/* Inline subtask creation */}
                  {onCreateSubtask && (
                    <li className="subtask-item subtask-create-inline">
                      <div className="subtask-check-wrapper placeholder" />
                      <input
                        type="text"
                        className="subtask-inline-input"
                        placeholder="＋ 新しいサブタスクを追加..."
                        value={newSubtaskTitle}
                        onChange={(e) => setNewSubtaskTitle(e.target.value)}
                        onKeyDown={async (e) => {
                          if (e.key === 'Enter' && newSubtaskTitle.trim() && !isCreatingSubtask) {
                            e.preventDefault();
                            setIsCreatingSubtask(true);
                            try {
                              // Pass false for openModal since modal is already open
                              await onCreateSubtask(task.id, newSubtaskTitle.trim(), false);
                              setNewSubtaskTitle('');
                            } catch {
                              alert('サブタスクの作成に失敗しました。');
                            } finally {
                              setIsCreatingSubtask(false);
                            }
                          }
                          if (e.key === 'Escape') {
                            setNewSubtaskTitle('');
                            (e.target as HTMLInputElement).blur();
                          }
                        }}
                        disabled={isCreatingSubtask}
                      />
                    </li>
                  )}
                </ul>
                {sortedSubtasks.length === 0 && !onCreateSubtask && (
                  <p className="empty-hint">サブタスクはまだありません</p>
                )}
              </div>

              <div className="detail-section footer-meta">

                <p>作成: {localTask.created_by === 'AGENT' ? 'AI秘書' : '自分'} • {formatDateValue(localTask.created_at)}</p>
                <p>更新: {formatDateValue(localTask.updated_at)}</p>
                {localTask.completed_at && (
                  <p>完了: {resolveCompletedByName(localTask.completed_by)} • {formatDateValue(localTask.completed_at)}</p>
                )}
              </div>
            </div>

            {/* Sidebar (always visible) */}
            <div className="modal-sidebar">
              <div className="sidebar-group">
                <h3 className="sidebar-label">状況</h3>
                <button
                  type="button"
                  className={`status-badge-lg status-${localStatus.toLowerCase()} ${isParentCompleted ? 'disabled' : 'clickable'}`}
                  onClick={() => {
                    if (isParentCompleted) return; // Parent is completed, subtask must stay DONE
                    // Skip DONE for requires_all_completion tasks (use check-completion instead)
                    const isAllCompletion = task.requires_all_completion && taskAssignments.filter(a => a.task_id === task.id).length > 1;
                    const statusOrder = isAllCompletion
                      ? ['TODO', 'IN_PROGRESS', 'WAITING']
                      : ['TODO', 'IN_PROGRESS', 'WAITING', 'DONE'];
                    const currentIndex = statusOrder.indexOf(localStatus);
                    const nextIndex = (currentIndex + 1) % statusOrder.length;
                    const nextStatus = statusOrder[nextIndex];
                    console.log('[TaskDetailModal] Status change:', task.id, localStatus, '->', nextStatus);
                    // Optimistic update - update local state immediately
                    setLocalStatus(nextStatus);
                    onStatusChange?.(task.id, nextStatus);
                  }}
                  disabled={isParentCompleted}
                  title={isParentCompleted ? '親タスクが完了しているため変更できません' : 'クリックでステータス変更'}
                >
                  {getStatusLabel(localStatus)}
                </button>

                <div className="progress-mini-item">

                  <div className="progress-header">
                    <span>進捗率</span>
                    <span className="progress-val">{localProgress}%</span>
                  </div>
                  <div className="progress-control">
                    <div className="progress-bar-container">
                      <div className="progress-bar-fill" style={{ width: `${localProgress}%` }} />
                      <input
                        type="range"
                        min="0"
                        max="100"
                        step="5"
                        value={localProgress}
                        onChange={(e) => setLocalProgress(parseInt(e.target.value, 10))}
                        onMouseUp={() => onProgressChange?.(task.id, localProgress)}
                        onTouchEnd={() => onProgressChange?.(task.id, localProgress)}
                        className="progress-slider"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {memberOptions.length > 0 && onAssigneeChange && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">担当者</h3>
                  <AssigneeSelect
                    taskId={task.id}
                    selectedIds={taskAssignments
                      .filter(a => a.task_id === task.id)
                      .map(a => a.assignee_id)}
                    options={memberOptions}
                    onChange={onAssigneeChange}
                  />
                </div>
              )}

              {/* Multi-member completion checklist */}
              {task.requires_all_completion && taskAssignments.filter(a => a.task_id === task.id).length > 1 && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">全員確認状況</h3>
                  <CompletionChecklist
                    assignments={taskAssignments.filter(a => a.task_id === task.id)}
                    memberOptions={memberOptions}
                    currentUserId={currentUserId || currentUser?.id}
                    onCheck={onCheckCompletion}
                    taskId={task.id}
                  />
                </div>
              )}

              {/* Toggle for requires_all_completion */}
              {onUpdateTask && taskAssignments.filter(a => a.task_id === task.id).length > 1 && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">完了条件</h3>
                  <label className="toggle-label-row">
                    <input
                      type="checkbox"
                      checked={localTask.requires_all_completion ?? false}
                      onChange={(e) => handleFieldUpdate('requires_all_completion', e.target.checked)}
                    />
                    <span>全員確認が必要</span>
                  </label>
                </div>
              )}

              <div className="sidebar-group">
                <h3 className="sidebar-label">メタデータ</h3>
                <div className="sidebar-meta-list">
                  <div className="sidebar-meta-item">
                    <span className="label">重要度</span>
                    {onUpdateTask ? (
                      <EditableSegment
                        value={localTask.importance}
                        options={[
                          { value: 'HIGH', label: 'HIGH', icon: <HiFire className="priority-icon-high" /> },
                          { value: 'MEDIUM', label: 'MEDIUM', icon: <HiOutlineFire className="priority-icon-medium" /> },
                          { value: 'LOW', label: 'LOW', icon: <HiOutlineClock className="priority-icon-low" /> },
                        ]}
                        onSave={async (newValue) => handleFieldUpdate('importance', newValue)}
                        renderValue={(val) => (
                          <span className={`meta-badge-sm importance-${val.toLowerCase()}`}>
                            {getPriorityIcon(val)}
                            {val}
                          </span>
                        )}
                      />
                    ) : (
                      <span className={`meta-badge-sm importance-${localTask.importance.toLowerCase()}`}>
                        {getPriorityIcon(localTask.importance)}
                        {localTask.importance}
                      </span>
                    )}
                  </div>
                  <div className="sidebar-meta-item">
                    <span className="label">緊急度</span>
                    {onUpdateTask ? (
                      <EditableSegment
                        value={localTask.urgency}
                        options={[
                          { value: 'HIGH', label: 'HIGH', icon: <HiFire className="priority-icon-high" /> },
                          { value: 'MEDIUM', label: 'MEDIUM', icon: <HiOutlineFire className="priority-icon-medium" /> },
                          { value: 'LOW', label: 'LOW', icon: <HiOutlineClock className="priority-icon-low" /> },
                        ]}
                        onSave={async (newValue) => handleFieldUpdate('urgency', newValue)}
                        renderValue={(val) => (
                          <span className={`meta-badge-sm urgency-${val.toLowerCase()}`}>
                            {getPriorityIcon(val)}
                            {val}
                          </span>
                        )}
                      />
                    ) : (
                      <span className={`meta-badge-sm urgency-${localTask.urgency.toLowerCase()}`}>
                        {getPriorityIcon(localTask.urgency)}
                        {localTask.urgency}
                      </span>
                    )}
                  </div>
                  <div className="sidebar-meta-item">
                    <span className="label">エネルギー</span>
                    {onUpdateTask ? (
                      <EditableSegment
                        value={localTask.energy_level}
                        options={[
                          { value: 'HIGH', label: 'HIGH', icon: <HiOutlineLightningBolt className="energy-icon-high" /> },
                          { value: 'LOW', label: 'LOW', icon: <HiOutlineClock className="energy-icon-low" /> },
                        ]}
                        onSave={async (newValue) => handleFieldUpdate('energy_level', newValue)}
                        renderValue={(val) => (
                          <span className={`meta-badge-sm energy-${val.toLowerCase()}`}>
                            {getEnergyIcon(val)}
                            {val}
                          </span>
                        )}
                      />
                    ) : (
                      <span className={`meta-badge-sm energy-${localTask.energy_level.toLowerCase()}`}>
                        {getEnergyIcon(localTask.energy_level)}
                        {localTask.energy_level}
                      </span>
                    )}
                  </div>
                  {(effectiveEstimatedMinutes > 0 || onUpdateTask) && (
                    <div className="sidebar-meta-item">
                      <span className="label">見積時間</span>
                      {onUpdateTask ? (
                        <EditableSection
                          value={localTask.estimated_minutes?.toString() || ''}
                          onSave={async (newValue) => {
                            const minutes = newValue ? parseInt(newValue, 10) : null;
                            await handleFieldUpdate('estimated_minutes', minutes);
                          }}
                          placeholder="分"
                          className="editable-number"
                          renderView={(val) => (
                            <span className="value"><HiOutlineClock /> {val}分</span>
                          )}
                        />
                      ) : (
                        <span className="value"><HiOutlineClock /> {effectiveEstimatedMinutes}分</span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {(localTask.project_id || localTask.phase_id || onUpdateTask) && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">プロジェクト</h3>
                  <div className="sidebar-meta-list">
                    <div className="sidebar-meta-item">
                      <span className="label">プロジェクト</span>
                      {onUpdateTask ? (
                        <EditableSelect
                          value={localTask.project_id}
                          options={projectOptions}
                          onSave={async (newValue) => {
                            // When project changes, clear phase
                            if (newValue !== localTask.project_id) {
                              await handleFieldUpdate('phase_id', null);
                            }
                            await handleFieldUpdate('project_id', newValue);
                          }}
                          placeholder="未設定"
                          icon={<FaProjectDiagram />}
                        />
                      ) : (
                        <span className="value"><FaProjectDiagram /> {effectiveProjectName || '読み込み中...'}</span>
                      )}
                    </div>
                    {(localTask.project_id || localTask.phase_id) && (
                      <div className="sidebar-meta-item">
                        <span className="label">フェーズ</span>
                        {onUpdateTask ? (
                          <EditableSelect
                            value={localTask.phase_id}
                            options={phaseOptions}
                            onSave={async (newValue) => handleFieldUpdate('phase_id', newValue)}
                            placeholder="未設定"
                            icon={<FaLayerGroup />}
                            disabled={!localTask.project_id}
                          />
                        ) : (
                          <span className="value"><FaLayerGroup /> {effectivePhaseName || '読み込み中...'}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {(localTask.due_date || localTask.start_not_before || onUpdateTask) && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">スケジュール</h3>
                  <div className="sidebar-meta-list">
                    {(localTask.start_not_before || onUpdateTask) && (
                      <div className="sidebar-meta-item">
                        <span className="label">着手可能日</span>
                        {onUpdateTask ? (
                          <EditableDateTime
                            value={localTask.start_not_before}
                            onSave={async (newValue) => handleFieldUpdate('start_not_before', newValue)}
                            placeholder="未設定"
                            timezone={timezone}
                            icon={<HiOutlineCalendar />}
                          />
                        ) : (
                          <span className="value"><HiOutlineCalendar /> {localTask.start_not_before ? formatDateValue(localTask.start_not_before) : '未設定'}</span>
                        )}
                      </div>
                    )}
                    {(localTask.due_date || onUpdateTask) && (
                      <div className="sidebar-meta-item">
                        <span className="label">期限</span>
                        {onUpdateTask ? (
                          <EditableDateTime
                            value={localTask.due_date}
                            onSave={async (newValue) => handleFieldUpdate('due_date', newValue)}
                            placeholder="未設定"
                            timezone={timezone}
                            icon={<HiOutlineCalendar />}
                          />
                        ) : (
                          <span className="value"><HiOutlineCalendar /> {localTask.due_date ? formatDateValue(localTask.due_date) : '未設定'}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {(localTask.touchpoint_count || localTask.touchpoint_minutes || (localTask.touchpoint_steps && localTask.touchpoint_steps.length > 0) || onUpdateTask) && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">Touchpoints</h3>
                  <div className="sidebar-meta-list">
                    <div className="sidebar-meta-item">
                      <span className="label">Count</span>
                      {onUpdateTask ? (
                        <EditableSection
                          value={localTask.touchpoint_count?.toString() || ''}
                          onSave={async (newValue) => {
                            const count = newValue ? parseInt(newValue, 10) : null;
                            await handleFieldUpdate('touchpoint_count', count);
                          }}
                          placeholder="未設定"
                          className="editable-number"
                          renderView={(val) => (
                            <span className="value">{val ? `${val}回` : '未設定'}</span>
                          )}
                        />
                      ) : (
                        <span className="value">
                          {localTask.touchpoint_count ? `${localTask.touchpoint_count}回` : '未設定'}
                        </span>
                      )}
                    </div>
                    <div className="sidebar-meta-item">
                      <span className="label">Minutes</span>
                      {onUpdateTask ? (
                        <EditableSection
                          value={localTask.touchpoint_minutes?.toString() || ''}
                          onSave={async (newValue) => {
                            const minutes = newValue ? parseInt(newValue, 10) : null;
                            await handleFieldUpdate('touchpoint_minutes', minutes);
                          }}
                          placeholder="未設定"
                          className="editable-number"
                          renderView={(val) => (
                            <span className="value">{val ? `${val}分` : '未設定'}</span>
                          )}
                        />
                      ) : (
                        <span className="value">
                          {localTask.touchpoint_minutes ? `${localTask.touchpoint_minutes}分` : '未設定'}
                        </span>
                      )}
                    </div>
                    <div className="sidebar-meta-item">
                      <span className="label">Gap</span>
                      {onUpdateTask ? (
                        <EditableSection
                          value={(localTask.touchpoint_gap_days ?? 0).toString()}
                          onSave={async (newValue) => {
                            const gap = newValue ? parseInt(newValue, 10) : 0;
                            await handleFieldUpdate('touchpoint_gap_days', gap);
                          }}
                          placeholder="0"
                          className="editable-number"
                          renderView={(val) => (
                            <span className="value">{val || '0'}日</span>
                          )}
                        />
                      ) : (
                        <span className="value">{localTask.touchpoint_gap_days ?? 0}日</span>
                      )}
                    </div>
                    {(localTask.touchpoint_steps && localTask.touchpoint_steps.length > 0) && (
                      <div className="sidebar-meta-item">
                        <span className="label">Steps</span>
                        <div className="value">
                          {localTask.touchpoint_steps.map((step, index) => (
                            <div key={`${step.title}-${index}`}>
                              {index + 1}. {step.title}
                              {step.estimated_minutes ? ` (${step.estimated_minutes}分)` : ''}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {(dependencies.length > 0 || onUpdateTask) && (
                <div className="sidebar-group">
                  <h3 className="sidebar-label">依存関係</h3>
                  {onUpdateTask ? (
                    <EditableDependencies
                      value={localTask.dependency_ids}
                      allTasks={allTasks}
                      currentTaskId={task.id}
                      onSave={async (newValue) => handleFieldUpdate('dependency_ids', newValue)}
                    />
                  ) : (
                    <ul className="sidebar-dependencies">
                      {dependencies.map((dep) => (
                        <li
                          key={dep.id}
                          className={`sidebar-dep-item ${dep.status === 'DONE' ? 'completed' : ''}`}
                          title={dep.title}
                          onClick={() => {
                            onClose();
                            setTimeout(() => {
                              const taskCard = document.querySelector(`[data-task-id="${dep.id}"]`);
                              if (taskCard) (taskCard as HTMLElement).click();
                            }, 300);
                          }}
                        >
                          {dep.status === 'DONE' ? <FaLockOpen /> : <FaLock />}
                          <span>{dep.title}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>

      <AnimatePresence>
        {selectedSubtask && (
          <motion.div
            layout
            className="guide-panel"
            onClick={(e) => e.stopPropagation()}
            initial={{ x: 50, opacity: 0, width: 0 }}

            animate={{ x: 0, opacity: 1, width: window.innerWidth > 1024 ? 700 : "100%" }}
            exit={{ x: 50, opacity: 0, width: 0 }}
            transition={{ type: "spring", damping: 35, stiffness: 400 }}
          >
            <div className="guide-header">
              <button className="back-btn" onClick={(e) => { e.stopPropagation(); setSelectedSubtask(null); }}>
                <FaArrowLeft />
              </button>

              <h3>サブタスク詳細</h3>

              <div className="guide-header-actions">
                {onDelete && (
                  <button
                    className="guide-delete-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(selectedSubtask);
                    }}
                    title="サブタスクを削除"
                  >
                    <FaTrash />
                  </button>
                )}
              </div>
            </div>

            <div className="guide-body">
              <div className="guide-title-row">
                {selectedSubtaskStepNumber != null && <StepNumber stepNumber={selectedSubtaskStepNumber} />}
                {onUpdateTask ? (
                  <EditableSection
                    value={selectedSubtask.title}
                    onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'title', newValue)}
                    placeholder="サブタスク名を入力"
                    className="editable-subtask-title"
                  />
                ) : (
                  <h4>{selectedSubtask.title}</h4>
                )}
              </div>

              <div className="guide-meta-box">
                <div className="metadata-grid">
                  <div className="metadata-item">
                    <span className="metadata-label">状況</span>
                    {onUpdateTask ? (
                      <button
                        type="button"
                        className={`status-badge status-${selectedSubtask.status.toLowerCase()} clickable`}
                        onClick={() => {
                          const statusOrder = ['TODO', 'IN_PROGRESS', 'WAITING', 'DONE'];
                          const currentIndex = statusOrder.indexOf(selectedSubtask.status);
                          const nextIndex = (currentIndex + 1) % statusOrder.length;
                          handleSubtaskFieldUpdate(selectedSubtask.id, 'status', statusOrder[nextIndex]);
                        }}
                        title="クリックでステータス変更"
                      >
                        {getStatusLabel(selectedSubtask.status)}
                      </button>
                    ) : (
                      <span className={`status-badge status-${selectedSubtask.status.toLowerCase()}`}>
                        {getStatusLabel(selectedSubtask.status)}
                      </span>
                    )}
                  </div>
                  <div className="metadata-item">
                    <span className="metadata-label">時間</span>
                    {onUpdateTask ? (
                      <EditableSection
                        value={selectedSubtask.estimated_minutes?.toString() || ''}
                        onSave={async (newValue) => {
                          const minutes = newValue ? parseInt(newValue, 10) : null;
                          await handleSubtaskFieldUpdate(selectedSubtask.id, 'estimated_minutes', minutes);
                        }}
                        placeholder="分"
                        className="editable-number"
                        renderView={(val) => (
                          <span className="metadata-value"><HiOutlineClock /> {val}分</span>
                        )}
                      />
                    ) : selectedSubtask.estimated_minutes ? (
                      <span className="metadata-value">{selectedSubtask.estimated_minutes}分</span>
                    ) : (
                      <span className="metadata-value empty">未設定</span>
                    )}
                  </div>
                </div>
                {onUpdateTask && (
                  <div className="subtask-progress-section">
                    <div className="progress-header">
                      <span className="metadata-label">進捗率</span>
                      <span className="progress-val">{localSubtaskProgress}%</span>
                    </div>
                    <div className="progress-control">
                      <div className="progress-bar-container">
                        <div className="progress-bar-fill" style={{ width: `${localSubtaskProgress}%` }} />
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="5"
                          value={localSubtaskProgress}
                          onChange={(e) => setLocalSubtaskProgress(parseInt(e.target.value, 10))}
                          onMouseUp={() => handleSubtaskFieldUpdate(selectedSubtask.id, 'progress', localSubtaskProgress)}
                          onTouchEnd={() => handleSubtaskFieldUpdate(selectedSubtask.id, 'progress', localSubtaskProgress)}
                          className="progress-slider"
                        />
                      </div>
                    </div>
                  </div>
                )}
                {memberOptions.length > 0 && onAssigneeChange && (
                  <div className="subtask-assignee-section">
                    <span className="metadata-label"><FaUser /> 担当者</span>
                    <AssigneeSelect
                      taskId={selectedSubtask.id}
                      selectedIds={taskAssignments
                        .filter(a => a.task_id === selectedSubtask.id)
                        .map(a => a.assignee_id)}
                      options={memberOptions}
                      onChange={onAssigneeChange}
                      compact
                    />
                  </div>
                )}
              </div>

              {/* スケジュール（期限・着手可能日） */}
              {(selectedSubtask.due_date || selectedSubtask.start_not_before || onUpdateTask) && (
                <div className="guide-section subtask-schedule-section">
                  <h4><HiOutlineCalendar /> スケジュール</h4>
                  <div className="subtask-schedule-grid">
                    {(selectedSubtask.start_not_before || onUpdateTask) && (
                      <div className="subtask-schedule-item">
                        <span className="metadata-label">着手可能日</span>
                        {onUpdateTask ? (
                          <EditableDateTime
                            value={selectedSubtask.start_not_before}
                            onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'start_not_before', newValue)}
                            placeholder="未設定"
                            timezone={timezone}
                            icon={<HiOutlineCalendar />}
                          />
                        ) : (
                          <span className="metadata-value">
                            <HiOutlineCalendar /> {selectedSubtask.start_not_before ? formatDateValue(selectedSubtask.start_not_before) : '未設定'}
                          </span>
                        )}
                      </div>
                    )}
                    {(selectedSubtask.due_date || onUpdateTask) && (
                      <div className="subtask-schedule-item">
                        <span className="metadata-label">期限</span>
                        {onUpdateTask ? (
                          <EditableDateTime
                            value={selectedSubtask.due_date}
                            onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'due_date', newValue)}
                            placeholder="未設定"
                            timezone={timezone}
                            icon={<HiOutlineCalendar />}
                          />
                        ) : (
                          <span className="metadata-value">
                            <HiOutlineCalendar /> {selectedSubtask.due_date ? formatDateValue(selectedSubtask.due_date) : '未設定'}
                          </span>
                        )}
                      </div>
                    )}
                    <div className="subtask-schedule-item">
                      <span className="metadata-label">Same day</span>
                      {onUpdateTask ? (
                        <EditableSegment
                          value={selectedSubtask.same_day_allowed === false ? 'false' : 'true'}
                          options={[
                            { value: 'true', label: 'OK' },
                            { value: 'false', label: 'NG' },
                          ]}
                          onSave={async (newValue) => {
                            await handleSubtaskFieldUpdate(
                              selectedSubtask.id,
                              'same_day_allowed',
                              newValue === 'true'
                            );
                          }}
                        />
                      ) : (
                        <span className="metadata-value">
                          {selectedSubtask.same_day_allowed === false ? 'NG' : 'OK'}
                        </span>
                      )}
                    </div>
                    <div className="subtask-schedule-item">
                      <span className="metadata-label">Gap (days)</span>
                      {onUpdateTask ? (
                        <EditableSection
                          value={(selectedSubtask.min_gap_days ?? 0).toString()}
                          onSave={async (newValue) => {
                            const gap = newValue ? parseInt(newValue, 10) : 0;
                            await handleSubtaskFieldUpdate(selectedSubtask.id, 'min_gap_days', gap);
                          }}
                          placeholder="0"
                          className="editable-number"
                          renderView={(val) => (
                            <span className="metadata-value">{val || '0'}日</span>
                          )}
                        />
                      ) : (
                        <span className="metadata-value">{selectedSubtask.min_gap_days ?? 0}日</span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* 依存関係 */}
              {((selectedSubtask.dependency_ids && selectedSubtask.dependency_ids.length > 0) || onUpdateTask) && (
                <div className="guide-section subtask-dependencies-section">
                  <h4><FaProjectDiagram /> 依存関係</h4>
                  {onUpdateTask ? (
                    <EditableDependencies
                      value={selectedSubtask.dependency_ids}
                      allTasks={[...allTasks, ...localSubtasks]}
                      currentTaskId={selectedSubtask.id}
                      onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'dependency_ids', newValue)}
                    />
                  ) : (
                    <ul className="sidebar-dependencies">
                      {(selectedSubtask.dependency_ids || []).map((depId) => {
                        const dep = [...allTasks, ...localSubtasks].find(t => t.id === depId);
                        if (!dep) return null;
                        return (
                          <li
                            key={dep.id}
                            className={`sidebar-dep-item ${dep.status === 'DONE' ? 'completed' : ''}`}
                            title={dep.title}
                          >
                            {dep.status === 'DONE' ? <FaLockOpen /> : <FaLock />}
                            <span>{dep.title}</span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              )}

              {(selectedGuide?.mainDescription || onUpdateTask) && (
                <div className="guide-section">
                  <h4>説明</h4>
                  {onUpdateTask ? (
                    <EditableSection
                      value={selectedSubtask.description}
                      onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'description', newValue)}
                      placeholder="説明を入力（Markdown対応）"
                      multiline
                      markdown
                      renderView={(value) => (
                        <div className="markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {value}
                          </ReactMarkdown>
                        </div>
                      )}
                    />
                  ) : (
                    <div className="markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {selectedGuide?.mainDescription || ''}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}

              {(selectedGuide?.guide || onUpdateTask) && (
                <div className="guide-section">
                  <div className="section-header-with-icon">
                    <HiOutlineBookOpen />
                    <h4>進め方ガイド</h4>
                  </div>
                  {onUpdateTask ? (
                    <EditableSection
                      value={selectedSubtask.guide}
                      onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'guide', newValue)}
                      placeholder="進め方ガイドを入力（Markdown対応）"
                      multiline
                      markdown
                      renderView={(value) => (
                        <div className="guide-steps-box markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {value}
                          </ReactMarkdown>
                        </div>
                      )}
                    />
                  ) : (
                    <div className="guide-steps-box markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {selectedGuide?.guide || ''}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}

              {(selectedSubtask.completion_note || onUpdateTask) && (
                <div className="guide-section completion-note-section">
                  <div className="section-header-with-icon">
                    <HiOutlinePencilAlt />
                    <h4>メモ</h4>
                  </div>
                  {onUpdateTask ? (
                    <EditableSection
                      value={selectedSubtask.completion_note}
                      onSave={async (newValue) => handleSubtaskFieldUpdate(selectedSubtask.id, 'completion_note', newValue)}
                      placeholder="メモを入力"
                      multiline
                      markdown
                      renderView={(value) => (
                        <div className="completion-note-container markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {value}
                          </ReactMarkdown>
                        </div>
                      )}
                    />
                  ) : (
                    <div className="completion-note-container markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {selectedSubtask.completion_note || ''}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div >
  );
}
