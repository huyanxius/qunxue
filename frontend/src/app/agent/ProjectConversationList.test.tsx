import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { expect, it, vi } from 'vitest'
import { AppLocaleProvider } from '../../i18n/AppLocaleProvider'
import { ProjectConversationList } from './ProjectConversationList'

it('expands project conversations and starts a conversation in the chosen project', () => {
  const onStart = vi.fn()
  render(<MemoryRouter><AppLocaleProvider><ProjectConversationList
    projects={[{ task_id: 'a', project_title: '社区研究', status: 'draft' }]}
    conversations={[
      { conversation_id: 'one', title: '访谈问题', task_id: 'a', updated_at: '', turn_count: 1 },
      { conversation_id: 'free', title: '临时讨论', task_id: null, updated_at: '', turn_count: 1 },
    ]}
    activeTaskId="a"
    onStart={onStart}
    renderConversation={(conversation) => <span key={conversation.conversation_id}>{conversation.title}</span>}
  /></AppLocaleProvider></MemoryRouter>)
  const project = screen.getByRole('group', { name: '社区研究' })
  expect(within(project).getByText('访谈问题')).toBeVisible()
  expect(within(project).queryByText('临时讨论')).toBeNull()
  fireEvent.click(within(project).getByRole('button', { name: '在社区研究中新建对话' }))
  expect(onStart).toHaveBeenCalledWith('a')
  expect(within(project).getByRole('link', { name: '项目材料' })).toHaveAttribute('href', '/research/a/workspace/materials')
  fireEvent.click(within(project).getByRole('button', { name: '社区研究' }))
  expect(within(project).queryByText('访谈问题')).toBeNull()
  expect(screen.getByText('临时讨论')).toBeVisible()
})
