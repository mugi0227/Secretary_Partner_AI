import { useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaStar, FaPlus, FaLock, FaUsers, FaChevronRight, FaGrip, FaSitemap } from 'react-icons/fa6';
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
  DragStartEvent,
  DragOverlay,
  useDraggable,
  useDroppable,
} from '@dnd-kit/core';
import { useProjects } from '../hooks/useProjects';
import { projectsApi } from '../api/projects';
import { ProjectCreateModal } from '../components/projects/ProjectCreateModal';
import { usePageTour } from '../hooks/usePageTour';
import { PageTour } from '../components/onboarding/PageTour';
import { TourHelpButton } from '../components/onboarding/TourHelpButton';
import type { ProjectWithTaskCount } from '../api/types';
import { userStorage } from '../utils/userStorage';
import { ProjectTreeView } from '../components/projects/ProjectTreeView';
import '../components/projects/ProjectDetailModal.css';
import './ProjectsPage.css';

function DraggableProjectCard({
  project,
  children,
}: {
  project: ProjectWithTaskCount;
  children: React.ReactNode;
}) {
  const {
    attributes,
    listeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({
    id: `drag-${project.id}`,
    data: { projectId: project.id, projectName: project.name },
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop-${project.id}`,
    data: { projectId: project.id, projectName: project.name },
  });

  const combinedRef = useCallback(
    (node: HTMLElement | null) => {
      setDragRef(node);
      setDropRef(node);
    },
    [setDragRef, setDropRef],
  );

  return (
    <div
      ref={combinedRef}
      className={`project-card${isDragging ? ' dragging' : ''}${isOver ? ' drop-target' : ''}`}
      {...attributes}
      {...listeners}
    >
      {children}
    </div>
  );
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const { projects: allProjects, isLoading, error, refetch } = useProjects();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [activeProject, setActiveProject] = useState<ProjectWithTaskCount | null>(null);
  const [linkConfirmation, setLinkConfirmation] = useState<{
    childId: string;
    childName: string;
    parentId: string;
    parentName: string;
  } | null>(null);
  const [linkError, setLinkError] = useState('');
  const [isLinking, setIsLinking] = useState(false);
  const [viewMode, setViewMode] = useState<'grid' | 'tree'>(() => {
    return (userStorage.get('projectsPageView') as 'grid' | 'tree') || 'grid';
  });

  const handleViewModeChange = useCallback((mode: 'grid' | 'tree') => {
    setViewMode(mode);
    userStorage.set('projectsPageView', mode);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 10 },
    }),
  );

  // Build tree: top-level projects with their children
  const { topLevelProjects, childrenMap } = useMemo(() => {
    const cMap = new Map<string, ProjectWithTaskCount[]>();
    const topLevel: ProjectWithTaskCount[] = [];
    for (const p of allProjects) {
      if (p.parent_project_id) {
        const siblings = cMap.get(p.parent_project_id) || [];
        siblings.push(p);
        cMap.set(p.parent_project_id, siblings);
      } else {
        topLevel.push(p);
      }
    }
    return { topLevelProjects: topLevel, childrenMap: cMap };
  }, [allProjects]);

  const projects = topLevelProjects;
  const tour = usePageTour('projects');

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const projectId = event.active.data.current?.projectId;
      const project = allProjects.find((p) => p.id === projectId);
      setActiveProject(project || null);
    },
    [allProjects],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveProject(null);
      const { active, over } = event;
      if (!over) return;

      const draggedId = active.data.current?.projectId;
      const targetId = over.data.current?.projectId;
      if (!draggedId || !targetId || draggedId === targetId) return;

      const draggedProject = allProjects.find((p) => p.id === draggedId);
      const targetProject = allProjects.find((p) => p.id === targetId);
      if (draggedProject && targetProject) {
        setLinkConfirmation({
          childId: draggedId,
          childName: draggedProject.name,
          parentId: targetId,
          parentName: targetProject.name,
        });
      }
    },
    [allProjects],
  );

  const handleConfirmLink = async () => {
    if (!linkConfirmation) return;
    setIsLinking(true);
    setLinkError('');
    try {
      await projectsApi.createLinkRequest(linkConfirmation.parentId, {
        child_project_id: linkConfirmation.childId,
        parent_project_id: linkConfirmation.parentId,
      });
      refetch();
      setLinkConfirmation(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '紐付けリクエストの送信に失敗しました';
      setLinkError(message);
    } finally {
      setIsLinking(false);
    }
  };

  if (error) {
    return (
      <div className="projects-page">
        <div className="error-state">
          プロジェクトの取得に失敗しました。バックエンドサーバーが起動しているか確認してください。
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="projects-page">
        <div className="loading-state">読み込み中...</div>
      </div>
    );
  }

  const renderStars = (priority: number) => {
    return (
      <div className="priority-stars">
        {[...Array(10)].map((_, i) => (
          <FaStar
            key={i}
            className={`star ${i < priority ? 'star-filled' : 'star-empty'}`}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2 className="page-title">プロジェクト</h2>
        <div className="header-actions">
          <TourHelpButton onClick={tour.startTour} />
          <div className="projects-view-toggle">
            <button
              className={`projects-view-btn${viewMode === 'grid' ? ' active' : ''}`}
              onClick={() => handleViewModeChange('grid')}
              title="グリッド表示"
            >
              <FaGrip />
            </button>
            <button
              className={`projects-view-btn${viewMode === 'tree' ? ' active' : ''}`}
              onClick={() => handleViewModeChange('tree')}
              title="ツリー表示"
            >
              <FaSitemap />
            </button>
          </div>
          <span className="project-total">
            全{viewMode === 'grid' ? projects.length : allProjects.length}件
          </span>
          <button className="button button-primary" onClick={() => setShowCreateModal(true)}>
            <FaPlus /> 新規プロジェクト
          </button>
        </div>
      </div>

      {viewMode === 'tree' ? (
        <ProjectTreeView
          topLevelProjects={topLevelProjects}
          childrenMap={childrenMap}
          allProjects={allProjects}
        />
      ) : (
      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="projects-grid">
          {projects.length === 0 ? (
            <div className="empty-state">
              <p className="empty-icon">📁</p>
              <p className="empty-title">プロジェクトがありません</p>
              <p className="empty-hint">
                チャットでプロジェクトを作成できます
              </p>
            </div>
          ) : (
            projects.map((project) => (
              <DraggableProjectCard key={project.id} project={project}>
                <div
                  className="project-card-inner"
                  onClick={() => navigate(`/projects/${project.id}/v2`)}
                >
                  <div className="project-header">
                    <h3 className="project-name">{project.name}</h3>
                    <div className="project-badges">
                      <span
                        className={`project-visibility visibility-${project.visibility?.toLowerCase() || 'private'}`}
                      >
                        {project.visibility === 'TEAM' ? <FaUsers /> : <FaLock />}
                        {project.visibility === 'TEAM' ? 'チーム' : '個人'}
                      </span>
                      <span
                        className={`project-status status-${project.status.toLowerCase()}`}
                      >
                        {project.status}
                      </span>
                    </div>
                  </div>

                  {project.description && (
                    <p className="project-description">{project.description}</p>
                  )}

                  <div className="project-priority">
                    <span className="priority-label">優先度:</span>
                    {renderStars(project.priority)}
                    <span className="priority-value">{project.priority}/10</span>
                  </div>

                  <div className="project-stats">
                    <div className="stat-item">
                      <span className="stat-label">合計</span>
                      <span className="stat-value">{project.total_tasks}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">進行中</span>
                      <span className="stat-value stat-progress">
                        {project.in_progress_tasks}
                      </span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">完了</span>
                      <span className="stat-value stat-done">
                        {project.completed_tasks}
                      </span>
                    </div>
                    {project.unassigned_tasks > 0 && (
                      <div className="stat-item stat-unassigned">
                        <span className="stat-label">未割当</span>
                        <span className="stat-value stat-warning">
                          {project.unassigned_tasks}
                        </span>
                      </div>
                    )}
                  </div>

                  {project.total_tasks > 0 && (
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{
                          width: `${
                            (project.completed_tasks / project.total_tasks) * 100
                          }%`,
                        }}
                      ></div>
                    </div>
                  )}

                  {childrenMap.has(project.id) && (
                    <div style={{ marginTop: '8px', borderTop: '1px solid var(--border-color, #e5e7eb)', paddingTop: '8px' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted, #6b7280)', marginBottom: '4px' }}>
                        子プロジェクト ({childrenMap.get(project.id)!.length}件)
                      </div>
                      {childrenMap.get(project.id)!.slice(0, 3).map((child) => {
                        const childProgress = child.total_tasks > 0
                          ? Math.round((child.completed_tasks / child.total_tasks) * 100)
                          : 0;
                        return (
                          <div
                            key={child.id}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '8px',
                              padding: '2px 0', fontSize: '0.8rem', cursor: 'pointer',
                            }}
                            onClick={(e) => { e.stopPropagation(); navigate(`/projects/${child.id}/v2`); }}
                          >
                            <FaChevronRight style={{ fontSize: '0.6rem', color: 'var(--text-muted, #999)' }} />
                            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {child.name}
                            </span>
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted, #999)' }}>
                              {childProgress}%
                            </span>
                          </div>
                        );
                      })}
                      {childrenMap.get(project.id)!.length > 3 && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted, #999)', paddingTop: '2px' }}>
                          他 {childrenMap.get(project.id)!.length - 3} 件
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </DraggableProjectCard>
            ))
          )}
        </div>

        <DragOverlay>
          {activeProject ? (
            <div className="project-card drag-overlay">
              <h3 className="project-name">{activeProject.name}</h3>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
      )}

      {linkConfirmation && (
        <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && setLinkConfirmation(null)}>
          <div className="modal-content project-create-modal" style={{ maxWidth: '450px' }}>
            <div className="modal-header">
              <h2>プロジェクトの紐付け</h2>
            </div>
            <div className="modal-body">
              <p>
                「<strong>{linkConfirmation.childName}</strong>」を
                「<strong>{linkConfirmation.parentName}</strong>」の
                子プロジェクトにしますか？
              </p>
              {linkError && (
                <div style={{
                  padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-md, 8px)',
                  background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#dc2626', fontSize: '0.875rem', marginTop: '0.5rem',
                }}>
                  {linkError}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="button button-secondary" onClick={() => { setLinkConfirmation(null); setLinkError(''); }}>
                キャンセル
              </button>
              <button
                className="button button-primary"
                onClick={handleConfirmLink}
                disabled={isLinking}
              >
                {isLinking ? '送信中...' : '紐付けリクエストを送信'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreateModal && (
        <ProjectCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreate={() => {
            refetch();
            setShowCreateModal(false);
          }}
        />
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
