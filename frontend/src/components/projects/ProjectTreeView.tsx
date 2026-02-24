import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaChevronRight, FaChevronDown, FaExpand, FaCompress } from 'react-icons/fa6';
import type { ProjectWithTaskCount } from '../../api/types';
import './ProjectTreeView.css';

interface ProjectTreeViewProps {
  topLevelProjects: ProjectWithTaskCount[];
  childrenMap: Map<string, ProjectWithTaskCount[]>;
  allProjects: ProjectWithTaskCount[];
}

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: '進行中',
  COMPLETED: '完了',
  ARCHIVED: 'アーカイブ',
};

function ProjectTreeNode({
  project,
  depth,
  childrenMap,
  expandedIds,
  onToggle,
}: {
  project: ProjectWithTaskCount;
  depth: number;
  childrenMap: Map<string, ProjectWithTaskCount[]>;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const navigate = useNavigate();
  const hasChildren = childrenMap.has(project.id);
  const isExpanded = expandedIds.has(project.id);
  const children = childrenMap.get(project.id) || [];

  // Use aggregated counts for projects with children, own counts for leaf
  const totalTasks = hasChildren ? project.aggregated_total_tasks : project.total_tasks;
  const completedTasks = hasChildren ? project.aggregated_completed_tasks : project.completed_tasks;
  const progress = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  return (
    <>
      <div
        className={`project-tree-node${depth === 0 ? ' depth-0' : ''}`}
        style={{ '--depth': depth } as React.CSSProperties}
      >
        {hasChildren ? (
          <button
            className="project-tree-toggle"
            onClick={() => onToggle(project.id)}
            title={isExpanded ? '折り畳む' : '展開する'}
          >
            {isExpanded ? <FaChevronDown /> : <FaChevronRight />}
          </button>
        ) : (
          <span className="project-tree-toggle spacer" />
        )}

        <span
          className="project-tree-name"
          onClick={() => navigate(`/projects/${project.id}/v2`)}
          role="link"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && navigate(`/projects/${project.id}/v2`)}
        >
          {project.name}
        </span>

        <span className={`project-tree-status status-${project.status.toLowerCase()}`}>
          {STATUS_LABELS[project.status] || project.status}
        </span>

        {totalTasks > 0 && (
          <div className="project-tree-progress">
            <div className="project-tree-progress-bar">
              <div
                className="project-tree-progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="project-tree-progress-text">{progress}%</span>
          </div>
        )}

        <span className="project-tree-stats">
          {completedTasks}/{totalTasks}
        </span>

        {hasChildren && (
          <span className="project-tree-child-badge">
            {children.length}子
          </span>
        )}
      </div>

      {isExpanded &&
        children.map((child) => (
          <ProjectTreeNode
            key={child.id}
            project={child}
            depth={depth + 1}
            childrenMap={childrenMap}
            expandedIds={expandedIds}
            onToggle={onToggle}
          />
        ))}
    </>
  );
}

export function ProjectTreeView({
  topLevelProjects,
  childrenMap,
  allProjects,
}: ProjectTreeViewProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    topLevelProjects.forEach((p) => {
      if (childrenMap.has(p.id)) initial.add(p.id);
    });
    return initial;
  });

  const toggleNode = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    const allParentIds = new Set<string>();
    allProjects.forEach((p) => {
      if (childrenMap.has(p.id)) allParentIds.add(p.id);
    });
    setExpandedIds(allParentIds);
  }, [allProjects, childrenMap]);

  const collapseAll = useCallback(() => {
    setExpandedIds(new Set());
  }, []);

  if (topLevelProjects.length === 0) {
    return (
      <div className="project-tree-empty">
        <div className="project-tree-empty-icon">📁</div>
        <p>プロジェクトがありません</p>
      </div>
    );
  }

  return (
    <div className="project-tree-container">
      <div className="project-tree-toolbar">
        <button onClick={expandAll} title="全展開">
          <FaExpand /> 展開
        </button>
        <button onClick={collapseAll} title="全折畳">
          <FaCompress /> 折畳
        </button>
      </div>

      <div className="project-tree-list">
        {topLevelProjects.map((project) => (
          <ProjectTreeNode
            key={project.id}
            project={project}
            depth={0}
            childrenMap={childrenMap}
            expandedIds={expandedIds}
            onToggle={toggleNode}
          />
        ))}
      </div>
    </div>
  );
}
