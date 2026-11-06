import { isRecord, request } from './client';
import { isVersionView } from './tasks';
import type { RoleCardView } from './tasks';

export type RunStatus = 'running' | 'waiting_confirmation' | 'completed' | 'failed' | 'cancelled';

export type RunView = {
  id: string;
  kind: string;
  status: RunStatus;
  displayMessage: string;
  sessionId: string | null;
  versionId: string | null;
  result: Record<string, unknown> | null;
  error: { code: string; message: string; retryable: boolean } | null;
  createdAt: string;
  finishedAt: string | null;
};

export type PublishReadiness = {
  ready: boolean;
  state: 'preparing' | 'needs_input' | 'ready' | 'unavailable';
  revision: number;
  taskRevision: number;
  contentHash: string;
  blockingIssues: Array<{ field?: string | null; message: string }>;
  nextQuestions: string[];
};

export type ConfirmationView = {
  confirmationId: string;
  action: 'publish_version' | 'archive_task' | 'apply_role_candidate' | 'replace_plan';
  versionRevision: number;
  expiresAt: string;
};

export type AppliedCandidate = {
  roleCard: RoleCardView;
  questionPlan: Array<Record<string, unknown>>;
  revision: number;
};

function isRunError(value: unknown): value is RunView['error'] {
  return value === null || (isRecord(value)
    && typeof value.code === 'string'
    && typeof value.message === 'string'
    && typeof value.retryable === 'boolean');
}

export function isRunView(value: unknown): value is RunView {
  return isRecord(value)
    && typeof value.id === 'string'
    && typeof value.kind === 'string'
    && ['running', 'waiting_confirmation', 'completed', 'failed', 'cancelled'].includes(String(value.status))
    && typeof value.displayMessage === 'string'
    && (value.sessionId === null || typeof value.sessionId === 'string')
    && (value.versionId === null || typeof value.versionId === 'string')
    && (value.result === null || isRecord(value.result))
    && isRunError(value.error)
    && typeof value.createdAt === 'string'
    && (value.finishedAt === null || typeof value.finishedAt === 'string');
}

function isReadiness(value: unknown): value is PublishReadiness {
  return isRecord(value)
    && typeof value.ready === 'boolean'
    && ['preparing', 'needs_input', 'ready', 'unavailable'].includes(String(value.state))
    && Number.isInteger(value.revision)
    && Number.isInteger(value.taskRevision)
    && typeof value.contentHash === 'string'
    && Array.isArray(value.blockingIssues)
    && value.blockingIssues.every(item => isRecord(item) && typeof item.message === 'string')
    && Array.isArray(value.nextQuestions)
    && value.nextQuestions.every(item => typeof item === 'string');
}

function isConfirmation(value: unknown): value is ConfirmationView {
  return isRecord(value)
    && typeof value.confirmationId === 'string'
    && ['publish_version', 'archive_task', 'apply_role_candidate', 'replace_plan'].includes(String(value.action))
    && Number.isInteger(value.versionRevision)
    && typeof value.expiresAt === 'string';
}

function isRoleCard(value: unknown): value is RoleCardView {
  return isRecord(value)
    && typeof value.roleId === 'string'
    && typeof value.name === 'string'
    && typeof value.identityDescription === 'string'
    && typeof value.openingMessage === 'string'
    && Array.isArray(value.recommendedQuestions);
}

function isRoleSave(value: unknown): value is { roleCard: RoleCardView; revision: number } {
  return isRecord(value) && isRoleCard(value.roleCard) && Number.isInteger(value.revision);
}

function isAppliedCandidate(value: unknown): value is AppliedCandidate {
  return isRecord(value)
    && isRoleCard(value.roleCard)
    && Array.isArray(value.questionPlan)
    && Number.isInteger(value.revision);
}

function writeHeaders(revision: number, key = crypto.randomUUID()) {
  return { 'If-Match': `"rev-${revision}"`, 'Idempotency-Key': key };
}

export function startPlanGeneration(
  versionId: string,
  revision: number,
  csrfToken: string,
  confirmationId?: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/plan-generations`, isRunView, {
    method: 'POST',
    body: confirmationId ? { confirmationId } : {},
    csrfToken,
    headers: writeHeaders(revision),
    timeoutMs: 30_000,
    ...(signal ? { signal } : {}),
  });
}

export function undoPlanGeneration(
  versionId: string,
  runId: string,
  revision: number,
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/plan-generations/${encodeURIComponent(runId)}/undo`, isVersionView, {
    method: 'POST',
    body: {},
    csrfToken,
    headers: writeHeaders(revision),
    ...(signal ? { signal } : {}),
  });
}

export function saveRoleCard(
  versionId: string,
  revision: number,
  csrfToken: string,
  roleCard: Record<string, unknown>,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/role-card`, isRoleSave, {
    method: 'PUT',
    body: { roleCard },
    csrfToken,
    headers: { 'If-Match': `"rev-${revision}"` },
    ...(signal ? { signal } : {}),
  });
}

export function startRoleGeneration(
  versionId: string,
  revision: number,
  csrfToken: string,
  instruction = '',
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/role-generations`, isRunView, {
    method: 'POST',
    body: instruction ? { instruction } : {},
    csrfToken,
    headers: writeHeaders(revision),
    timeoutMs: 30_000,
    ...(signal ? { signal } : {}),
  });
}

export function startValidation(
  versionId: string,
  revision: number,
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/validations`, isRunView, {
    method: 'POST', body: {}, csrfToken, headers: writeHeaders(revision),
    timeoutMs: 30_000, ...(signal ? { signal } : {}),
  });
}

export function startPreflight(
  versionId: string,
  revision: number,
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/preflights`, isRunView, {
    method: 'POST', body: {}, csrfToken, headers: writeHeaders(revision),
    timeoutMs: 30_000, ...(signal ? { signal } : {}),
  });
}

export function getRun(runId: string, signal?: AbortSignal) {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}`, isRunView, signal ? { signal } : {});
}

export async function waitForRun(
  runId: string,
  signal?: AbortSignal,
  options: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<RunView> {
  const intervalMs = options.intervalMs ?? 600;
  const timeoutMs = options.timeoutMs ?? 180_000;
  const deadline = Date.now() + timeoutMs;
  while (true) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const run = (await getRun(runId, signal)).data;
    if (run.status !== 'running') return run;
    if (Date.now() >= deadline) throw new Error('方案准备时间较长，请稍后重新打开页面查看。');
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(resolve, intervalMs);
      signal?.addEventListener('abort', () => {
        window.clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      }, { once: true });
    });
  }
}

export function getPublishReadiness(versionId: string, signal?: AbortSignal) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/publish-check`, isReadiness, signal ? { signal } : {});
}

export function createConfirmation(
  versionId: string,
  revision: number,
  csrfToken: string,
  taskRevision: number,
  body: {
    action: 'publish_version' | 'archive_task' | 'apply_role_candidate' | 'replace_plan';
    payload: { runId?: string; candidateHash?: string; intentHash?: string; overwrittenFields?: string[]; studentIds?: string[] };
  },
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/confirmations`, isConfirmation, {
    method: 'POST',
    body: { ...body, confirmed: true, taskRevision },
    csrfToken,
    headers: writeHeaders(revision),
    ...(signal ? { signal } : {}),
  });
}

export function applyRoleCandidate(
  versionId: string,
  runId: string,
  revision: number,
  csrfToken: string,
  confirmationId: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/role-candidates/${encodeURIComponent(runId)}/apply`, isAppliedCandidate, {
    method: 'POST',
    body: { confirmationId },
    csrfToken,
    headers: writeHeaders(revision),
    ...(signal ? { signal } : {}),
  });
}
