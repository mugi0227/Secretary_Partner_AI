import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FaChartPie, FaListCheck, FaFolderOpen, FaTrophy, FaGear, FaMoon, FaSun, FaRightFromBracket, FaRightToBracket, FaBookOpen, FaComments, FaChevronLeft, FaChevronRight, FaChevronDown, FaLock, FaUsers } from 'react-icons/fa6';
import { useTheme } from '../../context/ThemeContext';
import { clearAuthToken, getAuthToken } from '../../api/auth';
import { SettingsModal } from '../settings/SettingsModal';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { projectsApi } from '../../api/projects';
import type { ProjectWithTaskCount } from '../../api/types';
import { NotificationDropdown } from '../notifications/NotificationDropdown';
import { resolveDisplayName } from '../../utils/displayName';
import nagiIcon from '../../assets/nagi_icon.png';
import nagiBanner from '../../assets/nagi_banner.png';
import './Sidebar.css';

interface ProjectTreeNode {
  project: ProjectWithTaskCount;
  children: ProjectTreeNode[];
}

function buildProjectTree(projects: ProjectWithTaskCount[]): ProjectTreeNode[] {
  const nodeMap = new Map<string, ProjectTreeNode>();
  for (const project of projects) {
    nodeMap.set(project.id, { project, children: [] });
  }
  const roots: ProjectTreeNode[] = [];
  for (const project of projects) {
    const node = nodeMap.get(project.id)!;
    if (project.parent_project_id && nodeMap.has(project.parent_project_id)) {
      nodeMap.get(project.parent_project_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

interface ProjectTreeItemProps {
  node: ProjectTreeNode;
  depth: number;
  expandedIds: Set<string>;
  onToggle: (e: React.MouseEvent, id: string) => void;
  location: { pathname: string };
  onNavClick: () => void;
}

function ProjectTreeItem({ node, depth, expandedIds, onToggle, location, onNavClick }: ProjectTreeItemProps) {
  const { project } = node;
  const hasChildren = node.children.length > 0;
  const isExpanded = expandedIds.has(project.id);
  const projectPath = `/projects/${project.id}/v2`;
  const isActive = location.pathname === projectPath || location.pathname === `/projects/${project.id}`;

  return (
    <>
      <div className="project-subitem-row" style={{ paddingLeft: `${depth * 16}px` }}>
        {hasChildren ? (
          <button
            className="project-tree-toggle"
            onClick={(e) => onToggle(e, project.id)}
            title={isExpanded ? '折りたたむ' : '展開する'}
          >
            {isExpanded ? <FaChevronDown style={{ fontSize: '0.5rem' }} /> : <FaChevronRight style={{ fontSize: '0.5rem' }} />}
          </button>
        ) : (
          <span className="project-tree-toggle-spacer" />
        )}
        <Link
          to={projectPath}
          className={`project-subitem ${isActive ? 'active' : ''}`}
          title={project.name}
          onClick={onNavClick}
          style={{ flex: 1, minWidth: 0 }}
        >
          {project.visibility === 'TEAM'
            ? <FaUsers className="project-subitem-icon" />
            : <FaLock className="project-subitem-icon" />
          }
          <span className="project-subitem-name">{project.name}</span>
        </Link>
      </div>
      {hasChildren && isExpanded && node.children.map(child => (
        <ProjectTreeItem
          key={child.project.id}
          node={child}
          depth={depth + 1}
          expandedIds={expandedIds}
          onToggle={onToggle}
          location={location}
          onNavClick={onNavClick}
        />
      ))}
    </>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  isMobile?: boolean;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function Sidebar({ collapsed, onToggle, isMobile, mobileOpen, onMobileClose }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const { token, source } = getAuthToken();
  const { data: currentUser } = useCurrentUser();
  const [showSettings, setShowSettings] = useState(false);
  const [totalUnassigned, setTotalUnassigned] = useState(0);
  const [projects, setProjects] = useState<ProjectWithTaskCount[]>([]);
  const [projectsExpanded, setProjectsExpanded] = useState(() => {
    return localStorage.getItem('secretary_sidebar_projects_expanded') === 'true';
  });
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<string>>(new Set());
  const isAuthLocked = source === 'env' || source === 'mock';
  const displayName = currentUser
    ? resolveDisplayName({
        firstName: currentUser.first_name,
        lastName: currentUser.last_name,
        displayName: currentUser.display_name,
        userId: currentUser.id,
      })
    : (token ? 'User' : 'Guest');
  const avatarLabel = displayName ? displayName[0]?.toUpperCase() : '?';

  useEffect(() => {
    if (!token) return;
    projectsApi.getAll().then((fetched) => {
      setProjects(fetched);
      const total = fetched.reduce((sum, p) => sum + (p.unassigned_tasks || 0), 0);
      setTotalUnassigned(total);
    }).catch(() => {
      // Ignore errors
    });
  }, [token, location.pathname]);

  const toggleProjectsExpanded = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setProjectsExpanded(prev => {
      const next = !prev;
      localStorage.setItem('secretary_sidebar_projects_expanded', String(next));
      return next;
    });
  };

  const activeProjects = projects.filter(p => p.status === 'ACTIVE');

  const projectTree = useMemo(() => buildProjectTree(activeProjects), [activeProjects]);

  const toggleProjectNode = useCallback((e: React.MouseEvent, projectId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setExpandedProjectIds(prev => {
      const next = new Set(prev);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
  }, []);

  const enableIssues = import.meta.env.VITE_ENABLE_ISSUES === 'true';

  const navItems = [
    { path: '/', label: 'ダッシュボード', icon: FaChartPie },
    { path: '/tasks', label: 'タスク', icon: FaListCheck },
    { path: '/projects', label: 'プロジェクト', icon: FaFolderOpen },
    { path: '/memories', label: 'メモリー', icon: FaBookOpen },
    { path: '/achievement', label: '達成項目', icon: FaTrophy },
    ...(enableIssues ? [{ path: '/issues', label: '要望', icon: FaComments }] : []),
  ];

  const handleLogout = () => {
    if (isAuthLocked) return;
    clearAuthToken();
    navigate('/login');
  };

  const handleLogin = () => {
    navigate('/login');
  };

  // On mobile, sidebar is always shown expanded (full labels) regardless of collapsed state
  const showCollapsed = collapsed && !isMobile;

  const handleNavClick = () => {
    if (isMobile && onMobileClose) {
      onMobileClose();
    }
  };

  return (
    <>
      {isMobile && (
        <div
          className={`sidebar-backdrop ${mobileOpen ? 'visible' : ''}`}
          onClick={onMobileClose}
        />
      )}
      <aside
        className={`sidebar ${showCollapsed ? 'collapsed' : ''} ${isMobile && mobileOpen ? 'mobile-open' : ''}`}
        style={isMobile ? (mobileOpen ? {
          position: 'fixed',
          top: 0,
          left: 0,
          bottom: 0,
          width: 280,
          zIndex: 2000,
          borderRadius: 0,
          transform: 'translateX(0)',
          boxShadow: '0 25px 50px rgba(0,0,0,0.25)',
        } : {
          position: 'fixed',
          transform: 'translateX(-100%)',
          width: 280,
          pointerEvents: 'none',
        }) : undefined}
      >
      <div className="sidebar-header">
        {showCollapsed ? (
          <div className="sidebar-logo">
            <img
              src={nagiIcon}
              alt="Nagi AI"
              className="logo-icon-img"
            />
          </div>
        ) : (
          <div className="sidebar-banner">
            <img
              src={nagiBanner}
              alt="Nagi AI"
              className="logo-banner-img"
            />
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {navItems.map(item => {
          if (item.path === '/projects') {
            const isProjectActive = location.pathname === '/projects' || location.pathname.startsWith('/projects/');
            return (
              <div key={item.path} className="nav-group">
                <div className="nav-group-header">
                  <Link
                    to={item.path}
                    className={`nav-link ${isProjectActive ? 'active' : ''}`}
                    title={showCollapsed ? item.label : undefined}
                    onClick={handleNavClick}
                  >
                    <item.icon className="nav-icon" />
                    {!showCollapsed && <span className="nav-label">{item.label}</span>}
                    {totalUnassigned > 0 && showCollapsed && (
                      <span className="nav-badge unassigned-badge collapsed-badge" title="未割り当てタスク">
                        {totalUnassigned}
                      </span>
                    )}
                  </Link>
                  {!showCollapsed && activeProjects.length > 0 && (
                    <button
                      className={`expand-toggle ${projectsExpanded ? 'expanded' : ''}`}
                      onClick={toggleProjectsExpanded}
                      title={projectsExpanded ? '折りたたむ' : '展開する'}
                    >
                      <FaChevronDown />
                    </button>
                  )}
                </div>
                {!showCollapsed && projectsExpanded && activeProjects.length > 0 && (
                  <div className="project-sublist">
                    {projectTree.map(node => (
                      <ProjectTreeItem
                        key={node.project.id}
                        node={node}
                        depth={0}
                        expandedIds={expandedProjectIds}
                        onToggle={toggleProjectNode}
                        location={location}
                        onNavClick={handleNavClick}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          }
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-link ${location.pathname === item.path ? 'active' : ''}`}
              title={showCollapsed ? item.label : undefined}
              onClick={handleNavClick}
            >
              <item.icon className="nav-icon" />
              {!showCollapsed && <span className="nav-label">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className={`sidebar-footer ${showCollapsed ? 'collapsed' : ''}`}>
        {!showCollapsed ? (
          <div className="user-profile-row">
            <div className="user-profile">
              <div className="user-avatar">{avatarLabel}</div>
              <div className="user-info">
                <span className="user-name">{displayName}</span>
                <span className="user-status">{token ? 'Signed in' : 'Guest'}</span>
              </div>
            </div>
            <button
              className="sidebar-toggle-btn"
              onClick={onToggle}
              title="サイドバーを折りたたむ"
            >
              <FaChevronLeft />
            </button>
          </div>
        ) : (
          <button
            className="sidebar-toggle-btn"
            onClick={onToggle}
            title="サイドバーを展開"
          >
            <FaChevronRight />
          </button>
        )}
        <div className={`footer-actions ${showCollapsed ? 'collapsed' : ''}`}>
          <NotificationDropdown />
          <button
            className="footer-btn theme-toggle-btn"
            onClick={toggleTheme}
            title={theme === 'light' ? 'ダークモードに切り替え' : 'ライトモードに切り替え'}
          >
            {theme === 'light' ? <FaMoon /> : <FaSun />}
          </button>
          <button
            className="footer-btn settings-btn"
            onClick={() => setShowSettings(true)}
            title="設定"
          >
            <FaGear />
          </button>
          {token ? (
            <button
              className="footer-btn logout-btn"
              onClick={handleLogout}
              title={isAuthLocked ? '環境トークン利用中のためログアウトできません' : 'ログアウト'}
              disabled={isAuthLocked}
            >
              <FaRightFromBracket />
            </button>
          ) : (
            <button
              className="footer-btn login-btn"
              onClick={handleLogin}
              title="ログイン"
            >
              <FaRightToBracket />
            </button>
          )}
        </div>
      </div>

    </aside>
      {showSettings && (
        <SettingsModal onClose={() => setShowSettings(false)} />
      )}
    </>
  );
}
