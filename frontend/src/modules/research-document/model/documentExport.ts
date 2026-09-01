import { Markdown, MarkdownManager } from '@tiptap/markdown'
import StarterKit from '@tiptap/starter-kit'
import CSL from 'citeproc'
import {
  AlignmentType,
  Document,
  HeadingLevel,
  Packer,
  Paragraph,
  TextRun,
} from 'docx'
import { marked } from 'marked'

import asaStyle from '../csl/american-sociological-association.csl?raw'
import gbStyle from '../csl/china-national-standard-gb-t-7714-2015-author-date.csl?raw'
import chicagoStyle from '../csl/chicago-author-date.csl?raw'
import enUsLocale from '../csl/locales-en-US.xml?raw'
import zhCnLocale from '../csl/locales-zh-CN.xml?raw'

export type CitationState = 'verified' | 'needs_verification' | 'broken' | 'tombstoned'

export type ExportCitation = {
  citationId: string
  sourceId: string
  sourceVersion?: string | null
  locator: Record<string, unknown>
  state: CitationState
  csl: ({ id: string } & Record<string, unknown>) | null
}

export type DocumentExportSection = {
  title: string
  markdown: string
}

export type DocumentTemplateId = 'asa' | 'chinese-social-science' | 'custom'

export type DocumentExportInput = {
  title: string
  templateId: DocumentTemplateId
  sections: DocumentExportSection[]
  citationAudit: ExportCitation[]
}

const STYLE_XML: Record<string, string> = {
  'american-sociological-association': asaStyle,
  'china-national-standard-gb-t-7714-2015-author-date': gbStyle,
  'chicago-author-date': chicagoStyle,
}

const LOCALE_XML: Record<string, string> = {
  'en-US': enUsLocale,
  'zh-CN': zhCnLocale,
}

export function registerCustomCslStyle(styleId: string, xml: string) {
  const normalizedId = styleId.trim()
  if (!normalizedId || !xml.includes('<style')) throw new Error('CSL 样式文件无效。')
  STYLE_XML[normalizedId] = xml
  return normalizedId
}

export function formatBibliography(
  citations: ExportCitation[],
  options: { styleId: string; locale: string; customStyleXml?: string },
) {
  if (options.customStyleXml) registerCustomCslStyle(options.styleId, options.customStyleXml)
  const items = citations.flatMap((citation) => citation.csl ? [citation.csl] : [])
  if (!items.length) return ''
  const style = STYLE_XML[options.styleId]
  if (!style) throw new Error(`未找到 CSL 样式：${options.styleId}`)
  const itemById = Object.fromEntries(items.map((item) => [item.id, item]))
  const locale = LOCALE_XML[options.locale] ?? LOCALE_XML['en-US']
  const processor = new CSL.Engine({
    retrieveItem: (id: string) => itemById[id],
    retrieveLocale: () => locale,
  }, style, options.locale, true)
  processor.setOutputFormat('html')
  processor.updateItems(items.map((item) => item.id))
  const bibliography = processor.makeBibliography()
  if (!bibliography) return ''
  const [parameters, entries] = bibliography
  return sanitizeCslHtml(`${parameters.bibstart}${entries.join('')}${parameters.bibend}`)
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function sanitizeCslHtml(value: string) {
  return value
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*')/gi, '')
    .replace(/(href\s*=\s*["'])javascript:/gi, '$1')
}

function embedCss(value: string) {
  // A persisted template is CSS data, never permission to terminate the preview's style element.
  return value.replace(/<\/style/gi, '<\\/style')
}

function renderMarkdown(markdown: string) {
  const withoutRawHtml = markdown.replace(/<(?=\/?[A-Za-z!])/g, '&lt;')
  return marked.parse(withoutRawHtml, { async: false })
}

const PRINT_CSS: Record<Exclude<DocumentTemplateId, 'custom'>, string> = {
  asa: `
    @page { size: letter; margin: 1in; @bottom-center { content: counter(page); } }
    body { color: #171717; font-family: "Times New Roman", Times, serif; font-size: 12pt; line-height: 2; }
    .title-page { min-height: 8in; display: grid; place-content: center; text-align: center; break-after: page; }
    h1 { font-size: 16pt; } h2 { font-size: 12pt; text-align: left; } h3 { font-size: 12pt; font-style: italic; }
    p { margin: 0; text-indent: .5in; } table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #777; padding: 4pt; }
  `,
  'chinese-social-science': `
    @page { size: A4; margin: 25mm 24mm 24mm; @bottom-center { content: counter(page); } }
    body { color: #171717; font-family: "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", serif; font-size: 12pt; line-height: 1.8; text-autospace: normal; }
    .title-page { min-height: 235mm; display: grid; place-content: center; text-align: center; break-after: page; }
    h1 { font-family: "Heiti SC", "Noto Sans CJK SC", sans-serif; font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 14pt; }
    p { margin: 0; text-indent: 2em; orphans: 2; widows: 2; text-align: justify; } table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #777; padding: 4pt; }
  `,
}

function citationWarnings(citations: ExportCitation[]) {
  return citations.filter((citation) => citation.state !== 'verified' || !citation.csl)
}

export function buildPrintableDocument(
  input: DocumentExportInput & { bibliographyHtml: string; customCss?: string },
) {
  const profile = input.templateId === 'custom' ? PRINT_CSS['chinese-social-science'] : PRINT_CSS[input.templateId]
  const sections = input.sections.map((section) => `
    <section class="paper-section">
      <h2>${escapeHtml(section.title)}</h2>
      ${renderMarkdown(section.markdown)}
    </section>
  `).join('')
  const warnings = citationWarnings(input.citationAudit)
  const warningHtml = warnings.length ? `
    <aside class="citation-warnings">
      <h2>引用异常</h2>
      <ul>${warnings.map((citation) => `<li><code>${escapeHtml(citation.sourceId)}</code> · ${escapeHtml(citation.state)}</li>`).join('')}</ul>
    </aside>
  ` : ''

  return `<!doctype html>
  <html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(input.title)}</title>
  <style>${profile}${embedCss(input.customCss ?? '')}
    body { max-width: 180mm; margin: 0 auto; } .bibliography { break-before: page; }
    .citation-warnings { border: 1px solid #8b2c2c; padding: 12pt; color: #6f1d1d; }
    code { overflow-wrap: anywhere; }
  </style></head><body>
    <header class="title-page"><h1>${escapeHtml(input.title)}</h1></header>
    <main>${sections}</main>
    ${warningHtml}
    <section class="bibliography"><h2>参考文献</h2>${sanitizeCslHtml(input.bibliographyHtml)}</section>
  </body></html>`
}

const markdownManager = new MarkdownManager({ extensions: [StarterKit, Markdown] })

function textRuns(content: Array<Record<string, unknown>> | undefined): TextRun[] {
  return (content ?? []).flatMap((node) => {
    if (node.type === 'text') {
      const marks = Array.isArray(node.marks) ? node.marks as Array<{ type?: string }> : []
      return [new TextRun({
        text: String(node.text ?? ''),
        bold: marks.some((mark) => mark.type === 'bold'),
        italics: marks.some((mark) => mark.type === 'italic'),
      })]
    }
    return textRuns(Array.isArray(node.content) ? node.content as Array<Record<string, unknown>> : undefined)
  })
}

function markdownParagraphs(source: string): Paragraph[] {
  const parsed = markdownManager.parse(source)
  return (parsed.content ?? []).map((node) => {
    const attrs = node.attrs as { level?: number } | undefined
    if (node.type === 'heading') {
      const heading = attrs?.level === 1 ? HeadingLevel.HEADING_1
        : attrs?.level === 2 ? HeadingLevel.HEADING_2
          : HeadingLevel.HEADING_3
      return new Paragraph({ heading, children: textRuns(node.content as Array<Record<string, unknown>> | undefined) })
    }
    return new Paragraph({ children: textRuns(node.content as Array<Record<string, unknown>> | undefined) })
  })
}

export async function createDocxExport(
  input: DocumentExportInput & { bibliographyText: string },
) {
  const isAsa = input.templateId === 'asa'
  const font = isAsa ? 'Times New Roman' : '宋体'
  const children: Paragraph[] = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 720 },
      children: [new TextRun({ text: input.title, bold: true, size: isAsa ? 32 : 40 })],
    }),
  ]
  for (const section of input.sections) {
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(section.title)] }))
    children.push(...markdownParagraphs(section.markdown))
  }
  children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('参考文献')] }))
  children.push(...input.bibliographyText.split(/\n+/).filter(Boolean).map((entry) => new Paragraph(entry)))
  const warnings = citationWarnings(input.citationAudit)
  if (warnings.length) {
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('引用异常')] }))
    children.push(...warnings.map((citation) => new Paragraph(`${citation.sourceId} · ${citation.state}`)))
  }

  const document = new Document({
    styles: {
      default: {
        document: { run: { font, size: 24 }, paragraph: { spacing: { line: isAsa ? 480 : 432 } } },
      },
    },
    sections: [{
      properties: {
        page: {
          size: isAsa ? { width: 12240, height: 15840 } : { width: 11906, height: 16838 },
          margin: isAsa
            ? { top: 1440, right: 1440, bottom: 1440, left: 1440 }
            : { top: 1417, right: 1361, bottom: 1361, left: 1361 },
        },
      },
      children,
    }],
  })
  return await Packer.toBlob(document)
}
