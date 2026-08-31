import { describe, expect, it } from 'vitest'

import { createDocumentDiff } from './documentDiff'

describe('createDocumentDiff', () => {
  it('keeps rich-text marks and reports only the changed local passage', () => {
    const diff = createDocumentDiff(
      '迁移后的照护主要由**母亲**承担。',
      '迁移后的照护主要由**祖辈**承担，并依赖邻里互助。',
    )

    expect(diff.map((part) => [part.kind, part.text])).toEqual([
      ['unchanged', '迁移后的照护主要由'],
      ['deleted', '母亲'],
      ['inserted', '祖辈'],
      ['unchanged', '承担'],
      ['inserted', '，并依赖邻里互助'],
      ['unchanged', '。'],
    ])
  })

  it('does not flatten heading and list boundaries into one paragraph', () => {
    const diff = createDocumentDiff(
      '## Findings\n\n- Grandparents provide daily care.\n- Mothers coordinate remotely.',
      '## Findings\n\n- Grandparents provide daily care.\n- Parents coordinate remotely.',
    )

    expect(diff.filter((part) => part.kind !== 'unchanged')).toEqual([
      { kind: 'deleted', text: 'Mothers' },
      { kind: 'inserted', text: 'Parents' },
    ])
  })
})
