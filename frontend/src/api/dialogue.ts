import { isRecord, request } from './client';
import { isRunView } from './p3';
import type { RunView } from './p3';

export type PublicRole = {
  roleId: string;
  name: string;
  roleType: 'real_historical' | 'fictional_composite';
  identityDescription: string;
  timeAnchor: Record<string, unknown> | null;
  openingMessage: string;
  recommendedQuestions: string[];
};

export type RoleSessionView = {
  id: string;
  taskId: string;
  versionId: string;
  versionRevision: number;
  ownerId: string;
  mode: 'preview' | 'student';
  status: 'active' | 'ended';
  completedTurns: number;
  learningRevision: number;
  sourceTracking: 'complete' | 'partial' | 'unavailable';
  publicRole: PublicRole;
  summary: Record<string, unknown>;
  createdAt: string;
  endedAt: string | null;
};

export type CitationView = {
  id: string;
  messageId: string;
  blockIndex: number;
  evidenceId: string;
  sourceId: string;
  fileName: string;
  pageNo: number | null;
  startLine: number | null;
  endLine: number | null;
  paragraphNo: number;
  quote: string;
};

export type AnswerBlock = {
  blockIndex: number;
  type: 'fact' | 'opinion' | 'inference' | 'unknown';
  text: string;
  evidenceIds: string[];
};

export type MessageView = {
  id: string;
  sessionId: string;
  seq: number;
  speaker: 'user' | 'assistant';
  status: 'pending' | 'partial' | 'complete' | 'discarded';
  text: string;
  blocks: AnswerBlock[];
  citations: CitationView[];
  runId: string | null;
  supersedesMessageId: string | null;
  meta: {
    roleId: string | null;
    roleType: string | null;
    timeAnchor: Record<string, unknown> | null;
    followUpQuestions: string[];
    phase: string | null;
    memorySummary: string | null;
  };
  createdAt: string;
};

export type MessagePage = {
  items: MessageView[];
  nextAfterSeq: number;
  hasMore: boolean;
};

export function uniqueMessageSources(message: MessageView): CitationView[] {
  const sources = new Map<string, CitationView>();
  for (const citation of message.citations) {
    if (!sources.has(citation.sourceId)) sources.set(citation.sourceId, citation);
  }
  return [...sources.values()];
}

export type SessionListItem = {
  id: string;
  versionId: string;
  versionNo: number;
  status: 'active' | 'ended';
  completedTurns: number;
  createdAt: string;
};

export type SessionPage = { items: SessionListItem[]; nextCursor: string | null };

export type RunEvent = { seq: number; event: string; data: Record<string, unknown> };

export function applyRunEventToMessages(messages: MessageView[], event: RunEvent): MessageView[] {
  const messageId = typeof event.data.messageId === 'string' ? event.data.messageId : null;
  if (!messageId) return messages;

  const candidateBlock = event.data.block;
  if (event.event === 'answer.block' && isBlock(candidateBlock)) {
    const block = candidateBlock;
    const citations = Array.isArray(event.data.citations)
      ? event.data.citations.filter(isCitation)
      : [];
    return messages.map(message => {
      if (message.id !== messageId) return message;
      const blocks = [
        ...message.blocks.filter(item => item.blockIndex !== block.blockIndex),
        block,
      ].sort((left, right) => left.blockIndex - right.blockIndex);
      const citationById = new Map(message.citations.map(item => [item.id, item]));
      for (const citation of citations) citationById.set(citation.id, citation);
      return {
        ...message,
        status: 'partial',
        text: blocks.map(item => item.text).join('\n\n'),
        blocks,
        citations: [...citationById.values()],
      };
    });
  }

  if (event.event === 'answer.meta') {
    const followUpQuestions = isStringArray(event.data.followUpQuestions)
      ? event.data.followUpQuestions
      : [];
    return messages.map(message => message.id === messageId ? {
      ...message,
      meta: {
        ...message.meta,
        followUpQuestions,
        phase: typeof event.data.phase === 'string' ? event.data.phase : message.meta.phase,
        memorySummary: typeof event.data.memorySummary === 'string'
          ? event.data.memorySummary
          : message.meta.memorySummary,
      },
    } : message);
  }

  if (event.event === 'run.completed') {
    return messages.map(message => message.id === messageId
      ? { ...message, status: 'complete' }
      : message);
  }

  return messages;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}

function isPublicRole(value: unknown): value is PublicRole {
  return isRecord(value) && typeof value.roleId === 'string' && typeof value.name === 'string'
    && (value.roleType === 'real_historical' || value.roleType === 'fictional_composite')
    && typeof value.identityDescription === 'string' && typeof value.openingMessage === 'string'
    && isStringArray(value.recommendedQuestions);
}

export function isRoleSessionView(value: unknown): value is RoleSessionView {
  return isRecord(value) && typeof value.id === 'string' && typeof value.taskId === 'string'
    && typeof value.versionId === 'string' && Number.isInteger(value.versionRevision)
    && typeof value.ownerId === 'string' && (value.mode === 'preview' || value.mode === 'student')
    && (value.status === 'active' || value.status === 'ended') && Number.isInteger(value.completedTurns)
    && Number.isInteger(value.learningRevision)
    && ['complete', 'partial', 'unavailable'].includes(String(value.sourceTracking))
    && isPublicRole(value.publicRole)
    && isRecord(value.summary) && typeof value.createdAt === 'string';
}

function isCitation(value: unknown): value is CitationView {
  return isRecord(value) && typeof value.id === 'string' && typeof value.messageId === 'string'
    && Number.isInteger(value.blockIndex) && typeof value.evidenceId === 'string'
    && typeof value.sourceId === 'string' && typeof value.fileName === 'string'
    && Number.isInteger(value.paragraphNo) && typeof value.quote === 'string';
}

function isBlock(value: unknown): value is AnswerBlock {
  return isRecord(value) && Number.isInteger(value.blockIndex)
    && ['fact', 'opinion', 'inference', 'unknown'].includes(String(value.type))
    && typeof value.text === 'string' && isStringArray(value.evidenceIds);
}

export function isMessageView(value: unknown): value is MessageView {
  return isRecord(value) && typeof value.id === 'string' && typeof value.sessionId === 'string'
    && Number.isInteger(value.seq) && (value.speaker === 'user' || value.speaker === 'assistant')
    && ['pending', 'partial', 'complete', 'discarded'].includes(String(value.status))
    && typeof value.text === 'string' && Array.isArray(value.blocks) && value.blocks.every(isBlock)
    && Array.isArray(value.citations) && value.citations.every(isCitation) && isRecord(value.meta)
    && typeof value.createdAt === 'string';
}

export function isMessagePage(value: unknown): value is MessagePage {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isMessageView)
    && Number.isInteger(value.nextAfterSeq) && typeof value.hasMore === 'boolean';
}

function isStartedMessage(value: unknown): value is {
  userMessageId: string; assistantMessageId: string; runId: string;
} {
  return isRecord(value) && typeof value.userMessageId === 'string'
    && typeof value.assistantMessageId === 'string' && typeof value.runId === 'string';
}

function isCancelled(value: unknown): value is {
  runId: string; cancelRequested: boolean; status: string;
} {
  return isRecord(value) && typeof value.runId === 'string'
    && typeof value.cancelRequested === 'boolean' && typeof value.status === 'string';
}

export function createPreviewSession(
  versionId: string,
  revision: number,
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/preview-sessions`, isRoleSessionView, {
    method: 'POST', body: {}, csrfToken,
    headers: { 'If-Match': `"rev-${revision}"`, 'Idempotency-Key': crypto.randomUUID() },
    ...(signal ? { signal } : {}),
  });
}

export function getRoleSession(sessionId: string, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, isRoleSessionView, signal ? { signal } : {});
}

export function getMessages(sessionId: string, afterSeq = 0, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages?afterSeq=${afterSeq}&limit=100`, isMessagePage, signal ? { signal } : {});
}

function isSessionPage(value: unknown): value is SessionPage {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(item => isRecord(item)
    && typeof item.id === 'string' && typeof item.versionId === 'string'
    && Number.isInteger(item.versionNo) && ['active', 'ended'].includes(String(item.status))
    && Number.isInteger(item.completedTurns) && typeof item.createdAt === 'string');
}

export function listTaskSessions(taskId: string, signal?: AbortSignal) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/sessions?limit=100`, isSessionPage, signal ? { signal } : {});
}

export function sendDialogueMessage(
  sessionId: string,
  content: string,
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`, isStartedMessage, {
    method: 'POST', body: { content }, csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    ...(signal ? { signal } : {}),
  });
}

export function cancelRun(runId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, isCancelled, {
    method: 'POST', body: {}, csrfToken, ...(signal ? { signal } : {}),
  });
}

export function retryRun(runId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/retry`, isRunView, {
    method: 'POST', body: {}, csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    ...(signal ? { signal } : {}),
  });
}

export function startSummary(sessionId: string, csrfToken: string, signal?: AbortSignal) {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/summaries`, isRunView, {
    method: 'POST', body: {}, csrfToken,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    ...(signal ? { signal } : {}),
  });
}

export function getDialogueRun(runId: string, signal?: AbortSignal): Promise<{ data: RunView; requestId: string }> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}`, isRunView, signal ? { signal } : {});
}

export function parseSseChunk(buffer: string, chunk: string): { events: RunEvent[]; rest: string } {
  const normalized = `${buffer}${chunk}`.replace(/\r\n/g, '\n');
  const parts = normalized.split('\n\n');
  const rest = parts.pop() ?? '';
  const events: RunEvent[] = [];
  for (const part of parts) {
    if (!part || part.startsWith(':')) continue;
    let id: number | null = null;
    let event = '';
    const data: string[] = [];
    for (const line of part.split('\n')) {
      if (line.startsWith('id:')) id = Number(line.slice(3).trim());
      else if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    if (id === null || !Number.isInteger(id) || !event) continue;
    const parsed: unknown = JSON.parse(data.join('\n'));
    if (isRecord(parsed)) events.push({ seq: id, event, data: parsed });
  }
  return { events, rest };
}

export async function streamRunEvents(
  runId: string,
  afterSeq: number,
  onEvent: (event: RunEvent) => void,
  signal: AbortSignal,
): Promise<number> {
  const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/events?afterSeq=${afterSeq}`, {
    headers: { Accept: 'text/event-stream' }, credentials: 'same-origin', redirect: 'error',
    cache: 'no-store', signal,
  });
  if (!response.ok || !response.body) throw new Error('无法连接回答事件流。');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let cursor = afterSeq;
  while (true) {
    const { value, done } = await reader.read();
    const parsed = parseSseChunk(buffer, decoder.decode(value ?? new Uint8Array(), { stream: !done }));
    buffer = parsed.rest;
    for (const event of parsed.events) {
      if (event.seq <= cursor) continue;
      cursor = event.seq;
      onEvent(event);
    }
    if (done) return cursor;
  }
}
