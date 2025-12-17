import { useLocation } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { FaMoon, FaSun, FaBell } from 'react-icons/fa6';
import './TopBar.css';

export function TopBar() {
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();

  const formatDate = () => {
    const now = new Date();
    const days = ['日', '月', '火', '水', '木', '金', '土'];
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const date = now.getDate();
    const day = days[now.getDay()];
    return `${year}年${month}月${date}日 (${day})`;
  };

  const getPageTitle = () => {
    if (location.pathname === '/') return 'Dashboard';
    if (location.pathname === '/tasks') return 'Tasks';
    if (location.pathname === '/projects') return 'Projects';
    return 'Dashboard';
  };

  return (
    <header className="top-bar">
      <div className="page-info">
        <h1 id="page-title">{getPageTitle()}</h1>
        <span className="date-display">{formatDate()}</span>
      </div>

      <div className="top-actions">
        <button
          className="icon-btn theme-toggle"
          id="theme-toggle"
          title="Toggle Dark Mode"
          onClick={toggleTheme}
        >
          {theme === 'light' ? <FaMoon /> : <FaSun />}
        </button>
        <button className="icon-btn notification-btn" title="Notifications">
          <FaBell />
          <span className="badge">3</span>
        </button>
      </div>
    </header>
  );
}
