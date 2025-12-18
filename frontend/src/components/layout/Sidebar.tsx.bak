import { Link, useLocation } from 'react-router-dom';
import { FaBrain, FaChartPie, FaListCheck, FaFolderOpen, FaTrophy, FaGear } from 'react-icons/fa6';
import './Sidebar.css';

export function Sidebar() {
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Dashboard', icon: FaChartPie },
    { path: '/tasks', label: 'Tasks', icon: FaListCheck },
    { path: '/projects', label: 'Projects', icon: FaFolderOpen },
    { path: '/achievement', label: 'Achievement', icon: FaTrophy },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">
          <FaBrain />
        </div>
        <span className="logo-text">Brain Dump</span>
      </div>

      <nav className="sidebar-nav">
        {navItems.map(item => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-link ${location.pathname === item.path ? 'active' : ''}`}
          >
            <item.icon className="nav-icon" />
            <span className="nav-label">{item.label}</span>
          </Link>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="user-profile">
          <div className="user-avatar">S</div>
          <div className="user-info">
            <span className="user-name">Shuhei</span>
            <span className="user-status">Online</span>
          </div>
        </div>
        <Link to="/settings" className="settings-btn" title="Settings">
          <FaGear />
        </Link>
      </div>
    </aside>
  );
}
