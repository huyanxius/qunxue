import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ResearchCyclePanel } from './ResearchCyclePanel'

describe('ResearchCyclePanel', () => {
  it('shows traceable gap routing and non-blocking reporting coverage without a score or approval action', () => {
    render(<ResearchCyclePanel snapshot={{
      schema_version: 'research-cycle-v1',
      task_id: 'task-1',
      version: 4,
      content_hash: 'sha256:cycle-4',
      analysis_content_hash: 'sha256:analysis-3',
      theory_plan_id: 'theory-plan-1',
      theory_plan_version: 2,
      evidence: [],
      gaps: [{
        gap_id: 'gap-1',
        source_kind: 'analysis',
        source_id: 'comparison-1',
        description: '缺少照护者的长期观察。',
        suggested_action: '在下一轮补充两次跟访。',
        destination: 'sampling',
        priority: 'high',
        analysis_content_hash: 'sha256:analysis-3',
        theory_plan_id: 'theory-plan-1',
        theory_plan_version: 2,
        status: 'open',
      }],
      project_facts: {
        material_count: 1,
        material_kinds: [['interview_transcript', 1]],
        case_count: 1,
        case_material_coverage: [['家庭甲', 1]],
        consent_scopes: [['project_only', 1]],
        sensitivity_levels: [['sensitive', 1]],
        pending_deidentification_count: 0,
        sampling_batches: ['第一轮'],
        analysis_counts: [['codes', 1], ['memos', 0], ['comparisons', 1]],
      },
      reporting_hints: [{
        guideline: 'COREQ',
        item_key: 'researcher_characteristics',
        label: '研究者特征与反思',
        status: 'missing',
        message: '报告时补充研究者位置与反思。',
        blocking: false,
      }],
      research_map_patch: { nodes: [], relations: [] },
    }} />)

    expect(screen.getByRole('region', { name: '证据缺口与下一轮材料' })).toHaveTextContent('缺少照护者的长期观察。')
    expect(screen.getByText('下一轮取样')).toBeInTheDocument()
    expect(screen.getByText('高优先级')).toBeInTheDocument()
    expect(screen.getByText('依据：分析 comparison-1 · 理论计划 v2 · 循环 v4')).toBeInTheDocument()
    expect(screen.getByText('COREQ · 研究者特征与反思')).toBeInTheDocument()
    expect(screen.getByText('只提示报告覆盖，不影响理论或方法判断。')).toBeInTheDocument()
    expect(screen.queryByText(/质量分|确认方法|批准/)).not.toBeInTheDocument()
  })
})
