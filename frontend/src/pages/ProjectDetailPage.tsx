import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FaArrowLeft, FaStar, FaEdit, FaCheckCircle, FaBullseye, FaChartLine, FaLightbulb, FaBookOpen } from 'react-icons/fa';
import { motion } from 'framer-motion';
import { getProject } from '../api/projects';
import { useTasks } from '../hooks/useTasks';
import { KanbanBoard } from '../components/tasks/KanbanBoard';
import { ProjectDetailModal } from '../components/projects/ProjectDetailModal';
import { TaskDetailModal } from '../components/tasks/TaskDetailModal';
import type { ProjectWithTaskCount, Task, TaskStatus } from '../api/types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import './ProjectDetailPage.css';

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectWithTaskCount | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [openedParentTask, setOpenedParentTask] = useState<Task | null>(null);

  // Fetch tasks for this project
  const { tasks, isLoading: tasksLoading, refetch: refetchTasks, updateTask } = useTasks(projectId);

  // Fetch project details
  useEffect(() => {
    if (!projectId) return;

    const fetchProject = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await getProject(projectId);
        setProject(data);
      } catch (err) {
        console.error('Failed to fetch project:', err);
        setError('プロジェクトの取得に失敗しました');
      } finally {
        setIsLoading(false);
      }
    };

    fetchProject();
  }, [projectId]);

  const handleTaskClick = (task: Task) => {
    if (task.parent_id) {
      const parent = tasks.find(t => t.id === task.parent_id);
      if (parent) {
        setOpenedParentTask(parent);
        setSelectedTask(task);
      } else {
        setSelectedTask(task);
        setOpenedParentTask(null);
      }
    } else {
      setSelectedTask(task);
      setOpenedParentTask(null);
    }
  };

  const handleUpdate = () => {
    if (!projectId) return;
    // Refetch project data
    getProject(projectId).then(setProject).catch(console.error);
    refetchTasks();
    setShowEditModal(false);
  };

  if (error) {
    return (
      <div className="project-detail-page">
        <div className="error-state">
          <p>{error}</p>
          <button className="back-button" onClick={() => navigate('/projects')}>
            プロジェクト一覧へ戻る
          </button>
        </div>
      </div>
    );
  }

  if (isLoading || !project) {
    return (
      <div className="project-detail-page">
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

  const completionRate = project.total_tasks > 0
    ? Math.round((project.completed_tasks / project.total_tasks) * 100)
    : 0;

  return (
    <motion.div
      className="project-detail-page"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Header */}
      <div className="project-detail-header">
        <button className="back-button" onClick={() => navigate('/projects')}>
          <FaArrowLeft /> プロジェクト一覧
        </button>

        <div className="header-actions">
          <button className="back-button" onClick={() => setShowEditModal(true)}>
            <FaEdit /> 編集
          </button>
        </div>
      </div>

      {/* Hero Section */}
      <div className="project-info-hero">
        <div className="hero-main">
          <div className="project-title-row">
            <div>
              <h1 className="project-title">{project.name}</h1>
              {project.description && (
                <p className="project-description">{project.description}</p>
              )}
            </div>
            <span className={`project-status status-${project.status.toLowerCase()}`}>
              {project.status}
            </span>
          </div>

          <div className="hero-stats-row">
            <div className="hero-stat">
              <span className="label">優先度</span>
              <div className="priority-display">
                {renderStars(project.priority)}
                <span className="value">{project.priority}/10</span>
              </div>
            </div>
            <div className="hero-stat">
              <span className="label">進捗</span>
              <span className="value">{completionRate}%</span>
            </div>
            <div className="hero-stat">
              <span className="label">タスク</span>
              <span className="value">{project.completed_tasks} / {project.total_tasks}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="project-details-grid">
        <div className="details-main-column">
          {/* Goals Section */}
          {project.goals && project.goals.length > 0 && (
            <div className="detail-section">
              <div className="section-header">
                <FaBullseye className="section-icon" />
                <h3 className="section-title">プロジェクト目標</h3>
              </div>
              <ul className="goals-list">
                {project.goals.map((goal, index) => (
                  <li key={index} className="goal-item">
                    <FaCheckCircle className="goal-icon" />
                    {goal}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Context/README Section */}
          {project.context && (
            <div className="detail-section">
              <div className="section-header">
                <FaBookOpen className="section-icon" />
                <h3 className="section-title">README / コンテキスト</h3>
              </div>
              <div className="context-content markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                  {project.context}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>

        <div className="details-side-column">
          {/* KPI Section */}
          {project.kpi_config && project.kpi_config.metrics && project.kpi_config.metrics.length > 0 && (
            <div className="detail-section">
              <div className="section-header">
                <FaChartLine className="section-icon" />
                <h3 className="section-title">KPI 指標</h3>
              </div>
              <div className="kpi-grid">
                {project.kpi_config.metrics.map((metric, index) => {
                  const current = metric.current ?? 0;
                  const target = metric.target ?? 0;
                  const progress = target > 0
                    ? Math.min((current / target) * 100, 100)
                    : 0;
                  return (
                    <div key={index} className="kpi-card">
                      <div className="kpi-info">
                        <span className="kpi-name">{metric.label}</span>
                        <div className="kpi-values">
                          <span className="kpi-current">{current}</span>
                          <span className="kpi-target">/ {target}</span>
                          <span className="kpi-unit">{metric.unit}</span>
                        </div>
                      </div>
                      <div className="kpi-progress-container">
                        <div className="kpi-progress-bar">
                          <div
                            className="kpi-progress-fill"
                            style={{ width: `${progress}%` }}
                          ></div>
                        </div>
                        <span className="kpi-percentage">{Math.round(progress)}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Key Points Section */}
          {project.key_points && project.key_points.length > 0 && (
            <div className="detail-section">
              <div className="section-header">
                <FaLightbulb className="section-icon" />
                <h3 className="section-title">重要なポイント</h3>
              </div>
              <ul className="key-points-list">
                {project.key_points.map((point, index) => (
                  <li key={index} className="key-point-item">{point}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Tasks Section */}
      <div className="tasks-section">
        <h2 className="section-title">タスクボード</h2>
        {tasksLoading ? (
          <div className="loading-state">タスクを読み込み中...</div>
        ) : (
          <KanbanBoard
            tasks={tasks}
            onUpdateTask={(id: string, status: TaskStatus) => {
              updateTask(id, { status });
              refetchTasks();
            }}
            onTaskClick={handleTaskClick}
          />
        )}
      </div>

      {/* Project Edit Modal */}
      {showEditModal && (
        <ProjectDetailModal
          project={project}
          onClose={() => setShowEditModal(false)}
          onUpdate={handleUpdate}
        />
      )}

      {/* Task Detail Modal */}
      {selectedTask && (
        <TaskDetailModal
          task={openedParentTask || selectedTask}
          subtasks={tasks.filter(t => t.parent_id === (openedParentTask?.id || selectedTask.id))}
          allTasks={tasks}
          initialSubtask={openedParentTask ? selectedTask : null}
          onClose={() => {
            setSelectedTask(null);
            setOpenedParentTask(null);
          }}
          onEdit={() => {
            // Task editing is handled elsewhere or can be added here
            refetchTasks();
          }}
        />
      )}
    </motion.div>
  );
}
