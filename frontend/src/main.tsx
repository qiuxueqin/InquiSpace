import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { WorkspaceProvider } from './demo/Workspace';
import { AuthProvider } from './auth/AuthProvider';
import 'antd/dist/reset.css';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('缺少应用挂载节点。');

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#245a48',
          colorInfo: '#245a48',
          colorSuccess: '#245a48',
          colorWarning: '#95652e',
          colorText: '#27392f',
          colorTextSecondary: '#5e6d62',
          colorBgLayout: '#f7f8f4',
          colorBgContainer: '#ffffff',
          colorBorder: '#e2e7dc',
          borderRadius: 8,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Card: { borderRadiusLG: 14 },
          Tag: { borderRadiusSM: 5 },
          Menu: { itemSelectedBg: '#e8efe5', itemSelectedColor: '#245a48' },
        },
      }}
    >
      <AuthProvider><WorkspaceProvider><RouterProvider router={router} /></WorkspaceProvider></AuthProvider>
    </ConfigProvider>
  </StrictMode>,
);
