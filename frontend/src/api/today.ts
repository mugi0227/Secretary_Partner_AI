/**
 * Today API - Top 3 tasks
 */

import { api } from './client';
import type { Top3Response } from './types';

export const todayApi = {
  /**
   * Get today's top 3 priority tasks with capacity info
   */
  getTop3: (query?: {
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
    return api.get<Top3Response>(`/today/top3${suffix ? `?${suffix}` : ''}`);
  },
};
