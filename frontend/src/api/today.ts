/**
 * Today API - daily plan and Top 3 tasks
 */

import { api } from './client';
import type { TodayPlanResponse, TodaySelectionUpdate, Top3Response } from './types';

export const todayApi = {
  /**
   * Get today's selected tasks plus recommendations.
   */
  getPlan: (query?: {
    capacityHours?: number;
    bufferHours?: number;
    capacityByWeekday?: number[];
    recommendationLimit?: number;
  }) => {
    const params = new URLSearchParams();
    if (query?.capacityHours !== undefined) {
      params.set('capacity_hours', String(query.capacityHours));
    }
    if (query?.bufferHours !== undefined) {
      params.set('buffer_hours', String(query.bufferHours));
    }
    if (query?.capacityByWeekday && query.capacityByWeekday.length === 7) {
      params.set('capacity_by_weekday', JSON.stringify(query.capacityByWeekday));
    }
    if (query?.recommendationLimit !== undefined) {
      params.set('recommendation_limit', String(query.recommendationLimit));
    }
    const suffix = params.toString();
    return api.get<TodayPlanResponse>(`/today/plan${suffix ? `?${suffix}` : ''}`);
  },

  /**
   * Persist the tasks the user selected for today.
   */
  updateSelection: (
    data: TodaySelectionUpdate,
    query?: { recommendationLimit?: number },
  ) => {
    const params = new URLSearchParams();
    if (query?.recommendationLimit !== undefined) {
      params.set('recommendation_limit', String(query.recommendationLimit));
    }
    const suffix = params.toString();
    return api.put<TodayPlanResponse>(`/today/selection${suffix ? `?${suffix}` : ''}`, data);
  },

  /**
   * Get today's top 3 priority tasks with capacity info
   */
  getTop3: (query?: {
    capacityHours?: number;
    bufferHours?: number;
    capacityByWeekday?: number[];
  }) => {
    const params = new URLSearchParams();
    if (query?.capacityHours !== undefined) {
      params.set('capacity_hours', String(query.capacityHours));
    }
    if (query?.bufferHours !== undefined) {
      params.set('buffer_hours', String(query.bufferHours));
    }
    if (query?.capacityByWeekday && query.capacityByWeekday.length === 7) {
      params.set('capacity_by_weekday', JSON.stringify(query.capacityByWeekday));
    }
    const suffix = params.toString();
    return api.get<Top3Response>(`/today/top3${suffix ? `?${suffix}` : ''}`);
  },
};
