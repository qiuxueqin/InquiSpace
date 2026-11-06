import { FileTextOutlined, SendOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { StreamingAnswer } from './StreamingAnswer';
import {
  applyRunEventToMessages,
  cancelRun,
  createPreviewSession,
  getDialogueRun,
  getMessages,
  retryRun,
  sendDialogueMessage,
  startSummary,
  streamRunEvents,
  uniqueMessageSources,
} from '../api/dialogue';
import type { MessageView, RoleSessionView, RunEvent } from '../api/dialogue';

export function DialoguePanel({
  versionId,
  revision,
  csrfToken,
}: {
  versionId: string;
  revision: number;
  csrfToken: string;
}) {
  const [roleSession, setRoleSession] = useState<RoleSessionView | null>(null);
  const [messages, setMessages] = useState<MessageView[]>([]);
  const [input, setInput] = useState('');
  const [runId, setRunId] = useState('');
  const [lastFailedRun, setLastFailedRun] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const eventCursor = useRef(0);

  const refreshMessages = useCallback(async (sessionId: string) => {
    const result = await getMessages(sessionId);
    setMessages(result.data.items);
  }, []);

  const handleEvent = useCallback((event: RunEvent) => {
    if (event.event === 'answer.block' || event.event === 'answer.meta' || event.event === 'run.completed') {
      setMessages(current => applyRunEventToMessages(current, event));
    }
    if (event.event === 'run.progress') {
      setStatus(typeof event.data.displayMessage === 'string' ? event.data.displayMessage : '正在回答');
    } else if (event.event === 'answer.block') {
      setStatus('正在回答');
    } else if (event.event === 'run.failed' || event.event === 'run.cancelled') {
      setLastFailedRun(typeof event.data.runId === 'string' ? event.data.runId : runId);
      setStatus(event.event === 'run.cancelled' ? '回答已停止，问题仍然保留。' : '回答未能完成。');
      setRunId('');
    } else if (event.event === 'run.completed') {
      setStatus('');
      setLastFailedRun('');
      setRunId('');
    }
  }, [runId]);

  useEffect(() => {
    if (!runId || !roleSession) return;
    const controller = new AbortController();
    void streamRunEvents(runId, eventCursor.current, handleEvent, controller.signal)
      .then(async cursor => {
        eventCursor.current = cursor;
        await refreshMessages(roleSession.id);
        const run = await getDialogueRun(runId);
        if (run.data.status === 'failed' || run.data.status === 'cancelled') {
          setLastFailedRun(runId);
          setStatus(run.data.status === 'cancelled' ? '回答已停止，问题仍然保留。' : run.data.error?.message ?? '回答未能完成。');
        }
        setRunId('');
      })
      .catch(caught => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '事件流已断开。');
      });
    return () => controller.abort();
  }, [handleEvent, refreshMessages, roleSession, runId]);

  async function openPreview() {
    if (starting) return;
    setStarting(true);
    setError('');
    try {
      const created = await createPreviewSession(versionId, revision, csrfToken);
      setRoleSession(created.data);
      setMessages([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法开始试聊。');
    } finally {
      setStarting(false);
    }
  }

  async function send(content = input) {
    if (!roleSession || !content.trim() || runId) return;
    setError('');
    setStatus('正在准备回答');
    try {
      const started = await sendDialogueMessage(roleSession.id, content.trim(), csrfToken);
      setInput('');
      setLastFailedRun('');
      eventCursor.current = 0;
      setRunId(started.data.runId);
      await refreshMessages(roleSession.id);
    } catch (caught) {
      setStatus('');
      setError(caught instanceof Error ? caught.message : '无法发送消息。');
    }
  }

  async function stop() {
    if (!runId) return;
    try {
      await cancelRun(runId, csrfToken);
      setLastFailedRun(runId);
      setRunId('');
      setStatus('回答已停止，问题仍然保留。');
      if (roleSession) await refreshMessages(roleSession.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法停止回答。');
    }
  }

  async function retry() {
    if (!lastFailedRun || runId) return;
    try {
      const started = await retryRun(lastFailedRun, csrfToken);
      eventCursor.current = 0;
      setRunId(started.data.id);
      setStatus('正在准备回答');
      setLastFailedRun('');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法重试回答。');
    }
  }

  async function summarize() {
    if (!roleSession || runId) return;
    try {
      const started = await startSummary(roleSession.id, csrfToken);
      eventCursor.current = 0;
      setRunId(started.data.id);
      setStatus('正在整理阶段小结');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法整理阶段小结。');
    }
  }

  if (!roleSession) return <div className="free-preview-row"><div><p>试聊使用当前草稿快照，不计入学生学习统计。</p>{error && <Alert type="error" showIcon message={error} />}</div><Button loading={starting} onClick={() => void openPreview()}>开始试聊</Button></div>;

  return <div className="preview-dialogue">
    {error && <Alert className="spaced-bottom" type="error" showIcon message={error} />}
    <div className="chat-toolbar"><span>与 {roleSession.publicRole.name} 试聊</span><span>{roleSession.completedTurns} 轮</span></div>
    <div className="preview-transcript">
      {!messages.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={roleSession.publicRole.openingMessage} />}
      {messages.map(message => <article key={message.id} className={`message ${message.speaker === 'user' ? 'user' : ''}`}>
        <div className="message-body"><div className="message-author">{message.speaker === 'user' ? '我' : roleSession.publicRole.name}</div>
          <div className="bubble">{message.blocks.length ? <><StreamingAnswer blocks={message.blocks} streaming={message.speaker === 'assistant' && message.runId === runId} />{uniqueMessageSources(message).length > 0 && <div className="citations"><small>参考资料</small>{uniqueMessageSources(message).map(citation => <Link className="citation" key={citation.sourceId} to={`/sources/view?evidenceId=${encodeURIComponent(citation.evidenceId)}`} target="_blank"><FileTextOutlined /> {citation.fileName}</Link>)}</div>}</> : <p>{message.text || '正在准备回答…'}</p>}{message.status === 'partial' && <small className="muted">这次回答未完整完成</small>}</div>
          {message.meta.followUpQuestions.map(question => <button className="chip" key={question} disabled={!!runId} onClick={() => void send(question)}>{question}</button>)}
        </div>
      </article>)}
      {status && <div className="run-status" role="status">{status}</div>}
    </div>
    <div className="composer"><Input.TextArea value={input} onChange={event => setInput(event.target.value)} placeholder="输入一个试聊问题…" disabled={!!runId} autoSize={{ minRows: 2, maxRows: 5 }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} /><div className="compose-bottom"><Button disabled={!messages.length || !!runId} onClick={() => void summarize()}>整理阶段小结</Button>{runId ? <Button onClick={() => void stop()}>停止回答</Button> : <Button type="primary" icon={<SendOutlined />} disabled={!input.trim()} onClick={() => void send()}>发送</Button>}</div></div>
    {lastFailedRun && !runId && <div className="run-status"><span>问题已保留。</span><button className="link" onClick={() => void retry()}>重试回答</button></div>}
  </div>;
}
