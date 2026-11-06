export interface Source {
  id: string;
  name: string;
  location: string;
  text: string;
  status: 'ready' | 'failed';
}

export interface Plan {
  title: string;
  intent: string;
  subject: string;
  grade: string;
  background: string;
  question: string;
  goal: string;
  historical: boolean;
  anchor: string;
  region: string;
  roleName: string;
  roleType: 'historical' | 'fictional';
  identity: string;
  boundary: string;
  opening: string;
  questions: string[];
  maxTurns: number;
  duration: number;
  deadline: string;
  sources: Source[];
}

export interface Publication {
  id: string;
  number: number;
  plan: Plan;
  audience: string[];
  createdAt: string;
}

export interface Task {
  id: string;
  backendTaskId?: string;
  backendDraftVersionId?: string;
  backendPublishedVersionId?: string;
  backendDraftRevision?: number;
  backendTaskRevision?: number;
  lastPlanRunId?: string;
  draft: Plan;
  publications: Publication[];
  archived: boolean;
  editing: boolean;
  updatedAt: string;
  review: string;
}

export type Stance = '需要更多证据' | '暂时赞同' | '有不同解释';
export interface ChatMessage {
  id: string;
  role: 'student' | 'character';
  text: string;
  sourceIds: string[];
  saved: boolean;
  stance: Stance | null;
}
export interface Session {
  id: string;
  taskId: string;
  publicationId: string;
  studentId: string;
  plan: Plan;
  messages: ChatMessage[];
  viewedSources: string[];
  corrections: string[];
  finished: boolean;
}
export interface Workspace {
  tasks: Task[];
  sessions: Session[];
  selectedTaskId: string;
  studentId: string;
}

export const students = [{ id: 'xiaoyu', name: '陈小雨' }, { id: 'zihan', name: '李子涵' }, { id: 'yinuo', name: '张一诺' }];
export const uid = () => crypto.randomUUID();
export const exampleSources: Source[] = [
  { id: 'source-qing', name: '清末身份与权力 · 演示讲义.pdf', location: '第 2 页', status: 'ready', text: '【自编教学示例，不能作为真实史料】\n退位意味着统治权力发生变化，而优待条件中的称号、居住等安排属于另一层面的身份待遇。称号的保留不能直接等同于政治权力的保留。\n阅读时请区分制度安排与个人感受。制度文本并不能证明一个年幼人物当时理解了哪些内容。' },
  { id: 'source-debate', name: '课堂讨论 · 两种解释.txt', location: '第 3—5 行', status: 'ready', text: '【自编讨论材料，不是真实人物原话】\n讨论主题：身份与权力是否总是一致？\n解释一：形式上的称号仍被保留，可以观察到身份待遇的延续。\n解释二：统治权力发生转移，不能仅凭称号断言政治权力没有改变。\n两种解释关注的层面不同，需要结合材料范围判断，不能自动选择其中一种作为唯一结论。' },
];

export function defaultPlan(): Plan {
  return {
    title: '清朝灭亡：从溥仪的视角出发',
    intent: '让八年级学生与溥仪对话，理解清朝灭亡时身份与权力的变化，并学会核对依据。',
    subject: '历史', grade: '八年级', historical: true, anchor: '1912-02-12', region: '北京 · 清宫',
    background: '1912 年，清朝统治走向终结。从一个年幼皇帝的有限视角，探究个人处境与时代转折之间的关系。',
    question: '从皇室成员的视角，我们能如何理解清朝灭亡？这一视角又有哪些局限？',
    goal: '区分事实、人物视角与推断；使用可核验资料形成解释；意识到单一角色无法代表完整历史。',
    roleName: '溥仪', roleType: 'historical',
    identity: '处于清末宫廷环境中的年幼皇帝。仅在资料支持的范围内表达公开处境，不将后世分析当作亲历或真实想法。',
    boundary: '未来事件、未经证实的私人动机和其他群体的完整处境，均无法确认。不仿造人物原话，不替学生写结论。',
    opening: '我是本次探究中模拟的溥仪。你可以从我的身份与处境开始提问，但我的视角有限。没有资料支持的事，我会明确说无法确认。',
    questions: ['退位后，身份与权力有什么区别？', '这些材料为什么给出不同解释？', '你的视角有哪些局限？'],
    maxTurns: 20, duration: 30, deadline: '', sources: structuredClone(exampleSources),
  };
}

export function blankPlan(): Plan {
  return { ...defaultPlan(), title: '', intent: '', background: '', question: '', goal: '', anchor: '', region: '', roleName: '', identity: '', opening: '', questions: [], sources: [] };
}

export function createTask(plan = blankPlan()): Task {
  return { id: uid(), draft: plan, publications: [], archived: false, editing: true, updatedAt: new Date().toISOString(), review: '' };
}

export function validatePlan(plan: Plan): string[] {
  const missing: string[] = [];
  for (const [key, label] of [['title', '主题名称'], ['background', '主题背景'], ['question', '核心问题'], ['goal', '探究目标'], ['roleName', '角色名称'], ['identity', '角色介绍'], ['opening', '开场情境']] as const) {
    if (!plan[key].trim()) missing.push(`请补充${label}`);
  }
  if (plan.historical && !/^\d{4}(-\d{2}){0,2}$/.test(plan.anchor)) missing.push('请填写故事发生的时间（如 1912、1912-02 或 1912-02-12）');
  else if (plan.historical) {
    const fullDate = plan.anchor.length === 4 ? `${plan.anchor}-01-01` : plan.anchor.length === 7 ? `${plan.anchor}-01` : plan.anchor;
    const date = new Date(`${fullDate}T00:00:00Z`);
    if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, plan.anchor.length) !== plan.anchor) missing.push('故事发生的时间不是有效日期');
  }
  if (!Number.isInteger(plan.maxTurns) || plan.maxTurns < 1 || plan.maxTurns > 30) missing.push('对话轮次应为 1—30 轮');
  if (!Number.isInteger(plan.duration) || plan.duration < 5 || plan.duration > 120) missing.push('建议时长应为 5—120 分钟');
  if (plan.deadline && (!Number.isFinite(Date.parse(plan.deadline)) || Date.parse(plan.deadline) <= Date.now())) missing.push('请设置未来的截止时间，或留空');
  if (plan.sources.some(source => source.status !== 'ready')) missing.push('请移除未能读取的资料后再发布');
  return missing;
}

export function publishTask(task: Task, audience: string[]): Task {
  const errors = validatePlan(task.draft);
  if (task.archived) errors.push('请先恢复已归档任务');
  if (!task.editing) errors.push('当前方案已经发布');
  if (!audience.length || audience.some(id => !students.some(student => student.id === id))) errors.push('请选择有效的发布学生');
  if (errors.length) throw new Error(errors.join('；'));
  const publication: Publication = { id: uid(), number: task.publications.length + 1, plan: structuredClone(task.draft), audience: [...audience], createdAt: new Date().toISOString() };
  return { ...task, editing: false, publications: [...task.publications, publication], updatedAt: new Date().toISOString() };
}

export function createSession(task: Task, studentId: string): Session {
  const publication = task.publications.at(-1);
  if (task.archived || !publication?.audience.includes(studentId)) throw new Error('这个任务尚未向当前学生账号开放。');
  if (publication.plan.deadline && Date.parse(publication.plan.deadline) <= Date.now()) throw new Error('任务已截止，不能开始新的探究。');
  return { id: uid(), taskId: task.id, publicationId: publication.id, studentId, plan: structuredClone(publication.plan), messages: [], viewedSources: [], corrections: [], finished: false };
}

export const behaviorLabels = ['表达想法', '寻找依据', '查阅资料', '作出判断', '反思修正'] as const;
export type Behavior = typeof behaviorLabels[number];
export function evidenceFor(session: Session, behavior: Behavior): ChatMessage[] {
  const own = session.messages.filter(item => item.role === 'student');
  if (behavior === '表达想法') return own;
  if (behavior === '寻找依据') return own.filter(item => /依据|证据|材料|来源|为什么/.test(item.text));
  if (behavior === '作出判断') return own.filter(item => /我认为|我觉得|我判断|我的看法/.test(item.text));
  if (behavior === '反思修正') return own.filter(item => /不确定|修正|原来|局限|也许|可能|还需要/.test(item.text));
  return [];
}
export function behaviorCounts(sessions: Session[]): Record<Behavior, number> {
  return Object.fromEntries(behaviorLabels.map(label => [label, sessions.reduce((sum, session) => sum + (label === '查阅资料' ? session.viewedSources.length : evidenceFor(session, label).length), 0)])) as Record<Behavior, number>;
}
export function turnCount(session: Session): number {
  return session.messages.filter(item => item.role === 'character').length;
}
export function conversationGate(session: Session, task: Task | undefined): string {
  if (session.finished) return '本次探究已结束，对话和摘录为只读。你仍可补充或更正学习报告。';
  if (!task || task.archived) return '任务已归档，保留对话和学习报告，不再接受新提问。';
  if (session.plan.deadline && Date.parse(session.plan.deadline) <= Date.now()) return '任务已截止，可以查看报告并结束探究。';
  if (turnCount(session) >= session.plan.maxTurns) return '已达到本次对话轮次上限，可以查看报告并结束探究。';
  return '';
}

export function demoReply(plan: Plan, question: string): Pick<ChatMessage, 'text' | 'sourceIds'> {
  if (/未来|后来|之后|结论|代写|提示词/.test(question)) return { text: '这超出了本次角色的认知边界。我不能以角色身份知道未来，也不能代替你形成最终结论。你可以结合已经看到的材料，说说自己的判断，以及还不能确认的部分。', sourceIds: [] };
  const sources = plan.sources.filter(source => source.status === 'ready' && exampleSources.some(example => example.id === source.id));
  if (plan.roleName === '溥仪' && sources.length) return { text: '从这份演示讲义来看，身份待遇和实际政治权力需要分开讨论。保留某种称号，并不能直接证明仍拥有原先的统治权力。\n\n这是根据教学材料作出的角色表达，不是人物本人的真实原话，也不能据此推断当时的私人感受。\n\n你觉得材料中的哪一句能支持这个区分？如果从宫墙外的人们出发，又可能看到什么？', sourceIds: sources.map(source => source.id) };
  return { text: `作为“${plan.roleName}”这一教学角色，我的表达受到本次资料与情境的限制。当前演示没有足够依据回答这个具体问题，不能编造事实或引用。\n\n围绕“${plan.question}”，你已经观察到了什么？哪些是材料明确说明的，哪些还只是你的推测？`, sourceIds: [] };
}

export function seedWorkspace(): Workspace {
  return { tasks: [], sessions: [], selectedTaskId: '', studentId: 'xiaoyu' };
}
