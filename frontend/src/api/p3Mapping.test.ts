import { describe, expect, it } from 'vitest';
import { defaultPlan } from '../demo/model';
import { planFromVersion, versionPatchFromPlan } from './p3Mapping';
import type { VersionView } from './tasks';

function generatedVersion(): VersionView {
  return {
    id: 'version-1', taskId: 'task-1', versionNo: 1, revision: 2, status: 'draft',
    teachingIntent: '让八年级学生探究身份变化',
    brief: {
      topicName: '身份与权力', subject: '历史', grade: '八年级', background: '历史背景',
      learningGoals: ['区分身份与权力'], coreQuestion: '两者有何不同？', isHistoricalTopic: true,
      timeAnchor: { value: '1912', precision: 'year' }, region: '中国', roleName: '溥仪',
      restrictions: { maxTurns: 10, suggestedMinutes: 35, deadlineAt: null },
    },
    questionPlan: [{ question: '退位改变了什么？', dimension: '身份', purpose: '形成解释' }],
    roleCard: {
      roleId: 'role-1', name: '溥仪', roleType: 'real_historical', identityDescription: '历史角色',
      historicalPeriod: '1912年', timeAnchor: { value: '1912', precision: 'year' }, region: '中国',
      socialGroup: '皇室', position: '退位皇帝', goals: [], concerns: [], relationships: [], knownFacts: [],
      unknownFacts: ['未来事件'], sourceIds: [], disputedClaims: [], speechStyle: '克制',
      openingMessage: '你想了解什么？', recommendedQuestions: ['身份有什么变化？'],
      learningDimension: '身份', forbiddenBehaviors: ['不编造', '不越界', '不代写'],
    },
    sourceIds: [], manualFields: [], generationMeta: {}, validationStatus: 'stale',
    validatedRevision: null, previewRevision: null, missingFields: [], nextQuestions: [],
  };
}

describe('P3 方案映射', () => {
  it('把后端生成方案映射为现有教师界面字段', () => {
    const plan = planFromVersion(generatedVersion(), defaultPlan());
    expect(plan).toMatchObject({
      title: '身份与权力', intent: '让八年级学生探究身份变化', anchor: '1912',
      roleName: '溥仪', identity: '历史角色', maxTurns: 10, duration: 35,
    });
    expect(plan.questions).toEqual(['身份有什么变化？']);
    expect(plan.boundary).toContain('未来事件');
  });

  it('把教师编辑转换为 B07 的完整字段更新', () => {
    const patch = versionPatchFromPlan({ ...defaultPlan(), anchor: '1912-02', deadline: '' });
    expect(patch.teachingIntent).toContain('八年级');
    expect(patch.brief.timeAnchor).toEqual({ value: '1912-02', precision: 'month' });
    expect(patch.brief.roleType).toBe('real_historical');
    expect(patch.questionPlan).toHaveLength(3);
  });
});
