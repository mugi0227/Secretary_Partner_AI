import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FaTrophy,
  FaPlus,
  FaChevronDown,
  FaChevronUp,
  FaUsers,
  FaLightbulb,
  FaTriangleExclamation,
  FaBookOpen,
  FaTrash,
  FaPenToSquare,
  FaWandMagicSparkles,
  FaSpinner,
} from 'react-icons/fa6';
import { projectAchievementsApi } from '../../api/projectAchievements';
import type { ProjectAchievement, ProjectAchievementUpdate, MemberContribution } from '../../api/types';
import { formatDate, todayInTimezone, toUtcIsoString } from '../../utils/dateTime';
import { useTimezone } from '../../hooks/useTimezone';
import './ProjectAchievementsSection.css';

interface ProjectAchievementsSectionProps {
  projectId: string;
}

type EditableSection =
  | 'summary'
  | 'team_highlights'
  | 'challenges'
  | 'learnings'
  | 'open_issues';

function MemberContributionCard({ contribution }: { contribution: MemberContribution }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="member-contribution">
      <div
        className="member-contribution-header"
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setExpanded(!expanded)}
      >
        <div className="member-info">
          <span className="member-name">{contribution.display_name}</span>
          <span className="task-count">{contribution.task_count}件完了</span>
        </div>
        {contribution.task_titles.length > 0 && (
          <button className="expand-btn">
            {expanded ? <FaChevronUp /> : <FaChevronDown />}
          </button>
        )}
      </div>
      {contribution.main_areas.length > 0 && (
        <div className="member-areas">
          {contribution.main_areas.map((area, i) => (
            <span key={i} className="area-tag">{area}</span>
          ))}
        </div>
      )}
      <AnimatePresence>
        {expanded && contribution.task_titles.length > 0 && (
          <motion.div
            className="member-tasks"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <ul>
              {contribution.task_titles.map((title, i) => (
                <li key={i}>{title}</li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AchievementCard({
  achievement,
  onDelete,
  onUpdate,
  onSummarize,
  isDeleting,
  isUpdating,
  isSummarizing,
}: {
  achievement: ProjectAchievement;
  onDelete: () => void;
  onUpdate: (achievementId: string, payload: ProjectAchievementUpdate) => Promise<ProjectAchievement>;
  onSummarize: (achievementId: string) => void;
  isDeleting: boolean;
  isUpdating: boolean;
  isSummarizing: boolean;
}) {
  const timezone = useTimezone();
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState<{
    section: EditableSection;
    index?: number;
    value: string;
  } | null>(null);
  const [appendNoteDraft, setAppendNoteDraft] = useState<string | null>(null);
  const appendNote = appendNoteDraft ?? achievement.append_note ?? '';
  const isBusy = isDeleting || isUpdating || isSummarizing;

  const formatPeriod = () => {
    const start = formatDate(achievement.period_start, { month: 'numeric', day: 'numeric' }, timezone);
    const end = formatDate(achievement.period_end, { month: 'numeric', day: 'numeric' }, timezone);
    return `${start} - ${end}`;
  };

  const handleEditStart = (section: EditableSection, value: string, index?: number) => {
    setEditing({ section, value, index });
  };

  const handleEditCancel = () => {
    setEditing(null);
  };

  const buildListPayload = (section: EditableSection, list: string[]): ProjectAchievementUpdate => {
    switch (section) {
      case 'team_highlights':
        return { team_highlights: list };
      case 'challenges':
        return { challenges: list };
      case 'learnings':
        return { learnings: list };
      case 'open_issues':
        return { open_issues: list };
      default:
        return {};
    }
  };

  const handleEditSave = async () => {
    if (!editing) return;
    const trimmed = editing.value.trim();
    if (!trimmed) return;
    if (editing.section === 'summary') {
      await onUpdate(achievement.id, { summary: trimmed });
      setEditing(null);
      return;
    }
    const listSource =
      editing.section === 'team_highlights'
        ? achievement.team_highlights
        : editing.section === 'challenges'
          ? achievement.challenges
          : editing.section === 'learnings'
            ? achievement.learnings
            : achievement.open_issues;
    const updatedList = listSource.map((item, index) =>
      index === editing.index ? trimmed : item
    );
    await onUpdate(achievement.id, buildListPayload(editing.section, updatedList));
    setEditing(null);
  };

  const handleDeleteItem = async (section: EditableSection, index: number) => {
    if (!window.confirm('削除しますか？')) return;
    const listSource =
      section === 'team_highlights'
        ? achievement.team_highlights
        : section === 'challenges'
          ? achievement.challenges
          : section === 'learnings'
            ? achievement.learnings
            : achievement.open_issues;
    const updatedList = listSource.filter((_, itemIndex) => itemIndex !== index);
    await onUpdate(achievement.id, buildListPayload(section, updatedList));
  };

  const handleAppendNoteSave = async () => {
    await onUpdate(achievement.id, { append_note: appendNote });
    setAppendNoteDraft(null);
  };

  return (
    <div className="achievement-card">
      <div className="achievement-header">
        <div className="achievement-meta">
          <span className="achievement-period">{achievement.period_label || formatPeriod()}</span>
          <span className={`generation-type ${achievement.generation_type.toLowerCase()}`}>
            {achievement.generation_type === 'AUTO' ? '自動生成' : '手動生成'}
          </span>
        </div>
        <div className="achievement-actions">
          <button
            className="action-btn summarize"
            onClick={() => onSummarize(achievement.id)}
            disabled={isBusy}
            title="AIでまとめる"
          >
            {isSummarizing ? <FaSpinner className="spinner" /> : <FaWandMagicSparkles />}
            <span>{isSummarizing ? 'まとめ中' : 'AIでまとめる'}</span>
          </button>
          <button
            className="delete-btn"
            onClick={onDelete}
            disabled={isBusy}
            title="削除"
          >
            <FaTrash />
          </button>
        </div>
      </div>

      <div className="achievement-summary">
        {editing?.section === 'summary' ? (
          <textarea
            className="edit-textarea summary-textarea"
            rows={4}
            value={editing.value}
            onChange={(event) =>
              setEditing((current) =>
                current ? { ...current, value: event.target.value } : current
              )
            }
            disabled={isBusy}
          />
        ) : (
          <div className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{achievement.summary}</ReactMarkdown>
          </div>
        )}
        <div
          className={`item-actions summary-actions${
            editing?.section === 'summary' ? '' : ' hover-actions'
          }`}
        >
          {editing?.section === 'summary' ? (
            <>
              <button
                className="item-action-btn save"
                type="button"
                onClick={handleEditSave}
                disabled={isBusy}
              >
                {isUpdating ? '保存中' : '保存'}
              </button>
              <button
                className="item-action-btn cancel"
                type="button"
                onClick={handleEditCancel}
                disabled={isBusy}
              >
                キャンセル
              </button>
            </>
          ) : (
            <button
              className="item-action-btn icon edit"
              type="button"
              onClick={() => handleEditStart('summary', achievement.summary)}
              disabled={isBusy || editing !== null}
              aria-label="編集"
              title="編集"
            >
              <FaPenToSquare />
            </button>
          )}
        </div>
      </div>

      <div className="achievement-stats">
        <div className="stat">
          <span className="stat-value">{achievement.total_task_count}</span>
          <span className="stat-label">完了タスク</span>
        </div>
        <div className="stat">
          <span className="stat-value">{achievement.remaining_tasks_count}</span>
          <span className="stat-label">残タスク</span>
        </div>
        <div className="stat">
          <span className="stat-value">{achievement.member_contributions.length}</span>
          <span className="stat-label">貢献メンバー</span>
        </div>
      </div>

      <button
        className="expand-details-btn"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? '詳細を閉じる' : '詳細を見る'}
        {expanded ? <FaChevronUp /> : <FaChevronDown />}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            className="achievement-details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {/* Team Highlights */}
            {achievement.team_highlights.length > 0 && (
              <div className="detail-section">
                <h4><FaTrophy className="section-icon highlight" /> チームのハイライト</h4>
                <ul>
                  {achievement.team_highlights.map((item, i) => {
                    const isEditing =
                      editing?.section === 'team_highlights' && editing.index === i;
                    return (
                      <li key={i} className="editable-list-item">
                        <div className="item-content">
                          {isEditing ? (
                            <textarea
                              className="edit-textarea"
                              rows={2}
                              value={editing.value}
                              onChange={(event) =>
                                setEditing((current) =>
                                  current
                                    ? { ...current, value: event.target.value }
                                    : current
                                )
                              }
                              disabled={isBusy}
                            />
                          ) : (
                            <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item}</ReactMarkdown></div>
                          )}
                        </div>
                        <div className={`item-actions${isEditing ? '' : ' hover-actions'}`}>
                          {isEditing ? (
                            <>
                              <button
                                className="item-action-btn save"
                                type="button"
                                onClick={handleEditSave}
                                disabled={isBusy}
                              >
                                {isUpdating ? '保存中' : '保存'}
                              </button>
                              <button
                                className="item-action-btn cancel"
                                type="button"
                                onClick={handleEditCancel}
                                disabled={isBusy}
                              >
                                キャンセル
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                className="item-action-btn icon edit"
                                type="button"
                                onClick={() => handleEditStart('team_highlights', item, i)}
                                disabled={isBusy || editing !== null}
                                aria-label="編集"
                                title="編集"
                              >
                                <FaPenToSquare />
                              </button>
                              <button
                                className="item-action-btn icon delete"
                                type="button"
                                onClick={() => handleDeleteItem('team_highlights', i)}
                                disabled={isBusy || editing !== null}
                                aria-label="削除"
                                title="削除"
                              >
                                <FaTrash />
                              </button>
                            </>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Challenges */}
            {achievement.challenges.length > 0 && (
              <div className="detail-section">
                <h4><FaTriangleExclamation className="section-icon challenge" /> 直面した課題</h4>
                <ul>
                  {achievement.challenges.map((item, i) => {
                    const isEditing =
                      editing?.section === 'challenges' && editing.index === i;
                    return (
                      <li key={i} className="editable-list-item">
                        <div className="item-content">
                          {isEditing ? (
                            <textarea
                              className="edit-textarea"
                              rows={2}
                              value={editing.value}
                              onChange={(event) =>
                                setEditing((current) =>
                                  current
                                    ? { ...current, value: event.target.value }
                                    : current
                                )
                              }
                              disabled={isBusy}
                            />
                          ) : (
                            <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item}</ReactMarkdown></div>
                          )}
                        </div>
                        <div className={`item-actions${isEditing ? '' : ' hover-actions'}`}>
                          {isEditing ? (
                            <>
                              <button
                                className="item-action-btn save"
                                type="button"
                                onClick={handleEditSave}
                                disabled={isBusy}
                              >
                                {isUpdating ? '保存中' : '保存'}
                              </button>
                              <button
                                className="item-action-btn cancel"
                                type="button"
                                onClick={handleEditCancel}
                                disabled={isBusy}
                              >
                                キャンセル
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                className="item-action-btn icon edit"
                                type="button"
                                onClick={() => handleEditStart('challenges', item, i)}
                                disabled={isBusy || editing !== null}
                                aria-label="編集"
                                title="編集"
                              >
                                <FaPenToSquare />
                              </button>
                              <button
                                className="item-action-btn icon delete"
                                type="button"
                                onClick={() => handleDeleteItem('challenges', i)}
                                disabled={isBusy || editing !== null}
                                aria-label="削除"
                                title="削除"
                              >
                                <FaTrash />
                              </button>
                            </>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Learnings */}
            {achievement.learnings.length > 0 && (
              <div className="detail-section">
                <h4><FaLightbulb className="section-icon learning" /> 学び</h4>
                <ul>
                  {achievement.learnings.map((item, i) => {
                    const isEditing =
                      editing?.section === 'learnings' && editing.index === i;
                    return (
                      <li key={i} className="editable-list-item">
                        <div className="item-content">
                          {isEditing ? (
                            <textarea
                              className="edit-textarea"
                              rows={2}
                              value={editing.value}
                              onChange={(event) =>
                                setEditing((current) =>
                                  current
                                    ? { ...current, value: event.target.value }
                                    : current
                                )
                              }
                              disabled={isBusy}
                            />
                          ) : (
                            <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item}</ReactMarkdown></div>
                          )}
                        </div>
                        <div className={`item-actions${isEditing ? '' : ' hover-actions'}`}>
                          {isEditing ? (
                            <>
                              <button
                                className="item-action-btn save"
                                type="button"
                                onClick={handleEditSave}
                                disabled={isBusy}
                              >
                                {isUpdating ? '保存中' : '保存'}
                              </button>
                              <button
                                className="item-action-btn cancel"
                                type="button"
                                onClick={handleEditCancel}
                                disabled={isBusy}
                              >
                                キャンセル
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                className="item-action-btn icon edit"
                                type="button"
                                onClick={() => handleEditStart('learnings', item, i)}
                                disabled={isBusy || editing !== null}
                                aria-label="編集"
                                title="編集"
                              >
                                <FaPenToSquare />
                              </button>
                              <button
                                className="item-action-btn icon delete"
                                type="button"
                                onClick={() => handleDeleteItem('learnings', i)}
                                disabled={isBusy || editing !== null}
                                aria-label="削除"
                                title="削除"
                              >
                                <FaTrash />
                              </button>
                            </>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Open Issues */}
            {achievement.open_issues.length > 0 && (
              <div className="detail-section">
                <h4><FaBookOpen className="section-icon issue" /> 未解決の課題</h4>
                <ul>
                  {achievement.open_issues.map((item, i) => {
                    const isEditing =
                      editing?.section === 'open_issues' && editing.index === i;
                    return (
                      <li key={i} className="editable-list-item">
                        <div className="item-content">
                          {isEditing ? (
                            <textarea
                              className="edit-textarea"
                              rows={2}
                              value={editing.value}
                              onChange={(event) =>
                                setEditing((current) =>
                                  current
                                    ? { ...current, value: event.target.value }
                                    : current
                                )
                              }
                              disabled={isBusy}
                            />
                          ) : (
                            <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item}</ReactMarkdown></div>
                          )}
                        </div>
                        <div className={`item-actions${isEditing ? '' : ' hover-actions'}`}>
                          {isEditing ? (
                            <>
                              <button
                                className="item-action-btn save"
                                type="button"
                                onClick={handleEditSave}
                                disabled={isBusy}
                              >
                                {isUpdating ? '保存中' : '保存'}
                              </button>
                              <button
                                className="item-action-btn cancel"
                                type="button"
                                onClick={handleEditCancel}
                                disabled={isBusy}
                              >
                                キャンセル
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                className="item-action-btn icon edit"
                                type="button"
                                onClick={() => handleEditStart('open_issues', item, i)}
                                disabled={isBusy || editing !== null}
                                aria-label="編集"
                                title="編集"
                              >
                                <FaPenToSquare />
                              </button>
                              <button
                                className="item-action-btn icon delete"
                                type="button"
                                onClick={() => handleDeleteItem('open_issues', i)}
                                disabled={isBusy || editing !== null}
                                aria-label="削除"
                                title="削除"
                              >
                                <FaTrash />
                              </button>
                            </>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div className="detail-section">
              <h4><FaPenToSquare className="section-icon edit" /> 追記</h4>
              <div className="append-note">
                <textarea
                  className="edit-textarea"
                  rows={4}
                  value={appendNote}
                  onChange={(event) => setAppendNoteDraft(event.target.value)}
                  disabled={isBusy}
                />
                <div className="item-actions append-note-actions">
                  <button
                    className="item-action-btn save"
                    type="button"
                    onClick={handleAppendNoteSave}
                    disabled={isBusy}
                  >
                    {isUpdating ? '保存中' : '保存'}
                  </button>
                </div>
              </div>
            </div>

            {/* Member Contributions */}
            {achievement.member_contributions.length > 0 && (
              <div className="detail-section">
                <h4><FaUsers className="section-icon members" /> メンバー貢献</h4>
                <div className="member-contributions">
                  {achievement.member_contributions.map((mc, i) => (
                    <MemberContributionCard key={i} contribution={mc} />
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ProjectAchievementsSection({ projectId }: ProjectAchievementsSectionProps) {
  const queryClient = useQueryClient();
  const timezone = useTimezone();
  const [showGenerator, setShowGenerator] = useState(false);
  const [periodStart, setPeriodStart] = useState(() => {
    return todayInTimezone(timezone).minus({ days: 7 }).toISODate() ?? '';
  });
  const [periodEnd, setPeriodEnd] = useState(() => {
    return todayInTimezone(timezone).toISODate() ?? '';
  });
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [updateTargetId, setUpdateTargetId] = useState<string | null>(null);
  const [summarizeTargetId, setSummarizeTargetId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['project-achievements', projectId],
    queryFn: () => projectAchievementsApi.list(projectId, { limit: 10 }),
  });

  const generateMutation = useMutation({
    mutationFn: () => {
      const periodStartUtc = toUtcIsoString(`${periodStart}T00:00`, timezone);
      const periodEndUtc = toUtcIsoString(`${periodEnd}T23:59`, timezone);
      if (!periodStartUtc || !periodEndUtc) {
        throw new Error('Invalid period');
      }
      return projectAchievementsApi.create(projectId, {
        period_start: periodStartUtc,
        period_end: periodEndUtc,
        period_label: `${periodStart} - ${periodEnd}`,
      });
    },
    onMutate: () => setErrorMessage(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-achievements', projectId] });
      setShowGenerator(false);
    },
    onError: () => {
      setErrorMessage('生成に失敗しました。期間内の完了タスクを確認してください。');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (achievementId: string) =>
      projectAchievementsApi.delete(projectId, achievementId),
    onMutate: (achievementId) => {
      setDeleteTargetId(achievementId);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-achievements', projectId] });
    },
    onError: () => {
      setErrorMessage('削除に失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setDeleteTargetId(null),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      achievementId,
      payload,
    }: {
      achievementId: string;
      payload: ProjectAchievementUpdate;
    }) => projectAchievementsApi.update(projectId, achievementId, payload),
    onMutate: ({ achievementId }) => {
      setUpdateTargetId(achievementId);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-achievements', projectId] });
    },
    onError: () => {
      setErrorMessage('更新に失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setUpdateTargetId(null),
  });

  const summarizeMutation = useMutation({
    mutationFn: (achievementId: string) =>
      projectAchievementsApi.summarize(projectId, achievementId),
    onMutate: (achievementId) => {
      setSummarizeTargetId(achievementId);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-achievements', projectId] });
    },
    onError: () => {
      setErrorMessage('AIまとめに失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setSummarizeTargetId(null),
  });

  const handleUpdate = (achievementId: string, payload: ProjectAchievementUpdate) =>
    updateMutation.mutateAsync({ achievementId, payload });

  const handleSummarize = (achievementId: string) => {
    if (!window.confirm('編集内容と追記を反映してAIでまとめますか？')) return;
    summarizeMutation.mutate(achievementId);
  };

  const achievements = data?.achievements ?? [];

  return (
    <div className="project-achievements-section">
      <div className="section-header">
        <div className="header-title">
          <FaTrophy className="section-icon" />
          <h3>達成項目</h3>
        </div>
        <button
          className="generate-btn"
          onClick={() => setShowGenerator(!showGenerator)}
        >
          <FaPlus />
          <span>生成</span>
        </button>
      </div>

      {errorMessage && (
        <div className="project-achievement-error" role="alert">
          {errorMessage}
        </div>
      )}

      <AnimatePresence>
        {showGenerator && (
          <motion.div
            className="achievement-generator"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="generator-form">
              <div className="period-inputs">
                <label>
                  <span>開始日</span>
                  <input
                    type="date"
                    value={periodStart}
                    onChange={(e) => setPeriodStart(e.target.value)}
                  />
                </label>
                <label>
                  <span>終了日</span>
                  <input
                    type="date"
                    value={periodEnd}
                    onChange={(e) => setPeriodEnd(e.target.value)}
                  />
                </label>
              </div>
              <div className="generator-actions">
                <button
                  className="cancel-btn"
                  onClick={() => setShowGenerator(false)}
                  disabled={generateMutation.isPending}
                >
                  キャンセル
                </button>
                <button
                  className="submit-btn"
                  onClick={() => generateMutation.mutate()}
                  disabled={generateMutation.isPending || !periodStart || !periodEnd}
                >
                  {generateMutation.isPending ? '生成中...' : '達成項目を生成'}
                </button>
              </div>
              {generateMutation.isError && (
                <div className="generator-error">
                  生成に失敗しました。期間内に完了タスクがあることを確認してください。
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="achievements-list">
        {isLoading ? (
          <div className="loading-state">読み込み中...</div>
        ) : error ? (
          <div className="error-state">達成項目の取得に失敗しました</div>
        ) : achievements.length === 0 ? (
          <div className="empty-state">
            <FaTrophy className="empty-icon" />
            <p>まだ達成項目がありません</p>
            <p className="empty-hint">「生成」ボタンから期間を指定して生成できます</p>
          </div>
        ) : (
          achievements.map((achievement) => (
            <AchievementCard
              key={achievement.id}
              achievement={achievement}
              onDelete={() => deleteMutation.mutate(achievement.id)}
              onUpdate={handleUpdate}
              onSummarize={handleSummarize}
              isDeleting={deleteTargetId === achievement.id && deleteMutation.isPending}
              isUpdating={updateTargetId === achievement.id && updateMutation.isPending}
              isSummarizing={
                summarizeTargetId === achievement.id && summarizeMutation.isPending
              }
            />
          ))
        )}
      </div>
    </div>
  );
}
