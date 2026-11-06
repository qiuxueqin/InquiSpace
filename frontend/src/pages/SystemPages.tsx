import { BookOutlined, LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Result, Space } from 'antd';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiClientError } from '../api/client';
import { useAuth } from '../auth/useAuth';

export function LoginPage() {
  const { login, homeForRole, status, error: serviceError, retry } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  async function submit() {
    if (!username.trim() || !password || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const authenticated = await login(username.trim(), password);
      navigate(homeForRole(authenticated.user.role), { replace: true });
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.kind === 'http' && caught.status === 401) setError('账号或密码错误，请重新输入。');
      else setError(caught instanceof Error ? caught.message : '登录失败，请稍后重试。');
    } finally {
      setSubmitting(false);
    }
  }
  return <main className="login-page"><div className="login-layout"><div className="login-intro"><span className="brand-mark"><BookOutlined /></span><div className="eyebrow spaced">WELCOME TO INQUIRY STUDIO</div><h1 className="serif">一个好问题，<br />打开一个新世界。</h1><p>在真实、有边界的情境中，<br />让每一个观点有依据，让每一次思考被看见。</p></div><form className="card login-card" onSubmit={event => { event.preventDefault(); void submit(); }}><h2>欢迎来到知境</h2><p className="muted spaced">登录你的教学与探究工作台</p>{status === 'unavailable' && <Alert className="spaced" type="warning" showIcon message="暂时无法连接登录服务" description={serviceError} action={<Button size="small" onClick={() => void retry()}>重新连接</Button>} />}{error && <Alert className="spaced" type="error" showIcon message={error} />}
    <label className="field spaced">账号<Input autoFocus autoComplete="username" prefix={<UserOutlined />} placeholder="请输入账号" value={username} onChange={event => setUsername(event.target.value)} disabled={submitting} /></label><label className="field spaced">密码<Input.Password autoComplete="current-password" prefix={<LockOutlined />} placeholder="请输入密码" value={password} onChange={event => setPassword(event.target.value)} disabled={submitting} /></label><Button htmlType="submit" block type="primary" size="large" className="spaced" loading={submitting} disabled={!username.trim() || !password}>{submitting ? '正在登录' : '登录'}</Button><p className="login-security small muted">登录状态由服务端 HttpOnly Cookie 维护。登录成功后将根据账号角色进入教师或学生页面。</p></form></div></main>;
}
export function NotFoundPage() {
  const { session, homeForRole } = useAuth();
  const home = session ? homeForRole(session.user.role) : '/login';
  return <Result status="404" title="这页探究还没有开始" subTitle="当前地址不存在，请从工作台重新出发。" extra={<Link className="btn primary" to={home}>返回我的任务</Link>} />;
}
export function RouteErrorPage() {
  return <main className="route-error"><Result status="error" title="页面暂时无法显示" subTitle="前端页面出现异常。这不代表操作已完成，请重新加载或返回首页。" extra={<Space wrap><Button onClick={() => window.location.reload()}>重新加载</Button><a className="btn" href="/">返回首页</a></Space>} /></main>;
}
