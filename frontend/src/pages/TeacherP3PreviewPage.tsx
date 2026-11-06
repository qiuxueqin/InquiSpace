import { ArrowRightOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Modal, Select, message } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiClientError } from '../api/client';
import { getPublishReadiness, startPreflight, startValidation, waitForRun } from '../api/p3';
import { createPublishConfirmation, publishVersion } from '../api/p5';
import type { PublishReadiness } from '../api/p3';
import { planFromVersion } from '../api/p3Mapping';
import { getTask, getVersion } from '../api/tasks';
import { listStudents } from '../api/auth';
import type { VersionView } from '../api/tasks';
import type { StudentOption } from '../api/auth';
import { DialoguePanel } from '../components/DialoguePanel';
import { WorkflowProgress } from '../components/WorkflowProgress';
import type { WorkflowProgressState } from '../components/WorkflowProgress';
import { useAuth } from '../auth/useAuth';
import { useWorkspace } from '../demo/useWorkspace';

export function TeacherP3PreviewPage() {
  const { taskId = '' } = useParams();
  const { state, updateTask } = useWorkspace();
  const localTask = state.tasks.find(item => item.id === taskId);
  const localTaskId = localTask?.id;
  const backendTaskId = localTask?.backendTaskId;
  const editing = localTask?.editing;
  const versionId = editing
    ? (localTask.backendDraftVersionId ?? localTask.backendPublishedVersionId)
    : (localTask?.backendPublishedVersionId ?? localTask?.backendDraftVersionId);
  const localPlan = localTask?.draft;
  const localPlanRef = useRef(localPlan);
  localPlanRef.current = localPlan;
  const { session } = useAuth();
  const [version, setVersion] = useState<VersionView | null>(null);
  const [readiness, setReadiness] = useState<PublishReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [preparationProgress, setPreparationProgress] = useState<WorkflowProgressState | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [students, setStudents] = useState<StudentOption[]>([]);
  const [studentIds, setStudentIds] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [feedback, contextHolder] = message.useMessage();
  const navigate = useNavigate();

  useEffect(() => {
    if (!localTaskId || !versionId) {
      setLoading(false);
      setError('当前任务还没有后端方案，请先返回设计页保存并生成方案。');
      return;
    }
    const controller = new AbortController();
    void (async () => {
      try {
        const published = !editing;
        const [versionResult, taskResult, readinessResult] = await Promise.all([
          getVersion(versionId, controller.signal),
          backendTaskId ? getTask(backendTaskId, controller.signal) : null,
          published ? null : getPublishReadiness(versionId, controller.signal),
        ]);
        setVersion(versionResult.data);
        setReadiness(readinessResult?.data ?? null);
        const mapped = planFromVersion(versionResult.data, localPlanRef.current!);
        updateTask(localTaskId, current => ({
          ...current,
          draft: mapped,
          ...(published
            ? { backendPublishedVersionId: versionResult.data.id }
            : { backendDraftRevision: versionResult.data.revision }),
          ...(taskResult ? { backendTaskRevision: taskResult.data.taskRevision } : {}),
        }));
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '无法读取教学方案。');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [backendTaskId, editing, localTaskId, updateTask, versionId]);

  async function prepareChecks() {
    if (!version || !session?.csrfToken || preparing) return;
    setPreparing(true);
    setError('');
    setPreparationProgress({
      title: '检查角色一致性',
      detail: '正在检查角色身份、时间边界、资料引用和问题链是否一致。',
      percent: 8,
      ceiling: 45,
      status: 'active',
    });
    try {
      let current = version;
      if (current.validationStatus !== 'valid' || current.validatedRevision !== current.revision) {
        const validation = await startValidation(current.id, current.revision, session.csrfToken);
        const validationRun = await waitForRun(validation.data.id);
        if (validationRun.status !== 'completed') {
          throw new Error(validationRun.error?.message ?? '角色一致性检查失败。');
        }
        current = (await getVersion(current.id)).data;
        setVersion(current);
      }
      setPreparationProgress({
        title: '执行发布前检查',
        detail: '正在检查身份、未来信息、私人动机、观点冲突和提示注入五类风险。',
        percent: 50,
        ceiling: 86,
        status: 'active',
      });
      const preflight = await startPreflight(current.id, current.revision, session.csrfToken);
      const preflightRun = await waitForRun(preflight.data.id);
      if (preflightRun.status !== 'completed') {
        throw new Error(preflightRun.error?.message ?? '方案自动检查失败。');
      }
      setPreparationProgress({
        title: '刷新准备状态',
        detail: '检查已完成，正在汇总可发布状态和需要补充的内容。',
        percent: 90,
        ceiling: 98,
        status: 'active',
      });
      const [latest, status] = await Promise.all([
        getVersion(current.id),
        getPublishReadiness(current.id),
      ]);
      setVersion(latest.data);
      setReadiness(status.data);
      updateTask(localTask!.id, task => ({
        ...task,
        draft: planFromVersion(latest.data, task.draft),
        backendDraftRevision: latest.data.revision,
      }));
      setPreparationProgress({
        title: status.data.ready ? '方案准备完成' : '检查完成，请补充内容',
        detail: status.data.ready
          ? '角色一致性与发布前检查均已通过，可以选择学生并确认发布。'
          : '检查已完成，请根据下方提示修改方案后重新准备。',
        percent: 100,
        ceiling: 100,
        status: status.data.ready ? 'success' : 'error',
      });
      if (status.data.ready) void feedback.success('方案已准备完成。');
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : '方案检查失败。';
      setPreparationProgress(current => ({
        title: '方案准备未完成',
        detail,
        percent: current?.percent ?? 0,
        ceiling: current?.ceiling ?? 0,
        status: 'error',
      }));
      if (caught instanceof ApiClientError && caught.code === 'REVISION_CONFLICT') {
        setError('方案内容已经变化，请重新载入后再检查。');
      } else {
        setError(detail);
      }
    } finally {
      setPreparing(false);
    }
  }

  async function publish() {
    if (!version || !readiness?.ready || !session?.csrfToken || publishing) return;
    setPublishing(true);
    try {
      const roster = students.length ? students : (await listStudents()).data.items;
      if (!students.length) setStudents(roster);
      if (!publishOpen) { setPublishOpen(true); setPublishing(false); return; }
      if (!studentIds.length) throw new Error('请选择至少一名学生。');
      const confirmed = await createPublishConfirmation(
        version.id, version.revision, readiness.taskRevision, studentIds, session.csrfToken,
      );
      await publishVersion(version.id, version.revision, confirmed.data.confirmationId, session.csrfToken);
      setPublishOpen(false);
      updateTask(localTask!.id, current => {
        const next = { ...current };
        delete next.backendDraftVersionId;
        delete next.backendDraftRevision;
        return {
          ...next,
          editing: false,
          backendPublishedVersionId: version.id,
        backendTaskRevision: readiness.taskRevision + 1,
        };
      });
      void feedback.success('教学方案已发布，所选学生现在可以进入。');
      navigate(`/teacher/tasks/${localTask!.id}/report`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : '发布失败。'); }
    finally { setPublishing(false); }
  }

  if (!localTask) return <div className="card empty"><Empty description="找不到这项任务。" /></div>;
  if (loading) return <div className="loading-state">正在读取教学方案…</div>;
  if (!version) return <div className="card empty"><Empty description={error || '教学方案不可用。'} /><Link className="btn primary spaced" to={`/teacher/tasks/${taskId}/edit`}>返回设计页</Link></div>;

  const plan = planFromVersion(version, localTask.draft);
  const published = !localTask.editing || version.status === 'published';
  const blockers = readiness?.blockingIssues ?? [];
  return <>{contextHolder}<div className="page-heading"><div><h1>{published ? '查看教学方案' : '确认教学方案'}</h1><p>{published ? '当前展示的是已经发布的教学方案。' : '查看角色、探究问题和课堂安排；系统在后台完成一致性与发布前检查。'}</p></div>{published ? <Button onClick={() => navigate('/teacher/tasks')}>返回任务列表</Button> : <div className="row"><Button onClick={() => navigate(`/teacher/tasks/${taskId}/edit`)}>修改方案</Button><Button loading={preparing} onClick={() => void prepareChecks()}>{readiness?.ready ? '重新检查当前方案' : '准备方案'}</Button><Button type="primary" disabled={!readiness?.ready} loading={publishing} onClick={() => void publish()}>确认并发布 <ArrowRightOutlined /></Button></div>}</div>
    {error && <Alert className="spaced-bottom" type="error" showIcon message="暂时无法准备方案" description={error} />}
    {preparationProgress && <WorkflowProgress value={preparationProgress} />}
    <div className="plan-head"><h2>{plan.title || '未命名探究任务'}</h2><p>{plan.goal || '尚未生成探究目标。'}</p></div>
    <div className="plan-grid"><section className="card"><h3>和谁对话</h3><div className="spaced"><label className="field"><span>对话角色</span><Input readOnly value={plan.roleName} placeholder="尚未设置" /></label><span className="badge spaced">{plan.roleType === 'historical' ? '真实历史人物' : '虚拟综合角色'}</span><div className="spaced"><label className="field"><span>故事发生的时间</span><Input readOnly value={plan.anchor || (plan.historical ? '历史时间待确认' : '非历史情境')} /></label></div><p className="small muted spaced">AI 模拟角色，不代表人物本人真实言论。</p></div></section><section className="card"><h3>探究什么</h3><p className="spaced">{plan.question || '核心问题尚未生成。'}</p><ol className="plan-steps">{plan.questions.filter(Boolean).map((item, index) => <li key={index}>{item}</li>)}</ol></section><section className="card"><h3>课堂安排</h3><p className="spaced">建议 {plan.duration} 分钟 · 最多 {plan.maxTurns} 轮对话</p><p className="spaced">{version.sourceIds.length ? `${version.sourceIds.length} 份后端参考资料` : '暂未添加资料'}</p><p className="small spaced">没有资料支持的内容，角色会明确说明无法确认。</p><button className="link spaced" onClick={() => navigate(`/teacher/tasks/${taskId}/edit`)}>调整资料和安排 <ArrowRightOutlined /></button></section></div>
    {!published && (readiness?.ready ? <div className="notice spaced"><CheckCircleOutlined /> 当前方案已通过角色一致性与自动预检。请选择学生并确认发布。</div> : blockers.length || readiness?.nextQuestions.length ? <Alert className="spaced" type="warning" showIcon message="AI 检查发现的问题与修复建议" description={<><p className="small">请根据以下建议修改方案；需要补充资料或改变教学目标时，由教师确认后再重新准备。</p><ul className="compact-list">{[...blockers.map(item => item.message), ...(readiness?.nextQuestions ?? [])].filter((item, index, all) => all.indexOf(item) === index).map(item => <li key={item}>{item}</li>)}</ul><Button size="small" onClick={() => navigate(`/teacher/tasks/${taskId}/edit`)}>修改并修复方案</Button></>} /> : <div className="notice spaced">{preparing || readiness?.state === 'preparing' ? '系统正在准备方案。教师只需查看教学内容，不需要阅读技术检查记录。' : '点击“准备方案”后，系统将自动检查当前内容。'}</div>)}
    {!published && <details className="advanced-panel"><summary>和角色试聊 <span>使用真实对话工作流</span></summary>{session?.csrfToken ? <DialoguePanel versionId={version.id} revision={version.revision} csrfToken={session.csrfToken} /> : <Alert type="warning" showIcon message="登录状态已失效，请重新登录后试聊。" />}</details>}
    <div className="notice spaced">{published ? '这是当前已发布版本；如需调整内容，请从任务列表创建后续草稿。' : '当前方案保存在后端任务版本中；修改后旧检查会自动失效。'}</div>
    <Modal title="确认发布对象" open={publishOpen} onCancel={() => setPublishOpen(false)} onOk={() => void publish()} confirmLoading={publishing} okText="确认并发布" cancelText="取消"><p>发布后当前版本内容不可修改；后续调整需创建新版本。新的学生名单会覆盖当前任务授权名单。</p><label className="field spaced">选择学生<Select mode="multiple" style={{ width: '100%' }} value={studentIds} onChange={setStudentIds} options={students.map(item => ({ value: item.id, label: item.displayName }))} placeholder="选择可参与本次探究的学生" /></label></Modal>
  </>;
}
