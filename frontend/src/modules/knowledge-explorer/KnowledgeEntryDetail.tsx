import { createElement, useEffect, useMemo, useState, type ReactNode } from 'react'
import Markdown from 'react-markdown'

import { buildMarkdownOutline, type MarkdownHeading } from './markdownOutline'
import type { KnowledgeEntryDetail } from './types'
import { reviewStatusLabels, verificationStatusLabels } from './labels'

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

function KnowledgeMarkdown({ content, headings }: { content: string; headings: readonly MarkdownHeading[] }) {
  let headingIndex = 0
  function heading(level: number, children: ReactNode) {
    const current = headings[headingIndex]
    headingIndex += 1
    return createElement(`h${level}`, { id: current?.id }, children)
  }

  return (
    <Markdown components={{
      h1: ({ children }) => heading(1, children),
      h2: ({ children }) => heading(2, children),
      h3: ({ children }) => heading(3, children),
      h4: ({ children }) => heading(4, children),
      h5: ({ children }) => heading(5, children),
      h6: ({ children }) => heading(6, children),
      a: ({ children, href }) => <a href={href} rel="noreferrer">{children}</a>,
      pre: ({ children }) => <div className="knowledge-reader__wide"><pre>{children}</pre></div>,
      table: ({ children }) => <div className="knowledge-reader__wide"><table>{children}</table></div>,
    }}>{markdownForDisplay(content)}</Markdown>
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
  const canSeedTheory = theory?.relatedKnowledgeIds.includes(detail.knowledgeId)
  const outline = useMemo(() => buildMarkdownOutline(detail.content), [detail.content])
  const [activeHeadingId, setActiveHeadingId] = useState(outline.headings[0]?.id)
  const breadcrumbNodes = detail.directoryPath.slice(
    0,
    detail.directoryPath.length >= 4 ? -2 : -1,
  )

  useEffect(() => {
    if (!('IntersectionObserver' in window)) return undefined
    const nodes = outline.headings
      .map((heading) => document.getElementById(heading.id))
      .filter((node): node is HTMLElement => Boolean(node))
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0]
      if (visible?.target.id) setActiveHeadingId(visible.target.id)
    }, { rootMargin: '-18% 0px -68% 0px', threshold: [0, 1] })
    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [outline.headings])

  return (
    <div className="knowledge-reader">
      <header className="knowledge-reader__hero">
        <div className="knowledge-reader__breadcrumbs">{breadcrumbNodes.map((node) => node.title).join(' / ')}</div>
        <p className="knowledge-reader__kicker">{detail.dimension} · {detail.category}</p>
        <h1>{detail.title}</h1>
        {detail.aliases.length > 0 ? <p className="knowledge-reader__aliases">亦称：{detail.aliases.join('、')}</p> : null}
        <dl className="knowledge-reader__facts">
          <div><dt>审核状态</dt><dd data-review-status={detail.reviewStatus}>{reviewStatusLabels[detail.reviewStatus]}</dd></div>
          <div><dt>来源记录</dt><dd>{detail.sources.length} 条</dd></div>
          <div><dt>显式关系</dt><dd>{detail.relations.length} 条</dd></div>
          <div><dt>内容版本</dt><dd>v{detail.contentVersion}</dd></div>
        </dl>
        {outline.excerpt ? (
          <div className="knowledge-reader__excerpt"><span>正文节选</span><p>{outline.excerpt}</p></div>
        ) : null}
      </header>

      <details className="knowledge-reader__mobile-outline">
        <summary>本文目录 <span>{outline.headings.length} 节</span></summary>
        <nav aria-label="移动端本文目录"><Outline headings={outline.headings} activeId={activeHeadingId} /></nav>
      </details>

      <div className="knowledge-reader__layout">
        <nav className="knowledge-reader__outline" aria-label="本文目录">
          <p>本文目录</p>
          <Outline headings={outline.headings} activeId={activeHeadingId} />
        </nav>
        <article className="knowledge-reader__article">
          <div className="knowledge-reader__content"><KnowledgeMarkdown content={detail.content} headings={outline.headings} /></div>

          <section className="knowledge-reader__section" aria-labelledby="knowledge-sources-title">
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

          <section className="knowledge-reader__section" aria-labelledby="knowledge-relations-title">
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
            <section className="knowledge-reader__theory" aria-labelledby="knowledge-theory-title">
              <div><p>研究入口</p><h2 id="knowledge-theory-title">{theory.title}</h2><span>{reviewStatusLabels[theory.reviewStatus]} · {theory.matchEligible ? '可用于理论匹配' : '当前不用于理论匹配'}</span></div>
              {canSeedTheory ? <button type="button" onClick={() => onStartResearch({ theoryId: theory.theoryId, theoryName: theory.title })}>以此理论开始研究 <span aria-hidden="true">↗</span></button> : null}
            </section>
          ) : null}
        </article>
      </div>
    </div>
  )
}
