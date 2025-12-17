import { api } from './client';
import type {
  Project,
  ProjectWithTaskCount,
  ProjectCreate,
  ProjectUpdate,
} from './types';

export const projectsApi = {
  getAll: () => api.get<ProjectWithTaskCount[]>('/projects'),

  getById: (id: string) => api.get<Project>(`/projects/${id}`),

  create: (data: ProjectCreate) => api.post<Project>('/projects', data),

  update: (id: string, data: ProjectUpdate) =>
    api.patch<Project>(`/projects/${id}`, data),

  delete: (id: string) => api.delete<void>(`/projects/${id}`),
};
