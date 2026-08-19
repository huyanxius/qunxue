import { describe, expect, it } from 'vitest'

import { describeTaxonomyNode, dimensionTone } from './taxonomyPresentation'

describe('taxonomy presentation', () => {
  it('keeps each of the seven knowledge dimensions on a stable visual tone', () => {
    expect([
      dimensionTone('D1'),
      dimensionTone('D2'),
      dimensionTone('D3'),
      dimensionTone('D4'),
      dimensionTone('D5'),
      dimensionTone('D6'),
      dimensionTone('D7'),
    ]).toEqual([
      'ontology',
      'practice',
      'method',
      'value',
      'epistemology',
      'tradition',
      'history',
    ])
  })

  it.each([
    ['IV. 社会结构与过程', { badge: 'IV', kind: 'section', label: '社会结构与过程' }],
    ['21. 社会分层与流动（Social Stratification & Mobility）', { badge: '21', kind: 'family', label: '社会分层与流动（Social Stratification & Mobility）' }],
    ['C276 地位（Status）', { badge: 'C276', kind: 'concept', label: '地位（Status）' }],
    ['T4 当代发展', { badge: 'T4', kind: 'stage', label: '当代发展', stage: '4' }],
  ])('turns %s into an object label instead of a folder name', (title, expected) => {
    expect(describeTaxonomyNode(title)).toEqual(expected)
  })

  it('leaves an unstructured category readable without inventing a type', () => {
    expect(describeTaxonomyNode('其他理论')).toEqual({
      badge: undefined,
      kind: 'category',
      label: '其他理论',
    })
  })
})
