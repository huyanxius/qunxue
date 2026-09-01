import { describe, expect, it } from 'vitest'

import { formatTranscriptTime, normalizeTranscriptionWorkspace } from './transcriptionModel'

describe('transcriptionModel', () => {
  it('keeps immutable version and original media timecodes', () => {
    const workspace = normalizeTranscriptionWorkspace({
      material_id: 'material-1',
      status: 'ready',
      automatic_available: false,
      automatic_provider: null,
      error_code: null,
      current_version: {
        version_id: 'version-2',
        material_id: 'material-1',
        version: 2,
        source: 'manual_correction',
        provider: null,
        created_from_version_id: 'version-1',
        created_at: '2026-09-01T10:00:00Z',
        is_current: true,
        segments: [{
          segment_id: 'segment-1',
          ordinal: 0,
          speaker: '访谈员',
          start_ms: 1_250,
          end_ms: 3_800,
          text: '请先简单介绍一下自己。',
        }],
      },
      versions: [],
    })

    expect(workspace.currentVersion?.versionId).toBe('version-2')
    expect(workspace.currentVersion?.segments[0]).toMatchObject({ startMs: 1_250, endMs: 3_800 })
    expect(formatTranscriptTime(3_800)).toBe('00:03.800')
    expect(formatTranscriptTime(3_723_800)).toBe('01:02:03.800')
  })
})
