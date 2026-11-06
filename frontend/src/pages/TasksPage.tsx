import { PlusOutlined, SearchOutlined, ArrowRightOutlined, InboxOutlined, MoreOutlined } from '@ant-design/icons';
import { Button, Dropdown, Empty, Input, Modal, message } from 'antd';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useWorkspace } from '../demo/useWorkspace';
import { createConfirmation } from '../api/p3';
import { archiveTask as archiveRemoteTask, restoreTask as restoreRemoteTask } from '../api/p5';
import { getTask, getVersion } from '../api/tasks';
import { useAuth } from '../auth/useAuth';
import type { Task } from '../demo/model';

export function PalaceArt() {
  return <svg className="palace-art" viewBox="0 0 300 200" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true"><path d="M18 166h264M30 157h240M48 145h204M63 90h174v55H63ZM54 90h192M43 86c28-4 46-11 57-24h100c11 13 29 20 57 24ZM97 62h106M108 46h84M99 45c22-3 39-10 51-23 11 13 28 20 51 23ZM112 47v14M188 47v14M79 92v51M92 92v51M208 92v51M221 92v51M110 105h80v40M128 105v39M150 105v39M172 105v39M110 117h80M110 131h80M68 97h31M201 97h31M62 149h176M76 153h148" /><circle cx="150" cy="19" r="3" /></svg>;
}

export function TasksPage({ student = false }: { student?: boolean }) {
  const { state, setState, updateTask, openSession } = useWorkspace();
  const { session } = useAuth();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [archiveTask, setArchiveTask] = useState<Task | null>(null);
  const navigate = useNavigate();
  const [feedback, contextHolder] = message.useMessage();
  const isPublished = (task: Task) => task.publications.length > 0 || Boolean(task.backendPublishedVersionId);
  const available = state.tasks.filter(task => !student || (!task.archived && task.publications.at(-1)?.audience.includes(state.studentId)));
  const visible = available.filter(task => {
    const plan = student ? task.publications.at(-1)!.plan : task.draft;
    return `${plan.title} ${plan.roleName} ${plan.subject}`.includes(search.trim()) && (filter === 'archived' ? task.archived : !task.archived && (filter === 'all' || (filter === 'published' ? isPublished(task) : task.editing)));
  });
  function selectTask(task: Task) {
    setState(previous => ({ ...previous, selectedTaskId: task.id }));
  }
  function enter(task: Task) {
    try { selectTask(task); navigate(`/student/sessions/${openSession(task)}`); }
    catch (error) { void feedback.warning(error instanceof Error ? error.message : '暂时无法打开任务。'); }
  }
  async function toggleArchive(task: Task) {
    if (!task.backendTaskId || !session?.csrfToken) {
      void feedback.warning('该本地演示任务尚未连接后端，不能执行正式归档。');
      return;
    }
    try {
      const remote = await getTask(task.backendTaskId);
      let taskRevision = remote.data.taskRevision;
      if (task.archived) {
        taskRevision = (await restoreRemoteTask(task.backendTaskId, taskRevision, session.csrfToken)).data.taskRevision;
      } else {
        const versionId = remote.data.draftVersionId ?? remote.data.currentPublishedVersionId ?? task.backendPublishedVersionId;
        if (!versionId) throw new Error('当前任务没有可用于确认归档的版本。');
        const version = await getVersion(versionId);
        const confirmed = await createConfirmation(versionId, version.data.revision, session.csrfToken, taskRevision, { action: 'archive_task', payload: {} });
        taskRevision = (await archiveRemoteTask(task.backendTaskId, confirmed.data.confirmationId, taskRevision, session.csrfToken)).data.taskRevision;
      }
      updateTask(task.id, current => ({ ...current, archived: !current.archived, backendTaskRevision: taskRevision }));
      setArchiveTask(null);
    } catch (error) { void feedback.error(error instanceof Error ? error.message : '无法更新任务状态。'); }
  }
  return <>{contextHolder}<div className="page-heading"><div><h1>{student ? '带着好奇，开始一场探究。' : '把一个问题，变成一场探究。'}</h1><p>{student ? '与一个角色相遇，用问题打开情境，用证据形成自己的判断。' : '创建真实、有边界的角色，让学生在对话中发现自己的答案。'}</p></div>{!student && <Link className="btn primary" to="/teacher/tasks/new"><PlusOutlined /> 创建探究任务</Link>}</div>
    <div className="section-bar"><div className="row"><h2>我的探究任务</h2><span className="badge gray">{available.filter(task => !task.archived).length} 个任务</span></div><Input className="task-search" prefix={<SearchOutlined />} placeholder="搜索主题、角色…" aria-label="搜索任务" value={search} onChange={event => setSearch(event.target.value)} allowClear /></div>
    <div className="tabs" role="tablist" aria-label="任务筛选">{(student ? [['all', '可参与任务']] : [['all', '全部任务'], ['published', '已发布'], ['draft', '草稿'], ['archived', '已归档']]).map(([key, label]) => <button key={key} role="tab" aria-selected={filter === key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key!)}>{label}<span>{available.filter(task => key === 'archived' ? task.archived : !task.archived && (key === 'all' || (key === 'published' ? isPublished(task) : task.editing))).length}</span></button>)}</div>
    <div className="task-grid">{visible.map(task => {
      const plan = student ? task.publications.at(-1)!.plan : task.draft;
      const session = state.sessions.find(item => item.taskId === task.id && item.studentId === state.studentId && item.publicationId === task.publications.at(-1)?.id);
      return <article className="card task-card" key={task.id}><div className={`task-cover ${plan.subject === '生物' ? 'ecology' : ''}`}><span className={`badge ${task.editing ? 'amber' : ''}`}>● {task.archived ? '已归档' : task.editing ? '草稿 · 待确认' : task.backendPublishedVersionId ? '已发布 · 后端方案' : '已发布 · 本地演示'}</span><div className="cover-title">{plan.subject === '生物' ? '自然的回响' : plan.subject === '语文' ? '文字与人生' : '时代的转身'}</div><PalaceArt /></div><div className="task-body"><h3>{plan.title || '未命名探究任务'}</h3><p>{plan.background || '一个新的教学想法，正在等待被展开。'}</p><div className="meta"><span>{plan.subject} · {plan.grade}</span><span>角色：{plan.roleName || '待设置'}</span><span>{plan.anchor || '时间待设置'}</span></div><div className="task-bottom"><small>{student ? session ? session.finished ? '已完成探究 · 可查看报告' : `已有 ${session.messages.filter(item => item.role === 'student').length} 次表达` : '一段新的探究，等待开始' : `${task.backendPublishedVersionId ? '已发布 · 后端工作区' : task.publications.length ? `第 ${task.publications.length} 次发布 · 本地工作区` : '尚未发布 · 本地工作区'}`}</small><div className="row">{student ? <Button type="primary" onClick={() => enter(task)}>{session?.finished ? '查看探究记录' : session ? '继续探究' : '开始探究'} <ArrowRightOutlined /></Button> : <><Link className="link" onClick={() => selectTask(task)} to={`/teacher/tasks/${task.id}/${task.editing ? 'edit' : 'preview'}`}>{task.editing ? '继续设计' : '查看方案'} <ArrowRightOutlined /></Link><Dropdown menu={{ items: [{ key: 'report', label: '查看教学报告' }, { key: 'archive', label: task.archived ? '恢复任务' : '归档任务', icon: <InboxOutlined /> }], onClick: ({ key }) => { selectTask(task); if (key === 'report') navigate(`/teacher/tasks/${task.id}/report`); else setArchiveTask(task); } }} trigger={['click']}><Button type="text" aria-label={`${plan.title || '任务'}的更多操作`} icon={<MoreOutlined />} /></Dropdown></>}</div></div></div></article>;
    })}{!student && !search && filter !== 'archived' && <Link to="/teacher/tasks/new" className="new-card"><span className="plus"><PlusOutlined /></span><h3>从一个好问题开始</h3><span>设置主题、选择一个角色，<br />设计下一场有依据的探究。</span></Link>}</div>
    {!visible.length && <div className="card empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search ? '没有找到匹配的任务，试试其他关键词。' : student ? '当前账号暂无可参与任务。' : '这个分类下还没有任务。'} /></div>}
    <div className="tip">{student ? '不必急于找到答案。说说你的想法，也可以坦白还不确定。' : '写下教学想法，确认方案后即可发布。资料和详细配置可以稍后补充。'}</div>
    <Modal title={archiveTask?.archived ? '恢复这项探究任务？' : '将这项探究任务归档？'} open={!!archiveTask} onCancel={() => setArchiveTask(null)} okText={archiveTask?.archived ? '恢复任务' : '确认归档'} cancelText="取消" onOk={() => { if (archiveTask) void toggleArchive(archiveTask); }}><p>{archiveTask?.archived ? '恢复后，原授权名单中的学生可以重新进入任务。' : '归档后学生不能继续提问，已有对话、学习报告和历史版本都会保留。'}</p></Modal>
  </>;
}
