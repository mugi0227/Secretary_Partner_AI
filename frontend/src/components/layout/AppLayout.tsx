import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { FaBars } from 'react-icons/fa6';
import { projectsApi } from '../../api/projects';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { useRealtimeSync } from '../../hooks/useRealtimeSync';
import { userStorage } from '../../utils/userStorage';
import { ChatWidget } from '../chat/ChatWidget';
import { ChatWindow } from '../chat/ChatWindow';
import type { DraftCardData } from '../chat/DraftCard';
import nagiIcon from '../../assets/nagi_icon.png';
import './AppLayout.css';
import { Sidebar } from './Sidebar';

const CHAT_STORAGE_KEY = 'secretary_chat_state';
const SIDEBAR_STORAGE_KEY = 'secretary_sidebar_collapsed';

interface ChatState {
  isOpen: boolean;
  width: number;
}

export function AppLayout() {
  const location = useLocation();
  const isMobile = useIsMobile();
  useRealtimeSync();
  const [mobileMenuState, setMobileMenuState] = useState({
    isOpen: false,
    pathname: location.pathname,
  });
  const isMobileMenuOpen =
    mobileMenuState.pathname === location.pathname && mobileMenuState.isOpen;
  const setMobileMenuOpen = useCallback((isOpen: boolean) => {
    setMobileMenuState({ isOpen, pathname: location.pathname });
  }, [location.pathname]);
  const loadChatState = () => userStorage.getJson<ChatState>(CHAT_STORAGE_KEY, {
    isOpen: false,
    width: 400,
  });

  const [isChatOpen, setIsChatOpen] = useState(() => loadChatState().isOpen);
  const [chatWidth, setChatWidth] = useState(() => loadChatState().width);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [pendingDraftCard, setPendingDraftCard] = useState<DraftCardData | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() =>
    userStorage.getJson<boolean>(SIDEBAR_STORAGE_KEY, false)
  );

  // Detect project page from URL
  const currentProjectId = useMemo(() => {
    const match = location.pathname.match(/\/projects\/([^/]+)/);
    return match ? match[1] : null;
  }, [location.pathname]);

  const { data: scopedProject } = useQuery({
    queryKey: ['project', currentProjectId],
    queryFn: () => projectsApi.getById(currentProjectId!),
    enabled: !!currentProjectId,
    staleTime: 60_000,
  });

  const projectContext = currentProjectId && scopedProject
    ? { projectId: currentProjectId, projectName: scopedProject.name }
    : null;

  const isResizing = useRef(false);

  // Persist state changes
  useEffect(() => {
    const state: ChatState = { isOpen: isChatOpen, width: chatWidth };
    userStorage.setJson(CHAT_STORAGE_KEY, state);
  }, [isChatOpen, chatWidth]);

  useEffect(() => {
    userStorage.setJson(SIDEBAR_STORAGE_KEY, isSidebarCollapsed);
  }, [isSidebarCollapsed]);

  const toggleSidebar = () => setIsSidebarCollapsed(!isSidebarCollapsed);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing.current) return;
    const newWidth = window.innerWidth - e.clientX;
    if (newWidth > 300 && newWidth < 800) {
      setChatWidth(newWidth);
    }
  }, []);

  const stopResizing = useCallback(() => {
    isResizing.current = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.body.style.cursor = 'default';
  }, [handleMouseMove]);

  const startResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', stopResizing, { once: true });
    document.body.style.cursor = 'col-resize';
  }, [handleMouseMove, stopResizing]);

  // Cleanup
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', stopResizing);
    };
  }, [handleMouseMove, stopResizing]);

  useEffect(() => {
    const handleAuthChange = () => {
      const state = loadChatState();
      setIsChatOpen(state.isOpen);
      setChatWidth(state.width);
    };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => {
      window.removeEventListener('auth-changed', handleAuthChange);
    };
  }, []);

  useEffect(() => {
    const handleOpenChat = (e: CustomEvent<{ message?: string; draftCard?: DraftCardData; newChat?: boolean }>) => {
      if (e.detail?.draftCard) {
        setPendingDraftCard({ ...e.detail.draftCard, newChat: e.detail.newChat });
        setPendingMessage(null);
      } else if (e.detail?.message) {
        setPendingMessage(e.detail.message);
        setPendingDraftCard(null);
      }
      setIsChatOpen(true);
    };

    window.addEventListener('secretary:chat-open', handleOpenChat as EventListener);
    return () => {
      window.removeEventListener('secretary:chat-open', handleOpenChat as EventListener);
    };
  }, []);

  const toggleChat = () => setIsChatOpen(!isChatOpen);

  return (
    <div
      className={`app-container ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
      style={isMobile ? { flexDirection: 'column' } : undefined}
    >
      {isMobile && (
        <div className="mobile-header">
          <button
            className="hamburger-btn"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="メニューを開く"
          >
            <FaBars />
          </button>
          <div className="mobile-logo">
            <img src={nagiIcon} alt="Nagi AI" />
            <span>nagi</span>
          </div>
        </div>
      )}
      <Sidebar
        collapsed={isSidebarCollapsed}
        onToggle={toggleSidebar}
        isMobile={isMobile}
        mobileOpen={isMobileMenuOpen}
        onMobileClose={() => setMobileMenuOpen(false)}
      />
      <main className="main-content">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            className="content-area"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      {isChatOpen && (
        <>
          {!isMobile && (
            <div
              className="resize-handle"
              onMouseDown={startResizing}
            />
          )}
          <aside
            className="chat-sidebar"
            style={isMobile ? {
              position: 'fixed',
              inset: 0,
              width: '100%',
              borderRadius: 0,
              zIndex: 2500,
            } : { width: `${chatWidth}px` }}
          >
            <ChatWindow
              isOpen={isChatOpen}
              onClose={() => setIsChatOpen(false)}
              initialMessage={pendingMessage}
              onInitialMessageConsumed={() => setPendingMessage(null)}
              draftCard={pendingDraftCard}
              onDraftCardConsumed={() => setPendingDraftCard(null)}
              projectContext={projectContext}
            />
          </aside>
        </>
      )}

      {!isChatOpen && <ChatWidget forceOpen={toggleChat} />}
    </div>
  );
}
