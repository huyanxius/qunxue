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
})
