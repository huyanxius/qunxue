import { marked } from 'marked'

import brandMarkSvg from '../../assets/qunxue-brand-mark.svg?raw'
import {
  referenceGroupTitles,
  type ResearchReferenceGroup,
  type ResearchReport,
} from './researchReportContent'

// PDF 走浏览器自己的排版引擎：同一份版式规格用 CSS 再写一遍，字号行距与 Word 那边
// 一一对应（Word 的半磅换算成 pt，twip 换算成 em），这样两份导出看上去是同一份文件。
const PRINT_CSS = `
  @page { size: A4; margin: 25.4mm 30mm; }
  * { box-sizing: border-box; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    margin: 0;
    color: #1b1b18;
    font-family: "Times New Roman", "Songti SC", "宋体", "Noto Serif CJK SC", serif;
    font-size: 12pt;
    line-height: 1.5;
    text-autospace: ideograph-alpha ideograph-numeric;
  }
  .letterhead {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .letterhead svg { width: 30px; height: 30px; flex: 0 0 auto; }
  .letterhead b {
    font-family: "Times New Roman", "Heiti SC", "黑体", "Noto Sans CJK SC", sans-serif;
    font-size: 13pt;
    font-weight: 700;
    letter-spacing: .02em;
  }
  .masthead { margin: 30pt 0 18pt; text-align: center; }
  .masthead h1 {
    margin: 0 0 6pt;
    font-family: "Times New Roman", "Heiti SC", "黑体", "Noto Sans CJK SC", sans-serif;
    font-size: 20pt;
    font-weight: 700;
    line-height: 1.25;
  }
  .masthead .subtitle {
    margin: 0 0 6pt;
    font-family: "Kaiti SC", "楷体", "Times New Roman", serif;
    font-size: 15pt;
    color: #4a463e;
    text-align: center;
    text-indent: 0;
  }
  .masthead .meta {
    margin: 0;
    font-size: 9pt;
    color: #6b665c;
    text-align: center;
    text-indent: 0;
  }
  h2 {
    margin: 18pt 0 10pt;
    font-family: "Times New Roman", "Heiti SC", "黑体", "Noto Sans CJK SC", sans-serif;
    font-size: 15pt;
    font-weight: 700;
    line-height: 1.4;
    break-after: avoid;
  }
  h3 { margin: 12pt 0 6pt; font-family: "Times New Roman", "Heiti SC", "黑体", sans-serif; font-size: 13pt; font-weight: 700; break-after: avoid; }
  h4, h5, h6 { margin: 8pt 0 4pt; font-family: "Times New Roman", "Heiti SC", "黑体", sans-serif; font-size: 12pt; font-weight: 700; break-after: avoid; }
  p { margin: 0 0 6pt; text-indent: 2em; text-align: justify; orphans: 2; widows: 2; }
  ul, ol { margin: 0 0 6pt; padding-left: 2em; }
  li { margin-bottom: 3pt; }
  li > p { text-indent: 0; }
  blockquote {
    margin: 0 0 6pt;
    padding-left: 12pt;
    border-left: 2px solid #d8d4cc;
    color: #5a564e;
  }
  blockquote p { text-indent: 0; }
  pre {
    margin: 0 0 6pt;
    padding: 8pt 10pt;
    overflow-x: auto;
    border-radius: 3px;
    background: #f6f4ef;
    font-family: Consolas, "SF Mono", monospace;
    font-size: 9.5pt;
    line-height: 1.45;
  }
  code { font-family: Consolas, "SF Mono", monospace; font-size: .92em; }
  table { width: 100%; margin: 0 0 8pt; border-collapse: collapse; font-size: 10.5pt; }
  th, td { padding: 4pt 6pt; border: 1px solid #d8d4cc; text-align: left; vertical-align: top; }
  th { background: #f6f4ef; font-weight: 700; }
  hr { margin: 12pt 0; border: 0; border-top: 1px solid #d8d4cc; }
  a { color: #3b5f7a; text-decoration: none; word-break: break-all; }
  .references { break-inside: auto; }
  .references h3 { margin-top: 12pt; }
  .references ol { margin: 0; padding: 0; list-style: none; }
  .references li {
    margin-bottom: 4pt;
    padding-left: 2.2em;
    text-indent: -2.2em;
    font-size: 10.5pt;
    line-height: 1.5;
  }
  .references .locator { color: #6b665c; }
  .references .url { font-size: 10pt; }
  .note { margin-bottom: 10pt; color: #6b665c; font-size: 10.5pt; text-indent: 0; }
`

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function renderMarkdown(markdown: string) {
  // 回答是模型生成的文本，任何看着像标签的东西都当字面量渲染，不进 DOM 当 HTML 执行。
  const withoutRawHtml = markdown.replace(/<(?=\/?[A-Za-z!])/g, '&lt;')
  return marked.parse(withoutRawHtml, { async: false })
}

function referencesHtml(report: ResearchReport) {
  if (!report.references.length) return ''
  const groups: ResearchReferenceGroup[] = ['knowledge', 'web', 'material']
  const blocks = groups.flatMap((group) => {
    const entries = report.references.filter((reference) => reference.group === group)
    if (!entries.length) return []
    const items = entries.map((reference) => {
      const locator = reference.detail ? ` <span class="locator">· ${escapeHtml(reference.detail)}</span>` : ''
      const url = reference.url
        ? ` <a class="url" href="${escapeHtml(reference.url)}">${escapeHtml(reference.url)}</a>`
        : ''
      return `<li>[${reference.index}] ${escapeHtml(reference.title)}${locator}${url}</li>`
    }).join('')
    return [`<h3>${escapeHtml(referenceGroupTitles[group])}</h3><ol>${items}</ol>`]
  }).join('')
  return `<section class="references">
    <h2>引用资料</h2>
    <p class="note">以下为本次研究实际读取并据以作答的全部来源，按知识库、公开网页、个人研究材料分列。</p>
    ${blocks}
  </section>`
}

export function buildResearchReportHtml(report: ResearchReport) {
  const sections = report.sections.map((section, index) => {
    const label = report.sections.length > 1
      ? `${index + 1}　${escapeHtml(section.question)}`
      : escapeHtml(section.question)
    return `<section><h2>${label}</h2>${renderMarkdown(section.answer)}</section>`
  }).join('')
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(report.title)}</title>
<style>${PRINT_CSS}</style></head><body>
  <header class="letterhead">${brandMarkSvg}<b>群学致知</b></header>
  <div class="masthead">
    <h1>${escapeHtml(report.title)}</h1>
    <p class="subtitle">${escapeHtml(report.subtitle)}</p>
    <p class="meta">${report.meta.map(escapeHtml).join('　·　')}</p>
  </div>
  <main>${sections}</main>
  ${referencesHtml(report)}
</body></html>`
}

/**
 * PDF 交给浏览器的打印管线：中文 PDF 若在前端自己绘制就得随包附一份几 MB 的中日韩
 * 字体，打印管线用系统字体，排版和字形都更好，代价是最后一步落在系统的打印面板里。
 */
export function openResearchReportPrintWindow(report: ResearchReport) {
  const preview = window.open('', '_blank')
  if (!preview) throw new Error('浏览器阻止了导出窗口，请允许弹出窗口后重试。')
  preview.document.write(buildResearchReportHtml(report))
  preview.document.close()
  preview.focus()
  const start = () => preview.print()
  if (preview.document.readyState === 'complete') start()
  else preview.addEventListener('load', start, { once: true })
  return preview
}
