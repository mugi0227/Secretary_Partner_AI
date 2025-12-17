import { useState } from 'react';
import { FaTimes, FaFire, FaClock, FaLeaf, FaBatteryFull, FaBatteryQuarter, FaCheckCircle, FaCircle, FaArrowLeft, FaBookOpen } from 'react-icons/fa';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Task } from '../../api/types';
import './TaskDetailModal.css';

interface TaskDetailModalProps {
  task: Task;
  subtasks?: Task[];
  onClose: () => void;
}

// Helper to extract guide from description
function extractGuide(description?: string | null): { mainDescription: string; guide: string } {
  if (!description) return { mainDescription: '', guide: '' };

  // Look for guide separator
  const guideSeparator = '---\n\n## 進め方ガイド';
  const guideStartOnly = '## 進め方ガイド';

  let separatorIndex = description.indexOf(guideSeparator);
  if (separatorIndex !== -1) {
    return {
      mainDescription: description.substring(0, separatorIndex).trim(),
      guide: description.substring(separatorIndex + guideSeparator.length).trim(),
    };
  }

  // Check if it starts with guide directly
  if (description.startsWith(guideStartOnly)) {
    return {
      mainDescription: '',
      guide: description.substring(guideStartOnly.length).trim(),
    };
  }

  return { mainDescription: description, guide: '' };
}

export function TaskDetailModal({ task, subtasks = [], onClose }: TaskDetailModalProps) {
  const [selectedSubtask, setSelectedSubtask] = useState<Task | null>(null);
  const getPriorityIcon = (level: string) => {
    switch (level) {
      case 'HIGH':
        return <FaFire />;
      case 'MEDIUM':
        return <FaClock />;
      case 'LOW':
        return <FaLeaf />;
      default:
        return <FaLeaf />;
    }
  };

  const getEnergyIcon = (level: string) => {
    return level === 'HIGH' ? <FaBatteryFull /> : <FaBatteryQuarter />;
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      TODO: '未着手',
      IN_PROGRESS: '進行中',
      WAITING: '待機中',
      DONE: '完了',
    };
    return labels[status] || status;
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const selectedGuide = selectedSubtask ? extractGuide(selectedSubtask.description) : null;
  const taskDescription = extractGuide(task.description);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal-container ${selectedSubtask ? 'split-view' : ''}`} onClick={(e) => e.stopPropagation()}>
        {/* Main Task Panel */}
        <div className="modal-content">
          <div className="modal-header">
            <h2>{task.title}</h2>
            <button className="close-btn" onClick={onClose}>
              <FaTimes />
            </button>
          </div>

          <div className="modal-body">
          {/* Status */}
          <div className="detail-section">
            <h3>ステータス</h3>
            <span className={`status-badge status-${task.status.toLowerCase()}`}>
              {getStatusLabel(task.status)}
            </span>
          </div>

          {/* Description */}
          {task.description && (
            <div className="detail-section">
              <h3>説明</h3>
              {taskDescription.mainDescription && (
                <div className="description-text markdown-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {taskDescription.mainDescription}
                  </ReactMarkdown>
                </div>
              )}
              {taskDescription.guide && (
                <div className="task-guide markdown-content">
                  <h4>進め方ガイド</h4>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {taskDescription.guide}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}

          {/* Metadata */}
          <div className="detail-section">
            <h3>優先度・エネルギー</h3>
            <div className="metadata-grid">
              <div className="metadata-item">
                <span className="metadata-label">重要度</span>
                <span className={`meta-badge importance-${task.importance.toLowerCase()}`}>
                  {getPriorityIcon(task.importance)}
                  <span>{task.importance}</span>
                </span>
              </div>
              <div className="metadata-item">
                <span className="metadata-label">緊急度</span>
                <span className={`meta-badge urgency-${task.urgency.toLowerCase()}`}>
                  {getPriorityIcon(task.urgency)}
                  <span>{task.urgency}</span>
                </span>
              </div>
              <div className="metadata-item">
                <span className="metadata-label">必要エネルギー</span>
                <span className={`meta-badge energy-${task.energy_level.toLowerCase()}`}>
                  {getEnergyIcon(task.energy_level)}
                  <span>{task.energy_level}</span>
                </span>
              </div>
              {task.estimated_minutes && (
                <div className="metadata-item">
                  <span className="metadata-label">見積もり時間</span>
                  <span className="metadata-value">{task.estimated_minutes}分</span>
                </div>
              )}
            </div>
          </div>

          {/* Due Date */}
          {task.due_date && (
            <div className="detail-section">
              <h3>期限</h3>
              <p className="due-date">{formatDate(task.due_date)}</p>
            </div>
          )}

          {/* Subtasks */}
          {subtasks.length > 0 && (
            <div className="detail-section">
              <h3>サブタスク ({subtasks.length}件)</h3>
              <ul className="subtasks-list">
                {subtasks.map((subtask) => {
                  const { guide } = extractGuide(subtask.description);
                  const hasGuide = guide.length > 0;
                  return (
                    <li
                      key={subtask.id}
                      className={`subtask-item ${hasGuide ? 'has-guide' : ''} ${selectedSubtask?.id === subtask.id ? 'selected' : ''}`}
                      onClick={() => hasGuide && setSelectedSubtask(subtask)}
                    >
                      {subtask.status === 'DONE' ? (
                        <FaCheckCircle className="subtask-icon done" />
                      ) : (
                        <FaCircle className="subtask-icon" />
                      )}
                      <span className={subtask.status === 'DONE' ? 'subtask-title done' : 'subtask-title'}>
                        {subtask.title}
                      </span>
                      {hasGuide && (
                        <FaBookOpen className="subtask-guide-icon" title="進め方ガイドあり" />
                      )}
                      {subtask.estimated_minutes && (
                        <span className="subtask-time">{subtask.estimated_minutes}分</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Meta Info */}
          <div className="detail-section meta-info">
            <div className="meta-info-row">
              <span className="meta-info-label">作成者:</span>
              <span className="meta-info-value">{task.created_by === 'AGENT' ? 'AI秘書' : 'ユーザー'}</span>
            </div>
            <div className="meta-info-row">
              <span className="meta-info-label">作成日時:</span>
              <span className="meta-info-value">{formatDate(task.created_at)}</span>
            </div>
            <div className="meta-info-row">
              <span className="meta-info-label">更新日時:</span>
              <span className="meta-info-value">{formatDate(task.updated_at)}</span>
            </div>
          </div>
        </div>
        </div>

        {/* Guide Panel */}
        {selectedSubtask && selectedGuide && (
          <div className="guide-panel">
            <div className="guide-header">
              <button className="back-btn" onClick={() => setSelectedSubtask(null)}>
                <FaArrowLeft />
              </button>
              <h3>進め方ガイド</h3>
            </div>
            <div className="guide-content">
              <div className="guide-task-title">
                <FaBookOpen />
                <span>{selectedSubtask.title}</span>
              </div>
              {selectedGuide.mainDescription && (
                <div className="guide-description">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {selectedGuide.mainDescription}
                  </ReactMarkdown>
                </div>
              )}
              <div className="guide-steps markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {selectedGuide.guide}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
