import { AgentMaterialAttachmentPicker } from './AgentMaterialAttachmentPicker'
import { DocumentSourceView } from './DocumentWorkspace'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

afterEach(cleanup)
function expectBrand(message: string) {
  expect(screen.getByText(message).closest('.brand-loading')?.querySelector('.brand-loading__mark--waiting')).toBeInTheDocument()
}
it('shows an inline brand in the material picker, then the actual empty result', () => {
  const props = { inline: true, materials: [], selectedIds: new Set<string>(), onToggle: vi.fn(), onClose: vi.fn() }
  const { rerender } = render(<AgentMaterialAttachmentPicker {...props} loading />)
  expectBrand('正在加载文件…')
  rerender(<AgentMaterialAttachmentPicker {...props} loading={false} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('还没有文件，可以直接上传。')).toBeVisible()
})
it('animates original-document waiting without hiding already available reading content', () => {
  render(<DocumentSourceView loading onPageChange={vi.fn()}><p>已读取的原文</p></DocumentSourceView>)
  expectBrand('正在读取原文结构')
  expect(screen.getByText('已读取的原文')).toBeVisible()
})
