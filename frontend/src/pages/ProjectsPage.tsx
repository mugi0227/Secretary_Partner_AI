import { useProjects } from '../hooks/useProjects';
import './ProjectsPage.css';

export function ProjectsPage() {
  const { projects, isLoading, error } = useProjects();

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

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2 className="page-title">Projects</h2>
        <div className="header-actions">
          <span className="project-total">全{projects.length}件</span>
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
            <div key={project.id} className="project-card">
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
    </div>
  );
}
