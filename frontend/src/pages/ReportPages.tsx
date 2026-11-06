import { Button, Empty, Modal, Select, Tooltip } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { exportTeacherReport, getLearningReport, getTeacherReport } from '../api/p5';
import type { ReportEnvelope, ReportMetrics, TeacherReport } from '../api/p5';
import { useAuth } from '../auth/useAuth';
import { BehaviorBars, ProgressDonut } from '../components/ReportCharts';

const labels: Array<[keyof ReportMetrics, string]> = [
  ['expressionCount', '表达想法'],
  ['evidenceSeekingCount', '寻找依据'],
  ['sourceViewCount', '查阅资料'],
  ['judgmentCount', '作出判断'],
  ['reflectionCount', '反思修正'],
];

export function TeacherReportPage({ taskId }: { taskId: string }) {
  const { session } = useAuth();
  const [scope, setScope] = useState('latest');
  const [versionId, setVersionId] = useState<string>();
  const [report, setReport] = useState<TeacherReport | null>(null);
  const [detail, setDetail] = useState<ReportEnvelope | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    if (!taskId) return;
    try {
      const result = await getTeacherReport(taskId, scope, 'all', scope === 'version' ? versionId : undefined);
      setReport(result.data); setError('');
    } catch (caught) { setError(caught instanceof Error ? caught.message : '无法读取教学报告。'); }
  }, [scope, taskId, versionId]);
  useEffect(() => { void load(); }, [load]);
  async function openStudent(sessionId: string) {
    try { setDetail((await getLearningReport(sessionId)).data); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '无法读取学生报告。'); }
  }
  async function download() {
    if (!report || !session?.csrfToken) return;
    try {
      const blob = await exportTeacherReport(taskId, scope, scope === 'version' ? versionId : undefined, report.aggregateToken, session.csrfToken);
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = '知境_教学报告.html'; document.body.append(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) { setError(caught instanceof Error ? caught.message : '导出失败。'); }
  }
  if (!report) return <div className="loading-state">{error || '正在读取教学报告…'}</div>;
  return <><div className="page-heading"><div><h1>教学报告</h1><p>了解学生的探究进展，找到下一步值得讨论的问题。</p></div><Button onClick={() => void download()}>导出当前报告</Button></div>
    {error && <p role="alert" className="notice warning">{error}</p>}
    <div className="section-bar"><h2>任务报告</h2><div className="row"><label className="field">统计范围<Select value={scope === 'version' ? versionId : scope} style={{ minWidth: 160 }} onChange={value => { if (value === 'latest' || value === 'all') { setScope(value); setVersionId(undefined); } else { setScope('version'); setVersionId(value); } }} options={[{ value: 'latest', label: '最新发布' }, { value: 'all', label: '历次发布' }, ...report.versions.map(item => ({ value: item.id, label: `第 ${item.versionNo} 次发布` }))]} /></label></div></div>
    <p className="small muted">统计时间：{new Date(report.asOf).toLocaleString()}。状态筛选只影响学生列表，顶部指标与图表保持整个发布范围。</p>
    <div className="dashboard-kpis spaced">{[
      ['参与学生', report.kpis.participantCount, '人'], ['探究次数', report.kpis.sessionCount, '次'],
      ['对话轮数', report.kpis.completedTurns, '轮'], ['已完成报告', report.kpis.completedReportCount, '份'],
    ].map(([label, value, unit]) => <section className="card" key={label}><p className="small muted">{label}</p><div><strong>{value}</strong><span className="small"> {unit}</span></div></section>)}</div>
    <section className="ai-observation spaced"><span className="ai-mark">✦</span><div><h3>课堂小结</h3><p>{report.classroomSummary.text}</p>{report.suggestions.map(item => <p key={item.text}>{item.text}</p>)}</div></section>
    <div className="dashboard-charts spaced"><section className="card"><h3>探究进度</h3><ProgressDonut active={report.progress.activeSessions} ended={report.progress.endedSessions} /></section><section className="card"><div className="section-bar"><h3>学生如何探究</h3><span className="small muted">点击学生行查看报告依据</span></div><BehaviorBars metrics={report.metrics} /></section></div>
    <p className="small muted">语义报告覆盖 {report.coverage.readyReportSessions}/{report.coverage.totalSessions} 次探究；来源完整采集 {report.coverage.sourceTrackedSessions} 次，部分采集 {report.coverage.partialSourceSessions} 次，未采集 {report.coverage.unavailableSourceSessions} 次。未知不会显示为 0。</p>
    <section className="card spaced"><div className="section-bar"><h3>学生学习情况</h3><span className="small muted">{report.students.length} 份探究记录</span></div><div className="table-scroll"><table><caption>当前列表筛选；每行对应一次探究</caption><thead><tr><th>学生 / 版本</th><th>状态</th>{labels.map(([, label]) => <th key={label}>{label}</th>)}<th>学习报告</th></tr></thead><tbody>{report.students.map(row => <tr key={row.sessionId}><th>{row.displayName}<div className="small muted">第 {row.versionNo} 次发布</div></th><td>{row.status === 'ended' ? '已结束' : '进行中'}</td>{labels.map(([field, label]) => <td key={field}><Tooltip title={`${label}不代表成绩或能力`}><span>{row.metrics[field] ?? (field === 'sourceViewCount' && row.sourceTracking === 'unavailable' ? '未记录' : '整理中')}</span></Tooltip></td>)}<td><Button type="link" onClick={() => void openStudent(row.sessionId)}>{row.reportId ? '查看报告' : row.reportStatus === 'failed' ? '整理失败' : '尚未就绪'}</Button>{row.correctionCount > 0 && <div className="small muted">{row.correctionCount} 条学生补充</div>}</td></tr>)}{!report.students.length && <tr><td colSpan={8}><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前范围暂无探究记录。" /></td></tr>}</tbody></table></div></section>
    <Modal title="学生学习报告" open={!!detail} onCancel={() => setDetail(null)} footer={<Button onClick={() => setDetail(null)}>关闭</Button>} width={900}>{detail && <StudentReportDetail envelope={detail} />}</Modal></>;
}

function StudentReportDetail({ envelope }: { envelope: ReportEnvelope }) {
  const report = envelope.latestReadyReport;
  if (!report?.content) return <Empty description={envelope.freshness === 'failed' ? '报告整理失败，可由学生或教师重试。' : '报告仍在整理。'} />;
  return <><section className="learning-report-hero"><div><h2>探究摘要</h2><p>{report.content.summary.text}</p>{report.content.missingAspects.map(item => <p className="small muted" key={item}>{item}</p>)}</div><div className="report-turns"><strong>{report.metrics.expressionCount ?? 0}</strong><span>次表达</span></div></section><BehaviorBars metrics={report.metrics} /><details className="advanced-panel spaced"><summary>查看整理依据</summary>{report.content.findings.map((item, index) => <blockquote key={`${item.kind}-${index}`}>{item.text}<div className="small muted">{item.kind === 'role_view' ? '角色观点' : '学生已表达内容'}</div></blockquote>)}</details>{envelope.corrections.map(item => <blockquote key={item.id}><small>学生补充</small><p>{item.text}</p></blockquote>)}</>;
}

// Kept as a named export for existing imports while the old demo report surface is retired.
export function LearningReport() { return null; }
