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
  it('provides keyboard-navigable context tabs and a close action', () => {
    const onClose = vi.fn()
    const onPanelChange = vi.fn()

    render(<ResearchContextRail onClose={onClose} onPanelChange={onPanelChange} />)

    expect(screen.getAllByRole('tab')).toHaveLength(4)
    expect(screen.getByRole('tab', { name: 'Agent' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Agent' })).toBeVisible()

    const agentTab = screen.getByRole('tab', { name: 'Agent' })
    fireEvent.keyDown(agentTab, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Activity' })).toHaveFocus()
    expect(onPanelChange).toHaveBeenCalledWith('activity')

    fireEvent.click(screen.getByRole('button', { name: '关闭上下文栏' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('renders real activity records and delegates selection to the host', () => {
    const onActivitySelect = vi.fn()

    render(
      <ResearchContextRail
        activities={[activity]}
        onActivitySelect={onActivitySelect}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Activity' }))

    const panel = screen.getByRole('tabpanel', { name: 'Activity' })
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
        citations={[citation]}
        onCitationSelect={onCitationSelect}
        selectedCitationId={citation.id}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Sources' }))

    const panel = screen.getByRole('tabpanel', { name: 'Sources' })
    expect(panel).toHaveTextContent('知识条目 · D1:C029')
    expect(panel.querySelector(`[data-citation-id="${citation.id}"]`)).toHaveAttribute(
      'aria-current',
      'true',
    )

    fireEvent.click(within(panel).getByRole('button', { name: /社会行动四类型/ }))
    expect(onCitationSelect).toHaveBeenCalledWith(citation)
  })

  it('uses host-provided basis content and keeps the empty state honest', () => {
    const { rerender } = render(
      <ResearchContextRail basisContent={<p>来自当前条目的证据正文。</p>} />,
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Basis' }))
    expect(screen.getByRole('tabpanel', { name: 'Basis' })).toHaveTextContent(
      '来自当前条目的证据正文。',
    )

    rerender(<ResearchContextRail />)
    fireEvent.click(screen.getByRole('tab', { name: 'Basis' }))
    expect(screen.getByRole('tabpanel', { name: 'Basis' })).toHaveTextContent(
      '选择一条来源后，这里会显示它的依据。',
    )
  })
})
