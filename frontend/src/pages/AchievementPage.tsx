import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { DateTime } from 'luxon';
import {
  FaTrophy,
  FaCheckCircle,
  FaChartLine,
  FaLightbulb,
  FaRocket,
  FaStar,
  FaEdit,
  FaMagic,
  FaSpinner,
  FaCalendarAlt,
  FaChevronDown,
  FaChevronUp,
  FaTrash,
  FaFolder,
  FaClipboardList,
  FaLink,
  FaCheck,
} from 'react-icons/fa';
import { achievementsApi } from '../api/achievements';
import type { Achievement, AchievementUpdate, CompletedTaskPreview, SkillExperience } from '../api/types';
import { useProjects } from '../hooks/useProjects';
import { useTimezone } from '../hooks/useTimezone';
import { formatDate, nowInTimezone, toDateTime } from '../utils/dateTime';
import { WeeklyProgress } from '../components/dashboard/WeeklyProgress';
import { usePageTour } from '../hooks/usePageTour';
import { PageTour } from '../components/onboarding/PageTour';
import { TourHelpButton } from '../components/onboarding/TourHelpButton';
import './AchievementPage.css';

function SkillBar({ skill, maxCount }: { skill: SkillExperience; maxCount: number }) {
  const widthPercent = maxCount > 0 ? (skill.experience_count / maxCount) * 100 : 0;

  return (
    <div className="skill-bar-container">
      <div className="skill-bar-label">
        <span className="skill-name">{skill.category}</span>
        <span className="skill-count">{skill.experience_count}件</span>
      </div>
      <div className="skill-bar-track">
        <div
          className="skill-bar-fill"
          style={{ width: `${Math.max(widthPercent, 5)}%` }}
        />
      </div>
    </div>
  );
}

function SkillSection({
  title,
  skills,
  icon,
}: {
  title: string;
  skills: SkillExperience[];
  icon: ReactNode;
}) {
  const [expanded, setExpanded] = useState(true);
  const maxCount = Math.max(...skills.map((s) => s.experience_count), 1);

  if (skills.length === 0) return null;

  return (
    <div className="skill-section">
      <button className="skill-section-header" onClick={() => setExpanded(!expanded)}>
        <span className="skill-section-icon">{icon}</span>
        <span className="skill-section-title">{title}</span>
        <span className="skill-section-count">{skills.length}カテゴリ</span>
        {expanded ? <FaChevronUp /> : <FaChevronDown />}
      </button>
      {expanded && (
        <div className="skill-bars">
          {skills
            .sort((a, b) => b.experience_count - a.experience_count)
            .map((skill) => (
              <SkillBar key={skill.category} skill={skill} maxCount={maxCount} />
            ))}
        </div>
      )}
    </div>
  );
}

const getLatestWeekPeriod = (now: DateTime) => {
  const daysSinceFriday = (now.weekday - 5 + 7) % 7;
  const weekEnd = now.startOf('day').minus({ days: daysSinceFriday });
  const weekStart = weekEnd.minus({ days: 7 });
  return { weekStart, weekEnd };
};

const formatPeriodLabel = (start: string | Date, end: string | Date, timezone: string) => {
  const startLabel = formatDate(start, { month: 'numeric', day: 'numeric' }, timezone);
  const endLabel = formatDate(end, { month: 'numeric', day: 'numeric' }, timezone);
  return `${startLabel} - ${endLabel}`;
};

const isSamePeriod = (
  achievement: Achievement,
  weekStart: DateTime,
  weekEnd: DateTime,
  timezone: string,
) => {
  const start = toDateTime(achievement.period_start, timezone).toUTC();
  const end = toDateTime(achievement.period_end, timezone).toUTC();
  return (
    Math.abs(start.toMillis() - weekStart.toUTC().toMillis()) < 1000 &&
    Math.abs(end.toMillis() - weekEnd.toUTC().toMillis()) < 1000
  );
};

type EditableSection = 'summary' | 'weekly_activities' | 'growth_points' | 'next_suggestions' | 'strengths' | 'growth_areas';

interface TaskGroup {
  projectId: string;
  projectName: string;
  tasks: CompletedTaskPreview[];
}

function groupTasksByProject(
  tasks: CompletedTaskPreview[],
  projectMap: Map<string, string>,
): TaskGroup[] {
  const groups: Record<string, CompletedTaskPreview[]> = {};
  for (const task of tasks) {
    const key = task.project_id ?? '__personal__';
    if (!groups[key]) groups[key] = [];
    groups[key].push(task);
  }
  return Object.entries(groups).map(([key, groupTasks]) => ({
    projectId: key,
    projectName:
      key === '__personal__'
        ? '個人タスク'
        : (projectMap.get(key) ?? '不明なプロジェクト'),
    tasks: groupTasks,
  }));
}

function AchievementCard({
  achievement,
  projectMap,
  onDelete,
  onRegenerate,
  onUpdate,
  onSummarize,
  onShare,
  isDeleting,
  isRegenerating,
  isUpdating,
  isSummarizing,
  isSharing,
  shareSuccess,
}: {
  achievement: Achievement;
  projectMap: Map<string, string>;
  onDelete: (achievement: Achievement) => void;
  onRegenerate: (achievement: Achievement) => void;
  onUpdate: (achievementId: string, payload: AchievementUpdate) => Promise<Achievement>;
  onSummarize: (achievement: Achievement) => void;
  onShare: (achievement: Achievement) => void;
  isDeleting: boolean;
  isRegenerating: boolean;
  isUpdating: boolean;
  isSummarizing: boolean;
  isSharing: boolean;
  shareSuccess: string | null;
}) {
  const timezone = useTimezone();
  const [expanded, setExpanded] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  const [editing, setEditing] = useState<{
    section: EditableSection;
    index?: number;
    value: string;
  } | null>(null);
  const [appendNoteDraft, setAppendNoteDraft] = useState<string | null>(null);
  const appendNote = appendNoteDraft ?? achievement.append_note ?? '';
  const taskSnapshots = useMemo(() => achievement.task_snapshots ?? [], [achievement.task_snapshots]);
  const groupedTasks = useMemo(
    () => groupTasksByProject(taskSnapshots, projectMap),
    [taskSnapshots, projectMap],
  );
  const periodLabel =
    achievement.period_label ||
    formatPeriodLabel(achievement.period_start, achievement.period_end, timezone);
  const detailsAvailable =
    achievement.growth_points.length > 0 ||
    achievement.next_suggestions.length > 0 ||
    taskSnapshots.length > 0 ||
    achievement.skill_analysis.domain_skills.length > 0 ||
    achievement.skill_analysis.soft_skills.length > 0 ||
    achievement.skill_analysis.work_types.length > 0;
  const isBusy = isDeleting || isRegenerating || isUpdating || isSummarizing;

  const handleEditStart = (section: EditableSection, value: string, index?: number) => {
    setEditing({ section, value, index });
  };

  const handleEditCancel = () => {
    setEditing(null);
  };

  const buildListPayload = (section: EditableSection, list: string[]): AchievementUpdate => {
    switch (section) {
      case 'weekly_activities':
        return { weekly_activities: list };
      case 'growth_points':
        return { growth_points: list };
      case 'next_suggestions':
        return { next_suggestions: list };
      case 'strengths':
        return { strengths: list };
      case 'growth_areas':
        return { growth_areas: list };
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
      editing.section === 'weekly_activities'
        ? achievement.weekly_activities
        : editing.section === 'growth_points'
          ? achievement.growth_points
          : editing.section === 'next_suggestions'
            ? achievement.next_suggestions
            : editing.section === 'strengths'
              ? achievement.skill_analysis.strengths
              : achievement.skill_analysis.growth_areas;
    const updatedList = listSource.map((item, index) =>
      index === editing.index ? trimmed : item
    );
    await onUpdate(achievement.id, buildListPayload(editing.section, updatedList));
    setEditing(null);
  };

  const handleDeleteItem = async (section: EditableSection, index: number) => {
    if (!window.confirm('削除しますか？')) return;
    const listSource =
      section === 'weekly_activities'
        ? achievement.weekly_activities
        : section === 'growth_points'
          ? achievement.growth_points
          : section === 'next_suggestions'
            ? achievement.next_suggestions
            : section === 'strengths'
              ? achievement.skill_analysis.strengths
              : achievement.skill_analysis.growth_areas;
    const updatedList = listSource.filter((_, itemIndex) => itemIndex !== index);
    await onUpdate(achievement.id, buildListPayload(section, updatedList));
  };

  const handleAppendNoteSave = async () => {
    await onUpdate(achievement.id, { append_note: appendNote });
    setAppendNoteDraft(null);
  };

  return (
    <div className="achievement-week-card">
      <div className="achievement-week-header">
        <div className="achievement-week-title">
          <FaCalendarAlt className="achievement-week-icon" />
          <span>{periodLabel}</span>
        </div>
        <div className="achievement-week-actions">
          <span className={`generation-type ${achievement.generation_type.toLowerCase()}`}>
            {achievement.generation_type === 'AUTO' ? '自動生成' : '手動生成'}
          </span>
          <button
            className={`achievement-action-btn share${shareSuccess === achievement.id ? ' success' : ''}`}
            type="button"
            onClick={() => onShare(achievement)}
            disabled={isBusy || isSharing}
          >
            {isSharing ? (
              <>
                <FaSpinner className="spinner" />
                共有中
              </>
            ) : shareSuccess === achievement.id ? (
              <>
                <FaCheck />
                コピー済み
              </>
            ) : (
              <>
                <FaLink />
                リンクをコピー
              </>
            )}
          </button>
          <button
            className="achievement-action-btn summarize"
            type="button"
            onClick={() => onSummarize(achievement)}
            disabled={isBusy}
          >
            {isSummarizing ? (
              <>
                <FaSpinner className="spinner" />
                まとめ中
              </>
            ) : (
              <>
                <FaMagic />
                AIでまとめる
              </>
            )}
          </button>
          <button
            className="achievement-action-btn regenerate"
            type="button"
            onClick={() => onRegenerate(achievement)}
            disabled={isBusy}
          >
            {isRegenerating ? (
              <>
                <FaSpinner className="spinner" />
                再生成中
              </>
            ) : (
              <>
                <FaRocket />
                再生成
              </>
            )}
          </button>
          <button
            className="achievement-action-btn delete"
            type="button"
            onClick={() => onDelete(achievement)}
            disabled={isBusy}
          >
            {isDeleting ? (
              <>
                <FaSpinner className="spinner" />
                削除中
              </>
            ) : (
              <>
                <FaTrash />
                削除
              </>
            )}
          </button>
        </div>
      </div>

      <div className="achievement-summary-block">
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
          <div className="achievement-week-summary markdown-content">
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
                <FaEdit />
              </button>
            )}
        </div>
      </div>

      {(achievement.weekly_activities ?? []).length > 0 && (
        <div className="weekly-activities-section">
          <h3>
            <FaClipboardList className="section-icon" />
            今週やったこと
          </h3>
          <ul className="weekly-activities-list">
            {achievement.weekly_activities.map((activity, i) => {
              const isEditingActivity =
                editing?.section === 'weekly_activities' && editing.index === i;
              return (
                <li key={i} className="editable-list-item">
                  <div className="item-content">
                    <FaCheckCircle className="activity-icon" />
                    {isEditingActivity ? (
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
                      <span className="activity-text">{activity}</span>
                    )}
                  </div>
                  <div className={`item-actions${isEditingActivity ? '' : ' hover-actions'}`}>
                    {isEditingActivity ? (
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
                          onClick={() => handleEditStart('weekly_activities', activity, i)}
                          disabled={isBusy || editing !== null}
                          aria-label="編集"
                          title="編集"
                        >
                          <FaEdit />
                        </button>
                        <button
                          className="item-action-btn icon delete"
                          type="button"
                          onClick={() => handleDeleteItem('weekly_activities', i)}
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

      <div className="achievement-week-stats">
        <div className="achievement-week-stat">
          <span className="stat-value">{achievement.task_count}</span>
          <span className="stat-label">完了タスク</span>
        </div>
        <div className="achievement-week-stat">
          <span className="stat-value">{achievement.project_ids.length}</span>
          <span className="stat-label">関連プロジェクト</span>
        </div>
      </div>

      {detailsAvailable && (
        <button className="achievement-toggle-btn" onClick={() => setExpanded(!expanded)}>
          {expanded ? '詳細を閉じる' : '詳細を見る'}
          {expanded ? <FaChevronUp /> : <FaChevronDown />}
        </button>
      )}

      {expanded && (
        <div className="achievement-week-details">
          {(achievement.skill_analysis.domain_skills.length > 0 ||
            achievement.skill_analysis.soft_skills.length > 0 ||
            achievement.skill_analysis.work_types.length > 0) && (
            <div className="achievement-section">
              <h3>
                <FaChartLine className="section-icon" />
                スキルマップ
              </h3>
              <div className="skill-map">
                <SkillSection
                  title="専門領域"
                  skills={achievement.skill_analysis.domain_skills}
                  icon="🎯"
                />
                <SkillSection
                  title="ソフトスキル"
                  skills={achievement.skill_analysis.soft_skills}
                  icon="💬"
                />
                <SkillSection
                  title="作業タイプ"
                  skills={achievement.skill_analysis.work_types}
                  icon="🛠️"
                />
              </div>

              <div className="skill-insights">
                {achievement.skill_analysis.strengths.length > 0 && (
                  <div className="insight-box strengths">
                    <h4>
                      <FaStar className="insight-icon" />
                      強み
                    </h4>
                    <ul>
                      {achievement.skill_analysis.strengths.map((s, i) => {
                        const isEditing =
                          editing?.section === 'strengths' && editing.index === i;
                        return (
                          <li key={i}>
                            <div className="insight-item-row">
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
                                <div className="insight-item-text markdown-content">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{s}</ReactMarkdown>
                                </div>
                              )}
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
                                      onClick={() => handleEditStart('strengths', s, i)}
                                      disabled={isBusy || editing !== null}
                                      aria-label="編集"
                                      title="編集"
                                    >
                                      <FaEdit />
                                    </button>
                                    <button
                                      className="item-action-btn icon delete"
                                      type="button"
                                      onClick={() => handleDeleteItem('strengths', i)}
                                      disabled={isBusy || editing !== null}
                                      aria-label="削除"
                                      title="削除"
                                    >
                                      <FaTrash />
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
                {achievement.skill_analysis.growth_areas.length > 0 && (
                  <div className="insight-box growth-areas">
                    <h4>
                      <FaRocket className="insight-icon" />
                      伸びしろ
                    </h4>
                    <ul>
                      {achievement.skill_analysis.growth_areas.map((g, i) => {
                        const isEditing =
                          editing?.section === 'growth_areas' && editing.index === i;
                        return (
                          <li key={i}>
                            <div className="insight-item-row">
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
                                <div className="insight-item-text markdown-content">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{g}</ReactMarkdown>
                                </div>
                              )}
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
                                      onClick={() => handleEditStart('growth_areas', g, i)}
                                      disabled={isBusy || editing !== null}
                                      aria-label="編集"
                                      title="編集"
                                    >
                                      <FaEdit />
                                    </button>
                                    <button
                                      className="item-action-btn icon delete"
                                      type="button"
                                      onClick={() => handleDeleteItem('growth_areas', i)}
                                      disabled={isBusy || editing !== null}
                                      aria-label="削除"
                                      title="削除"
                                    >
                                      <FaTrash />
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {achievement.growth_points.length > 0 && (
            <div className="achievement-section">
              <h3>
                <FaChartLine className="section-icon" />
                成長ポイント
              </h3>
              <ul className="growth-points-list">
                {achievement.growth_points.map((point, i) => {
                  const isEditing =
                    editing?.section === 'growth_points' && editing.index === i;
                  return (
                    <li key={i} className="editable-list-item">
                      <div className="item-content">
                        <FaCheckCircle className="point-icon" />
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
                          <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{point}</ReactMarkdown></div>
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
                              onClick={() => handleEditStart('growth_points', point, i)}
                              disabled={isBusy || editing !== null}
                              aria-label="編集"
                              title="編集"
                            >
                              <FaEdit />
                            </button>
                            <button
                              className="item-action-btn icon delete"
                              type="button"
                              onClick={() => handleDeleteItem('growth_points', i)}
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

          {achievement.next_suggestions.length > 0 && (
            <div className="achievement-section">
              <h3>
                <FaLightbulb className="section-icon" />
                次への提案
              </h3>
              <ul className="suggestions-list">
                {achievement.next_suggestions.map((suggestion, i) => {
                  const isEditing =
                    editing?.section === 'next_suggestions' && editing.index === i;
                  return (
                    <li key={i} className="editable-list-item">
                      <div className="item-content">
                        <FaRocket className="suggestion-icon" />
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
                          <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{suggestion}</ReactMarkdown></div>
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
                              onClick={() => handleEditStart('next_suggestions', suggestion, i)}
                              disabled={isBusy || editing !== null}
                              aria-label="編集"
                              title="編集"
                            >
                              <FaEdit />
                            </button>
                            <button
                              className="item-action-btn icon delete"
                              type="button"
                              onClick={() => handleDeleteItem('next_suggestions', i)}
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

          <div className="achievement-section">
            <h3>
              <FaEdit className="section-icon" />
              追記
            </h3>
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

          <div className="achievement-section">
            <h3>
              <FaCalendarAlt className="section-icon" />
              対象タスク
            </h3>
            {taskSnapshots.length === 0 ? (
              <p className="empty-hint">対象タスクはありません</p>
            ) : (
              <>
                <button
                  className="toggle-task-list"
                  onClick={() => setShowTasks(!showTasks)}
                >
                  <FaCalendarAlt />
                  対象タスク一覧を{showTasks ? '隠す' : '見る'} ({taskSnapshots.length}件)
                  {showTasks ? <FaChevronUp /> : <FaChevronDown />}
                </button>

                {showTasks && (
                  <div className="grouped-task-list">
                    {groupedTasks.map((group) => (
                      <div key={group.projectId} className="task-group">
                        <div className="task-group-header">
                          <FaFolder className="task-group-icon" />
                          <span className="task-group-name">{group.projectName}</span>
                          <span className="task-group-count">{group.tasks.length}件</span>
                        </div>
                        <ul className="task-preview-list achievement-task-list">
                          {group.tasks.map((task) => (
                            <li key={task.id} className="task-preview-item">
                              <FaCheckCircle className="check-icon" />
                              <div className="task-info">
                                <span className="task-title">{task.title}</span>
                                <span className="task-date">
                                  {formatDate(
                                    task.completed_at,
                                    { month: 'numeric', day: 'numeric' },
                                    timezone
                                  )}
                                </span>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function AchievementPage() {
  const queryClient = useQueryClient();
  const timezone = useTimezone();
  const tour = usePageTour('achievement');
  const { projects } = useProjects();
  const projectMap = useMemo(
    () => new Map(projects.map((p) => [p.id, p.name])),
    [projects],
  );
  const now = nowInTimezone(timezone);
  const { weekStart, weekEnd } = getLatestWeekPeriod(now);
  const [showPreviewTasks, setShowPreviewTasks] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [regenerateTargetId, setRegenerateTargetId] = useState<string | null>(null);
  const [updateTargetId, setUpdateTargetId] = useState<string | null>(null);
  const [summarizeTargetId, setSummarizeTargetId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: achievementsData, isLoading: isLoadingAchievements } = useQuery({
    queryKey: ['achievements', 'weekly'],
    queryFn: () => achievementsApi.list({ limit: 20 }),
  });

  const achievements = useMemo(
    () => achievementsData?.achievements ?? [],
    [achievementsData?.achievements],
  );
  const hasLatestWeekAchievement = useMemo(
    () => achievements.some((achievement) => isSamePeriod(achievement, weekStart, weekEnd, timezone)),
    [achievements, weekStart, weekEnd, timezone]
  );

  const previewEnabled = !isLoadingAchievements && !hasLatestWeekAchievement;
  const previewStartIso = weekStart.toUTC().toISO() ?? '';
  const previewEndIso = weekEnd.toUTC().toISO() ?? '';
  const weekLabel = `週次振り返り (${formatPeriodLabel(
    weekStart.toJSDate(),
    weekEnd.toJSDate(),
    timezone
  )})`;

  const { data: previewData, isLoading: isLoadingPreview } = useQuery({
    queryKey: ['achievement-preview', previewStartIso, previewEndIso],
    queryFn: () => achievementsApi.previewCompletedTasks(previewStartIso, previewEndIso),
    enabled: previewEnabled && !!previewStartIso && !!previewEndIso,
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      achievementsApi.create({
        period_start: previewStartIso,
        period_end: previewEndIso,
        period_label: weekLabel,
      }),
    onMutate: () => setErrorMessage(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['achievements'] });
      setShowPreviewTasks(false);
    },
    onError: () => {
      setErrorMessage('週次の生成に失敗しました。時間をおいて再度お試しください。');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (achievementId: string) => achievementsApi.delete(achievementId),
    onMutate: (achievementId) => {
      setDeleteTargetId(achievementId);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['achievements'] });
    },
    onError: () => {
      setErrorMessage('削除に失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setDeleteTargetId(null),
  });

  const regenerateMutation = useMutation({
    mutationFn: async (achievement: Achievement) => {
      await achievementsApi.delete(achievement.id);
      return achievementsApi.create({
        period_start: achievement.period_start,
        period_end: achievement.period_end,
        period_label:
          achievement.period_label ||
          formatPeriodLabel(achievement.period_start, achievement.period_end, timezone),
      });
    },
    onMutate: (achievement) => {
      setRegenerateTargetId(achievement.id);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['achievements'] });
    },
    onError: () => {
      setErrorMessage('再生成に失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setRegenerateTargetId(null),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      achievementId,
      payload,
    }: {
      achievementId: string;
      payload: AchievementUpdate;
    }) => achievementsApi.update(achievementId, payload),
    onMutate: ({ achievementId }) => {
      setUpdateTargetId(achievementId);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['achievements'] });
    },
    onError: () => {
      setErrorMessage('更新に失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setUpdateTargetId(null),
  });

  const summarizeMutation = useMutation({
    mutationFn: (achievementId: string) => achievementsApi.summarize(achievementId),
    onMutate: (achievementId) => {
      setSummarizeTargetId(achievementId);
      setErrorMessage(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['achievements'] });
    },
    onError: () => {
      setErrorMessage('AIまとめに失敗しました。時間をおいて再度お試しください。');
    },
    onSettled: () => setSummarizeTargetId(null),
  });

  const [shareTargetId, setShareTargetId] = useState<string | null>(null);
  const [shareSuccess, setShareSuccess] = useState<string | null>(null);

  const shareMutation = useMutation({
    mutationFn: (achievementId: string) => achievementsApi.createShareLink(achievementId),
    onMutate: (achievementId) => {
      setShareTargetId(achievementId);
      setShareSuccess(null);
      setErrorMessage(null);
    },
    onSuccess: async (data, achievementId) => {
      const url = `${window.location.origin}/shared/achievements/${data.share_token}`;
      try {
        await navigator.clipboard.writeText(url);
        setShareSuccess(achievementId);
        setTimeout(() => setShareSuccess(null), 3000);
      } catch {
        window.prompt('共有リンクをコピーしてください:', url);
      }
    },
    onError: () => {
      setErrorMessage('共有リンクの生成に失敗しました。');
    },
    onSettled: () => setShareTargetId(null),
  });

  const handleShare = (achievement: Achievement) => {
    shareMutation.mutate(achievement.id);
  };

  const handleUpdate = (achievementId: string, payload: AchievementUpdate) =>
    updateMutation.mutateAsync({ achievementId, payload });

  const handleDelete = (achievement: Achievement) => {
    if (!window.confirm('この達成項目を削除しますか？')) return;
    deleteMutation.mutate(achievement.id);
  };

  const handleRegenerate = (achievement: Achievement) => {
    if (!window.confirm('この達成項目を再生成しますか？')) return;
    regenerateMutation.mutate(achievement);
  };

  const handleSummarize = (achievement: Achievement) => {
    if (!window.confirm('編集内容と追記を反映してAIでまとめますか？')) return;
    summarizeMutation.mutate(achievement.id);
  };

  return (
    <div className="achievement-page">
      <div className="page-header">
        <div className="header-left">
          <FaTrophy className="page-icon" />
          <h2 className="page-title">達成項目</h2>
        </div>
        <div className="header-actions">
          <TourHelpButton onClick={tour.startTour} />
        </div>
      </div>

      {errorMessage && (
        <div className="achievement-error" role="alert">
          {errorMessage}
        </div>
      )}

      <div className="achievement-weekly-progress">
        <WeeklyProgress />
      </div>

      <div className="weekly-generator">
        <div className="weekly-generator-header">
          <div>
            <div className="weekly-generator-title">最新の週次</div>
            <div className="weekly-generator-range">{weekLabel}</div>
          </div>
          <div className="weekly-generator-tag">金曜締め</div>
        </div>

        {isLoadingAchievements || (previewEnabled && isLoadingPreview) ? (
          <div className="loading-state">
            <FaSpinner className="spinner" />
            読み込み中...
          </div>
        ) : hasLatestWeekAchievement ? (
          <div className="weekly-generator-status">
            週次の達成項目は生成済みです
          </div>
        ) : previewData && previewData.task_count > 0 ? (
          <div className="weekly-generator-body">
            <div className="preview-stats compact">
              <div className="stat-card">
                <div className="stat-icon completed">
                  <FaCheckCircle />
                </div>
                <div className="stat-info">
                  <div className="stat-value">{previewData.task_count}</div>
                  <div className="stat-label">完了タスク</div>
                </div>
              </div>
            </div>

            <div className="weekly-generator-actions">
              <button
                className="generate-btn"
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending || !previewStartIso || !previewEndIso}
              >
                {generateMutation.isPending ? (
                  <>
                    <FaSpinner className="spinner" />
                    生成中...
                  </>
                ) : (
                  <>
                    <FaRocket />
                    週次を生成
                  </>
                )}
              </button>
            </div>

            <div className="task-preview-section">
              <button
                className="toggle-task-list"
                onClick={() => setShowPreviewTasks(!showPreviewTasks)}
              >
                <FaCalendarAlt />
                対象タスク一覧を{showPreviewTasks ? '隠す' : '見る'}
                {showPreviewTasks ? <FaChevronUp /> : <FaChevronDown />}
              </button>

              {showPreviewTasks && (
                <div className="grouped-task-list">
                  {groupTasksByProject(previewData.tasks, projectMap).map((group) => (
                    <div key={group.projectId} className="task-group">
                      <div className="task-group-header">
                        <FaFolder className="task-group-icon" />
                        <span className="task-group-name">{group.projectName}</span>
                        <span className="task-group-count">{group.tasks.length}件</span>
                      </div>
                      <ul className="task-preview-list">
                        {group.tasks.map((task) => (
                          <li key={task.id} className="task-preview-item">
                            <FaCheckCircle className="check-icon" />
                            <div className="task-info">
                              <span className="task-title">{task.title}</span>
                              <span className="task-date">
                                {formatDate(
                                  task.completed_at,
                                  { month: 'numeric', day: 'numeric' },
                                  timezone
                                )}
                              </span>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="weekly-generator-status">
            対象期間に完了タスクがありません
          </div>
        )}
      </div>

      {isLoadingAchievements ? (
        <div className="loading-state">
          <FaSpinner className="spinner" />
          読み込み中...
        </div>
      ) : achievements.length === 0 ? (
        <div className="empty-state">
          <FaTrophy className="empty-icon" />
          <p>まだ達成項目がありません</p>
          <p className="empty-hint">週次の達成項目が生成されるとここに表示されます</p>
        </div>
      ) : (
        <div className="achievement-list">
          {achievements.map((achievement) => (
            <AchievementCard
              key={achievement.id}
              achievement={achievement}
              projectMap={projectMap}
              onDelete={handleDelete}
              onRegenerate={handleRegenerate}
              onUpdate={handleUpdate}
              onSummarize={handleSummarize}
              onShare={handleShare}
              isDeleting={deleteTargetId === achievement.id && deleteMutation.isPending}
              isRegenerating={regenerateTargetId === achievement.id && regenerateMutation.isPending}
              isUpdating={updateTargetId === achievement.id && updateMutation.isPending}
              isSummarizing={
                summarizeTargetId === achievement.id && summarizeMutation.isPending
              }
              isSharing={shareTargetId === achievement.id && shareMutation.isPending}
              shareSuccess={shareSuccess}
            />
          ))}
        </div>
      )}
      <PageTour
        run={tour.run}
        steps={tour.steps}
        stepIndex={tour.stepIndex}
        onCallback={tour.handleCallback}
      />
    </div>
  );
}
