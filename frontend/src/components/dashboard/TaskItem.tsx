import { FaCircle, FaCheckCircle } from 'react-icons/fa';
import { FaFire, FaClock, FaLeaf, FaBatteryFull, FaBatteryQuarter, FaEllipsis } from 'react-icons/fa6';
import type { Task } from '../../api/types';
import './TaskItem.css';

interface TaskItemProps {
  task: Task;
  onCheck?: (taskId: string) => void;
  onClick?: (task: Task) => void;
  isRemoving?: boolean;
}

export function TaskItem({ task, onCheck, onClick, isRemoving = false }: TaskItemProps) {
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
    e.stopPropagation(); // モーダルを開かないようにする
    if (onCheck && task.status !== 'DONE') {
      onCheck(task.id);
    }
  };

  const handleActionClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    // 将来的にアクションメニューを実装する場合に使用
  };

  const isDone = task.status === 'DONE';

  return (
    <div 
      className={`task-item ${isRemoving ? 'removing' : ''}`}
      onClick={handleClick}
      data-done={isDone}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <div 
        className="task-check" 
        onClick={handleCheckClick}
        style={{ cursor: 'pointer' }}
      >
        <FaCircle className="circle-icon" />
        {isDone ? (
          <FaCheckCircle className="circle-icon check-icon done" />
        ) : (
          <FaCheckCircle className="circle-icon check-icon hover-preview" />
        )}
      </div>

      <div className="task-content">
        <span className="task-title">{task.title}</span>

        <div className="task-meta">
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
