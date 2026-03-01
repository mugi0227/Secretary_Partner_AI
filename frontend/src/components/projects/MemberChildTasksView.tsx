import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '../../api/projects';
import type { MemberProjectTask } from '../../api/types';
import { FaSpinner, FaCircle, FaUser } from 'react-icons/fa6';
import './MemberChildTasksView.css';

const TASK_STATUS_COLORS: Record<string, string> = {
  TODO: '#94a3b8',
  IN_PROGRESS: '#0ea5e9',
  WAITING: '#f59e0b',
  DONE: '#22c55e',
};

interface MemberChildTasksViewProps {
  projectId: string;
}

export function MemberChildTasksView({ projectId }: MemberChildTasksViewProps) {
  const { data: memberTasks, isLoading } = useQuery({
    queryKey: ['member-child-tasks', projectId],
    queryFn: () => projectsApi.getMemberChildTasks(projectId),
  });

  const memberGroups = useMemo(() => {
    if (!memberTasks) return [];
    return memberTasks.map((member) => {
      const byProject = member.tasks_by_project.reduce(
        (acc, task) => {
          const key = task.child_project_name;
          if (!acc[key]) acc[key] = [];
          acc[key].push(task);
          return acc;
        },
        {} as Record<string, MemberProjectTask[]>,
      );
      return { ...member, byProject };
    });
  }, [memberTasks]);

  if (isLoading) {
    return (
      <div className="member-tasks-loading">
        <FaSpinner className="spinner" /> 読み込み中...
      </div>
    );
  }

  if (!memberGroups.length) {
    return (
      <div className="member-tasks-empty">
        子プロジェクトにタスクが割り当てられているメンバーはいません
      </div>
    );
  }

  return (
    <div className="member-child-tasks-view">
      {memberGroups.map((member) => (
        <div key={member.member_user_id} className="member-task-group">
          <div className="member-task-group-header">
            <FaUser style={{ fontSize: '0.7rem' }} />
            <span className="member-task-group-name">
              {member.member_display_name}
            </span>
            <span className="member-task-group-count">
              {member.tasks_by_project.length} タスク
            </span>
          </div>
          <div className="member-task-group-body">
            {Object.entries(member.byProject).map(([projectName, tasks]) => (
              <div key={projectName} className="member-project-section">
                <div className="member-project-label">{projectName}</div>
                {tasks.map((task) => (
                  <div key={task.task_id} className="member-task-row">
                    <FaCircle
                      className="member-task-status-dot"
                      style={{
                        color: TASK_STATUS_COLORS[task.task_status] || '#94a3b8',
                      }}
                    />
                    <span className="member-task-title">{task.task_title}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
