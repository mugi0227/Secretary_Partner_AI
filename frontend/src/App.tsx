import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from './context/ThemeContext';
import { MeetingTimerProvider } from './contexts/MeetingTimerContext';
import { AppLayout } from './components/layout/AppLayout';
import { FloatingMeetingTimer } from './components/meetings/FloatingMeetingTimer';
import { GlobalMeetingModal } from './components/meetings/GlobalMeetingModal';
import { DashboardPage } from './pages/DashboardPage';
import { TasksPage } from './pages/TasksPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectDetailV2Page } from './pages/ProjectDetailV2Page';
import { AchievementPage } from './pages/AchievementPage';
import { MemoriesPage } from './pages/MemoriesPage';
import { IssuesPage } from './pages/IssuesPage';
import { LoginPage } from './pages/LoginPage';
import { RequireAuth } from './components/auth/RequireAuth';
import { InvitationAcceptPage } from './pages/InvitationAcceptPage';
import { OidcCallbackPage } from './pages/OidcCallbackPage';
import { NativeLinkPage } from './pages/NativeLinkPage';
import { SharedAchievementPage } from './pages/SharedAchievementPage';

function ProjectDetailRedirect() {
  const { projectId } = useParams();
  return <Navigate to={`/projects/${projectId}/v2`} replace />;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30 seconds
      retry: 1,
    },
  },
});

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<OidcCallbackPage />} />
      <Route path="/invite/accept" element={<InvitationAcceptPage />} />
      <Route path="/shared/achievements/:token" element={<SharedAchievementPage />} />
      <Route
        path="/"
        element={(
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        )}
      >
        <Route index element={<DashboardPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailRedirect />} />
        <Route path="projects/:projectId/v2" element={<ProjectDetailV2Page />} />
        <Route path="achievement" element={<AchievementPage />} />
        <Route path="memories" element={<MemoriesPage />} />
        {import.meta.env.VITE_ENABLE_ISSUES === 'true' && (
          <Route path="issues" element={<IssuesPage />} />
        )}
        <Route path="native-link" element={<NativeLinkPage />} />
      </Route>
    </Routes>
  );
}

function App() {
  // ログアウト時にReact Queryのキャッシュをクリア
  useEffect(() => {
    const handleAuthChanged = () => {
      queryClient.clear();
    };
    window.addEventListener('auth-changed', handleAuthChanged);
    return () => window.removeEventListener('auth-changed', handleAuthChanged);
  }, []);

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MeetingTimerProvider>
          <BrowserRouter>
            <AppRoutes />
            <FloatingMeetingTimer />
            <GlobalMeetingModal />
          </BrowserRouter>
        </MeetingTimerProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
