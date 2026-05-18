import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { todayApi } from '../api/today';
import { useCapacitySettings } from './useCapacitySettings';

const TODAY_PLAN_INVALIDATION_KEYS: string[][] = [
  ['today-plan'],
  ['today-tasks'],
  ['top3'],
  ['schedule'],
  ['tasks'],
];

export function useTodayPlan() {
  const queryClient = useQueryClient();
  const { capacityHours, bufferHours, capacityByWeekday } = useCapacitySettings();

  const query = useQuery({
    queryKey: ['today-plan', capacityHours, bufferHours, capacityByWeekday],
    queryFn: () => todayApi.getPlan({
      capacityHours,
      bufferHours,
      capacityByWeekday,
    }),
    staleTime: 30_000,
  });

  const selectionMutation = useMutation({
    mutationFn: (taskIds: string[]) => todayApi.updateSelection({
      task_ids: taskIds,
      replace: true,
    }),
    onSuccess: () => {
      for (const key of TODAY_PLAN_INVALIDATION_KEYS) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  return {
    ...query,
    updateSelection: selectionMutation.mutateAsync,
    isUpdatingSelection: selectionMutation.isPending,
  };
}
