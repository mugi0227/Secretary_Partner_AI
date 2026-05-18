import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaCheck, FaLock, FaLockOpen, FaPlus, FaTimes } from 'react-icons/fa';
import type { Task } from '../../api/types';
import './EditableDependencies.css';

interface EditableDependenciesProps {
  value: string[] | null | undefined;
  allTasks: Task[];
  currentTaskId: string;
  onSave: (newValue: string[]) => Promise<void>;
  disabled?: boolean;
}

export function EditableDependencies({
  value,
  allTasks,
  currentTaskId,
  onSave,
  disabled = false,
}: EditableDependenciesProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [pendingValue, setPendingValue] = useState<string[]>(value || []);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);

  const handleCancel = useCallback(() => {
    setIsEditing(false);
    setPendingValue(value || []);
  }, [value]);

  useEffect(() => {
    if (isEditing) {
      setPendingValue(value || []);
      setSearchQuery('');
    }
  }, [isEditing, value]);

  // Close when clicking outside
  useEffect(() => {
    if (!isEditing) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        handleCancel();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditing, handleCancel]);

  const handleStartEdit = useCallback(() => {
    if (disabled) return;
    setIsEditing(true);
  }, [disabled]);

  const handleSave = useCallback(async () => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      await onSave(pendingValue);
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save dependencies:', error);
    } finally {
      setIsSaving(false);
    }
  }, [pendingValue, onSave, isSaving]);

  const handleToggle = useCallback((taskId: string) => {
    setPendingValue(prev => {
      if (prev.includes(taskId)) {
        return prev.filter(id => id !== taskId);
      }
      return [...prev, taskId];
    });
  }, []);

  // Get selected dependencies with task info
  const selectedDeps = (value || [])
    .map(depId => allTasks.find(t => t.id === depId))
    .filter((t): t is Task => t !== undefined);

  // Filter available tasks (exclude self, already selected can stay for toggle)
  const availableTasks = allTasks
    .filter(t => t.id !== currentTaskId)
    .filter(t => {
      if (!searchQuery.trim()) return true;
      return t.title.toLowerCase().includes(searchQuery.toLowerCase());
    });

  return (
    <div className={`editable-dependencies ${isEditing ? 'editing' : ''} ${disabled ? 'disabled' : ''}`}>
      <AnimatePresence mode="wait">
        {isEditing ? (
          <motion.div
            key="edit"
            ref={panelRef}
            className="editable-deps-edit-mode"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
          >
            <input
              type="text"
              placeholder="タスクを検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="deps-search-input"
              autoFocus
            />

            <ul className="deps-task-list">
              {availableTasks.length > 0 ? (
                availableTasks.map((task) => {
                  const isSelected = pendingValue.includes(task.id);
                  const isTaskDone = task.status === 'DONE';
                  return (
                    <li
                      key={task.id}
                      className={`deps-task-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleToggle(task.id)}
                    >
                      <div className="deps-checkbox">
                        {isSelected && <FaCheck />}
                      </div>
                      <span className={`deps-task-title ${isTaskDone ? 'done' : ''}`}>
                        {task.title}
                      </span>
                      <span className={`deps-status-badge-small ${isTaskDone ? 'completed' : 'pending'}`}>
                        {isTaskDone ? <><FaLockOpen /> 完了</> : <><FaLock /> 未完了</>}
                      </span>
                    </li>
                  );
                })
              ) : (
                <li className="deps-empty">
                  {searchQuery ? '該当するタスクがありません' : 'タスクがありません'}
                </li>
              )}
            </ul>

            <div className="editable-deps-actions">
              <button
                type="button"
                className="editable-deps-btn save"
                onClick={handleSave}
                disabled={isSaving}
                title="保存"
              >
                <FaCheck /> 保存
              </button>
              <button
                type="button"
                className="editable-deps-btn cancel"
                onClick={handleCancel}
                disabled={isSaving}
                title="キャンセル"
              >
                <FaTimes /> キャンセル
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="view"
            className="editable-deps-view-mode"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {selectedDeps.length > 0 ? (
              <ul className="sidebar-dependencies">
                {selectedDeps.map((dep) => {
                  const isCompleted = dep.status === 'DONE';
                  return (
                    <li
                      key={dep.id}
                      className={`sidebar-dep-item ${isCompleted ? 'completed' : ''}`}
                      title={dep.title}
                    >
                      <div className={`dep-status-badge ${isCompleted ? 'completed' : 'pending'}`}>
                        {isCompleted ? <FaLockOpen /> : <FaLock />}
                      </div>
                      <div className="dep-content">
                        <span className="dep-title">{dep.title}</span>
                        <span className="dep-status-label">
                          {isCompleted ? '完了' : '未完了'}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="empty-hint">依存関係なし</p>
            )}
            {!disabled && (
              <button
                type="button"
                className="editable-deps-add-btn"
                onClick={handleStartEdit}
                title="依存関係を編集"
              >
                <FaPlus /> 依存タスクを追加
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
