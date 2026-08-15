import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ResearchFrameworkWorkspace,
  type ResearchFrameworkView,
} from './ResearchFrameworkWorkspace'


const framework: ResearchFrameworkView = {
  frameworkId: 'framework-1',
  revisionId: 'revision-1',
  version: 1,
  status: 'revision_required',
  contentOrigin: 'system_generated',
  revisionReason: null,
  confirmedResearchQuestion: '成员流动如何影响社区互助？',
  theoryPlan: ['社会资本理论：解释重复互动与互惠规范'],
  conceptMappings: [{
    candidateId: 'candidate-1',
    theoryConcept: '重复互动',
    meaningInStudy: '成员之间稳定出现的联系',
    empiricalIndicators: ['互助频率'],
    unresolvedQuestions: ['如何区分资源效应？'],
  }],
  materialRequirements: ['去标识化互动记录'],
  evidenceConstraints: ['支持：重复互动增加时互助更稳定', '排除：两者无可观察联系'],
  alternativeExplanations: ['资源供给变化'],
  ethicalBoundaries: ['不上传未授权的原始材料'],
  nextActions: ['补充去标识化访谈摘要'],
  scopeAndLimitations: ['仅解释已确认现象'],
  unresolvedItems: ['缺少区分性材料'],
  audit: {
    auditId: 'audit-1',
    isStale: false,
    findings: [{
      findingId: 'finding-1',
      severity: 'blocking',
      summary: '区分性证据不足',
      reason: '草稿仍保留未解决项',
      impact: '无法排除替代解释',
      recommendation: '补充区分性材料并重新审校',
      blocking: true,
    }],
  },
}

afterEach(cleanup)


describe('ResearchFrameworkWorkspace', () => {
  it('区分系统草稿并展示完整研究框架', () => {
    render(
      <ResearchFrameworkWorkspace
        framework={framework}
        versions={[framework]}
        onSave={vi.fn()}
        onReview={vi.fn()}
        onResolve={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )

    expect(screen.getAllByText('系统草稿')).toHaveLength(2)
    expect(screen.getByRole('heading', { name: '研究问题' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '理论方案' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '概念映射' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '材料要求' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '证据约束' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '替代解释' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '伦理边界' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '下一步行动' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '材料要求' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '证据约束' })).not.toBeInTheDocument()
  })

  it('保存用户修改时提交新版本理由', () => {
    const onSave = vi.fn()
    render(
      <ResearchFrameworkWorkspace
        framework={framework}
        versions={[framework]}
        onSave={onSave}
        onReview={vi.fn()}
        onResolve={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('下一步行动'), {
      target: { value: '补充时间序列\n核对竞争解释' },
    })
    fireEvent.change(screen.getByLabelText('修改理由'), {
      target: { value: '明确补充材料的顺序' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存为新版本' }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      nextActions: ['补充时间序列', '核对竞争解释'],
    }), '明确补充材料的顺序')
  })

  it('覆盖阻断意见时必须填写理由', () => {
    const onResolve = vi.fn()
    render(
      <ResearchFrameworkWorkspace
        framework={framework}
        versions={[framework]}
        onSave={vi.fn()}
        onReview={vi.fn()}
        onResolve={onResolve}
        onConfirm={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('处理方式'), { target: { value: 'override' } })
    fireEvent.click(screen.getByRole('button', { name: '保存审校处理' }))
    expect(screen.getByText('覆盖阻断意见必须说明理由。')).toBeInTheDocument()
    expect(onResolve).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('处理理由'), {
      target: { value: '当前仅做探索性研究，将该限制保留在最终框架中' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存审校处理' }))
    expect(onResolve).toHaveBeenCalledWith([{
      findingId: 'finding-1',
      action: 'override',
      reason: '当前仅做探索性研究，将该限制保留在最终框架中',
    }])
  })

  it('暂缓或拒绝审校意见也必须记录理由', () => {
    const onResolve = vi.fn()
    render(
      <ResearchFrameworkWorkspace
        framework={framework}
        versions={[framework]}
        onSave={vi.fn()}
        onReview={vi.fn()}
        onResolve={onResolve}
        onConfirm={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '保存审校处理' }))

    expect(screen.getByRole('alert')).toHaveTextContent('每条审校处理都必须记录理由。')
    expect(onResolve).not.toHaveBeenCalled()
  })

  it('只有明确覆盖全部阻断意见并填写理由后才允许确认', () => {
    render(
      <ResearchFrameworkWorkspace
        framework={framework}
        versions={[framework]}
        onSave={vi.fn()}
        onReview={vi.fn()}
        onResolve={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )

    const confirm = screen.getByRole('button', { name: '由我确认框架' })
    expect(confirm).toBeDisabled()

    fireEvent.change(screen.getByLabelText('处理方式'), { target: { value: 'override' } })
    expect(confirm).toBeDisabled()

    fireEvent.change(screen.getByLabelText('处理理由'), {
      target: { value: '保留限制并承担判断责任' },
    })
    expect(confirm).toBeEnabled()
  })

  it('允许暂不处理非阻断建议并以空处理集确认', () => {
    const onConfirm = vi.fn()
    const ready = {
      ...framework,
      status: 'ready_to_confirm' as const,
      audit: {
        ...framework.audit!,
        findings: [{ ...framework.audit!.findings[0]!, blocking: false, severity: 'warning' as const }],
      },
    }
    render(
      <ResearchFrameworkWorkspace
        framework={ready}
        versions={[ready]}
        onSave={vi.fn()}
        onReview={vi.fn()}
        onResolve={vi.fn()}
        onConfirm={onConfirm}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '由我确认框架' }))

    expect(onConfirm).toHaveBeenCalledWith([])
  })
})
