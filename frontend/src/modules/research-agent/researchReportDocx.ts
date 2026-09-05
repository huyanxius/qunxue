import {
  AlignmentType,
  BorderStyle,
  Document,
  ExternalHyperlink,
  ImageRun,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableLayoutType,
  TableRow,
  TextRun,
  WidthType,
  type IParagraphOptions,
  type IRunOptions,
} from 'docx'
import { marked, type Token, type Tokens } from 'marked'

import brandMarkSvg from '../../assets/qunxue-brand-mark.svg?raw'
import { BRAND_MARK_PNG_BASE64 } from './brandMarkPng'
import {
  referenceGroupTitles,
  researchReportFilename,
  type ResearchReferenceGroup,
  type ResearchReport,
} from './researchReportContent'

// 版式沿用《群学致知作品方案》那份 Word：正文宋体小四、1.5 倍行距、首行缩进两字，
// 标题黑体，西文一律 Times New Roman。数值都是 OOXML 原生单位——字号是半磅，
// 间距和缩进是 twip（1/20 磅，一个中文字符宽 240）。
const SERIF_CJK = '宋体'
const SANS_CJK = '黑体'
const KAI_CJK = '楷体'
const LATIN = 'Times New Roman'

const BODY_SIZE = 24
const LINE = 360
const AFTER = 120
const FIRST_LINE = 480
const BLOCK_INDENT = 420
// A4 去掉左右各 1701 twip 页边距后的版心宽度，表格按它均分列宽。
const CONTENT_WIDTH = 11906 - 1701 * 2

type Fonts = { ascii: string; hAnsi: string; eastAsia: string }

const bodyFonts: Fonts = { ascii: LATIN, hAnsi: LATIN, eastAsia: SERIF_CJK }
const headingFonts: Fonts = { ascii: LATIN, hAnsi: LATIN, eastAsia: SANS_CJK }
const kaiFonts: Fonts = { ascii: LATIN, hAnsi: LATIN, eastAsia: KAI_CJK }

function bodyParagraph(children: TextRun[] | (TextRun | ExternalHyperlink)[], options: Partial<IParagraphOptions> = {}) {
  return new Paragraph({
    spacing: { line: LINE, lineRule: 'auto', before: 0, after: AFTER },
    indent: { firstLine: FIRST_LINE },
    ...options,
    children,
  })
}

function headingParagraph(text: string, level: 1 | 2 | 3) {
  const size = level === 1 ? 30 : level === 2 ? 26 : 24
  const before = level === 1 ? 360 : level === 2 ? 240 : 160
  return new Paragraph({
    spacing: { line: LINE, lineRule: 'auto', before, after: level === 1 ? 200 : AFTER },
    indent: { firstLine: 0 },
    outlineLevel: level - 1,
    keepNext: true,
    children: [new TextRun({ text, bold: true, size, font: headingFonts, color: '1B1B18' })],
  })
}

function inlineRuns(tokens: Token[] | undefined, inherited: Partial<IRunOptions> = {}): (TextRun | ExternalHyperlink)[] {
  if (!tokens) return []
  return tokens.flatMap((token): (TextRun | ExternalHyperlink)[] => {
    switch (token.type) {
      case 'strong':
        return inlineRuns((token as Tokens.Strong).tokens, { ...inherited, bold: true })
      case 'em':
        return inlineRuns((token as Tokens.Em).tokens, { ...inherited, italics: true })
      case 'del':
        return inlineRuns((token as Tokens.Del).tokens, { ...inherited, strike: true })
      case 'link': {
        const link = token as Tokens.Link
        return [new ExternalHyperlink({
          link: link.href,
          children: inlineRuns(link.tokens, { ...inherited, color: '3B5F7A', underline: {} }),
        })]
      }
      case 'codespan':
        return [new TextRun({
          ...inherited,
          text: (token as Tokens.Codespan).text,
          font: { ascii: 'Consolas', hAnsi: 'Consolas', eastAsia: SERIF_CJK },
          size: BODY_SIZE - 2,
        })]
      case 'br':
        return [new TextRun({ ...inherited, text: '', break: 1 })]
      case 'image':
        return [new TextRun({ ...inherited, text: (token as Tokens.Image).text, font: bodyFonts, size: BODY_SIZE })]
      case 'escape':
      case 'text':
      case 'html': {
        const nested = (token as Tokens.Text).tokens
        if (nested?.length) return inlineRuns(nested, inherited)
        return [new TextRun({ ...inherited, text: (token as Tokens.Text).text, font: bodyFonts, size: BODY_SIZE })]
      }
      default:
        return [new TextRun({ ...inherited, text: 'raw' in token ? String(token.raw) : '', font: bodyFonts, size: BODY_SIZE })]
    }
  })
}

function cellParagraph(tokens: Token[] | undefined, bold: boolean) {
  return new Paragraph({
    spacing: { line: 280, lineRule: 'auto', before: 40, after: 40 },
    indent: { firstLine: 0 },
    children: inlineRuns(tokens, { bold, size: BODY_SIZE - 2 }),
  })
}

const hairline = { style: BorderStyle.SINGLE, size: 2, color: 'D8D4CC' } as const

function markdownTable(token: Tokens.Table) {
  // 不给列宽的话 Word 会按内容自动收缩，中文表头会被压成一字一行，所以这里显式均分。
  const columns = Math.max(1, token.header.length)
  const columnWidth = Math.floor(CONTENT_WIDTH / columns)
  const columnWidths = Array.from({ length: columns }, () => columnWidth)
  const cell = (tokens: Token[] | undefined, header: boolean) => new TableCell({
    width: { size: columnWidth, type: WidthType.DXA },
    ...(header ? { shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'F6F4EF' } } : {}),
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    children: [cellParagraph(tokens, header)],
  })
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    layout: TableLayoutType.FIXED,
    columnWidths,
    borders: { top: hairline, bottom: hairline, left: hairline, right: hairline, insideHorizontal: hairline, insideVertical: hairline },
    rows: [
      new TableRow({
        tableHeader: true,
        children: token.header.map((column) => cell(column.tokens, true)),
      }),
      ...token.rows.map((row) => new TableRow({
        children: row.map((column) => cell(column.tokens, false)),
      })),
    ],
  })
}

function listParagraphs(token: Tokens.List, depth: number): Paragraph[] {
  return token.items.flatMap((item, index) => {
    const marker = token.ordered ? `${(Number(token.start) || 1) + index}.` : depth ? '–' : '·'
    const own = item.tokens.filter((child) => child.type !== 'list')
    const nested = item.tokens.filter((child): child is Tokens.List => child.type === 'list')
    return [
      new Paragraph({
        spacing: { line: LINE, lineRule: 'auto', before: 0, after: AFTER },
        indent: { left: BLOCK_INDENT * (depth + 1), hanging: 240, firstLine: 0 },
        children: [
          new TextRun({ text: `${marker} `, font: bodyFonts, size: BODY_SIZE }),
          ...inlineRuns(own.flatMap((child) => 'tokens' in child && child.tokens ? child.tokens as Token[] : [])),
        ],
      }),
      ...nested.flatMap((child) => listParagraphs(child, depth + 1)),
    ]
  })
}

function blockContent(tokens: Token[]): (Paragraph | Table)[] {
  return tokens.flatMap((token): (Paragraph | Table)[] => {
    switch (token.type) {
      case 'heading': {
        const heading = token as Tokens.Heading
        return [headingParagraph(heading.text, heading.depth <= 1 ? 1 : heading.depth === 2 ? 2 : 3)]
      }
      case 'paragraph':
        return [bodyParagraph(inlineRuns((token as Tokens.Paragraph).tokens))]
      case 'list':
        return listParagraphs(token as Tokens.List, 0)
      case 'blockquote':
        return blockContent((token as Tokens.Blockquote).tokens).map((child) => child instanceof Paragraph
          ? new Paragraph({
            spacing: { line: LINE, lineRule: 'auto', before: 0, after: AFTER },
            indent: { left: BLOCK_INDENT, firstLine: 0 },
            border: { left: { style: BorderStyle.SINGLE, size: 12, color: 'C9C4BA', space: 10 } },
            children: [new TextRun({ text: (token as Tokens.Blockquote).text.replace(/\n+/g, ' ').trim(), font: bodyFonts, size: BODY_SIZE, color: '5A564E' })],
          })
          : child)
      case 'code':
        return (token as Tokens.Code).text.split('\n').map((line) => new Paragraph({
          spacing: { line: 260, lineRule: 'auto', before: 0, after: 0 },
          indent: { left: BLOCK_INDENT, firstLine: 0 },
          children: [new TextRun({ text: line || ' ', font: { ascii: 'Consolas', hAnsi: 'Consolas', eastAsia: SERIF_CJK }, size: BODY_SIZE - 4 })],
        }))
      case 'table':
        return [markdownTable(token as Tokens.Table), new Paragraph({ spacing: { after: AFTER }, children: [] })]
      case 'hr':
        return [new Paragraph({
          spacing: { before: AFTER, after: AFTER },
          border: { bottom: hairline },
          children: [],
        })]
      case 'space':
      case 'def':
        return []
      default:
        return 'text' in token && String(token.text).trim()
          ? [bodyParagraph([new TextRun({ text: String(token.text), font: bodyFonts, size: BODY_SIZE })])]
          : []
    }
  })
}

/** Markdown 走 marked 的词法分析，再逐块映射到 Word 段落，不经过 HTML。 */
export function markdownBlocks(markdown: string): (Paragraph | Table)[] {
  return blockContent(marked.lexer(markdown) as Token[])
}

function base64ToBytes(value: string) {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return bytes
}

function brandMarkRun() {
  return new ImageRun({
    type: 'svg',
    data: Uint8Array.from(new TextEncoder().encode(brandMarkSvg)),
    fallback: { type: 'png', data: base64ToBytes(BRAND_MARK_PNG_BASE64) },
    transformation: { width: 30, height: 30 },
    altText: { name: '群学致知', title: '群学致知', description: '群学致知品牌标志' },
  })
}

function letterhead() {
  return new Paragraph({
    spacing: { before: 0, after: 120, line: 240, lineRule: 'auto' },
    indent: { firstLine: 0 },
    children: [
      brandMarkRun(),
      new TextRun({ text: '  群学致知', bold: true, size: 26, font: headingFonts, color: '1B1B18' }),
    ],
  })
}

function referenceParagraphs(report: ResearchReport) {
  const groups: ResearchReferenceGroup[] = ['knowledge', 'web', 'material']
  return groups.flatMap((group) => {
    const entries = report.references.filter((reference) => reference.group === group)
    if (!entries.length) return []
    return [
      new Paragraph({
        spacing: { before: 240, after: AFTER, line: LINE, lineRule: 'auto' },
        indent: { firstLine: 0 },
        keepNext: true,
        children: [new TextRun({ text: referenceGroupTitles[group], bold: true, size: 24, font: headingFonts, color: '1B1B18' })],
      }),
      ...entries.map((reference) => new Paragraph({
        spacing: { line: LINE, lineRule: 'auto', before: 0, after: 80 },
        indent: { left: BLOCK_INDENT, hanging: BLOCK_INDENT, firstLine: 0 },
        children: [
          new TextRun({ text: `[${reference.index}] `, size: BODY_SIZE - 2, font: bodyFonts }),
          new TextRun({ text: reference.title, size: BODY_SIZE - 2, font: bodyFonts }),
          ...(reference.detail ? [new TextRun({ text: ` · ${reference.detail}`, size: BODY_SIZE - 2, font: bodyFonts, color: '6B665C' })] : []),
          ...(reference.url ? [
            new TextRun({ text: ' ', size: BODY_SIZE - 2, font: bodyFonts }),
            new ExternalHyperlink({
              link: reference.url,
              children: [new TextRun({ text: reference.url, size: BODY_SIZE - 4, font: bodyFonts, color: '3B5F7A', underline: {} })],
            }),
          ] : []),
        ],
      })),
    ]
  })
}

export async function createResearchReportDocx(report: ResearchReport) {
  const children: (Paragraph | Table)[] = [
    letterhead(),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 480, after: 120, line: 240, lineRule: 'auto' },
      indent: { firstLine: 0 },
      children: [new TextRun({ text: report.title, bold: true, size: 40, font: headingFonts, color: '1B1B18' })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 120, line: LINE, lineRule: 'auto' },
      indent: { firstLine: 0 },
      children: [new TextRun({ text: report.subtitle, size: 30, font: kaiFonts, color: '4A463E' })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 360, line: 240, lineRule: 'auto' },
      indent: { firstLine: 0 },
      children: [new TextRun({ text: report.meta.join('　·　'), size: 18, font: bodyFonts, color: '6B665C' })],
    }),
  ]

  report.sections.forEach((section, index) => {
    const label = report.sections.length > 1 ? `${index + 1}　${section.question}` : section.question
    children.push(headingParagraph(label, 1))
    children.push(...markdownBlocks(section.answer))
  })

  if (report.references.length) {
    children.push(headingParagraph('引用资料', 1))
    children.push(bodyParagraph([new TextRun({
      text: '以下为本次研究实际读取并据以作答的全部来源，按知识库、公开网页、个人研究材料分列。',
      size: BODY_SIZE - 2,
      font: bodyFonts,
      color: '6B665C',
    })], { indent: { firstLine: 0 } }))
    children.push(...referenceParagraphs(report))
  }

  const document = new Document({
    creator: '群学致知',
    title: report.title,
    description: '由群学致知研究 Agent 的对话导出',
    styles: {
      default: {
        document: {
          run: { font: bodyFonts, size: BODY_SIZE, color: '1B1B18' },
          paragraph: { spacing: { line: LINE, lineRule: 'auto', after: AFTER } },
        },
      },
    },
    sections: [{
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1701 },
        },
      },
      children,
    }],
  })
  return await Packer.toBlob(document)
}

export function researchReportDocxFilename(report: ResearchReport) {
  return researchReportFilename(report, 'docx')
}
