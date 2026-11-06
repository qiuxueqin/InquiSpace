import { useContext } from 'react';
import { AuthContext } from './authContext';

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('页面缺少认证上下文。');
  return context;
}
