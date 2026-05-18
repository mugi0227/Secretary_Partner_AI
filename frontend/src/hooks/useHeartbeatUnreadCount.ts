import { useQuery } from '@tanstack/react-query';
import { heartbeatApi } from '../api/heartbeat';

export function useHeartbeatUnreadCount() {
  const query = useQuery({
    queryKey: ['heartbeat', 'unread-count'],
    queryFn: heartbeatApi.getUnreadCount,
    refetchInterval: 30000,
  });

  return {
    count: query.data?.count ?? 0,
    unreadSessionIds: query.data?.unread_session_ids ?? [],
    isLoading: query.isLoading,
  };
}
