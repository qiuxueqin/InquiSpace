import type { Plan } from '../demo/model';
import type { RoleCardView, VersionView } from './tasks';

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function timeAnchor(value: unknown): string {
  if (typeof value !== 'object' || value === null || !('value' in value)) return '';
  return text((value as { value?: unknown }).value);
}

function roleBoundary(role: RoleCardView): string {
  const unknown = role.unknownFacts.length ? `未知范围：${role.unknownFacts.join('；')}。` : '';
  const forbidden = role.forbiddenBehaviors.length ? `行为边界：${role.forbiddenBehaviors.join('；')}。` : '';
  return `${unknown}${forbidden}`.trim();
}

export function planFromVersion(version: VersionView, previous: Plan): Plan {
  const brief = version.brief;
  const role = version.roleCard;
  const restrictions = typeof brief.restrictions === 'object' && brief.restrictions !== null
    ? brief.restrictions as Record<string, unknown>
    : {};
  const goals = strings(brief.learningGoals);
  const questionPlan = version.questionPlan
    .map(item => text(item.question))
    .filter(Boolean)
    .slice(0, 3);
  return {
    ...previous,
    title: text(brief.topicName, previous.title),
    intent: version.teachingIntent,
    subject: text(brief.subject, previous.subject),
    grade: text(brief.grade, previous.grade),
    background: text(brief.background, previous.background),
    question: text(brief.coreQuestion, previous.question),
    goal: goals.join('；') || previous.goal,
    historical: typeof brief.isHistoricalTopic === 'boolean' ? brief.isHistoricalTopic : previous.historical,
    anchor: timeAnchor(brief.timeAnchor) || previous.anchor,
    region: text(brief.region, previous.region),
    roleName: role?.name ?? text(brief.roleName, previous.roleName),
    roleType: role?.roleType === 'fictional_composite' ? 'fictional' : 'historical',
    identity: role?.identityDescription ?? previous.identity,
    boundary: role ? roleBoundary(role) : previous.boundary,
    opening: role?.openingMessage ?? previous.opening,
    questions: role?.recommendedQuestions.length ? role.recommendedQuestions : (questionPlan.length ? questionPlan : previous.questions),
    maxTurns: Number.isInteger(restrictions.maxTurns) ? Number(restrictions.maxTurns) : previous.maxTurns,
    duration: Number.isInteger(restrictions.suggestedMinutes) ? Number(restrictions.suggestedMinutes) : previous.duration,
    deadline: text(restrictions.deadlineAt).replace(/Z$/, '').slice(0, 16) || previous.deadline,
  };
}

function anchorPrecision(anchor: string): 'year' | 'month' | 'day' {
  return anchor.length === 4 ? 'year' : anchor.length === 7 ? 'month' : 'day';
}

export function roleInputFromPlan(plan: Plan, version: VersionView) {
  const current = version.roleCard;
  return {
    name: plan.roleName || current?.name || '待确认角色',
    roleType: plan.roleType === 'historical' ? 'real_historical' as const : 'fictional_composite' as const,
    identityDescription: plan.identity || current?.identityDescription || '身份尚待教师确认',
    historicalPeriod: plan.historical ? (plan.anchor || current?.historicalPeriod || '时间待确认') : '非历史情境',
    timeAnchor: plan.historical && plan.anchor
      ? { value: plan.anchor, precision: anchorPrecision(plan.anchor) }
      : null,
    region: plan.region || current?.region || '未限定',
    socialGroup: current?.socialGroup || '未限定',
    position: current?.position || plan.identity || '未限定',
    goals: current?.goals ?? [],
    concerns: current?.concerns ?? [],
    relationships: current?.relationships ?? [],
    knownFacts: current?.knownFacts ?? [],
    unknownFacts: current?.unknownFacts ?? ['未获得资料支持的事实'],
    sourceIds: current?.sourceIds.filter(id => version.sourceIds.includes(id)) ?? [],
    disputedClaims: current?.disputedClaims ?? [],
    speechStyle: current?.speechStyle || '清楚说明角色视角与认知边界',
    openingMessage: plan.opening || current?.openingMessage || '你想从什么问题开始探究？',
    recommendedQuestions: plan.questions.filter(Boolean).slice(0, 3),
    learningDimension: current?.learningDimension || plan.goal || '依据与解释',
    forbiddenBehaviors: current?.forbiddenBehaviors.length
      ? current.forbiddenBehaviors
      : ['不编造事实或私人动机', '不越过时间与认知边界', '不替学生代写结论'],
  };
}

export function versionPatchFromPlan(plan: Plan) {
  return {
    teachingIntent: plan.intent,
    brief: {
      topicName: plan.title || null,
      background: plan.background || null,
      subject: plan.subject || null,
      grade: plan.grade || null,
      learningGoals: plan.goal.trim() ? [plan.goal.trim()] : [],
      coreQuestion: plan.question || null,
      isHistoricalTopic: plan.historical,
      timeAnchor: plan.anchor ? { value: plan.anchor, precision: anchorPrecision(plan.anchor) } : null,
      region: plan.region || null,
      roleType: plan.roleType === 'historical' ? 'real_historical' : 'fictional_composite',
      roleName: plan.roleName || null,
      materialPolicy: { externalKnowledgeAllowed: false, externalKnowledgeScope: '' },
      restrictions: {
        maxTurns: plan.maxTurns,
        suggestedMinutes: plan.duration,
        deadlineAt: plan.deadline ? new Date(plan.deadline).toISOString() : null,
        difficulty: plan.grade || '未限定',
        forbiddenContent: [],
      },
      expectedOutcome: plan.goal || '在对话中提出问题并依据资料形成解释',
      confirmedFields: [],
    },
    questionPlan: plan.questions.filter(Boolean).map(question => ({
      question,
      dimension: '探究问题',
      purpose: '引导学生提出依据并辨认视角局限',
    })),
  };
}
