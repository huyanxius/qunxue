import { describe, expect, it } from 'vitest'
import { groupProjectConversations } from './projectContext'

describe('project conversation scope', () => {
  it('keeps empty projects and groups multiple conversations without swallowing independent ones', () => {
    const groups = groupProjectConversations(
      [{ task_id: 'a', project_title: '社区研究' }, { task_id: 'b', project_title: '空项目' }],
      [
        { conversation_id: 'one', task_id: 'a' },
        { conversation_id: 'free', task_id: null },
        { conversation_id: 'two', task_id: 'a' },
      ],
    )
    expect(groups.projects.map((group) => [group.project.task_id, group.conversations.map((c) => c.conversation_id)]))
      .toEqual([['a', ['one', 'two']], ['b', []]])
    expect(groups.unassigned.map((c) => c.conversation_id)).toEqual(['free'])
  })
  it('retains conversations whose project is temporarily unavailable without calling them unassigned', () => {
    const groups = groupProjectConversations([], [{ conversation_id: 'one', task_id: 'missing' }])
    expect(groups.unavailable.map((c) => c.conversation_id)).toEqual(['one'])
    expect(groups.unassigned).toEqual([])
  })
})
