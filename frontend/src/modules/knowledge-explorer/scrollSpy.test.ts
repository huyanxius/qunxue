import { describe, expect, it } from 'vitest'

import { activeHeadingAtOffset } from './scrollSpy'

describe('knowledge reader scroll spy', () => {
  it('keeps the first heading active before the reading threshold reaches it', () => {
    expect(activeHeadingAtOffset([
      { id: 'overview', top: 420 },
      { id: 't1', top: 470 },
    ], 180)).toBe('overview')
  })

  it('selects the last heading that crossed the reading threshold', () => {
    expect(activeHeadingAtOffset([
      { id: 'overview', top: -920 },
      { id: 't1', top: -880 },
      { id: 't2', top: -265 },
      { id: 't3', top: 377 },
    ], 180)).toBe('t2')
  })
})
