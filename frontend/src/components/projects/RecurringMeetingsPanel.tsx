import { useCallback, useEffect, useMemo, useState } from 'react';
import { FaCalendarAlt, FaPause, FaPlay, FaPlus, FaTrash, FaPen, FaCalendarPlus } from 'react-icons/fa';
import { recurringMeetingsApi } from '../../api/recurringMeetings';
import type { RecurringMeeting, RecurringMeetingCreate, RecurrenceFrequency } from '../../api/types';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, nowInTimezone, toDateTime } from '../../utils/dateTime';
import './RecurringMeetingsPanel.css';

const WEEKDAYS = [
  { value: 0, label: '月' },
  { value: 1, label: '火' },
  { value: 2, label: '水' },
  { value: 3, label: '木' },
  { value: 4, label: '金' },
  { value: 5, label: '土' },
  { value: 6, label: '日' },
];

const FREQUENCIES: { value: RecurrenceFrequency; label: string }[] = [
  { value: 'weekly', label: '毎週' },
  { value: 'biweekly', label: '隔週' },
];

const defaultFormState = {
  title: '',
  frequency: 'weekly' as RecurrenceFrequency,
  weekday: 0,
  start_time: '10:00',
  duration_minutes: 60,
  location: '',
  attendees: '',
};

const buildNextOccurrence = (meeting: RecurringMeeting, timezone: string) => {
  const now = nowInTimezone(timezone);
  const anchorDate = toDateTime(`${meeting.anchor_date}T00:00:00`, timezone);
  const [hour, minute] = meeting.start_time.split(':').map((value) => parseInt(value, 10));
  const targetWeekday = meeting.weekday + 1;

  const alignToWeekday = (date: ReturnType<typeof toDateTime>) => {
    const delta = (targetWeekday - date.weekday + 7) % 7;
    return date.plus({ days: delta });
  };

  let candidate = alignToWeekday(now).set({ hour, minute, second: 0, millisecond: 0 });
  if (candidate.toMillis() <= now.toMillis()) {
    candidate = candidate.plus({ days: 7 });
  }
  if (candidate.toMillis() < anchorDate.toMillis()) {
    candidate = anchorDate.set({ hour, minute, second: 0, millisecond: 0 });
  }

  const intervalWeeks = meeting.frequency === 'weekly' ? 1 : 2;
  while (Math.floor(candidate.diff(anchorDate, 'days').days / 7) % intervalWeeks !== 0) {
    candidate = candidate.plus({ days: 7 });
  }

  return candidate;
};

const formatNextOccurrence = (meeting: RecurringMeeting, timezone: string) => {
  const next = buildNextOccurrence(meeting, timezone);
  return formatDate(
    next.toJSDate(),
    { month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit' },
    timezone,
  );
};

interface RecurringMeetingsPanelProps {
  projectId: string;
}

export function RecurringMeetingsPanel({ projectId }: RecurringMeetingsPanelProps) {
  const timezone = useTimezone();
  const [meetings, setMeetings] = useState<RecurringMeeting[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingMeeting, setEditingMeeting] = useState<RecurringMeeting | null>(null);
  const [formState, setFormState] = useState(defaultFormState);
  const [generatingMeetingId, setGeneratingMeetingId] = useState<string | null>(null);
  const [lookaheadDays, setLookaheadDays] = useState(30);
  const [generateSuccess, setGenerateSuccess] = useState<string | null>(null);

  const loadMeetings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await recurringMeetingsApi.list({ projectId, includeInactive: true });
      setMeetings(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load recurring meetings:', err);
      setError('定例会議の読み込みに失敗しました。');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadMeetings();
  }, [loadMeetings]);

  const meetingCards = useMemo(() => {
    return meetings.map((meeting) => ({
      ...meeting,
      nextLabel: formatNextOccurrence(meeting, timezone),
      frequencyLabel: FREQUENCIES.find((item) => item.value === meeting.frequency)?.label ?? meeting.frequency,
      weekdayLabel: WEEKDAYS.find((item) => item.value === meeting.weekday)?.label ?? String(meeting.weekday),
      startTimeLabel: meeting.start_time.slice(0, 5),
    }));
  }, [meetings, timezone]);

  const resetForm = () => {
    setFormState(defaultFormState);
    setEditingMeeting(null);
  };

  const openCreateForm = () => {
    setError(null);
    resetForm();
    setIsFormOpen(true);
  };

  const openEditForm = (meeting: RecurringMeeting) => {
    setError(null);
    setEditingMeeting(meeting);
    setFormState({
      title: meeting.title,
      frequency: meeting.frequency,
      weekday: meeting.weekday,
      start_time: meeting.start_time.slice(0, 5),
      duration_minutes: meeting.duration_minutes,
      location: meeting.location ?? '',
      attendees: meeting.attendees.join(', '),
    });
    setIsFormOpen(true);
  };

  const handleCancel = () => {
    setIsFormOpen(false);
    setError(null);
    resetForm();
  };

  const handleSave = async () => {
    if (isSaving) return;
    if (!formState.title.trim()) {
      setError('タイトルを入力してください。');
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const attendees = formState.attendees
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);

      if (editingMeeting) {
        await recurringMeetingsApi.update(editingMeeting.id, {
          title: formState.title.trim(),
          frequency: formState.frequency,
          weekday: formState.weekday,
          start_time: formState.start_time,
          duration_minutes: formState.duration_minutes,
          location: formState.location.trim(),
          attendees,
        });
      } else {
        const payload: RecurringMeetingCreate = {
          title: formState.title.trim(),
          project_id: projectId,
          frequency: formState.frequency,
          weekday: formState.weekday,
          start_time: formState.start_time,
          duration_minutes: formState.duration_minutes,
          location: formState.location.trim() || undefined,
          attendees,
          agenda_window_days: 7,
        };
        await recurringMeetingsApi.create(payload);
      }
      setIsFormOpen(false);
      resetForm();
      await loadMeetings();
    } catch (err) {
      console.error('Failed to save recurring meeting:', err);
      setError(editingMeeting ? '定例会議の更新に失敗しました。' : '定例会議の作成に失敗しました。');
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggleActive = async (meeting: RecurringMeeting) => {
    try {
      await recurringMeetingsApi.update(meeting.id, { is_active: !meeting.is_active });
      await loadMeetings();
    } catch (err) {
      console.error('Failed to update recurring meeting:', err);
      setError('定例会議の更新に失敗しました。');
    }
  };

  const handleDelete = async (meetingId: string) => {
    const confirmed = window.confirm('この定例会議を削除しますか？');
    if (!confirmed) return;
    try {
      await recurringMeetingsApi.delete(meetingId);
      setMeetings((prev) => prev.filter((item) => item.id !== meetingId));
    } catch (err) {
      console.error('Failed to delete recurring meeting:', err);
      setError('定例会議の削除に失敗しました。');
    }
  };

  const handleGenerateTasks = async (meetingId: string) => {
    setGeneratingMeetingId(meetingId);
    setError(null);
    setGenerateSuccess(null);
    try {
      const result = await recurringMeetingsApi.generateTasks(meetingId, lookaheadDays);
      setGenerateSuccess(`${result.created_count}件の会議を作成しました。`);
      setTimeout(() => setGenerateSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to generate tasks:', err);
      setError('会議の作成に失敗しました。');
    } finally {
      setGeneratingMeetingId(null);
    }
  };

  return (
    <div className="detail-section recurring-meetings-section">
      <div className="section-header">
        <FaCalendarAlt className="section-icon" />
        <h3 className="section-title">定例会議</h3>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label style={{ fontSize: '0.9rem' }}>作成期間:</label>
          <select
            value={lookaheadDays}
            onChange={(e) => setLookaheadDays(parseInt(e.target.value, 10))}
            style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid #ccc' }}
          >
            <option value={7}>7日先まで</option>
            <option value={14}>14日先まで</option>
            <option value={30}>30日先まで</option>
            <option value={60}>60日先まで</option>
            <option value={90}>90日先まで</option>
          </select>
          <button
            type="button"
            className="recurring-toggle-btn"
            onClick={() => (isFormOpen ? handleCancel() : openCreateForm())}
          >
            {isFormOpen ? '閉じる' : '定例会議を追加'}
          </button>
        </div>
      </div>

      {isFormOpen && (
        <div className="recurring-meetings-form">
          <div className="recurring-form-header">
            <h4>{editingMeeting ? '定例会議を編集' : '定例会議を追加'}</h4>
            {editingMeeting && (
              <button type="button" className="recurring-cancel-btn" onClick={handleCancel}>
                キャンセル
              </button>
            )}
          </div>
          <div className="recurring-form-row">
            <label htmlFor="meeting-title">タイトル</label>
            <input
              id="meeting-title"
              type="text"
              value={formState.title}
              onChange={(event) => setFormState((prev) => ({ ...prev, title: event.target.value }))}
              placeholder="週次定例"
            />
          </div>
          <div className="recurring-form-grid">
            <div className="recurring-form-row">
              <label htmlFor="meeting-frequency">頻度</label>
              <select
                id="meeting-frequency"
                value={formState.frequency}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, frequency: event.target.value as RecurrenceFrequency }))
                }
              >
                {FREQUENCIES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="recurring-form-row">
              <label htmlFor="meeting-weekday">曜日</label>
              <select
                id="meeting-weekday"
                value={formState.weekday}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, weekday: parseInt(event.target.value, 10) }))
                }
              >
                {WEEKDAYS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="recurring-form-row">
              <label htmlFor="meeting-time">開始時刻</label>
              <input
                id="meeting-time"
                type="time"
                value={formState.start_time}
                onChange={(event) => setFormState((prev) => ({ ...prev, start_time: event.target.value }))}
              />
            </div>
            <div className="recurring-form-row">
              <label htmlFor="meeting-duration">所要時間（分）</label>
              <input
                id="meeting-duration"
                type="number"
                min={15}
                max={480}
                value={formState.duration_minutes}
                onChange={(event) =>
                  setFormState((prev) => {
                    const parsed = parseInt(event.target.value, 10);
                    return { ...prev, duration_minutes: Number.isNaN(parsed) ? prev.duration_minutes : parsed };
                  })
                }
              />
            </div>
          </div>
          <div className="recurring-form-grid">
            <div className="recurring-form-row">
              <label htmlFor="meeting-location">場所</label>
              <input
                id="meeting-location"
                type="text"
                value={formState.location}
                onChange={(event) => setFormState((prev) => ({ ...prev, location: event.target.value }))}
                placeholder="Zoom / 会議室A"
              />
            </div>
            <div className="recurring-form-row">
              <label htmlFor="meeting-attendees">参加者</label>
              <input
                id="meeting-attendees"
                type="text"
                value={formState.attendees}
                onChange={(event) => setFormState((prev) => ({ ...prev, attendees: event.target.value }))}
                placeholder="田中さん, 佐藤さん"
              />
            </div>
          </div>
          {error && <p className="recurring-meetings-error">{error}</p>}
          <div className="recurring-form-actions">
            <button
              type="button"
              className="recurring-create-btn"
              onClick={handleSave}
              disabled={isSaving}
            >
              <FaPlus />
              {isSaving ? '保存中...' : (editingMeeting ? '更新する' : '定例会議を追加')}
            </button>
            <button type="button" className="recurring-cancel-btn" onClick={handleCancel}>
              閉じる
            </button>
          </div>
        </div>
      )}

      {!isFormOpen && error && <p className="recurring-meetings-error">{error}</p>}
      {generateSuccess && <p className="recurring-meetings-success">{generateSuccess}</p>}
      <div className="recurring-meetings-list">
        {isLoading ? (
          <p className="recurring-meetings-empty">読み込み中...</p>
        ) : meetingCards.length === 0 ? (
          <p className="recurring-meetings-empty">定例会議はまだありません。</p>
        ) : (
          meetingCards.map((meeting) => (
            <div key={meeting.id} className={`recurring-meeting-card ${meeting.is_active ? '' : 'inactive'}`}>
              <div className="recurring-meeting-main">
                <div className="recurring-meeting-title">{meeting.title}</div>
                <div className="recurring-meeting-meta">
                  <span>{meeting.frequencyLabel}</span>
                  <span>{meeting.weekdayLabel}</span>
                  <span>{meeting.startTimeLabel}</span>
                  <span>{meeting.duration_minutes}分</span>
                </div>
                {meeting.location && <div className="recurring-meeting-location">{meeting.location}</div>}
                <div className="recurring-meeting-next">次回: {meeting.nextLabel}</div>
              </div>
              <div className="recurring-meeting-actions">
                <button
                  type="button"
                  className="recurring-action-btn primary"
                  onClick={() => handleGenerateTasks(meeting.id)}
                  disabled={generatingMeetingId === meeting.id}
                >
                  <FaCalendarPlus />
                  {generatingMeetingId === meeting.id ? '作成中...' : '会議作成'}
                </button>
                <button
                  type="button"
                  className="recurring-action-btn"
                  onClick={() => openEditForm(meeting)}
                >
                  <FaPen />
                  編集
                </button>
                <button
                  type="button"
                  className="recurring-action-btn"
                  onClick={() => handleToggleActive(meeting)}
                >
                  {meeting.is_active ? <FaPause /> : <FaPlay />}
                  {meeting.is_active ? '停止' : '再開'}
                </button>
                <button
                  type="button"
                  className="recurring-action-btn danger"
                  onClick={() => handleDelete(meeting.id)}
                >
                  <FaTrash />
                  削除
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
