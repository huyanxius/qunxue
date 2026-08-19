import { describe, expect, it } from 'vitest'

import {
  applyArtifactAction,
  applyRunEvent,
  closeContextRail,
  createArtifactAction,
  createCanvasAction,
  createInitialResearchWorkspaceState,
  openContextRail,
  routeModeFromPathname,
  selectContextRailTab,
} from './index'
import type {
  ArtifactDocument,
  CanvasState,
  ResearchWorkspaceState,
} from './index'

describe('research workspace route mode', () => {
  it('keeps the agent route as the conversation-first mode', () => {
    expect(routeModeFromPathname('/agent')).toEqual({
      mode: 'agent',
      researchId: null,
      artifactId: null,
    })
  })

  it('recognises a research artifact deep link without relying on query parsing', () => {
    expect(routeModeFromPathname('/research/task-42/artifacts/draft-7')).toEqual({
      mode: 'artifact',
      researchId: 'task-42',
      artifactId: 'draft-7',
    })
  })
})

describe('research workspace context rail', () => {
  it('opens the requested context and clears activity unread count', () => {
    const state = createInitialResearchWorkspaceState()
    const withActivity = openContextRail(state.rail, 'activity')

    expect(withActivity).toMatchObject({ open: true, activeTab: 'activity' })
    expect(withActivity.unreadActivity).toBe(0)
  })

  it('does not mutate the previous rail when switching tabs or closing', () => {
    const state = createInitialResearchWorkspaceState()
    const selected = selectContextRailTab(openContextRail(state.rail, 'sources'), 'basis')
    const closed = closeContextRail(selected)

    expect(state.rail).toEqual({
      open: false,
      activeTab: 'agent',
      unreadActivity: 0,
    })
    expect(selected).toMatchObject({ open: true, activeTab: 'basis' })
    expect(closed).toMatchObject({ open: false, activeTab: 'basis' })
  })
})

describe('workspace actions', () => {
  it('creates a reversible canvas action with an explicit version boundary', () => {
    expect(createCanvasAction({
      actionId: 'action-1',
      kind: 'update_canvas_node',
      targetId: 'node-question',
      beforeVersion: 3,
      payload: { title: '新的研究问题' },
    })).toEqual({
      domain: 'canvas',
      actionId: 'action-1',
      kind: 'update_canvas_node',
      targetId: 'node-question',
      beforeVersion: 3,
      afterVersion: null,
      status: 'pending',
      reversible: true,
      undoActionId: null,
      evidence: [],
      payload: { title: '新的研究问题' },
    })
  })

  it('applies a text patch only when the artifact version is current', () => {
    const artifact: ArtifactDocument = {
      artifactId: 'artifact-1',
      kind: 'draft',
      title: '研究摘要',
      content: '青年孤独正在成为公共议题。',
      version: 4,
      updatedAt: '2026-08-19T00:00:00Z',
    }
    const action = createArtifactAction({
      actionId: 'action-2',
      kind: 'apply_text_patch',
      targetId: artifact.artifactId,
      beforeVersion: artifact.version,
      payload: { start: 0, end: 4, replacement: '青年孤独感' },
    })

    expect(applyArtifactAction(artifact, action)).toEqual({
      ok: true,
      artifact: {
        ...artifact,
        content: '青年孤独感正在成为公共议题。',
        version: 5,
      },
      action: {
        ...action,
        afterVersion: 5,
        status: 'succeeded',
      },
    })
  })

  it('rejects a stale artifact action without changing content', () => {
    const artifact: ArtifactDocument = {
      artifactId: 'artifact-1',
      kind: 'draft',
      title: '研究摘要',
      content: '原始内容',
      version: 2,
      updatedAt: '2026-08-19T00:00:00Z',
    }
    const action = createArtifactAction({
      actionId: 'action-stale',
      kind: 'apply_text_patch',
      targetId: artifact.artifactId,
      beforeVersion: 1,
      payload: { start: 0, end: 2, replacement: '新内容' },
    })

    expect(applyArtifactAction(artifact, action)).toEqual({
      ok: false,
      reason: 'stale_version',
      artifact,
      action: { ...action, status: 'failed' },
    })
  })
})

describe('workspace run state', () => {
  it('moves from queued to running to completed while preserving action history', () => {
    const state = createInitialResearchWorkspaceState()
    const action = createCanvasAction({
      actionId: 'action-run',
      kind: 'run_canvas_node',
      targetId: 'node-1',
      beforeVersion: 1,
      payload: {},
    })
    const queued = applyRunEvent(state, {
      type: 'run_queued',
      runId: 'run-1',
      action,
    })
    const running = applyRunEvent(queued, { type: 'run_started', runId: 'run-1' })
    const completed = applyRunEvent(running, {
      type: 'run_completed',
      runId: 'run-1',
    })

    expect(completed.run).toMatchObject({ runId: 'run-1', status: 'succeeded' })
    expect(completed.actions).toHaveLength(1)
    expect(completed.actions[0]).toMatchObject({ actionId: 'action-run', status: 'succeeded' })
    expect(completed.rail).toMatchObject({ open: true, activeTab: 'sources' })
  })
})

describe('canvas state is a value object', () => {
  it('keeps node selection separate from the server-backed canvas snapshot', () => {
    const canvas: CanvasState = {
      nodes: [],
      edges: [],
      selectedNodeId: null,
      focusedNodeId: null,
    }
    const state: ResearchWorkspaceState = {
      ...createInitialResearchWorkspaceState(),
      canvas,
    }

    expect(state.canvas).toEqual(canvas)
  })
})
