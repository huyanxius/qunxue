import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ResearchContextRail,
  type ResearchActivity,
  type ResearchCitation,
} from './ResearchContextRail'

afterEach(cleanup)

const activity: ResearchActivity = {
  id: 'activity-1',
  tool: 'search_knowledge',
  label: '检索知识库',
  status: 'completed',
  input: { query: '社会行动四类型' },
  detail: '检索完成，返回 1 条结果。',
  resultItems: [
    {
      id: 'entry-1',
      title: '社会行动四类型',
      excerpt: '韦伯将社会行动区分为四类。',
    },
  ],
}

const citation: ResearchCitation = {
  id: 'citation-1',
  title: '社会行动四类型',
  kind: 'knowledge',
  subtitle: '知识条目 · D1:C029',
  excerpt: '韦伯将社会行动区分为目的理性、价值理性、情感和传统四类。',
}

describe('ResearchContextRail', () => {
  it('shows one direct panel without a second set of navigation controls', () => {
    const onClose = vi.fn()

    render(<ResearchContextRail activeTab="activity" onClose={onClose} />)

    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: '活动' })).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: '关闭上下文栏' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('renders real activity records and delegates selection to the host', () => {
    const onActivitySelect = vi.fn()

    render(
      <ResearchContextRail
        activeTab="activity"
        activities={[activity]}
        onActivitySelect={onActivitySelect}
      />,
    )

    const panel = screen.getByRole('region', { name: '活动' })
    expect(panel).toHaveTextContent('检索知识库')
    expect(panel).toHaveTextContent('检索完成，返回 1 条结果。')
    expect(panel).toHaveTextContent('社会行动四类型')
    expect(panel).toHaveTextContent('韦伯将社会行动区分为四类。')

    fireEvent.click(within(panel).getByRole('button', { name: /检索知识库/ }))
    expect(onActivitySelect).toHaveBeenCalledWith(activity)
  })

  it('renders citations without adding records and reports the selected citation', () => {
    const onCitationSelect = vi.fn()

    render(
      <ResearchContextRail
        activeTab="sources"
        citations={[citation]}
        onCitationSelect={onCitationSelect}
        selectedCitationId={citation.id}
      />,
    )

    const panel = screen.getByRole('region', { name: '来源' })
    expect(panel).toHaveTextContent('知识条目 · D1:C029')
    expect(panel.querySelector(`[data-citation-id="${citation.id}"]`)).toHaveAttribute(
      'aria-current',
      'true',
    )

    fireEvent.click(within(panel).getByRole('button', { name: /社会行动四类型/ }))
    expect(onCitationSelect).toHaveBeenCalledWith(citation)
  })

  it('splits knowledge, web and workflow into one stacked panel', () => {
    const webCitation: ResearchCitation = {
      id: 'citation-web-1',
      title: '高校毕业生就业政策',
      kind: 'source',
      subtitle: '来源 · gov.cn',
      group: 'web',
    }

    render(
      <ResearchContextRail
        variant="sections"
        activeTab="sources"
        activities={[activity]}
        citations={[{ ...citation, group: 'knowledge' }, webCitation]}
        elapsedSeconds={39}
      />,
    )

    const panel = screen.getByRole('region', { name: '研究面板' })
    expect(within(panel).getByRole('group', { name: '知识库' })).toHaveTextContent('知识条目 · D1:C029')
    expect(within(panel).getByRole('group', { name: '网页' })).toHaveTextContent('高校毕业生就业政策')
    expect(within(panel).getByRole('group', { name: '知识库' })).not.toHaveTextContent('高校毕业生就业政策')
    const workflow = within(panel).getByRole('group', { name: '工作流程' })
    expect(workflow).toHaveTextContent('检索知识库')
    expect(panel).toHaveTextContent('用时 39 秒')
  })

  it('says what is still missing instead of hiding an empty section', () => {
    render(<ResearchContextRail variant="sections" activeTab="sources" />)

    const panel = screen.getByRole('region', { name: '研究面板' })
    expect(within(panel).getByRole('group', { name: '网页' })).toHaveTextContent('这次回答还没有读取网页。')
    expect(within(panel).queryByRole('group', { name: '研究材料' })).not.toBeInTheDocument()
  })

  it('returns from a basis view to the stacked panel', () => {
    const onBack = vi.fn()

    render(
      <ResearchContextRail
        variant="sections"
        activeTab="basis"
        basisContent={<p>来自当前条目的证据正文。</p>}
        onBack={onBack}
      />,
    )

    expect(screen.getByRole('region', { name: '依据' })).toHaveTextContent('来自当前条目的证据正文。')
    fireEvent.click(screen.getByRole('button', { name: '依据' }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('uses host-provided basis content and keeps the empty state honest', () => {
    const { rerender } = render(
      <ResearchContextRail activeTab="basis" basisContent={<p>来自当前条目的证据正文。</p>} />,
    )

    expect(screen.getByRole('region', { name: '依据' })).toHaveTextContent(
      '来自当前条目的证据正文。',
    )

    rerender(<ResearchContextRail activeTab="basis" />)
    expect(screen.getByRole('region', { name: '依据' })).toHaveTextContent(
      '选择一条来源后，这里会显示它的依据。',
    )
  })
})
