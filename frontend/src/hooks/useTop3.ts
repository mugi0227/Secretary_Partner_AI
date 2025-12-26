/**
 * useTop3 - Fetch today's top 3 priority tasks
 */

import { useQuery } from '@tanstack/react-query';
import { todayApi } from '../api/today';
import { useCapacitySettings } from './useCapacitySettings';

export function useTop3() {
  const { capacityHours, bufferHours } = useCapacitySettings();
  return useQuery({
    queryKey: ['top3', capacityHours, bufferHours],
    queryFn: () => todayApi.getTop3({ capacityHours, bufferHours }),
    staleTime: 30_000, // 30 seconds
  });
}
