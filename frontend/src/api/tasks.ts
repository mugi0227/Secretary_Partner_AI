import { api } from './client';
import type {
  Task,
  TaskCreate,
  TaskUpdate,
  TodayTasksResponse,
  ScheduleResponse
} from './types';

export const tasksApi = {
  getAll: (query?: {
    includeDone?: boolean;
    limit?: number;
    offset?: number;
    projectId?: string;
    status?: string;
  }) => {
    const params = new URLSearchParams();
    const includeDone = query?.includeDone ?? true;
    params.set('include_done', String(includeDone));
    params.set('limit', String(query?.limit ?? 1000));
    if (query?.offset !== undefined) {
      params.set('offset', String(query.offset));
    }
    if (query?.projectId) {
      params.set('project_id', query.projectId);
    }
    if (query?.status) {
      params.set('status', query.status);
    }
    return api.get<Task[]>(`/tasks?${params.toString()}`);
  },

  getById: (id: string) => api.get<Task>(`/tasks/${id}`),

  getSubtasks: (id: string) => api.get<Task[]>(`/tasks/${id}/subtasks`),

  create: (data: TaskCreate) => api.post<Task>('/tasks', data),

  update: (id: string, data: TaskUpdate) =>
    api.patch<Task>(`/tasks/${id}`, data),

  delete: (id: string) => api.delete<void>(`/tasks/${id}`),

  getToday: (query?: {
    capacityHours?: number;
    bufferHours?: number;
  }) => {
    const params = new URLSearchParams();
    if (query?.capacityHours !== undefined) {
      params.set('capacity_hours', String(query.capacityHours));
    }
    if (query?.bufferHours !== undefined) {
      params.set('buffer_hours', String(query.bufferHours));
    }
    const suffix = params.toString();
    return api.get<TodayTasksResponse>(`/tasks/today${suffix ? `?${suffix}` : ''}`);
  },

  getSchedule: (query?: {
    startDate?: string;
    capacityHours?: number;
    bufferHours?: number;
    maxDays?: number;
  }) => {
    const params = new URLSearchParams();
    if (query?.startDate) {
      params.set('start_date', query.startDate);
    }
    if (query?.capacityHours !== undefined) {
      params.set('capacity_hours', String(query.capacityHours));
    }
    if (query?.bufferHours !== undefined) {
      params.set('buffer_hours', String(query.bufferHours));
    }
    if (query?.maxDays !== undefined) {
      params.set('max_days', String(query.maxDays));
    }
    const suffix = params.toString();
    return api.get<ScheduleResponse>(`/tasks/schedule${suffix ? `?${suffix}` : ''}`);
  },
};
