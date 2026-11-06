import { isRecord, request } from './client';

export type UserRole = 'teacher' | 'student';

export interface AuthUser {
  id: string;
  displayName: string;
  role: UserRole;
}

export interface AuthSession {
  user: AuthUser;
  csrfToken: string;
}

function isAuthUser(value: unknown): value is AuthUser {
  return isRecord(value)
    && typeof value.id === 'string'
    && value.id.length > 0
    && typeof value.displayName === 'string'
    && value.displayName.length > 0
    && (value.role === 'teacher' || value.role === 'student');
}

function isAuthSession(value: unknown): value is AuthSession {
  return isRecord(value)
    && isAuthUser(value.user)
    && typeof value.csrfToken === 'string'
    && value.csrfToken.length > 0;
}

function isLogoutData(value: unknown): value is { loggedOut: true } {
  return isRecord(value) && value.loggedOut === true;
}

export type StudentOption = { id: string; displayName: string };
function isStudentPage(value: unknown): value is { items: StudentOption[]; nextCursor: string | null } {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(item => isRecord(item)
    && typeof item.id === 'string' && typeof item.displayName === 'string');
}

export function login(username: string, password: string, signal?: AbortSignal) {
  return request('/api/v1/auth/login', isAuthSession, {
    method: 'POST',
    body: { username, password },
    ...(signal ? { signal } : {}),
  });
}

export function getCurrentSession(signal?: AbortSignal) {
  return request('/api/v1/auth/me', isAuthSession, signal ? { signal } : {});
}

export function listStudents(signal?: AbortSignal) {
  return request('/api/v1/users?role=student&limit=100', isStudentPage, signal ? { signal } : {});
}

export function logout(csrfToken: string, signal?: AbortSignal) {
  return request('/api/v1/auth/logout', isLogoutData, {
    method: 'POST',
    body: {},
    csrfToken,
    ...(signal ? { signal } : {}),
  });
}
