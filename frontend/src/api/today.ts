/**
 * Today API - Top 3 tasks
 */

import { api } from './client';
import type { Task } from './types';

export const todayApi = {
  /**
   * Get today's top 3 priority tasks
   */
  getTop3: () => api.get<Task[]>('/today/top3'),
};
