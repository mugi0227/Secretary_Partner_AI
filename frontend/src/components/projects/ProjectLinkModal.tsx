import { useState, useMemo } from 'react';
import { FaXmark } from 'react-icons/fa6';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../../api/projects';
import type { ProjectMember, ProjectLinkRequestCreate } from '../../api/types';
import './ProjectDetailModal.css';

interface ProjectLinkModalProps {
  isOpen: boolean;
  onClose: () => void;
  childProjectId: string;
  childProjectName: string;
}

export function ProjectLinkModal({
  isOpen,
  onClose,
  childProjectId,
  childProjectName,
}: ProjectLinkModalProps) {
  const queryClient = useQueryClient();
  const [selectedParentId, setSelectedParentId] = useState('');
  const [selectedMemberIds, setSelectedMemberIds] = useState<string[]>([]);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // Fetch all projects
  const { data: allProjects = [], isLoading: isLoadingProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.getAll(),
    enabled: isOpen,
  });

  // Fetch descendants of the child project (to exclude from parent options)
  const { data: descendants = [] } = useQuery({
    queryKey: ['projects', childProjectId, 'descendants'],
    queryFn: () => projectsApi.getDescendants(childProjectId),
    enabled: isOpen && !!childProjectId,
  });

  // Fetch members of the child project
  const { data: childMembers = [], isLoading: isLoadingMembers } = useQuery({
    queryKey: ['projects', childProjectId, 'members'],
    queryFn: () => projectsApi.listMembers(childProjectId),
    enabled: isOpen && !!childProjectId,
  });

  // Filter out the child project and its descendants from selectable parents
  const availableParents = useMemo(() => {
    const descendantIds = new Set(descendants.map((d) => d.id));
    return allProjects.filter(
      (p) => p.id !== childProjectId && !descendantIds.has(p.id)
    );
  }, [allProjects, descendants, childProjectId]);

  // Submit link request mutation
  const linkMutation = useMutation({
    mutationFn: (data: ProjectLinkRequestCreate) =>
      projectsApi.createLinkRequest(selectedParentId, data),
    onSuccess: () => {
      setSuccessMessage('紐付けリクエストを送信しました');
      setErrorMessage('');
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setTimeout(() => {
        onClose();
        setSuccessMessage('');
        setSelectedParentId('');
        setSelectedMemberIds([]);
      }, 1500);
    },
    onError: (error: Error) => {
      setErrorMessage(error.message || '紐付けリクエストの送信に失敗しました');
      setSuccessMessage('');
    },
  });

  const handleToggleMember = (memberUserId: string) => {
    setSelectedMemberIds((prev) =>
      prev.includes(memberUserId)
        ? prev.filter((id) => id !== memberUserId)
        : [...prev, memberUserId]
    );
  };

  const handleSubmit = () => {
    if (!selectedParentId) {
      setErrorMessage('親プロジェクトを選択してください');
      return;
    }

    setErrorMessage('');
    linkMutation.mutate({
      child_project_id: childProjectId,
      parent_project_id: selectedParentId,
      member_ids_to_add: selectedMemberIds,
    });
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-content project-create-modal" style={{ maxWidth: '600px' }}>
        <div className="modal-header">
          <h2>プロジェクトの紐付け</h2>
          <button className="close-button" onClick={onClose}>
            <FaXmark />
          </button>
        </div>

        <div className="modal-body">
          {/* Child project info */}
          <div className="section">
            <label className="field-label">子プロジェクト</label>
            <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-main)' }}>
              {childProjectName}
            </p>
          </div>

          {/* Parent project selector */}
          <div className="section">
            <label className="field-label">親プロジェクト *</label>
            {isLoadingProjects ? (
              <p className="empty-text">読み込み中...</p>
            ) : (
              <select
                className="text-input"
                value={selectedParentId}
                onChange={(e) => setSelectedParentId(e.target.value)}
              >
                <option value="">親プロジェクトを選択</option>
                {availableParents.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Member checkboxes */}
          <div className="section">
            <label className="field-label">親プロジェクトに追加するメンバー</label>
            {isLoadingMembers ? (
              <p className="empty-text">読み込み中...</p>
            ) : childMembers.length === 0 ? (
              <p className="empty-text">メンバーがいません</p>
            ) : (
              <div className="members-list">
                {childMembers.map((member: ProjectMember) => (
                  <label
                    key={member.id}
                    className="member-chip"
                    style={{ cursor: 'pointer' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <input
                        type="checkbox"
                        checked={selectedMemberIds.includes(member.member_user_id)}
                        onChange={() => handleToggleMember(member.member_user_id)}
                        style={{ width: '18px', height: '18px', accentColor: 'var(--primary)' }}
                      />
                      <div className="member-info">
                        <span className="member-name">
                          {member.member_display_name || member.member_user_id}
                        </span>
                        {member.member_display_name && (
                          <span className="member-id">{member.member_user_id}</span>
                        )}
                      </div>
                    </div>
                    <span
                      className="member-role-select"
                      style={{ pointerEvents: 'none' }}
                    >
                      {member.role}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Success/Error messages */}
          {successMessage && (
            <div
              style={{
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: '#059669',
                fontWeight: 600,
                fontSize: '0.9rem',
              }}
            >
              {successMessage}
            </div>
          )}
          {errorMessage && (
            <div
              style={{
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#dc2626',
                fontWeight: 600,
                fontSize: '0.9rem',
              }}
            >
              {errorMessage}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="button button-secondary" onClick={onClose}>
            キャンセル
          </button>
          <button
            className="button button-primary"
            onClick={handleSubmit}
            disabled={linkMutation.isPending || !selectedParentId || !!successMessage}
          >
            {linkMutation.isPending ? '送信中...' : '紐付けリクエストを送信'}
          </button>
        </div>
      </div>
    </div>
  );
}
