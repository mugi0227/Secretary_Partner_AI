import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../../api/projects';
import type { ProjectWithTaskCount, ProjectLinkRequest } from '../../api/types';
import { useNavigate } from 'react-router-dom';
import { FaPlus, FaWandMagicSparkles, FaSpinner, FaCheck, FaXmark, FaFolderOpen } from 'react-icons/fa6';
import './ChildProjectsSection.css';

interface ChildProjectsSectionProps {
  projectId: string;
  projectName: string;
}

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: '進行中',
  COMPLETED: '完了',
  ARCHIVED: 'アーカイブ',
};

function ChildProjectCard({ project }: { project: ProjectWithTaskCount }) {
  const navigate = useNavigate();
  const progress =
    project.total_tasks > 0
      ? Math.round((project.completed_tasks / project.total_tasks) * 100)
      : 0;

  return (
    <div className="child-project-card">
      <div className="child-project-info">
        <span
          className="child-project-name"
          onClick={() => navigate(`/projects/${project.id}`)}
          role="link"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && navigate(`/projects/${project.id}`)}
        >
          {project.name}
        </span>
        <div className="child-project-meta">
          <span className={`child-project-status-badge status-${project.status}`}>
            {STATUS_LABELS[project.status] || project.status}
          </span>
          <span className="child-project-task-summary">
            {project.completed_tasks}/{project.total_tasks} タスク完了
          </span>
        </div>
        <div className="child-project-progress">
          <div className="child-project-progress-bar">
            <div
              className="child-project-progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function PendingRequestCard({
  request,
  parentProjectId,
  isOwner,
}: {
  request: ProjectLinkRequest;
  parentProjectId: string;
  isOwner: boolean;
}) {
  const queryClient = useQueryClient();

  const { data: childProject } = useQuery({
    queryKey: ['project', request.child_project_id],
    queryFn: () => projectsApi.getById(request.child_project_id),
  });

  const approveMutation = useMutation({
    mutationFn: () => projectsApi.approveLinkRequest(parentProjectId, request.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-children', parentProjectId] });
      queryClient.invalidateQueries({ queryKey: ['project-link-requests', parentProjectId] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => projectsApi.rejectLinkRequest(parentProjectId, request.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-link-requests', parentProjectId] });
    },
  });

  const isProcessing = approveMutation.isPending || rejectMutation.isPending;

  return (
    <div className="child-project-card pending-request">
      <div className="child-project-info">
        <span className="child-project-name" style={{ color: 'var(--text-main)', cursor: 'default' }}>
          {childProject?.name || '読み込み中...'}
        </span>
        <div className="child-project-meta">
          <span className="child-project-status-badge status-pending">承認待ち</span>
        </div>
      </div>
      {isOwner && (
        <div className="child-project-actions">
          <button
            className="btn-approve"
            onClick={() => approveMutation.mutate()}
            disabled={isProcessing}
            title="承認"
          >
            <FaCheck /> 承認
          </button>
          <button
            className="btn-reject"
            onClick={() => rejectMutation.mutate()}
            disabled={isProcessing}
            title="拒否"
          >
            <FaXmark /> 拒否
          </button>
        </div>
      )}
    </div>
  );
}

export function ChildProjectsSection({ projectId, projectName }: ChildProjectsSectionProps) {
  const [showAddOptions, setShowAddOptions] = useState(false);

  const {
    data: children,
    isLoading: isLoadingChildren,
  } = useQuery({
    queryKey: ['project-children', projectId],
    queryFn: () => projectsApi.getChildren(projectId),
  });

  const {
    data: pendingRequests,
    isLoading: isLoadingRequests,
  } = useQuery({
    queryKey: ['project-link-requests', projectId],
    queryFn: () => projectsApi.listLinkRequests(projectId, 'PENDING'),
  });

  const isLoading = isLoadingChildren || isLoadingRequests;
  const childCount = (children?.length || 0) + (pendingRequests?.length || 0);

  return (
    <div className="child-projects-section">
      <div className="child-projects-section-header">
        <h3 className="child-projects-section-title">
          <FaFolderOpen />
          子プロジェクト
          {childCount > 0 && <span className="count-badge">{childCount}</span>}
        </h3>
      </div>

      {isLoading ? (
        <div className="child-projects-loading">
          <FaSpinner className="spinner" />
          読み込み中...
        </div>
      ) : (
        <>
          {(children && children.length > 0) || (pendingRequests && pendingRequests.length > 0) ? (
            <div className="child-projects-grid">
              {pendingRequests?.map((request) => (
                <PendingRequestCard
                  key={request.id}
                  request={request}
                  parentProjectId={projectId}
                  isOwner={true}
                />
              ))}
              {children?.map((child) => (
                <ChildProjectCard key={child.id} project={child} />
              ))}
            </div>
          ) : (
            <div className="child-projects-empty">
              子プロジェクトはまだありません
            </div>
          )}
        </>
      )}

      <div className="child-project-add-area">
        <button
          className="child-project-add-btn"
          onClick={() => setShowAddOptions(!showAddOptions)}
        >
          <FaPlus className="btn-icon" />
          子プロジェクトを追加
        </button>
      </div>

      {showAddOptions && (
        <div className="child-project-add-area" style={{ marginTop: '8px' }}>
          <button
            className="child-project-add-btn"
            onClick={() => {
              // Placeholder: open ProjectCreateModal with parent_project_id
              setShowAddOptions(false);
            }}
          >
            <FaPlus className="btn-icon" />
            手動で作成
          </button>
          <button
            className="child-project-add-btn"
            onClick={() => {
              // Placeholder: trigger AI-based child project creation
              setShowAddOptions(false);
            }}
          >
            <FaWandMagicSparkles className="btn-icon" />
            AIで作成
          </button>
        </div>
      )}
    </div>
  );
}
