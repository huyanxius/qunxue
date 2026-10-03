import { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectCreatePopover } from './ProjectCreatePopover'

const previousViewport = Object.getOwnPropertyDescriptor(window, 'visualViewport')
afterEach(() => {
  cleanup()
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
  if (previousViewport) Object.defineProperty(window, 'visualViewport', previousViewport)
  else Reflect.deleteProperty(window, 'visualViewport')
})

it('keeps the mobile project name when the keyboard opens and stays within the drawer', () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
  const cancel = vi.fn(), submit = vi.fn()
  function Harness() {
    const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null)
    const [title, setTitle] = useState('')
    return <aside className="desktop-rail" aria-label="手机抽屉"><button ref={setAnchor}>新建项目</button>{anchor ? <ProjectCreatePopover anchor={anchor} title={title} saving={false} error={null} onTitleChange={setTitle} onCancel={cancel} onSubmit={submit} /> : null}</aside>
  }
  render(<Harness />)
  const input = screen.getByRole('textbox', { name: '项目名称' })
  fireEvent.change(input, { target: { value: '保留手机项目名称' } })
  fireEvent(window, new Event('resize'))
  expect(cancel).not.toHaveBeenCalled()
  expect(input).toHaveValue('保留手机项目名称')
  expect(screen.getByRole('complementary', { name: '手机抽屉' })).toContainElement(screen.getByRole('dialog', { name: '新建项目' }))
  expect(submit).not.toHaveBeenCalled()
  fireEvent.keyDown(input, { key: 'Escape' })
  expect(cancel).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: '新建项目' })).toHaveFocus()
})
