import { createContext } from 'react';
import type { AuthSession, UserRole } from '../api/auth';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'unavailable';

export interface AuthContextValue {
  status: AuthStatus;
  session: AuthSession | null;
  error: string;
  login: (username: string, password: string) => Promise<AuthSession>;
  logout: () => Promise<void>;
  retry: () => Promise<void>;
  homeForRole: (role: UserRole) => string;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function homeForRole(role: UserRole) {
  return role === 'teacher' ? '/teacher/tasks' : '/student/tasks';
}
