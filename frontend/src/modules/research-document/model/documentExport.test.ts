import { describe, expect, it } from 'vitest'

import {
  buildPrintableDocument,
  createDocxExport,
  formatBibliography,
  type ExportCitation,
} from './documentExport'

const citations: ExportCitation[] = [
  {
    citationId: 'zhou-2024',
    sourceId: 'literature-entry-1',
    locator: { label: 'page', value: '42-44' },
    state: 'verified',
    csl: {
      id: 'literature-entry-1',
      type: 'article-journal',
      title: 'Intergenerational Care across Migration',
      author: [{ family: 'Zhou', given: 'Min' }],
      issued: { 'date-parts': [[2024]] },
      'container-title': 'Journal of Family Sociology',
      volume: '18',
      issue: '2',
      page: '101-122',
    },
  },
  {
    citationId: 'li-2023',
    sourceId: 'literature-entry-2',
    locator: { label: 'chapter', value: '第三章' },
    state: 'verified',
    csl: {
      id: 'literature-entry-2',
      type: 'book',
      title: '流动家庭与代际照护',
      author: [{ family: '李', given: '敏' }],
      issued: { 'date-parts': [[2023]] },
      publisher: '社会科学文献出版社',
      'publisher-place': '北京',
      language: 'zh-CN',
    },
  },
]

describe('research document export', () => {
  it('formats one metadata set with official CSL styles instead of handwritten punctuation', () => {
    const asa = formatBibliography(citations, {
      styleId: 'american-sociological-association',
      locale: 'en-US',
    })
    const gbt = formatBibliography(citations, {
      styleId: 'china-national-standard-gb-t-7714-2015-author-date',
      locale: 'zh-CN',
    })

    expect(asa).toContain('Zhou, Min')
    expect(asa).toContain('Intergenerational Care across Migration')
    expect(gbt).toContain('李敏')
    expect(gbt).toContain('流动家庭与代际照护')
    expect(asa).not.toBe(gbt)
  })

  it('keeps unresolved citations visible in printable PDF content and audit output', () => {
    const html = buildPrintableDocument({
      title: '跨语言照护研究',
      templateId: 'chinese-social-science',
      sections: [
        { title: '摘要', markdown: '照护实践 combines family duty and neighborhood support.' },
      ],
      bibliographyHtml: '<div class="csl-entry">李敏. 流动家庭与代际照护.</div>',
      citationAudit: [
        ...citations,
        {
          citationId: 'missing-1',
          sourceId: 'literature-entry-missing',
          locator: { label: 'page', value: '9' },
          state: 'tombstoned',
          csl: null,
        },
      ],
    })

    expect(html).toContain('@page')
    expect(html).toContain('跨语言照护研究')
    expect(html).toContain('照护实践 combines family duty')
    expect(html).toContain('引用异常')
    expect(html).toContain('literature-entry-missing')
  })

  it('keeps imported print CSS inside the style element', () => {
    const html = buildPrintableDocument({
      title: '自定义模板',
      templateId: 'custom',
      sections: [{ title: '摘要', markdown: '正文' }],
      bibliographyHtml: '',
      citationAudit: [],
      customCss: 'body { color: black; }</style><script>globalThis.compromised = true</script>',
    })

    const parsed = new DOMParser().parseFromString(html, 'text/html')
    expect(parsed.querySelector('script')).toBeNull()
  })

  it('creates a real DOCX package from the same mixed-language content', async () => {
    const blob = await createDocxExport({
      title: '跨语言照护研究',
      templateId: 'asa',
      sections: [
        { title: 'Findings / 发现', markdown: '照护实践 combines family duty and neighborhood support.' },
      ],
      bibliographyText: 'Zhou, Min. 2024. “Intergenerational Care across Migration.”',
      citationAudit: citations,
    })

    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    expect(blob.size).toBeGreaterThan(1_000)
    const signature = new Uint8Array(await blob.slice(0, 2).arrayBuffer())
    expect([...signature]).toEqual([0x50, 0x4b])
  })
})
