import { inflateRawSync } from 'node:zlib'

import { describe, expect, it } from 'vitest'

import type { AgentCitation, AgentConversation } from './model'
import {
  buildResearchReport,
  collectReferences,
  conclusionDigest,
  formatElapsed,
  researchReportFilename,
} from './researchReportContent'
import { createResearchReportDocx } from './researchReportDocx'
import { buildResearchReportHtml } from './researchReportPrint'

function citation(overrides: Partial<AgentCitation> & { citation_id: string; label: string }): AgentCitation {
  return { kind: 'entry', ...overrides }
}

const conversation: AgentConversation = {
  conversation_id: 'conversation-1',
  title: '困惑人类的不平等从哪里来',
  created_at: '2026-09-05T02:10:00Z',
  updated_at: '2026-09-05T04:23:00Z',
  turn_count: 2,
  turns: [
    {
      turn_id: 'turn-1',
      user: { message_id: 'm1', role: 'user', content: '不平等的社会根源是什么？', citations: [], sequence: 1, created_at: '2026-09-05T02:10:00Z' },
      assistant: {
        message_id: 'm2',
        role: 'assistant',
        content: '## 结论\n\n不平等首先是一种结构位置的产物[knowledge:D1:C213]，而不是个体努力的残差。\n\n- 结构位置决定机会\n- 机会差异随时间累积\n',
        citations: [
          citation({ citation_id: 'c1', label: '社会学与社会秩序', knowledge_id: 'D1:C213' }),
          citation({ citation_id: 'c2', label: "How's Life? 2024", kind: 'source', source_kind: 'web', source_id: 'https://www.oecd.org/en/publications/2024/11/how-s-life' }),
        ],
        sequence: 2,
        created_at: '2026-09-05T02:11:00Z',
      },
    },
    {
      turn_id: 'turn-2',
      user: { message_id: 'm3', role: 'user', content: '那教育能抵消多少？', citations: [], sequence: 3, created_at: '2026-09-05T04:20:00Z' },
      assistant: {
        message_id: 'm4',
        role: 'assistant',
        content: '教育只能抵消一部分。\n\n| 机制 | 效果 |\n| --- | --- |\n| 文凭信号 | 中等 |\n',
        citations: [
          // 同一条知识条目在第二轮再次被引，参考资料里只应出现一次。
          citation({ citation_id: 'c3', label: '社会学与社会秩序', knowledge_id: 'D1:C213' }),
          citation({ citation_id: 'c4', label: '访谈记录 2026-08', kind: 'research_material', material_id: 'material-1' }),
        ],
        sequence: 4,
        created_at: '2026-09-05T04:23:00Z',
      },
    },
  ],
}

/** docx 是个 zip，直接从本地文件头里取出某个条目再解压，避免为测试引入解包依赖。 */
function readZipEntry(buffer: Buffer, name: string) {
  let offset = 0
  while (offset < buffer.length - 30) {
    if (buffer.readUInt32LE(offset) !== 0x04034b50) {
      offset += 1
      continue
    }
    const method = buffer.readUInt16LE(offset + 8)
    const compressedSize = buffer.readUInt32LE(offset + 18)
    const nameLength = buffer.readUInt16LE(offset + 26)
    const extraLength = buffer.readUInt16LE(offset + 28)
    const entryName = buffer.subarray(offset + 30, offset + 30 + nameLength).toString('utf8')
    const dataStart = offset + 30 + nameLength + extraLength
    if (entryName === name) {
      const data = buffer.subarray(dataStart, dataStart + compressedSize)
      return method === 8 ? inflateRawSync(data) : Buffer.from(data)
    }
    offset = dataStart + compressedSize
  }
  return null
}

async function zipEntryNames(blob: Blob) {
  const buffer = Buffer.from(await blob.arrayBuffer())
  const names: string[] = []
  let offset = 0
  while (offset < buffer.length - 30) {
    if (buffer.readUInt32LE(offset) !== 0x04034b50) {
      offset += 1
      continue
    }
    const compressedSize = buffer.readUInt32LE(offset + 18)
    const nameLength = buffer.readUInt16LE(offset + 26)
    const extraLength = buffer.readUInt16LE(offset + 28)
    names.push(buffer.subarray(offset + 30, offset + 30 + nameLength).toString('utf8'))
    offset = offset + 30 + nameLength + extraLength + compressedSize
  }
  return names
}

describe('research report content', () => {
  it('摘一句结论，跳过标题行并在超长时截断', () => {
    expect(conclusionDigest('## 研究结论\n\n不平等首先是一种结构位置的产物。')).toBe('不平等首先是一种结构位置的产物。')
    const long = `${'不平等首先是一种结构位置的产物，'.repeat(8)}到此为止。`
    const digest = conclusionDigest(long)
    expect(digest.length).toBeLessThanOrEqual(97)
    expect(digest.endsWith('…')).toBe(true)
  })

  it('把用时读成中文', () => {
    expect(formatElapsed(47)).toBe('47 秒')
    expect(formatElapsed(267)).toBe('4 分 27 秒')
  })

  it('引用按知识库、网页、材料分组连号，并去掉重复条目', () => {
    const references = collectReferences(conversation.turns.flatMap((turn) => turn.assistant.citations))
    expect(references.map((reference) => [reference.index, reference.group, reference.title])).toEqual([
      [1, 'knowledge', '社会学与社会秩序'],
      [2, 'web', "How's Life? 2024"],
      [3, 'material', '访谈记录 2026-08'],
    ])
    expect(references[1].url).toBe('https://www.oecd.org/en/publications/2024/11/how-s-life')
  })

  it('删除的引用不进参考资料', () => {
    const references = collectReferences([citation({ citation_id: 'c9', label: '已删除材料', kind: 'research_material', deleted: true })])
    expect(references).toEqual([])
  })

  it('报告沿用对话本身：一轮问答一节，正文里的引用锚点被摘掉', () => {
    const report = buildResearchReport({ conversation, elapsedSeconds: 267 })
    expect(report.title).toBe('困惑人类的不平等从哪里来')
    expect(report.meta).toEqual(['2026 年 9 月 5 日', '研究用时 4 分 27 秒', '知识库 1 条', '网页资料 1 条', '研究材料 1 份'])
    expect(report.sections).toHaveLength(2)
    expect(report.sections[0].question).toBe('不平等的社会根源是什么？')
    expect(report.sections[0].answer).not.toContain('[knowledge:D1:C213]')
    expect(report.sections[0].answer).toContain('结构位置的产物')
  })

  it('文件名去掉路径字符并挂上品牌前缀', () => {
    const report = buildResearchReport({ conversation: { ...conversation, title: '研究/报告: 初稿' } })
    expect(researchReportFilename(report, 'docx')).toBe('群学致知-研究 报告 初稿.docx')
  })
})

describe('research report docx', () => {
  it('生成带信头、正文、表格与引用资料的 Word', async () => {
    const report = buildResearchReport({ conversation, elapsedSeconds: 267 })
    const blob = await createResearchReportDocx(report)
    expect(blob.size).toBeGreaterThan(4000)

    const buffer = Buffer.from(await blob.arrayBuffer())
    const document = readZipEntry(buffer, 'word/document.xml')?.toString('utf8') ?? ''
    expect(document).toContain('困惑人类的不平等从哪里来')
    expect(document).toContain('结构位置的产物')
    expect(document).toContain('引用资料')
    expect(document).toContain('群学知识库')
    expect(document).toContain('https://www.oecd.org/en/publications/2024/11/how-s-life')
    // 版式沿用作品方案那份 Word：正文宋体小四、1.5 倍行距、首行缩进两字。
    expect(document).toContain('w:eastAsia="宋体"')
    expect(document).toContain('w:eastAsia="黑体"')
    expect(document).toContain('w:firstLine="480"')
    expect(document).toContain('w:line="360"')
    expect(document).toContain('<w:tbl>')

    const names = await zipEntryNames(blob)
    // 信头的标志同时嵌 SVG 与位图兜底，旧版 Word 才不会开出一个空框。
    expect(names.some((name) => name.endsWith('.svg'))).toBe(true)
    expect(names.some((name) => name.endsWith('.png'))).toBe(true)
  })
})

describe('research report print page', () => {
  it('打印页带品牌信头、A4 版心和引用资料', () => {
    const report = buildResearchReport({ conversation, elapsedSeconds: 267 })
    const html = buildResearchReportHtml(report)
    expect(html).toContain('群学致知')
    expect(html).toContain('<svg')
    expect(html).toContain('@page { size: A4; margin: 25.4mm 30mm; }')
    expect(html).toContain('困惑人类的不平等从哪里来')
    expect(html).toContain('研究用时 4 分 27 秒')
    expect(html).toContain('<table>')
    expect(html).toContain('https://www.oecd.org/en/publications/2024/11/how-s-life')
  })

  it('回答里的标签当字面量渲染，不进 DOM 当 HTML 执行', () => {
    const withScript: AgentConversation = {
      ...conversation,
      turns: [{
        ...conversation.turns[0],
        assistant: { ...conversation.turns[0].assistant, content: '注意 <script>alert(1)</script> 这段。', citations: [] },
      }],
    }
    const html = buildResearchReportHtml(buildResearchReport({ conversation: withScript }))
    expect(html).not.toContain('<script>alert(1)</script>')
    expect(html).toContain('&lt;script&gt;')
  })
})
