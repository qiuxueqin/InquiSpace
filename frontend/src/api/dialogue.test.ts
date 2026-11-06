import { describe, expect, it } from 'vitest';
import { applyRunEventToMessages, isMessagePage, isRoleSessionView, parseSseChunk, uniqueMessageSources } from './dialogue';

const roleSession = {
  id: 'session-1', taskId: 'task-1', versionId: 'version-1', versionRevision: 2,
  ownerId: 'teacher-1', mode: 'preview', status: 'active', completedTurns: 0,
  learningRevision: 0, sourceTracking: 'unavailable',
  publicRole: {
    roleId: 'role-1', name: '角色', roleType: 'fictional_composite',
    identityDescription: '身份', timeAnchor: null, openingMessage: '你好', recommendedQuestions: [],
  },
  summary: {}, createdAt: '2026-11-04T00:00:00Z', endedAt: null,
};

describe('dialogue runtime validators', () => {
  it('validates the public session projection without hidden role fields', () => {
    expect(isRoleSessionView(roleSession)).toBe(true);
    expect(isRoleSessionView({ ...roleSession, completedTurns: '0' })).toBe(false);
  });

  it('validates message pages and rejects malformed blocks', () => {
    const page = {
      items: [{
        id: 'message-1', sessionId: 'session-1', seq: 1, speaker: 'assistant', status: 'complete',
        text: '回答', blocks: [{ blockIndex: 0, type: 'unknown', text: '回答', evidenceIds: [] }],
        citations: [], runId: 'run-1', supersedesMessageId: null,
        meta: { roleId: 'role-1', roleType: 'fictional_composite', timeAnchor: null, followUpQuestions: [], phase: 'answer', memorySummary: null },
        createdAt: '2026-11-04T00:00:00Z',
      }],
      nextAfterSeq: 1,
      hasMore: false,
    };
    expect(isMessagePage(page)).toBe(true);
    expect(isMessagePage({ ...page, items: [{ ...page.items[0], blocks: [{ type: 'fact' }] }] })).toBe(false);
  });
  it('deduplicates references by source for end-of-answer display', () => {
    const citation = {
      id: 'citation-1', messageId: 'message-1', blockIndex: 0, evidenceId: 'evidence-1',
      sourceId: 'source-1', fileName: '资料.txt', pageNo: null, startLine: 1, endLine: 1,
      paragraphNo: 1, quote: '原文',
    };
    const message = {
      id: 'message-1', sessionId: 'session-1', seq: 1, speaker: 'assistant' as const,
      status: 'complete' as const, text: '回答', blocks: [],
      citations: [citation, { ...citation, id: 'citation-2', blockIndex: 1, evidenceId: 'evidence-2' }],
      runId: 'run-1', supersedesMessageId: null,
      meta: { roleId: 'role-1', roleType: 'fictional_composite', timeAnchor: null, followUpQuestions: [], phase: 'answer', memorySummary: null },
      createdAt: '2026-11-04T00:00:00Z',
    };

    expect(uniqueMessageSources(message)).toEqual([citation]);
  });
});

describe('SSE parsing', () => {
  it('keeps split frames and parses persisted events in sequence', () => {
    const first = parseSseChunk('', 'id: 1\nevent: run.started\ndata: {"runId":"r"}\n\nid: 2\nevent: answer.');
    expect(first.events).toEqual([{ seq: 1, event: 'run.started', data: { runId: 'r' } }]);
    const second = parseSseChunk(first.rest, 'block\ndata: {"runId":"r","seq":2}\n\n');
    expect(second.events).toEqual([{ seq: 2, event: 'answer.block', data: { runId: 'r', seq: 2 } }]);
    expect(second.rest).toBe('');
  });

  it('applies answer blocks as soon as SSE events arrive', () => {
    const pending = {
      id: 'message-1', sessionId: 'session-1', seq: 2, speaker: 'assistant' as const,
      status: 'pending' as const, text: '', blocks: [], citations: [], runId: 'run-1',
      supersedesMessageId: null,
      meta: { roleId: 'role-1', roleType: 'fictional_composite', timeAnchor: null, followUpQuestions: [], phase: null, memorySummary: null },
      createdAt: '2026-11-04T00:00:00Z',
    };
    const block = { blockIndex: 0, type: 'opinion' as const, text: '先显示这一段。', evidenceIds: [] };

    const partial = applyRunEventToMessages([pending], {
      seq: 2, event: 'answer.block', data: { messageId: 'message-1', block, citations: [] },
    });
    expect(partial[0]).toMatchObject({ status: 'partial', text: '先显示这一段。', blocks: [block] });

    const complete = applyRunEventToMessages(partial, {
      seq: 3, event: 'run.completed', data: { messageId: 'message-1' },
    });
    expect(complete[0]?.status).toBe('complete');
  });

  it('ignores heartbeat comments', () => {
    expect(parseSseChunk('', ': heartbeat\n\n').events).toEqual([]);
  });
});
