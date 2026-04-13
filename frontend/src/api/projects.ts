import { api, ApiError } from './client';
import type {
  Project,
  ProjectWithTaskCount,
  ProjectCreate,
  ProjectUpdate,
  ProjectMember,
  ProjectMemberCreate,
  ProjectMemberUpdate,
  ProjectInvitation,
  ProjectInvitationCreate,
  ProjectInvitationUpdate,
  ProjectLinkRequest,
  ProjectLinkRequestCreate,
  ProjectRole,
  TaskAssignment,
  Blocker,
  Checkin,
  CheckinCreate,
  CheckinSummary,
  CheckinType,
  CheckinSummarySave,
  CheckinV2,
  CheckinCreateV2,
  CheckinUpdateV2,
  CheckinAgendaItems,
  ProjectKpiTemplate,
  Memory,
  ChildProjectTaskSummary,
  MemberChildTasksSummary,
  TaskUpdate,
} from './types';

export const projectsApi = {
  getAll: (topLevelOnly = false) =>
    api.get<ProjectWithTaskCount[]>(`/projects?top_level_only=${topLevelOnly}`),

  getById: (id: string) => api.get<ProjectWithTaskCount>(`/projects/${id}`),

  create: (data: ProjectCreate) => api.post<Project>('/projects', data),

  update: (id: string, data: ProjectUpdate) =>
    api.patch<Project>(`/projects/${id}`, data),

  getKpiTemplates: () => api.get<ProjectKpiTemplate[]>('/projects/kpi-templates'),

  delete: (id: string) => api.delete<void>(`/projects/${id}`),

  // Child / Descendant projects
  getChildren: (projectId: string) =>
    api.get<ProjectWithTaskCount[]>(`/projects/${projectId}/children`),

  getDescendants: (projectId: string) =>
    api.get<ProjectWithTaskCount[]>(`/projects/${projectId}/descendants`),

  getChildProjectTasks: (parentProjectId: string, childProjectId: string) =>
    api.get<ChildProjectTaskSummary[]>(
      `/projects/${parentProjectId}/children/${childProjectId}/tasks`,
    ),

  getMemberChildTasks: (projectId: string) =>
    api.get<MemberChildTasksSummary[]>(`/projects/${projectId}/member-child-tasks`),

  updateMemberChildTask: (projectId: string, taskId: string, data: TaskUpdate) =>
    api.patch(`/projects/${projectId}/member-child-tasks/${taskId}`, data),

  inviteFromParent: (projectId: string, data: { member_user_id: string; role: ProjectRole }) =>
    api.post<ProjectMember>(`/projects/${projectId}/invite-from-parent`, data),

  // Link requests
  createLinkRequest: (projectId: string, data: ProjectLinkRequestCreate) =>
    api.post<ProjectLinkRequest>(`/projects/${projectId}/link-requests`, data),

  listLinkRequests: (projectId: string, status?: string) => {
    const params = status ? `?status=${status}` : '';
    return api.get<ProjectLinkRequest[]>(`/projects/${projectId}/link-requests${params}`);
  },

  approveLinkRequest: (projectId: string, requestId: string) =>
    api.post<ProjectLinkRequest>(`/projects/${projectId}/link-requests/${requestId}/approve`, {}),

  rejectLinkRequest: (projectId: string, requestId: string) =>
    api.post<ProjectLinkRequest>(`/projects/${projectId}/link-requests/${requestId}/reject`, {}),

  listIncomingLinkRequests: (projectId: string, status?: string) => {
    const params = status ? `?status=${status}` : '';
    return api.get<ProjectLinkRequest[]>(`/projects/${projectId}/incoming-link-requests${params}`);
  },

  listMembers: (projectId: string) =>
    api.get<ProjectMember[]>(`/projects/${projectId}/members`),

  addMember: (projectId: string, data: ProjectMemberCreate) =>
    api.post<ProjectMember>(`/projects/${projectId}/members`, data),

  updateMember: (projectId: string, memberId: string, data: ProjectMemberUpdate) =>
    api.patch<ProjectMember>(`/projects/${projectId}/members/${memberId}`, data),

  removeMember: (projectId: string, memberId: string) =>
    api.delete<void>(`/projects/${projectId}/members/${memberId}`),

  listInvitations: async (projectId: string) => {
    try {
      return await api.get<ProjectInvitation[]>(`/projects/${projectId}/invitations`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        return [];
      }
      throw error;
    }
  },

  createInvitation: (projectId: string, data: ProjectInvitationCreate) =>
    api.post<ProjectInvitation>(`/projects/${projectId}/invitations`, data),

  updateInvitation: (projectId: string, invitationId: string, data: ProjectInvitationUpdate) =>
    api.patch<ProjectInvitation>(`/projects/${projectId}/invitations/${invitationId}`, data),

  acceptInvitation: (token: string) =>
    api.post<ProjectInvitation>(`/projects/invitations/${token}/accept`, {}),

  listAssignments: (projectId: string) =>
    api.get<TaskAssignment[]>(`/projects/${projectId}/assignments`),

  listBlockers: (projectId: string) =>
    api.get<Blocker[]>(`/projects/${projectId}/blockers`),

  listCheckins: (projectId: string, query?: {
    memberUserId?: string;
    startDate?: string;
    endDate?: string;
  }) => {
    const params = new URLSearchParams();
    if (query?.memberUserId) {
      params.set('member_user_id', query.memberUserId);
    }
    if (query?.startDate) {
      params.set('start_date', query.startDate);
    }
    if (query?.endDate) {
      params.set('end_date', query.endDate);
    }
    const suffix = params.toString();
    return api.get<Checkin[]>(`/projects/${projectId}/checkins${suffix ? `?${suffix}` : ''}`);
  },

  createCheckin: (projectId: string, data: CheckinCreate) =>
    api.post<Checkin>(`/projects/${projectId}/checkins`, data),

  summarizeCheckins: (projectId: string, payload?: {
    memberUserId?: string;
    startDate?: string;
    endDate?: string;
    checkinType?: CheckinType;
    weeklyContext?: string;
  }) => api.post<CheckinSummary>(`/projects/${projectId}/checkins/summary`, {
    member_user_id: payload?.memberUserId,
    start_date: payload?.startDate,
    end_date: payload?.endDate,
    checkin_type: payload?.checkinType,
    weekly_context: payload?.weeklyContext,
  }),

  saveCheckinSummary: (projectId: string, data: CheckinSummarySave) =>
    api.post<Memory>(`/projects/${projectId}/checkins/summary/save`, data),

  // V2 Check-in API (Structured)
  listCheckinsV2: (projectId: string, query?: {
    memberUserId?: string;
    startDate?: string;
    endDate?: string;
  }) => {
    const params = new URLSearchParams();
    if (query?.memberUserId) {
      params.set('member_user_id', query.memberUserId);
    }
    if (query?.startDate) {
      params.set('start_date', query.startDate);
    }
    if (query?.endDate) {
      params.set('end_date', query.endDate);
    }
    const suffix = params.toString();
    return api.get<CheckinV2[]>(`/projects/${projectId}/checkins/v2${suffix ? `?${suffix}` : ''}`);
  },

  createCheckinV2: (projectId: string, data: CheckinCreateV2) =>
    api.post<CheckinV2>(`/projects/${projectId}/checkins/v2`, data),

  updateCheckinV2: (projectId: string, checkinId: string, data: CheckinUpdateV2) =>
    api.patch<CheckinV2>(`/projects/${projectId}/checkins/v2/${checkinId}`, data),

  deleteCheckinV2: (projectId: string, checkinId: string) =>
    api.delete<void>(`/projects/${projectId}/checkins/v2/${checkinId}`),

  getCheckinAgendaItems: (projectId: string, query?: {
    startDate?: string;
    endDate?: string;
  }) => {
    const params = new URLSearchParams();
    if (query?.startDate) {
      params.set('start_date', query.startDate);
    }
    if (query?.endDate) {
      params.set('end_date', query.endDate);
    }
    const suffix = params.toString();
    return api.get<CheckinAgendaItems>(`/projects/${projectId}/checkins/agenda-items${suffix ? `?${suffix}` : ''}`);
  },
};

// Convenience export
export const getProject = (id: string) => projectsApi.getById(id);
