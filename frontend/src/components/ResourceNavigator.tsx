import { Button, Form, Input, Space } from 'antd';
import { useNavigate } from 'react-router-dom';

type ResourceNavigatorProps = {
  resource: 'task' | 'session';
};

/** 只拼装开发预览路由，不查询、创建或验证资源。 */
export function ResourceNavigator({ resource }: ResourceNavigatorProps) {
  const navigate = useNavigate();
  const isTask = resource === 'task';
  const label = isTask ? '任务 ID' : '会话 ID';

  function openPage(values: { resourceId: string }) {
    const id = encodeURIComponent(values.resourceId.trim());
    void navigate(isTask ? `/teacher/tasks/${id}/edit` : `/student/sessions/${id}`);
  }

  return (
    <section className="resource-preview" aria-label="按标识打开开发页面">
      <h2>按标识预览页面结构</h2>
      <p className="muted">填写已有的{label}可打开对应页面壳。不会验证资源是否存在，也不会创建或加入任何任务、会话。</p>
      <Form<{ resourceId: string }> layout="vertical" onFinish={openPage} requiredMark={false}>
        <Form.Item name="resourceId" label={label} rules={[
          { required: true, whitespace: true, message: `请输入${label}` },
          { max: 200, message: '标识最多 200 个字符' },
          { pattern: /^(?!\s*\.{1,2}\s*$)[^/?#\\]+$/, message: '请填写标识，而不是路径或 URL' },
        ]}>
          <Input placeholder={`输入${label}，不提供演示 ID`} maxLength={200} autoComplete="off" />
        </Form.Item>
        <Space><Button htmlType="submit">打开页面壳</Button><span className="muted">仅导航，无业务操作</span></Space>
      </Form>
    </section>
  );
}
