import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { SupportCenter } from './SupportCenter'

afterEach(cleanup)

describe('SupportCenter', () => {
  it('shows product boundaries and a keyboard-dismissable help dialog', () => {
    render(
      <div className="app-frame">
        <button type="button">页面操作</button>
        <SupportCenter accountEmail="student@example.com" />
      </div>,
    )

    fireEvent.click(screen.getByRole('button', { name: '帮助与边界' }))

    const dialog = screen.getByRole('dialog', { name: '帮助与产品边界' })
    expect(dialog).toHaveTextContent('知识浏览与现象确认')
    expect(dialog).toHaveTextContent('理论匹配与研究框架尚未开放')
    expect(dialog).toHaveTextContent('student@example.com')
    expect(dialog).toHaveTextContent('标注为预览或 mock 的对话只用于体验界面')
    expect(document.querySelector('.app-frame')).toHaveAttribute('inert')

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('link', { name: '查看研究记录' })).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.querySelector('.app-frame')).not.toHaveAttribute('inert')
  })
})
