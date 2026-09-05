import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { AppLocaleProvider } from '../i18n/AppLocaleProvider'
import { ProjectActionsMenu } from './ProjectActionsMenu'

it('requires confirmation and keeps the project when deletion fails', async () => {
  const onDelete = vi.fn().mockRejectedValueOnce(new Error('项目删除失败')).mockResolvedValueOnce(undefined)
  render(<AppLocaleProvider><ProjectActionsMenu taskId="project-a" title="社区研究" onDelete={onDelete} /></AppLocaleProvider>)
  fireEvent.click(screen.getByRole('button', { name: '社区研究的项目操作' }))
  fireEvent.click(screen.getByRole('menuitem', { name: '删除项目' }))
  expect(onDelete).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog')).toHaveTextContent('所属对话会保留为独立对话')
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '社区研究的项目操作' }))
  fireEvent.click(screen.getByRole('menuitem', { name: '删除项目' }))
  fireEvent.click(screen.getByRole('button', { name: '确认删除项目' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('项目删除失败')
  expect(onDelete).toHaveBeenCalledWith('project-a')
  fireEvent.click(screen.getByRole('button', { name: '确认删除项目' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})
