import { Card, Empty, Tag } from 'antd';
import { useEffect } from 'react';
import type { ReactNode } from 'react';

export function PageHeading({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · 知境 InquiSpace`;
  }, [title]);

  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">INQUISPACE / 单角色教学</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-action">{action}</div>}
    </div>
  );
}

export function Unconnected({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return (
    <Card className="section-card" title={title} extra={<Tag color="warning">未接入</Tag>}>
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span>{description}</span>} />
      {children && <div className="empty-actions">{children}</div>}
    </Card>
  );
}
