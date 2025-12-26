import { FaCheck } from 'react-icons/fa';
import { FaFire, FaClock, FaLeaf, FaBatteryFull, FaBatteryQuarter, FaEllipsis, FaLock } from 'react-icons/fa6';
import { motion, AnimatePresence } from 'framer-motion';
import type { Task } from '../../api/types';
import './TaskItem.css';

interface TaskItemProps {
  task: Task;
  onCheck?: (taskId: string) => void;
  onClick?: (task: Task) => void;
  isRemoving?: boolean;
  allowToggleDone?: boolean;
  isBlocked?: boolean;
  blockedReason?: string;
}

const TEXT = {
  blocked: '\u30d6\u30ed\u30c3\u30af\u4e2d',
};

export function TaskItem({
  task,
  onCheck,
  onClick,
  isRemoving = false,
  allowToggleDone = false,
  isBlocked = false,
  blockedReason,
}: TaskItemProps) {
  const getPriorityIcon = (level: string) => {
    switch (level) {
      case 'HIGH': return <FaFire />;
      case 'MEDIUM': return <FaClock />;
      case 'LOW': return <FaLeaf />;
      default: return null;
    }
  };

  const getEnergyIcon = (level: string) => {
    return level === 'LOW' ? <FaBatteryQuarter /> : <FaBatteryFull />;
  };

  const getEnergyLabel = (level: string) => {
    return level === 'LOW' ? 'Low Energy' : 'High Energy';
  };

  const handleClick = () => {
    if (onClick) {
      onClick(task);
    }
  };

  const handleCheckClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onCheck && (allowToggleDone || task.status !== 'DONE')) {
      onCheck(task.id);
    }
  };

  const handleActionClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  const isDone = task.status === 'DONE';

  return (
    <div
      className={`task-item ${isRemoving ? 'removing' : ''}`}
      onClick={handleClick}
      data-done={isDone}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <div className={`task-check ${isDone ? 'done' : ''}`} onClick={handleCheckClick}>
        <div className="circle-bg" />
        <AnimatePresence mode="wait">
          {isDone ? (
            <motion.div
              key="check"
              className="check-icon-wrapper done"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={{ type: "spring", damping: 12, stiffness: 200 }}
            >
              <FaCheck className="check-icon" />
            </motion.div>
          ) : (
            <motion.div
              key="preview"
              className="check-icon-wrapper hover-preview"
            >
              <FaCheck className="check-icon" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="task-content">
        <span className="task-title">{task.title}</span>

        <div className="task-meta">
          {isBlocked && (
            <span className="task-dependency-indicator" title={blockedReason ?? TEXT.blocked}>
              <FaLock />
              <span>{TEXT.blocked}</span>
            </span>
          )}
          <span className={`meta-tag urgency-${task.urgency.toLowerCase()}`}>
            {getPriorityIcon(task.urgency)}
            <span>{task.urgency === 'HIGH' ? 'High Urgency' : task.urgency === 'MEDIUM' ? 'Medium' : 'Low'}</span>
          </span>

          <span className={`meta-tag energy-${task.energy_level.toLowerCase()}`}>
            {getEnergyIcon(task.energy_level)}
            <span>{getEnergyLabel(task.energy_level)}</span>
          </span>
        </div>
      </div>

      <button
        className="task-action-btn"
        aria-label="More actions"
        onClick={handleActionClick}
      >
        <FaEllipsis />
      </button>
    </div>
  );
}
