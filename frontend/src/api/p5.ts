import { isRecord, request } from './client';

export type TaskListItem = {
  taskId: string;
  topicName: string;
  status: 'active' | 'archived';
  currentPublishedVersionId: string | null;
};

export type TaskPage = { items: TaskListItem[]; nextCursor: string | null };

export type LearningReport = {
  id: string;
  sessionId: string;
  reportNo: number;
  kind: 'live' | 'final';
  status: 'queued' | 'generating' | 'ready' | 'failed' | 'superseded';
  inputRevision: number;
  generatedAt: string | null;
  content: {
    summary: { text: string; messageIds: string[] };
    findings: Array<{ kind: string; text: string; messageIds: string[]; evidenceIds: string[] }>;
    signals: Array<{ messageId: string; quote: string; tags: string[] }>;
    missingAspects: string[];
    nextSteps: string[];
  } | null;
  metrics: ReportMetrics;
  sourceTracking: 'complete' | 'partial' | 'unavailable';
};

export type ReportMetrics = {
  expressionCount: number | null;
  evidenceSeekingCount: number | null;
  sourceViewCount: number | null;
  judgmentCount: number | null;
  reflectionCount: number | null;
};

export type ReportEnvelope = {
  sessionId: string;
  sessionStatus: 'active' | 'ended';
  currentLearningRevision: number;
  currentReport: LearningReport | null;
  latestReadyReport: LearningReport | null;
  freshness: 'empty' | 'updating' | 'current' | 'failed';
  corrections: Array<{ id: string; sessionId: string; reportId: string; authorId: string; text: string; createdAt: string }>;
  nextCorrectionCursor: string | null;
  legacySubmission: Record<string, unknown> | null;
};

export type NoteView = {
  id: string; sessionId: string; messageId: string; blockIndex: number; originalView: string;
  type: string; evidenceIds: string[]; judgment: string; credibility: string; limitations: string;
  rowVersion: number; createdAt: string; updatedAt: string;
};

export type TeacherReport = {
  taskId: string;
  scope: 'latest' | 'all' | 'version';
  versionId: string | null;
  versions: Array<{ id: string; versionNo: number }>;
  asOf: string;
  aggregateToken: string;
  kpis: { participantCount: number; sessionCount: number; completedTurns: number; completedReportCount: number };
  progress: { activeSessions: number; endedSessions: number };
  metrics: ReportMetrics;
  coverage: { totalSessions: number; readyReportSessions: number; currentReportSessions: number; sourceTrackedSessions: number; partialSourceSessions: number; unavailableSourceSessions: number };
  classroomSummary: { text: string; sessionIds: string[] };
  suggestions: Array<{ text: string; sessionIds: string[]; messageIds: string[] }>;
  students: Array<{
    userId: string; displayName: string; sessionId: string; versionId: string; versionNo: number;
    status: 'active' | 'ended'; metrics: ReportMetrics; reportId: string | null;
    reportStatus: string | null; reportFreshness: string; sourceTracking: string; correctionCount: number;
  }>;
  nextCursor: string | null;
};

const stringArray = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');
const nullableNumber = (value: unknown): value is number | null => value === null || Number.isInteger(value);

function isTaskPage(value: unknown): value is TaskPage {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(item => isRecord(item)
    && typeof item.taskId === 'string' && typeof item.topicName === 'string'
    && (item.status === 'active' || item.status === 'archived'));
}

function isMetrics(value: unknown): value is ReportMetrics {
  return isRecord(value) && nullableNumber(value.expressionCount) && nullableNumber(value.evidenceSeekingCount)
    && nullableNumber(value.sourceViewCount) && nullableNumber(value.judgmentCount) && nullableNumber(value.reflectionCount);
}

function isLearningReport(value: unknown): value is LearningReport {
  return isRecord(value) && typeof value.id === 'string' && typeof value.sessionId === 'string'
    && Number.isInteger(value.reportNo) && ['live', 'final'].includes(String(value.kind))
    && ['queued', 'generating', 'ready', 'failed', 'superseded'].includes(String(value.status))
    && Number.isInteger(value.inputRevision) && isMetrics(value.metrics)
    && (value.content === null || (isRecord(value.content) && isRecord(value.content.summary)
      && typeof value.content.summary.text === 'string' && stringArray(value.content.missingAspects)
      && stringArray(value.content.nextSteps)));
}

function isReportEnvelope(value: unknown): value is ReportEnvelope {
  return isRecord(value) && typeof value.sessionId === 'string'
    && ['active', 'ended'].includes(String(value.sessionStatus))
    && Number.isInteger(value.currentLearningRevision)
    && (value.currentReport === null || isLearningReport(value.currentReport))
    && (value.latestReadyReport === null || isLearningReport(value.latestReadyReport))
    && Array.isArray(value.corrections);
}

function isTeacherReport(value: unknown): value is TeacherReport {
  return isRecord(value) && typeof value.taskId === 'string' && typeof value.aggregateToken === 'string'
    && isRecord(value.kpis) && isRecord(value.progress) && isMetrics(value.metrics)
    && isRecord(value.coverage) && isRecord(value.classroomSummary) && Array.isArray(value.students)
    && value.students.every(item => isRecord(item) && typeof item.sessionId === 'string'
      && typeof item.displayName === 'string' && isMetrics(item.metrics));
}

const isSession = (value: unknown): value is { id: string } => isRecord(value) && typeof value.id === 'string';
const isEnd = (value: unknown): value is { sessionId: string; status: 'ended'; reportId: string | null; reportStatus: string | null } => isRecord(value) && typeof value.sessionId === 'string' && value.status === 'ended';
const isEvent = (value: unknown): value is { id: string; rowVersion: number } => isRecord(value) && typeof value.id === 'string' && Number.isInteger(value.rowVersion);
const isCorrection = (value: unknown): value is { id: string; text: string } => isRecord(value) && typeof value.id === 'string' && typeof value.text === 'string';
const isNote = (value: unknown): value is NoteView => isRecord(value) && typeof value.id === 'string'
  && typeof value.messageId === 'string' && Number.isInteger(value.blockIndex)
  && typeof value.originalView === 'string' && Number.isInteger(value.rowVersion);
const isNotePage = (value: unknown): value is { items: NoteView[]; nextCursor: string | null } => isRecord(value)
  && Array.isArray(value.items) && value.items.every(isNote);
const isQueue = (value: unknown): value is { reportId: string | null; status: string } => isRecord(value) && (value.reportId === null || typeof value.reportId === 'string') && typeof value.status === 'string';
const isPublish = (value: unknown): value is { taskId: string; versionId: string; status: 'published'; taskRevision: number } => isRecord(value) && typeof value.taskId === 'string' && typeof value.versionId === 'string' && value.status === 'published' && Number.isInteger(value.taskRevision);
const isTaskStatus = (value: unknown): value is { taskId: string; status: 'active' | 'archived'; taskRevision: number } => isRecord(value) && typeof value.taskId === 'string' && ['active', 'archived'].includes(String(value.status)) && Number.isInteger(value.taskRevision);

export function listRealTasks(signal?: AbortSignal) {
  return request('/api/v1/tasks?limit=100', isTaskPage, signal ? { signal } : {});
}

export function createStudentSession(taskId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/sessions`, isSession, {
    method: 'POST', body: {}, csrfToken, headers: { 'Idempotency-Key': crypto.randomUUID() }, ...(signal ? { signal } : {}),
  });
}

export function endSession(sessionId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/end`, isEnd, {
    method: 'POST', body: {}, csrfToken, headers: { 'Idempotency-Key': crypto.randomUUID() }, ...(signal ? { signal } : {}),
  });
}

export function getLearningReport(sessionId: string, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/learning-report`, isReportEnvelope, signal ? { signal } : {});
}

export function ensureLearningReport(sessionId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/learning-reports`, isQueue, {
    method: 'POST', body: {}, csrfToken, headers: { 'Idempotency-Key': crypto.randomUUID() }, timeoutMs: 30_000, ...(signal ? { signal } : {}),
  });
}

export function retryLearningReport(reportId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/learning-reports/${encodeURIComponent(reportId)}/retry`, isQueue, {
    method: 'POST', body: {}, csrfToken, headers: { 'Idempotency-Key': crypto.randomUUID() }, timeoutMs: 30_000, ...(signal ? { signal } : {}),
  });
}

export function recordLearningEvent(
  sessionId: string,
  body: { type: 'source_open'; sourceId: string } | { type: 'stance'; messageId: string; value: string; expectedRowVersion: number },
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/learning-events`, isEvent, {
    method: 'POST', body, csrfToken, headers: { 'Idempotency-Key': crypto.randomUUID() }, ...(signal ? { signal } : {}),
  });
}

export function listNotes(sessionId: string, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/notes?limit=100`, isNotePage, signal ? { signal } : {});
}

export function createNote(sessionId: string, messageId: string, blockIndex: number, csrfToken: string) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/notes`, isNote, {
    method: 'POST', body: { messageId, blockIndex }, csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
}

export function deleteNote(noteId: string, rowVersion: number, csrfToken: string) {
  const validator = (value: unknown): value is { deleted: true } => isRecord(value) && value.deleted === true;
  return request(`/api/v1/notes/${encodeURIComponent(noteId)}`, validator, {
    method: 'DELETE', csrfToken, headers: { 'If-Match': `"rev-${rowVersion}"` },
  });
}

export function addReportCorrection(sessionId: string, reportId: string, text: string, csrfToken: string) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/report-corrections`, isCorrection, {
    method: 'POST', body: { reportId, text }, csrfToken, headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
}

export function getTeacherReport(taskId: string, scope = 'latest', state = 'all', versionId?: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ scope, state, limit: '100' });
  if (versionId) query.set('versionId', versionId);
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/report?${query}` as `/api/${string}`, isTeacherReport, signal ? { signal } : {});
}

export function createPublishConfirmation(versionId: string, revision: number, taskRevision: number, studentIds: string[], csrfToken: string) {
  const validator = (value: unknown): value is { confirmationId: string } => isRecord(value) && typeof value.confirmationId === 'string';
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/confirmations`, validator, {
    method: 'POST', body: { action: 'publish_version', confirmed: true, taskRevision, payload: { studentIds } }, csrfToken,
    headers: { 'If-Match': `"rev-${revision}"`, 'Idempotency-Key': crypto.randomUUID() },
  });
}

export function publishVersion(versionId: string, revision: number, confirmationId: string, csrfToken: string) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/publish`, isPublish, {
    method: 'POST', body: { confirmationId }, csrfToken,
    headers: { 'If-Match': `"rev-${revision}"`, 'Idempotency-Key': crypto.randomUUID() },
  });
}

export function archiveTask(taskId: string, confirmationId: string, taskRevision: number, csrfToken: string) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/archive`, isTaskStatus, {
    method: 'POST', body: { confirmationId, expectedTaskRevision: taskRevision }, csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
}

export function restoreTask(taskId: string, taskRevision: number, csrfToken: string) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/restore`, isTaskStatus, {
    method: 'POST', body: { expectedTaskRevision: taskRevision }, csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
}

export async function exportTeacherReport(taskId: string, scope: string, versionId: string | undefined, aggregateToken: string, csrfToken: string) {
  const response = await fetch(`/api/v1/tasks/${encodeURIComponent(taskId)}/report-exports`, {
    method: 'POST', credentials: 'same-origin', redirect: 'error',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ scope, ...(versionId ? { versionId } : {}), aggregateToken }),
  });
  if (!response.ok) throw new Error('教学报告导出失败，请刷新后重试。');
  return response.blob();
}
