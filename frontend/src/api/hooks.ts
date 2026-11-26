import { useMutation, useQuery, type UseQueryOptions } from '@tanstack/react-query';
import { api, get, post } from './client';

type Q = Record<string, string | number | boolean | undefined | null>;

/** GET with caching. The key is the path plus query, so identical calls are shared across components. */
export function useGet<T>(path: string, query?: Q, opts?: Omit<UseQueryOptions<T>, 'queryKey' | 'queryFn'>) {
  return useQuery<T>({ queryKey: [path, query ?? {}], queryFn: () => get<T>(path, query), ...opts });
}

export function usePost<T, B = unknown>(path: string) {
  return useMutation<T, Error, B>({ mutationFn: (body) => post<T>(path, body) });
}

export function useApiMutation<T, B = unknown>(fn: (body: B) => Promise<T>) {
  return useMutation<T, Error, B>({ mutationFn: fn });
}

export { api, get, post };
