import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CanvasCardEditor } from './CanvasCardEditor'
import { saveCanvasNode, getAgentConversation, type AgentConversation } from '../../modules/research-agent'
vi.mock('../../modules/research-agent', async importOriginal => ({ ...await importOriginal<object>(), saveCanvasNode: vi.fn(), getAgentConversation: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
const node = { id: 'claim-1', kind: 'claim' as const, title: '原主张', summary: '原说明', status: 'developing' as const, citation_ids: ['real-source'] }
const conversation = { conversation_id: 'conv-1', canvas_edit_version: 3, turns: [], research_map: { schema_version: 1, nodes: [node], relations: [] } } as unknown as AgentConversation
it('saves the stable ID and original version without sending modified evidence', async () => {
  const saved = { ...conversation, canvas_edit_version: 4 }
  vi.mocked(saveCanvasNode).mockResolvedValue(saved)
  const onSaved = vi.fn()
  render(<CanvasCardEditor conversation={conversation} node={node} onSaved={onSaved} />)
  fireEvent.click(screen.getByText('编辑卡片'))
  fireEvent.change(screen.getByLabelText('标题'), { target: { value: '用户修改的主张' } })
  fireEvent.click(screen.getByText('保存修改'))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved))
  expect(saveCanvasNode).toHaveBeenCalledWith('conv-1', 'claim-1', { title: '用户修改的主张', summary: '原说明', expected_title: '原主张', expected_summary: '原说明', expected_version: 3 })
})
it('retains the draft after a conflict and requires another save after reloading', async () => {
  vi.mocked(saveCanvasNode).mockRejectedValue(new Error('卡片已在另一处更新'))
  vi.mocked(getAgentConversation).mockResolvedValue({ ...conversation, canvas_edit_version: 4, research_map: { ...conversation.research_map!, nodes: [{ ...node, title: '另一处修改' }] } })
  render(<CanvasCardEditor conversation={conversation} node={node} onSaved={() => {}} />)
  fireEvent.click(screen.getByText('编辑卡片'))
  fireEvent.change(screen.getByLabelText('标题'), { target: { value: '我的草稿' } })
  fireEvent.click(screen.getByText('保存修改'))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('标题')).toHaveValue('我的草稿')
  fireEvent.click(screen.getByText('载入最新版本，保留草稿'))
  await screen.findByText('已载入最新原文。请与下面的草稿核对后再保存。')
  expect(screen.getByLabelText('标题')).toHaveValue('我的草稿')
  expect(saveCanvasNode).toHaveBeenCalledTimes(1)
})
