import { isRecord, request } from './client';

export type TimeAnchor = {
  value: string;
  precision: 'year' | 'month' | 'day';
};

export type RoleCardView = {
  roleId: string;
  name: string;
  roleType: 'real_historical' | 'fictional_composite';
  identityDescription: string;
  historicalPeriod: string;
  timeAnchor: TimeAnchor | null;
  region: string;
  socialGroup: string;
  position: string;
  goals: string[];
  concerns: string[];
  relationships: Array<{ target: string; description: string }>;
  knownFacts: Array<{ text: string; evidenceIds: string[]; origin: 'material' | 'teacher' }>;
  unknownFacts: string[];
  sourceIds: string[];
  disputedClaims: Array<{ text: string; evidenceIds: string[]; limitation: string }>;
  speechStyle: string;
  openingMessage: string;
  recommendedQuestions: string[];
  learningDimension: string;
  forbiddenBehaviors: string[];
};

export type VersionView = {
  id: string;
  taskId: string;
  versionNo: number;
  revision: number;
  status: string;
  teachingIntent: string;
  brief: Record<string, unknown>;
  questionPlan: Array<Record<string, unknown>>;
  roleCard: RoleCardView | null;
  sourceIds: string[];
  manualFields: string[];
  generationMeta: Record<string, unknown>;
  validationStatus: 'stale' | 'valid' | 'invalid';
  validatedRevision: number | null;
  previewRevision: number | null;
  missingFields: string[];
  nextQuestions: string[];
};

export type TaskDetail = {
  id: string;
  status: string;
  taskRevision: number;
  currentPublishedVersionId: string | null;
  draftVersionId: string | null;
};

export type CreatedTask = {
  taskId: string;
  taskRevision: number;
  draft: VersionView;
};

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}

function isRoleCard(value: unknown): value is RoleCardView {
  return isRecord(value)
    && typeof value.roleId === 'string'
    && typeof value.name === 'string'
    && (value.roleType === 'real_historical' || value.roleType === 'fictional_composite')
    && typeof value.identityDescription === 'string'
    && typeof value.openingMessage === 'string'
    && isStringArray(value.recommendedQuestions)
    && isStringArray(value.sourceIds);
}

function isTaskDetail(value: unknown): value is TaskDetail {
  return isRecord(value) && typeof value.id === 'string' && typeof value.status === 'string'
    && Number.isInteger(value.taskRevision)
    && isNullableString(value.currentPublishedVersionId)
    && isNullableString(value.draftVersionId);
}

export function isVersionView(value: unknown): value is VersionView {
  return isRecord(value)
    && typeof value.id === 'string'
    && typeof value.taskId === 'string'
    && Number.isInteger(value.versionNo)
    && Number.isInteger(value.revision)
    && typeof value.status === 'string'
    && typeof value.teachingIntent === 'string'
    && isRecord(value.brief)
    && Array.isArray(value.questionPlan)
    && (value.roleCard === null || isRoleCard(value.roleCard))
    && isStringArray(value.sourceIds)
    && isStringArray(value.manualFields)
    && isRecord(value.generationMeta)
    && ['stale', 'valid', 'invalid'].includes(String(value.validationStatus))
    && (value.validatedRevision === null || Number.isInteger(value.validatedRevision))
    && (value.previewRevision === null || Number.isInteger(value.previewRevision))
    && isStringArray(value.missingFields)
    && isStringArray(value.nextQuestions);
}

function isCreatedTask(value: unknown): value is CreatedTask {
  return isRecord(value) && typeof value.taskId === 'string' && Number.isInteger(value.taskRevision)
    && isVersionView(value.draft);
}

export function createTaskDraftWithIntent(
  csrfToken: string,
  body: { teachingIntent?: string; brief?: Record<string, unknown> } = {},
  signal?: AbortSignal,
) {
  return request('/api/v1/tasks', isCreatedTask, {
    method: 'POST',
    body,
    csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    ...(signal ? { signal } : {}),
  });
}

export function createTaskDraft(csrfToken: string, signal?: AbortSignal) {
  return createTaskDraftWithIntent(csrfToken, {}, signal);
}

export function getTask(taskId: string, signal?: AbortSignal) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}`, isTaskDetail, signal ? { signal } : {});
}

export function getVersion(versionId: string, signal?: AbortSignal) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}`, isVersionView, signal ? { signal } : {});
}

export function patchVersion(
  versionId: string,
  revision: number,
  csrfToken: string,
  body: { teachingIntent?: string; brief?: Record<string, unknown>; questionPlan?: Array<Record<string, unknown>> },
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}`, isVersionView, {
    method: 'PATCH',
    body,
    csrfToken,
    headers: { 'If-Match': `"rev-${revision}"` },
    ...(signal ? { signal } : {}),
  });
}
