import { useCallback, useEffect, useState } from 'react';
import { OpsApiError } from '../api/client';

export interface UseOpsFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: { message: string; status?: number } | null;
  reload: () => Promise<void>;
}

export function useOpsFetch<T>(fetcher: () => Promise<T>): UseOpsFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<{ message: string; status?: number } | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetcher();
      setData(res);
    } catch (err) {
      if (err instanceof OpsApiError) {
        setError({ message: err.message, status: err.status });
      } else if (err instanceof Error) {
        setError({ message: err.message });
      } else {
        setError({ message: 'Unknown API error occurred.' });
      }
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    data,
    loading,
    error,
    reload,
  };
}
