import type { ReactNode } from 'react';

export function AuthLoading({ children }: { children?: ReactNode }) {
  return <div className="auth-loading" role="status"><span className="loading-dots">•••</span><span>{children ?? '正在确认登录状态'}</span></div>;
}
