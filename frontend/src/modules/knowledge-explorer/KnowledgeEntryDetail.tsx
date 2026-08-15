import { createElement, useEffect, useMemo, useState, type ReactNode } from 'react'
import { HighlighterIcon } from '@phosphor-icons/react'
import Markdown from 'react-markdown'

import { buildMarkdownOutline, type MarkdownHeading } from './markdownOutline'
import { activeHeadingAtOffset } from './scrollSpy'
import type { KnowledgeEntryDetail } from './types'
import { reviewStatusLabels, verificationStatusLabels } from './labels'
import { describeTaxonomyNode, dimensionTone } from './taxonomyPresentation'

interface KnowledgeEntryDetailProps {
  detail: KnowledgeEntryDetail
  onStartResearch: (input: { theoryId: string; theoryName: string }) => void
}

function sourceMetadata(source: KnowledgeEntryDetail['sources'][number]) {
  return [
    source.authorsOrInstitution.join('、'),
    source.year,
    source.publication,
    source.sourceType,
    source.locator,
  ].filter(Boolean).join(' · ')
}

function markdownForDisplay(content: string) {
  return content.replace(/(\*\*[^*\n]+：\*\*)(?=\S)/g, '$1 ')
}

interface MarkdownAstNode {
  type: string
  value?: string
  url?: string
  children?: MarkdownAstNode[]
  data?: {
    hProperties?: Record<string, unknown>
  }
}

type EvidenceDisplayMode = 'expanded' | 'hover' | 'annotations'

function markdownNodeText(node: MarkdownAstNode): string {
  if (node.value) return node.value
  return node.children?.map(markdownNodeText).join('') ?? ''
}

function evidenceCount(text: string) {
  const declared = text.match(/观点[—-]文献依据[（(](\d+)条[）)]/)
  if (declared) return Number(declared[1])
  const numberedClaims = text.match(/P\d+\s*\|/g)
  return Math.max(1, numberedClaims?.length ?? 0)
}

function remarkEvidenceClaims() {
  let evidenceIndex = 0
  return (root: MarkdownAstNode) => {
    root.children?.forEach((node, index, children) => {
      if (node.type !== 'blockquote' || index === 0) return
      const text = markdownNodeText(node)
      if (!/文献[：:]|观点[—-]文献依据/.test(text)) return

      const claim = children[index - 1]
      if (claim.type !== 'paragraph') return

      evidenceIndex += 1
      const count = evidenceCount(text)
      const noteId = `knowledge-evidence-${index}`
      claim.data = {
        ...claim.data,
        hProperties: {
          ...claim.data?.hProperties,
          className: ['knowledge-reader__evidence-claim'],
          tabIndex: 0,
          'aria-describedby': noteId,
        },
      }
      claim.children = [
        ...(claim.children ?? []),
        {
          type: 'link',
          value: String(evidenceIndex),
          url: `#${noteId}`,
          children: [{ type: 'text', value: String(evidenceIndex) }],
          data: {
            hProperties: {
              className: ['knowledge-reader__evidence-marker'],
              'data-evidence-id': noteId,
              'aria-label': `打开第 ${evidenceIndex} 条文献依据`,
            },
          },
        },
      ]
      node.data = {
        ...node.data,
        hProperties: {
          ...node.data?.hProperties,
          id: noteId,
          role: 'note',
          'aria-label': `文献依据，${count} 条`,
          'data-content-role': 'evidence',
        },
      }
    })
  }
}

function KnowledgeMarkdown({
  content,
  evidenceMode,
  headings,
}: {
  content: string
  evidenceMode: EvidenceDisplayMode
  headings: readonly MarkdownHeading[]
}) {
  const [openEvidenceId, setOpenEvidenceId] = useState<string>()
  let headingIndex = 0
  function heading(level: number, children: ReactNode) {
    const current = headings[headingIndex]
    headingIndex += 1
    const presentation = current ? describeTaxonomyNode(current.title) : undefined
    if (presentation?.kind === 'stage') {
      return createElement(
        `h${level}`,
        { id: current?.id, 'data-stage': presentation.stage },
        <><span className="knowledge-reader__stage-badge">{presentation.badge}</span>{' '}{presentation.label}</>,
      )
    }
    return createElement(`h${level}`, { id: current?.id }, children)
  }

  useEffect(() => setOpenEvidenceId(undefined), [evidenceMode])

  return (
    <div className="knowledge-reader__content" data-evidence-display={evidenceMode}>
      <Markdown
        remarkPlugins={[remarkEvidenceClaims]}
        components={{
          h1: ({ children }) => heading(1, children),
          h2: ({ children }) => heading(2, children),
          h3: ({ children }) => heading(3, children),
          h4: ({ children }) => heading(4, children),
          h5: ({ children }) => heading(5, children),
          h6: ({ children }) => heading(6, children),
          a: ({ children, className, href, node }) => {
            const evidenceId = node?.properties?.['data-evidence-id']
            if (className?.includes('knowledge-reader__evidence-marker') && typeof evidenceId === 'string') {
              return (
                <button
                  type="button"
                  className={className}
                  aria-label={node.properties['aria-label'] as string}
                  aria-expanded={openEvidenceId === evidenceId}
                  aria-controls={evidenceId}
                  onClick={() => setOpenEvidenceId((current) => current === evidenceId ? undefined : evidenceId)}
                >{children}</button>
              )
            }
            return <a href={href} rel="noreferrer">{children}</a>
          },
          blockquote: ({ children, node, ...props }) => {
            const evidenceId = typeof node?.properties?.id === 'string' ? node.properties.id : undefined
            return (
              <blockquote {...props} data-open={evidenceId === openEvidenceId ? 'true' : undefined}>
                {evidenceId === openEvidenceId ? (
                  <button className="knowledge-reader__evidence-close" type="button" aria-label="关闭文献依据" onClick={() => setOpenEvidenceId(undefined)}>×</button>
                ) : null}
                {children}
              </blockquote>
            )
          },
          pre: ({ children }) => <div className="knowledge-reader__wide"><pre>{children}</pre></div>,
          table: ({ children }) => <div className="knowledge-reader__wide"><table>{children}</table></div>,
        }}
      >{markdownForDisplay(content)}</Markdown>
    </div>
  )
}

function ReadingTools({ evidenceMode, onChangeEvidenceMode }: {
  evidenceMode: EvidenceDisplayMode
  onChangeEvidenceMode: (mode: EvidenceDisplayMode) => void
}) {
  return (
    <div className="knowledge-reader__tools" role="group" aria-label="阅读工具">
      <p>阅读工具</p>
      <div className="knowledge-reader__evidence-modes" role="radiogroup" aria-label="文献显示方式">
        <button type="button" role="radio" aria-label="默认展开全部文献" aria-checked={evidenceMode === 'expanded'} onClick={() => onChangeEvidenceMode('expanded')}>展开</button>
        <button type="button" role="radio" aria-label="悬浮正文显示文献" aria-checked={evidenceMode === 'hover'} onClick={() => onChangeEvidenceMode('hover')}>悬浮</button>
        <button type="button" role="radio" aria-label="点击批注显示文献" aria-checked={evidenceMode === 'annotations'} onClick={() => onChangeEvidenceMode('annotations')}>批注</button>
      </div>
      <button type="button" aria-label="划线批注（暂未开放）" title="本期暂不引入划线批注" disabled>
        <HighlighterIcon size={14} />
        <span><strong>划线批注</strong><small>暂未开放</small></span>
      </button>
    </div>
  )
}

function Outline({ headings, activeId }: { headings: readonly MarkdownHeading[]; activeId?: string }) {
  if (headings.length === 0) return <p className="knowledge-reader__outline-empty">正文未设置章节标题</p>
  return (
    <ol>
      {headings.map((heading) => (
        <li key={heading.id} data-depth={heading.depth}>
          <a href={`#${heading.id}`} aria-current={activeId === heading.id ? 'location' : undefined}>{heading.title}</a>
        </li>
      ))}
    </ol>
  )
}

export function KnowledgeEntryDetail({ detail, onStartResearch }: KnowledgeEntryDetailProps) {
  const theory = detail.theoryProfile
  const tone = dimensionTone(detail.dimensionId)
  const category = describeTaxonomyNode(detail.category)
  const canSeedTheory = theory?.relatedKnowledgeIds.includes(detail.knowledgeId)
  const outline = useMemo(() => buildMarkdownOutline(detail.content), [detail.content])
  const [activeHeadingId, setActiveHeadingId] = useState(outline.headings[0]?.id)
  const [evidenceMode, setEvidenceMode] = useState<EvidenceDisplayMode>('annotations')
  const breadcrumbNodes = detail.directoryPath.slice(
    0,
    detail.directoryPath.length >= 4 ? -2 : -1,
  )

  useEffect(() => {
    const scrollContainer = document.querySelector<HTMLElement>('.knowledge-reader-page')
    if (!scrollContainer) return undefined
    const nodes = outline.headings
      .map((heading) => document.getElementById(heading.id))
      .filter((node): node is HTMLElement => Boolean(node))
    let animationFrame = 0

    function updateActiveHeading() {
      animationFrame = 0
      const containerTop = scrollContainer.getBoundingClientRect().top
      const readingOffset = containerTop + Math.min(180, scrollContainer.clientHeight * 0.25)
      const activeId = activeHeadingAtOffset(
        nodes.map((node) => ({ id: node.id, top: node.getBoundingClientRect().top })),
        readingOffset,
      )
      if (activeId) setActiveHeadingId(activeId)
    }

    function scheduleUpdate() {
      if (animationFrame) return
      animationFrame = window.requestAnimationFrame(updateActiveHeading)
    }

    scheduleUpdate()
    scrollContainer.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)
    return () => {
      scrollContainer.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
    }
  }, [outline.headings])

  return (
    <div className="knowledge-reader" data-dimension-tone={tone}>
      <header className="knowledge-reader__hero">
        <div className="knowledge-reader__breadcrumbs">{breadcrumbNodes.map((node) => node.title).join(' / ')}</div>
        <div className="knowledge-reader__identity-tags">
          <span data-object-role="dimension">{detail.dimensionId} {detail.dimension}</span>
          <span data-object-role="category" data-stage={category.stage}>{category.badge ?? '分类'} {category.label}</span>
          <span data-object-role="concept">{detail.knowledgeId.split(':').at(-1)}</span>
        </div>
        <h1>{detail.title}</h1>
        {detail.aliases.length > 0 ? <p className="knowledge-reader__aliases">亦称：{detail.aliases.join('、')}</p> : null}
        <dl className="knowledge-reader__facts">
          <div><dt>审核状态</dt><dd data-review-status={detail.reviewStatus}>{reviewStatusLabels[detail.reviewStatus]}</dd></div>
          <div><dt>来源记录</dt><dd>{detail.sources.length} 条</dd></div>
          <div><dt>显式关系</dt><dd>{detail.relations.length} 条</dd></div>
          <div><dt>内容版本</dt><dd>v{detail.contentVersion}</dd></div>
        </dl>
      </header>

      <details className="knowledge-reader__mobile-outline">
        <summary>本文目录 <span>{outline.headings.length} 节</span></summary>
        <nav aria-label="移动端本文目录"><Outline headings={outline.headings} activeId={activeHeadingId} /></nav>
      </details>

      <div className="knowledge-reader__layout">
        <aside className="knowledge-reader__rail">
          <nav className="knowledge-reader__outline" aria-label="本文目录">
            <p>本文目录</p>
            <Outline headings={outline.headings} activeId={activeHeadingId} />
          </nav>
          <ReadingTools
            evidenceMode={evidenceMode}
            onChangeEvidenceMode={setEvidenceMode}
          />
        </aside>
        <article className="knowledge-reader__article">
          <KnowledgeMarkdown
            content={detail.content}
            evidenceMode={evidenceMode}
            headings={outline.headings}
          />

          <section className="knowledge-reader__section" data-section-role="evidence" aria-labelledby="knowledge-sources-title">
            <header><p>证据记录</p><h2 id="knowledge-sources-title">来源与核验</h2></header>
            {detail.sources.length > 0 ? (
              <ol className="knowledge-reader__evidence-list">
                {detail.sources.map((source, index) => (
                  <li key={source.sourceId} data-verification-status={source.verificationStatus}>
                    <span className="knowledge-reader__evidence-index">{String(index + 1).padStart(2, '0')}</span>
                    <div>
                      <p>{source.url ? <a href={source.url}>{source.title}</a> : source.title}</p>
                      <small>{sourceMetadata(source)}</small>
                    </div>
                    <dl>
                      <div><dt>核验状态</dt><dd>{verificationStatusLabels[source.verificationStatus]}</dd></div>
                      <div><dt>使用边界</dt><dd>{source.useBoundary}</dd></div>
                    </dl>
                  </li>
                ))}
              </ol>
            ) : <p className="knowledge-reader__empty">当前发布未提供可展示来源，不能据此视为已核验事实。</p>}
          </section>

          <section className="knowledge-reader__section" data-section-role="relation" aria-labelledby="knowledge-relations-title">
            <header><p>审核关系</p><h2 id="knowledge-relations-title">已审核显式关系</h2></header>
            {detail.relations.length > 0 ? (
              <ul className="knowledge-reader__relation-list">
                {detail.relations.map((relation) => {
                  const targetId = relation.sourceKnowledgeId === detail.knowledgeId ? relation.targetKnowledgeId : relation.sourceKnowledgeId
                  return (
                    <li key={relation.relationId}>
                      <strong>{targetId}</strong>
                      <span>{relation.relationType} · {relation.direction} · {reviewStatusLabels[relation.reviewStatus]}</span>
                      <p>{relation.description}</p>
                      {relation.evidenceSourceIds.length > 0 ? <small>依据来源：{relation.evidenceSourceIds.join('、')}</small> : null}
                    </li>
                  )
                })}
              </ul>
            ) : <p className="knowledge-reader__empty">当前发布没有与此条目关联的已审核关系。</p>}
          </section>

          {theory ? (
            <section className="knowledge-reader__theory" data-section-role="research" aria-labelledby="knowledge-theory-title">
              <div><p>研究入口</p><h2 id="knowledge-theory-title">{theory.title}</h2><span>{reviewStatusLabels[theory.reviewStatus]} · {theory.matchEligible ? '可用于理论匹配' : '当前不用于理论匹配'}</span></div>
              {canSeedTheory ? <button type="button" onClick={() => onStartResearch({ theoryId: theory.theoryId, theoryName: theory.title })}>以此理论开始研究 <span aria-hidden="true">↗</span></button> : null}
            </section>
          ) : null}
        </article>
      </div>
    </div>
  )
}
