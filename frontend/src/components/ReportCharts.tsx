import { Tooltip } from 'antd';
import type { ReportMetrics } from '../api/p5';

// Single-series light-mode palette. The dataviz validator passes all checks
// against the application report surface; the neutral track is context only.
export const reportGreen = '#367a42';

const labels: Array<[keyof ReportMetrics, string, string]> = [
  ['expressionCount', '表达想法', '学生发送的实际消息数；提问也计入。'],
  ['evidenceSeekingCount', '寻找依据', '最新可用报告中 evidence_seeking 信号的学生消息去重数。'],
  ['sourceViewCount', '查阅资料', '每次探究中成功打开的不同资料数；未采集显示为未知。'],
  ['judgmentCount', '作出判断', '判断信号消息数与当前有效判断选择数。'],
  ['reflectionCount', '反思修正', '最新可用报告中 reflection 信号的学生消息去重数。'],
];

export function BehaviorBars({ metrics }: { metrics: ReportMetrics }) {
  const known = labels.map(([field]) => metrics[field]).filter((value): value is number => value !== null);
  const maximum = Math.max(1, ...known);
  return <>
    <div aria-label="探究行为次数">
      {labels.map(([field, label, rule]) => {
        const value = metrics[field];
        return <Tooltip key={field} trigger={['hover', 'focus']} title={`${label}：${value ?? '尚未知'}。${rule}`}>
          <div className="chart-bar-row" tabIndex={0} aria-label={`${label} ${value ?? '尚未知'}`}>
            <span>{label}</span><span className="bar-track" aria-hidden="true"><span style={{ width: `${value === null ? 0 : value / maximum * 100}%`, backgroundColor: reportGreen }} /></span><strong>{value ?? '—'}</strong>
          </div>
        </Tooltip>;
      })}
    </div>
    <p className="small muted spaced">按实际表达、学习事件与已整理信号统计，不代表成绩。未知值显示为“—”，不会伪装成 0。</p>
    <details className="small spaced"><summary>查看图表数据与统计口径</summary><div className="table-scroll"><table><caption>当前报告范围的探究行为统计</caption><thead><tr><th>行为</th><th>次数</th><th>统计口径</th></tr></thead><tbody>{labels.map(([field, label, rule]) => <tr key={field}><th>{label}</th><td>{metrics[field] ?? '尚未知'}</td><td>{rule}</td></tr>)}</tbody></table></div></details>
  </>;
}

export function ProgressDonut({ active, ended }: { active: number; ended: number }) {
  const total = active + ended;
  const percentage = total ? Math.round(ended / total * 100) : 0;
  const label = `${total} 次探究，已结束 ${ended} 次，进行中 ${active} 次。`;
  return <><div className="donut-layout"><Tooltip title={label}><div className="donut" tabIndex={0} role="img" aria-label={label}><svg viewBox="0 0 200 200" width="200" height="200" aria-hidden="true"><circle cx="100" cy="100" r="78" fill="none" stroke="var(--report-track, #e8eee2)" strokeWidth="22" />{ended > 0 && <circle cx="100" cy="100" r="78" fill="none" stroke={reportGreen} strokeWidth="22" pathLength="100" strokeDasharray={`${ended / total * 100} 100`} transform="rotate(-90 100 100)" />}<text x="100" y="99" textAnchor="middle" fill="currentColor" fontSize="38" fontWeight="600">{total}</text><text x="100" y="124" textAnchor="middle" fill="currentColor" fontSize="12">次探究</text></svg></div></Tooltip><div className="donut-legend"><p><span style={{ background: reportGreen }} />已结束 <strong>{ended}</strong></p><p><span style={{ background: 'var(--report-track, #e8eee2)' }} />进行中 <strong>{active}</strong></p><p className="small muted">{total ? `${percentage}% 已结束` : '暂无探究记录'}</p></div></div><p className="small muted">“已结束”表示学生结束了探究，不代表达成学习目标。</p><details className="small"><summary>查看进度数据</summary><table><tbody><tr><th>已结束</th><td>{ended}</td></tr><tr><th>进行中</th><td>{active}</td></tr><tr><th>合计</th><td>{total}</td></tr></tbody></table></details></>;
}
