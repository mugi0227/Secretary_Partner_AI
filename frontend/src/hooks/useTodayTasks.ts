/**
 * useTodayTasks - Fetch today's tasks derived from the schedule
 */

import { useQuery } from '@tanstack/react-query';
import { tasksApi } from '../api/tasks';
import { useCapacitySettings } from './useCapacitySettings';

export function useTodayTasks() {
  const { capacityHours, bufferHours } = useCapacitySettings();
  return useQuery({
    queryKey: ['today-tasks', capacityHours, bufferHours],
    queryFn: () => tasksApi.getToday({ capacityHours, bufferHours }),
    staleTime: 30_000,
  });
}
