import { useEffect, useState } from 'react';
import { FaXmark, FaStar, FaPlus, FaTrash } from 'react-icons/fa6';
import type {
  ProjectCreate,
  ProjectKpiConfig,
  ProjectKpiMetric,
  ProjectKpiTemplate,
} from '../../api/types';
import { projectsApi } from '../../api/projects';
import './ProjectDetailModal.css';

interface ProjectCreateModalProps {
  onClose: () => void;
  onCreate: () => void;
}

export function ProjectCreateModal({ onClose, onCreate }: ProjectCreateModalProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState(5);
  const [goals, setGoals] = useState<string[]>([]);
  const [keyPoints, setKeyPoints] = useState<string[]>([]);
  const [newGoal, setNewGoal] = useState('');
  const [newKeyPoint, setNewKeyPoint] = useState('');
  const [kpiConfig, setKpiConfig] = useState<ProjectKpiConfig>({
    strategy: 'custom',
    metrics: [],
  });
  const [kpiTemplates, setKpiTemplates] = useState<ProjectKpiTemplate[]>([]);

  useEffect(() => {
    let isActive = true;
    const loadTemplates = async () => {
      setIsLoadingTemplates(true);
      try {
        const templates = await projectsApi.getKpiTemplates();
        if (isActive) {
          setKpiTemplates(templates);
        }
      } catch (error) {
        console.error('Failed to load KPI templates:', error);
      } finally {
        if (isActive) {
          setIsLoadingTemplates(false);
        }
      }
    };

    loadTemplates();
    return () => {
      isActive = false;
    };
  }, []);

  const handleCreate = async () => {
    if (!name.trim()) {
      alert('プロジェクト名を入力してください');
      return;
    }

    setIsSaving(true);
    try {
      const projectData: ProjectCreate = {
        name: name.trim(),
        description: description.trim() || undefined,
        priority,
        goals,
        key_points: keyPoints,
        kpi_config: kpiConfig,
      };
      await projectsApi.create(projectData);
      onCreate();
      onClose();
    } catch (error) {
      console.error('Failed to create project:', error);
      alert('プロジェクトの作成に失敗しました');
    } finally {
      setIsSaving(false);
    }
  };

  const addGoal = () => {
    if (newGoal.trim()) {
      setGoals([...goals, newGoal.trim()]);
      setNewGoal('');
    }
  };

  const removeGoal = (index: number) => {
    setGoals(goals.filter((_, i) => i !== index));
  };

  const addKeyPoint = () => {
    if (newKeyPoint.trim()) {
      setKeyPoints([...keyPoints, newKeyPoint.trim()]);
      setNewKeyPoint('');
    }
  };

  const removeKeyPoint = (index: number) => {
    setKeyPoints(keyPoints.filter((_, i) => i !== index));
  };

  const handleStrategyChange = (strategy: ProjectKpiConfig['strategy']) => {
    setKpiConfig((prev) => ({
      ...prev,
      strategy: strategy || 'custom',
      template_id: strategy === 'template' ? prev.template_id : undefined,
    }));
  };

  const applyTemplate = (templateId: string) => {
    const template = kpiTemplates.find((item) => item.id === templateId);
    setKpiConfig((prev) => ({
      ...prev,
      strategy: 'template',
      template_id: templateId || undefined,
      metrics: template ? template.metrics.map((metric) => ({ ...metric })) : prev.metrics,
    }));
  };

  const addKpiMetric = () => {
    setKpiConfig((prev) => ({
      ...prev,
      metrics: [
        ...prev.metrics,
        {
          key: `metric_${Date.now()}_${prev.metrics.length + 1}`,
          label: `KPI ${prev.metrics.length + 1}`,
          direction: 'neutral',
        },
      ],
    }));
  };

  const updateKpiMetric = (index: number, updates: Partial<ProjectKpiMetric>) => {
    setKpiConfig((prev) => {
      const metrics = [...prev.metrics];
      metrics[index] = { ...metrics[index], ...updates };
      return { ...prev, metrics };
    });
  };

  const removeKpiMetric = (index: number) => {
    setKpiConfig((prev) => ({
      ...prev,
      metrics: prev.metrics.filter((_, i) => i !== index),
    }));
  };

  const renderStars = (count: number) => {
    return (
      <div className="priority-stars">
        {[...Array(10)].map((_, i) => (
          <FaStar
            key={i}
            className={`star ${i < count ? 'star-filled' : 'star-empty'} star-interactive`}
            onClick={() => setPriority(i + 1)}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content project-detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>新規プロジェクト作成</h2>
          <button className="close-button" onClick={onClose}>
            <FaXmark />
          </button>
        </div>

        <div className="modal-body">
          {/* Basic Info */}
          <div className="section">
            <label className="field-label">プロジェクト名 *</label>
            <input
              type="text"
              className="text-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例: ブログ執筆"
              autoFocus
            />
          </div>

          {/* KPI */}
          <div className="section">
            <label className="field-label">KPI</label>
            <div className="kpi-editor">
              <div className="kpi-controls">
                <div className="kpi-control-row">
                  <span className="kpi-control-label">戦略</span>
                  <select
                    className="text-input"
                    value={kpiConfig.strategy || 'custom'}
                    onChange={(e) =>
                      handleStrategyChange(e.target.value as ProjectKpiConfig['strategy'])
                    }
                  >
                    <option value="template">テンプレート</option>
                    <option value="custom">カスタム</option>
                  </select>
                </div>

                {kpiConfig.strategy === 'template' && (
                  <div className="kpi-control-row">
                    <span className="kpi-control-label">テンプレート</span>
                    <select
                      className="text-input"
                      value={kpiConfig.template_id || ''}
                      onChange={(e) => applyTemplate(e.target.value)}
                      disabled={isLoadingTemplates}
                    >
                      <option value="">テンプレートを選択</option>
                      {kpiTemplates.map((template) => (
                        <option key={template.id} value={template.id}>
                          {template.name}
                        </option>
                      ))}
                    </select>
                    {isLoadingTemplates && (
                      <span className="kpi-loading">読み込み中...</span>
                    )}
                  </div>
                )}
              </div>

              <p className="kpi-hint">
                ソースは「tasks=タスク連動」「manual=手入力」です。ソースがtasksのKPIは現在値が自動計算されます。
              </p>

              {kpiConfig.metrics.length > 0 ? (
                <div className="kpi-metric-list">
                  {kpiConfig.metrics.map((metric, index) => {
                    const isAutoMetric = metric.source === 'tasks';
                    return (
                      <div className="kpi-metric-card" key={`${metric.key}-${index}`}>
                      <div className="kpi-metric-header">
                        <span className="kpi-metric-title">
                          {metric.label || 'Untitled KPI'}
                        </span>
                        <button
                          className="remove-button"
                          onClick={() => removeKpiMetric(index)}
                        >
                          <FaTrash />
                        </button>
                      </div>
                      <div className="kpi-metric-grid">
                        <label className="kpi-field">
                          <span>名称</span>
                          <input
                            className="text-input"
                            value={metric.label}
                            onChange={(e) =>
                              updateKpiMetric(index, { label: e.target.value })
                            }
                          />
                        </label>
                        <label className="kpi-field">
                          <span>キー</span>
                          <input
                            className="text-input"
                            value={metric.key}
                            readOnly={isAutoMetric}
                            onChange={(e) =>
                              updateKpiMetric(index, { key: e.target.value })
                            }
                          />
                        </label>
                        <label className="kpi-field">
                          <span>目標</span>
                          <input
                            className="text-input"
                            type="number"
                            step="any"
                            value={metric.target ?? ''}
                            onChange={(e) =>
                              updateKpiMetric(index, {
                                target:
                                  e.target.value === '' ? undefined : Number(e.target.value),
                              })
                            }
                          />
                        </label>
                        <label className="kpi-field">
                          <span>現在値</span>
                          <input
                            className="text-input"
                            type="number"
                            step="any"
                            value={metric.current ?? ''}
                            disabled={isAutoMetric}
                            placeholder={isAutoMetric ? '自動計算' : ''}
                            onChange={(e) =>
                              updateKpiMetric(index, {
                                current:
                                  e.target.value === '' ? undefined : Number(e.target.value),
                              })
                            }
                          />
                        </label>
                        <label className="kpi-field">
                          <span>単位</span>
                          <input
                            className="text-input"
                            value={metric.unit || ''}
                            onChange={(e) =>
                              updateKpiMetric(index, { unit: e.target.value })
                            }
                          />
                        </label>
                        <label className="kpi-field">
                          <span>方向</span>
                          <select
                            className="text-input"
                            value={metric.direction || 'neutral'}
                            onChange={(e) =>
                              updateKpiMetric(index, {
                                direction: e.target.value as ProjectKpiMetric['direction'],
                              })
                            }
                          >
                            <option value="up">上がるほど良い</option>
                            <option value="down">下がるほど良い</option>
                            <option value="neutral">中立</option>
                          </select>
                        </label>
                        <label className="kpi-field">
                          <span>ソース</span>
                          <input
                            className="text-input"
                            value={metric.source || ''}
                            placeholder="tasks / manual"
                            onChange={(e) =>
                              updateKpiMetric(index, { source: e.target.value })
                            }
                          />
                        </label>
                      </div>
                      <label className="kpi-field kpi-field-full">
                        <span>説明</span>
                        <textarea
                          className="text-area"
                          rows={2}
                          value={metric.description || ''}
                          onChange={(e) =>
                            updateKpiMetric(index, { description: e.target.value })
                          }
                        />
                      </label>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="empty-text">KPIはまだ設定されていません。</p>
              )}

              <div className="kpi-actions">
                <button className="add-button" onClick={addKpiMetric}>
                  <FaPlus />
                </button>
              </div>
            </div>
          </div>

          <div className="section">
            <label className="field-label">説明</label>
            <textarea
              className="text-area"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="プロジェクトの概要を入力..."
              rows={3}
            />
          </div>

          {/* Priority */}
          <div className="section">
            <label className="field-label">優先度 ({priority}/10)</label>
            {renderStars(priority)}
            <p className="field-hint">クリックして優先度を設定</p>
          </div>

          {/* Goals */}
          <div className="section">
            <label className="field-label">プロジェクトのゴール（オプション）</label>
            {goals.length > 0 ? (
              <ul className="item-list">
                {goals.map((goal, index) => (
                  <li key={index} className="item-list-entry">
                    <span>🎯 {goal}</span>
                    <button
                      className="remove-button"
                      onClick={() => removeGoal(index)}
                    >
                      <FaTrash />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">ゴール未設定</p>
            )}
            <div className="add-item-row">
              <input
                type="text"
                className="text-input"
                placeholder="新しいゴールを追加..."
                value={newGoal}
                onChange={(e) => setNewGoal(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addGoal()}
              />
              <button className="add-button" onClick={addGoal}>
                <FaPlus />
              </button>
            </div>
          </div>

          {/* Key Points */}
          <div className="section">
            <label className="field-label">重要なポイント（オプション）</label>
            {keyPoints.length > 0 ? (
              <ul className="item-list">
                {keyPoints.map((point, index) => (
                  <li key={index} className="item-list-entry">
                    <span>💡 {point}</span>
                    <button
                      className="remove-button"
                      onClick={() => removeKeyPoint(index)}
                    >
                      <FaTrash />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">重要なポイント未設定</p>
            )}
            <div className="add-item-row">
              <input
                type="text"
                className="text-input"
                placeholder="新しいポイントを追加..."
                value={newKeyPoint}
                onChange={(e) => setNewKeyPoint(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addKeyPoint()}
              />
              <button className="add-button" onClick={addKeyPoint}>
                <FaPlus />
              </button>
            </div>
          </div>

          <div className="section">
            <p className="field-hint">
              ℹ️ README（詳細コンテキスト）は作成後に編集できます
            </p>
          </div>
        </div>

        <div className="modal-footer">
          <button className="button button-secondary" onClick={onClose}>
            キャンセル
          </button>
          <button
            className="button button-primary"
            onClick={handleCreate}
            disabled={isSaving || !name.trim()}
          >
            {isSaving ? '作成中...' : '作成'}
          </button>
        </div>
      </div>
    </div>
  );
}
