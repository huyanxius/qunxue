import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { AppLocaleProvider } from '../../i18n/AppLocaleProvider'
import { ProjectScopeMenu } from './ProjectScopeMenu'

afterEach(cleanup)

it('searches all fifty projects and selects a result beyond the initial visible list', () => {
  const onChange = vi.fn()
  render(<AppLocaleProvider><ProjectScopeMenu
    projects={Array.from({ length: 50 }, (_, index) => ({ task_id: `project-${index}`, project_title: `社区研究 ${index}`, status: 'draft' }))}
    taskId="project-0" disabled={false} onChange={onChange}
  /></AppLocaleProvider>)
  fireEvent.click(screen.getByRole('button', { name: '对话所属项目' }))
  const search = screen.getByRole('searchbox', { name: '搜索项目' })
  expect(search).toHaveFocus()
  expect(screen.getAllByRole('menuitemradio')).toHaveLength(51)
  expect(screen.getByRole('menuitemradio', { name: '社区研究 0' })).toHaveAttribute('aria-checked', 'true')
  fireEvent.change(search, { target: { value: '49' } })
  expect(screen.getAllByRole('menuitemradio')).toHaveLength(1)
  fireEvent.keyDown(search, { key: 'ArrowDown' })
  expect(screen.getByRole('menuitemradio', { name: '社区研究 49' })).toHaveFocus()
  fireEvent.click(screen.getByRole('menuitemradio', { name: '社区研究 49' }))
  expect(onChange).toHaveBeenCalledWith('project-49')
  expect(screen.queryByRole('dialog', { name: '切换项目' })).toBeNull()
})

it('shows empty search results and dismisses without changing project', () => {
  const onChange = vi.fn()
  render(<AppLocaleProvider><ProjectScopeMenu projects={[]} taskId={null} disabled={false} onChange={onChange} /></AppLocaleProvider>)
  const trigger = screen.getByRole('button', { name: '对话所属项目' })
  fireEvent.click(trigger)
  const search = screen.getByRole('searchbox', { name: '搜索项目' })
  fireEvent.change(search, { target: { value: '不存在' } })
  expect(screen.getByText('没有匹配的项目')).toBeVisible()
  expect(fireEvent.keyDown(search, { key: 'Enter', cancelable: true })).toBe(false)
  expect(screen.getByRole('dialog', { name: '切换项目' })).toBeVisible()
  fireEvent.keyDown(search, { key: 'Escape' })
  expect(trigger).toHaveFocus()
  expect(onChange).not.toHaveBeenCalled()
})
