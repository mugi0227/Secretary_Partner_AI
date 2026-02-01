import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { tasksApi } from '../../api/tasks';
import { useTimezone } from '../../hooks/useTimezone';
import { todayInTimezone, toDateTime } from '../../utils/dateTime';
import { userStorage } from '../../utils/userStorage';
import type { DraftCardData } from '../chat/DraftCard';
import './WeeklyMeetingNotificationBanner.css';

const MEETING_IMPORT_PROMPT =
  '今週の会議情報をまとめて登録して。以下にカレンダーの内容を貼り付けるので、それぞれ会議タスクとして作成してください：\n\n（ここに会議情報をペースト）';

const getWeekKey = (timezone: string) => {
  const today = todayInTimezone(timezone);
  const weekStart = today.minus({ days: today.weekday - 1 }).startOf('day');
  return `meetings_dismissed_${weekStart.toISODate()}`;
};

export function WeeklyMeetingNotificationBanner() {
  const timezone = useTimezone();

  const calendarIntegrationEnabled = userStorage.get('calendarIntegrationEnabled') === 'true';

  const weekKey = useMemo(() => getWeekKey(timezone), [timezone]);
  const isDismissed = userStorage.get(weekKey) === 'true';

  const today = useMemo(() => todayInTimezone(timezone), [timezone]);
  const weekStart = useMemo(
    () => today.minus({ days: today.weekday - 1 }).startOf('day'),
    [today],
  );
  const weekEnd = useMemo(() => weekStart.plus({ days: 7 }), [weekStart]);

  const { data: meetingTasks = [] } = useQuery({
    queryKey: ['meetings', 'week-notification'],
    queryFn: () => tasksApi.getAll({ includeDone: true, onlyMeetings: true }),
    staleTime: 60_000,
  });

  const hasThisWeekMeetings = useMemo(() => {
    return meetingTasks.some((task) => {
      if (!task.is_fixed_time || !task.start_time) return false;
      const start = toDateTime(task.start_time, timezone);
      if (!start.isValid) return false;
      return (
        start.toMillis() >= weekStart.toMillis() &&
        start.toMillis() < weekEnd.toMillis()
      );
    });
  }, [meetingTasks, weekStart, weekEnd, timezone]);

  if (calendarIntegrationEnabled || isDismissed || hasThisWeekMeetings) {
    return null;
  }

  const handleAddMeetings = () => {
    const event = new CustomEvent<{ message?: string; draftCard?: DraftCardData; newChat?: boolean }>(
      'secretary:chat-open',
      { detail: { message: MEETING_IMPORT_PROMPT, newChat: true } },
    );
    window.dispatchEvent(event);
  };

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    userStorage.set(weekKey, 'true');
    window.dispatchEvent(new Event('meeting-notification-dismissed'));
  };

  return (
    <button
      type="button"
      className="meeting-notification-banner"
      onClick={handleAddMeetings}
    >
      <span className="meeting-notification-icon">!</span>
      <span className="meeting-notification-text">
        今週の会議情報が追加されていません。AIチャットでまとめて登録できます。
      </span>
      <span className="meeting-notification-action">
        会議を追加 →
      </span>
      <span
        className="meeting-notification-dismiss"
        role="button"
        tabIndex={0}
        onClick={handleDismiss}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleDismiss(e as unknown as React.MouseEvent);
          }
        }}
        title="今週は非表示"
      >
        ×
      </span>
    </button>
  );
}
