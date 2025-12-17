/**
 * useTop3 - Fetch today's top 3 priority tasks
 */

import { useQuery } from '@tanstack/react-query';
import { todayApi } from '../api/today';

export function useTop3() {
  return useQuery({
    queryKey: ['top3'],
    queryFn: todayApi.getTop3,
    staleTime: 30_000, // 30 seconds
  });
}
