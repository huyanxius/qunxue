import type {
  ResearchMaterialLocator,
  ResearchMaterialSegment,
} from './researchMaterialsModel'

export type ResearchMaterialSelectionDraft = {
  materialId: string
  parseId: string
  segmentId: string
  quote: string
  quoteStart: number
  quoteEnd: number
  locator: ResearchMaterialLocator
}

function codePointLength(value: string): number {
  return Array.from(value).length
}

/**
 * Convert browser Range offsets (UTF-16 code units) into the code-point
 * offsets used by Python when it slices the immutable source segment.
 */
export function selectionDraftFromDomRange(
  segment: ResearchMaterialSegment,
  container: HTMLElement,
  range: Range,
): ResearchMaterialSelectionDraft | null {
  if (
    range.collapsed
    || !container.contains(range.startContainer)
    || !container.contains(range.endContainer)
  ) return null

  const rawQuote = range.toString()
  const quote = rawQuote.trim()
  if (!quote) return null

  const prefixRange = range.cloneRange()
  prefixRange.selectNodeContents(container)
  prefixRange.setEnd(range.startContainer, range.startOffset)
  const leadingWhitespace = rawQuote.slice(0, rawQuote.indexOf(quote))
  const quoteStart = codePointLength(prefixRange.toString()) + codePointLength(leadingWhitespace)
  const quoteEnd = quoteStart + codePointLength(quote)
  const sourceQuote = Array.from(segment.text).slice(quoteStart, quoteEnd).join('')
  if (sourceQuote !== quote) return null

  return {
    materialId: segment.materialId,
    parseId: segment.parseId,
    segmentId: segment.segmentId,
    quote,
    quoteStart,
    quoteEnd,
    locator: segment.locator,
  }
}
