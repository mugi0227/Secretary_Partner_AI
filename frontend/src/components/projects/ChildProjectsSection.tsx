import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../../api/projects';
import type { ProjectWithTaskCount, ProjectLinkRequest } from '../../api/types';
import { useNavigate } from 'react-router-dom';
import { FaPlus, FaWandMagicSparkles, FaSpinner, FaCheck, FaXmark, FaFolderOpen, FaLink, FaArrowRight } from 'react-icons/fa6';
import { ProjectCreateModal } from './ProjectCreateModal';
import { ChildProjectLinkModal } from './ChildProjectLinkModal';
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
          onClick={() => navigate(`/projects/${project.id}/v2`)}
          role="link"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && navigate(`/projects/${project.id}/v2`)}
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

  const approvalLabel = request.parent_approved && !request.child_approved
    ? '子オーナー承認待ち'
    : !request.parent_approved && request.child_approved
    ? '親オーナー承認待ち'
    : '承認待ち';

  return (
    <div className="child-project-card pending-request">
      <div className="child-project-info">
        <span className="child-project-name" style={{ color: 'var(--text-main)', cursor: 'default' }}>
          {childProject?.name || '読み込み中...'}
        </span>
        <div className="child-project-meta">
          <span className="child-project-status-badge status-pending">{approvalLabel}</span>
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

function IncomingRequestCard({
  request,
  childProjectId,
}: {
  request: ProjectLinkRequest;
  childProjectId: string;
}) {
  const queryClient = useQueryClient();

  const { data: parentProject } = useQuery({
    queryKey: ['project', request.parent_project_id],
    queryFn: () => projectsApi.getById(request.parent_project_id),
  });

  const approveMutation = useMutation({
    mutationFn: () => projectsApi.approveLinkRequest(request.parent_project_id, request.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incoming-link-requests', childProjectId] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => projectsApi.rejectLinkRequest(request.parent_project_id, request.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incoming-link-requests', childProjectId] });
    },
  });

  const isProcessing = approveMutation.isPending || rejectMutation.isPending;

  const approvalLabel = request.parent_approved && !request.child_approved
    ? 'あなたの承認待ち'
    : !request.parent_approved && request.child_approved
    ? '親オーナー承認待ち'
    : '承認待ち';

  return (
    <div className="child-project-card pending-request incoming-request">
      <div className="child-project-info">
        <div className="incoming-request-label">
          <FaArrowRight style={{ fontSize: '0.65rem' }} />
          親プロジェクトへの紐付けリクエスト
        </div>
        <span className="child-project-name" style={{ color: 'var(--text-main)', cursor: 'default' }}>
          {parentProject?.name || '読み込み中...'}
        </span>
        <div className="child-project-meta">
          <span className="child-project-status-badge status-pending">{approvalLabel}</span>
        </div>
      </div>
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
    </div>
  );
}

export function ChildProjectsSection({ projectId, projectName }: ChildProjectsSectionProps) {
  const queryClient = useQueryClient();
  const [showAddOptions, setShowAddOptions] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);

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

  const {
    data: incomingRequests,
    isLoading: isLoadingIncoming,
  } = useQuery({
    queryKey: ['incoming-link-requests', projectId],
    queryFn: () => projectsApi.listIncomingLinkRequests(projectId, 'PENDING'),
  });

  const isLoading = isLoadingChildren || isLoadingRequests || isLoadingIncoming;
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

      {incomingRequests && incomingRequests.length > 0 && (
        <div className="child-projects-grid" style={{ marginBottom: '12px' }}>
          {incomingRequests.map((request) => (
            <IncomingRequestCard
              key={request.id}
              request={request}
              childProjectId={projectId}
            />
          ))}
        </div>
      )}

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
              setShowCreateModal(true);
              setShowAddOptions(false);
            }}
          >
            <FaPlus className="btn-icon" />
            手動で作成
          </button>
          <button
            className="child-project-add-btn"
            onClick={() => {
              const draftCard = {
                type: 'task' as const,
                title: '子プロジェクト作成',
                info: [
                  { label: '親プロジェクト', value: projectName },
                ],
                placeholder: '例: 3つのサブプロジェクトに分解して',
                promptTemplate: `プロジェクト「${projectName}」(ID: ${projectId}) の子プロジェクトを作成して。\n\n追加の指示があれば以下に記入:\n{instruction}`,
              };
              const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
              window.dispatchEvent(event);
              setShowAddOptions(false);
            }}
          >
            <FaWandMagicSparkles className="btn-icon" />
            AIで作成
          </button>
          <button
            className="child-project-add-btn"
            onClick={() => {
              setShowLinkModal(true);
              setShowAddOptions(false);
            }}
          >
            <FaLink className="btn-icon" />
            既存プロジェクトを紐付け
          </button>
        </div>
      )}

      {showCreateModal && (
        <ProjectCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreate={() => {
            queryClient.invalidateQueries({ queryKey: ['project-children', projectId] });
            setShowCreateModal(false);
          }}
          parentProjectId={projectId}
        />
      )}

      <ChildProjectLinkModal
        isOpen={showLinkModal}
        onClose={() => setShowLinkModal(false)}
        parentProjectId={projectId}
        parentProjectName={projectName}
      />
    </div>
  );
}
