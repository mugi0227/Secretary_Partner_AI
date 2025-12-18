import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ChatWidget } from '../chat/ChatWidget';
import './AppLayout.css';

export function AppLayout() {
  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="content-area">
          <Outlet />
        </div>
      </main>
      <ChatWidget />
    </div>
  );
}
