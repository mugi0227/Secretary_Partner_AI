import { useState, useEffect } from 'react';
import { FaXmark, FaStar, FaPlus, FaTrash } from 'react-icons/fa6';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import type {
  ProjectWithTaskCount,
  ProjectUpdate,
  ProjectKpiConfig,
  ProjectKpiMetric,
  ProjectKpiTemplate,
} from '../../api/types';
import { projectsApi } from '../../api/projects';
import './ProjectDetailModal.css';

const buildKpiConfig = (config?: ProjectKpiConfig | null): ProjectKpiConfig => ({
  strategy: config?.strategy ?? 'custom',
  template_id: config?.template_id,
  metrics: config?.metrics ? config.metrics.map((metric) => ({ ...metric })) : [],
});

const createKpiMetric = (index: number): ProjectKpiMetric => ({
  key: `metric_${Date.now()}_${index}`,
  label: `KPI ${index}`,
  direction: 'neutral',
});

interface ProjectDetailModalProps {
  project: ProjectWithTaskCount;
  onClose: () => void;
  onUpdate: () => void;
}

export function ProjectDetailModal({ project, onClose, onUpdate }: ProjectDetailModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [activeTab, setActiveTab] = useState<'general' | 'roadmap' | 'kpi' | 'context'>('general');

  // Form state
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description || '');
  const [context, setContext] = useState(project.context || '');
  const [priority, setPriority] = useState(project.priority);
  const [goals, setGoals] = useState<string[]>(project.goals || []);
  const [keyPoints, setKeyPoints] = useState<string[]>(project.key_points || []);
  const [newGoal, setNewGoal] = useState('');
  const [newKeyPoint, setNewKeyPoint] = useState('');
  const [kpiConfig, setKpiConfig] = useState<ProjectKpiConfig>(() =>
    buildKpiConfig(project.kpi_config)
  );
  const [kpiTemplates, setKpiTemplates] = useState<ProjectKpiTemplate[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  // Reset form when project changes
  useEffect(() => {
    setName(project.name);
    setDescription(project.description || '');
    setContext(project.context || '');
    setPriority(project.priority);
    setGoals(project.goals || []);
    setKeyPoints(project.key_points || []);
    setKpiConfig(buildKpiConfig(project.kpi_config));
  }, [project]);

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

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updates: ProjectUpdate = {
        name,
        description,
        context,
        priority,
        goals,
        key_points: keyPoints,
        kpi_config: kpiConfig,
      };
      await projectsApi.update(project.id, updates);
      setIsEditing(false);
      onUpdate();
    } catch (error) {
      console.error('Failed to update project:', error);
      alert('プロジェクトの更新に失敗しました');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    // Reset to original values
    setName(project.name);
    setDescription(project.description || '');
    setContext(project.context || '');
    setPriority(project.priority);
    setGoals(project.goals || []);
    setKeyPoints(project.key_points || []);
    setKpiConfig(buildKpiConfig(project.kpi_config));
    setIsEditing(false);
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
      metrics: [...prev.metrics, createKpiMetric(prev.metrics.length + 1)],
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

  const renderStars = (count: number, interactive: boolean = false) => {
    return (
      <div className="priority-stars">
        {[...Array(10)].map((_, i) => (
          <FaStar
            key={i}
            className={`star ${i < count ? 'star-filled' : 'star-empty'} ${interactive ? 'star-interactive' : ''
              }`}
            onClick={interactive ? () => {
              setPriority(i + 1);
              setIsEditing(true);
            } : undefined}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content project-detail-modal" onClick={(e) => e.stopPropagation()}>
        {/* Sidebar Navigation */}
        <aside className="modal-sidebar">
          <div className="sidebar-header">
            <h2>プロジェクト管理</h2>
          </div>
          <nav className="sidebar-nav">
            <button
              className={`nav-item ${activeTab === 'general' ? 'active' : ''}`}
              onClick={() => setActiveTab('general')}
            >
              <FaStar className="nav-item-icon" /> 概要
            </button>
            <button
              className={`nav-item ${activeTab === 'roadmap' ? 'active' : ''}`}
              onClick={() => setActiveTab('roadmap')}
            >
              <FaPlus className="nav-item-icon" /> ロードマップ
            </button>
            <button
              className={`nav-item ${activeTab === 'kpi' ? 'active' : ''}`}
              onClick={() => setActiveTab('kpi')}
            >
              <FaStar className="nav-item-icon" /> KPI
            </button>
            <button
              className={`nav-item ${activeTab === 'context' ? 'active' : ''}`}
              onClick={() => setActiveTab('context')}
            >
              <FaPlus className="nav-item-icon" /> README
            </button>
          </nav>
        </aside>

        {/* Main Content Area */}
        <div className="modal-main">
          <div className="modal-body">
            {activeTab === 'general' && (
              <div className="section-content">
                <div className="section">
                  <label className="field-label">
                    <FaStar className="field-label-icon" /> プロジェクト名
                  </label>
                  <input
                    type="text"
                    className="text-input"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value);
                      setIsEditing(true);
                    }}
                  />
                </div>
                <div className="section">
                  <label className="field-label">説明</label>
                  <textarea
                    className="text-area"
                    value={description}
                    onChange={(e) => {
                      setDescription(e.target.value);
                      setIsEditing(true);
                    }}
                    rows={4}
                  />
                </div>
                <div className="section">
                  <label className="field-label">優先度 ({priority}/10)</label>
                  {renderStars(priority, true)}
                </div>
                <div className="section">
                  <label className="field-label">タスク統計</label>
                  <div className="stats-grid">
                    <div className="stat-card">
                      <span className="stat-label">合計</span>
                      <span className="stat-value">{project.total_tasks}</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-label">進行中</span>
                      <span className="stat-value stat-progress">{project.in_progress_tasks}</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-label">完了</span>
                      <span className="stat-value stat-done">{project.completed_tasks}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'roadmap' && (
              <div className="section-content">
                <div className="section">
                  <label className="field-label">プロジェクトのゴール</label>
                  <ul className="item-list">
                    {goals.map((goal, index) => (
                      <li key={index} className="item-list-entry">
                        <span>🎯 {goal}</span>
                        <button className="remove-button" onClick={() => {
                          removeGoal(index);
                          setIsEditing(true);
                        }}>
                          <FaTrash />
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="add-item-row">
                    <input
                      type="text"
                      className="text-input"
                      placeholder="新しいゴールを追加..."
                      value={newGoal}
                      onChange={(e) => setNewGoal(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && (addGoal(), setIsEditing(true))}
                    />
                    <button className="add-button" onClick={() => {
                      addGoal();
                      setIsEditing(true);
                    }}>
                      <FaPlus />
                    </button>
                  </div>
                </div>

                <div className="section">
                  <label className="field-label">重要なポイント</label>
                  <ul className="item-list">
                    {keyPoints.map((point, index) => (
                      <li key={index} className="item-list-entry">
                        <span>💡 {point}</span>
                        <button className="remove-button" onClick={() => {
                          removeKeyPoint(index);
                          setIsEditing(true);
                        }}>
                          <FaTrash />
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="add-item-row">
                    <input
                      type="text"
                      className="text-input"
                      placeholder="新しいポイントを追加..."
                      value={newKeyPoint}
                      onChange={(e) => setNewKeyPoint(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && (addKeyPoint(), setIsEditing(true))}
                    />
                    <button className="add-button" onClick={() => {
                      addKeyPoint();
                      setIsEditing(true);
                    }}>
                      <FaPlus />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'kpi' && (
              <div className="section-content">
                <div className="kpi-editor">
                  <div className="kpi-controls">
                    <div className="kpi-control-row">
                      <span className="kpi-control-label">戦略</span>
                      <select
                        className="text-input"
                        value={kpiConfig.strategy || 'custom'}
                        onChange={(e) => {
                          handleStrategyChange(e.target.value as ProjectKpiConfig['strategy']);
                          setIsEditing(true);
                        }}
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
                          onChange={(e) => {
                            applyTemplate(e.target.value);
                            setIsEditing(true);
                          }}
                          disabled={isLoadingTemplates}
                        >
                          <option value="">テンプレートを選択</option>
                          {kpiTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  <div className="kpi-metric-list">
                    {kpiConfig.metrics.map((metric, index) => (
                      <div className="kpi-metric-card" key={`${metric.key}-${index}`}>
                        <div className="kpi-metric-header">
                          <span className="kpi-metric-title">{metric.label || '新規KPI'}</span>
                          <button className="remove-button" onClick={() => {
                            removeKpiMetric(index);
                            setIsEditing(true);
                          }}>
                            <FaTrash />
                          </button>
                        </div>
                        <div className="kpi-metric-grid">
                          <label className="kpi-field">
                            <span>名称</span>
                            <input
                              className="text-input"
                              value={metric.label}
                              onChange={(e) => {
                                updateKpiMetric(index, { label: e.target.value });
                                setIsEditing(true);
                              }}
                            />
                          </label>
                          <label className="kpi-field">
                            <span>単位</span>
                            <input
                              className="text-input"
                              value={metric.unit || ''}
                              onChange={(e) => {
                                updateKpiMetric(index, { unit: e.target.value });
                                setIsEditing(true);
                              }}
                            />
                          </label>
                          <label className="kpi-field">
                            <span>目標値</span>
                            <input
                              className="text-input"
                              type="number"
                              value={metric.target ?? ''}
                              onChange={(e) => {
                                updateKpiMetric(index, { target: e.target.value === '' ? undefined : Number(e.target.value) });
                                setIsEditing(true);
                              }}
                            />
                          </label>
                          <label className="kpi-field">
                            <span>現在値</span>
                            <input
                              className="text-input"
                              type="number"
                              value={metric.current ?? ''}
                              onChange={(e) => {
                                updateKpiMetric(index, { current: e.target.value === '' ? undefined : Number(e.target.value) });
                                setIsEditing(true);
                              }}
                            />
                          </label>
                        </div>
                      </div>
                    ))}
                  </div>

                  <button className="button button-secondary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => {
                    addKpiMetric();
                    setIsEditing(true);
                  }}>
                    <FaPlus /> KPIを追加
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'context' && (
              <div className="section-content">
                <div className="context-header">
                  <label className="field-label">README (詳細コンテキスト)</label>
                  <button className="preview-toggle" onClick={() => setShowPreview(!setShowPreview)}>
                    {showPreview ? 'エディター' : 'プレビュー'}
                  </button>
                </div>
                {showPreview ? (
                  <div className="markdown-preview">
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                      {context || '*プレビューする内容がありません*'}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <textarea
                    className="text-area context-editor"
                    value={context}
                    onChange={(e) => {
                      setContext(e.target.value);
                      setIsEditing(true);
                    }}
                    placeholder="プロジェクトの詳細な情報をMarkdown形式で記述..."
                    rows={20}
                  />
                )}
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button className="button button-secondary" onClick={onClose}>
              閉じる
            </button>
            <button
              className="button button-primary"
              onClick={handleSave}
              disabled={isSaving || !isEditing}
            >
              {isSaving ? '保存中...' : '変更を保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
