import { describe, expect, it } from 'vitest';
import { behaviorCounts, blankPlan, conversationGate, createSession, createTask, defaultPlan, demoReply, publishTask, seedWorkspace, turnCount, validatePlan } from './model';

describe('本地演示的任务与版本', () => {
  it('空白任务需要补充教学内容，默认示例可以发布', () => {
    expect(validatePlan(blankPlan()).length).toBeGreaterThan(0);
    expect(validatePlan(defaultPlan())).toEqual([]);
  });
  it.each(['1912', '1912-02', '1912-02-12'])('接受时间精度 %s', anchor => {
    expect(validatePlan({ ...defaultPlan(), anchor })).toEqual([]);
  });
  it.each(['1912-13', '1912-02-31', 'not-a-date'])('拒绝无效日期 %s', anchor => {
    expect(validatePlan({ ...defaultPlan(), anchor }).length).toBeGreaterThan(0);
  });
  it('发布必须有学生、可用资料与有效时间', () => {
    const task = createTask(defaultPlan());
    expect(() => publishTask(task, [])).toThrow('学生');
    expect(() => publishTask(task, ['unknown'])).toThrow('学生');
    expect(validatePlan({ ...task.draft, deadline: '2000-01-01T12:00' })).toContain('请设置未来的截止时间，或留空');
    expect(validatePlan({ ...task.draft, sources: [{ id: 'failed', name: 'x.pdf', location: '', text: '读取失败', status: 'failed' }] })).toContain('请移除未能读取的资料后再发布');
  });
  it('发布冻结方案，后续草稿修改不污染旧会话', () => {
    const task = publishTask(createTask(defaultPlan()), ['xiaoyu']);
    const session = createSession(task, 'xiaoyu');
    const oldTitle = session.plan.title;
    task.draft.title = '修改后的标题';
    task.draft.sources[0]!.text = '改写的资料';
    expect(task.publications[0]!.plan.title).toBe(oldTitle);
    expect(session.plan.title).toBe(oldTitle);
    expect(session.plan.sources[0]!.text).not.toBe('改写的资料');
    expect(() => publishTask(task, ['xiaoyu'])).toThrow('已经发布');
    const next = publishTask({ ...task, editing: true }, ['xiaoyu']);
    expect(next.publications).toHaveLength(2);
    expect(next.publications[1]!.plan.title).toBe('修改后的标题');
    expect(session.publicationId).toBe(next.publications[0]!.id);
  });
  it('归档与发布名单限制新会话', () => {
    const task = publishTask(createTask(defaultPlan()), ['xiaoyu']);
    expect(() => createSession(task, 'zihan')).toThrow();
    expect(() => createSession({ ...task, archived: true }, 'xiaoyu')).toThrow();
    expect(() => publishTask({ ...task, archived: true, editing: true }, ['xiaoyu'])).toThrow('归档');
  });
});

describe('对话与报告规则', () => {
  it('结束、截止、归档及轮次限制阻止新提问', () => {
    const task = publishTask(createTask(defaultPlan()), ['zihan']);
    const session = createSession(task, 'zihan');
    session.messages = [{ id: 'answer', role: 'character', text: '回答', sourceIds: [], saved: false, stance: null }];
    expect(conversationGate(session, task)).toBe('');
    expect(conversationGate({ ...session, finished: true }, task)).toContain('已结束');
    expect(conversationGate(session, { ...task, archived: true })).toContain('归档');
    expect(conversationGate({ ...session, plan: { ...session.plan, maxTurns: 1 } }, task)).toContain('上限');
    expect(conversationGate({ ...session, plan: { ...session.plan, deadline: '2000-01-01T12:00' } }, task)).toContain('截止');
  });
  it('只有示例角色和示例资料组合会产生演示引用', () => {
    const plan = defaultPlan();
    expect(demoReply(plan, '权力').sourceIds).toHaveLength(2);
    expect(demoReply({ ...plan, sources: [] }, '权力').sourceIds).toEqual([]);
    expect(demoReply({ ...plan, roleName: '虚拟观察员' }, '权力').sourceIds).toEqual([]);
    expect(demoReply(plan, '请代写结论').sourceIds).toEqual([]);
  });
  it('行为统计只匹配学生表达，不把角色观点算作学生判断', () => {
    const session = createSession(publishTask(createTask(defaultPlan()), ['zihan']), 'zihan');
    session.messages = [
      { id: 'student-1', role: 'student', text: '我认为这个判断需要证据，也许还需要修正。', sourceIds: [], saved: false, stance: null },
      { id: 'character-1', role: 'character', text: '请继续核对材料。', sourceIds: [], saved: false, stance: null },
    ];
    session.viewedSources = ['source-qing'];
    expect(behaviorCounts([session])).toEqual({ 表达想法: 1, 寻找依据: 1, 查阅资料: 1, 作出判断: 1, 反思修正: 1 });
    const character = session.messages.find(item => item.role === 'character')!;
    character.text = '我认为有证据，也许还需要修正';
    expect(behaviorCounts([session]).作出判断).toBe(1);
    expect(turnCount(session)).toBe(1);
  });
  it('初始工作区不注入虚假演示任务或会话', () => {
    expect(seedWorkspace()).toEqual({ tasks: [], sessions: [], selectedTaskId: '', studentId: 'xiaoyu' });
  });
  it('空会话不填充虚假统计', () => {
    expect(behaviorCounts([])).toEqual({ 表达想法: 0, 寻找依据: 0, 查阅资料: 0, 作出判断: 0, 反思修正: 0 });
  });
});
