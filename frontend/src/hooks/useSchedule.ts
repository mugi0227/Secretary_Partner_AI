/**
 * useSchedule - Fetch multi-day schedule derived from tasks
 */

import { useQuery } from '@tanstack/react-query';
import { tasksApi } from '../api/tasks';
import { useCapacitySettings } from './useCapacitySettings';
import { useTimezone } from './useTimezone';

export function useSchedule(maxDays: number) {
  const timezone = useTimezone();
  const { capacityHours, bufferHours, capacityByWeekday } = useCapacitySettings();
  return useQuery({
    queryKey: ['schedule', timezone, maxDays, capacityHours, bufferHours, capacityByWeekday],
    queryFn: () => tasksApi.getSchedule({
      maxDays,
      capacityHours,
      bufferHours,
      capacityByWeekday,
      filterByAssignee: true,
    }),
    staleTime: Infinity,
  });
}
