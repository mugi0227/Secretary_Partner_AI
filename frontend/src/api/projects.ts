import { api } from './client';
import type {
  Project,
  ProjectWithTaskCount,
  ProjectCreate,
  ProjectUpdate,
  ProjectKpiTemplate,
} from './types';

export const projectsApi = {
  getAll: () => api.get<ProjectWithTaskCount[]>('/projects'),

  getById: (id: string) => api.get<ProjectWithTaskCount>(`/projects/${id}`),

  create: (data: ProjectCreate) => api.post<Project>('/projects', data),

  update: (id: string, data: ProjectUpdate) =>
    api.patch<Project>(`/projects/${id}`, data),

  getKpiTemplates: () => api.get<ProjectKpiTemplate[]>('/projects/kpi-templates'),

  delete: (id: string) => api.delete<void>(`/projects/${id}`),
};

// Convenience export
export const getProject = (id: string) => projectsApi.getById(id);
