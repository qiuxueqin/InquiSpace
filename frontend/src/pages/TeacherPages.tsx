import { ArrowRightOutlined, FileTextOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Empty, Input, InputNumber, Modal, Select, message } from 'antd';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiClientError } from '../api/client';
import { createConfirmation, saveRoleCard, startPlanGeneration, undoPlanGeneration, waitForRun } from '../api/p3';
import { planFromVersion, roleInputFromPlan, versionPatchFromPlan } from '../api/p3Mapping';
import { detachSource, getParseRun, getSource, listSources, uploadSource } from '../api/materials';
import type { SourceView } from '../api/materials';
import { createTaskDraftWithIntent, getTask, getVersion, patchVersion } from '../api/tasks';
import { useAuth } from '../auth/useAuth';
import { useWorkspace } from '../demo/useWorkspace';
import { createTask, defaultPlan } from '../demo/model';
import type { Plan, Task } from '../demo/model';
import { TeacherReportPage } from './ReportPages';
import { TasksPage } from './TasksPage';
import { WorkflowProgress } from '../components/WorkflowProgress';
import type { WorkflowProgressState } from '../components/WorkflowProgress';

const subjects = [
  '语文', '数学', '英语',
  '历史', '地理', '道德与法治',
  '物理', '化学', '生物',
  '科学', '信息科技', '艺术',
];

const grades = [
  '一年级', '二年级', '三年级',
  '四年级', '五年级', '六年级',
  '七年级', '八年级', '九年级',
  '高一年级', '高二年级', '高三年级',
];

async function sha256(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
export function TeacherTasksPage() { return <TasksPage />; }
function Field({ label, children, full = false }: { label: string; children: ReactNode; full?: boolean }) { return <label className={`field ${full ? 'full' : ''}`}><span>{label}</span>{children}</label>; }

export function TeacherTaskPage({ mode }: { mode: 'new' | 'edit' | 'preview' | 'report' }) {
  const { taskId } = useParams();
  const { state } = useWorkspace();
  const [freshTask] = useState(() => createTask());
  const task = mode === 'new' ? freshTask : state.tasks.find(item => item.id === taskId);
  if (!task && mode === 'report' && taskId) return <TeacherReportPage key={taskId} taskId={taskId} />;
  if (!task) return <div className="card empty"><Empty description="找不到这项本地任务。请返回任务列表选择。" /><Link className="btn primary spaced" to="/teacher/tasks">返回任务列表</Link></div>;
  if (mode === 'report') {
    const backendTaskId = task.backendTaskId;
    return backendTaskId ? <TeacherReportPage key={backendTaskId} taskId={backendTaskId} /> : <div className="card empty"><Empty description="该任务尚未保存到后端，暂无教学报告。" /></div>;
  }
  return <TaskEditor key={`${task.id}-${mode}`} task={task} isNew={mode === 'new'} />;
}

function TaskEditor({ task, isNew }: { task: Task; isNew: boolean }) {
  const { setState, updateTask } = useWorkspace();
  const [plan, setPlan] = useState(() => structuredClone(task.draft));
  const [tab, setTab] = useState('brief');
  const [advanced, setAdvanced] = useState(false);
  const [saved, setSaved] = useState(false);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [previousPlan, setPreviousPlan] = useState<Plan | null>(null);
  const [feedback, contextHolder] = message.useMessage();
  const { session } = useAuth();
  const uploading = useRef(false);
  const remoteTask = useRef<Task | null>(task.backendTaskId && task.backendDraftVersionId ? task : null);
  const [readingFiles, setReadingFiles] = useState(false);
  const [remoteVersion, setRemoteVersion] = useState<{ id: string; revision: number } | null>(null);
  const [remoteSources, setRemoteSources] = useState<SourceView[]>([]);
  const [sourceNotice, setSourceNotice] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<WorkflowProgressState | null>(null);
  const [generationNotice, setGenerationNotice] = useState<{
    state: 'working' | 'success' | 'error';
    text: string;
  } | null>(null);
  const [undoRunId, setUndoRunId] = useState(task.lastPlanRunId ?? '');
  const navigate = useNavigate();
  const readOnly = !isNew && !task.editing;
  function storeLocalTask(next: Task) {
    setState(previous => {
      let replaced = false;
      const tasks = previous.tasks.flatMap(current => {
        if (current.id !== next.id) return [current];
        if (replaced) return [];
        replaced = true;
        return [next];
      });
      if (!replaced) tasks.push(next);
      return { ...previous, selectedTaskId: next.id, tasks };
    });
  }
  useEffect(() => {
    if (isNew || session?.user.role !== 'teacher') return;
    const controller = new AbortController();
    void (async () => {
      try {
        let versionId = task.backendDraftVersionId;
        if (!versionId && task.backendTaskId) {
          const taskResult = await getTask(task.backendTaskId, controller.signal);
          versionId = taskResult.data.draftVersionId ?? undefined;
        }
        if (!versionId) {
          setSourceNotice('当前任务还没有后端草稿；保存草稿后即可上传参考资料。');
          return;
        }
        const version = await getVersion(versionId, controller.signal);
        if (version.data.status !== 'draft') {
          setSourceNotice('当前后端版本不是草稿，参考资料保持只读。');
          return;
        }
        setRemoteVersion({ id: version.data.id, revision: version.data.revision });
        setPlan(current => planFromVersion(version.data, current));
        updateTask(task.id, current => ({
          ...current,
          draft: planFromVersion(version.data, current.draft),
          backendDraftRevision: version.data.revision,
        }));
        const sources = await listSources(version.data.id, controller.signal);
        setRemoteSources(sources.data);
        setSourceNotice('参考资料将保存到后端草稿。PDF 和 UTF-8 TXT 会在隔离进程中解析。');
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiClientError && error.status === 404) {
          setSourceNotice('对应的后端草稿不存在或已不可访问。请重新保存草稿后再上传。');
        } else {
          setSourceNotice(error instanceof Error ? `暂时无法连接资料服务：${error.message}` : '暂时无法连接资料服务。');
        }
      }
    })();
    return () => controller.abort();
  }, [isNew, session?.user.role, task.backendDraftVersionId, task.backendTaskId, task.id, updateTask]);
  function patch<K extends keyof Plan>(key: K, value: Plan[K]) { setPlan(previous => ({ ...previous, [key]: value })); setSaved(false); }
  async function ensureRemoteDraft(current: Plan): Promise<{ task: Task; versionId: string; revision: number }> {
    if (!session?.csrfToken) throw new Error('登录状态已失效，请重新登录。');
    if (remoteVersion && remoteTask.current) {
      return { task: remoteTask.current, versionId: remoteVersion.id, revision: remoteVersion.revision };
    }
    const created = await createTaskDraftWithIntent(session.csrfToken, {
      teachingIntent: current.intent,
      brief: { subject: current.subject, grade: current.grade },
    });
    const next = {
      ...task,
      backendTaskId: created.data.taskId,
      backendDraftVersionId: created.data.draft.id,
      backendDraftRevision: created.data.draft.revision,
      backendTaskRevision: created.data.taskRevision,
    };
    remoteTask.current = next;
    setRemoteVersion({ id: created.data.draft.id, revision: created.data.draft.revision });
    setSourceNotice('参考资料将保存到后端草稿。PDF 和 UTF-8 TXT 会在隔离进程中解析。');
    return { task: next, versionId: created.data.draft.id, revision: created.data.draft.revision };
  }
  async function save(preview = false) {
    if (readingFiles || generating) return;
    if (readOnly) { navigate(`/teacher/tasks/${task.id}/preview`); return; }
    let next: Task = { ...task, draft: structuredClone(plan), updatedAt: new Date().toISOString() };
    try {
      const remote = await ensureRemoteDraft(plan);
      let latest = (await patchVersion(remote.versionId, remote.revision, session!.csrfToken, versionPatchFromPlan(plan))).data;
      if (plan.roleName.trim() && plan.identity.trim() && plan.opening.trim() && plan.questions.some(Boolean)) {
        await saveRoleCard(
          remote.versionId,
          latest.revision,
          session!.csrfToken,
          roleInputFromPlan(plan, latest),
        );
        latest = (await getVersion(remote.versionId)).data;
      }
      next = {
        ...remote.task,
        draft: structuredClone(plan),
        backendDraftRevision: latest.revision,
        updatedAt: new Date().toISOString(),
      };
      setRemoteVersion({ id: latest.id, revision: latest.revision });
    } catch (error) {
      void feedback.error(error instanceof Error ? `后端草稿保存失败：${error.message}` : '后端草稿保存失败。');
      return;
    }
    if (isNew) storeLocalTask(next);
    else updateTask(task.id, () => next);
    setSaved(true);
    if (preview || isNew) navigate(`/teacher/tasks/${task.id}/${preview ? 'preview' : 'edit'}`);
    void feedback.success('草稿已保存到后端。');
  }
  async function generate() {
    if (!session?.csrfToken || generating || readingFiles) return;
    setGenerating(true);
    setGenerationProgress({
      title: '保存教学意图',
      detail: '正在保存当前输入，并固定本次生成所用的资料范围。',
      percent: 8,
      ceiling: 22,
      status: 'active',
    });
    setGenerationNotice({ state: 'working', text: '正在根据教学意图与资料生成方案，请不要关闭页面。' });
    setReplaceOpen(false);
    setPreviousPlan(structuredClone(plan));
    try {
      const remote = await ensureRemoteDraft(plan);
      const saved = await patchVersion(remote.versionId, remote.revision, session.csrfToken, {
        teachingIntent: plan.intent,
        brief: { subject: plan.subject, grade: plan.grade },
      });
      setGenerationProgress({
        title: '生成教学方案',
        detail: '模型正在结合教学意图、默认课堂设置和当前可引用资料生成主题、角色与问题链。',
        percent: 25,
        ceiling: 72,
        status: 'active',
      });
      let revision = saved.data.revision;
      setRemoteVersion({ id: remote.versionId, revision });
      let confirmationId: string | undefined;
      const overwrittenFields = saved.data.manualFields.filter(field =>
        field === 'roleCard' || field === 'questionPlan' || field.startsWith('brief.'),
      );
      if (overwrittenFields.length) {
        const confirmed = await createConfirmation(
          remote.versionId,
          revision,
          session.csrfToken,
          remote.task.backendTaskRevision ?? 1,
          {
            action: 'replace_plan',
            payload: {
              intentHash: await sha256(plan.intent),
              overwrittenFields,
            },
          },
        );
        confirmationId = confirmed.data.confirmationId;
      }
      const started = await startPlanGeneration(
        remote.versionId, revision, session.csrfToken, confirmationId,
      );
      const run = await waitForRun(started.data.id);
      if (run.status !== 'completed') throw new Error(run.error?.message ?? '教学方案生成失败。');
      setGenerationProgress({
        title: '校验并应用结果',
        detail: '正在校验方案结构、资料引用和角色边界，并将合格结果写入当前草稿。',
        percent: 76,
        ceiling: 90,
        status: 'active',
      });
      const requiredQuestions = Array.isArray(run.result?.nextQuestions)
        ? run.result.nextQuestions.filter((item): item is string => typeof item === 'string')
        : [];
      const version = (await getVersion(remote.versionId)).data;
      setGenerationProgress({
        title: '更新编辑页面',
        detail: '正在读取已保存的教学方案，并回填主题、角色、问题链和课堂安排。',
        percent: 92,
        ceiling: 98,
        status: 'active',
      });
      revision = version.revision;
      const nextPlan = planFromVersion(version, plan);
      const nextTask = {
        ...remote.task,
        draft: nextPlan,
        backendDraftRevision: revision,
        lastPlanRunId: run.id,
        updatedAt: new Date().toISOString(),
      };
      setPlan(nextPlan);
      setRemoteVersion({ id: remote.versionId, revision });
      setUndoRunId(run.id);
      remoteTask.current = nextTask;
      if (isNew) storeLocalTask(nextTask);
      else updateTask(task.id, () => nextTask);
      setSaved(true);
      setGenerationProgress({
        title: '教学方案已生成',
        detail: requiredQuestions.length
          ? '安全草稿已保存，请补充页面提示的必要信息。'
          : '主题、角色、问题链和课堂安排已写入当前草稿。',
        percent: 100,
        ceiling: 100,
        status: 'success',
      });
      if (requiredQuestions.length) {
        setAdvanced(true);
        setTab('brief');
        setGenerationNotice({
          state: 'success',
          text: `已生成安全草稿，还需要确认：${requiredQuestions.join('；')}`,
        });
        void feedback.warning('方案草稿已生成，请补充必要信息后重新生成或完善角色。');
      } else {
        setGenerationNotice({ state: 'success', text: '教学方案已生成，请检查角色、问题链和课堂安排。' });
        void feedback.success('教学方案已生成，请检查角色、问题和课堂安排。');
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '教学方案生成失败。';
      setGenerationProgress(current => ({
        title: '教学方案未生成',
        detail,
        percent: current?.percent ?? 0,
        ceiling: current?.ceiling ?? 0,
        status: 'error',
      }));
      if (error instanceof ApiClientError && error.code === 'CONFIRMATION_REQUIRED') {
        setGenerationNotice({ state: 'error', text: '当前方案包含人工编辑，请确认替换范围后重试。' });
        void feedback.warning('当前方案包含人工编辑，请确认替换范围后重试。');
      } else {
        setGenerationNotice({ state: 'error', text: `${detail} 可以点击“重新生成教学方案”再试一次。` });
        void feedback.error(detail);
      }
    } finally {
      setGenerating(false);
    }
  }
  async function undoGeneratedPlan() {
    if (!session?.csrfToken || !remoteVersion || !undoRunId || generating) return;
    setGenerating(true);
    try {
      const restored = await undoPlanGeneration(
        remoteVersion.id, undoRunId, remoteVersion.revision, session.csrfToken,
      );
      const restoredPlan = planFromVersion(restored.data, previousPlan ?? plan);
      setPlan(restoredPlan);
      setRemoteVersion({ id: restored.data.id, revision: restored.data.revision });
      setUndoRunId('');
      setPreviousPlan(null);
      updateTask(task.id, current => {
        const rest = { ...current };
        delete rest.lastPlanRunId;
        return {
          ...rest,
          draft: restoredPlan,
          backendDraftRevision: restored.data.revision,
        };
      });
      void feedback.success('已恢复生成前的方案。');
    } catch (error) {
      void feedback.error(error instanceof Error ? error.message : '当前方案无法撤销。');
    } finally {
      setGenerating(false);
    }
  }
  async function addFiles(files: FileList | null) {
    if (!files || uploading.current) return;
    const selected = Array.from(files);
    if (!remoteVersion || !session?.csrfToken) {
      void feedback.warning(sourceNotice || '请先保存并打开后端草稿，再上传参考资料。');
      return;
    }
    if (selected.length + remoteSources.length > 10) {
      void feedback.warning('每个方案最多添加 10 份资料。');
      return;
    }
    const invalid = selected.find(file => !/\.(pdf|txt)$/i.test(file.name) || file.size > 10 * 1024 * 1024);
    if (invalid) {
      void feedback.warning(!/\.(pdf|txt)$/i.test(invalid.name) ? `${invalid.name} 不是 PDF 或 TXT。` : `${invalid.name} 超过 10 MiB。`);
      return;
    }
    uploading.current = true;
    setReadingFiles(true);
    let revision = remoteVersion.revision;
    try {
      for (const file of selected) {
        const uploaded = await uploadSource(remoteVersion.id, file, revision, session.csrfToken);
        revision = uploaded.data.revision;
        setRemoteVersion(current => current ? { ...current, revision } : current);
        setRemoteSources(current => [...current, uploaded.data.source]);
        const runId = uploaded.data.run.id;
        let run = uploaded.data.run;
        while (run.status === 'running') {
          await new Promise(resolve => setTimeout(resolve, 400));
          run = (await getParseRun(runId)).data;
        }
        const source = (await getSource(uploaded.data.source.id)).data;
        setRemoteSources(current => current.map(item => item.id === source.id ? source : item));
        if (run.status === 'completed') {
          const version = await getVersion(remoteVersion.id);
          revision = version.data.revision;
          setRemoteVersion({ id: remoteVersion.id, revision });
          void feedback.success(`${file.name} 已解析，可用于后续检索与引用。`);
        } else {
          void feedback.error(run.error?.message ?? `${file.name} 解析失败。`);
        }
      }
    } catch (error) {
      if (error instanceof ApiClientError && error.code === 'REVISION_CONFLICT') {
        try {
          const version = await getVersion(remoteVersion.id);
          setRemoteVersion({ id: remoteVersion.id, revision: version.data.revision });
        } catch { /* Keep the original actionable conflict message. */ }
      }
      void feedback.error(error instanceof Error ? error.message : '参考资料上传失败。');
    } finally {
      uploading.current = false;
      setReadingFiles(false);
    }
  }
  async function removeRemoteSource(source: SourceView) {
    if (!remoteVersion || !session?.csrfToken || readingFiles) return;
    setReadingFiles(true);
    try {
      const result = await detachSource(remoteVersion.id, source.id, remoteVersion.revision, session.csrfToken);
      setRemoteVersion({ id: remoteVersion.id, revision: result.data.revision });
      setRemoteSources(current => current.filter(item => item.id !== source.id));
      void feedback.success('已从当前草稿移除参考资料。');
    } catch (error) {
      void feedback.error(error instanceof Error ? error.message : '无法移除参考资料。');
    } finally {
      setReadingFiles(false);
    }
  }
  function example(type: string) {
    patch('intent', type === 'qing' ? defaultPlan().intent : type === 'eco' ? '让学生从湿地观察员的视角探究食物链变化，比较证据并说明生态系统的相互影响。' : '让学生与一个虚拟文学人物对话，理解人物处境，使用文本证据解释不同选择。');
    patch('subject', type === 'eco' ? '生物' : type === 'literature' ? '语文' : '历史');
  }
  return <>{contextHolder}<div className="page-heading"><div><h1>设计一节探究课</h1><p>写下教学想法，准备一场有依据的对话。</p></div><div className="row"><small>{saved ? '已保存在本地' : readOnly ? '已发布 · 只读' : '草稿 · 待保存'}</small><Button disabled={readOnly || readingFiles} onClick={() => void save()}>保存草稿</Button><Button type="primary" disabled={readingFiles} onClick={() => void save(true)}>查看方案 <ArrowRightOutlined /></Button></div></div>
    <div className="notice">{readOnly ? '当前方案已发布，不能直接修改。创建新版草稿后调整，历史学习记录不会被覆盖。' : '草稿内容保存到后端；修改时间、目标、资料或角色后，系统会使旧检查失效。'}{readOnly && <Button className="inline-action" size="small" onClick={() => updateTask(task.id, current => ({ ...current, editing: true }))}>创建新版草稿</Button>}</div>
    <fieldset className="editor-fieldset" disabled={readOnly}>
      <section className="card ai-workbench"><div className="ai-heading"><span className="ai-mark">✦</span><div><div className="eyebrow">DESIGN AN INQUIRY</div><h2>你想让学生探究什么？</h2><p>可以说清主题、希望对话的人物，以及想让学生理解的问题。</p></div><span className="badge gray">AI 方案</span></div>
        <Field label="一句话教学需求" full><Input.TextArea className="intent-input" aria-label="一句话教学需求" value={plan.intent} rows={3} onChange={event => patch('intent', event.target.value)} placeholder="例如：让八年级学生与溥仪对话，理解清朝灭亡时身份与权力的变化，并学会核对依据。" /></Field>
        <div className="intent-examples"><span>试试：</span><button className="chip" onClick={() => example('qing')}>身份与权力</button><button className="chip" onClick={() => example('eco')}>湿地生态</button><button className="chip" onClick={() => example('literature')}>人物与处境</button></div>
        <div className="quick-options"><Field label="学科"><Select aria-label="学科" disabled={readOnly} value={plan.subject} options={subjects.map(value => ({ value }))} onChange={value => patch('subject', value)} /></Field><Field label="年级"><Select aria-label="年级" disabled={readOnly} value={plan.grade} options={grades.map(value => ({ value }))} onChange={value => patch('grade', value)} /></Field><div className="quick-source"><Button icon={<PlusOutlined />} onClick={() => { setAdvanced(true); setTab('sources'); }}>添加参考资料（可选）</Button><small>{remoteSources.length || plan.sources.length} 份资料 · 也可以先不上传</small></div></div>
        <div className="ai-next"><div><p>{generating ? '正在根据教学意图与资料准备方案…' : '生成后请检查角色、问题链和课堂安排；不会自动发布。'}</p>{generationNotice && <div className={`generation-notice ${generationNotice.state}`} role="status" aria-live="polite">{generationNotice.text}</div>}{generationProgress && <WorkflowProgress value={generationProgress} />}</div><Button type="primary" size="large" loading={generating} disabled={readOnly || readingFiles || !plan.intent.trim()} onClick={() => { if (plan.title || plan.roleName) setReplaceOpen(true); else void generate(); }}>{generationNotice?.state === 'error' ? '✦ 重新生成教学方案' : '✦ 生成教学方案'}</Button></div>
        {undoRunId && <div className="small spaced">已保留生成前的草稿。<button className="link" disabled={generating} onClick={() => void undoGeneratedPlan()}>恢复生成前的方案</button></div>}
      </section>
      <details className="advanced-panel" open={advanced} onToggle={event => setAdvanced(event.currentTarget.open)}><summary>更多设置 <span>资料、角色介绍、探究时长</span></summary><div className="editor-tabs" role="tablist" aria-label="任务编辑设置">{[['brief', '主题与目标'], ['sources', '资料与来源'], ['role', '角色介绍'], ['settings', '任务设置']].map(([key, label], index) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key!)}><b>{index + 1}</b>{label}</button>)}</div>
        {tab === 'brief' && <div className="form-grid"><Field label="主题名称 *" full><Input value={plan.title} onChange={event => patch('title', event.target.value)} /></Field><Field label="主题背景 *" full><Input.TextArea rows={3} value={plan.background} onChange={event => patch('background', event.target.value)} /></Field><Field label="核心问题 *" full><Input.TextArea rows={2} value={plan.question} onChange={event => patch('question', event.target.value)} /></Field><Field label="探究目标 *" full><Input.TextArea rows={2} value={plan.goal} onChange={event => patch('goal', event.target.value)} /></Field><Field label="主题类型"><Select disabled={readOnly} value={plan.historical ? 'yes' : 'no'} options={[{ value: 'yes', label: '历史主题' }, { value: 'no', label: '非历史主题' }]} onChange={value => patch('historical', value === 'yes')} /></Field><Field label="故事发生的时间"><Input placeholder="如 1912、1912-02 或 1912-02-12" value={plan.anchor} onChange={event => patch('anchor', event.target.value)} /></Field><Field label="地域范围" full><Input placeholder="如 北京 · 清宫" value={plan.region} onChange={event => patch('region', event.target.value)} /></Field></div>}
        {tab === 'sources' && <div><h2>让每个观点，都有据可查</h2><p className="muted spaced">参考资料可以不上传。没有证据支持的内容，必须明确说明无法确认。</p><label className={`upload spaced ${!remoteVersion ? 'disabled' : ''}`}><UploadOutlined /><strong>{readingFiles ? '正在上传并解析资料…' : '点击选择参考资料'}</strong><span>PDF 或 UTF-8 TXT · 最多 10 份 · 单文件 10 MiB</span><input type="file" accept=".pdf,.txt,application/pdf,text/plain" multiple disabled={readOnly || readingFiles || !remoteVersion} onChange={event => { void addFiles(event.target.files); event.target.value = ''; }} /><span className="small">{remoteVersion ? '文件会保存到当前后端草稿；解析完成后才能用于检索与引用。' : sourceNotice || '请先保存并打开后端草稿。'}</span></label>{remoteSources.map(source => <div className="file-row" key={source.id}><span className="file-icon"><FileTextOutlined /></span><div className="grow"><h3>{source.fileName}</h3><p className="small">{source.status === 'ready' ? `${source.fileType === 'pdf' ? `${source.pageCount ?? 0} 页` : `${source.totalLines ?? 0} 行`} · 已保存到后端` : source.status === 'failed' ? source.parseError?.message ?? '解析失败，请移除后重新上传。' : '正在解析，请稍候…'}</p></div><span className={`badge ${source.status === 'failed' ? 'red' : source.status === 'ready' ? '' : 'amber'}`}>{source.status === 'ready' ? '✓ 可引用' : source.status === 'failed' ? '解析失败' : '解析中'}</span><Button size="small" disabled={readOnly || readingFiles} onClick={() => void removeRemoteSource(source)}>移除</Button></div>)}{plan.sources.filter(source => source.id.startsWith('source-')).map(source => <div className="file-row" key={source.id}><span className="file-icon"><FileTextOutlined /></span><div className="grow"><h3>{source.name}</h3><p className="small">{source.location} · 内置演示材料，未上传到后端</p></div><span className="badge gray">演示</span></div>)}{!remoteSources.length && !plan.sources.some(source => source.id.startsWith('source-')) && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未上传参考资料；可以直接继续设计任务。" />}<div className="notice spaced">学生可以从回答中的引用查看资料原文。参考资料为可选项；没有资料支持时，角色必须明确说明无法确认。</div></div>}
        {tab === 'role' && <div className="form-grid"><Field label="角色名称 *"><Input value={plan.roleName} onChange={event => patch('roleName', event.target.value)} /></Field><Field label="角色类型"><Select disabled={readOnly} value={plan.roleType} options={[{ value: 'historical', label: '真实历史人物' }, { value: 'fictional', label: '虚拟综合角色' }]} onChange={value => patch('roleType', value)} /></Field><Field label="身份与社会位置 *" full><Input.TextArea rows={3} value={plan.identity} onChange={event => patch('identity', event.target.value)} /></Field><Field label="角色边界与局限" full><Input.TextArea rows={3} value={plan.boundary} onChange={event => patch('boundary', event.target.value)} /></Field><Field label="开场情境 *" full><Input.TextArea rows={3} value={plan.opening} onChange={event => patch('opening', event.target.value)} /></Field><Field label="推荐问题（每行一个，最多三个）" full><Input.TextArea rows={3} value={plan.questions.join('\n')} onChange={event => patch('questions', event.target.value.split('\n').slice(0, 3))} /></Field></div>}
        {tab === 'settings' && <div className="form-grid"><Field label="最大对话轮次"><InputNumber min={1} max={30} value={plan.maxTurns} onChange={value => patch('maxTurns', value ?? 20)} /></Field><Field label="建议时长（分钟）"><InputNumber min={5} max={120} value={plan.duration} onChange={value => patch('duration', value ?? 30)} /></Field><Field label="截止时间（可选）" full><input type="datetime-local" className="native-input" value={plan.deadline} onChange={event => patch('deadline', event.target.value)} /></Field><div className="notice full">发布时选择学生并确认教学内容。学习结束后自动整理报告，无需填写长成果表。</div></div>}
      </details>
    </fieldset>
    <Modal title="替换当前教学方案？" open={replaceOpen} onCancel={() => setReplaceOpen(false)} onOk={() => void generate()} okText="确认替换并生成" cancelText="保留当前方案" confirmLoading={generating}><p>AI 将重新生成主题、背景、核心问题、目标、角色介绍与推荐问题。已关联的参考资料不会被移除。</p><p className="muted spaced">替换范围会与当前草稿绑定并由后端确认；生成后可以恢复生成前的方案。</p></Modal>
  </>;
}
