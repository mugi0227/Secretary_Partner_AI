import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../../api/projects';
import type { ProjectWithTaskCount, ProjectLinkRequest } from '../../api/types';
import { useNavigate } from 'react-router-dom';
import { FaPlus, FaWandMagicSparkles, FaSpinner, FaCheck, FaXmark, FaFolderOpen, FaLink, FaArrowRight, FaUser, FaChevronDown, FaChevronRight, FaCircle } from 'react-icons/fa6';
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

const TASK_STATUS_COLORS: Record<string, string> = {
  TODO: '#94a3b8',
  IN_PROGRESS: '#0ea5e9',
  WAITING: '#f59e0b',
  DONE: '#22c55e',
};

function ChildProjectCard({
  project,
  parentProjectId,
}: {
  project: ProjectWithTaskCount;
  parentProjectId: string;
}) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const progress =
    project.total_tasks > 0
      ? Math.round((project.completed_tasks / project.total_tasks) * 100)
      : 0;

  const { data: tasks, isLoading: tasksLoading } = useQuery({
    queryKey: ['child-project-tasks', parentProjectId, project.id],
    queryFn: () => projectsApi.getChildProjectTasks(parentProjectId, project.id),
    enabled: expanded,
  });

  return (
    <div className={`child-project-card ${expanded ? 'expanded' : ''}`}>
      <div className="child-project-info">
        <div className="child-project-header-row">
          <button
            className="child-project-expand-btn"
            onClick={() => setExpanded(!expanded)}
            title={expanded ? '折りたたむ' : '展開'}
          >
            {expanded ? <FaChevronDown /> : <FaChevronRight />}
          </button>
          <span
            className="child-project-name"
            onClick={() => navigate(`/projects/${project.id}/v2`)}
            role="link"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && navigate(`/projects/${project.id}/v2`)}
          >
            {project.name}
          </span>
        </div>
        <div className="child-project-meta">
          {project.owner_display_name && (
            <span className="child-project-owner">
              <FaUser style={{ fontSize: '0.55rem' }} />
              {project.owner_display_name}
            </span>
          )}
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
        {expanded && (
          <div className="child-project-tasks">
            {tasksLoading ? (
              <div className="child-project-tasks-loading">
                <FaSpinner className="spinner" /> 読み込み中...
              </div>
            ) : tasks && tasks.length > 0 ? (
              tasks.map((task) => (
                <div key={task.id} className="child-task-row">
                  <FaCircle
                    className="child-task-status-dot"
                    style={{ color: TASK_STATUS_COLORS[task.status] || '#94a3b8' }}
                  />
                  <span className="child-task-title">{task.title}</span>
                  {task.assignee_names.length > 0 && (
                    <span className="child-task-assignee">
                      {task.assignee_names.join(', ')}
                    </span>
                  )}
                </div>
              ))
            ) : (
              <div className="child-project-tasks-empty">タスクなし</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function groupChildrenByOwner(
  children: ProjectWithTaskCount[],
): Record<string, ProjectWithTaskCount[]> {
  const grouped: Record<string, ProjectWithTaskCount[]> = {};
  for (const child of children) {
    const owner = child.owner_display_name || child.user_id;
    if (!grouped[owner]) grouped[owner] = [];
    grouped[owner].push(child);
  }
  return grouped;
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
          {request.child_project_name || '不明なプロジェクト'}
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
          {request.parent_project_name || '不明なプロジェクト'}
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

  const groupedChildren = useMemo(() => {
    if (!children || children.length === 0) return {};
    return groupChildrenByOwner(children);
  }, [children]);

  const ownerGroups = Object.entries(groupedChildren);
  const hasMultipleOwners = ownerGroups.length > 1;

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
          {pendingRequests && pendingRequests.length > 0 && (
            <div className="child-projects-grid" style={{ marginBottom: '12px' }}>
              {pendingRequests.map((request) => (
                <PendingRequestCard
                  key={request.id}
                  request={request}
                  parentProjectId={projectId}
                  isOwner={true}
                />
              ))}
            </div>
          )}
          {ownerGroups.length > 0 ? (
            hasMultipleOwners ? (
              ownerGroups.map(([ownerName, projects]) => (
                <div key={ownerName} className="child-projects-owner-group">
                  <div className="child-projects-owner-header">
                    <FaUser style={{ fontSize: '0.7rem' }} />
                    <span>{ownerName}</span>
                  </div>
                  <div className="child-projects-grid">
                    {projects.map((child) => (
                      <ChildProjectCard key={child.id} project={child} parentProjectId={projectId} />
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="child-projects-grid">
                {children?.map((child) => (
                  <ChildProjectCard key={child.id} project={child} parentProjectId={projectId} />
                ))}
              </div>
            )
          ) : (
            !pendingRequests?.length && (
              <div className="child-projects-empty">
                子プロジェクトはまだありません
              </div>
            )
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
