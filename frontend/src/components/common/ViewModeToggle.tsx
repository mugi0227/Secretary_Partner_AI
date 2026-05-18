import { FaGrip, FaList } from 'react-icons/fa6';
import type { ViewMode } from './viewModeStorage';
import './ViewModeToggle.css';

interface ViewModeToggleProps {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
}

export function ViewModeToggle({ value, onChange }: ViewModeToggleProps) {
  return (
    <div className="view-mode-toggle">
      <button
        className={`view-mode-btn ${value === 'normal' ? 'active' : ''}`}
        onClick={() => onChange('normal')}
        title="通常表示"
      >
        <FaGrip />
      </button>
      <button
        className={`view-mode-btn ${value === 'compact' ? 'active' : ''}`}
        onClick={() => onChange('compact')}
        title="コンパクト表示"
      >
        <FaList />
      </button>
    </div>
  );
}
