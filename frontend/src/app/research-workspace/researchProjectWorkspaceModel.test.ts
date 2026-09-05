import { describe, expect, it } from 'vitest'

import {
  legacyResearchWorkspaceDestination,
  readResearchWorkspaceResumePath,
  rememberResearchWorkspaceResumePath,
  researchWorkspaceDestination,
  researchWorkspaceToolFromProject,
  type ResearchWorkspaceTool,
} from './researchProjectWorkspaceModel'

describe('research project workspace routes', () => {
  it.each<readonly [string, ResearchWorkspaceTool]>([
    ['agent', 'map'],
    ['research_map', 'map'],
    ['phenomenon', 'map'],
    ['materials', 'materials'],
    ['theory_matching', 'theory'],
    ['framework', 'writing'],
    ['method', 'method'],
  ])('maps the project central tool %s into one workspace tool', (centralTool, expected) => {
    expect(researchWorkspaceToolFromProject(centralTool)).toBe(expected)
  })

  it('keeps restorable object positions in the canonical workspace URL', () => {
    expect(researchWorkspaceDestination('task/1', 'materials', {
      materialId: 'material 1',
      parseId: 'parse/2',
      segmentId: 'segment?3',
    })).toBe(
      '/research/task%2F1/workspace/materials?material_id=material+1&parse_id=parse%2F2&segment_id=segment%3F3',
    )
  })

  it('recognizes the stable archive tool as a project workspace destination', () => {
    expect(researchWorkspaceDestination('task-1', 'archive')).toBe(
      '/research/task-1/workspace/archive',
    )
  })

  it.each([
    ['/research/task-1/phenomenon?focus=evidence#quote', '/research/task-1/workspace/map?focus=evidence#quote'],
    ['/research/task-1/match?section_id=evidence', '/research/task-1/workspace/theory?section_id=evidence'],
    ['/research/task-1/framework?section_id=ethics', '/research/task-1/workspace/writing?section_id=ethics'],
    ['/research/task-1/method?plan_id=plan-1', '/research/task-1/workspace/method?plan_id=plan-1'],
    [
      '/research/materials?task_id=task-1&material_id=material-1&segment_id=segment-1',
      '/research/task-1/workspace/materials?material_id=material-1&segment_id=segment-1',
    ],
  ])('restores the legacy deep link %s inside the project workspace', (legacy, expected) => {
    expect(legacyResearchWorkspaceDestination(legacy)).toBe(expected)
  })

  it('does not turn the global material chooser into a made-up project', () => {
    expect(legacyResearchWorkspaceDestination('/research/materials')).toBeNull()
  })

  it('keeps project folders in the library until a specific file is opened', () => {
    expect(legacyResearchWorkspaceDestination('/research/materials?task_id=task-1')).toBeNull()
    expect(legacyResearchWorkspaceDestination('/research/materials?task_id=task-1&tab=memory')).toBeNull()
  })

  it('restores the last tool and key object only inside the same project', () => {
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    }
    const path = '/research/task-1/workspace/materials?material_id=material-1&segment_id=segment-1'

    rememberResearchWorkspaceResumePath('task-1', path, storage)

    expect(readResearchWorkspaceResumePath('task-1', storage)).toBe(path)
    expect(readResearchWorkspaceResumePath('task-2', storage)).toBeNull()
    values.set('qunxue.research-workspace.resume.v1:task-1', '/research/task-2/workspace/map')
    expect(readResearchWorkspaceResumePath('task-1', storage)).toBeNull()
  })
})
