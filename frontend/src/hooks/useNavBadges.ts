import { useQuery } from '@tanstack/react-query';
import { get } from '@/api/client';
import { useWorkspace } from '@/features/start/useWorkspace';

interface Summary {
  nav_badges: Record<string, number>;
}

/** Sidebar count badges. Fails soft: the shell still renders when the API is down. */
export function useNavBadges(): Record<string, number> {
  // counts about an estate the person has not asked for yet would only confuse
  const ready = useWorkspace().data?.status === 'ready';
  const { data } = useQuery({
    queryKey: ['overview', 'summary'],
    queryFn: () => get<Summary>('/overview/summary'),
    staleTime: 30_000,
    retry: false,
    enabled: ready,
  });
  return ready ? (data?.nav_badges ?? {}) : {};
}
