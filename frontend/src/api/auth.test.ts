import { afterEach, describe, expect, it, vi } from 'vitest';
import { getCurrentSession, login, logout } from './auth';
import { homeForRole } from '../auth/authContext';

function mockResponse(body: unknown, status = 200) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

const session = {
  data: { user: { id: 'user-1', displayName: '教师', role: 'teacher' }, csrfToken: 'csrf-token' },
  requestId: 'request-1',
};

describe('认证 API', () => {
  it('按后端角色进入对应首页', () => {
    expect(homeForRole('teacher')).toBe('/teacher/tasks');
    expect(homeForRole('student')).toBe('/student/tasks');
  });

  it('登录使用同源 Cookie 且不伪造角色', async () => {
    const fetchMock = mockResponse(session);
    await expect(login('teacher', 'secret')).resolves.toEqual(session);
    const [path, init] = fetchMock.mock.calls[0]!;
    expect(path).toBe('/api/v1/auth/login');
    expect(init).toEqual(expect.objectContaining({ method: 'POST', credentials: 'same-origin' }));
    expect(init?.body).toBe(JSON.stringify({ username: 'teacher', password: 'secret' }));
    expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('恢复会话读取后端返回的角色与 CSRF', async () => {
    const fetchMock = mockResponse(session);
    await expect(getCurrentSession()).resolves.toEqual(session);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/me');
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ method: 'GET', credentials: 'same-origin' }));
  });

  it('退出携带内存中的 CSRF token', async () => {
    const fetchMock = mockResponse({ data: { loggedOut: true }, requestId: 'request-2' });
    await expect(logout('csrf-token')).resolves.toMatchObject({ data: { loggedOut: true } });
    const init = fetchMock.mock.calls[0]?.[1];
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/logout');
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('csrf-token');
    expect(init?.body).toBe('{}');
  });

  it.each([
    { user: { id: '1', displayName: '用户', role: 'admin' }, csrfToken: 'x' },
    { user: { id: '', displayName: '用户', role: 'teacher' }, csrfToken: 'x' },
    { user: { id: '1', displayName: '', role: 'student' }, csrfToken: 'x' },
    { user: { id: '1', displayName: '用户', role: 'student' }, csrfToken: '' },
  ])('拒绝无效认证响应 %#', async data => {
    mockResponse({ data, requestId: 'invalid' });
    await expect(getCurrentSession()).rejects.toMatchObject({ kind: 'invalid-response' });
  });
});
