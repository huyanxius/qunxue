import { describe, expect, it } from 'vitest'

import { createEmptyResearchCanvasProjection } from './researchCanvasProjection'
import { projectFormalResearchCanvas } from './formalResearchCanvasProjection'

describe('formal research canvas projection', () => {
  it('rebuilds an identical map from the same server snapshots', () => {
    const input = {
      taskId: 'task-1',
      mode: 'match' as const,
      agentProjection: createEmptyResearchCanvasProjection(),
      navigation: {
        phenomenon_summary: {
          phenomenon: '社区互助为何减少？',
          research_intent: '解释重复互动机会的变化机制',
        },
      },
      matchRun: {
        candidate_page: {
          candidates: [{
            candidate_id: 'candidate-1',
            title: '社会资本理论',
            applicability_rationale: '可解释稳定关系如何支持互助。',
            problem_focus: '稳定关系与互惠规范',
            source_ids: ['source-theory-1'],
            supporting_evidence: [{
              evidence_ref_id: 'evidence-1',
              claim: '重复互动有助于形成互惠预期。',
              excerpt: '稳定交往使互惠规范更容易维持。',
              locator: 'p.12',
              source_id: 'source-evidence-1',
            }],
            conflicting_evidence: [],
          }],
        },
      },
      pendingTheoryDecisions: {
        'candidate-1': { action: 'adopt' as const },
      },
      sections: [{
        section_id: 'research_question',
        title: '研究问题',
        content: '社区中的重复互动机会如何影响互助？',
        status: 'confirmed',
        evidence_refs: [{ source_id: 'source-evidence-1' }],
      }],
      documentTitle: '社区互助研究',
    }
    const original = structuredClone(input)

    const first = projectFormalResearchCanvas(input)
    const second = projectFormalResearchCanvas(input)

    expect(second).toEqual(first)
    expect(input).toEqual(original)
    expect(first.question).toBe('社区互助为何减少？')
    expect(first.nodes.map((node) => node.id)).toEqual([
      'research-question:task-1',
      'research-phenomenon:task-1',
      'research-theory:candidate-1',
      'research-evidence:evidence-1',
      'research-section:task-1:match:research_question',
    ])
    expect(first.edges.map((edge) => edge.id)).toEqual([
      'research-phenomenon-edge:task-1',
      'research-theory-edge:candidate-1',
      'research-support:candidate-1:evidence-1',
      'research-section-edge:0:research-section:task-1:match:research_question',
    ])
  })

  it('projects only researcher-confirmed case comparisons into M4 evidence, gaps, and theory implications', () => {
    const projection = projectFormalResearchCanvas({
      taskId: 'task-1',
      mode: 'match',
      agentProjection: createEmptyResearchCanvasProjection(),
      navigation: null,
      matchRun: null,
      pendingTheoryDecisions: {},
      sections: [],
      analysisSnapshot: {
        comparisons: [
          {
            comparison_id: 'comparison-confirmed',
            title: '迁移前后的照护责任',
            question: '迁移如何改变家庭照护分工？',
            status: 'confirmed',
            findings: [
              { kind: 'support', statement: '跨城务工后日常照护转向祖辈。', annotation_ids: ['annotation-support'] },
              { kind: 'counterexample', statement: '案例乙仍由父亲承担日常照护。', annotation_ids: ['annotation-counter'] },
              { kind: 'contradict', statement: '同一家庭对责任归属的叙述不一致。', annotation_ids: ['annotation-conflict'] },
              { kind: 'competing_explanation', statement: '收入差异可能比迁移本身更关键。', annotation_ids: [] },
              { kind: 'evidence_gap', statement: '缺少留守家庭的长期观察。', annotation_ids: [] },
            ],
            competing_explanations: ['收入差异可能比迁移本身更关键。'],
            evidence_gaps: ['缺少留守家庭的长期观察。'],
            next_steps: [{ kind: 'interview', action: '追问家庭成员如何协商照护责任。', priority: 'high' }],
            theory_implication: '需要把迁移机制修订为受家庭资源条件约束的责任重组。',
          },
          {
            comparison_id: 'comparison-candidate',
            title: '尚未确认的 Agent 比较',
            question: '候选问题',
            status: 'candidate',
            findings: [],
            competing_explanations: [],
            evidence_gaps: [],
            next_steps: [],
            theory_implication: '不得进入 M4',
          },
          {
            comparison_id: 'comparison-rejected',
            title: '已拒绝的比较',
            question: '已拒绝问题',
            status: 'rejected',
            findings: [],
            competing_explanations: [],
            evidence_gaps: [],
            next_steps: [],
            theory_implication: '不得进入 M4',
          },
        ],
      },
    })

    expect(projection.nodes.map((node) => [node.kind, node.title])).toEqual([
      ['question', '当前研究问题'],
      ['synthesis', '迁移前后的照护责任'],
      ['evidence', '跨城务工后日常照护转向祖辈。'],
      ['evidence', '案例乙仍由父亲承担日常照护。'],
      ['evidence', '同一家庭对责任归属的叙述不一致。'],
      ['theory', '收入差异可能比迁移本身更关键。'],
      ['gap', '缺少留守家庭的长期观察。'],
      ['gap', '追问家庭成员如何协商照护责任。'],
      ['theory', '案例比较形成的理论判断'],
    ])
    expect(projection.nodes.find((node) => node.title.startsWith('跨城务工'))?.citationIds).toEqual(['annotation-support'])
    expect(projection.nodes.at(-1)?.summary).toBe('需要把迁移机制修订为受家庭资源条件约束的责任重组。')
    expect(projection.edges.map((edge) => edge.label)).toEqual([
      '已确认比较',
      '支持证据',
      '反例',
      '矛盾材料',
      '竞争解释',
      '证据缺口',
      '下一步研究',
      '修订理论判断',
    ])
    expect(projection.nodes.some((node) => node.title.includes('Agent'))).toBe(false)
    expect(projection.nodes.some((node) => node.title.includes('已拒绝'))).toBe(false)
  })
})
