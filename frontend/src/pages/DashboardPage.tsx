import { AgentCard } from '../components/dashboard/AgentCard';
import { Top3Card } from '../components/dashboard/Top3Card';
import { WeeklyProgress } from '../components/dashboard/WeeklyProgress';
import './DashboardPage.css';

export function DashboardPage() {
  return (
    <div className="dashboard-page">
      <AgentCard />

      <div className="dashboard-grid">
        <div className="grid-main">
          <Top3Card />
        </div>

        <div className="grid-side">
          <WeeklyProgress />
        </div>
      </div>
    </div>
  );
}
