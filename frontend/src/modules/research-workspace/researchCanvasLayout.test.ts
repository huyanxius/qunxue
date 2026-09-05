import { describe, expect, it } from 'vitest'
import { arrangeResearchCanvas, CANVAS_CARD_SIZE } from './researchCanvasLayout'
import type { ResearchCanvasNode } from './researchCanvasProjection'
const node = (id: string, kind: ResearchCanvasNode['kind']): ResearchCanvasNode => ({ id, kind, title: id, status: 'developing', provenance: 'agent', citationIds: [] })

describe('research canvas structure', () => {
  it('groups real research roles and avoids overlap with many disconnected cards', () => {
    const kinds = ['question', 'phenomenon', 'theory', 'claim', 'evidence', 'gap', 'synthesis', 'document'] as const
    const nodes = Array.from({ length: 48 }, (_, i) => node(`card-${i}`, kinds[i % 8]))
    const positions = arrangeResearchCanvas(nodes)
    expect(positions.get('card-0')!.x).toBeLessThan(positions.get('card-2')!.x)
    expect(positions.get('card-2')!.x).toBeLessThan(positions.get('card-4')!.x)
    expect(positions.get('card-4')!.x).toBeLessThan(positions.get('card-6')!.x)
    const all = [...positions.values()]
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
      expect(Math.abs(all[i].x - all[j].x) >= CANVAS_CARD_SIZE.width || Math.abs(all[i].y - all[j].y) >= CANVAS_CARD_SIZE.height).toBe(true)
    }
  })
  it('preserves dragged positions and does not jump when the Agent edits or adds a card', () => {
    const nodes = [node('q', 'question'), node('claim', 'claim')]
    const previous = arrangeResearchCanvas(nodes)
    previous.set('claim', { x: 465, y: 392 })
    const updated = arrangeResearchCanvas([node('new', 'claim'), ...nodes.map(item => ({ ...item, title: '改写后的标题' }))], previous)
    expect(updated.get('claim')).toEqual({ x: 465, y: 392 })
    expect(updated.get('q')).toEqual(previous.get('q'))
    expect(updated.get('new')).not.toEqual(updated.get('claim'))
  })
})
