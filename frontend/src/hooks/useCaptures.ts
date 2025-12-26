import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Capture } from '../api/types';

export function useCaptures() {
    const queryClient = useQueryClient();

    const { data: unprocessedCaptures = [], isLoading, error } = useQuery({
        queryKey: ['captures', 'unprocessed'],
        queryFn: () => api.get<Capture[]>('/captures?processed=false'),
    });

    const deleteCapture = useMutation({
        mutationFn: (id: string) => api.delete<void>(`/captures/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['captures'] });
        },
    });

    const processCapture = useMutation({
        mutationFn: (id: string) => api.post<Capture>(`/captures/${id}/process`, {}),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['captures'] });
        },
    });

    const analyzeCapture = useMutation({
        mutationFn: (id: string) => api.post<any>(`/captures/${id}/analyze`, {}),
    });

    return {
        unprocessedCaptures,
        isLoading,
        error,
        deleteCapture: deleteCapture.mutate,
        processCapture: processCapture.mutate,
        analyzeCapture: analyzeCapture.mutateAsync, // Expose as async to await result
        isAnalyzing: analyzeCapture.isPending,
    };
}
