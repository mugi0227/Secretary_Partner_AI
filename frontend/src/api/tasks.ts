import { api } from './client';
import type { Task, TaskCreate, TaskUpdate } from './types';

export const tasksApi = {
  getAll: () => api.get<Task[]>('/tasks?include_done=true'),

  getById: (id: string) => api.get<Task>(`/tasks/${id}`),

  getSubtasks: (id: string) => api.get<Task[]>(`/tasks/${id}/subtasks`),

  create: (data: TaskCreate) => api.post<Task>('/tasks', data),

  update: (id: string, data: TaskUpdate) =>
    api.patch<Task>(`/tasks/${id}`, data),

  delete: (id: string) => api.delete<void>(`/tasks/${id}`),
};
