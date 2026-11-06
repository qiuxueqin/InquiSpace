import { afterEach, describe, expect, it, vi } from 'vitest';
import { request, isRecord } from './client';
import { getHealth } from './health';

const health = {
  data: { status: 'ok', service: 'inquispace', version: '0.1.0', database: 'ok' },
  requestId: 'test-request',
};

function mockResponse(body: unknown, status = 200) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('API client', () => {
  it('读取真实契约并使用同源凭据', async () => {
    const fetchMock = mockResponse(health);
    await expect(getHealth()).resolves.toEqual(health);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', expect.objectContaining({
      method: 'GET', credentials: 'same-origin', redirect: 'error',
    }));
    const init = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('保留服务错误、请求编号与可重试标识', async () => {
    mockResponse({
      error: { code: 'DATABASE_UNAVAILABLE', message: '数据库暂不可用', details: {}, retryable: true },
      requestId: 'failed-request',
    }, 503);
    await expect(getHealth()).rejects.toMatchObject({
      kind: 'http', status: 503, code: 'DATABASE_UNAVAILABLE',
      requestId: 'failed-request', retryable: true, details: {},
    });
  });

  it('保留文档中的对象错误详情', async () => {
    mockResponse({
      error: { code: 'REVISION_CONFLICT', message: '内容已变化', details: { currentRevision: 4 }, retryable: false },
      requestId: 'conflict-request',
    }, 412);
    await expect(getHealth()).rejects.toMatchObject({
      kind: 'http', status: 412, details: { currentRevision: 4 },
    });
  });

  it.each([[], null, 'invalid', 4])('拒绝非对象错误详情 %#', async (details) => {
    mockResponse({
      error: { code: 'ERROR', message: '错误', details, retryable: false },
      requestId: 'invalid-details',
    }, 422);
    await expect(getHealth()).rejects.toMatchObject({ kind: 'invalid-response' });
  });

  it.each([
    { data: health.data },
    { data: { ...health.data, database: 'down' }, requestId: 'bad' },
    { data: null, requestId: 'bad' },
  ])('拒绝不符合健康接口契约的响应 %#', async (payload) => {
    mockResponse(payload);
    await expect(getHealth()).rejects.toMatchObject({ kind: 'invalid-response' });
  });

  it('拒绝非 JSON 响应及错误信封', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response('<html>proxy error</html>')));
    await expect(getHealth()).rejects.toMatchObject({ kind: 'invalid-response' });
    mockResponse({ error: 'bad gateway' }, 502);
    await expect(getHealth()).rejects.toMatchObject({ kind: 'invalid-response', status: 502 });
  });

  it('区分网络失败', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(getHealth()).rejects.toMatchObject({ kind: 'network', retryable: true });
  });

  it('已取消请求不会发出网络调用', async () => {
    const fetchMock = mockResponse(health);
    const controller = new AbortController();
    controller.abort();
    await expect(getHealth(controller.signal)).rejects.toMatchObject({ kind: 'aborted', retryable: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('请求过程中可取消', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation((_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      }),
    ));
    const controller = new AbortController();
    const pending = getHealth(controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ kind: 'aborted' });
  });

  it('超时可重试且不会永远 loading', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation((_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      }),
    ));
    const assertion = expect(getHealth()).rejects.toMatchObject({ kind: 'timeout', retryable: true });
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
  });

  it('写操作支持调用方提供 CSRF token，不设置 Authorization', async () => {
    const fetchMock = mockResponse({ data: {}, requestId: 'write-test' });
    await request('/api/test-only', isRecord, { method: 'POST', body: { title: '测试' }, csrfToken: 'memory-token' });
    const init = fetchMock.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(headers.get('X-CSRF-Token')).toBe('memory-token');
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(headers.has('Authorization')).toBe(false);
    expect(init?.body).toBe(JSON.stringify({ title: '测试' }));
  });

  it('上传 FormData 时保留浏览器 multipart 边界并支持条件头', async () => {
    const fetchMock = mockResponse({ data: {}, requestId: 'upload-test' });
    const formData = new FormData();
    formData.set('file', new Blob(['资料']), '资料.txt');
    await request('/api/test-upload', isRecord, {
      method: 'POST', formData, csrfToken: 'memory-token', headers: { 'If-Match': '"rev-2"' },
    });
    const init = fetchMock.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(init?.body).toBe(formData);
    expect(headers.has('Content-Type')).toBe(false);
    expect(headers.get('If-Match')).toBe('"rev-2"');
    expect(headers.get('X-CSRF-Token')).toBe('memory-token');
  });

  it('拒绝同时发送 JSON 与 FormData', async () => {
    const formData = new FormData();
    await expect(request('/api/test-upload', isRecord, {
      method: 'POST', body: {}, formData,
    })).rejects.toThrow('不能同时包含');
  });
});
