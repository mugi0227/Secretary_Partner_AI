import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { FaCheck, FaChevronDown, FaChevronUp, FaEdit, FaPlus, FaRobot, FaTimes, FaTrash } from 'react-icons/fa';
import type {
  Milestone,
  MilestoneCreate,
  MilestoneUpdate,
  PhaseCreate,
  PhaseUpdate,
  PhaseWithTaskCount,
} from '../../api/types';
import type { DraftCardData } from '../chat/DraftCard';
import './PhaseList.css';

interface PhaseListProps {
  phases: PhaseWithTaskCount[];
  milestones: Milestone[];
  isMilestonesLoading?: boolean;
  onCreatePhase: (phase: PhaseCreate) => Promise<void>;
  onUpdatePhase: (id: string, phase: PhaseUpdate) => Promise<void>;
  onDeletePhase: (id: string) => Promise<void>;
  onCreateMilestone: (milestone: MilestoneCreate) => Promise<void>;
  onUpdateMilestone: (id: string, milestone: MilestoneUpdate) => Promise<void>;
  onDeleteMilestone: (id: string) => Promise<void>;
  onGeneratePhases?: (instruction?: string) => Promise<void>;
  onGeneratePhaseTasks?: (phaseId: string, instruction?: string) => Promise<void>;
  isPlanningPhases?: boolean;
  planningPhaseId?: string | null;
  projectId: string;
}

export function PhaseList({
  phases,
  milestones,
  isMilestonesLoading = false,
  onCreatePhase,
  onUpdatePhase,
  onDeletePhase,
  onCreateMilestone,
  onUpdateMilestone,
  onDeleteMilestone,
  projectId,
}: PhaseListProps) {
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [newPhaseName, setNewPhaseName] = useState('');
  const [newPhaseDescription, setNewPhaseDescription] = useState('');
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [addingMilestonePhaseId, setAddingMilestonePhaseId] = useState<string | null>(null);
  const [milestoneTitle, setMilestoneTitle] = useState('');
  const [milestoneDescription, setMilestoneDescription] = useState('');
  const [milestoneDueDate, setMilestoneDueDate] = useState('');
  const [editingMilestoneId, setEditingMilestoneId] = useState<string | null>(null);
  const [editMilestoneTitle, setEditMilestoneTitle] = useState('');
  const [editMilestoneDescription, setEditMilestoneDescription] = useState('');
  const [editMilestoneDueDate, setEditMilestoneDueDate] = useState('');
  const [phasePlanInstruction, setPhasePlanInstruction] = useState('');
  const [phaseTaskInstructions, setPhaseTaskInstructions] = useState<Record<string, string>>({});

  const milestonesByPhaseId = useMemo(() => {
    const map: Record<string, Milestone[]> = {};
    milestones.forEach((milestone) => {
      if (!map[milestone.phase_id]) {
        map[milestone.phase_id] = [];
      }
      map[milestone.phase_id].push(milestone);
    });
    Object.keys(map).forEach((phaseId) => {
      map[phaseId] = map[phaseId].sort((a, b) => a.order_in_phase - b.order_in_phase);
    });
    return map;
  }, [milestones]);

  const sortedPhases = useMemo(
    () => [...phases].sort((a, b) => a.order_in_project - b.order_in_project),
    [phases]
  );

  const handleCreate = async () => {
    if (!newPhaseName.trim()) return;

    try {
      await onCreatePhase({
        project_id: projectId,
        name: newPhaseName.trim(),
        description: newPhaseDescription.trim() || undefined,
        order_in_project: phases.length + 1,
      });
      setNewPhaseName('');
      setNewPhaseDescription('');
      setIsAdding(false);
    } catch (error) {
      console.error('Failed to create phase:', error);
      alert('フェーズの作成に失敗しました。');
    }
  };

  const handleUpdate = async (id: string) => {
    if (!editName.trim()) return;

    try {
      await onUpdatePhase(id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
      });
      setEditingId(null);
    } catch (error) {
      console.error('Failed to update phase:', error);
      alert('フェーズの更新に失敗しました。');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('このフェーズを削除しますか？')) return;

    try {
      await onDeletePhase(id);
    } catch (error) {
      console.error('Failed to delete phase:', error);
      alert('フェーズの削除に失敗しました。');
    }
  };

  const handleStartEdit = (phase: PhaseWithTaskCount) => {
    setEditingId(phase.id);
    setEditName(phase.name);
    setEditDescription(phase.description || '');
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditName('');
    setEditDescription('');
  };

  const handleMoveUp = async (phase: PhaseWithTaskCount) => {
    if (phase.order_in_project <= 1) return;
    try {
      await onUpdatePhase(phase.id, { order_in_project: phase.order_in_project - 1 });
    } catch (error) {
      console.error('Failed to move phase up:', error);
      alert('フェーズの並び替えに失敗しました。');
    }
  };

  const handleMoveDown = async (phase: PhaseWithTaskCount) => {
    if (phase.order_in_project >= sortedPhases.length) return;
    try {
      await onUpdatePhase(phase.id, { order_in_project: phase.order_in_project + 1 });
    } catch (error) {
      console.error('Failed to move phase down:', error);
      alert('フェーズの並び替えに失敗しました。');
    }
  };

  const handleStartAddMilestone = (phaseId: string) => {
    setAddingMilestonePhaseId(phaseId);
    setMilestoneTitle('');
    setMilestoneDescription('');
    setMilestoneDueDate('');
  };

  const handleCreateMilestone = async (phaseId: string) => {
    if (!milestoneTitle.trim()) return;
    try {
      await onCreateMilestone({
        project_id: projectId,
        phase_id: phaseId,
        title: milestoneTitle.trim(),
        description: milestoneDescription.trim() || undefined,
        order_in_phase: (milestonesByPhaseId[phaseId]?.length || 0) + 1,
        due_date: milestoneDueDate || undefined,
      });
      setAddingMilestonePhaseId(null);
      setMilestoneTitle('');
      setMilestoneDescription('');
      setMilestoneDueDate('');
    } catch (error) {
      console.error('Failed to create milestone:', error);
      alert('マイルストーンの作成に失敗しました。');
    }
  };

  const handleStartEditMilestone = (milestone: Milestone) => {
    setEditingMilestoneId(milestone.id);
    setEditMilestoneTitle(milestone.title);
    setEditMilestoneDescription(milestone.description || '');
    setEditMilestoneDueDate(milestone.due_date ? milestone.due_date.slice(0, 10) : '');
  };

  const handleUpdateMilestone = async (milestoneId: string) => {
    if (!editMilestoneTitle.trim()) return;
    try {
      await onUpdateMilestone(milestoneId, {
        title: editMilestoneTitle.trim(),
        description: editMilestoneDescription.trim() || undefined,
        due_date: editMilestoneDueDate || undefined,
      });
      setEditingMilestoneId(null);
    } catch (error) {
      console.error('Failed to update milestone:', error);
      alert('マイルストーンの更新に失敗しました。');
    }
  };

  const handleCancelMilestoneEdit = () => {
    setEditingMilestoneId(null);
    setEditMilestoneTitle('');
    setEditMilestoneDescription('');
    setEditMilestoneDueDate('');
  };

  const handleDeleteMilestone = async (milestoneId: string) => {
    if (!confirm('このマイルストーンを削除しますか？')) return;
    try {
      await onDeleteMilestone(milestoneId);
    } catch (error) {
      console.error('Failed to delete milestone:', error);
      alert('マイルストーンの削除に失敗しました。');
    }
  };

  const handlePhaseTaskInstructionChange = (phaseId: string, value: string) => {
    setPhaseTaskInstructions((prev) => ({
      ...prev,
      [phaseId]: value,
    }));
  };

  return (
    <div className="phase-list">
      <div className="phase-list-header">
        <h3>フェーズマネージャー</h3>
        <div className="phase-header-actions">
          <button
            className="add-phase-btn"
            onClick={() => {
              const draftCard: DraftCardData = {
                type: 'phase',
                title: 'フェーズ生成',
                info: [
                  { label: 'プロジェクトID', value: projectId },
                ],
                placeholder: '例: MVP優先、フェーズは3〜5件に絞る',
                promptTemplate: `プロジェクト (ID: ${projectId}) のフェーズを作成して。

追加の指示があれば以下に記入:
{instruction}`,
              };
              const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
              window.dispatchEvent(event);
            }}
            title="AIでフェーズとマイルストーンを生成"
          >
            <FaRobot /> AIでフェーズ生成
          </button>
          <button className="add-phase-btn" onClick={() => setIsAdding(true)}>
            <FaPlus /> フェーズ追加
          </button>
        </div>
      </div>

      <div className="phase-plan-input">
        <label htmlFor="phase-plan-instruction">AI指示</label>
        <textarea
          id="phase-plan-instruction"
          value={phasePlanInstruction}
          onChange={(e) => setPhasePlanInstruction(e.target.value)}
          placeholder="例: MVP優先、フェーズは3〜5件に絞る"
          rows={2}
        />
      </div>

      <AnimatePresence>
        {isAdding && (
          <motion.div
            className="phase-form"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <input
              type="text"
              placeholder="フェーズ名"
              value={newPhaseName}
              onChange={(e) => setNewPhaseName(e.target.value)}
              className="phase-name-input"
              autoFocus
            />
            <textarea
              placeholder="説明（任意）"
              value={newPhaseDescription}
              onChange={(e) => setNewPhaseDescription(e.target.value)}
              className="phase-description-input"
              rows={2}
            />
            <div className="phase-form-actions">
              <button className="btn-save" onClick={handleCreate}>
                <FaCheck /> 作成
              </button>
              <button
                className="btn-cancel"
                onClick={() => {
                  setIsAdding(false);
                  setNewPhaseName('');
                  setNewPhaseDescription('');
                }}
              >
                <FaTimes /> キャンセル
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="phases-container">
        <AnimatePresence>
          {sortedPhases.map((phase) => (
            <motion.div
              key={phase.id}
              className={`phase-item ${phase.status === 'COMPLETED' ? 'phase-completed' : ''}`}
              layout
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              {editingId === phase.id ? (
                <div className="phase-edit-form">
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="phase-name-input"
                    autoFocus
                  />
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    className="phase-description-input"
                    rows={2}
                  />
                  <div className="phase-form-actions">
                    <button className="btn-save" onClick={() => handleUpdate(phase.id)}>
                      <FaCheck /> 保存
                    </button>
                    <button className="btn-cancel" onClick={handleCancelEdit}>
                      <FaTimes /> キャンセル
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="phase-header">
                    <div className="phase-order-controls">
                      <button
                        className="order-btn"
                        onClick={() => handleMoveUp(phase)}
                        disabled={phase.order_in_project <= 1}
                        title="上へ移動"
                      >
                        <FaChevronUp />
                      </button>
                      <span className="phase-order">{phase.order_in_project}</span>
                      <button
                        className="order-btn"
                        onClick={() => handleMoveDown(phase)}
                        disabled={phase.order_in_project >= sortedPhases.length}
                        title="下へ移動"
                      >
                        <FaChevronDown />
                      </button>
                    </div>
                    <div className="phase-info">
                      <h4 className="phase-name">{phase.name}</h4>
                      {phase.description && <p className="phase-description">{phase.description}</p>}
                    </div>
                    <div className="phase-stats">
                      <span className="stat">
                        全体 <strong>{phase.total_tasks}</strong>
                      </span>
                      <span className="stat in-progress">
                        進行中 <strong>{phase.in_progress_tasks}</strong>
                      </span>
                      <span className="stat completed">
                        完了 <strong>{phase.completed_tasks}</strong>
                      </span>
                    </div>
                    <div className="phase-actions">
                      <button
                        className="btn-icon"
                        onClick={() => handleStartEdit(phase)}
                        title="編集"
                      >
                        <FaEdit />
                      </button>
                      <button
                        className="btn-icon btn-danger"
                        onClick={() => handleDelete(phase.id)}
                        title="削除"
                      >
                        <FaTrash />
                      </button>
                    </div>
                  </div>
                  <div className="phase-milestones">
                    <div className="milestones-header">
                      <span className="milestones-title">マイルストーン</span>
                      <input
                        className="milestone-instruction-input"
                        type="text"
                        value={phaseTaskInstructions[phase.id] || ''}
                        onChange={(e) => handlePhaseTaskInstructionChange(phase.id, e.target.value)}
                        placeholder="タスク分解の指示を入力（任意）"
                      />
                      <div className="milestones-actions">
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            const draftCard: DraftCardData = {
                              type: 'task',
                              title: 'フェーズからタスク作成',
                              info: [
                                { label: 'フェーズ', value: phase.name },
                                { label: 'フェーズID', value: phase.id },
                              ],
                              placeholder: '例: MVP優先で、3〜5個のタスクに分解して',
                              promptTemplate: `フェーズ「${phase.name}」(ID: ${phase.id}) からタスクを作成して。

追加の指示があれば以下に記入:
{instruction}`,
                            };
                            const event = new CustomEvent('secretary:chat-open', { detail: { draftCard } });
                            window.dispatchEvent(event);
                          }}
                        >
                          <FaRobot /> AIでタスク分解
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() => handleStartAddMilestone(phase.id)}
                        >
                          <FaPlus /> マイルストーン追加
                        </button>
                      </div>
                    </div>

                    {isMilestonesLoading ? (
                      <div className="milestones-loading">読み込み中...</div>
                    ) : (
                      <div className="milestones-list">
                        {(milestonesByPhaseId[phase.id] || []).length === 0 && (
                          <div className="milestones-empty">マイルストーンがまだありません。</div>
                        )}
                        {(milestonesByPhaseId[phase.id] || []).map((milestone) => (
                          <div key={milestone.id} className="milestone-item">
                            {editingMilestoneId === milestone.id ? (
                              <div className="milestone-edit">
                                <input
                                  type="text"
                                  value={editMilestoneTitle}
                                  onChange={(e) => setEditMilestoneTitle(e.target.value)}
                                  className="milestone-input"
                                />
                                <input
                                  type="date"
                                  value={editMilestoneDueDate}
                                  onChange={(e) => setEditMilestoneDueDate(e.target.value)}
                                  className="milestone-date"
                                />
                                <textarea
                                  value={editMilestoneDescription}
                                  onChange={(e) => setEditMilestoneDescription(e.target.value)}
                                  className="milestone-textarea"
                                  rows={2}
                                />
                                <div className="milestone-actions">
                                  <button
                                    className="btn-save"
                                    onClick={() => handleUpdateMilestone(milestone.id)}
                                  >
                                    <FaCheck /> 保存
                                  </button>
                                  <button className="btn-cancel" onClick={handleCancelMilestoneEdit}>
                                    <FaTimes /> キャンセル
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <>
                                <div className="milestone-main">
                                  <div className="milestone-info">
                                    <span className="milestone-title">{milestone.title}</span>
                                    {milestone.due_date && (
                                      <span className="milestone-date">
                                        {milestone.due_date.slice(0, 10)}
                                      </span>
                                    )}
                                  </div>
                                  <div className="milestone-buttons">
                                    <button
                                      className="btn-icon"
                                      onClick={() => handleStartEditMilestone(milestone)}
                                      title="マイルストーンを編集"
                                    >
                                      <FaEdit />
                                    </button>
                                    <button
                                      className="btn-icon btn-danger"
                                      onClick={() => handleDeleteMilestone(milestone.id)}
                                      title="削除"
                                    >
                                      <FaTrash />
                                    </button>
                                  </div>
                                </div>
                                {milestone.description && (
                                  <p className="milestone-description">{milestone.description}</p>
                                )}
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {addingMilestonePhaseId === phase.id && (
                      <div className="milestone-form">
                        <input
                          type="text"
                          placeholder="マイルストーン名"
                          value={milestoneTitle}
                          onChange={(e) => setMilestoneTitle(e.target.value)}
                          className="milestone-input"
                          autoFocus
                        />
                        <input
                          type="date"
                          value={milestoneDueDate}
                          onChange={(e) => setMilestoneDueDate(e.target.value)}
                          className="milestone-date"
                        />
                        <textarea
                          placeholder="説明（任意）"
                          value={milestoneDescription}
                          onChange={(e) => setMilestoneDescription(e.target.value)}
                          className="milestone-textarea"
                          rows={2}
                        />
                        <div className="milestone-actions">
                          <button className="btn-save" onClick={() => handleCreateMilestone(phase.id)}>
                            <FaCheck /> 保存
                          </button>
                          <button
                            className="btn-cancel"
                            onClick={() => setAddingMilestonePhaseId(null)}
                          >
                            <FaTimes /> キャンセル
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {sortedPhases.length === 0 && !isAdding && (
        <div className="empty-state">
          <p>フェーズがまだありません。</p>
          <button className="btn-primary" onClick={() => setIsAdding(true)}>
            <FaPlus /> 最初のフェーズを追加
          </button>
        </div>
      )}
    </div>
  );
}
