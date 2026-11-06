import { ArrowRightOutlined, CheckOutlined, FileTextOutlined, SendOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Modal, Spin, message as antMessage } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  applyRunEventToMessages,
  cancelRun,
  getMessages,
  getRoleSession,
  retryRun,
  sendDialogueMessage,
  streamRunEvents,
  uniqueMessageSources,
} from '../api/dialogue';
import type { MessageView, RoleSessionView, RunEvent } from '../api/dialogue';
import {
  addReportCorrection,
  createStudentSession,
  createNote,
  deleteNote,
  endSession,
  ensureLearningReport,
  getLearningReport,
  listRealTasks,
  listNotes,
  recordLearningEvent,
  retryLearningReport,
} from '../api/p5';
import type { LearningReport, NoteView, ReportEnvelope, TaskListItem } from '../api/p5';
import { StreamingAnswer } from '../components/StreamingAnswer';
import { useAuth } from '../auth/useAuth';

const stanceOptions = [
  ['need_more_evidence', '需要更多证据'],
  ['agree_for_now', '暂时赞同'],
  ['alternative_explanation', '有不同解释'],
] as const;

export function StudentTasksPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [opening, setOpening] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    void listRealTasks(controller.signal).then(result => setTasks(result.data.items)).catch(caught => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '无法读取任务。');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  async function enter(task: TaskListItem) {
    if (!session?.csrfToken || opening) return;
    setOpening(task.taskId);
    try {
      const created = await createStudentSession(task.taskId, session.csrfToken);
      navigate(`/student/sessions/${created.data.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法进入任务。');
    } finally { setOpening(''); }
  }
  if (loading) return <div className="loading-state"><Spin /> 正在读取可参与任务…</div>;
  return <><div className="page-heading"><div><h1>带着好奇，开始一场探究。</h1><p>与一个角色相遇，用问题打开情境，用证据形成自己的判断。</p></div></div>
    {error && <Alert type="error" showIcon message={error} className="spaced-bottom" />}
    <div className="task-grid">{tasks.map(task => <article className="card task-card" key={task.taskId}><div className="task-body"><span className="badge">已发布</span><h3>{task.topicName || '未命名探究任务'}</h3><p>从一个角色的有限视角展开探究；报告只整理你实际表达的内容。</p><div className="task-bottom"><small>可以继续已有会话，也可以进入当前发布版本。</small><Button type="primary" loading={opening === task.taskId} onClick={() => void enter(task)}>进入探究 <ArrowRightOutlined /></Button></div></div></article>)}</div>
    {!tasks.length && <div className="card empty"><Empty description="当前账号暂无可参与任务。" /></div>}
    <div className="tip">不必急于找到答案。说说你的想法，也可以坦白还不确定。</div></>;
}

export function StudentSessionPage({ submission = false }: { submission?: boolean }) {
  const { sessionId = '' } = useParams();
  return submission ? <RealLearningReport sessionId={sessionId} /> : <RealInquirySession sessionId={sessionId} />;
}

function RealInquirySession({ sessionId }: { sessionId: string }) {
  const { session: auth } = useAuth();
  const [roleSession, setRoleSession] = useState<RoleSessionView | null>(null);
  const [messages, setMessages] = useState<MessageView[]>([]);
  const [input, setInput] = useState('');
  const [runId, setRunId] = useState('');
  const [lastFailedRun, setLastFailedRun] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [finishOpen, setFinishOpen] = useState(false);
  const [stanceVersions, setStanceVersions] = useState<Record<string, number>>({});
  const [saved, setSaved] = useState<Record<string, NoteView>>({});
  const [feedback, contextHolder] = antMessage.useMessage();
  const cursor = useRef(0);
  const transcript = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const [current, page, notes] = await Promise.all([getRoleSession(sessionId), getMessages(sessionId), listNotes(sessionId)]);
    setRoleSession(current.data); setMessages(page.data.items);
    setSaved(Object.fromEntries(notes.data.items.map(item => [`${item.messageId}:${item.blockIndex}`, item])));
  }, [sessionId]);
  useEffect(() => {
    const controller = new AbortController();
    void refresh().catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '无法读取会话。'); });
    return () => controller.abort();
  }, [refresh]);
  useEffect(() => { transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: 'smooth' }); }, [messages, status]);
  const onEvent = useCallback((event: RunEvent) => {
    if (event.event === 'answer.block' || event.event === 'answer.meta' || event.event === 'run.completed') {
      setMessages(current => applyRunEventToMessages(current, event));
    }
    if (event.event === 'answer.block') setStatus('正在回答');
    if (event.event === 'run.completed') { setStatus(''); setRunId(''); setLastFailedRun(''); }
    if (event.event === 'run.failed' || event.event === 'run.cancelled') {
      setStatus(event.event === 'run.cancelled' ? '回答已停止，问题仍然保留。' : '回答未能完成。');
      setLastFailedRun(typeof event.data.runId === 'string' ? event.data.runId : runId); setRunId('');
    }
  }, [runId]);
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    void streamRunEvents(runId, cursor.current, onEvent, controller.signal).then(async value => {
      cursor.current = value; await refresh();
    }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '回答事件流已断开。'); });
    return () => controller.abort();
  }, [onEvent, refresh, runId]);

  async function send(question = input) {
    if (!auth?.csrfToken || !question.trim() || runId || roleSession?.status !== 'active') return;
    try {
      setStatus('正在准备回答');
      const started = await sendDialogueMessage(sessionId, question.trim(), auth.csrfToken);
      setInput(''); setLastFailedRun(''); cursor.current = 0; setRunId(started.data.runId); await refresh();
    } catch (caught) { setStatus(''); setError(caught instanceof Error ? caught.message : '无法发送消息。'); }
  }
  async function stop() {
    if (!auth?.csrfToken || !runId) return;
    try { await cancelRun(runId, auth.csrfToken); setLastFailedRun(runId); setRunId(''); setStatus('回答已停止，问题仍然保留。'); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法停止回答。'); }
  }
  async function retry() {
    if (!auth?.csrfToken || !lastFailedRun) return;
    try { const started = await retryRun(lastFailedRun, auth.csrfToken); cursor.current = 0; setRunId(started.data.id); setLastFailedRun(''); setStatus('正在准备回答'); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法重试回答。'); }
  }
  async function setStance(messageId: string, value: string) {
    if (!auth?.csrfToken || roleSession?.status !== 'active') return;
    try {
      const result = await recordLearningEvent(sessionId, { type: 'stance', messageId, value, expectedRowVersion: stanceVersions[messageId] ?? 0 }, auth.csrfToken);
      setStanceVersions(current => ({ ...current, [messageId]: result.data.rowVersion }));
      void feedback.success('已记录当前选择。');
    } catch (caught) { setError(caught instanceof Error ? caught.message : '无法记录选择。'); }
  }
  async function toggleSaved(message: MessageView) {
    if (!auth?.csrfToken || roleSession?.status !== 'active' || !message.blocks.length) return;
    const key = `${message.id}:0`;
    try {
      const existing = saved[key];
      if (existing) await deleteNote(existing.id, existing.rowVersion, auth.csrfToken);
      else await createNote(sessionId, message.id, 0, auth.csrfToken);
      await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : '无法更新收藏。'); }
  }
  async function end() {
    if (!auth?.csrfToken) return;
    try { await endSession(sessionId, auth.csrfToken); setFinishOpen(false); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法结束探究。'); }
  }
  if (!roleSession) return <div className="loading-state">{error || '正在读取探究会话…'}</div>;
  const active = roleSession.status === 'active';
  return <>{contextHolder}<div className="page-heading"><div><h1 className="serif">与 {roleSession.publicRole.name} 的探究</h1><p>从一个人的处境，看见时代的一角。</p></div><div className="row"><Link className="btn" to={`/student/sessions/${sessionId}/submission`}>我的学习报告</Link><Button type="primary" disabled={!active || !!runId || !messages.some(item => item.speaker === 'user')} onClick={() => setFinishOpen(true)}>结束探究 <ArrowRightOutlined /></Button></div></div>
    {error && <Alert type="error" showIcon message={error} className="spaced-bottom" />}
    {!active && <div className="notice spaced"><CheckOutlined /> 这次探究已经结束。对话为只读，仍可查看和补充学习报告。</div>}
    <div className="mobile-role notice"><strong>{roleSession.publicRole.name}</strong> · {roleSession.publicRole.roleType === 'real_historical' ? '真实历史人物' : '虚拟综合角色'}<br />AI 模拟角色，不代表人物本人真实言论。</div>
    <div className="chat-grid"><aside className="role-aside"><div className="role-card"><div className="seal">{roleSession.publicRole.name.slice(0, 1)}</div><h3>{roleSession.publicRole.name}</h3><span className="badge">AI 模拟角色</span><p className="spaced">{roleSession.publicRole.identityDescription}</p><div className="boundaries">角色只依据会话快照与已核验来源回答；无法确认时会明确说明。</div></div></aside>
      <section className="chat-column"><div className="chat-toolbar"><span>与 {roleSession.publicRole.name} 的探究对话</span><span>{roleSession.completedTurns} 轮</span></div><div className="transcript" ref={transcript}><article className="message"><span className="avatar">{roleSession.publicRole.name.slice(0, 1)}</span><div className="message-body"><div className="message-author">{roleSession.publicRole.name}<span className="badge gray">AI 模拟</span></div><div className="bubble"><p>{roleSession.publicRole.openingMessage}</p></div></div></article>
        {messages.map(item => <article key={item.id} className={`message ${item.speaker === 'user' ? 'user' : ''}`}><span className="avatar">{item.speaker === 'user' ? '我' : roleSession.publicRole.name.slice(0, 1)}</span><div className="message-body"><div className="message-author">{item.speaker === 'user' ? '我' : roleSession.publicRole.name}</div><div className="bubble">{item.blocks.length ? <><StreamingAnswer blocks={item.blocks} streaming={item.speaker === 'assistant' && item.runId === runId} />{uniqueMessageSources(item).length > 0 && <div className="citations"><small>参考资料</small>{uniqueMessageSources(item).map(citation => <Link key={citation.sourceId} className="citation" target="_blank" to={`/sources/view?evidenceId=${encodeURIComponent(citation.evidenceId)}&sessionId=${encodeURIComponent(sessionId)}`}><FileTextOutlined /> {citation.fileName}</Link>)}</div>}</> : <p>{item.text || '正在准备回答…'}</p>}{item.status === 'partial' && <small className="muted">这次回答未完整完成</small>}</div>
          {item.speaker === 'assistant' && item.status === 'complete' && <><div className="message-actions"><button className="link" disabled={!active || !item.blocks.length} onClick={() => void toggleSaved(item)}>{saved[`${item.id}:0`] ? <StarFilled /> : <StarOutlined />} {saved[`${item.id}:0`] ? '已收藏' : '收藏这段话'}</button></div><div className="thinking-prompt"><p>读完这段话，你现在的想法是？</p><div className="row">{stanceOptions.map(([value, label]) => <button className="chip" disabled={!active} key={value} onClick={() => void setStance(item.id, value)}>{label}</button>)}</div><small>选不选都可以。更重要的是，在对话里说说你的理由。</small></div></>}
        </div></article>)}{status && <div className="answer-pending" role="status">{status}</div>}</div>
        <div className="chat-compose"><div className="suggestions">{roleSession.publicRole.recommendedQuestions.map(question => <button key={question} disabled={!active || !!runId} onClick={() => void send(question)}>{question}</button>)}</div><div className="composer"><Input.TextArea value={input} onChange={event => setInput(event.target.value)} disabled={!active || !!runId} placeholder={active ? '说说你的问题或想法，接着追问…' : '探究已结束，对话为只读。'} autoSize={{ minRows: 2, maxRows: 6 }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} /><div className="compose-bottom"><small>Enter 发送 · Shift + Enter 换行</small>{runId ? <Button onClick={() => void stop()}>停止回答</Button> : <Button type="primary" icon={<SendOutlined />} disabled={!active || !input.trim()} onClick={() => void send()}>发送</Button>}</div></div>{lastFailedRun && <div className="run-status"><span>问题已保留。</span><button className="link" onClick={() => void retry()}>重试回答</button></div>}</div>
      </section><aside className="right-column"><div className="card learning-trail"><h3>我的探究</h3><p className="small muted">学习报告会随对话更新，不阻塞继续提问。</p><div className="trail-metrics"><div><strong>{messages.filter(item => item.speaker === 'user').length}</strong><small>次表达</small></div><div><strong>{roleSession.completedTurns}</strong><small>轮完成</small></div><div><strong>{Object.keys(saved).length}</strong><small>条收藏</small></div></div><Link className="link spaced" to={`/student/sessions/${sessionId}/submission`}>查看我的学习报告 <ArrowRightOutlined /></Link></div></aside></div>
    <Modal title="结束这次探究？" open={finishOpen} onCancel={() => setFinishOpen(false)} onOk={() => void end()} okText="结束并整理报告" cancelText="继续思考"><p>结束后不能继续提问或修改学习事件，但仍可在报告中追加补充与更正。</p></Modal></>;
}

function RealLearningReport({ sessionId }: { sessionId: string }) {
  const { session: auth } = useAuth();
  const [envelope, setEnvelope] = useState<ReportEnvelope | null>(null);
  const [error, setError] = useState('');
  const [correction, setCorrection] = useState('');
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const load = useCallback(async () => {
    const result = await getLearningReport(sessionId); setEnvelope(result.data);
  }, [sessionId]);
  useEffect(() => {
    const controller = new AbortController();
    void load().catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '无法读取报告。'); });
    return () => controller.abort();
  }, [load]);
  useEffect(() => {
    if (envelope?.freshness !== 'updating') return;
    const timer = window.setInterval(() => void load(), 1200);
    return () => window.clearInterval(timer);
  }, [envelope?.freshness, load]);
  async function ensure() {
    if (!auth?.csrfToken) return;
    setWorking(true);
    try { await ensureLearningReport(sessionId, auth.csrfToken); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法整理报告。'); }
    finally { setWorking(false); }
  }
  async function retry() {
    if (!auth?.csrfToken || !envelope?.currentReport) return;
    setWorking(true);
    try { await retryLearningReport(envelope.currentReport.id, auth.csrfToken); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法重试报告。'); }
    finally { setWorking(false); }
  }
  async function saveCorrection() {
    const report = envelope?.latestReadyReport;
    if (!auth?.csrfToken || !report || !correction.trim()) return;
    try { await addReportCorrection(sessionId, report.id, correction.trim(), auth.csrfToken); setCorrection(''); setCorrectionOpen(false); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法保存补充。'); }
  }
  if (!envelope) return <div className="loading-state">{error || '正在读取学习报告…'}</div>;
  const report: LearningReport | null = envelope.currentReport?.status === 'ready' ? envelope.currentReport : envelope.latestReadyReport;
  const content = report?.content;
  const metrics = report?.metrics;
  return <><div className="page-heading"><div><h1>我的学习报告</h1><p>根据探究对话整理；未表达的内容不会被补写。</p></div><div className="row"><Link className="btn" to={`/student/sessions/${sessionId}`}>返回对话</Link>{envelope.freshness === 'failed' && <Button loading={working} onClick={() => void retry()}>重试整理</Button>}</div></div>
    {error && <Alert type="error" showIcon message={error} className="spaced-bottom" />}
    {envelope.freshness === 'empty' && <div className="card empty"><Empty description="已有表达后，系统会整理学习报告。" /><Button loading={working} onClick={() => void ensure()}>刷新报告</Button></div>}
    {envelope.freshness === 'updating' && <div className="notice spaced">正在整理最新报告。你仍可查看上一份有效结果。</div>}
    {content && <><section className="learning-report-hero"><div><p className="small">自动整理 · {envelope.sessionStatus === 'ended' ? '探究已结束' : '探究中'}</p><h2>这次探究的摘要</h2><p>{content.summary.text}</p>{content.missingAspects.map(item => <p className="small muted" key={item}>{item}</p>)}</div><div className="report-turns"><strong>{metrics?.expressionCount ?? 0}</strong><span>次表达</span></div></section>
      <div className="report-content-grid spaced"><section className="card"><h3>探究过程</h3><dl><div><dt>寻找依据</dt><dd>{metrics?.evidenceSeekingCount ?? '整理中'}</dd></div><div><dt>查阅资料</dt><dd>{metrics?.sourceViewCount ?? '未记录'}</dd></div><div><dt>作出判断</dt><dd>{metrics?.judgmentCount ?? '整理中'}</dd></div><div><dt>反思修正</dt><dd>{metrics?.reflectionCount ?? '整理中'}</dd></div></dl><p className="small muted">次数不代表成绩或能力。</p></section><section className="card"><h3>下一步可以这样探索</h3>{content.nextSteps.map(item => <p key={item}>{item}</p>)}</section></div>
      <details className="advanced-panel spaced"><summary>查看已整理的表达与依据</summary>{content.findings.map((item, index) => <blockquote key={`${item.kind}-${index}`}><p>{item.text}</p><small className="muted">{item.kind === 'role_view' ? '角色看法，不是学生结论' : '来自学生已表达内容'}</small></blockquote>)}</details></>}
    {!!envelope.corrections.length && <section className="card spaced"><h3>我的补充与更正</h3>{envelope.corrections.map(item => <blockquote key={item.id}>{item.text}</blockquote>)}</section>}
    {report && <div className="section-bar spaced"><span className="small muted">补充只追加，不覆盖原话和报告。</span><Button onClick={() => setCorrectionOpen(true)}>有一处想补充或更正</Button></div>}
    <Modal title="补充或更正学习报告" open={correctionOpen} onCancel={() => setCorrectionOpen(false)} onOk={() => void saveCorrection()} okButtonProps={{ disabled: !correction.trim() }}><Input.TextArea maxLength={2000} showCount autoSize={{ minRows: 4, maxRows: 10 }} value={correction} onChange={event => setCorrection(event.target.value)} /></Modal></>;
}
