import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiClientError } from '../api/client';
import { getCurrentSession, login as loginRequest, logout as logoutRequest } from '../api/auth';
import type { AuthSession } from '../api/auth';
import { AuthContext, homeForRole } from './authContext';
import type { AuthStatus } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [error, setError] = useState('');
  const activeRequest = useRef<AbortController | null>(null);

  const restore = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setStatus('loading');
    setError('');
    try {
      const response = await getCurrentSession(controller.signal);
      setSession(response.data);
      setStatus('authenticated');
    } catch (caught) {
      if (controller.signal.aborted) return;
      setSession(null);
      if (caught instanceof ApiClientError && caught.kind === 'http' && caught.status === 401) {
        setStatus('anonymous');
        return;
      }
      setStatus('unavailable');
      setError(caught instanceof Error ? caught.message : '暂时无法确认登录状态，请稍后重试。');
    }
  }, []);

  useEffect(() => {
    void restore();
    return () => activeRequest.current?.abort();
  }, [restore]);

  const logIn = useCallback(async (username: string, password: string) => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const response = await loginRequest(username, password, controller.signal);
    setSession(response.data);
    setStatus('authenticated');
    setError('');
    return response.data;
  }, []);

  const logOut = useCallback(async () => {
    const current = session;
    if (!current) {
      setSession(null);
      setStatus('anonymous');
      return;
    }
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    await logoutRequest(current.csrfToken, controller.signal);
    setSession(null);
    setStatus('anonymous');
    setError('');
  }, [session]);

  const value = useMemo(() => ({
    status,
    session,
    error,
    login: logIn,
    logout: logOut,
    retry: restore,
    homeForRole,
  }), [error, logIn, logOut, restore, session, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
