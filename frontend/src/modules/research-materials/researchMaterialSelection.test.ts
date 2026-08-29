import { afterEach, describe, expect, it } from 'vitest'

import type { ResearchMaterialSegment } from './researchMaterialsModel'
import { selectionDraftFromDomRange } from './researchMaterialSelection'

const segment: ResearchMaterialSegment = {
  segmentId: 'segment-1',
  materialId: 'material-1',
  parseId: 'parse-1',
  ordinal: 0,
  kind: 'paragraph',
  text: '甲😀乙丙',
  locator: {
    page: 2,
    headingPath: ['家庭分工'],
    paragraph: 3,
    lineStart: null,
    lineEnd: null,
    charStart: null,
    charEnd: null,
  },
}

afterEach(() => {
  document.body.replaceChildren()
})

describe('research material text selection', () => {
  it('converts a single-segment DOM range from UTF-16 offsets to Python code-point offsets', () => {
    const paragraph = document.createElement('p')
    paragraph.textContent = segment.text
    document.body.append(paragraph)
    const text = paragraph.firstChild as Text
    const range = document.createRange()
    range.setStart(text, 1)
    range.setEnd(text, 4)

    expect(selectionDraftFromDomRange(segment, paragraph, range)).toEqual({
      materialId: 'material-1',
      parseId: 'parse-1',
      segmentId: 'segment-1',
      quote: '😀乙',
      quoteStart: 1,
      quoteEnd: 3,
      locator: segment.locator,
    })
  })

  it('rejects a range whose endpoints cross two source segments', () => {
    const first = document.createElement('p')
    const second = document.createElement('p')
    first.textContent = segment.text
    second.textContent = '第二个片段'
    document.body.append(first, second)
    const range = document.createRange()
    range.setStart(first.firstChild as Text, 1)
    range.setEnd(second.firstChild as Text, 2)

    expect(selectionDraftFromDomRange(segment, first, range)).toBeNull()
  })
})
