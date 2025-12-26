import { useState, useMemo, type FormEvent } from 'react';
import { FaTimes, FaSave, FaLock } from 'react-icons/fa';
import { motion } from 'framer-motion';
import { useProjects } from '../../hooks/useProjects';
import type { Task, TaskCreate, TaskUpdate, Priority, EnergyLevel } from '../../api/types';
import './TaskFormModal.css';

interface TaskFormModalProps {
  task?: Task;
  initialData?: Partial<TaskCreate>;
  allTasks?: Task[];
  onClose: () => void;
  onSubmit: (data: TaskCreate | TaskUpdate) => void;
  isSubmitting?: boolean;
}

export function TaskFormModal({ task, initialData, allTasks = [], onClose, onSubmit, isSubmitting }: TaskFormModalProps) {
  const { projects } = useProjects();
  const isEditMode = !!task;

  const [formData, setFormData] = useState({
    title: task?.title || initialData?.title || '',
    description: task?.description || initialData?.description || '',
    importance: task?.importance || initialData?.importance || 'MEDIUM' as Priority,
    urgency: task?.urgency || initialData?.urgency || 'MEDIUM' as Priority,
    estimated_minutes: task?.estimated_minutes?.toString() || initialData?.estimated_minutes?.toString() || '',
    due_date: task?.due_date ? new Date(task.due_date).toISOString().slice(0, 16) : (initialData?.due_date ? new Date(initialData.due_date).toISOString().slice(0, 16) : ''),
    project_id: task?.project_id || initialData?.project_id || '',
    dependency_ids: task?.dependency_ids || initialData?.dependency_ids || [] as string[],
    energy_level: task?.energy_level || initialData?.energy_level || 'LOW' as EnergyLevel,
  });

  // Filter available tasks for dependencies (exclude self and completed tasks)
  const availableDependencyTasks = useMemo(() => {
    return allTasks.filter(t =>
      t.id !== task?.id && // Exclude self
      t.status !== 'DONE'  // Exclude completed tasks
    );
  }, [allTasks, task?.id]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    const submitData: TaskCreate | TaskUpdate = {
      title: formData.title,
      description: formData.description || undefined,
      importance: formData.importance,
      urgency: formData.urgency,
      energy_level: formData.energy_level,
      estimated_minutes: formData.estimated_minutes ? parseInt(formData.estimated_minutes) : undefined,
      due_date: formData.due_date || undefined,
      project_id: formData.project_id || undefined,
      dependency_ids: formData.dependency_ids.length > 0 ? formData.dependency_ids : undefined,
    };

    onSubmit(submitData);
  };

  const handleToggleDependency = (taskId: string) => {
    setFormData(prev => ({
      ...prev,
      dependency_ids: prev.dependency_ids.includes(taskId)
        ? prev.dependency_ids.filter(id => id !== taskId)
        : [...prev.dependency_ids, taskId]
    }));
  };

  return (
    <motion.div
      className="modal-overlay"
      onClick={onClose}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="task-form-modal"
        onClick={(e) => e.stopPropagation()}
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 10 }}
        transition={{ type: "spring", damping: 30, stiffness: 450, mass: 0.8 }}
      >
        <div className="modal-header">
          <h2>{isEditMode ? 'タスク編集' : '新規タスク作成'}</h2>
          <button className="close-btn" onClick={onClose}>
            <FaTimes />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="task-form">
          {/* Title */}
          <div className="form-group">
            <label htmlFor="title">タスク名 *</label>
            <input
              type="text"
              id="title"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="例: 確定申告の書類を集める"
              required
              autoFocus
            />
          </div>

          {/* Description */}
          <div className="form-group">
            <label htmlFor="description">説明</label>
            <textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="詳細や補足情報を入力..."
              rows={3}
            />
          </div>

          {/* Priority Row */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="importance">重要度</label>
              <select
                id="importance"
                value={formData.importance}
                onChange={(e) => setFormData({ ...formData, importance: e.target.value as Priority })}
              >
                <option value="HIGH">高</option>
                <option value="MEDIUM">中</option>
                <option value="LOW">低</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="urgency">緊急度</label>
              <select
                id="urgency"
                value={formData.urgency}
                onChange={(e) => setFormData({ ...formData, urgency: e.target.value as Priority })}
              >
                <option value="HIGH">高</option>
                <option value="MEDIUM">中</option>
                <option value="LOW">低</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="energy_level">エネルギー</label>
              <select
                id="energy_level"
                value={formData.energy_level}
                onChange={(e) => setFormData({ ...formData, energy_level: e.target.value as EnergyLevel })}
              >
                <option value="LOW">軽い</option>
                <option value="HIGH">重い</option>
              </select>
            </div>
          </div>

          {/* Time & Date Row */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="estimated_minutes">見積時間（分）</label>
              <input
                type="number"
                id="estimated_minutes"
                value={formData.estimated_minutes}
                onChange={(e) => setFormData({ ...formData, estimated_minutes: e.target.value })}
                placeholder="15"
                min="1"
              />
            </div>

            <div className="form-group">
              <label htmlFor="due_date">期限</label>
              <input
                type="datetime-local"
                id="due_date"
                value={formData.due_date}
                onChange={(e) => setFormData({ ...formData, due_date: e.target.value })}
              />
            </div>
          </div>

          {/* Project */}
          <div className="form-group">
            <label htmlFor="project_id">プロジェクト</label>
            <select
              id="project_id"
              value={formData.project_id}
              onChange={(e) => setFormData({ ...formData, project_id: e.target.value })}
            >
              <option value="">なし（Inbox）</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>

          {/* Dependencies */}
          {availableDependencyTasks.length > 0 && (
            <div className="form-group">
              <label>
                <FaLock style={{ marginRight: '0.5rem' }} />
                依存関係（先に完了が必要なタスク）
              </label>
              <p className="field-hint">このタスクを開始する前に完了が必要なタスクを選択してください</p>
              <div className="dependency-checkboxes">
                {availableDependencyTasks.map((depTask) => (
                  <label key={depTask.id} className="dependency-checkbox-item">
                    <input
                      type="checkbox"
                      checked={formData.dependency_ids.includes(depTask.id)}
                      onChange={() => handleToggleDependency(depTask.id)}
                    />
                    <span className="checkbox-label">{depTask.title}</span>
                    <span className={`checkbox-status status-${depTask.status.toLowerCase()}`}>
                      {depTask.status === 'TODO' ? '未着手' :
                        depTask.status === 'IN_PROGRESS' ? '進行中' :
                          depTask.status === 'WAITING' ? '待機中' : depTask.status}
                    </span>
                  </label>
                ))}
              </div>
              {formData.dependency_ids.length > 0 && (
                <p className="selected-count">{formData.dependency_ids.length}個のタスクに依存</p>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="form-actions">
            <button type="button" onClick={onClose} className="cancel-btn">
              キャンセル
            </button>
            <button type="submit" className="submit-btn" disabled={isSubmitting || !formData.title}>
              <FaSave />
              {isSubmitting ? '保存中...' : (isEditMode ? '更新' : '作成')}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
