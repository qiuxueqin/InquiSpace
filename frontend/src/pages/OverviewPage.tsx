import { ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Descriptions, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiClientError } from '../api/client';
import type { ApiResponse } from '../api/client';
import { getHealth } from '../api/health';
import type { HealthData } from '../api/health';
import { PageHeading } from '../components/Page';

type HealthState =
  | { status: 'loading' }
  | { status: 'success'; response: ApiResponse<HealthData> }
  | { status: 'error'; error: ApiClientError };

function HealthCheck() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<HealthState>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    void getHealth(controller.signal).then(
      (response) => {
        if (!controller.signal.aborted) setState({ status: 'success', response });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            error: error instanceof ApiClientError ? error : new ApiClientError('network', '健康检查未完成，请重试。'),
          });
        }
      },
    );
    return () => controller.abort();
  }, [attempt]);

  function retry() {
    setState({ status: 'loading' });
    setAttempt((previous) => previous + 1);
  }

  return (
    <Card className="section-card" title="后端连接检查" extra={
      <Button icon={<ReloadOutlined />} onClick={retry} loading={state.status === 'loading'}>
        {state.status === 'error' ? '重试' : '重新检查'}
      </Button>
    }>
      <p className="muted">实际请求 <code>GET /api/v1/health</code>，不使用模拟响应。检查结果只表示本次服务连接情况，不代表业务功能可用。</p>
      <div aria-live="polite" aria-busy={state.status === 'loading'}>
        {state.status === 'loading' && (
          <div className="loading-state" role="status"><Spin /><span>正在连接后端服务…</span></div>
        )}
        {state.status === 'error' && (
          <Alert
            type="error"
            showIcon
            message="后端连接检查失败"
            description={
              <div className="error-detail">
                <p>{state.error.message}</p>
                <p>错误类型：{state.error.kind}{state.error.status ? ` · HTTP ${state.error.status}` : ''}</p>
                {state.error.code && <p>错误代码：<code>{state.error.code}</code></p>}
                {state.error.requestId && <p>请求编号：<code>{state.error.requestId}</code></p>}
                <p>{state.error.retryable ? '可手动重试。' : '请先检查服务或响应契约，修复后可重新检查。'}开发环境应在 127.0.0.1:8000 启动后端。</p>
              </div>
            }
          />
        )}
        {state.status === 'success' && (
          <div className="stack">
            <Alert type="success" showIcon message="后端与数据库健康检查通过" />
            <Descriptions size="small" bordered column={1} items={[
              { key: 'service', label: '服务', children: state.response.data.service },
              { key: 'version', label: '版本', children: state.response.data.version },
              { key: 'status', label: '服务状态', children: state.response.data.status },
              { key: 'database', label: '数据库状态', children: state.response.data.database },
              { key: 'requestId', label: '请求编号', children: <code>{state.response.requestId}</code> },
            ]} />
          </div>
        )}
      </div>
    </Card>
  );
}

export function OverviewPage() {
  return (
    <>
      <PageHeading title="为每一次探究，留出思考的空间" description="知境面向单角色探究教学。当前提供页面结构与后端连接检查，尚不提供真实教学业务。" />
      <div className="intro-grid">
        <Card className="section-card" title="教师教学空间">
          <p>教学任务的创建、编辑、预览与报告将在这里承载。当前只提供页面壳，不生成方案、不保存草稿、不发布任务。</p>
          <Link className="text-link" to="/teacher/tasks">查看教师页面结构 →</Link>
        </Card>
        <Card className="section-card" title="学生探究空间">
          <p>围绕单一角色开展探究，会话与学习成果将在这里呈现。当前不生成对话、不创建会话、不提交成果。</p>
          <Link className="text-link" to="/student/tasks">查看学生页面结构 →</Link>
        </Card>
      </div>
      <HealthCheck />
      <section className="scope-note" aria-labelledby="scope-title">
        <h2 id="scope-title">当前框架边界</h2>
        <p>本页是项目说明，不是教学数据看板。暂无任务统计、学习结论或图表，也不预置演示任务与学生数据。</p>
        <p>页面可直接访问是开发预览能力，不是权限方案。认证、授权及业务接口接入后，将以服务端真实状态为准。</p>
      </section>
    </>
  );
}
