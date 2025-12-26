import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaStar, FaPlus } from 'react-icons/fa6';
import { useProjects } from '../hooks/useProjects';
import { ProjectCreateModal } from '../components/projects/ProjectCreateModal';
import './ProjectsPage.css';

export function ProjectsPage() {
  const navigate = useNavigate();
  const { projects, isLoading, error, refetch } = useProjects();
  const [showCreateModal, setShowCreateModal] = useState(false);

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
        <h2 className="page-title">Projects</h2>
        <div className="header-actions">
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
              onClick={() => navigate(`/projects/${project.id}`)}
            >
              <div className="project-header">
                <h3 className="project-name">{project.name}</h3>
                <span
                  className={`project-status status-${project.status.toLowerCase()}`}
                >
                  {project.status}
                </span>
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
    </div>
  );
}
