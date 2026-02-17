import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaStar, FaPlus, FaLock, FaUsers, FaChevronRight } from 'react-icons/fa6';
import { useProjects } from '../hooks/useProjects';
import { ProjectCreateModal } from '../components/projects/ProjectCreateModal';
import { usePageTour } from '../hooks/usePageTour';
import { PageTour } from '../components/onboarding/PageTour';
import { TourHelpButton } from '../components/onboarding/TourHelpButton';
import type { ProjectWithTaskCount } from '../api/types';
import './ProjectsPage.css';

export function ProjectsPage() {
  const navigate = useNavigate();
  const { projects: allProjects, isLoading, error, refetch } = useProjects();
  const [showCreateModal, setShowCreateModal] = useState(false);

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
          <span className="project-total">全{projects.length}件</span>
          <button className="button button-primary" onClick={() => setShowCreateModal(true)}>
            <FaPlus /> 新規プロジェクト
          </button>
        </div>
      </div>

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
            <div
              key={project.id}
              className="project-card"
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

              {/* Priority display */}
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

              {/* Compact child project display */}
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
          ))
        )}
      </div>

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
