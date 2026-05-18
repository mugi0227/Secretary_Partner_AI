import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { tasksApi } from '../api/tasks';
import type { Task, TaskCreate, TaskUpdate } from '../api/types';

/** Invalidation keys shared across all task mutations. */
const TASK_INVALIDATION_KEYS: string[][] = [
  ['tasks'],
  ['subtasks'],
  ['top3'],
  ['today-tasks'],
  ['today-plan'],
  ['schedule'],
  ['task-detail'],
  ['task-assignments'],
  ['project'],
  ['member-child-tasks'],
];

export function useTasks(projectId?: string) {
  const queryClient = useQueryClient();

  const invalidateAll = () => {
    for (const key of TASK_INVALIDATION_KEYS) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const query = useQuery({
    queryKey: projectId ? ['tasks', 'project', projectId] : ['tasks'],
    queryFn: async () => {
      const tasks = await tasksApi.getAll({ projectId });
      return tasks;
    },
  });

  const createMutation = useMutation({
    mutationFn: tasksApi.create,
    onSuccess: invalidateAll,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) =>
      tasksApi.update(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['tasks'] });
      await queryClient.cancelQueries({ queryKey: ['today-tasks'] });
      await queryClient.cancelQueries({ queryKey: ['today-plan'] });
      await queryClient.cancelQueries({ queryKey: ['subtasks'] });

      const previousTasks = queryClient.getQueryData<Task[]>(['tasks']);
      const previousSubtasks = queryClient.getQueryData<Task[]>(['subtasks']);

      queryClient.setQueryData<Task[]>(['tasks'], (old) => {
        if (!old) return old;
        return old.map((task) => (task.id === id ? { ...task, ...data } : task));
      });

      queryClient.setQueryData<Task[]>(['subtasks'], (old) => {
        if (!old) return old;
        return old.map((task) => (task.id === id ? { ...task, ...data } : task));
      });

      return { previousTasks, previousSubtasks };
    },
    onError: (_err, _newTodo, context) => {
      if (context?.previousTasks) {
        queryClient.setQueryData(['tasks'], context.previousTasks);
      }
      if (context?.previousSubtasks) {
        queryClient.setQueryData(['subtasks'], context.previousSubtasks);
      }
    },
    onSuccess: invalidateAll,
  });

  const deleteMutation = useMutation({
    mutationFn: tasksApi.delete,
    onSuccess: invalidateAll,
    onError: (error: Error) => {
      console.error('Failed to delete task:', error);
      alert('タスクの削除に失敗しました。');
    },
  });

  return {
    tasks: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
    createTask: (data: TaskCreate) => createMutation.mutate(data),
    updateTask: (id: string, data: TaskUpdate) =>
      updateMutation.mutate({ id, data }),
    deleteTask: (id: string) => deleteMutation.mutate(id),
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
}
