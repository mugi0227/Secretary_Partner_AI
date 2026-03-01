import type { ReactElement } from 'react';
import { useEffect, useMemo, useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  FaCalendarAlt,
  FaChartBar,
  FaCheck,
  FaCheckCircle,
  FaChevronDown,
  FaChevronRight,
  FaColumns,
  FaEdit,
  FaLock,
  FaPlus,
  FaStream,
  FaTasks,
  FaThLarge,
  FaTimes,
  FaTrash,
  FaTrophy,
  FaSitemap,
  FaUsers,
  FaCircle,
} from 'react-icons/fa';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { usePageTour } from '../hooks/usePageTour';
import { PageTour } from '../components/onboarding/PageTour';
import { TourHelpButton } from '../components/onboarding/TourHelpButton';
import { milestonesApi } from '../api/milestones';
import { phasesApi } from '../api/phases';
import { getProject, projectsApi } from '../api/projects';
import { tasksApi } from '../api/tasks';
import type {
  Blocker,
  CheckinV2,
  MemberProjectTask,
  Milestone,
  MilestoneUpdate,
  PhaseWithTaskCount,
  ProjectInvitation,
  ProjectKpiMetric,
  ProjectMember,
  Task,
  TaskAssignment,
  TaskStatus,
} from '../api/types';
import type { UserSearchResult } from '../api/users';
import type { DraftCardData } from '../components/chat/DraftCard';
import { UserSearchInput } from '../components/common/UserSearchInput';
import { MilestoneEditModal } from '../components/gantt/MilestoneEditModal';
import { ProjectGanttChart } from '../components/gantt/ProjectGanttChart';
import { MeetingsTab } from '../components/meetings/MeetingsTab';
import { ProjectAchievementsSection } from '../components/projects/ProjectAchievementsSection';
import { ProjectHierarchyTree } from '../components/projects/ProjectHierarchyTree';
import { ChildProjectsSection } from '../components/projects/ChildProjectsSection';
import { InviteFromParentSection } from '../components/projects/InviteFromParentSection';
import { ProjectDetailModal } from '../components/projects/ProjectDetailModal';
import { ProjectTasksView } from '../components/projects/ProjectTasksView';
import { RecurringTaskList } from '../components/tasks/RecurringTaskList';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { useRecurringTasks } from '../hooks/useRecurringTasks';
import { useTaskModal } from '../hooks/useTaskModal';
import { useTasks } from '../hooks/useTasks';
import { useTimezone } from '../hooks/useTimezone';
import { formatDate, getDeadlineStatus, toDateKey, toDateTime, todayInTimezone } from '../utils/dateTime';
import './ProjectDetailV2Page.css';

type TabId = 'dashboard' | 'team' | 'timeline' | 'board' | 'gantt' | 'meetings' | 'achievements' | 'tree';
type InviteMode = 'email' | 'user_id';

const TAB_LABELS: Record<TabId, string> = {
  dashboard: 'ダッシュボード',
  team: 'チーム',
  timeline: 'タイムライン',
  board: 'ボード',
  gantt: 'ガント',
  meetings: 'ミーティング',
  achievements: '達成項目',
  tree: 'ツリー',
};

const TAB_ICONS: Record<TabId, ReactElement> = {
  dashboard: <FaThLarge />,
  team: <FaUsers />,
  timeline: <FaStream />,
  board: <FaColumns />,
  gantt: <FaChartBar />,
  meetings: <FaCalendarAlt />,
  achievements: <FaTrophy />,
  tree: <FaSitemap />,
};

const STATUS_LABELS: Record<TaskStatus, string> = {
  TODO: '未着手',
  IN_PROGRESS: '進行中',
  WAITING: '待機中',
  DONE: '完了',
};

const CHILD_TASK_STATUS_COLORS: Record<string, string> = {
  TODO: '#94a3b8',
  IN_PROGRESS: '#0ea5e9',
  WAITING: '#f59e0b',
  DONE: '#22c55e',
};

const PRIORITY_RANK: Record<string, number> = {
  HIGH: 0,
  MEDIUM: 1,
  LOW: 2,
};

const formatHours = (minutes: number) => {
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours}h`;
};

const computeKpiProgress = (metric: ProjectKpiMetric) => {
  const current = metric.current ?? 0;
  const target = metric.target ?? 0;

  if (metric.key === 'remaining_hours') {
    if (target > 0) {
      const ratio = 1 - current / target;
      return Math.max(0, Math.min(ratio * 100, 100));
    }
    return current <= 0 ? 100 : 0;
  }

  if (metric.direction === 'down') {
    if (target <= 0) {
      return current <= 0 ? 100 : 0;
    }
    if (current <= 0) {
      return 100;
    }
    return Math.min((target / current) * 100, 100);
  }

  if (target <= 0) {
    return 0;
  }

  return Math.min((current / target) * 100, 100);
};

const getInitial = (value?: string) => {
  if (!value) return '?';
  const trimmed = value.trim();
  return trimmed ? trimmed.charAt(0) : '?';
};

const VALID_TABS: TabId[] = ['dashboard', 'team', 'timeline', 'board', 'gantt', 'meetings', 'achievements', 'tree'];

function CollapsibleChildTaskNode({
  task,
  subtasks,
  onTaskClick,
}: {
  task: MemberProjectTask;
  subtasks: MemberProjectTask[];
  onTaskClick: (taskId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasChildren = subtasks.length > 0;

  return (
    <div>
      <div
        className={`project-v2-child-task-row${task.task_status === 'DONE' ? ' done' : ''}`}
        onClick={hasChildren ? () => setOpen(!open) : () => onTaskClick(task.task_id)}
        style={{ cursor: 'pointer' }}
      >
        <span className="project-v2-child-task-toggle">
          {hasChildren ? (open ? <FaChevronDown /> : <FaChevronRight />) : null}
        </span>
        <FaCircle
          className="project-v2-child-task-dot"
          style={{ color: CHILD_TASK_STATUS_COLORS[task.task_status] || '#94a3b8' }}
        />
        <span className="project-v2-child-task-title">{task.task_title}</span>
        {hasChildren && <span className="project-v2-child-task-count">{subtasks.length}</span>}
        <div className="project-v2-member-task-status" data-status={task.task_status}>
          {STATUS_LABELS[task.task_status as TaskStatus] || task.task_status}
        </div>
      </div>
      {open && subtasks.map(sub => (
        <div
          key={sub.task_id}
          className={`project-v2-child-task-row project-v2-child-task-indent${sub.task_status === 'DONE' ? ' done' : ''}`}
          onClick={() => onTaskClick(sub.task_id)}
          style={{ cursor: 'pointer' }}
        >
          <FaCircle
            className="project-v2-child-task-dot"
            style={{ color: CHILD_TASK_STATUS_COLORS[sub.task_status] || '#94a3b8' }}
          />
          <span className="project-v2-child-task-title">{sub.task_title}</span>
          <div className="project-v2-member-task-status" data-status={sub.task_status}>
            {STATUS_LABELS[sub.task_status as TaskStatus] || sub.task_status}
          </div>
        </div>
      ))}
    </div>
  );
}

function CollapsibleChildTaskGroup({
  projectName,
  tasks,
  onTaskClick,
}: {
  projectName: string;
  tasks: MemberProjectTask[];
  onTaskClick: (taskId: string) => void;
}) {
  const [open, setOpen] = useState(false);

  const taskIdSet = new Set(tasks.map(t => t.task_id));
  const childrenMap = new Map<string, MemberProjectTask[]>();
  const roots: MemberProjectTask[] = [];
  for (const ct of tasks) {
    if (ct.parent_id && taskIdSet.has(ct.parent_id)) {
      const arr = childrenMap.get(ct.parent_id) || [];
      arr.push(ct);
      childrenMap.set(ct.parent_id, arr);
    } else {
      roots.push(ct);
    }
  }

  return (
    <div>
      <div
        className="project-v2-task-group-label collapsible"
        onClick={() => setOpen(!open)}
      >
        {open ? <FaChevronDown className="group-chevron" /> : <FaChevronRight className="group-chevron" />}
        {projectName}
        <span className="group-task-count">{tasks.length}</span>
      </div>
      {open && roots.map((ct) => {
        const subs = childrenMap.get(ct.task_id) || [];
        return (
          <CollapsibleChildTaskNode
            key={ct.task_id}
            task={ct}
            subtasks={subs}
            onTaskClick={onTaskClick}
          />
        );
      })}
    </div>
  );
}

export function ProjectDetailV2Page() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const timezone = useTimezone();
  const tour = usePageTour('projectDetail');

  // Read initial tab from URL query parameter
  const getInitialTab = (): TabId => {
    const tabParam = searchParams.get('tab');
    if (tabParam && VALID_TABS.includes(tabParam as TabId)) {
      return tabParam as TabId;
    }
    return 'dashboard';
  };

  const [activeTab, setActiveTab] = useState<TabId>(getInitialTab);
  const { deleteGeneratedTasks, generateTasks } = useRecurringTasks(projectId);
  const queryClient = useQueryClient();
  const {
    data: project = null,
    isLoading,
    error: projectError,
  } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId!),
    enabled: !!projectId,
  });
  const error = projectError ? 'プロジェクトの取得に失敗しました。' : (!projectId ? 'プロジェクトIDが不正です。' : null);

  const { data: memberChildTasks } = useQuery({
    queryKey: ['member-child-tasks', projectId],
    queryFn: () => projectsApi.getMemberChildTasks(projectId!),
    enabled: !!projectId && (project?.child_project_count ?? 0) > 0,
  });

  const childTasksByMember = useMemo(() => {
    if (!memberChildTasks) return {} as Record<string, Record<string, MemberProjectTask[]>>;
    const map: Record<string, Record<string, MemberProjectTask[]>> = {};
    for (const m of memberChildTasks) {
      const byProject: Record<string, MemberProjectTask[]> = {};
      for (const t of m.tasks_by_project) {
        if (!byProject[t.child_project_name]) byProject[t.child_project_name] = [];
        byProject[t.child_project_name].push(t);
      }
      map[m.member_user_id] = byProject;
    }
    return map;
  }, [memberChildTasks]);

  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [invitations, setInvitations] = useState<ProjectInvitation[]>([]);
  const [blockers, setBlockers] = useState<Blocker[]>([]);
  const [checkins, setCheckins] = useState<CheckinV2[]>([]);
  const [isCollabLoading, setIsCollabLoading] = useState(false);
  const [inviteMode, setInviteMode] = useState<InviteMode>('email');
  const [inviteValue, setInviteValue] = useState('');
  const [isInviting, setIsInviting] = useState(false);
  const [memberActionId, setMemberActionId] = useState<string | null>(null);
  const [invitationActionId, setInvitationActionId] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<TaskAssignment[]>([]);
  const [phases, setPhases] = useState<PhaseWithTaskCount[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [isPhasesLoading, setIsPhasesLoading] = useState(false);
  const [isMilestonesLoading, setIsMilestonesLoading] = useState(false);
  const [phasePlanInstruction, setPhasePlanInstruction] = useState('');
  const [capacityDrafts, setCapacityDrafts] = useState<Record<string, string>>({});
  const [capacityActionId, setCapacityActionId] = useState<string | null>(null);
  const [editingCapacityId, setEditingCapacityId] = useState<string | null>(null);
  const [phaseBufferDrafts, setPhaseBufferDrafts] = useState<Record<string, string>>({});
  const [phaseBufferActionId, setPhaseBufferActionId] = useState<string | null>(null);

  // Phase edit/delete state
  const [editingPhaseId, setEditingPhaseId] = useState<string | null>(null);
  const [editPhaseName, setEditPhaseName] = useState('');
  const [editPhaseDescription, setEditPhaseDescription] = useState('');

  // Milestone edit/add/delete state
  const [editingMilestoneId, setEditingMilestoneId] = useState<string | null>(null);
  const [editMilestoneTitle, setEditMilestoneTitle] = useState('');
  const [editMilestoneDescription, setEditMilestoneDescription] = useState('');
  const [editMilestoneDueDate, setEditMilestoneDueDate] = useState('');
  const [addingMilestonePhaseId, setAddingMilestonePhaseId] = useState<string | null>(null);
  const [newMilestoneTitle, setNewMilestoneTitle] = useState('');
  const [newMilestoneDescription, setNewMilestoneDescription] = useState('');
  const [newMilestoneDueDate, setNewMilestoneDueDate] = useState('');

  // Gantt milestone edit modal state
  const [ganttEditingMilestone, setGanttEditingMilestone] = useState<Milestone | null>(null);
  const [ganttMilestoneSubmitting, setGanttMilestoneSubmitting] = useState(false);
  const [pendingDeleteMilestone, setPendingDeleteMilestone] = useState<{
    id: string;
    title: string;
    linkedTaskCount: number;
  } | null>(null);
  const [isDeletingMilestone, setIsDeletingMilestone] = useState(false);

  // Team accordion state
  const [expandedMemberIds, setExpandedMemberIds] = useState<Set<string>>(new Set());
  const toggleMemberExpand = useCallback((memberId: string) => {
    setExpandedMemberIds((prev) => {
      const next = new Set(prev);
      if (next.has(memberId)) {
        next.delete(memberId);
      } else {
        next.add(memberId);
      }
      return next;
    });
  }, []);

  // Project edit/delete state
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [isDeletingProject, setIsDeletingProject] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  const {
    tasks,
    isLoading: tasksLoading,
    refetch: refetchTasks,
    updateTask,
    deleteTask,
  } = useTasks(projectId);
  const { data: currentUser } = useCurrentUser();

  // NOTE: useTaskModal is defined after memberOptions/handleAssignMultiple (see below)

  // Update tab when URL query param changes
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam && VALID_TABS.includes(tabParam as TabId)) {
      setActiveTab(tabParam as TabId);
    }
  }, [searchParams]);

  const refetchProject = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['project', projectId] });
  }, [queryClient, projectId]);

  useEffect(() => {
    if (!projectId) return;

    const fetchCollaboration = async () => {
      setIsCollabLoading(true);
      try {
        const [membersData, invitationsData, blockersData, checkinsData, assignmentsData] = await Promise.all([
          projectsApi.listMembers(projectId),
          projectsApi.listInvitations(projectId),
          projectsApi.listBlockers(projectId),
          projectsApi.listCheckinsV2(projectId),
          projectsApi.listAssignments(projectId),
        ]);
        setMembers(Array.isArray(membersData) ? membersData : []);
        setInvitations(Array.isArray(invitationsData) ? invitationsData : []);
        setBlockers(Array.isArray(blockersData) ? blockersData : []);
        setCheckins(Array.isArray(checkinsData) ? checkinsData : []);
        setAssignments(Array.isArray(assignmentsData) ? assignmentsData : []);
      } catch (err) {
        console.error('Failed to fetch collaboration data:', err);
      } finally {
        setIsCollabLoading(false);
      }
    };

    fetchCollaboration();
  }, [projectId]);

  const refreshPhases = async () => {
    if (!projectId) return;
    setIsPhasesLoading(true);
    try {
      const data = await phasesApi.listByProject(projectId);
      setPhases(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch phases:', err);
    } finally {
      setIsPhasesLoading(false);
    }
  };

  const refreshMilestones = async () => {
    if (!projectId) return;
    setIsMilestonesLoading(true);
    try {
      const data = await milestonesApi.listByProject(projectId);
      setMilestones(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch milestones:', err);
    } finally {
      setIsMilestonesLoading(false);
    }
  };

  useEffect(() => {
    if (!projectId) return;
    refreshPhases();
    refreshMilestones();
  }, [projectId]);

  useEffect(() => {
    if (members.length === 0) {
      setCapacityDrafts({});
      return;
    }
    const next: Record<string, string> = {};
    members.forEach((member) => {
      next[member.id] = member.capacity_hours != null ? String(member.capacity_hours) : '';
    });
    setCapacityDrafts(next);
  }, [members]);

  useEffect(() => {
    if (phases.length === 0) {
      setPhaseBufferDrafts({});
      return;
    }
    const next: Record<string, string> = {};
    phases.forEach((phase) => {
      const minutes = phase.fixed_buffer_minutes ?? 0;
      const hours = minutes > 0 ? Math.round((minutes / 60) * 10) / 10 : 0;
      next[phase.id] = minutes > 0 ? String(hours) : '';
    });
    setPhaseBufferDrafts(next);
  }, [phases]);

  const completionRate = project && project.total_tasks > 0
    ? Math.round((project.completed_tasks / project.total_tasks) * 100)
    : 0;
  const formatShortDate = (value?: string) => {
    if (!value) return '';
    return formatDate(value, { month: 'numeric', day: 'numeric' }, timezone);
  };

  const inProgressCount = useMemo(
    () => tasks.filter(task => task.status === 'IN_PROGRESS').length,
    [tasks]
  );

  const waitingCount = useMemo(
    () => tasks.filter(task => task.status === 'WAITING').length,
    [tasks]
  );

  const openBlockerCount = useMemo(() =>
    blockers.filter(blocker => blocker.status === 'OPEN').length
    , [blockers]);

  const blockedDependencyCount = useMemo(() => {
    if (tasks.length === 0) return 0;
    const taskMap = new Map(tasks.map(task => [task.id, task]));
    return tasks.filter((task) => {
      if (task.status === 'DONE') {
        return false;
      }
      return task.dependency_ids?.some((depId) => {
        const dep = taskMap.get(depId);
        return dep && dep.status !== 'DONE';
      });
    }).length;
  }, [tasks]);

  const overdueTasks = useMemo(() => {
    const today = todayInTimezone(timezone);
    return tasks.filter(task => {
      if (!task.due_date || task.status === 'DONE') return false;
      const due = toDateTime(task.due_date, timezone).startOf('day');
      return due.isValid && due < today;
    });
  }, [tasks, timezone]);

  const memberLabelById = useMemo(() => {
    const map: Record<string, string> = {};
    members.forEach((member) => {
      map[member.member_user_id] = member.member_display_name || member.member_user_id;
    });
    return map;
  }, [members]);

  const pendingInvitations = useMemo(() =>
    invitations.filter((inv) => inv.status === 'PENDING')
    , [invitations]);

  const taskTitleById = useMemo(() => {
    const map = new Map<string, string>();
    tasks.forEach((task) => {
      if (task.id) {
        map.set(task.id, task.title);
      }
    });
    return map;
  }, [tasks]);

  const invitationLabelById = useMemo(() => {
    const map: Record<string, string> = {};
    pendingInvitations.forEach((invitation) => {
      map[`inv:${invitation.id}`] = `${invitation.email} (招待中)`;
    });
    return map;
  }, [pendingInvitations]);

  const assigneeByTaskId = useMemo(() => {
    const assigneeMap: Record<string, string> = {};

    assignments.forEach((assignment) => {
      if (!assignment.assignee_id) return;

      let label: string;
      if (assignment.assignee_id.startsWith('inv:')) {
        label = invitationLabelById[assignment.assignee_id] || assignment.assignee_id;
      } else {
        label = memberLabelById[assignment.assignee_id] || assignment.assignee_id;
      }

      if (assigneeMap[assignment.task_id]) {
        assigneeMap[assignment.task_id] += `, ${label}`;
      } else {
        assigneeMap[assignment.task_id] = label;
      }
    });

    return assigneeMap;
  }, [assignments, invitationLabelById, memberLabelById]);

  const assignedMemberIdsByTaskId = useMemo(() => {
    const map: Record<string, string[]> = {};
    assignments.forEach((assignment) => {
      if (!assignment.assignee_id) return;
      if (!map[assignment.task_id]) {
        map[assignment.task_id] = [];
      }
      map[assignment.task_id].push(assignment.assignee_id);
    });
    return map;
  }, [assignments]);

  const memberOptions = useMemo(() => ([
    ...members.map((member) => ({
      id: member.member_user_id,
      label: member.member_display_name || member.member_user_id,
    })),
    ...pendingInvitations.map((invitation) => ({
      id: `inv:${invitation.id}`,
      label: `${invitation.email} (招待中)`,
    })),
  ]), [members, pendingInvitations]);

  const sortedPhases = useMemo(
    () => [...phases].sort((a, b) => a.order_in_project - b.order_in_project),
    [phases]
  );

  const currentPhase = useMemo(() => {
    if (sortedPhases.length === 0) return null;
    const today = todayInTimezone(timezone);
    const byDate = sortedPhases.find((phase) => {
      if (!phase.start_date || !phase.end_date) return false;
      const start = toDateTime(phase.start_date, timezone).startOf('day');
      const end = toDateTime(phase.end_date, timezone).startOf('day');
      if (!start.isValid || !end.isValid) return false;
      return start <= today && today <= end;
    });
    return byDate ?? sortedPhases.find(phase => phase.status === 'ACTIVE') ?? sortedPhases[0];
  }, [sortedPhases, timezone]);

  const milestonesByPhaseId = useMemo(() => {
    const map: Record<string, Milestone[]> = {};
    milestones.forEach((milestone) => {
      if (!map[milestone.phase_id]) {
        map[milestone.phase_id] = [];
      }
      map[milestone.phase_id].push(milestone);
    });
    Object.keys(map).forEach((phaseId) => {
      map[phaseId] = map[phaseId].sort((a, b) => a.order_in_phase - b.order_in_phase);
    });
    return map;
  }, [milestones]);

  const tasksByPhaseId = useMemo(() => {
    const map: Record<string, Task[]> = {};
    tasks.forEach((task) => {
      const phaseId = task.phase_id ?? 'unassigned';
      if (!map[phaseId]) {
        map[phaseId] = [];
      }
      map[phaseId].push(task);
    });
    return map;
  }, [tasks]);

  const phaseRows = useMemo(() => {
    const rows = sortedPhases.map((phase) => ({
      id: phase.id,
      name: phase.name,
      status: phase.status,
      start_date: phase.start_date,
      end_date: phase.end_date,
      tasks: tasksByPhaseId[phase.id] ?? [],
      taskCounts: {
        total: phase.total_tasks,
        done: phase.completed_tasks,
        inProgress: phase.in_progress_tasks,
      },
    }));
    if (tasksByPhaseId.unassigned && tasksByPhaseId.unassigned.length > 0) {
      rows.push({
        id: 'unassigned',
        name: '未割当',
        status: 'ACTIVE',
        start_date: undefined,
        end_date: undefined,
        tasks: tasksByPhaseId.unassigned,
        taskCounts: {
          total: tasksByPhaseId.unassigned.length,
          done: tasksByPhaseId.unassigned.filter(task => task.status === 'DONE').length,
          inProgress: tasksByPhaseId.unassigned.filter(task => task.status === 'IN_PROGRESS').length,
        },
      });
    }
    return rows;
  }, [sortedPhases, tasksByPhaseId]);

  const assignmentIdsByTaskId = useMemo(() => {
    const map = new Map<string, string[]>();
    assignments.forEach((assignment) => {
      if (!assignment.assignee_id) return;
      if (!map.has(assignment.task_id)) {
        map.set(assignment.task_id, []);
      }
      map.get(assignment.task_id)!.push(assignment.assignee_id);
    });
    return map;
  }, [assignments]);

  const workloadByPhaseId = useMemo(() => {
    const matrix: Record<string, Record<string, number>> = {};
    phaseRows.forEach((phase) => {
      const row: Record<string, number> = {};
      phase.tasks.forEach((task) => {
        const minutes = task.estimated_minutes ?? 0;
        if (minutes <= 0) return;
        const assignees = assignmentIdsByTaskId.get(task.id) ?? [];
        assignees.forEach((assigneeId) => {
          row[assigneeId] = (row[assigneeId] ?? 0) + minutes;
        });
      });
      matrix[phase.id] = row;
    });
    return matrix;
  }, [assignmentIdsByTaskId, phaseRows]);

  const memberStatsById = useMemo(() => {
    const stats: Record<string, { total: number; done: number; inProgress: number; weeklyMinutes: number }> = {};
    const taskMap = new Map(tasks.map(task => [task.id, task]));

    // Calculate this week's range (Monday to Sunday)
    const today = todayInTimezone(timezone);
    const dayOfWeek = today.weekday; // 1 = Monday, 7 = Sunday
    const weekStart = today.minus({ days: dayOfWeek - 1 }).startOf('day');
    const weekEnd = weekStart.plus({ days: 6 }).endOf('day');

    assignments.forEach((assignment) => {
      const task = taskMap.get(assignment.task_id);
      if (!task) return;
      const key = assignment.assignee_id;
      if (!stats[key]) {
        stats[key] = { total: 0, done: 0, inProgress: 0, weeklyMinutes: 0 };
      }
      stats[key].total += 1;
      if (task.status === 'DONE') stats[key].done += 1;
      if (task.status === 'IN_PROGRESS') stats[key].inProgress += 1;

      // Skip DONE tasks for workload calculation
      if (task.status === 'DONE') return;

      const estimatedMinutes = task.estimated_minutes ?? 0;
      if (estimatedMinutes <= 0) return;

      const taskStart = task.start_not_before ? toDateTime(task.start_not_before, timezone).startOf('day') : null;
      const taskDue = task.due_date ? toDateTime(task.due_date, timezone).endOf('day') : null;

      // If both dates are set, calculate weekly workload based on task duration
      if (taskStart && taskDue && taskStart.isValid && taskDue.isValid && taskDue >= taskStart) {
        // Check if task overlaps with this week
        const overlapStart = taskStart > weekStart ? taskStart : weekStart;
        const overlapEnd = taskDue < weekEnd ? taskDue : weekEnd;

        if (overlapStart <= overlapEnd) {
          // Task overlaps with this week - calculate proportional workload
          const taskDurationDays = Math.max(1, Math.ceil(taskDue.diff(taskStart, 'days').days));
          const taskDurationWeeks = Math.max(1, taskDurationDays / 7);
          const weeklyWorkload = estimatedMinutes / taskDurationWeeks;
          stats[key].weeklyMinutes += weeklyWorkload;
        }
        // If no overlap, don't add to this week's workload
      } else {
        // No valid date range - assume all workload falls on this week
        stats[key].weeklyMinutes += estimatedMinutes;
      }
    });
    return stats;
  }, [assignments, tasks, timezone]);

  const STATUS_ORDER: Record<string, number> = { IN_PROGRESS: 0, TODO: 1, WAITING: 2, DONE: 3 };

  const tasksByMemberId = useMemo(() => {
    const map: Record<string, Task[]> = {};
    const taskMap = new Map(tasks.map(t => [t.id, t]));
    const parentTaskIds = new Set(tasks.filter(t => t.parent_id).map(t => t.parent_id as string));
    assignments.forEach((a) => {
      if (!a.assignee_id) return;
      const task = taskMap.get(a.task_id);
      if (!task || parentTaskIds.has(task.id)) return;
      if (!map[a.assignee_id]) map[a.assignee_id] = [];
      map[a.assignee_id].push(task);
    });
    // Sort: IN_PROGRESS → TODO → WAITING → DONE
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9));
    }
    return map;
  }, [assignments, tasks]);

  const kpiMetrics = useMemo(
    () => project?.kpi_config?.metrics ?? [],
    [project]
  );

  const priorityTasks = useMemo(() => {
    // 子タスクを持つタスクID（親タスク）を特定
    const parentTaskIds = new Set(
      tasks.filter(t => t.parent_id).map(t => t.parent_id as string)
    );
    // 親タスクを除外し、DONEでないタスクのみをフィルタリング（ダッシュボードと同じ仕様）
    const openLeafTasks = tasks.filter(
      task => task.status !== 'DONE' && !parentTaskIds.has(task.id)
    );
    return [...openLeafTasks].sort((a, b) => {
      const aDue = a.due_date ? toDateTime(a.due_date, timezone).toMillis() : Number.POSITIVE_INFINITY;
      const bDue = b.due_date ? toDateTime(b.due_date, timezone).toMillis() : Number.POSITIVE_INFINITY;
      if (aDue !== bDue) return aDue - bDue;
      const urgencyGap = (PRIORITY_RANK[a.urgency] ?? 99) - (PRIORITY_RANK[b.urgency] ?? 99);
      if (urgencyGap !== 0) return urgencyGap;
      const importanceGap = (PRIORITY_RANK[a.importance] ?? 99) - (PRIORITY_RANK[b.importance] ?? 99);
      if (importanceGap !== 0) return importanceGap;
      return a.title.localeCompare(b.title);
    }).slice(0, 5);
  }, [tasks, timezone]);

  const activityFeed = useMemo(() => {
    const items: { id: string; type: string; title: string; detail?: string; timestamp: string; checkin?: CheckinV2 }[] = [];
    tasks.forEach((task) => {
      items.push({
        id: `task-${task.id}`,
        type: task.status === 'DONE' ? 'タスク完了' : 'タスク更新',
        title: task.title,
        detail: STATUS_LABELS[task.status],
        timestamp: task.updated_at,
      });
    });
    checkins.forEach((checkin) => {
      items.push({
        id: `checkin-${checkin.id}`,
        type: 'チェックイン',
        title: memberLabelById[checkin.member_user_id] || checkin.member_user_id,
        detail: checkin.raw_text,
        timestamp: checkin.created_at,
        checkin,
      });
    });
    blockers.forEach((blocker) => {
      items.push({
        id: `blocker-${blocker.id}`,
        type: 'ブロッカー',
        title: taskTitleById.get(blocker.task_id) || 'タスク',
        detail: blocker.reason,
        timestamp: blocker.created_at,
      });
    });
    return items
      .filter(item => item.timestamp)
      .sort((a, b) => toDateTime(b.timestamp, timezone).toMillis() - toDateTime(a.timestamp, timezone).toMillis())
      .slice(0, 10);
  }, [blockers, checkins, memberLabelById, taskTitleById, tasks, timezone]);

  const handleDeleteCheckin = async (checkinId: string) => {
    if (!projectId) return;
    if (!confirm('このチェックインを削除しますか？')) return;
    try {
      await projectsApi.deleteCheckinV2(projectId, checkinId);
      setCheckins(prev => prev.filter(c => c.id !== checkinId));
    } catch (err) {
      console.error('Failed to delete checkin:', err);
      alert('チェックインの削除に失敗しました');
    }
  };

  const handleSetCurrentPhase = async (phaseId: string) => {
    if (!projectId) return;
    try {
      await phasesApi.setCurrent(phaseId);
      await refreshPhases();
    } catch (err) {
      console.error('Failed to set current phase:', err);
      alert('現在フェーズの設定に失敗しました');
    }
  };

  const handleGenerateTasksFromPhase = (phaseId: string) => {
    const phase = phases?.find(p => p.id === phaseId);
    if (!phase) return;

    const draftCard: DraftCardData = {
      type: 'phase_tasks',
      title: 'フェーズからタスク生成',
      info: [
        { label: 'フェーズ', value: phase.name },
        { label: 'フェーズID', value: phaseId },
        ...(phase.description ? [{ label: '説明', value: phase.description }] : []),
      ],
      placeholder: '例: テスト作成も含めて、担当者は適切に割り当てて',
      promptTemplate: `フェーズ「${phase.name}」(ID: ${phaseId}) からタスクを生成して。

追加の指示があれば以下に記入:
{instruction}`,
    };
    const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
    window.dispatchEvent(event);
  };

  const getPhaseRangeLabel = (phase: {
    start_date?: string;
    end_date?: string;
  }) => {
    if (!phase.start_date || !phase.end_date) {
      return '期間未設定';
    }
    return `${formatShortDate(phase.start_date)} - ${formatShortDate(phase.end_date)}`;
  };

  const getPhaseRemainingDays = (phase: { start_date?: string; end_date?: string }) => {
    if (!phase.start_date || !phase.end_date) return null;
    const startDate = toDateTime(phase.start_date, timezone).startOf('day');
    const endDate = toDateTime(phase.end_date, timezone).startOf('day');
    if (!startDate.isValid || !endDate.isValid) return null;
    const today = todayInTimezone(timezone);
    const start = startDate > today ? startDate : today;
    if (endDate < start) return 0;
    const diff = endDate.diff(start, 'days').days;
    return Math.max(0, Math.ceil(diff) + 1);
  };

  const getPhaseCapacityMinutes = (phase: { start_date?: string; end_date?: string }, member: ProjectMember) => {
    const capacityHours = member.capacity_hours;
    if (capacityHours == null) return null;
    const remainingDays = getPhaseRemainingDays(phase);
    if (remainingDays == null) return null;
    const weeks = remainingDays / 7;
    return Math.max(0, Math.round(capacityHours * 60 * weeks));
  };

  const handleGeneratePhases = () => {
    if (!projectId || !project) return;

    const draftCard: DraftCardData = {
      type: 'phase',
      title: 'フェーズ生成',
      info: [
        { label: 'プロジェクト', value: project.name },
        { label: 'プロジェクトID', value: projectId },
      ],
      placeholder: '例: MVP優先、フェーズは3〜5件に絞る',
      promptTemplate: `プロジェクト「${project.name}」(ID: ${projectId}) のフェーズを作成して。

追加の指示があれば以下に記入:
{instruction}`,
    };

    const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
    window.dispatchEvent(event);
  };

  const handleCapacityDraftChange = (memberId: string, value: string) => {
    setCapacityDrafts((prev) => ({ ...prev, [memberId]: value }));
  };

  const handleCapacitySave = async (member: ProjectMember) => {
    if (!projectId) return;
    const raw = capacityDrafts[member.id];
    const trimmed = raw?.trim() ?? '';
    const parsed = trimmed === '' ? null : Number(trimmed);
    if (trimmed !== '' && !Number.isFinite(parsed)) {
      alert('数値を入力してください。');
      setEditingCapacityId(null);
      return;
    }
    if (trimmed === '' && member.capacity_hours == null) {
      setEditingCapacityId(null);
      return;
    }
    if (trimmed !== '' && parsed === member.capacity_hours) {
      setEditingCapacityId(null);
      return;
    }
    setCapacityActionId(member.id);
    try {
      await projectsApi.updateMember(projectId, member.id, {
        capacity_hours: parsed ?? undefined,
      });
      const membersData = await projectsApi.listMembers(projectId);
      setMembers(membersData);
    } catch (err) {
      console.error('Failed to update capacity:', err);
      alert('基本工数の更新に失敗しました。');
    } finally {
      setCapacityActionId(null);
      setEditingCapacityId(null);
    }
  };

  const handleCapacityCancel = (member: ProjectMember) => {
    setCapacityDrafts((prev) => ({
      ...prev,
      [member.id]: member.capacity_hours != null ? String(member.capacity_hours) : '',
    }));
    setEditingCapacityId(null);
  };

  const handlePhaseBufferDraftChange = (phaseId: string, value: string) => {
    setPhaseBufferDrafts((prev) => ({ ...prev, [phaseId]: value }));
  };

  const handlePhaseBufferSave = async (phase: PhaseWithTaskCount) => {
    if (!projectId) return;
    const raw = phaseBufferDrafts[phase.id];
    const trimmed = raw?.trim() ?? '';
    if (trimmed !== '' && !Number.isFinite(Number(trimmed))) {
      alert('数値を入力してください。');
      return;
    }
    const minutes = trimmed === '' ? 0 : Math.max(0, Math.round(Number(trimmed) * 60));
    if ((phase.fixed_buffer_minutes ?? 0) === minutes) return;

    setPhaseBufferActionId(phase.id);
    try {
      await phasesApi.update(phase.id, { fixed_buffer_minutes: minutes });
      await refreshPhases();
    } catch (err) {
      console.error('Failed to update fixed buffer:', err);
      alert('固定バッファの更新に失敗しました。');
    } finally {
      setPhaseBufferActionId(null);
    }
  };

  // Phase edit/delete handlers
  const handleStartPhaseEdit = (phase: PhaseWithTaskCount) => {
    setEditingPhaseId(phase.id);
    setEditPhaseName(phase.name);
    setEditPhaseDescription(phase.description || '');
  };

  const handleCancelPhaseEdit = () => {
    setEditingPhaseId(null);
    setEditPhaseName('');
    setEditPhaseDescription('');
  };

  const handlePhaseUpdate = async () => {
    if (!editingPhaseId || !editPhaseName.trim()) return;
    try {
      await phasesApi.update(editingPhaseId, {
        name: editPhaseName.trim(),
        description: editPhaseDescription.trim() || undefined,
      });
      await refreshPhases();
      handleCancelPhaseEdit();
    } catch (err) {
      console.error('Failed to update phase:', err);
      alert('フェーズの更新に失敗しました。');
    }
  };

  const handleDeletePhase = async (phaseId: string) => {
    if (!confirm('このフェーズを削除しますか？')) return;
    try {
      await phasesApi.delete(phaseId);
      await refreshPhases();
    } catch (err) {
      console.error('Failed to delete phase:', err);
      alert('フェーズの削除に失敗しました。');
    }
  };

  // Milestone edit/add/delete handlers
  const handleStartMilestoneEdit = (milestone: Milestone) => {
    setEditingMilestoneId(milestone.id);
    setEditMilestoneTitle(milestone.title);
    setEditMilestoneDescription(milestone.description || '');
    setEditMilestoneDueDate(milestone.due_date ? toDateKey(milestone.due_date, timezone) : '');
  };

  const handleCancelMilestoneEdit = () => {
    setEditingMilestoneId(null);
    setEditMilestoneTitle('');
    setEditMilestoneDescription('');
    setEditMilestoneDueDate('');
  };

  const handleMilestoneUpdate = async () => {
    if (!editingMilestoneId || !editMilestoneTitle.trim()) return;
    try {
      await milestonesApi.update(editingMilestoneId, {
        title: editMilestoneTitle.trim(),
        description: editMilestoneDescription.trim() || undefined,
        due_date: editMilestoneDueDate || undefined,
      });
      await refreshMilestones();
      handleCancelMilestoneEdit();
    } catch (err) {
      console.error('Failed to update milestone:', err);
      alert('マイルストーンの更新に失敗しました。');
    }
  };

  const handleDeleteMilestone = async (milestoneId: string) => {
    if (!confirm('このマイルストーンを削除しますか？')) return;
    try {
      await milestonesApi.delete(milestoneId);
      await refreshMilestones();
    } catch (err) {
      console.error('Failed to delete milestone:', err);
      alert('マイルストーンの削除に失敗しました。');
    }
  };

  const handleStartAddMilestone = (phaseId: string) => {
    setAddingMilestonePhaseId(phaseId);
    setNewMilestoneTitle('');
    setNewMilestoneDescription('');
    setNewMilestoneDueDate('');
  };

  const handleCancelAddMilestone = () => {
    setAddingMilestonePhaseId(null);
    setNewMilestoneTitle('');
    setNewMilestoneDescription('');
    setNewMilestoneDueDate('');
  };

  const handleCreateMilestone = async (phaseId: string) => {
    if (!projectId || !newMilestoneTitle.trim()) return;
    try {
      const phaseMilestones = milestonesByPhaseId[phaseId] || [];
      await milestonesApi.create({
        project_id: projectId,
        phase_id: phaseId,
        title: newMilestoneTitle.trim(),
        description: newMilestoneDescription.trim() || undefined,
        due_date: newMilestoneDueDate || undefined,
        order_in_phase: phaseMilestones.length + 1,
      });
      await refreshMilestones();
      handleCancelAddMilestone();
    } catch (err) {
      console.error('Failed to create milestone:', err);
      alert('マイルストーンの作成に失敗しました。');
    }
  };

  const handleInvite = async () => {
    if (!projectId) return;
    const value = inviteValue.trim();
    if (!value) return;
    setIsInviting(true);
    try {
      if (inviteMode === 'email') {
        await projectsApi.createInvitation(projectId, { email: value });
      } else {
        await projectsApi.addMember(projectId, { member_user_id: value });
      }
      const [membersData, invitationsData] = await Promise.all([
        projectsApi.listMembers(projectId),
        projectsApi.listInvitations(projectId),
      ]);
      setMembers(membersData);
      setInvitations(invitationsData);
      setInviteValue('');
    } catch (err) {
      console.error('Failed to invite member:', err);
      alert('メンバー追加に失敗しました。');
    } finally {
      setIsInviting(false);
    }
  };

  const handleCopyInviteLink = async (token: string, email?: string) => {
    const emailParam = email ? `&email=${encodeURIComponent(email)}` : '';
    const link = `${window.location.origin}/invite/accept?token=${encodeURIComponent(token)}${emailParam}`;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(link);
        return;
      } catch (err) {
        console.error('Clipboard write failed:', err);
      }
    }
    try {
      const textarea = document.createElement('textarea');
      textarea.value = link;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    } catch (err) {
      console.error('Fallback copy failed:', err);
    }
  };

  const handleRevokeInvitation = async (invitation: ProjectInvitation) => {
    if (!projectId) return;
    setInvitationActionId(invitation.id);
    try {
      await projectsApi.updateInvitation(projectId, invitation.id, { status: 'REVOKED' });
      const invitationsData = await projectsApi.listInvitations(projectId);
      setInvitations(invitationsData);
    } catch (err) {
      console.error('Failed to revoke invitation:', err);
      alert('招待の取消に失敗しました。');
    } finally {
      setInvitationActionId(null);
    }
  };

  const handleMemberRoleChange = async (memberId: string, role: ProjectMember['role']) => {
    if (!projectId) return;
    setMemberActionId(memberId);
    try {
      await projectsApi.updateMember(projectId, memberId, { role });
      const membersData = await projectsApi.listMembers(projectId);
      setMembers(membersData);
    } catch (err) {
      console.error('Failed to update member role:', err);
      alert('ロールの更新に失敗しました。');
    } finally {
      setMemberActionId(null);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (!projectId) return;
    setMemberActionId(memberId);
    try {
      await projectsApi.removeMember(projectId, memberId);
      const membersData = await projectsApi.listMembers(projectId);
      setMembers(membersData);
    } catch (err) {
      console.error('Failed to remove member:', err);
      alert('メンバーの削除に失敗しました。');
    } finally {
      setMemberActionId(null);
    }
  };

  const handleAssignMultiple = async (taskId: string, memberUserIds: string[]) => {
    if (!projectId) return;
    try {
      if (memberUserIds.length > 0) {
        const newAssignments = await tasksApi.assignTaskMultiple(taskId, { assignee_ids: memberUserIds });
        setAssignments((prev) => {
          const filtered = prev.filter((item) => item.task_id !== taskId);
          return [...filtered, ...newAssignments];
        });
      } else {
        await tasksApi.unassignTask(taskId);
        setAssignments((prev) => prev.filter((item) => item.task_id !== taskId));
      }
    } catch (err) {
      console.error('Failed to update assignment:', err);
      alert('担当者の更新に失敗しました。');
    }
  };

  // Unified task modal hook (placed after memberOptions/handleAssignMultiple)
  const taskModal = useTaskModal({
    tasks,
    onRefetch: refetchTasks,
    projectName: project?.name,
    getPhaseName: (phaseId) => phases.find(p => p.id === phaseId)?.name,
    defaultTaskData: { project_id: projectId },
    memberOptions,
    taskAssignments: assignments,
    onAssigneeChange: handleAssignMultiple,
  });

  const handleCheckCompletion = async (taskId: string) => {
    try {
      await tasksApi.checkCompletion(taskId);
      refetchTasks();
      // Refresh assignments to update check status
      if (projectId) {
        const assignmentsData = await projectsApi.listAssignments(projectId);
        setAssignments(Array.isArray(assignmentsData) ? assignmentsData : []);
      }
    } catch {
      alert('確認の切り替えに失敗しました');
    }
  };

  const handleOpenCreateTask = (phaseId: string | null) => {
    taskModal.openCreateForm({
      project_id: projectId,
      phase_id: phaseId ?? undefined,
    });
  };

  // Current user's role in this project
  const currentUserMember = members.find((m) => m.member_user_id === currentUser?.id);
  const canDeleteProject = currentUserMember?.role === 'OWNER' || currentUserMember?.role === 'ADMIN';
  const canDeleteAnyCheckin = canDeleteProject;

  const handleOpenProjectModal = () => {
    setIsProjectModalOpen(true);
  };

  const handleCloseProjectModal = () => {
    setIsProjectModalOpen(false);
  };

  const handleProjectUpdate = () => {
    refetchProject();
  };

  const handleOpenDeleteConfirm = () => {
    setDeleteConfirmText('');
    setIsDeleteConfirmOpen(true);
  };

  const handleCancelDelete = () => {
    setIsDeleteConfirmOpen(false);
    setDeleteConfirmText('');
  };

  const handleDeleteProject = async () => {
    if (!projectId || deleteConfirmText !== project?.name) return;
    setIsDeletingProject(true);
    try {
      await projectsApi.delete(projectId);
      navigate('/projects');
    } catch (err: unknown) {
      console.error('Failed to delete project:', err);
      const errorMessage = err instanceof Error ? err.message : '';
      if (errorMessage.includes('403') || errorMessage.includes('Forbidden')) {
        alert('プロジェクトの削除権限がありません。オーナーまたは管理者のみが削除できます。');
      } else {
        alert('プロジェクトの削除に失敗しました。');
      }
    } finally {
      setIsDeletingProject(false);
    }
  };

  if (error) {
    return (
      <div className="project-v2-page">
        <div className="project-v2-panel">
          <p className="project-v2-error">{error}</p>
          <button className="project-v2-secondary" onClick={() => navigate('/projects')}>
            プロジェクト一覧へ戻る
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="project-v2-page">
        <div className="project-v2-panel">
          <p>読み込み中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="project-v2-page">
      <header className="project-v2-header">
        <div className="project-v2-header-top">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem' }}>
              <button className="project-v2-secondary" onClick={() => navigate('/projects')}>
                プロジェクト一覧
              </button>
              {project?.parent_project_id && (
                <>
                  <span style={{ color: 'var(--text-muted, #999)' }}>/</span>
                  <button
                    className="project-v2-secondary"
                    onClick={() => navigate(`/projects/${project.parent_project_id}/v2`)}
                  >
                    親プロジェクト
                  </button>
                </>
              )}
            </div>
            <h1 className="project-v2-title">
              {project?.name || 'プロジェクト'}
              <span className={`project-v2-visibility-badge ${project?.visibility === 'TEAM' ? 'team' : 'private'}`}>
                {project?.visibility === 'TEAM' ? <><FaUsers /> チーム</> : <><FaLock /> 個人</>}
              </span>
            </h1>
          </div>
          <div className="project-v2-header-actions">
            <TourHelpButton onClick={tour.startTour} />
            <button
              className="project-v2-icon-btn"
              onClick={handleOpenProjectModal}
              title="プロジェクトを編集"
            >
              <FaEdit />
            </button>
            {canDeleteProject && (
              <button
                className="project-v2-icon-btn danger"
                onClick={handleOpenDeleteConfirm}
                title="プロジェクトを削除"
              >
                <FaTrash />
              </button>
            )}
          </div>
        </div>
        <div className="project-v2-progress">
          <div className="project-v2-progress-stats-row">
            <div className="project-v2-progress-chip">
              <span className="project-v2-progress-chip-value">{project?.completed_tasks ?? 0}/{project?.total_tasks ?? 0}</span>
              <span className="project-v2-progress-chip-label">完了 ({completionRate}%)</span>
            </div>
            <div className="project-v2-progress-chip">
              <span className="project-v2-progress-chip-value">{inProgressCount}</span>
              <span className="project-v2-progress-chip-label">進行中</span>
            </div>
            <div className="project-v2-progress-chip">
              <span className="project-v2-progress-chip-value">{waitingCount}</span>
              <span className="project-v2-progress-chip-label">待機</span>
            </div>
          </div>
          <div className="project-v2-progress-bar">
            <div
              className="project-v2-progress-fill"
              style={{ width: `${completionRate}%` }}
            />
          </div>
        </div>
        {currentPhase && (
          <div className="project-v2-current-phase">
            <span className="project-v2-current-phase-icon">📍</span>
            現在フェーズ: {currentPhase.name}
          </div>
        )}
      </header>

      {(overdueTasks.length > 0 || blockedDependencyCount > 0) && (
        <div className="project-v2-alert">
          <div className="project-v2-alert-icon">!</div>
          <div>
            <div className="project-v2-alert-title">
              注意が必要なタスクがあります
            </div>
            <div className="project-v2-alert-text">
              期限超過 {overdueTasks.length}件 / 依存ブロック {blockedDependencyCount}件
            </div>
          </div>
        </div>
      )}

      <nav className="project-v2-tabs">
        {(Object.keys(TAB_LABELS) as TabId[]).map((tabId) => {
          if (tabId === 'team' && project?.visibility !== 'TEAM') return null;
          return (
            <button
              key={tabId}
              type="button"
              className={`project-v2-tab ${activeTab === tabId ? 'is-active' : ''}`}
              onClick={() => setActiveTab(tabId)}
            >
              <span className="project-v2-tab-icon">{TAB_ICONS[tabId]}</span>
              <span>{TAB_LABELS[tabId]}</span>
            </button>
          );
        })}
      </nav>

      <section className="project-v2-panel">
        {activeTab === 'dashboard' && (
          <div className="project-v2-section project-v2-dashboard">
            <div className="project-v2-kpi-grid">
              {kpiMetrics.length === 0 ? (
                <div className="project-v2-kpi-card">
                  <div className="project-v2-kpi-label">KPI</div>
                  <div className="project-v2-muted">KPI設定がありません。</div>
                </div>
              ) : (
                kpiMetrics.map((metric) => {
                  const progress = computeKpiProgress(metric);
                  const current = metric.current ?? '-';
                  const target = metric.target ?? '-';
                  const unit = metric.unit ?? '';
                  return (
                    <div key={metric.key} className="project-v2-kpi-card">
                      <div className="project-v2-kpi-label">{metric.label}</div>
                      <div className="project-v2-kpi-value">{current}{unit}</div>
                      <div className="project-v2-kpi-target">目標: {target}{unit}</div>
                      <div className="project-v2-kpi-progress">
                        <div
                          className="project-v2-kpi-progress-fill"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {projectId && (
              <ChildProjectsSection
                projectId={projectId}
                projectName={project?.name || ''}
                onTaskClick={(taskId) => taskModal.openTaskDetailById(taskId)}
              />
            )}

            <div className="project-v2-dashboard-grid">
              <div className="project-v2-dashboard-main">
                {/* TODO: 将来実装 - AI提案機能
                <div className="project-v2-card">
                  <div className="project-v2-card-header">
                    <h3>AI提案</h3>
                  </div>
                  <div className="project-v2-ai-suggestion">
                    <div className="project-v2-ai-header">
                      <span className="project-v2-ai-badge">ベースライン更新</span>
                      <span className="project-v2-ai-title">ベースライン再生成の提案</span>
                    </div>
                    <div className="project-v2-ai-body">
                      Phase 2のバッファ残量が低下しています。start_not_beforeは固定したまま、計画ベースラインを再生成して差分を確認します。
                    </div>
                    <div className="project-v2-ai-actions">
                      <button className="project-v2-button primary">ベースラインを生成</button>
                      <button className="project-v2-button ghost">差分をプレビュー</button>
                    </div>
                  </div>
                  <div className="project-v2-ai-suggestion">
                    <div className="project-v2-ai-header">
                      <span className="project-v2-ai-badge">ボトルネック</span>
                      <span className="project-v2-ai-title">依存タスクの遅延検知</span>
                    </div>
                    <div className="project-v2-ai-body">
                      依存ブロック {blockedDependencyCount}件。担当の負荷を分散し、クリティカルチェーンの遅延リスクを抑えましょう。
                    </div>
                    <div className="project-v2-ai-actions">
                      <button className="project-v2-button primary">再割り当て</button>
                      <button className="project-v2-button ghost">詳細を見る</button>
                    </div>
                  </div>
                </div>
                */}

                <div className="project-v2-card project-v2-priority-tasks">
                  <div className="project-v2-card-header">
                    <h3>今日の優先タスク</h3>
                  </div>
                  {priorityTasks.length === 0 ? (
                    <p className="project-v2-muted project-v2-empty-state">優先タスクはありません。</p>
                  ) : (
                    <>
                      {/* NEXT ACTION - 最初のタスクを強調表示 */}
                      {(() => {
                        const focusTask = priorityTasks[0];
                        const isDone = focusTask.status === 'DONE';
                        const progress = focusTask.progress ?? (isDone ? 100 : 0);
                        const parentTask = focusTask.parent_id ? tasks.find(t => t.id === focusTask.parent_id) : null;
                        const assigneeLabel = assigneeByTaskId[focusTask.id];
                        const assigneeInitial = assigneeLabel ? assigneeLabel.trim().charAt(0) : null;
                        const formatTime = (mins: number) => {
                          if (mins >= 60) {
                            const h = Math.floor(mins / 60);
                            const m = mins % 60;
                            return m > 0 ? `${h}h ${m}m` : `${h}h`;
                          }
                          return `${mins}m`;
                        };

                        return (
                          <div className="project-v2-focus-section">
                            <div className="project-v2-focus-label">NEXT ACTION</div>
                            <div
                              className="project-v2-focus-item"
                              onClick={() => taskModal.openTaskDetail(focusTask)}
                            >
                              {/* 進捗バー背景 */}
                              <div
                                className="project-v2-focus-progress"
                                style={{ width: `${progress}%` }}
                              />
                              {/* チェックボックス */}
                              <div
                                className={`project-v2-focus-checkbox ${isDone ? 'checked' : ''}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  updateTask(focusTask.id, { status: isDone ? 'TODO' : 'DONE' });
                                }}
                              />
                              <div className="project-v2-focus-content">
                                <div className={`project-v2-focus-title ${isDone ? 'done' : ''}`}>
                                  {focusTask.title}
                                </div>
                                {parentTask && (
                                  <div className="project-v2-focus-parent">↳ {parentTask.title}</div>
                                )}
                                <div className="project-v2-focus-meta">
                                  {focusTask.estimated_minutes ? formatTime(focusTask.estimated_minutes) : '0m'}
                                  {' / 目標100%'}
                                </div>
                              </div>
                              {/* 担当者アイコン */}
                              {assigneeInitial && (
                                <div className="project-v2-focus-assignee" title={assigneeLabel}>
                                  {assigneeInitial}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })()}

                      {/* 残りのタスクリスト */}
                      {priorityTasks.length > 1 && (
                        <div className="project-v2-task-list">
                          {priorityTasks.slice(1).map((task) => {
                            const isDone = task.status === 'DONE';
                            const progress = task.progress ?? (isDone ? 100 : 0);
                            const parentTask = task.parent_id ? tasks.find(t => t.id === task.parent_id) : null;
                            const taskAssigneeLabel = assigneeByTaskId[task.id];
                            const taskAssigneeInitial = taskAssigneeLabel ? taskAssigneeLabel.trim().charAt(0) : null;
                            const dlStatus = getDeadlineStatus(task.due_date, task.status, timezone);
                            const formatTime = (mins: number) => {
                              if (mins >= 60) {
                                const h = Math.floor(mins / 60);
                                const m = mins % 60;
                                return m > 0 ? `${h}h ${m}m` : `${h}h`;
                              }
                              return `${mins}m`;
                            };

                            return (
                              <div
                                key={task.id}
                                className={`project-v2-task-item ${isDone ? 'done' : ''} ${dlStatus ? `deadline-${dlStatus}` : ''}`}
                                onClick={() => taskModal.openTaskDetail(task)}
                              >
                                {/* 進捗バー */}
                                <div
                                  className="project-v2-task-progress-bar"
                                  style={{ width: `${progress}%` }}
                                />
                                {/* チェックボックス */}
                                <div
                                  className={`project-v2-task-checkbox ${isDone ? 'checked' : ''}`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    updateTask(task.id, { status: isDone ? 'TODO' : 'DONE' });
                                  }}
                                />
                                <div className="project-v2-task-content">
                                  <div className={`project-v2-task-title ${isDone ? 'done' : ''}`}>
                                    {task.title}
                                  </div>
                                  {parentTask && (
                                    <div className="project-v2-task-parent">↳ {parentTask.title}</div>
                                  )}
                                </div>
                                <div className="project-v2-task-time">
                                  {task.estimated_minutes ? formatTime(task.estimated_minutes) : '0m'}
                                </div>
                                {/* 担当者アイコン */}
                                {taskAssigneeInitial && (
                                  <div className="project-v2-task-assignee" title={taskAssigneeLabel}>
                                    {taskAssigneeInitial}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className="project-v2-dashboard-side">
                <div className="project-v2-card">
                  <div className="project-v2-card-header">
                    <h3>ブロッカー</h3>
                    <span className="project-v2-badge">{openBlockerCount}</span>
                  </div>
                  {blockers.length === 0 ? (
                    <p className="project-v2-muted">ブロッカーはありません。</p>
                  ) : (
                    <div className="project-v2-blocker-list">
                      {blockers.slice(0, 5).map((blocker) => (
                        <div key={blocker.id} className="project-v2-blocker-item">
                          <div className="project-v2-blocker-title">
                            {taskTitleById.get(blocker.task_id) || 'タスク'}
                          </div>
                          <div className="project-v2-muted">{blocker.reason}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="project-v2-card">
                  <div className="project-v2-card-header">
                    <h3>アクティビティ</h3>
                    <span className="project-v2-badge">{activityFeed.length}</span>
                  </div>
                  {activityFeed.length === 0 ? (
                    <p className="project-v2-muted">最近のアクティビティはありません。</p>
                  ) : (
                    <div className="project-v2-activity-list">
                      {activityFeed.map((item) => (
                        <div key={item.id} className="project-v2-activity-item">
                          <div className="project-v2-activity-content">
                            <div className="project-v2-activity-title">{item.type}</div>
                            <div className="project-v2-muted">{item.title}</div>
                            {item.detail && <div className="project-v2-muted">{item.detail}</div>}
                          </div>
                          <div className="project-v2-activity-actions">
                            <span className="project-v2-muted">
                              {formatShortDate(item.timestamp)}
                            </span>
                            {item.checkin && (canDeleteAnyCheckin || item.checkin.member_user_id === currentUser?.id) && (
                              <button
                                className="project-v2-activity-delete-btn"
                                onClick={() => handleDeleteCheckin(item.checkin!.id)}
                                title="削除"
                              >
                                <FaTrash />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'team' && (
          <div className="project-v2-section">
            <div className="project-v2-team-grid">
              {members.length === 0 ? (
                <div className="project-v2-card">
                  <p className="project-v2-muted">メンバーがまだいません。</p>
                </div>
              ) : (
                members.map((member) => {
                  const stats = memberStatsById[member.member_user_id] ?? {
                    total: 0,
                    done: 0,
                    inProgress: 0,
                    weeklyMinutes: 0,
                  };
                  const capacityMinutes = member.capacity_hours && member.capacity_hours > 0
                    ? member.capacity_hours * 60
                    : null;
                  const loadPercent = capacityMinutes
                    ? Math.round((stats.weeklyMinutes / capacityMinutes) * 100)
                    : null;
                  const cappedPercent = loadPercent ? Math.min(loadPercent, 100) : 0;
                  const loadClass = loadPercent == null
                    ? 'unknown'
                    : loadPercent > 110
                      ? 'over'
                      : loadPercent > 80
                        ? 'warn'
                        : 'ok';
                  const displayName = member.member_display_name || member.member_user_id;
                  const isExpanded = expandedMemberIds.has(member.member_user_id);
                  const memberTasks = tasksByMemberId[member.member_user_id] ?? [];
                  const childProjects = childTasksByMember[member.member_user_id] ?? {};
                  const childProjectEntries = Object.entries(childProjects);
                  const hasChildTasks = childProjectEntries.length > 0;
                  const showGroupLabels = memberTasks.length > 0 && hasChildTasks;
                  return (
                    <div
                      key={member.id}
                      className={`project-v2-team-card${isExpanded ? ' expanded' : ''}`}
                    >
                      <div
                        className="project-v2-team-card-toggle"
                        onClick={() => toggleMemberExpand(member.member_user_id)}
                      >
                        <div className="project-v2-team-header">
                          <div className="project-v2-team-avatar">{getInitial(displayName)}</div>
                          <div style={{ flex: 1 }}>
                            <div className="project-v2-team-name">{displayName}</div>
                            <div className="project-v2-muted">{member.role}</div>
                          </div>
                          <div className={`project-v2-team-chevron${isExpanded ? ' open' : ''}`}>
                            <FaChevronDown />
                          </div>
                        </div>
                        <div className="project-v2-team-stats">
                          <div className="project-v2-team-stat">
                            <div className="project-v2-team-stat-value">{stats.total}</div>
                            <div className="project-v2-team-stat-label">TOTAL</div>
                          </div>
                          <div className="project-v2-team-stat">
                            <div className="project-v2-team-stat-value">{stats.inProgress}</div>
                            <div className="project-v2-team-stat-label">IN PROGRESS</div>
                          </div>
                          <div className="project-v2-team-stat">
                            <div className="project-v2-team-stat-value">{stats.done}</div>
                            <div className="project-v2-team-stat-label">DONE</div>
                          </div>
                        </div>
                        <div className="project-v2-team-workload">
                          <div className="project-v2-muted">
                            今週の負荷 {loadPercent != null ? `${loadPercent}%` : '未設定'}
                          </div>
                          <div className="project-v2-workload-bar">
                            <div
                              className={`project-v2-workload-fill ${loadClass}`}
                              style={{ width: `${cappedPercent}%` }}
                            />
                          </div>
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="project-v2-member-tasks">
                          {memberTasks.length === 0 && !hasChildTasks ? (
                            <p className="project-v2-muted">割り当てられたタスクはありません。</p>
                          ) : (
                            <>
                              {showGroupLabels && (
                                <div className="project-v2-task-group-label">このプロジェクト</div>
                              )}
                              {memberTasks.length > 0 && (
                                <div className="project-v2-task-list">
                                  {memberTasks.map((task) => {
                                    const isDone = task.status === 'DONE';
                                    const progress = task.progress ?? (isDone ? 100 : 0);
                                    const dlStatus = getDeadlineStatus(task.due_date, task.status, timezone);
                                    const est = task.estimated_minutes;
                                    const timeLabel = est
                                      ? est >= 60
                                        ? `${Math.floor(est / 60)}h${est % 60 > 0 ? ` ${est % 60}m` : ''}`
                                        : `${est}m`
                                      : '';
                                    const parentTask = task.parent_id
                                      ? tasks.find(t => t.id === task.parent_id)
                                      : null;
                                    return (
                                      <div
                                        key={task.id}
                                        className={`project-v2-task-item ${isDone ? 'done' : ''} ${dlStatus ? `deadline-${dlStatus}` : ''}`}
                                        onClick={() => taskModal.openTaskDetail(task)}
                                      >
                                        <div
                                          className="project-v2-task-progress-bar"
                                          style={{ width: `${progress}%` }}
                                        />
                                        <div
                                          className={`project-v2-task-checkbox ${isDone ? 'checked' : ''}`}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            updateTask(task.id, { status: isDone ? 'TODO' : 'DONE' });
                                          }}
                                        />
                                        <div className="project-v2-task-content">
                                          <div className={`project-v2-task-title ${isDone ? 'done' : ''}`}>
                                            {task.title}
                                          </div>
                                          {parentTask && (
                                            <div className="project-v2-task-parent">↳ {parentTask.title}</div>
                                          )}
                                          {!parentTask && task.due_date && (
                                            <div className="project-v2-muted">{formatShortDate(task.due_date)}</div>
                                          )}
                                        </div>
                                        {timeLabel && (
                                          <div className="project-v2-task-time">{timeLabel}</div>
                                        )}
                                        <div
                                          className="project-v2-member-task-status"
                                          data-status={task.status}
                                        >
                                          {STATUS_LABELS[task.status]}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                              {childProjectEntries.map(([projectName, cTasks]) => (
                                <CollapsibleChildTaskGroup
                                  key={projectName}
                                  projectName={projectName}
                                  tasks={cTasks}
                                  onTaskClick={(taskId) => taskModal.openTaskDetailById(taskId)}
                                />
                              ))}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            <div className="project-v2-team-panels">
              <div className="project-v2-card">
                <h3>フェーズ別 負荷積み上げ</h3>
                <p className="project-v2-muted">フェーズ期間と現在日付から動的にキャパ算出（週あたり工数）</p>
                {members.length === 0 ? (
                  <p className="project-v2-muted">メンバーを追加すると表示されます。</p>
                ) : isPhasesLoading ? (
                  <p className="project-v2-muted">読み込み中...</p>
                ) : phaseRows.length === 0 ? (
                  <p className="project-v2-muted">フェーズがありません。</p>
                ) : (
                  <div className="project-v2-table-wrap">
                    <table className="project-v2-table">
                      <thead>
                        <tr>
                          <th>フェーズ</th>
                          {members.map((member) => (
                            <th key={member.id}>
                              {member.member_display_name || member.member_user_id}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {phaseRows.map((phase) => (
                          <tr key={phase.id}>
                            <td>
                              <div className="project-v2-list-title">{phase.name}</div>
                              <div className="project-v2-muted">{getPhaseRangeLabel(phase)}</div>
                              <div className="project-v2-muted">
                                完了 {phase.taskCounts.done} / 全体 {phase.taskCounts.total}
                              </div>
                            </td>
                            {members.map((member) => {
                              const memberId = member.member_user_id;
                              const loadMinutes = workloadByPhaseId[phase.id]?.[memberId] ?? 0;
                              const capacityMinutes = getPhaseCapacityMinutes(phase, member);
                              const bufferMinutes = capacityMinutes != null ? capacityMinutes - loadMinutes : null;
                              return (
                                <td key={`${phase.id}-${member.id}`}>
                                  <div className="project-v2-workload-cell">
                                    <div>{formatHours(loadMinutes)}</div>
                                    {capacityMinutes != null ? (
                                      <>
                                        <div className="project-v2-muted">
                                          キャパ {formatHours(capacityMinutes)}
                                        </div>
                                        <div
                                          className={`project-v2-workload-buffer ${bufferMinutes != null && bufferMinutes < 0 ? 'is-negative' : ''}`}
                                        >
                                          バッファ {formatHours(bufferMinutes ?? 0)}
                                        </div>
                                      </>
                                    ) : (
                                      <div className="project-v2-muted">キャパ未設定</div>
                                    )}
                                  </div>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
              <div className="project-v2-card">
                <h3>メンバー管理</h3>
                <div className="project-v2-form-row">
                  <select
                    className="project-v2-select"
                    value={inviteMode}
                    onChange={(e) => setInviteMode(e.target.value as InviteMode)}
                    disabled={isInviting}
                  >
                    <option value="email">Email</option>
                    <option value="user_id">ユーザー検索</option>
                  </select>
                  {inviteMode === 'email' ? (
                    <>
                      <input
                        className="project-v2-input"
                        type="text"
                        placeholder="member@example.com"
                        value={inviteValue}
                        onChange={(e) => setInviteValue(e.target.value)}
                        disabled={isInviting}
                      />
                      <button
                        className="project-v2-button primary"
                        onClick={handleInvite}
                        disabled={!inviteValue.trim() || isInviting}
                      >
                        招待
                      </button>
                    </>
                  ) : (
                    <UserSearchInput
                      placeholder="ユーザー名またはメールで検索..."
                      disabled={isInviting}
                      onSelect={async (selectedUser: UserSearchResult) => {
                        if (!projectId) return;
                        setIsInviting(true);
                        try {
                          await projectsApi.addMember(projectId, {
                            member_user_id: selectedUser.id,
                          });
                          const [membersData, invitationsData] = await Promise.all([
                            projectsApi.listMembers(projectId),
                            projectsApi.listInvitations(projectId),
                          ]);
                          setMembers(membersData);
                          setInvitations(invitationsData);
                        } catch (err) {
                          console.error('Failed to add member:', err);
                          alert('メンバー追加に失敗しました');
                        } finally {
                          setIsInviting(false);
                        }
                      }}
                    />
                  )}
                </div>
                <p className="project-v2-muted">Email招待とユーザー検索で追加を選べます。</p>

                {isCollabLoading ? (
                  <p className="project-v2-muted">読み込み中...</p>
                ) : (
                  <div className="project-v2-list">
                    {members.length === 0 ? (
                      <p className="project-v2-muted">メンバーがまだいません。</p>
                    ) : (
                      members.map((member) => (
                        <div key={member.id} className="project-v2-list-item">
                          <div>
                            <div className="project-v2-list-title">
                              {member.member_display_name || member.member_user_id}
                            </div>
                            <div className="project-v2-muted">{member.member_user_id}</div>
                            <div className="project-v2-inline-field">
                              {editingCapacityId === member.id ? (
                                <>
                                  <label className="project-v2-inline-label" htmlFor={`capacity-${member.id}`}>
                                    基本工数 (h/週)
                                  </label>
                                  <input
                                    id={`capacity-${member.id}`}
                                    className="project-v2-input project-v2-inline-input"
                                    type="number"
                                    min="0"
                                    step="0.5"
                                    value={capacityDrafts[member.id] ?? ''}
                                    onChange={(e) => handleCapacityDraftChange(member.id, e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') handleCapacitySave(member);
                                      if (e.key === 'Escape') handleCapacityCancel(member);
                                    }}
                                    onBlur={() => handleCapacitySave(member)}
                                    disabled={capacityActionId === member.id}
                                    autoFocus
                                  />
                                  {capacityActionId === member.id && (
                                    <span className="project-v2-muted">保存中...</span>
                                  )}
                                </>
                              ) : (
                                <span
                                  className="project-v2-inline-value"
                                  onClick={() => setEditingCapacityId(member.id)}
                                  title="クリックして編集"
                                >
                                  <FaEdit className="project-v2-inline-edit-icon" />
                                  基本工数: {member.capacity_hours != null ? `${member.capacity_hours} h/週` : '未設定'}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="project-v2-actions">
                            <select
                              className="project-v2-select"
                              value={member.role}
                              onChange={(e) => handleMemberRoleChange(member.id, e.target.value as ProjectMember['role'])}
                              disabled={memberActionId === member.id}
                            >
                              <option value="OWNER">OWNER</option>
                              <option value="ADMIN">ADMIN</option>
                              <option value="MEMBER">MEMBER</option>
                            </select>
                            <button
                              className="project-v2-button ghost"
                              onClick={() => handleRemoveMember(member.id)}
                              disabled={memberActionId === member.id}
                            >
                              削除
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {project?.parent_project_id && (
                  <InviteFromParentSection
                    projectId={projectId!}
                    parentProjectId={project.parent_project_id}
                    currentMembers={members}
                    ownerUserId={project.user_id}
                    onMemberAdded={async () => {
                      if (!projectId) return;
                      const membersData = await projectsApi.listMembers(projectId);
                      setMembers(membersData);
                    }}
                  />
                )}

                {pendingInvitations.length > 0 && (
                  <div className="project-v2-subsection">
                    <h4>招待中</h4>
                    <div className="project-v2-list">
                      {pendingInvitations.map((invitation) => (
                        <div key={invitation.id} className="project-v2-list-item">
                          <div>
                            <div className="project-v2-list-title">{invitation.email}</div>
                            <div className="project-v2-muted">{invitation.status}</div>
                            {invitation.token && (
                              <div className="project-v2-muted">{invitation.token}</div>
                            )}
                          </div>
                          <div className="project-v2-actions">
                            {invitation.token && (
                              <button
                                className="project-v2-button"
                                onClick={() => handleCopyInviteLink(invitation.token as string, invitation.email)}
                              >
                                リンクコピー
                              </button>
                            )}
                            <button
                              className="project-v2-button ghost"
                              onClick={() => handleRevokeInvitation(invitation)}
                              disabled={invitationActionId === invitation.id}
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="project-v2-section">
            <div className="project-v2-card">
              <div className="project-v2-card-header">
                <h3>フェーズ & マイルストーン</h3>
              </div>
              <div className="project-v2-phase-generation-group">
                <div className="project-v2-form" style={{ flex: 1, marginBottom: 0 }}>
                  <label className="project-v2-label" htmlFor="phase-instruction">
                    AI指示（フェーズ生成用）
                  </label>
                  <input
                    id="phase-instruction"
                    className="project-v2-input"
                    type="text"
                    placeholder="例: MVP優先、3フェーズで分割"
                    value={phasePlanInstruction}
                    onChange={(e) => setPhasePlanInstruction(e.target.value)}
                  />
                </div>
                <button
                  className="project-v2-button"
                  onClick={handleGeneratePhases}
                  disabled={!project}
                  style={{ alignSelf: 'flex-end', marginBottom: '8px' }}
                >
                  AIでフェーズ生成
                </button>
              </div>
              {isPhasesLoading ? (
                <p className="project-v2-muted">読み込み中...</p>
              ) : sortedPhases.length === 0 ? (
                <p className="project-v2-muted">フェーズがありません。</p>
              ) : (
                <div className="project-v2-timeline">
                  {sortedPhases.map((phase) => {
                    const isCurrent = currentPhase?.id === phase.id;
                    const isCompleted = phase.status === 'COMPLETED';
                    const isEditing = editingPhaseId === phase.id;
                    return (
                      <div
                        key={phase.id}
                        className={`project-v2-timeline-item ${isCurrent ? 'is-current' : ''} ${isCompleted ? 'is-complete' : ''}`}
                      >
                        <div className="project-v2-timeline-card">
                          {isEditing ? (
                            <div className="project-v2-phase-edit-form">
                              <input
                                className="project-v2-input"
                                type="text"
                                value={editPhaseName}
                                onChange={(e) => setEditPhaseName(e.target.value)}
                                placeholder="フェーズ名"
                                autoFocus
                              />
                              <textarea
                                className="project-v2-textarea"
                                value={editPhaseDescription}
                                onChange={(e) => setEditPhaseDescription(e.target.value)}
                                placeholder="説明（任意）"
                                rows={2}
                              />
                              <div className="project-v2-phase-edit-actions">
                                <button
                                  className="project-v2-button"
                                  onClick={handlePhaseUpdate}
                                >
                                  <FaCheck /> 保存
                                </button>
                                <button
                                  className="project-v2-button ghost"
                                  onClick={handleCancelPhaseEdit}
                                >
                                  <FaTimes /> キャンセル
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="project-v2-timeline-title">
                                <span>
                                  {phase.name}
                                  {isCurrent && <span className="project-v2-phase-badge">進行中</span>}
                                </span>
                                <div className="project-v2-phase-actions">
                                  {!isCurrent && (
                                    <button
                                      className="project-v2-phase-set-current-btn"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleSetCurrentPhase(phase.id);
                                      }}
                                      title="このフェーズを現在フェーズに設定"
                                    >
                                      <FaCheckCircle />
                                    </button>
                                  )}
                                  <button
                                    className="project-v2-icon-btn"
                                    onClick={() => handleStartPhaseEdit(phase)}
                                    title="編集"
                                  >
                                    <FaEdit />
                                  </button>
                                  <button
                                    className="project-v2-icon-btn danger"
                                    onClick={() => handleDeletePhase(phase.id)}
                                    title="削除"
                                  >
                                    <FaTrash />
                                  </button>
                                </div>
                              </div>
                              {phase.description && (
                                <div className="project-v2-muted project-v2-phase-description">
                                  {phase.description}
                                </div>
                              )}
                              <div className="project-v2-muted">{getPhaseRangeLabel(phase)}</div>
                              <div className="project-v2-muted">
                                完了 {phase.completed_tasks} / 全体 {phase.total_tasks}
                              </div>
                              <div className="project-v2-inline-field project-v2-phase-buffer">
                                <label className="project-v2-inline-label" htmlFor={`phase-buffer-${phase.id}`}>
                                  固定バッファ (h)
                                </label>
                                <input
                                  id={`phase-buffer-${phase.id}`}
                                  className="project-v2-input"
                                  type="number"
                                  min="0"
                                  step="0.5"
                                  value={phaseBufferDrafts[phase.id] ?? ''}
                                  onChange={(e) => handlePhaseBufferDraftChange(phase.id, e.target.value)}
                                  disabled={phaseBufferActionId === phase.id}
                                />
                                <button
                                  className="project-v2-button"
                                  onClick={() => handlePhaseBufferSave(phase)}
                                  disabled={phaseBufferActionId === phase.id}
                                >
                                  {phaseBufferActionId === phase.id ? '保存中...' : '保存'}
                                </button>
                              </div>
                              <div className="project-v2-milestone-section">
                                <div className="project-v2-milestone-header">
                                  <span className="project-v2-milestone-header-title">マイルストーン</span>
                                  <button
                                    className="project-v2-icon-btn"
                                    onClick={() => handleStartAddMilestone(phase.id)}
                                    title="マイルストーン追加"
                                  >
                                    <FaPlus />
                                  </button>
                                </div>
                                <div className="project-v2-milestone-list">
                                  {isMilestonesLoading ? (
                                    <p className="project-v2-muted">マイルストーン読み込み中...</p>
                                  ) : (milestonesByPhaseId[phase.id] || []).length === 0 ? (
                                    <p className="project-v2-muted">マイルストーンはまだありません。</p>
                                  ) : (
                                    (milestonesByPhaseId[phase.id] || []).map((milestone) => (
                                      <div key={milestone.id} className="project-v2-milestone-item">
                                        {editingMilestoneId === milestone.id ? (
                                          <div className="project-v2-milestone-edit-form">
                                            <input
                                              className="project-v2-input"
                                              type="text"
                                              value={editMilestoneTitle}
                                              onChange={(e) => setEditMilestoneTitle(e.target.value)}
                                              placeholder="マイルストーン名"
                                              autoFocus
                                            />
                                            <input
                                              className="project-v2-input"
                                              type="date"
                                              value={editMilestoneDueDate}
                                              onChange={(e) => setEditMilestoneDueDate(e.target.value)}
                                            />
                                            <textarea
                                              className="project-v2-textarea"
                                              value={editMilestoneDescription}
                                              onChange={(e) => setEditMilestoneDescription(e.target.value)}
                                              placeholder="説明（任意）"
                                              rows={2}
                                            />
                                            <div className="project-v2-milestone-edit-actions">
                                              <button
                                                className="project-v2-button"
                                                onClick={handleMilestoneUpdate}
                                              >
                                                <FaCheck /> 保存
                                              </button>
                                              <button
                                                className="project-v2-button ghost"
                                                onClick={handleCancelMilestoneEdit}
                                              >
                                                <FaTimes /> キャンセル
                                              </button>
                                            </div>
                                          </div>
                                        ) : (
                                          <>
                                            <div className="project-v2-milestone-content">
                                              <div className="project-v2-list-title">{milestone.title}</div>
                                              <div className="project-v2-muted">
                                                {milestone.due_date ? formatShortDate(milestone.due_date) : '期限未設定'}
                                              </div>
                                            </div>
                                            <div className="project-v2-milestone-actions">
                                              <button
                                                className="project-v2-icon-btn"
                                                onClick={() => handleStartMilestoneEdit(milestone)}
                                                title="編集"
                                              >
                                                <FaEdit />
                                              </button>
                                              <button
                                                className="project-v2-icon-btn danger"
                                                onClick={() => handleDeleteMilestone(milestone.id)}
                                                title="削除"
                                              >
                                                <FaTrash />
                                              </button>
                                            </div>
                                          </>
                                        )}
                                      </div>
                                    ))
                                  )}
                                  {addingMilestonePhaseId === phase.id && (
                                    <div className="project-v2-milestone-add-form">
                                      <input
                                        className="project-v2-input"
                                        type="text"
                                        value={newMilestoneTitle}
                                        onChange={(e) => setNewMilestoneTitle(e.target.value)}
                                        placeholder="マイルストーン名"
                                        autoFocus
                                      />
                                      <input
                                        className="project-v2-input"
                                        type="date"
                                        value={newMilestoneDueDate}
                                        onChange={(e) => setNewMilestoneDueDate(e.target.value)}
                                      />
                                      <textarea
                                        className="project-v2-textarea"
                                        value={newMilestoneDescription}
                                        onChange={(e) => setNewMilestoneDescription(e.target.value)}
                                        placeholder="説明（任意）"
                                        rows={2}
                                      />
                                      <div className="project-v2-milestone-edit-actions">
                                        <button
                                          className="project-v2-button"
                                          onClick={() => handleCreateMilestone(phase.id)}
                                        >
                                          <FaCheck /> 作成
                                        </button>
                                        <button
                                          className="project-v2-button ghost"
                                          onClick={handleCancelAddMilestone}
                                        >
                                          <FaTimes /> キャンセル
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                              <button
                                className="project-v2-phase-generate-tasks-btn"
                                onClick={() => handleGenerateTasksFromPhase(phase.id)}
                              >
                                <FaTasks /> タスクを生成
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'board' && (
          <div className="project-v2-section">
            <RecurringTaskList projectId={projectId} />
            <div className="project-v2-card">
              {tasksLoading ? (
                <p className="project-v2-muted">タスクを読み込み中...</p>
              ) : (
                <ProjectTasksView
                  projectId={projectId!}
                  tasks={tasks.filter(t => !t.is_fixed_time)}
                  onUpdateTask={(id: string, status: TaskStatus) => {
                    updateTask(id, { status });
                    refetchTasks();
                  }}
                  onTaskClick={taskModal.openTaskDetail}
                  assigneeByTaskId={assigneeByTaskId}
                  assignedMemberIdsByTaskId={assignedMemberIdsByTaskId}
                  memberOptions={memberOptions}
                  onAssignMultiple={handleAssignMultiple}
                  onDeleteTask={(taskId: string) => {
                    deleteTask(taskId);
                    refetchTasks();
                  }}
                  onRefreshTasks={refetchTasks}
                  onCreateTask={handleOpenCreateTask}
                  onDeleteGeneratedTasks={deleteGeneratedTasks}
                  onGenerateTasks={generateTasks}
                  taskAssignments={assignments}
                  currentUserId={currentUser?.id}
                  onCheckCompletion={handleCheckCompletion}
                />
              )}
            </div>
          </div>
        )}

        {activeTab === 'gantt' && (
          <div className="project-v2-section">
            <div className="project-v2-grid">
              <div className="project-v2-card">
                <ProjectGanttChart
                  projectId={projectId}
                  tasks={tasks}
                  phases={phases}
                  milestones={milestones}
                  assigneeByTaskId={assigneeByTaskId}
                  onTaskUpdate={async (taskId, updates) => {
                    try {
                      await tasksApi.update(taskId, updates);
                      refetchTasks();
                    } catch (err) {
                      console.error('Failed to update task:', err);
                    }
                  }}
                  onPhaseUpdate={async (phaseId, updates) => {
                    try {
                      await phasesApi.update(phaseId, updates);
                      refreshPhases();
                    } catch (err) {
                      console.error('Failed to update phase:', err);
                    }
                  }}
                  onTaskClick={(taskId) => taskModal.openTaskDetailById(taskId)}
                  onMilestoneClick={(milestoneId) => {
                    const milestone = milestones.find(m => m.id === milestoneId);
                    if (milestone) {
                      setGanttEditingMilestone(milestone);
                    }
                  }}
                  onTaskCreate={(phaseId) => taskModal.openCreateForm({
                    project_id: projectId,
                    phase_id: phaseId,
                  })}
                  onBatchTaskUpdate={async (updates) => {
                    try {
                      // Update all tasks in sequence
                      for (const { taskId, updates: taskUpdates } of updates) {
                        await tasksApi.update(taskId, taskUpdates);
                      }
                      refetchTasks();
                    } catch (err) {
                      console.error('Failed to batch update tasks:', err);
                    }
                  }}
                  onDependencyUpdate={async (taskId, newDependencyIds) => {
                    try {
                      await tasksApi.update(taskId, { dependency_ids: newDependencyIds });
                      refetchTasks();
                    } catch (err) {
                      console.error('Failed to update dependencies:', err);
                    }
                  }}
                  onMilestoneLink={async (taskId, milestoneId) => {
                    try {
                      await tasksApi.update(taskId, { milestone_id: milestoneId ?? undefined });
                      refetchTasks();
                    } catch (err) {
                      console.error('Failed to link task to milestone:', err);
                    }
                  }}
                  onMilestoneUpdate={async (milestoneId, updates) => {
                    try {
                      await milestonesApi.update(milestoneId, updates);
                      await refreshMilestones();
                    } catch (err) {
                      console.error('Failed to update milestone:', err);
                    }
                  }}
                  onSubtaskCreate={(parentTaskId) => taskModal.openCreateSubtaskForm(parentTaskId)}
                  onGenerateSubtasks={(parentTaskId, taskTitle) => {
                    const draftCard: DraftCardData = {
                      type: 'subtask',
                      title: 'サブタスク生成',
                      info: [
                        { label: '親タスク', value: taskTitle },
                        { label: 'タスクID', value: parentTaskId },
                      ],
                      placeholder: '例: 3つに分割して',
                      promptTemplate: `タスク「${taskTitle}」(ID: ${parentTaskId}) のサブタスクを作成して。

追加の指示があれば以下に記入:
{instruction}`,
                    };
                    window.dispatchEvent(new CustomEvent('secretary:chat-open', {
                      detail: { draftCard }
                    }));
                  }}
                  onDeleteTask={async (taskId) => {
                    try {
                      await tasksApi.delete(taskId);
                      refetchTasks();
                    } catch (err) {
                      console.error('Failed to delete task:', err);
                    }
                  }}
                  onDeleteMilestone={async (milestoneId) => {
                    try {
                      await milestonesApi.delete(milestoneId);
                      await refreshMilestones();
                      refetchTasks(); // タスクのマイルストーン紐づけも更新
                    } catch (err) {
                      console.error('Failed to delete milestone:', err);
                    }
                  }}
                  onGenerateMilestoneTasks={(milestoneId, milestoneTitle) => {
                    const draftCard: DraftCardData = {
                      type: 'task',
                      title: 'タスク生成',
                      info: [
                        { label: 'マイルストーン', value: milestoneTitle },
                        { label: 'マイルストーンID', value: milestoneId },
                      ],
                      placeholder: '例: 3つのタスクに分解して',
                      promptTemplate: `マイルストーン「${milestoneTitle}」(ID: ${milestoneId}) のタスクを作成して。

追加の指示があれば以下に記入:
{instruction}`,
                    };
                    window.dispatchEvent(new CustomEvent('secretary:chat-open', {
                      detail: { draftCard }
                    }));
                  }}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'meetings' && (
          <MeetingsTab
            projectId={projectId!}
            members={members}
            tasks={tasks}
            currentUserId={currentUser?.id || members[0]?.member_user_id || ''}
            canDeleteAnyCheckin={canDeleteAnyCheckin}
          />
        )}

        {activeTab === 'achievements' && (
          <ProjectAchievementsSection projectId={projectId!} />
        )}

        {activeTab === 'tree' && project && (
          <ProjectHierarchyTree
            project={project}
            phases={phases}
            milestones={milestones}
            tasks={tasks}
            assigneeByTaskId={assigneeByTaskId}
            onTaskClick={(id) => taskModal.openTaskDetailById(id)}
          />
        )}
      </section>

      {/* Task Modals (via unified hook) */}
      {taskModal.renderModals()}

      {/* Project Edit Modal (v1 reuse) */}
      {isProjectModalOpen && project && (
        <ProjectDetailModal
          project={project}
          onClose={handleCloseProjectModal}
          onUpdate={handleProjectUpdate}
        />
      )}

      {/* Project Delete Confirmation Modal */}
      {isDeleteConfirmOpen && (
        <div className="project-v2-modal-overlay" onClick={handleCancelDelete}>
          <div className="project-v2-modal project-v2-modal-danger" onClick={(e) => e.stopPropagation()}>
            <div className="project-v2-modal-header">
              <h2>プロジェクトを削除</h2>
              <button className="project-v2-icon-btn" onClick={handleCancelDelete}>
                <FaTimes />
              </button>
            </div>
            <div className="project-v2-modal-body">
              <p className="project-v2-modal-warning">
                この操作は取り消せません。プロジェクト「{project?.name}」とそれに関連するすべてのデータ（タスク、フェーズ、マイルストーンなど）が完全に削除されます。
              </p>
              <label className="project-v2-label">
                確認のため、プロジェクト名「<strong>{project?.name}</strong>」を入力してください
                <input
                  type="text"
                  className="project-v2-input"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder={project?.name}
                />
              </label>
            </div>
            <div className="project-v2-modal-actions">
              <button
                className="project-v2-button ghost"
                onClick={handleCancelDelete}
                disabled={isDeletingProject}
              >
                キャンセル
              </button>
              <button
                className="project-v2-button danger"
                onClick={handleDeleteProject}
                disabled={isDeletingProject || deleteConfirmText !== project?.name}
              >
                {isDeletingProject ? '削除中...' : '削除する'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gantt Milestone Edit Modal */}
      {ganttEditingMilestone && (
        <MilestoneEditModal
          milestone={ganttEditingMilestone}
          linkedTaskCount={tasks.filter(t => t.milestone_id === ganttEditingMilestone.id).length}
          phaseName={phases.find(p => p.id === ganttEditingMilestone.phase_id)?.name}
          phaseId={ganttEditingMilestone.phase_id}
          onClose={() => setGanttEditingMilestone(null)}
          onUpdate={async (data: MilestoneUpdate) => {
            setGanttMilestoneSubmitting(true);
            try {
              await milestonesApi.update(ganttEditingMilestone.id, data);
              await refreshMilestones();
              setGanttEditingMilestone(null);
            } catch (err) {
              console.error('Failed to update milestone:', err);
            } finally {
              setGanttMilestoneSubmitting(false);
            }
          }}
          onDelete={() => {
            setPendingDeleteMilestone({
              id: ganttEditingMilestone.id,
              title: ganttEditingMilestone.title,
              linkedTaskCount: tasks.filter(t => t.milestone_id === ganttEditingMilestone.id).length,
            });
          }}
          isSubmitting={ganttMilestoneSubmitting}
        />
      )}

      {/* Milestone Delete Confirmation Dialog */}
      {pendingDeleteMilestone && (
        <div className="project-v2-modal-overlay" onClick={() => setPendingDeleteMilestone(null)}>
          <div className="project-v2-modal project-v2-modal-danger" onClick={(e) => e.stopPropagation()}>
            <div className="project-v2-modal-header">
              <h2>マイルストーンを削除</h2>
              <button className="project-v2-icon-btn" onClick={() => setPendingDeleteMilestone(null)}>
                <FaTimes />
              </button>
            </div>
            <div className="project-v2-modal-body">
              <p className="project-v2-modal-warning">
                「{pendingDeleteMilestone.title}」を削除しますか？
              </p>
              {pendingDeleteMilestone.linkedTaskCount > 0 && (
                <p className="project-v2-modal-warning" style={{ background: '#fef3c7', color: '#92400e', padding: '8px 12px', borderRadius: '6px', fontWeight: 500 }}>
                  {pendingDeleteMilestone.linkedTaskCount}件のタスクが紐づいています。タスクの紐づけは解除されます。
                </p>
              )}
              <p className="project-v2-modal-warning">この操作は取り消せません。</p>
            </div>
            <div className="project-v2-modal-actions">
              <button
                className="project-v2-button ghost"
                onClick={() => setPendingDeleteMilestone(null)}
                disabled={isDeletingMilestone}
              >
                キャンセル
              </button>
              <button
                className="project-v2-button danger"
                onClick={async () => {
                  setIsDeletingMilestone(true);
                  try {
                    await milestonesApi.delete(pendingDeleteMilestone.id);
                    await refreshMilestones();
                    refetchTasks();
                    setPendingDeleteMilestone(null);
                    setGanttEditingMilestone(null);
                  } catch (err) {
                    console.error('Failed to delete milestone:', err);
                  } finally {
                    setIsDeletingMilestone(false);
                  }
                }}
                disabled={isDeletingMilestone}
              >
                {isDeletingMilestone ? '削除中...' : '削除する'}
              </button>
            </div>
          </div>
        </div>
      )}
      <PageTour
        run={tour.run}
        steps={tour.steps}
        stepIndex={tour.stepIndex}
        onCallback={tour.handleCallback}
      />
    </div>
  );
}
