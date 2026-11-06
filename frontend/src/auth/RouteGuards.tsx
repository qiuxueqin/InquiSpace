import { Button, Result } from 'antd';
import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import type { UserRole } from '../api/auth';
import { AuthLoading } from './AuthLoading';
import { useAuth } from './useAuth';

function ServiceUnavailable() {
  const { error, retry } = useAuth();
  return <Result status="warning" title="暂时无法连接登录服务" subTitle={error || '请检查后端服务后重试。'} extra={<Button type="primary" onClick={() => void retry()}>重新连接</Button>} />;
}

export function RootRedirect() {
  const { status, session, homeForRole } = useAuth();
  if (status === 'loading') return <AuthLoading />;
  if (status === 'unavailable') return <ServiceUnavailable />;
  return <Navigate to={session ? homeForRole(session.user.role) : '/login'} replace />;
}

export function LoginRoute() {
  const { status, session, homeForRole } = useAuth();
  if (status === 'loading') return <AuthLoading />;
  if (status === 'authenticated' && session) return <Navigate to={homeForRole(session.user.role)} replace />;
  return <Outlet />;
}

export function AuthenticatedRoute() {
  const { status, session } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <AuthLoading />;
  if (status === 'unavailable') return <ServiceUnavailable />;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

export function RoleRoute({ role, children }: { role: UserRole; children?: ReactNode }) {
  const { session, homeForRole } = useAuth();
  if (!session) return null;
  if (session.user.role !== role) return <Navigate to={homeForRole(session.user.role)} replace />;
  return children ?? <Outlet />;
}
