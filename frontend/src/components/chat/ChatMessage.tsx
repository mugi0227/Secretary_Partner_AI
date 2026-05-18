import { type CSSProperties, useMemo } from 'react';
import { FaSpinner, FaCheck, FaTriangleExclamation } from 'react-icons/fa6';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ToolCall, ProposalInfo, TimelineEvent } from '../../hooks/useChat';
import type { Task, TokenUsage } from '../../api/types';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate, toDateKey, toDateTime } from '../../utils/dateTime';
import { CreatedTaskCards } from './CreatedTaskCards';
import nagiIcon from '../../assets/nagi_icon.png';
import './ChatMessage.css';

const PREVIEW_DEFAULT_START = 0;
const PREVIEW_DEFAULT_END = 24;
const PREVIEW_MIN_START = 0;
const PREVIEW_MAX_END = 24;
const PREVIEW_HOUR_HEIGHT = 24;
const TASK_LINK_PATTERN = /task:\/\/([0-9a-fA-F-]{36})/g;

function extractLinkedTaskIds(content: string): string[] {
  const ids = new Set<string>();
  if (!content) return [];
  for (const match of content.matchAll(TASK_LINK_PATTERN)) {
    if (match[1]) {
      ids.add(match[1]);
    }
  }
  return Array.from(ids);
}

type MeetingPreviewBlock = {
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
  kind: 'proposal' | 'existing';
};

type MeetingPreviewDay = {
  key: string;
  label: string;
};

type MeetingPreviewData = {
  days: MeetingPreviewDay[];
  hours: number[];
  startHour: number;
  endHour: number;
  gridHeight: number;
  rangeLabel: string;
  blocksByDay: Map<string, MeetingPreviewBlock[]>;
};

const toLocalDateKey = (date: Date, timezone: string) => toDateKey(date, timezone);

const formatDayLabel = (dateKey: string, timezone: string) =>
  formatDate(dateKey, { month: 'numeric', day: 'numeric', weekday: 'short' }, timezone);

const formatRangeLabel = (startKey: string, endKey: string, timezone: string) => {
  const startLabel = formatDate(startKey, { month: 'numeric', day: 'numeric' }, timezone);
  const endLabel = formatDate(endKey, { month: 'numeric', day: 'numeric' }, timezone);
  return `${startLabel} - ${endLabel}`;
};

const formatTimeLabel = (date: Date, timezone: string) =>
  formatDate(date, { hour: '2-digit', minute: '2-digit' }, timezone);

const buildCombinedMeetingPreview = (
  proposals?: ProposalInfo[],
  existingMeetings?: Task[],
  timezone?: string
): MeetingPreviewData | null => {
  if (!proposals || proposals.length === 0 || !timezone) return null;

  const proposalMeetings: MeetingPreviewBlock[] = [];
  proposals.forEach((proposal) => {
    if (proposal.proposalType !== 'create_task') return;
    const payload = proposal.payload as {
      title?: string;
      is_fixed_time?: boolean;
      start_time?: string;
      end_time?: string;
      location?: string;
    };
    if (!payload.is_fixed_time || !payload.start_time || !payload.end_time) return;

    const start = toDateTime(payload.start_time, timezone);
    const end = toDateTime(payload.end_time, timezone);
    if (!start.isValid || !end.isValid) return;
    if (end.toMillis() <= start.toMillis()) return;

    const startMinutes = start.hour * 60 + start.minute;
    const endMinutesRaw = end.hour * 60 + end.minute;
    const endMinutes = Math.max(startMinutes + 15, endMinutesRaw);

    proposalMeetings.push({
      id: proposal.id,
      title: payload.title || 'Meeting',
      start: start.toJSDate(),
      end: end.toJSDate(),
      dayKey: toLocalDateKey(start.toJSDate(), timezone),
      startMinutes,
      endMinutes,
      lane: 0,
      laneCount: 1,
      location: payload.location,
      kind: 'proposal',
    });
  });

  if (proposalMeetings.length === 0) return null;

  proposalMeetings.sort((a, b) => a.start.getTime() - b.start.getTime());
  const rangeStart = toDateTime(proposalMeetings[0].start, timezone).startOf('day');
  const rangeEnd = toDateTime(proposalMeetings[proposalMeetings.length - 1].start, timezone).endOf('day');

  const existingBlocks: MeetingPreviewBlock[] = [];
  if (existingMeetings && existingMeetings.length > 0) {
    existingMeetings.forEach((task) => {
      if (!task.is_fixed_time || !task.start_time || !task.end_time) return;
      const start = toDateTime(task.start_time, timezone);
      const end = toDateTime(task.end_time, timezone);
      if (!start.isValid || !end.isValid) return;
      if (start.toMillis() < rangeStart.toMillis() || start.toMillis() > rangeEnd.toMillis()) return;
      const startMinutes = start.hour * 60 + start.minute;
      const endMinutesRaw = end.hour * 60 + end.minute;
      const endMinutes = Math.max(startMinutes + 15, endMinutesRaw);
      existingBlocks.push({
        id: task.id,
        title: task.title,
        start: start.toJSDate(),
        end: end.toJSDate(),
        dayKey: toLocalDateKey(start.toJSDate(), timezone),
        startMinutes,
        endMinutes,
        lane: 0,
        laneCount: 1,
        location: task.location,
        kind: 'existing',
      });
    });
  }

  const meetings = [...proposalMeetings, ...existingBlocks];
  meetings.sort((a, b) => a.start.getTime() - b.start.getTime());

  const dayMap = new Map<string, number>();
  meetings.forEach((meeting) => {
    if (!dayMap.has(meeting.dayKey)) {
      const dayStart = toDateTime(meeting.start, timezone).startOf('day');
      if (dayStart.isValid) {
        dayMap.set(meeting.dayKey, dayStart.toMillis());
      }
    }
  });

  const days = Array.from(dayMap.entries())
    .sort((a, b) => a[1] - b[1])
    .map(([key]) => ({ key, label: formatDayLabel(key, timezone) }));

  const minStart = Math.min(...meetings.map((meeting) => meeting.startMinutes));
  const maxEnd = Math.max(...meetings.map((meeting) => meeting.endMinutes));
  let startHour = Math.min(PREVIEW_DEFAULT_START, Math.floor(minStart / 60));
  let endHour = Math.max(PREVIEW_DEFAULT_END, Math.ceil(maxEnd / 60));
  startHour = Math.max(PREVIEW_MIN_START, startHour);
  endHour = Math.min(PREVIEW_MAX_END, Math.max(startHour + 1, endHour));

  const hourCount = endHour - startHour;
  const hours = Array.from({ length: hourCount }, (_, index) => startHour + index);
  const gridHeight = hourCount * PREVIEW_HOUR_HEIGHT;

  const blocksByDay = new Map<string, MeetingPreviewBlock[]>();
  days.forEach((day) => {
    const dayMeetings = meetings
      .filter((meeting) => meeting.dayKey === day.key)
      .sort((a, b) => a.startMinutes - b.startMinutes)
      .map((meeting) => ({ ...meeting }));

    const laneEnds: number[] = [];
    dayMeetings.forEach((meeting) => {
      let laneIndex = laneEnds.findIndex((end) => meeting.startMinutes >= end);
      if (laneIndex === -1) {
        laneIndex = laneEnds.length;
        laneEnds.push(meeting.endMinutes);
      } else {
        laneEnds[laneIndex] = meeting.endMinutes;
      }
      meeting.lane = laneIndex;
    });

    const laneCount = Math.max(1, laneEnds.length);
    dayMeetings.forEach((meeting) => {
      meeting.laneCount = laneCount;
    });

    blocksByDay.set(day.key, dayMeetings);
  });

  const rangeLabel = days.length > 0
    ? formatRangeLabel(days[0].key, days[days.length - 1].key, timezone)
    : '';

  return {
    days,
    hours,
    startHour,
    endHour,
    gridHeight,
    rangeLabel,
    blocksByDay,
  };
};

const TASK_CREATION_TOOLS = new Set(['create_task', 'create_meeting']);

function extractCreatedTaskIds(toolCalls?: ToolCall[]): string[] {
  if (!toolCalls) return [];
  const ids: string[] = [];
  for (const tc of toolCalls) {
    if (tc.status !== 'completed' || !tc.result) continue;
    if (!TASK_CREATION_TOOLS.has(tc.name)) continue;
    try {
      const parsed = JSON.parse(tc.result);
      if (parsed.status === 'pending_approval') continue;
      const taskId = parsed.id ?? parsed.task_id;
      if (typeof taskId === 'string' && taskId) {
        ids.push(taskId);
      }
    } catch {
      // ignore parse errors
    }
  }
  return ids;
}

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  proposals?: ProposalInfo[];
  meetingTasks?: Task[];
  isStreaming?: boolean;
  imageUrl?: string;
  toolPlacement?: 'before' | 'after';
  timeline?: TimelineEvent[];
  onTaskClick?: (taskId: string) => void;
  usage?: TokenUsage;
}

export function ChatMessage({
  role,
  content,
  timestamp,
  toolCalls,
  proposals,
  meetingTasks,
  isStreaming,
  imageUrl,
  toolPlacement = 'before',
  timeline,
  onTaskClick,
  usage,
}: ChatMessageProps) {
  const timezone = useTimezone();
  const combinedPreview = buildCombinedMeetingPreview(proposals, meetingTasks, timezone);
  const createdTaskIds = useMemo(() => extractCreatedTaskIds(toolCalls), [toolCalls]);
  const linkedTaskIds = useMemo(() => extractLinkedTaskIds(content), [content]);
  const taskIdsForCards = useMemo(() => {
    const ids = new Set<string>();
    createdTaskIds.forEach((id) => ids.add(id));
    linkedTaskIds.forEach((id) => ids.add(id));
    return Array.from(ids);
  }, [createdTaskIds, linkedTaskIds]);
  const taskCardHeader = linkedTaskIds.length > 0 && createdTaskIds.length === 0
    ? 'タスクを開く'
    : undefined;

  const formatTime = (date: Date) => {
    return formatDate(date, { hour: '2-digit', minute: '2-digit' }, timezone);
  };

  const getToolDisplayName = (toolName: string): string => {
    const toolNames: Record<string, string> = {
      get_current_datetime: 'Now',
      create_task: 'Create task',
      update_task: 'Update task',
      delete_task: 'Delete task',
      search_similar_tasks: 'Search tasks',
      breakdown_task: 'Breakdown task',
      search_work_memory: 'Search memory',
      add_to_memory: 'Add memory',
      refresh_user_profile: 'Refresh profile',
      schedule_agent_task: 'Schedule',
      create_project: 'Create project',
      create_work_memory: 'Create work memory',
      assign_task: 'Assign task',
      propose_phase_breakdown: 'Phase breakdown',
      plan_project_phases: 'Phase planning',
      plan_phase_tasks: 'Phase task breakdown',
      list_project_members: 'Project members',
      list_project_invitations: 'Project invitations',
      list_project_assignments: 'Project assignments',
      list_task_assignments: 'Task assignments',
      register_browser_work_memory: 'Save browser workflow',
      add_agenda_item: 'Add agenda',
      update_agenda_item: 'Update agenda',
      delete_agenda_item: 'Delete agenda',
      reorder_agenda_items: 'Reorder agenda',
    };
    return toolNames[toolName] || toolName;
  };

  const hasTimeline = !!(timeline && timeline.length > 0);

  const toolChips = !hasTimeline && toolCalls && toolCalls.length > 0 ? (
    <div className="tool-chips">
      {toolCalls.map((tool) => (
        <div key={tool.id} className={`tool-chip ${tool.status}`}>
          <span className="tool-chip-icon">
            {tool.status === 'running' ? (
              <FaSpinner className="spinner" />
            ) : tool.status === 'failed' ? (
              <FaTriangleExclamation />
            ) : (
              <FaCheck />
            )}
          </span>
          <span className="tool-chip-name">{getToolDisplayName(tool.name)}</span>
        </div>
      ))}
    </div>
  ) : null;

  const timelineItems = hasTimeline ? (
    <div className="message-timeline">
      {timeline?.map((item) =>
        item.kind === 'announcement' ? (
          <div key={item.id} className="timeline-item announcement">
            {item.content}
          </div>
        ) : (
          <div key={item.id} className="timeline-item tool">
            <div className={`tool-chip ${item.status}`}>
              <span className="tool-chip-icon">
                {item.status === 'running' ? (
                  <FaSpinner className="spinner" />
                ) : item.status === 'failed' ? (
                  <FaTriangleExclamation />
                ) : (
                  <FaCheck />
                )}
              </span>
              <span className="tool-chip-name">{getToolDisplayName(item.name)}</span>
            </div>
          </div>
        )
      )}
    </div>
  ) : null;

  const messageText = isStreaming ? (
    <div className="thinking-animation">
      <div className="thinking-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <span className="thinking-text">Thinking...</span>
    </div>
  ) : content ? (
    <div className="message-text markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children, node, ...rest }) => {
            void node;
            if (href && href.startsWith('task://')) {
              return null;
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" {...rest}>
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  ) : null;

  return (
    <div className={`chat-message ${role}`}>
      <div className="message-avatar">
        {role === 'assistant' ? (
          <img src={nagiIcon} alt="Nagi" className="avatar-icon-img" />
        ) : '👤'}
      </div>
      <div className="message-content">
        {toolPlacement === 'before' && toolChips}
        {timelineItems}

        {/* Image Attachment */}
        {imageUrl && role === 'user' && (
          <div className="message-image">
            <img src={imageUrl} alt="Uploaded attachment" />
          </div>
        )}

        {/* Meeting Preview for proposals (visual only - approval handled by ProposalPanel) */}
        {combinedPreview && (
          <div className="proposals">
            <div className="proposal-combined-preview">
              <div className="proposal-preview-header">
                <div className="proposal-preview-title">Combined preview</div>
                <div className="proposal-preview-range">{combinedPreview.rangeLabel}</div>
              </div>
              <div
                className="proposal-preview-grid"
                style={{
                  '--preview-days': combinedPreview.days.length,
                  '--preview-hour-height': `${PREVIEW_HOUR_HEIGHT}px`,
                } as CSSProperties}
              >
                <div
                  className="proposal-preview-header-row"
                  style={{ '--preview-days': combinedPreview.days.length } as CSSProperties}
                >
                  <div className="proposal-preview-time-header" />
                  {combinedPreview.days.map((day) => (
                    <div key={day.key} className="proposal-preview-day-header">
                      {day.label}
                    </div>
                  ))}
                </div>
                <div className="proposal-preview-body">
                  <div className="proposal-preview-time-col">
                    {combinedPreview.hours.map((hour) => (
                      <div key={hour} className="proposal-preview-time-slot">
                        {String(hour).padStart(2, '0')}:00
                      </div>
                    ))}
                  </div>
                  {combinedPreview.days.map((day) => {
                    const blocks = combinedPreview.blocksByDay.get(day.key) ?? [];
                    return (
                      <div
                        key={day.key}
                        className="proposal-preview-day-col"
                        style={{ height: `${combinedPreview.gridHeight}px` }}
                      >
                        <div className="proposal-preview-hour-lines">
                          {combinedPreview.hours.map((hour) => (
                            <span key={hour} className="proposal-preview-hour-line" />
                          ))}
                        </div>
                        {blocks.map((meeting) => {
                          const startBound = combinedPreview.startHour * 60;
                          const endBound = combinedPreview.endHour * 60;
                          const clampedStart = Math.max(startBound, meeting.startMinutes);
                          const clampedEnd = Math.min(endBound, meeting.endMinutes);
                          const top = ((clampedStart - startBound) / 60) * PREVIEW_HOUR_HEIGHT;
                          const height = Math.max(12, ((clampedEnd - clampedStart) / 60) * PREVIEW_HOUR_HEIGHT);
                          const width = 100 / meeting.laneCount;
                          const left = width * meeting.lane;
                          return (
                            <div
                              key={meeting.id}
                              className={`proposal-preview-block ${meeting.kind}`}
                              style={{ top: `${top}px`, height: `${height}px`, left: `${left}%`, width: `${width}%` }}
                            >
                              <div className="proposal-preview-block-title">{meeting.title}</div>
                              <div className="proposal-preview-block-time">
                                {formatTimeLabel(meeting.start, timezone)} - {formatTimeLabel(meeting.end, timezone)}
                              </div>
                              {meeting.location && (
                                <div className="proposal-preview-block-location">{meeting.location}</div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Questions are now handled by QuestionsPanel in ChatWindow */}

        {messageText}

        {taskIdsForCards.length > 0 && onTaskClick && (
          <CreatedTaskCards
            taskIds={taskIdsForCards}
            onTaskClick={onTaskClick}
            header={taskCardHeader}
          />
        )}

        {toolPlacement === 'after' && toolChips}

        <div className="message-time">
          {formatTime(timestamp)}
          {role === 'assistant' && usage && usage.total_tokens > 0 && (
            <span className="message-usage">
              {usage.total_tokens.toLocaleString()} tokens
              {usage.cost_usd != null && usage.cost_usd > 0 && (
                <> / ${usage.cost_usd < 0.01
                  ? usage.cost_usd.toFixed(4)
                  : usage.cost_usd.toFixed(2)}</>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
