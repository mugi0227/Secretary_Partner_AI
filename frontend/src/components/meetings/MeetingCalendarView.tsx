import { useState } from 'react';
import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { tasksApi } from '../../api/tasks';
import type { Task } from '../../api/types';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateKey, toDateTime, todayInTimezone } from '../../utils/dateTime';

const DEFAULT_START_HOUR = 0;
const DEFAULT_END_HOUR = 24;
const MIN_START_HOUR = 0;
const MAX_END_HOUR = 24;
const HOUR_HEIGHT = 44;

const toLocalDateKey = (date: Date, timezone: string) => toDateKey(date, timezone);

const startOfWeek = (date: ReturnType<typeof todayInTimezone>) => {
  const diff = date.weekday - 1;
  return date.minus({ days: diff }).startOf('day');
};

const formatDayLabel = (date: Date, timezone: string) => (
  formatDate(date, { month: 'numeric', day: 'numeric', weekday: 'short' }, timezone)
);

const formatTime = (date: Date, timezone: string) => (
  formatDate(date, { hour: '2-digit', minute: '2-digit' }, timezone)
);

type MeetingBlock = {
  id: string;
  title: string;
  start: Date;
  end: Date;
  dayKey: string;
  startMinutes: number;
  endMinutes: number;
  lane: number;
  laneCount: number;
  location?: string;
  status: Task['status'];
  recurringMeetingId?: string;
};

interface MeetingCalendarViewProps {
  projectId?: string;
  onMeetingSelect?: (task: Task, date: Date) => void;
}

export function MeetingCalendarView({
  projectId,
  onMeetingSelect
}: MeetingCalendarViewProps) {
  const timezone = useTimezone();
  const [weekOffset, setWeekOffset] = useState(0);

  const today = todayInTimezone(timezone);
  const currentWeekStart = startOfWeek(today);
  const weekStart = currentWeekStart.plus({ days: weekOffset * 7 });

  const weekEnd = weekStart.plus({ days: 7 });
  const weekStartKey = toDateKey(weekStart.toJSDate(), timezone);

  const isCurrentWeek = weekOffset === 0;
  const goToPrevWeek = () => setWeekOffset(prev => prev - 1);
  const goToNextWeek = () => setWeekOffset(prev => prev + 1);
  const goToCurrentWeek = () => setWeekOffset(0);

  const days = (
    Array.from({ length: 7 }, (_, index) => {
      return weekStart.plus({ days: index });
    })
  );

  const { data: meetingTasks = [], isLoading, error } = useQuery({
    queryKey: ['meetings', 'week', weekStartKey, projectId],
    queryFn: () => tasksApi.getAll({
      includeDone: true,
      onlyMeetings: true,
      ...(projectId ? { projectId } : {})
    }),
    staleTime: 30_000,
  });

  const weekStartDate = weekStart.startOf('day');
  const weekEndDateForFilter = weekEnd.startOf('day');
  const meetings = meetingTasks
    .filter(task => task.is_fixed_time && task.start_time && task.end_time)
    .map((task): MeetingBlock | null => {
      const start = toDateTime(task.start_time as string, timezone);
      const end = toDateTime(task.end_time as string, timezone);
      if (!start.isValid || !end.isValid) return null;
      if (
        start.toMillis() < weekStartDate.toMillis() ||
        start.toMillis() >= weekEndDateForFilter.toMillis()
      ) {
        return null;
      }
      const startMinutes = start.hour * 60 + start.minute;
      const endMinutesRaw = end.hour * 60 + end.minute;
      const endMinutes = Math.max(startMinutes + 15, endMinutesRaw);
      const block: MeetingBlock = {
        id: task.id,
        title: task.title,
        start: start.toJSDate(),
        end: end.toJSDate(),
        dayKey: toLocalDateKey(start.toJSDate(), timezone),
        startMinutes,
        endMinutes,
        lane: 0,
        laneCount: 1,
        status: task.status,
      };
      if (task.location) {
        block.location = task.location;
      }
      if (task.recurring_meeting_id) {
        block.recurringMeetingId = task.recurring_meeting_id;
      }
      return block;
    })
    .filter((meeting): meeting is MeetingBlock => meeting !== null);

  const timeBounds = (() => {
    if (!meetings.length) {
      return { startHour: DEFAULT_START_HOUR, endHour: DEFAULT_END_HOUR };
    }
    const minStart = Math.min(...meetings.map(meeting => meeting.startMinutes));
    const maxEnd = Math.max(...meetings.map(meeting => meeting.endMinutes));
    let startHour = Math.min(DEFAULT_START_HOUR, Math.floor(minStart / 60));
    let endHour = Math.max(DEFAULT_END_HOUR, Math.ceil(maxEnd / 60));
    startHour = Math.max(MIN_START_HOUR, startHour);
    endHour = Math.min(MAX_END_HOUR, Math.max(startHour + 1, endHour));
    return { startHour, endHour };
  })();

  const meetingsByDay = (() => {
    const grouped = new Map<string, MeetingBlock[]>();
    meetings.forEach(meeting => {
      const list = grouped.get(meeting.dayKey) ?? [];
      list.push({ ...meeting });
      grouped.set(meeting.dayKey, list);
    });

    const results = new Map<string, MeetingBlock[]>();
    grouped.forEach((list, dayKey) => {
      const sorted = [...list].sort((a, b) => a.startMinutes - b.startMinutes);
      const laneEnds: number[] = [];
      const withLanes = sorted.map(item => {
        let laneIndex = laneEnds.findIndex(end => item.startMinutes >= end);
        if (laneIndex === -1) {
          laneIndex = laneEnds.length;
          laneEnds.push(item.endMinutes);
        } else {
          laneEnds[laneIndex] = item.endMinutes;
        }
        return { ...item, lane: laneIndex };
      });
      const laneCount = Math.max(1, laneEnds.length);
      results.set(
        dayKey,
        withLanes.map(item => ({ ...item, laneCount }))
      );
    });

    return results;
  })();

  const hourCount = timeBounds.endHour - timeBounds.startHour;
  const hours = (
    Array.from({ length: hourCount }, (_, index) => timeBounds.startHour + index)
  );

  const gridHeight = hourCount * HOUR_HEIGHT;

  const handleMeetingClick = (meeting: MeetingBlock) => {
    if (onMeetingSelect) {
      const task = meetingTasks.find(t => t.id === meeting.id);
      if (task) {
        onMeetingSelect(task, meeting.start);
      }
    }
  };

  const weekEndDate = weekEnd.minus({ days: 1 });
  const startLabel = formatDate(weekStart.toJSDate(), { month: 'numeric', day: 'numeric' }, timezone);
  const endLabel = formatDate(weekEndDate.toJSDate(), { month: 'numeric', day: 'numeric' }, timezone);
  const rangeLabel = `${startLabel} - ${endLabel}`;

  return (
    <div className="meeting-calendar-view">
      <div className="meeting-calendar-header">
        <div className="meeting-calendar-nav">
          <button
            type="button"
            className="meeting-calendar-nav-btn"
            onClick={goToPrevWeek}
            aria-label="前の週"
          >
            ←
          </button>
          <span className="meeting-calendar-range">{rangeLabel}</span>
          <button
            type="button"
            className="meeting-calendar-nav-btn"
            onClick={goToNextWeek}
            aria-label="次の週"
          >
            →
          </button>
          {!isCurrentWeek && (
            <button
              type="button"
              className="meeting-calendar-today-btn"
              onClick={goToCurrentWeek}
            >
              今週
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-message">会議の読み込みに失敗しました</div>}
      {isLoading && <div className="loading-state">読み込み中...</div>}
      {!isLoading && !error && meetings.length === 0 && (
        <div className="meeting-calendar-empty">この週には会議がありません</div>
      )}

      {!isLoading && !error && (
        <div className="meeting-calendar-grid">
          <div className="meeting-calendar-header-row" style={{ '--days': days.length } as CSSProperties}>
            <div className="meeting-calendar-time-header" />
            {days.map(day => {
              const dayKey = toLocalDateKey(day.toJSDate(), timezone);
              const isToday = dayKey === toLocalDateKey(today.toJSDate(), timezone);
              return (
                <div
                  key={dayKey}
                  className={`meeting-calendar-day-header ${isToday ? 'today' : ''}`}
                >
                  {formatDayLabel(day.toJSDate(), timezone)}
                </div>
              );
            })}
          </div>
          <div className="meeting-calendar-body" style={{ '--days': days.length, '--hour-height': `${HOUR_HEIGHT}px` } as CSSProperties}>
            <div className="meeting-calendar-time-col">
              {hours.map(hour => (
                <div key={hour} className="meeting-calendar-time-slot">
                  {String(hour).padStart(2, '0')}:00
                </div>
              ))}
            </div>
            {days.map(day => {
              const dayKey = toLocalDateKey(day.toJSDate(), timezone);
              const dayMeetings = meetingsByDay.get(dayKey) ?? [];
              return (
                <div key={dayKey} className="meeting-calendar-day-col" style={{ height: `${gridHeight}px` }}>
                  <div className="meeting-calendar-hour-lines">
                    {hours.map(hour => (
                      <span key={hour} className="meeting-calendar-hour-line" />
                    ))}
                  </div>
                  {dayMeetings.map(meeting => {
                    const startBound = timeBounds.startHour * 60;
                    const endBound = timeBounds.endHour * 60;
                    const clampedStart = Math.max(startBound, meeting.startMinutes);
                    const clampedEnd = Math.min(endBound, meeting.endMinutes);
                    const top = ((clampedStart - startBound) / 60) * HOUR_HEIGHT;
                    const height = Math.max(18, ((clampedEnd - clampedStart) / 60) * HOUR_HEIGHT);
                    const width = 100 / meeting.laneCount;
                    const left = width * meeting.lane;
                    const timeLabel = `${formatTime(meeting.start, timezone)} - ${formatTime(meeting.end, timezone)}`;
                    return (
                      <div
                        key={meeting.id}
                        className={`meeting-calendar-block ${meeting.status === 'DONE' ? 'done' : ''}`}
                        style={{ top: `${top}px`, height: `${height}px`, left: `${left}%`, width: `${width}%` }}
                        title={`${meeting.title} (${timeLabel})`}
                        role="button"
                        tabIndex={0}
                        onClick={() => handleMeetingClick(meeting)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            handleMeetingClick(meeting);
                          }
                        }}
                      >
                        <div className="meeting-calendar-block-title">{meeting.title}</div>
                        <div className="meeting-calendar-block-time">{timeLabel}</div>
                        {meeting.location && <div className="meeting-calendar-block-location">{meeting.location}</div>}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
