import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
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
}

/* ============================
   Props
   ============================ */

interface ProjectHierarchyTreeProps {
  project: ProjectWithTaskCount;
  phases: PhaseWithTaskCount[];
  milestones: Milestone[];
  tasks: Task[];
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
   Build tree from flat data
   ============================ */

function buildTree(
  project: ProjectWithTaskCount,
  phases: PhaseWithTaskCount[],
  milestones: Milestone[],
  tasks: Task[],
  childProjects: ProjectWithTaskCount[],
): TreeNode {
  // Group helpers
  const milestonesByPhase = new Map<string, Milestone[]>();
  milestones.forEach((ms) => {
    const list = milestonesByPhase.get(ms.phase_id) || [];
    list.push(ms);
    milestonesByPhase.set(ms.phase_id, list);
  });

  const parentTasks = tasks.filter((t) => !t.parent_id);
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

  // Build milestone nodes
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
      children: msTasks.map((t) => ({
        id: t.id,
        type: 'task' as const,
        label: t.title,
        status: t.status,
        children: [],
      })),
    };
  };

  // Build phase nodes
  const buildPhaseNode = (phase: PhaseWithTaskCount): TreeNode => {
    const phaseMilestones = (milestonesByPhase.get(phase.id) || [])
      .sort((a, b) => a.order_in_phase - b.order_in_phase);
    const phaseDirectTasks = tasksByPhase.get(phase.id) || [];

    const children: TreeNode[] = [
      ...phaseMilestones.map(buildMilestoneNode),
      ...phaseDirectTasks.map((t) => ({
        id: t.id,
        type: 'task' as const,
        label: t.title,
        status: t.status,
        children: [] as TreeNode[],
      })),
    ];

    const progress = phase.total_tasks > 0
      ? Math.round((phase.completed_tasks / phase.total_tasks) * 100)
      : undefined;

    return {
      id: phase.id,
      type: 'phase',
      label: phase.name,
      status: phase.status,
      progress,
      children,
    };
  };

  // Build child project nodes
  const buildChildProjectNode = (cp: ProjectWithTaskCount): TreeNode => ({
    id: cp.id,
    type: 'child-project',
    label: cp.name,
    status: cp.status,
    progress: cp.aggregated_total_tasks > 0
      ? Math.round((cp.aggregated_completed_tasks / cp.aggregated_total_tasks) * 100)
      : undefined,
    linkTo: `/projects/${cp.id}/v2?tab=tree`,
    children: [],
  });

  // Sort phases
  const sortedPhases = [...phases].sort((a, b) => a.order_in_project - b.order_in_project);

  // Root children
  const rootChildren: TreeNode[] = [
    ...sortedPhases.map(buildPhaseNode),
    ...childProjects.sort((a, b) => a.name.localeCompare(b.name)).map(buildChildProjectNode),
    ...orphanTasks.map((t) => ({
      id: t.id,
      type: 'task' as const,
      label: t.title,
      status: t.status,
      children: [] as TreeNode[],
    })),
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
   Tree Node Renderer
   ============================ */

function TreeNodeCard({ node }: { node: TreeNode }) {
  const navigate = useNavigate();
  const cls = statusClass(node.status);
  const isClickable = !!node.linkTo;

  const TYPE_LABELS: Record<string, string> = {
    project: 'Project',
    'child-project': 'Sub Project',
    phase: 'Phase',
    milestone: 'Milestone',
    task: 'Task',
  };

  return (
    <div
      className={`tree-node type-${node.type} ${cls}${isClickable ? ' clickable' : ''}`}
      onClick={isClickable ? () => navigate(node.linkTo!) : undefined}
      title={node.label}
    >
      <span className="tree-node-type">{TYPE_LABELS[node.type]}</span>
      <span className="tree-node-label">{node.label}</span>
      {node.progress !== undefined && (
        <div className="tree-node-progress">
          <div className="tree-node-progress-bar">
            <div
              className="tree-node-progress-fill"
              style={{ width: `${node.progress}%` }}
            />
          </div>
          <span className="tree-node-progress-text">{node.progress}%</span>
        </div>
      )}
    </div>
  );
}

/* ============================
   Recursive Branch Renderer
   ============================ */

function TreeBranch({ node }: { node: TreeNode }) {
  if (node.children.length === 0) {
    return <TreeNodeCard node={node} />;
  }

  return (
    <div className="tree-branch">
      <TreeNodeCard node={node} />
      <div className="tree-connector" />
      <div className="tree-children">
        {node.children.map((child, i) => (
          <div
            key={child.id}
            className="tree-child-item"
            style={
              node.children.length === 1
                ? undefined
                : {
                    // Adjust vertical connector height
                    '--is-first': i === 0 ? '1' : '0',
                    '--is-last': i === node.children.length - 1 ? '1' : '0',
                  } as React.CSSProperties
            }
          >
            <TreeBranch node={child} />
          </div>
        ))}
      </div>
    </div>
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
}: ProjectHierarchyTreeProps) {
  const { data: childProjects } = useQuery({
    queryKey: ['project-children', project.id],
    queryFn: () => projectsApi.getChildren(project.id),
  });

  const tree = useMemo(
    () => buildTree(project, phases, milestones, tasks, childProjects || []),
    [project, phases, milestones, tasks, childProjects],
  );

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
      <TreeBranch node={tree} />
    </div>
  );
}
