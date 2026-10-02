import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import { SiteHeader } from './SiteHeader'

afterEach(cleanup)
function setup(authenticated = false) {
  return render(<MemoryRouter><SiteHeader authenticated={authenticated} /><button>正文按钮</button><Routes><Route path="/features" element={<h1>功能说明</h1>} /><Route path="*" element={null} /></Routes></MemoryRouter>)
}
describe('SiteHeader disclosure navigation', () => {
  it('closes after a pointer click outside the header', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '功能' }))
    fireEvent.pointerDown(screen.getByRole('button', { name: '正文按钮' }))
    expect(screen.getByRole('button', { name: '功能' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('allows keyboard entry and closes when focus leaves the header', () => {
    setup()
    const trigger = screen.getByRole('button', { name: '功能' })
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    expect(screen.getByRole('link', { name: /探索功能/ })).toHaveFocus()
    fireEvent.blur(screen.getByRole('link', { name: /探索功能/ }), { relatedTarget: screen.getByRole('button', { name: '正文按钮' }) })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })
  it('switches panels without leaving stale feature links', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '功能' }))
    fireEvent.click(screen.getByRole('button', { name: 'Docs' }))
    expect(screen.queryByRole('link', { name: /深入研究/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /快速开始/ })).toHaveAttribute('href', '/docs#quick-start')
  })
  it('closes navigation when a feature destination is selected', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '功能' }))
    fireEvent.click(screen.getByRole('link', { name: /深入研究/ }))
    expect(screen.getByRole('heading', { name: '功能说明' })).toBeVisible()
    expect(screen.getByRole('button', { name: '功能' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('retains real account destinations for authenticated visitors', () => {
    setup(true)
    expect(screen.getByRole('link', { name: '工作台' })).toHaveAttribute('href', '/app')
    expect(screen.getByRole('link', { name: /开始体验/ })).toHaveAttribute('href', '/agent')
  })
})
