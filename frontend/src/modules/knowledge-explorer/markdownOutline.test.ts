import { describe, expect, it } from 'vitest'

import { buildMarkdownOutline } from './markdownOutline'

describe('buildMarkdownOutline', () => {
  it('creates stable Chinese anchors and disambiguates duplicate headings', () => {
    expect(buildMarkdownOutline([
      '## 理论背景',
      '### 核心命题',
      '## 理论背景',
      '## !!!',
    ].join('\n')).headings).toEqual([
      { depth: 2, id: '理论背景', title: '理论背景' },
      { depth: 3, id: '核心命题', title: '核心命题' },
      { depth: 2, id: '理论背景-2', title: '理论背景' },
      { depth: 2, id: 'section', title: '!!!' },
    ])
  })
})
