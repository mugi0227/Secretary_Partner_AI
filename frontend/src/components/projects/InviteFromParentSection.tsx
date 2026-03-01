import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { projectsApi } from '../../api/projects';
import type { ProjectMember, ProjectRole } from '../../api/types';
import { FaUserPlus } from 'react-icons/fa';

interface InviteFromParentSectionProps {
  projectId: string;
  parentProjectId: string;
  currentMembers: ProjectMember[];
  ownerUserId: string;
  onMemberAdded: () => void;
}

const ROLE_OPTIONS: { value: ProjectRole; label: string }[] = [
  { value: 'MEMBER', label: 'MEMBER' },
  { value: 'ADMIN', label: 'ADMIN' },
];

export function InviteFromParentSection({
  projectId,
  parentProjectId,
  currentMembers,
  ownerUserId,
  onMemberAdded,
}: InviteFromParentSectionProps) {
  const [selectedRole, setSelectedRole] = useState<ProjectRole>('MEMBER');

  const { data: parentMembers, isLoading } = useQuery({
    queryKey: ['project-members', parentProjectId],
    queryFn: () => projectsApi.listMembers(parentProjectId),
  });

  const { data: parentProject } = useQuery({
    queryKey: ['project', parentProjectId],
    queryFn: () => projectsApi.getById(parentProjectId),
  });

  const inviteMutation = useMutation({
    mutationFn: (memberUserId: string) =>
      projectsApi.inviteFromParent(projectId, {
        member_user_id: memberUserId,
        role: selectedRole,
      }),
    onSuccess: () => {
      onMemberAdded();
    },
    onError: (err: Error) => {
      alert(err.message || '招待に失敗しました');
    },
  });

  // Build list of parent members who are NOT already direct members of this child
  const currentMemberIds = new Set([
    ownerUserId,
    ...currentMembers.map((m) => m.member_user_id),
  ]);

  const availableMembers: { userId: string; displayName: string }[] = [];

  // Include the parent project owner
  if (parentProject && !currentMemberIds.has(parentProject.user_id)) {
    availableMembers.push({
      userId: parentProject.user_id,
      displayName: parentProject.owner_display_name || parentProject.user_id,
    });
  }

  // Include parent project members
  if (parentMembers) {
    for (const pm of parentMembers) {
      if (!currentMemberIds.has(pm.member_user_id)) {
        availableMembers.push({
          userId: pm.member_user_id,
          displayName: pm.member_display_name || pm.member_user_id,
        });
      }
    }
  }

  if (isLoading) {
    return (
      <div className="project-v2-subsection">
        <h4>親プロジェクトから招待</h4>
        <p className="project-v2-muted">読み込み中...</p>
      </div>
    );
  }

  return (
    <div className="project-v2-subsection">
      <h4>
        <FaUserPlus style={{ marginRight: '6px', fontSize: '0.85rem' }} />
        親プロジェクトから招待
      </h4>
      {availableMembers.length === 0 ? (
        <p className="project-v2-muted">招待可能な親プロジェクトメンバーはいません。</p>
      ) : (
        <>
          <div className="project-v2-form-row" style={{ marginBottom: '8px' }}>
            <label className="project-v2-muted" style={{ fontSize: '0.8rem' }}>
              ロール:
            </label>
            <select
              className="project-v2-select"
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value as ProjectRole)}
              style={{ width: 'auto' }}
            >
              {ROLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div className="project-v2-list">
            {availableMembers.map((am) => (
              <div key={am.userId} className="project-v2-list-item">
                <div>
                  <div className="project-v2-list-title">{am.displayName}</div>
                  <div className="project-v2-muted" style={{ fontSize: '0.75rem' }}>
                    {am.userId}
                  </div>
                </div>
                <button
                  className="project-v2-button primary"
                  onClick={() => inviteMutation.mutate(am.userId)}
                  disabled={inviteMutation.isPending}
                  style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                >
                  招待
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
