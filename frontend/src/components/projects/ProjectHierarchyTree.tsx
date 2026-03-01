import { useMemo, useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueries } from '@tanstack/react-query';
import { FaCalendarAlt, FaUser, FaChevronDown, FaChevronRight } from 'react-icons/fa';
import { phasesApi } from '../../api/phases';
import { milestonesApi } from '../../api/milestones';
import { tasksApi } from '../../api/tasks';
import { projectsApi } from '../../api/projects';
import type { ProjectWithTaskCount, PhaseWithTaskCount, Milestone, Task } from '../../api/types';
import './ProjectHierarchyTree.css';

/* ============================
   Tree Node Model
   ============================ */

interface TreeNode {
  id: string;
  type: 'project' | 'child-project' | 'phase' | 'milestone' | 'task';
  label: string;
  status: string;
  progress?: number;
  linkTo?: string;
  children: TreeNode[];
  dueDate?: string;
  startNotBefore?: string;
  startDate?: string;
  endDate?: string;
  assigneeLabel?: string;
  ownerLabel?: string;
  subtaskCount?: number;
}

/* ============================
   Props
   ============================ */

interface ProjectHierarchyTreeProps {
  project: ProjectWithTaskCount;
  phases: PhaseWithTaskCount[];
  milestones: Milestone[];
  tasks: Task[];
  assigneeByTaskId?: Record<string, string>;
  onTaskClick?: (taskId: string) => void;
}

/* ============================
   Status → CSS class mapping
   ============================ */

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s === 'active' || s === 'in_progress') return 'status-active';
  if (s === 'completed' || s === 'done') return 'status-done';
  if (s === 'planned' || s === 'todo') return 'status-planned';
  if (s === 'waiting') return 'status-waiting';
  if (s === 'archived') return 'status-archived';
  return 'status-planned';
}

/* ============================
   Helpers
   ============================ */

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function truncateAssignee(label: string): string {
  const parts = label.split(',').map((s) => s.trim());
  if (parts.length <= 1) return label.length > 8 ? label.slice(0, 7) + '…' : label;
  return `${parts[0].length > 6 ? parts[0].slice(0, 5) + '…' : parts[0]} +${parts.length - 1}`;
}

function formatDateRange(start?: string, end?: string): string {
  if (start && end) return `${formatShortDate(start)} - ${formatShortDate(end)}`;
  if (start) return `${formatShortDate(start)} -`;
  if (end) return `- ${formatShortDate(end)}`;
  return '';
}

function truncateOwner(name: string): string {
  return name.length > 10 ? name.slice(0, 9) + '…' : name;
}

/* ============================
   Child Project Data
   ============================ */

interface ChildProjectData {
  phases: PhaseWithTaskCount[];
  milestones: Milestone[];
  tasks: Task[];
}

/* ============================
   Build subtree from flat data
   (shared between parent & child projects)
   ============================ */

function buildSubtreeChildren(
  projectPhases: PhaseWithTaskCount[],
  projectMilestones: Milestone[],
  projectTasks: Task[],
  assigneeByTaskId?: Record<string, string>,
): TreeNode[] {
  const milestonesByPhase = new Map<string, Milestone[]>();
  projectMilestones.forEach((ms) => {
    const list = milestonesByPhase.get(ms.phase_id) || [];
    list.push(ms);
    milestonesByPhase.set(ms.phase_id, list);
  });

  const subtaskCounts = new Map<string, number>();
  projectTasks.forEach((t) => {
    if (t.parent_id) {
      subtaskCounts.set(t.parent_id, (subtaskCounts.get(t.parent_id) || 0) + 1);
    }
  });

  const parentTasks = projectTasks.filter((t) => !t.parent_id);
  const tasksByPhase = new Map<string, Task[]>();
  const tasksByMilestone = new Map<string, Task[]>();
  const orphanTasks: Task[] = [];

  parentTasks.forEach((t) => {
    if (t.milestone_id) {
      const list = tasksByMilestone.get(t.milestone_id) || [];
      list.push(t);
      tasksByMilestone.set(t.milestone_id, list);
    } else if (t.phase_id) {
      const list = tasksByPhase.get(t.phase_id) || [];
      list.push(t);
      tasksByPhase.set(t.phase_id, list);
    } else {
      orphanTasks.push(t);
    }
  });

  const makeTaskNode = (t: Task): TreeNode => ({
    id: t.id,
    type: 'task',
    label: t.title,
    status: t.status,
    dueDate: t.due_date,
    startNotBefore: t.start_not_before,
    assigneeLabel: assigneeByTaskId?.[t.id],
    subtaskCount: subtaskCounts.get(t.id) || 0,
    children: [],
  });

  const buildMilestoneNode = (ms: Milestone): TreeNode => {
    const msTasks = tasksByMilestone.get(ms.id) || [];
    return {
      id: ms.id,
      type: 'milestone',
      label: ms.title,
      status: ms.status,
      progress: ms.task_count && ms.task_count > 0
        ? Math.round(((ms.completed_task_count || 0) / ms.task_count) * 100)
        : undefined,
      children: msTasks.map(makeTaskNode),
    };
  };

  const buildPhaseNode = (phase: PhaseWithTaskCount): TreeNode => {
    const phaseMilestones = (milestonesByPhase.get(phase.id) || [])
      .sort((a, b) => a.order_in_phase - b.order_in_phase);
    const phaseDirectTasks = tasksByPhase.get(phase.id) || [];

    return {
      id: phase.id,
      type: 'phase',
      label: phase.name,
      status: phase.status,
      startDate: phase.start_date,
      endDate: phase.end_date,
      progress: phase.total_tasks > 0
        ? Math.round((phase.completed_tasks / phase.total_tasks) * 100)
        : undefined,
      children: [
        ...phaseMilestones.map(buildMilestoneNode),
        ...phaseDirectTasks.map(makeTaskNode),
      ],
    };
  };

  const sortedPhases = [...projectPhases].sort((a, b) => a.order_in_project - b.order_in_project);

  return [
    ...sortedPhases.map(buildPhaseNode),
    ...orphanTasks.map(makeTaskNode),
  ];
}

/* ============================
   Build full tree
   ============================ */

function buildTree(
  project: ProjectWithTaskCount,
  phases: PhaseWithTaskCount[],
  milestones: Milestone[],
  tasks: Task[],
  childProjects: ProjectWithTaskCount[],
  childDataMap: Map<string, ChildProjectData>,
  assigneeByTaskId?: Record<string, string>,
): TreeNode {
  const buildChildProjectNode = (cp: ProjectWithTaskCount): TreeNode => {
    const childData = childDataMap.get(cp.id);
    const children = childData
      ? buildSubtreeChildren(childData.phases, childData.milestones, childData.tasks, assigneeByTaskId)
      : [];

    return {
      id: cp.id,
      type: 'child-project',
      label: cp.name,
      status: cp.status,
      ownerLabel: cp.owner_display_name,
      progress: cp.aggregated_total_tasks > 0
        ? Math.round((cp.aggregated_completed_tasks / cp.aggregated_total_tasks) * 100)
        : undefined,
      linkTo: `/projects/${cp.id}/v2?tab=tree`,
      children,
    };
  };

  const parentChildren = buildSubtreeChildren(phases, milestones, tasks, assigneeByTaskId);

  const rootChildren: TreeNode[] = [
    ...childProjects.sort((a, b) => a.name.localeCompare(b.name)).map(buildChildProjectNode),
    ...parentChildren,
  ];

  const totalTasks = project.aggregated_total_tasks || project.total_tasks;
  const completedTasks = project.aggregated_completed_tasks || project.completed_tasks;

  return {
    id: project.id,
    type: 'project',
    label: project.name,
    status: project.status,
    progress: totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : undefined,
    children: rootChildren,
  };
}

/* ============================
   Layout Constants
   ============================ */

const NODE_W = 180;
const NODE_H_DEFAULT = 68;
const NODE_H_WITH_META = 88;
const ROW_GAP = 10;
const COL_GAP = 60;

function nodeHeight(type: string): number {
  if (type === 'task' || type === 'phase' || type === 'child-project') return NODE_H_WITH_META;
  return NODE_H_DEFAULT;
}

/* ============================
   Column Detection (5 columns)
   ============================ */

interface ColumnDef {
  key: string;
  label: string;
}

function detectColumns(root: TreeNode): ColumnDef[] {
  const types = new Set<string>();
  (function collect(n: TreeNode) {
    types.add(n.type);
    n.children.forEach(collect);
  })(root);

  const cols: ColumnDef[] = [{ key: 'project', label: 'プロジェクト' }];

  if (types.has('child-project')) {
    cols.push({ key: 'child-project', label: 'サブプロジェクト' });
  }

  if (types.has('phase')) {
    cols.push({ key: 'phase', label: 'フェーズ' });
  }

  if (types.has('milestone')) {
    cols.push({ key: 'milestone', label: 'マイルストーン' });
  }

  if (types.has('task')) {
    cols.push({ key: 'task', label: 'タスク' });
  }

  return cols;
}

function columnX(type: string, cols: ColumnDef[]): number {
  const idx = cols.findIndex((c) => c.key === type);
  return (idx < 0 ? 0 : idx) * (NODE_W + COL_GAP);
}

/* ============================
   Layout Computation
   ============================ */

interface LayoutItem {
  node: TreeNode;
  x: number;
  y: number;
  centerY: number;
  h: number;
}

interface Seg {
  x1: number; y1: number;
  x2: number; y2: number;
}

function subtreeH(n: TreeNode): number {
  const h = nodeHeight(n.type);
  if (n.children.length === 0) return h;
  return n.children.reduce((s, c) => s + subtreeH(c), 0)
    + (n.children.length - 1) * ROW_GAP;
}

function computeLayout(root: TreeNode, cols: ColumnDef[]) {
  const items: LayoutItem[] = [];
  const segs: Seg[] = [];

  function lay(node: TreeNode, yStart: number): void {
    const x = columnX(node.type, cols);
    const h = subtreeH(node);
    const nh = nodeHeight(node.type);
    const cy = yStart + h / 2;

    items.push({ node, x, y: cy - nh / 2, centerY: cy, h: nh });

    if (node.children.length === 0) return;

    const childInfos: { x: number; cy: number }[] = [];
    let childY = yStart;

    for (const ch of node.children) {
      const chH = subtreeH(ch);
      const chCY = childY + chH / 2;
      childInfos.push({ x: columnX(ch.type, cols), cy: chCY });
      lay(ch, childY);
      childY += chH + ROW_GAP;
    }

    // Connector lines
    const pRight = x + NODE_W;
    const minCX = Math.min(...childInfos.map((c) => c.x));
    const midX = pRight + (minCX - pRight) / 2;

    // Horizontal stub from parent
    segs.push({ x1: pRight, y1: cy, x2: midX, y2: cy });

    // Vertical bar connecting children
    if (childInfos.length > 1) {
      const minCY = Math.min(...childInfos.map((c) => c.cy));
      const maxCY = Math.max(...childInfos.map((c) => c.cy));
      segs.push({ x1: midX, y1: minCY, x2: midX, y2: maxCY });
    }

    // Horizontal stub to each child
    for (const ci of childInfos) {
      segs.push({ x1: midX, y1: ci.cy, x2: ci.x, y2: ci.cy });
    }
  }

  lay(root, 0);

  const totalH = subtreeH(root);
  const totalW = (cols.length - 1) * (NODE_W + COL_GAP) + NODE_W;
  return { items, segs, totalW, totalH };
}

/* ============================
   Node Type Labels
   ============================ */

const TYPE_LABELS: Record<string, string> = {
  project: 'Project',
  'child-project': 'Sub Project',
  phase: 'Phase',
  milestone: 'Milestone',
  task: 'Task',
};

/* ============================
   Subtask Popover
   ============================ */

function SubtaskPopover({
  subtasks,
  position,
  onClose,
  onTaskClick,
}: {
  subtasks: Task[];
  position: { top: number; left: number };
  onClose: () => void;
  onTaskClick?: (taskId: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  const sorted = [...subtasks].sort(
    (a, b) => (a.order_in_parent ?? 0) - (b.order_in_parent ?? 0),
  );

  return createPortal(
    <div
      ref={ref}
      className="subtask-popover"
      style={{ position: 'fixed', top: position.top, left: position.left, zIndex: 9999 }}
    >
      <div className="subtask-popover-header">
        サブタスク ({sorted.length})
      </div>
      {sorted.map((st) => (
        <div
          key={st.id}
          className="subtask-popover-item"
          onClick={() => onTaskClick?.(st.id)}
        >
          <span className={`subtask-dot ${statusClass(st.status)}`} />
          <span className="subtask-label">{st.title}</span>
        </div>
      ))}
    </div>,
    document.body,
  );
}

/* ============================
   Main Component
   ============================ */

export function ProjectHierarchyTree({
  project,
  phases,
  milestones,
  tasks,
  assigneeByTaskId,
  onTaskClick,
}: ProjectHierarchyTreeProps) {
  const navigate = useNavigate();
  const [expandedSubtaskId, setExpandedSubtaskId] = useState<string | null>(null);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);

  /* --- Fetch child projects --- */
  const { data: childProjects } = useQuery({
    queryKey: ['project-children', project.id],
    queryFn: () => projectsApi.getChildren(project.id),
  });

  const childIds = useMemo(
    () => (childProjects || []).map((cp) => cp.id),
    [childProjects],
  );

  /* --- Fetch phases/milestones/tasks for each child project --- */
  const childPhaseQueries = useQueries({
    queries: childIds.map((id) => ({
      queryKey: ['child-project-phases', id],
      queryFn: () => phasesApi.listByProject(id),
      staleTime: 60_000,
    })),
  });

  const childMilestoneQueries = useQueries({
    queries: childIds.map((id) => ({
      queryKey: ['child-project-milestones', id],
      queryFn: () => milestonesApi.listByProject(id),
      staleTime: 60_000,
    })),
  });

  const childTaskQueries = useQueries({
    queries: childIds.map((id) => ({
      queryKey: ['child-project-tasks', id],
      queryFn: () => tasksApi.getAll({ projectId: id, includeDone: true }),
      staleTime: 60_000,
    })),
  });

  /* --- Build child data map --- */
  const childDataMap = useMemo(() => {
    const map = new Map<string, ChildProjectData>();
    childIds.forEach((id, i) => {
      map.set(id, {
        phases: childPhaseQueries[i]?.data || [],
        milestones: childMilestoneQueries[i]?.data || [],
        tasks: childTaskQueries[i]?.data || [],
      });
    });
    return map;
  }, [childIds, childPhaseQueries, childMilestoneQueries, childTaskQueries]);

  /* --- Build tree --- */
  const tree = useMemo(
    () => buildTree(project, phases, milestones, tasks, childProjects || [], childDataMap, assigneeByTaskId),
    [project, phases, milestones, tasks, childProjects, childDataMap, assigneeByTaskId],
  );

  const cols = useMemo(() => detectColumns(tree), [tree]);

  const { items, segs, totalW, totalH } = useMemo(
    () => computeLayout(tree, cols),
    [tree, cols],
  );

  /* --- Subtask lookup (parent + all child project tasks) --- */
  const allTasks = useMemo(() => {
    const combined = [...tasks];
    childDataMap.forEach((data) => {
      combined.push(...data.tasks);
    });
    return combined;
  }, [tasks, childDataMap]);

  const subtasksByParentId = useMemo(() => {
    const map = new Map<string, Task[]>();
    allTasks.forEach((t) => {
      if (t.parent_id) {
        const list = map.get(t.parent_id) || [];
        list.push(t);
        map.set(t.parent_id, list);
      }
    });
    return map;
  }, [allTasks]);

  const handleSubtaskToggle = useCallback((taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (expandedSubtaskId === taskId) {
      setExpandedSubtaskId(null);
      setPopoverPos(null);
      return;
    }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopoverPos({ top: rect.bottom + 4, left: rect.left });
    setExpandedSubtaskId(taskId);
  }, [expandedSubtaskId]);

  const closePopover = useCallback(() => {
    setExpandedSubtaskId(null);
    setPopoverPos(null);
  }, []);

  if (tree.children.length === 0) {
    return (
      <div className="hierarchy-tree">
        <div className="hierarchy-tree-empty">
          フェーズ・タスクがまだありません
        </div>
      </div>
    );
  }

  return (
    <div className="hierarchy-tree">
      <div className="hierarchy-tree-scroll">
        {/* Column headers */}
        <div className="hierarchy-tree-headers" style={{ width: totalW }}>
          {cols.map((c, i) => (
            <div
              key={c.key}
              className="hierarchy-tree-header"
              style={{
                position: 'absolute',
                left: i * (NODE_W + COL_GAP),
                width: NODE_W,
              }}
            >
              {c.label}
            </div>
          ))}
        </div>

        {/* Tree canvas */}
        <div
          className="hierarchy-tree-canvas"
          style={{ width: totalW, height: totalH }}
        >
          {/* SVG connector lines */}
          <svg
            className="hierarchy-tree-svg"
            width={totalW}
            height={totalH}
          >
            {segs.map((s, i) => (
              <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} />
            ))}
          </svg>

          {/* Node cards */}
          {items.map((item) => {
            const hasLink = !!item.node.linkTo;
            const isTaskOrMs = item.node.type === 'task' || item.node.type === 'milestone';
            const isClickable = hasLink || (isTaskOrMs && !!onTaskClick);
            const isTask = item.node.type === 'task';
            const hasSubtasks = (item.node.subtaskCount ?? 0) > 0;

            return (
              <div
                key={item.node.id}
                className={`tree-node type-${item.node.type} ${statusClass(item.node.status)}${isClickable ? ' clickable' : ''}`}
                style={{
                  position: 'absolute',
                  left: item.x,
                  top: item.y,
                  width: NODE_W,
                  height: item.h,
                }}
                onClick={
                  isClickable
                    ? () => {
                        if (hasLink) {
                          navigate(item.node.linkTo!);
                        } else if (onTaskClick) {
                          onTaskClick(item.node.id);
                        }
                      }
                    : undefined
                }
                title={item.node.label}
              >
                <span className="tree-node-type">{TYPE_LABELS[item.node.type]}</span>
                <span className="tree-node-label">{item.node.label}</span>
                {item.node.progress !== undefined && (
                  <div className="tree-node-progress">
                    <div className="tree-node-progress-bar">
                      <div
                        className="tree-node-progress-fill"
                        style={{ width: `${item.node.progress}%` }}
                      />
                    </div>
                    <span className="tree-node-progress-text">{item.node.progress}%</span>
                  </div>
                )}
                {/* Child-project: owner */}
                {item.node.type === 'child-project' && item.node.ownerLabel && (
                  <div className="tree-node-meta">
                    <span className="tree-node-assignee" title={item.node.ownerLabel}>
                      <FaUser className="tree-node-meta-icon" />
                      {truncateOwner(item.node.ownerLabel)}
                    </span>
                  </div>
                )}
                {/* Phase: period (start - end) */}
                {item.node.type === 'phase' && (item.node.startDate || item.node.endDate) && (
                  <div className="tree-node-meta">
                    <span className="tree-node-due" title={formatDateRange(item.node.startDate, item.node.endDate)}>
                      <FaCalendarAlt className="tree-node-meta-icon" />
                      {formatDateRange(item.node.startDate, item.node.endDate)}
                    </span>
                  </div>
                )}
                {/* Task: start_not_before ~ due_date + assignee */}
                {isTask && (item.node.startNotBefore || item.node.dueDate || item.node.assigneeLabel) && (
                  <div className="tree-node-meta">
                    {(item.node.startNotBefore || item.node.dueDate) && (
                      <span className="tree-node-due" title={
                        item.node.startNotBefore && item.node.dueDate
                          ? `${item.node.startNotBefore} ~ ${item.node.dueDate}`
                          : item.node.dueDate || item.node.startNotBefore || ''
                      }>
                        <FaCalendarAlt className="tree-node-meta-icon" />
                        {item.node.startNotBefore && item.node.dueDate
                          ? `${formatShortDate(item.node.startNotBefore)}~${formatShortDate(item.node.dueDate)}`
                          : item.node.startNotBefore
                            ? `${formatShortDate(item.node.startNotBefore)}~`
                            : `~${formatShortDate(item.node.dueDate!)}`
                        }
                      </span>
                    )}
                    {item.node.assigneeLabel && (
                      <span className="tree-node-assignee" title={item.node.assigneeLabel}>
                        <FaUser className="tree-node-meta-icon" />
                        {truncateAssignee(item.node.assigneeLabel)}
                      </span>
                    )}
                  </div>
                )}
                {/* Subtask expand toggle */}
                {isTask && hasSubtasks && (
                  <button
                    className="tree-node-subtask-toggle"
                    onClick={(e) => handleSubtaskToggle(item.node.id, e)}
                    title={`サブタスク (${item.node.subtaskCount})`}
                  >
                    {expandedSubtaskId === item.node.id
                      ? <FaChevronDown />
                      : <FaChevronRight />}
                    <span className="tree-node-subtask-count">{item.node.subtaskCount}</span>
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Subtask popover */}
      {expandedSubtaskId && popoverPos && subtasksByParentId.has(expandedSubtaskId) && (
        <SubtaskPopover
          subtasks={subtasksByParentId.get(expandedSubtaskId)!}
          position={popoverPos}
          onClose={closePopover}
          onTaskClick={onTaskClick}
        />
      )}
    </div>
  );
}
