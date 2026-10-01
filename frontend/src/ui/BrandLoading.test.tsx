import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { BrandLoading } from './BrandLoading'

afterEach(cleanup)

describe('brand loading', () => {
  it('announces a stable waiting message without inventing a percentage', () => {
    render(<BrandLoading message="正在恢复研究" />)
    expect(screen.getByRole('status')).toHaveTextContent('正在恢复研究')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('uses real progress without announcing every update', () => {
    const { rerender } = render(<BrandLoading progress={0} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
    rerender(<BrandLoading progress={42} compact />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-live', 'off')
    expect(screen.getByRole('status')).not.toHaveTextContent('42')
    rerender(<BrandLoading progress={120} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
    rerender(<BrandLoading progress={Number.NaN} />)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
