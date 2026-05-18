import { useState, useEffect, useRef } from 'react';
import { FaStar, FaPlus, FaTrash, FaUsers } from 'react-icons/fa6';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import type {
  ProjectWithTaskCount,
  ProjectUpdate,
  ProjectVisibility,
  ProjectKpiConfig,
  ProjectKpiMetric,
  ProjectKpiTemplate,
  ProjectMember,
  ProjectInvitation,
} from '../../api/types';
import type { UserSearchResult } from '../../api/users';
import { projectsApi } from '../../api/projects';
import { UserSearchInput } from '../common/UserSearchInput';
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
  const [isEditingReadme, setIsEditingReadme] = useState(false);
  const readmeEditorRef = useRef<HTMLTextAreaElement>(null);
  const [showVisibilityConfirm, setShowVisibilityConfirm] = useState(false);
  const [activeTab, setActiveTab] = useState<'general' | 'roadmap' | 'kpi' | 'context' | 'members'>('general');

  // Form state
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description || '');
  const [visibility, setVisibility] = useState<ProjectVisibility>(project.visibility || 'PRIVATE');
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
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [isMembersLoading, setIsMembersLoading] = useState(false);
  const [memberActionId, setMemberActionId] = useState<string | null>(null);
  const [invitations, setInvitations] = useState<ProjectInvitation[]>([]);
  const [invitationActionId, setInvitationActionId] = useState<string | null>(null);
  const [inviteMode, setInviteMode] = useState<'email' | 'user_id'>('email');
  const [inviteValue, setInviteValue] = useState('');
  const [isInviting, setIsInviting] = useState(false);
  const [isInviteMenuOpen, setInviteMenuOpen] = useState(false);
  const inviteMenuRef = useRef<HTMLDivElement | null>(null);

  // Reset form when project changes
  useEffect(() => {
    setName(project.name);
    setDescription(project.description || '');
    setVisibility(project.visibility || 'PRIVATE');
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

  useEffect(() => {
    if (activeTab !== 'members') {
      setInviteMenuOpen(false);
      return;
    }
    let isActive = true;
    setIsMembersLoading(true);
    Promise.all([
      projectsApi.listMembers(project.id),
      projectsApi.listInvitations(project.id),
    ])
      .then(([membersData, invitationsData]) => {
        if (!isActive) return;
        setMembers(membersData);
        setInvitations(invitationsData);
      })
      .catch((error) => {
        console.error('Failed to load members:', error);
      })
      .finally(() => {
        if (isActive) setIsMembersLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, [activeTab, project.id]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!inviteMenuRef.current) return;
      if (inviteMenuRef.current.contains(event.target as Node)) return;
      setInviteMenuOpen(false);
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setInviteMenuOpen(false);
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, []);

  const executeSave = async () => {
    setIsSaving(true);
    try {
      const updates: ProjectUpdate = {
        name,
        description,
        visibility,
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

  const handleSave = () => {
    if (project.visibility === 'TEAM' && visibility === 'PRIVATE') {
      setShowVisibilityConfirm(true);
      return;
    }
    executeSave();
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

  const handleMemberRoleChange = async (memberId: string, role: ProjectMember['role']) => {
    setMemberActionId(memberId);
    try {
      await projectsApi.updateMember(project.id, memberId, { role });
      const membersData = await projectsApi.listMembers(project.id);
      setMembers(membersData);
    } catch (error) {
      console.error('Failed to update member role:', error);
      alert('Failed to update member role.');
    } finally {
      setMemberActionId(null);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    setMemberActionId(memberId);
    try {
      await projectsApi.removeMember(project.id, memberId);
      const membersData = await projectsApi.listMembers(project.id);
      setMembers(membersData);
    } catch (error) {
      console.error('Failed to remove member:', error);
      alert('Failed to remove member.');
    } finally {
      setMemberActionId(null);
    }
  };

  const handleInvite = async () => {
    const value = inviteValue.trim();
    if (!value) return;
    setIsInviting(true);
    try {
      if (inviteMode === 'email') {
        await projectsApi.createInvitation(project.id, { email: value });
      } else {
        await projectsApi.addMember(project.id, { member_user_id: value });
      }
      const [membersData, invitationsData] = await Promise.all([
        projectsApi.listMembers(project.id),
        projectsApi.listInvitations(project.id),
      ]);
      setMembers(membersData);
      setInvitations(invitationsData);
      setInviteValue('');
    } catch (error) {
      console.error('Failed to add member:', error);
      alert('Failed to add member.');
    } finally {
      setIsInviting(false);
    }
  };

  const handleRevokeInvitation = async (invitation: ProjectInvitation) => {
    setInvitationActionId(invitation.id);
    try {
      await projectsApi.updateInvitation(project.id, invitation.id, { status: 'REVOKED' });
      const invitationsData = await projectsApi.listInvitations(project.id);
      setInvitations(invitationsData);
    } catch (error) {
      console.error('Failed to revoke invitation:', error);
      alert('Failed to revoke invitation.');
    } finally {
      setInvitationActionId(null);
    }
  };

  const handleCopyInviteLink = async (token: string, email?: string) => {
    const emailParam = email ? `&email=${encodeURIComponent(email)}` : '';
    const link = `${window.location.origin}/invite/accept?token=${encodeURIComponent(token)}${emailParam}`;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(link);
        return;
      } catch (error) {
        console.error('Clipboard write failed:', error);
      }
    }
    try {
      const textarea = document.createElement('textarea');
      textarea.value = link;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    } catch (error) {
      console.error('Fallback copy failed:', error);
    }
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

  const pendingInvitations = invitations.filter((invitation) => invitation.status === 'PENDING');

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-content project-detail-modal">
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
            {visibility === 'TEAM' && (
              <button
                className={`nav-item ${activeTab === 'members' ? 'active' : ''}`}
                onClick={() => setActiveTab('members')}
              >
                <FaUsers className="nav-item-icon" /> Members
              </button>
            )}
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
                  <label className="field-label">公開設定</label>
                  <div className="visibility-selector">
                    <label className={`visibility-option ${visibility === 'PRIVATE' ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="edit-visibility"
                        value="PRIVATE"
                        checked={visibility === 'PRIVATE'}
                        onChange={() => {
                          setVisibility('PRIVATE');
                          setIsEditing(true);
                        }}
                      />
                      <span className="visibility-label">🔒 個人</span>
                      <span className="visibility-desc">自分だけのプロジェクト</span>
                    </label>
                    <label className={`visibility-option ${visibility === 'TEAM' ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="edit-visibility"
                        value="TEAM"
                        checked={visibility === 'TEAM'}
                        onChange={() => {
                          setVisibility('TEAM');
                          setIsEditing(true);
                        }}
                      />
                      <span className="visibility-label">👥 チーム</span>
                      <span className="visibility-desc">メンバーを招待して共同作業</span>
                    </label>
                  </div>
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
                {isEditingReadme ? (
                  <textarea
                    ref={readmeEditorRef}
                    className="text-area context-editor"
                    value={context}
                    autoFocus
                    onChange={(e) => {
                      setContext(e.target.value);
                      setIsEditing(true);
                    }}
                    onBlur={() => setIsEditingReadme(false)}
                    placeholder="プロジェクトの詳細な情報をMarkdown形式で記述..."
                    rows={20}
                  />
                ) : (
                  <div
                    className="markdown-preview readme-clickable"
                    onClick={() => setIsEditingReadme(true)}
                    title="クリックして編集"
                  >
                    {context ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {context}
                      </ReactMarkdown>
                    ) : (
                      <p className="readme-placeholder">クリックしてREADMEを編集...</p>
                    )}
                  </div>
                )}
              </div>
            )}
            {activeTab === 'members' && (
              <div className="section-content">
                <div className="section members-panel">
                  <label className="field-label">
                    <FaUsers className="field-label-icon" /> Members
                  </label>
                  {isMembersLoading ? (
                    <div className="members-loading">Loading...</div>
                  ) : (
                    <>
                      <div className="members-invite">
                        <div className="members-invite-row">
                          <div
                            className={`members-invite-select-wrap ${isInviteMenuOpen ? 'is-open' : ''}`}
                            ref={inviteMenuRef}
                          >
                            <button
                              type="button"
                              className="members-invite-select"
                              onClick={() => setInviteMenuOpen((prev) => !prev)}
                              aria-haspopup="listbox"
                              aria-expanded={isInviteMenuOpen}
                              disabled={isInviting}
                            >
                              {inviteMode === 'email' ? 'Email' : 'User Search'}
                            </button>
                            {isInviteMenuOpen && (
                              <div className="members-invite-menu" role="listbox">
                                <button
                                  type="button"
                                  className={`members-invite-option ${inviteMode === 'email' ? 'active' : ''}`}
                                  onClick={() => {
                                    setInviteMode('email');
                                    setInviteMenuOpen(false);
                                  }}
                                  role="option"
                                  aria-selected={inviteMode === 'email'}
                                >
                                  Email
                                </button>
                                <button
                                  type="button"
                                  className={`members-invite-option ${inviteMode === 'user_id' ? 'active' : ''}`}
                                  onClick={() => {
                                    setInviteMode('user_id');
                                    setInviteMenuOpen(false);
                                  }}
                                  role="option"
                                  aria-selected={inviteMode === 'user_id'}
                                >
                                  User Search
                                </button>
                              </div>
                            )}
                          </div>
                          {inviteMode === 'email' ? (
                            <>
                              <input
                                type="text"
                                className="text-input members-input"
                                placeholder="member@example.com"
                                value={inviteValue}
                                onChange={(e) => setInviteValue(e.target.value)}
                                disabled={isInviting}
                              />
                              <button
                                type="button"
                                className="members-invite-btn"
                                onClick={handleInvite}
                                disabled={!inviteValue.trim() || isInviting}
                              >
                                Invite
                              </button>
                            </>
                          ) : (
                            <UserSearchInput
                              placeholder="Search by username or email..."
                              disabled={isInviting}
                              onSelect={async (selectedUser: UserSearchResult) => {
                                setIsInviting(true);
                                try {
                                  await projectsApi.addMember(project.id, {
                                    member_user_id: selectedUser.id,
                                  });
                                  const [membersData, invitationsData] = await Promise.all([
                                    projectsApi.listMembers(project.id),
                                    projectsApi.listInvitations(project.id),
                                  ]);
                                  setMembers(membersData);
                                  setInvitations(invitationsData);
                                } catch (error) {
                                  console.error('Failed to add member:', error);
                                  alert('Failed to add member.');
                                } finally {
                                  setIsInviting(false);
                                }
                              }}
                            />
                          )}
                        </div>
                        <p className="members-invite-note">
                          Invite by email or search users to add.
                        </p>
                      </div>

                      {members.length === 0 && pendingInvitations.length === 0 ? (
                        <div className="members-empty">No members yet.</div>
                      ) : (
                        members.length > 0 && (
                          <div className="members-list">
                            {members.map((member) => {
                              const isOwnerMember = member.member_user_id === project.user_id;
                              return (
                              <div key={member.id} className="member-chip">
                                <div className="member-info">
                                  <span className="member-name">
                                    {member.member_display_name || member.member_user_id}
                                  </span>
                                  <span className="member-id">{member.member_user_id}</span>
                                </div>
                                <div className="member-actions">
                                  <select
                                    className="member-role-select"
                                    value={member.role}
                                    onChange={(e) =>
                                      handleMemberRoleChange(member.id, e.target.value as ProjectMember['role'])
                                    }
                                    disabled={memberActionId === member.id || isOwnerMember}
                                  >
                                    {isOwnerMember && <option value="OWNER">OWNER</option>}
                                    <option value="ADMIN">ADMIN</option>
                                    <option value="MEMBER">MEMBER</option>
                                  </select>
                                  <button
                                    type="button"
                                    className="member-remove-btn"
                                    onClick={() => handleRemoveMember(member.id)}
                                    disabled={memberActionId === member.id || isOwnerMember}
                                  >
                                    Remove
                                  </button>
                                </div>
                              </div>
                              );
                            })}
                          </div>
                        )
                      )}

                      {pendingInvitations.length > 0 && (
                        <div className="members-invitations">
                          <p className="invitations-title">Pending Invitations</p>
                          <p className="invitations-note">
                            Accept with the invite link.
                          </p>
                          <div className="invitations-list">
                            {pendingInvitations.map((invitation) => (
                              <div key={invitation.id} className="invitation-item">
                                <div className="invitation-main">
                                  <span className="invitation-email">{invitation.email}</span>
                                  <span className={`invitation-status status-${invitation.status.toLowerCase()}`}>
                                    {invitation.status}
                                  </span>
                                </div>
                                {invitation.token && (
                                  <div className="invitation-token-row">
                                    <code className="invitation-token" title={invitation.token}>
                                      {invitation.token}
                                    </code>
                                    <button
                                      type="button"
                                      className="invitation-btn primary"
                                      onClick={() => handleCopyInviteLink(invitation.token as string, invitation.email)}
                                    >
                                      Copy link
                                    </button>
                                  </div>
                                )}
                                <div className="invitation-actions">
                                  <button
                                    type="button"
                                    className="invitation-btn ghost"
                                    onClick={() => handleRevokeInvitation(invitation)}
                                    disabled={invitationActionId === invitation.id}
                                  >
                                    Revoke
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
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

      {showVisibilityConfirm && (
        <div className="confirm-overlay" onMouseDown={(e) => e.target === e.currentTarget && setShowVisibilityConfirm(false)}>
          <div className="confirm-dialog">
            <div className="confirm-icon">⚠️</div>
            <h3 className="confirm-title">個人プロジェクトに変更</h3>
            <p className="confirm-message">
              個人プロジェクトに変更すると、オーナー以外のメンバーが<strong>全員削除</strong>されます。この操作は取り消せません。
            </p>
            <div className="confirm-actions">
              <button
                className="button button-secondary"
                onClick={() => setShowVisibilityConfirm(false)}
              >
                キャンセル
              </button>
              <button
                className="button button-danger"
                onClick={() => {
                  setShowVisibilityConfirm(false);
                  executeSave();
                }}
              >
                変更する
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
