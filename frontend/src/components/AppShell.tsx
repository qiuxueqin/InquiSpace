import { AppstoreOutlined, BookOutlined, BarChartOutlined, FileTextOutlined, LogoutOutlined, MenuOutlined, MessageOutlined, SafetyCertificateOutlined, ReadOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Dropdown, message } from 'antd';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { useWorkspace } from '../demo/useWorkspace';

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const { session } = useAuth();
  const { state } = useWorkspace();
  const task = state.tasks.find(item => item.id === state.selectedTaskId) ?? state.tasks[0];
  const base = task ? `/teacher/tasks/${task.id}` : '/teacher/tasks/new';
  const currentStudentId = session?.user.id ?? '';
  const sessionRecord = state.sessions.filter(item => item.studentId === currentStudentId).at(-1);
  const items = session?.user.role === 'student' ? [
    { to: '/student/tasks', icon: <AppstoreOutlined />, label: '我的任务' },
    { to: sessionRecord ? `/student/sessions/${sessionRecord.id}` : '/student/tasks', icon: <MessageOutlined />, label: '学生探究' },
    { to: sessionRecord ? `/student/sessions/${sessionRecord.id}/submission` : '/student/tasks', icon: <ReadOutlined />, label: '学习报告' },
  ] : [
    { to: '/teacher/tasks', icon: <AppstoreOutlined />, label: '我的任务' },
    { to: task ? `${base}/edit` : base, icon: <FileTextOutlined />, label: '任务设计' },
    { to: task ? `${base}/preview` : base, icon: <SafetyCertificateOutlined />, label: '方案预览' },
    { to: task ? `${base}/report` : base, icon: <BarChartOutlined />, label: '教学报告' },
  ];
  return <nav className="main-nav" aria-label="主要导航">{items.map(item => <NavLink key={item.label} to={item.to} end onClick={onNavigate}>{item.icon}<span>{item.label}</span></NavLink>)}</nav>;
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { session, logout, homeForRole } = useAuth();
  const { storageError } = useWorkspace();
  const [feedback, contextHolder] = message.useMessage();
  const title = pathname.endsWith('/preview') ? '方案预览' : pathname.endsWith('/report') ? '教学报告' : pathname.endsWith('/submission') ? '学习报告' : pathname.includes('/sessions/') ? '学生探究' : pathname.endsWith('/edit') || pathname.endsWith('/new') ? '任务设计' : pathname === '/system' ? '系统状态' : '我的任务';
  useEffect(() => {
    document.title = `${title} · 知境`;
    document.getElementById('main-content')?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [pathname, title]);
  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (error) {
      void feedback.error(error instanceof Error ? error.message : '退出登录失败，请稍后重试。');
    } finally {
      setLoggingOut(false);
    }
  }
  const home = session ? homeForRole(session.user.role) : '/login';
  const brand = <Link className="brand" to={home}><span className="brand-mark"><BookOutlined /></span><span><strong>知境</strong><small>INQUIRY STUDIO</small></span></Link>;
  const userInitial = session?.user.displayName.trim().slice(0, 1) || '知';
  return <div className="app-shell">
    {contextHolder}
    <a className="skip-link" href="#main-content">跳转到主要内容</a>
    <aside className="sidebar">{brand}<div className="workspace-label"><BookOutlined /><div>主题探究工作台<small>{session?.user.role === 'student' ? '我的探究空间' : '单角色探究教学'}</small></div></div><div><p className="nav-caption">工作空间</p><Navigation /></div><div className="sidebar-note">每一个好问题，<br />都是理解世界的开始。</div></aside>
    <div className="workspace">
      <header className="topbar"><div className="breadcrumb"><Button type="text" className="mobile-menu" icon={<MenuOutlined />} onClick={() => setMenuOpen(true)} aria-label="打开导航" /><span>工作空间</span><span>/</span><strong>{title}</strong></div><div className="profile"><Dropdown placement="bottomRight" menu={{ items: [{ key: 'identity', label: session?.user.role === 'teacher' ? '教师账号' : '学生账号', icon: <UserOutlined />, disabled: true }, { type: 'divider' }, { key: 'logout', label: loggingOut ? '正在退出…' : '退出登录', icon: <LogoutOutlined />, disabled: loggingOut }], onClick: ({ key }) => { if (key === 'logout') void handleLogout(); } }}><Button type="text" className="profile-account" aria-label={`${session?.user.displayName ?? '当前用户'}，打开账号菜单`}><span className="avatar">{userInitial}</span><span>{session?.user.displayName}</span></Button></Dropdown></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>{storageError && <Alert className="spaced-bottom" type="warning" showIcon message={storageError} />}<Outlet /></main>
      <footer className="site-footer"><span>以问题为起点，以证据为路径。</span></footer>
    </div>
    <Drawer title="知境 · 工作空间" placement="left" width={280} open={menuOpen} onClose={() => setMenuOpen(false)}><Navigation onNavigate={() => setMenuOpen(false)} /><div className="mobile-account spaced"><span className="avatar">{userInitial}</span><div><strong>{session?.user.displayName}</strong><p className="small muted">{session?.user.role === 'teacher' ? '教师账号' : '学生账号'}</p></div></div><Button danger block icon={<LogoutOutlined />} loading={loggingOut} onClick={() => void handleLogout()}>退出登录</Button></Drawer>
  </div>;
}
