import { KnowledgeEntryList } from './KnowledgeEntryList'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

afterEach(cleanup)
function expectBrand(message: string) {
  expect(screen.getByText(message).closest('.brand-loading')?.querySelector('.brand-loading__mark--waiting')).toBeInTheDocument()
}
it('uses the brand in a knowledge result wait, while empty and failed results are not loading', () => {
  const props = { entries: [], hasNextPage: false, totalEntries: 0, loadingMore: false, onSelect: vi.fn(), onLoadMore: vi.fn(), onRetry: vi.fn() }
  const { rerender } = render(<KnowledgeEntryList {...props} state="loading" />)
  expectBrand('正在读取条目')
  rerender(<KnowledgeEntryList {...props} state="empty" />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('没有找到符合条件的条目')).toBeVisible()
  rerender(<KnowledgeEntryList {...props} state="error" error="服务暂不可用" />)
  expect(screen.getByRole('alert')).toHaveTextContent('服务暂不可用')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
