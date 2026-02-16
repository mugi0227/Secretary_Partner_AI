import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTasks } from '../../hooks/useTasks';
import { useProjects } from '../../hooks/useProjects';
import { useTimezone } from '../../hooks/useTimezone';
import { toDateTime, todayInTimezone } from '../../utils/dateTime';
import type { ProjectWithTaskCount } from '../../api/types';
import './OverdueCheckinCard.css';

type OverdueProjectInfo = {
  project: ProjectWithTaskCount;
  overdueCount: number;
  maxOverdueDays: number;
};

export function OverdueCheckinCard() {
  const timezone = useTimezone();
  const navigate = useNavigate();
  const { tasks } = useTasks();
  const { projects } = useProjects();

  const todayStr = useMemo(() => {
    return todayInTimezone(timezone).toISODate() ?? '';
  }, [timezone]);

  const teamProjectMap = useMemo(() => {
    const map = new Map<string, ProjectWithTaskCount>();
    projects.forEach(p => {
      if (p.visibility === 'TEAM' && p.status === 'ACTIVE') {
        map.set(p.id, p);
      }
    });
    return map;
  }, [projects]);

  const overdueProjects: OverdueProjectInfo[] = useMemo(() => {
    if (!todayStr) return [];

    const grouped = new Map<string, { count: number; maxDays: number }>();

    tasks.forEach(task => {
      if (task.status === 'DONE') return;
      if (!task.project_id || !task.due_date) return;
      if (!teamProjectMap.has(task.project_id)) return;
      if (task.is_fixed_time) return;

      if (task.due_date < todayStr) {
        const due = toDateTime(task.due_date, timezone).startOf('day');
        const today = todayInTimezone(timezone).startOf('day');
        const overdueDays = Math.floor(today.diff(due, 'days').days);
        if (overdueDays <= 0) return;

        const existing = grouped.get(task.project_id) ?? { count: 0, maxDays: 0 };
        existing.count++;
        existing.maxDays = Math.max(existing.maxDays, overdueDays);
        grouped.set(task.project_id, existing);
      }
    });

    const result: OverdueProjectInfo[] = [];
    grouped.forEach(({ count, maxDays }, projectId) => {
      const project = teamProjectMap.get(projectId);
      if (!project) return;
      result.push({ project, overdueCount: count, maxOverdueDays: maxDays });
    });

    result.sort((a, b) => b.maxOverdueDays - a.maxOverdueDays);
    return result;
  }, [tasks, todayStr, teamProjectMap, timezone]);

  if (overdueProjects.length === 0) return null;

  const handleNavigate = (projectId: string) => {
    navigate(`/projects/${projectId}/v2?tab=meetings&checkin=true`);
  };

  return (
    <div className="overdue-checkin-alerts">
      {overdueProjects.map(({ project, overdueCount, maxOverdueDays }) => (
        <button
          key={project.id}
          type="button"
          className={`overdue-checkin-alert ${maxOverdueDays >= 7 ? 'serious' : 'mild'}`}
          onClick={() => handleNavigate(project.id)}
        >
          <span className="overdue-alert-icon">
            {maxOverdueDays >= 7 ? '!!' : '!'}
          </span>
          <span className="overdue-alert-text">
            <strong>{project.name}</strong>
            {' '}
            {overdueCount}件のタスクが期限超過（最大{maxOverdueDays}日）
          </span>
          <span className="overdue-alert-action">
            Check-in →
          </span>
        </button>
      ))}
    </div>
  );
}
