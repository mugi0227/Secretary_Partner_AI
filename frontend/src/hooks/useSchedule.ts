/**
 * useSchedule - Fetch multi-day schedule derived from tasks
 */

import { useQuery } from '@tanstack/react-query';
import { tasksApi } from '../api/tasks';
import { useCapacitySettings } from './useCapacitySettings';

export function useSchedule(maxDays: number) {
  const { capacityHours, bufferHours } = useCapacitySettings();
  return useQuery({
    queryKey: ['schedule', maxDays, capacityHours, bufferHours],
    queryFn: () => tasksApi.getSchedule({ maxDays, capacityHours, bufferHours }),
    staleTime: 30_000,
  });
}
