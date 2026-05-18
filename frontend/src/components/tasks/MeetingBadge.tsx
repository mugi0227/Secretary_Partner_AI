import { FaCalendarAlt, FaMapMarkerAlt, FaUsers } from 'react-icons/fa';
import type { Task } from '../../api/types';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate } from '../../utils/dateTime';
import './MeetingBadge.css';

interface MeetingBadgeProps {
  task: Task;
  showDetails?: boolean;
}

export function MeetingBadge({ task, showDetails = false }: MeetingBadgeProps) {
  const timezone = useTimezone();

  if (!task.is_fixed_time) {
    return null;
  }

  const formatTime = (dateString: string) => {
    return formatDate(dateString, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }, timezone);
  };

  const formatDateRange = (start?: string, end?: string) => {
    if (!start || !end) return '';
    return `${formatTime(start)} - ${formatTime(end)}`;
  };

  const getTimeDisplay = () => {
    if (task.is_all_day) {
      return '終日';
    }
    return formatDateRange(task.start_time, task.end_time);
  };

  if (!showDetails) {
    // Compact badge for inline display
    return (
      <span className="meeting-badge compact">
        <FaCalendarAlt className="meeting-icon" />
        {(task.is_all_day || (task.start_time && task.end_time)) && (
          <span className="meeting-time">
            {getTimeDisplay()}
          </span>
        )}
        {task.location && (
          <span className="meeting-location">· {task.location}</span>
        )}
      </span>
    );
  }

  // Detailed view for task cards
  return (
    <div className="meeting-badge detailed">
      <div className="meeting-header">
        <FaCalendarAlt className="meeting-icon" />
        <span className="meeting-label">会議</span>
      </div>

      {(task.is_all_day || (task.start_time && task.end_time)) && (
        <div className="meeting-detail">
          <span className="meeting-time-range">
            {getTimeDisplay()}
          </span>
        </div>
      )}

      {task.location && (
        <div className="meeting-detail">
          <FaMapMarkerAlt className="detail-icon" />
          <span>{task.location}</span>
        </div>
      )}

      {task.attendees && task.attendees.length > 0 && (
        <div className="meeting-detail">
          <FaUsers className="detail-icon" />
          <span>{task.attendees.length}名参加</span>
        </div>
      )}
    </div>
  );
}
