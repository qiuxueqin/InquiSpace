import { describe, expect, it, vi } from 'vitest';
import {
  addReportCorrection,
  createStudentSession,
  getLearningReport,
  getTeacherReport,
  recordLearningEvent,
} from './p5';

function response(data: unknown) {
  return new Response(JSON.stringify({ data, requestId: 'request-1' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

const report = {
  id: 'report-1', sessionId: 'session-1', reportNo: 1, kind: 'live', status: 'ready', inputRevision: 2,
  generatedAt: '2026-11-04T00:00:00Z', sourceTracking: 'complete',
  content: { summary: { text: '摘要', messageIds: ['m1'] }, findings: [], signals: [], missingAspects: [], nextSteps: [] },
  metrics: { expressionCount: 1, evidenceSeekingCount: 0, sourceViewCount: 0, judgmentCount: 0, reflectionCount: 0 },
};

const envelope = {
  sessionId: 'session-1', sessionStatus: 'active', currentLearningRevision: 2,
  currentReport: report, latestReadyReport: report, freshness: 'current', corrections: [],
  nextCorrectionCursor: null, legacySubmission: null,
};

describe('P5 API runtime contracts', () => {
  it('creates student sessions and validates report envelopes', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({ id: 'session-1' }))
      .mockResolvedValueOnce(response(envelope));
    await expect(createStudentSession('task-1', 'csrf')).resolves.toMatchObject({ data: { id: 'session-1' } });
    await expect(getLearningReport('session-1')).resolves.toMatchObject({ data: { freshness: 'current' } });
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/tasks/task-1/sessions');
    fetchMock.mockRestore();
  });

  it('sends source and correction writes with the required body', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({ id: 'event-1', rowVersion: 1 }))
      .mockResolvedValueOnce(response({ id: 'correction-1', text: '补充' }));
    await recordLearningEvent('session-1', { type: 'source_open', sourceId: 'source-1' }, 'csrf');
    await addReportCorrection('session-1', 'report-1', '补充', 'csrf');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ type: 'source_open', sourceId: 'source-1' });
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ reportId: 'report-1', text: '补充' });
    fetchMock.mockRestore();
  });

  it('validates teacher aggregate metrics including null unknowns', async () => {
    const teacher = {
      taskId: 'task-1', scope: 'latest', versionId: null, versions: [], asOf: '2026-11-04T00:00:00Z', aggregateToken: 'hash',
      kpis: {}, progress: {}, metrics: { expressionCount: 1, evidenceSeekingCount: null, sourceViewCount: null, judgmentCount: null, reflectionCount: null },
      coverage: {}, classroomSummary: {}, suggestions: [], students: [], nextCursor: null,
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(teacher));
    await expect(getTeacherReport('task-1')).resolves.toMatchObject({ data: { aggregateToken: 'hash' } });
    fetchMock.mockRestore();
  });
});
