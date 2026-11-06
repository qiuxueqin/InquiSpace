import { Progress } from 'antd';
import { useEffect, useState } from 'react';

export type WorkflowProgressState = {
  title: string;
  detail: string;
  percent: number;
  ceiling: number;
  status: 'active' | 'success' | 'error';
};

export function WorkflowProgress({ value }: { value: WorkflowProgressState }) {
  const [displayed, setDisplayed] = useState(value.percent);

  useEffect(() => {
    setDisplayed(value.percent);
  }, [value.percent, value.status]);

  useEffect(() => {
    if (value.status !== 'active') return;
    const timer = window.setInterval(() => {
      setDisplayed(current => Math.min(value.ceiling, current + 1));
    }, 900);
    return () => window.clearInterval(timer);
  }, [value.ceiling, value.status]);

  const status = value.status === 'success'
    ? 'success'
    : value.status === 'error'
      ? 'exception'
      : 'active';

  return <div className={`workflow-progress ${value.status}`} role="status" aria-live="polite">
    <div className="workflow-progress-heading">
      <strong>{value.title}</strong>
      <span>{value.status === 'active' ? '正在处理' : value.status === 'success' ? '已完成' : '未完成'}</span>
    </div>
    <Progress
      percent={value.status === 'success' ? 100 : displayed}
      status={status}
      showInfo={false}
      {...(value.status === 'active' ? { strokeColor: '#367a42' } : {})}
      trailColor="#e3e9dc"
      aria-label={value.title}
      aria-valuetext={value.detail}
    />
    <p>{value.detail}</p>
  </div>;
}
