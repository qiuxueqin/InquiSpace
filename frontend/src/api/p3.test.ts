import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createConfirmation,
  getPublishReadiness,
  startPlanGeneration,
  startPreflight,
  startValidation,
  saveRoleCard,
  undoPlanGeneration,
} from './p3';

function mockResponse(data: unknown, status = 200) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify({ data, requestId: 'request-1' }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const run = {
  id: 'run-1', kind: 'plan_generate', status: 'running', displayMessage: '正在生成教学方案',
  sessionId: null, versionId: 'version-1', result: null, error: null,
  createdAt: '2026-11-04T00:00:00Z', finishedAt: null,
};

const version = {
  id: 'version-1', taskId: 'task-1', versionNo: 1, revision: 3, status: 'draft',
  teachingIntent: '探究身份变化', brief: {}, questionPlan: [], roleCard: null, sourceIds: [],
  manualFields: [], generationMeta: {}, validationStatus: 'stale', validatedRevision: null,
  previewRevision: null, missingFields: [], nextQuestions: [],
};

afterEach(() => vi.unstubAllGlobals());

describe('P3 API', () => {
  it('启动方案生成时发送并发、幂等与 CSRF 头', async () => {
    const fetchMock = mockResponse(run, 202);
    await startPlanGeneration('version-1', 2, 'csrf-token');
    const [path, init] = fetchMock.mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);
    expect(path).toBe('/api/v1/versions/version-1/plan-generations');
    expect(init?.body).toBe('{}');
    expect(headers.get('If-Match')).toBe('"rev-2"');
    expect(headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(headers.get('Idempotency-Key')).toBeTruthy();
  });

  it('校验和自动预检均使用当前 revision', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: run, requestId: 'request-1' }), {
        status: 202, headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: run, requestId: 'request-2' }), {
        status: 202, headers: { 'Content-Type': 'application/json' },
      }));
    vi.stubGlobal('fetch', fetchMock);
    await startValidation('version-1', 4, 'csrf');
    await startPreflight('version-1', 5, 'csrf');
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('If-Match')).toBe('"rev-4"');
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('If-Match')).toBe('"rev-5"');
  });

  it('读取准备状态不会发送写请求', async () => {
    const readiness = {
      ready: false, state: 'needs_input', revision: 2, taskRevision: 1,
      contentHash: 'a'.repeat(64), blockingIssues: [{ message: '请补充角色' }], nextQuestions: [],
    };
    const fetchMock = mockResponse(readiness);
    await expect(getPublishReadiness('version-1')).resolves.toMatchObject({ data: readiness });
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'GET' });
  });

  it('手工角色保存使用 PUT 和当前 revision', async () => {
    const fetchMock = mockResponse({ roleCard: {
      roleId: 'role-1', name: '角色', identityDescription: '身份', openingMessage: '你好',
      recommendedQuestions: ['问题'], roleType: 'fictional_composite', sourceIds: [],
    }, revision: 3 });
    await saveRoleCard('version-1', 2, 'csrf', { name: '角色' });
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('PUT');
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('If-Match')).toBe('"rev-2"');
  });

  it('替换确认和撤销均绑定当前版本', async () => {
    const confirmation = {
      confirmationId: 'confirmation-1', action: 'replace_plan', versionRevision: 2,
      expiresAt: '2026-11-04T10:00:00Z',
    };
    const confirmFetch = mockResponse(confirmation, 201);
    await createConfirmation('version-1', 2, 'csrf', 1, {
      action: 'replace_plan',
      payload: { intentHash: 'hash', overwrittenFields: ['brief.topicName'] },
    });
    expect(JSON.parse(String(confirmFetch.mock.calls[0]?.[1]?.body))).toMatchObject({
      confirmed: true, taskRevision: 1, action: 'replace_plan',
    });

    const undoFetch = mockResponse(version);
    await expect(undoPlanGeneration('version-1', 'run-1', 2, 'csrf')).resolves.toMatchObject({
      data: { revision: 3 },
    });
    expect(undoFetch.mock.calls[0]?.[0]).toBe('/api/v1/versions/version-1/plan-generations/run-1/undo');
  });
});
