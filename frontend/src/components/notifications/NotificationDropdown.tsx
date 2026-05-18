import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { FaBell, FaCheckDouble, FaTrophy, FaUsers, FaListCheck, FaEnvelope, FaFlag, FaClipboardCheck, FaLightbulb, FaHeart, FaHeartPulse, FaComment, FaCircleInfo, FaLink } from 'react-icons/fa6';
import { motion, AnimatePresence } from 'framer-motion';
import { useNotifications, useUnreadNotificationCount } from '../../hooks/useNotifications';
import type { Notification, NotificationType } from '../../api/types';
import { formatDate } from '../../utils/dateTime';
import { useTimezone } from '../../hooks/useTimezone';
import './NotificationDropdown.css';

const NOTIFICATION_TEXT = {
  title: '通知',
  markAllRead: 'すべて既読',
  markAllReadTitle: 'すべて既読にする',
  empty: '通知はありません',
};

function getNotificationIcon(type: NotificationType) {
  switch (type) {
    case 'achievement_personal':
      return <FaTrophy className="notification-icon achievement" />;
    case 'achievement_project':
      return <FaUsers className="notification-icon project-achievement" />;
    case 'task_assigned':
      return <FaListCheck className="notification-icon task" />;
    case 'project_invited':
      return <FaEnvelope className="notification-icon invite" />;
    case 'milestone_reached':
      return <FaFlag className="notification-icon milestone" />;
    case 'checkin_created':
    case 'checkin_updated':
      return <FaClipboardCheck className="notification-icon checkin" />;
    case 'issue_new':
    case 'issue_edited':
      return <FaLightbulb className="notification-icon issue" />;
    case 'issue_liked':
      return <FaHeart className="notification-icon issue-like" />;
    case 'issue_commented':
      return <FaComment className="notification-icon issue-comment" />;
    case 'issue_status_changed':
      return <FaCircleInfo className="notification-icon issue-status" />;
    case 'heartbeat':
      return <FaHeartPulse className="notification-icon heartbeat" />;
    case 'project_link_request':
    case 'project_link_approved':
    case 'project_link_rejected':
      return <FaLink className="notification-icon project-link" />;
    default:
      return <FaBell className="notification-icon default" />;
  }
}

function getNavigationPath(notification: Notification): string | null {
  const { link_type, link_id, project_id } = notification;

  switch (link_type) {
    case 'achievement':
      return '/achievement';
    case 'project_achievement':
      return project_id ? `/projects/${project_id}/v2?tab=achievements` : null;
    case 'task':
      return link_id ? `/tasks?task=${link_id}` : '/tasks';
    case 'project':
      return link_id ? `/projects/${link_id}/v2` : '/projects';
    case 'checkin':
      return project_id ? `/projects/${project_id}/v2?tab=meetings` : null;
    case 'issue':
      return '/issues';
    default:
      return null;
  }
}

interface NotificationItemProps {
  notification: Notification;
  onRead: (id: string) => void;
  onClick: () => void;
}

function NotificationItem({ notification, onRead, onClick }: NotificationItemProps) {
  const timezone = useTimezone();

  const handleClick = () => {
    if (!notification.is_read) {
      onRead(notification.id);
    }
    onClick();
  };

  return (
    <div
      className={`notification-item ${notification.is_read ? 'read' : 'unread'}`}
      onClick={handleClick}
    >
      <div className="notification-icon-wrapper">
        {getNotificationIcon(notification.type)}
      </div>
      <div className="notification-content">
        <div className="notification-title">{notification.title}</div>
        <div className="notification-message">{notification.message}</div>
        <div className="notification-meta">
          {notification.project_name && (
            <span className="notification-project">{notification.project_name}</span>
          )}
          <span className="notification-time">
            {formatDate(
              new Date(notification.created_at),
              { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' },
              timezone
            )}
          </span>
        </div>
      </div>
      {!notification.is_read && <div className="unread-indicator" />}
    </div>
  );
}

export function NotificationDropdown() {
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownPos, setDropdownPos] = useState<{ bottom: number; left: number } | null>(null);
  const navigate = useNavigate();
  const { count: unreadCount } = useUnreadNotificationCount();
  const {
    notifications,
    markAsRead,
    markAllAsRead,
    isMarkingAllAsRead,
  } = useNotifications();

  // Calculate position from button's viewport rect
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPos({
        bottom: window.innerHeight - rect.top + 8,
        left: rect.left,
      });
    }
  }, [isOpen]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (
        buttonRef.current?.contains(target) ||
        dropdownRef.current?.contains(target)
      ) {
        return;
      }
      setIsOpen(false);
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleNotificationClick = (notification: Notification) => {
    const path = getNavigationPath(notification);
    if (path) {
      navigate(path);
    }
    setIsOpen(false);
  };

  const handleMarkAllAsRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    markAllAsRead();
  };

  const dropdownContent = (
    <AnimatePresence>
      {isOpen && dropdownPos && (
        <motion.div
          ref={dropdownRef}
          className="notification-dropdown"
          style={{
            position: 'fixed',
            bottom: dropdownPos.bottom,
            left: dropdownPos.left,
            zIndex: 9999,
          }}
          initial={{ opacity: 0, y: 10, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.95 }}
          transition={{ duration: 0.15 }}
        >
          <div className="notification-header">
            <h3>{NOTIFICATION_TEXT.title}</h3>
            {unreadCount > 0 && (
              <button
                className="mark-all-read-btn"
                onClick={handleMarkAllAsRead}
                disabled={isMarkingAllAsRead}
                aria-label={NOTIFICATION_TEXT.markAllReadTitle}
                title={NOTIFICATION_TEXT.markAllReadTitle}
              >
                <FaCheckDouble />
                <span>{NOTIFICATION_TEXT.markAllRead}</span>
              </button>
            )}
          </div>

          <div className="notification-list">
            {notifications.length === 0 ? (
              <div className="notification-empty">
                <FaBell className="empty-icon" />
                <span>{NOTIFICATION_TEXT.empty}</span>
              </div>
            ) : (
              notifications.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onRead={markAsRead}
                  onClick={() => handleNotificationClick(notification)}
                />
              ))
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  return (
    <div className="notification-dropdown-container">
      <button
        ref={buttonRef}
        className="footer-btn notification-btn"
        title={NOTIFICATION_TEXT.title}
        aria-label={
          unreadCount > 0
            ? `${NOTIFICATION_TEXT.title} (${unreadCount}件未読)`
            : NOTIFICATION_TEXT.title
        }
        onClick={() => setIsOpen(!isOpen)}
      >
        <FaBell />
        {unreadCount > 0 && (
          <span className="notification-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
        )}
      </button>

      {createPortal(dropdownContent, document.body)}
    </div>
  );
}
