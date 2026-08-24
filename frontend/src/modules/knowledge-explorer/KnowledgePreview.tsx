import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type {
  AnchorHTMLAttributes,
  ComponentType,
  CSSProperties,
  PropsWithChildren,
} from 'react'

import {
  readCurrentKnowledgeRelease,
  readKnowledgeEntry,
  readKnowledgePreview,
} from './knowledgeApi'
import type { KnowledgeEntrySummary } from './types'
import './knowledge-preview.css'

function useKnowledgeHomePreview() {
  return useQuery({
    queryKey: ['knowledge', 'home-preview'],
    queryFn: async () => {
      const release = await readCurrentKnowledgeRelease()
      const entries = await readKnowledgePreview(release.knowledgeReleaseId)
      return { releaseId: release.knowledgeReleaseId, entries }
    },
    retry: false,
  })
}

type LinkAdapterProps = PropsWithChildren<Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & {
  href: string
}>

function AnchorLink({ children, ...props }: LinkAdapterProps) {
  return <a {...props}>{children}</a>
}

function knowledgeExcerpt(content: string, title: string, limit = 148) {
  const plainText = content
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .split('\n')
    .map((line) => line.replace(/^[#>\s-]+/, '').replace(/[*`_]/g, '').trim())
    .filter((line) => line && line !== title && !/^文献[：:]/.test(line))
    .join(' ')
    .replace(/\s+/g, ' ')
  if (!plainText) return '进入知识库查看这条概念的完整解释、来源与关系。'
  return plainText.length > limit ? `${plainText.slice(0, limit)}…` : plainText
}

export function KnowledgePreview({
  LinkComponent = AnchorLink,
}: {
  LinkComponent?: ComponentType<LinkAdapterProps>
}) {
  const preview = useKnowledgeHomePreview()
  const journeyRef = useRef<HTMLDivElement>(null)
  const journeyTrackRef = useRef<HTMLDivElement>(null)
  const releaseTimerRef = useRef<number | null>(null)
  const [activeCardIndex, setActiveCardIndex] = useState<number | null>(null)
  const [frontCardIndex, setFrontCardIndex] = useState<number | null>(null)
  const showcase = useQuery({
    queryKey: ['knowledge', 'home-showcase', preview.data?.releaseId],
    queryFn: async () => {
      if (!preview.data) throw new Error('知识目录尚未载入')
      return Promise.all(
        preview.data.entries.slice(0, 10).map((entry) => readKnowledgeEntry({
          knowledgeId: entry.knowledgeId,
          releaseId: preview.data.releaseId,
        })),
      )
    },
    enabled: Boolean(preview.data),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  function bringCardForward(index: number) {
    if (releaseTimerRef.current !== null) window.clearTimeout(releaseTimerRef.current)
    releaseTimerRef.current = null
    setActiveCardIndex(index)
    setFrontCardIndex(index)
  }

  function releaseCard(index: number) {
    setActiveCardIndex((current) => current === index ? null : current)
    if (releaseTimerRef.current !== null) window.clearTimeout(releaseTimerRef.current)
    releaseTimerRef.current = window.setTimeout(() => {
      setFrontCardIndex((current) => current === index ? null : current)
      releaseTimerRef.current = null
    }, 440)
  }

  useEffect(() => () => {
    if (releaseTimerRef.current !== null) window.clearTimeout(releaseTimerRef.current)
  }, [])

  useEffect(() => {
    const journey = journeyRef.current
    const track = journeyTrackRef.current
    if (!journey || !track || showcase.data?.length === 0) return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return

    let frame = 0
    function paintJourney() {
      frame = 0
      const rect = journey!.getBoundingClientRect()
      const startAt = window.innerHeight * 1.35
      const endAt = -journey!.offsetHeight * 0.45
      const progress = Math.min(1, Math.max(0, (startAt - rect.top) / (startAt - endAt)))
      const eased = progress * progress * (3 - 2 * progress)
      const cards = Array.from(track!.querySelectorAll<HTMLElement>('.knowledge-journey__card'))
      const width = journey!.clientWidth
      const height = journey!.clientHeight
      const cardWidth = cards[0]?.offsetWidth ?? 340
      const cardHeight = cards[0]?.offsetHeight ?? 240
      const cardCount = Math.max(1, cards.length)
      const minimumSpread = width < 680 ? 42 : 118
      const maximumSpread = width < 680 ? 68 : 230
      const spread = cardCount <= 1
        ? 0
        : Math.max(
            minimumSpread,
            Math.min(maximumSpread, (width + cardWidth * 0.36) / (cardCount - 1)),
          )
      const closedX = -cardWidth * 0.34
      const closedY = height - cardHeight * 0.58

      cards.forEach((card, index) => {
        const normalized = cards.length <= 1 ? 0 : index / (cards.length - 1)
        const delay = normalized * 0.32
        const cardProgress = Math.min(1, Math.max(0, (eased - delay) / (1 - delay)))
        const opened = 1 - (1 - cardProgress) ** 3
        const targetX = closedX + index * spread
        const curvedRise = normalized ** 0.72
        const targetY = height * (
          0.7
          - curvedRise * 0.54
          + Math.sin(normalized * Math.PI) * 0.045
        )
        const targetRotation = -10 + normalized * 16
        const closedRotation = -12 + index * 0.08
        const x = closedX + (targetX - closedX) * opened
        const y = closedY + (targetY - closedY) * opened
        const rotation = closedRotation + (targetRotation - closedRotation) * opened
        const scale = 0.96 + opened * 0.04

        card.style.setProperty('--path-x', `${x}px`)
        card.style.setProperty('--path-y', `${y}px`)
        card.style.setProperty('--path-r', `${rotation}deg`)
        card.style.setProperty('--path-counter-r', `${-rotation}deg`)
        card.style.setProperty('--path-scale', `${scale}`)
        card.style.setProperty('--path-opacity', '1')
        card.style.zIndex = `${10 + index}`
        card.style.pointerEvents = index === cards.length - 1 || opened > 0.12 ? 'auto' : 'none'
      })
    }
    function schedulePaint() {
      if (frame) return
      frame = window.requestAnimationFrame(paintJourney)
    }

    paintJourney()
    window.addEventListener('scroll', schedulePaint, { passive: true })
    window.addEventListener('resize', schedulePaint)
    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? undefined
      : new ResizeObserver(schedulePaint)
    resizeObserver?.observe(journey)
    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      resizeObserver?.disconnect()
      window.removeEventListener('scroll', schedulePaint)
      window.removeEventListener('resize', schedulePaint)
    }
  }, [showcase.data?.length])

  if (preview.isPending) {
    return (
      <div className="knowledge-preview knowledge-preview--loading" role="status">
        <span />
        <span />
        <span />
        <p>正在读取知识内容</p>
      </div>
    )
  }

  if (preview.isError) {
    return (
      <div className="knowledge-preview knowledge-preview--error" role="alert">
        <h3>暂时无法读取知识内容</h3>
        <p>介绍页仍可使用，你也可以直接进入知识库后再试。</p>
        <div>
          <button
            type="button"
            disabled={preview.isFetching}
            onClick={() => preview.refetch()}
          >
            {preview.isFetching ? '正在重新加载' : '重新加载知识'}
          </button>
          <LinkComponent href="/knowledge">直接进入知识库</LinkComponent>
        </div>
      </div>
    )
  }

  if (showcase.isPending) {
    return (
      <div className="knowledge-preview knowledge-preview--loading" role="status">
        <span />
        <span />
        <span />
        <p>正在读取知识解释</p>
      </div>
    )
  }

  if (showcase.isError) {
    return (
      <div className="knowledge-preview knowledge-preview--error" role="alert">
        <h3>暂时无法读取知识解释</h3>
        <p>知识目录仍然可用，你可以直接进入知识库查看完整条目。</p>
        <div>
          <button type="button" onClick={() => showcase.refetch()}>重新加载解释</button>
          <LinkComponent href="/knowledge">直接进入知识库</LinkComponent>
        </div>
      </div>
    )
  }

  const showcaseEntries = showcase.data ?? []

  return (
    <div className="knowledge-preview knowledge-preview--journey" ref={journeyRef}>
      <div className="knowledge-journey__stage">
        <div className="knowledge-journey__meta">
          <span>{showcaseEntries.length} 条真实知识解释</span>
          <p>继续向下，展开知识牌组</p>
        </div>
        <div className="knowledge-journey__track" ref={journeyTrackRef}>
          {showcaseEntries.map((entry, index) => (
            <LinkComponent
              key={`${entry.knowledgeId}:${entry.contentVersion}`}
              className={[
                'knowledge-journey__card',
                activeCardIndex === index ? 'is-active' : '',
                frontCardIndex === index ? 'is-foreground' : '',
                activeCardIndex !== null && activeCardIndex !== index ? 'is-receding' : '',
              ].filter(Boolean).join(' ')}
              href={`/knowledge/${encodeURIComponent(entry.knowledgeId)}?knowledge_release_id=${encodeURIComponent(preview.data.releaseId)}`}
              style={{ '--knowledge-card-order': index } as CSSProperties}
              onPointerEnter={() => bringCardForward(index)}
              onPointerLeave={() => releaseCard(index)}
              onFocus={() => bringCardForward(index)}
              onBlur={() => releaseCard(index)}
            >
              <div className="knowledge-journey__card-surface">
                <span className="knowledge-journey__card-head">
                  <b>知识条目</b>
                  <em>{String(index + 1).padStart(2, '0')}</em>
                </span>
                <h3>{entry.title}</h3>
                <p>{knowledgeExcerpt(entry.content, entry.title, 112)}</p>
                <span className="knowledge-journey__card-foot">
                  <span>{entry.dimension} / {entry.category}</span>
                  <i aria-hidden="true">↗</i>
                </span>
              </div>
            </LinkComponent>
          ))}
        </div>
      </div>
    </div>
  )
}

export function KnowledgeTicker({
  LinkComponent = AnchorLink,
}: {
  LinkComponent?: ComponentType<LinkAdapterProps>
}) {
  const preview = useKnowledgeHomePreview()
  const tickerRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const closeTimerRef = useRef<number | undefined>(undefined)
  const [activeEntry, setActiveEntry] = useState<{
    anchorKey: string
    entry: KnowledgeEntrySummary
    left: number
  } | null>(null)

  const detail = useQuery({
    queryKey: [
      'knowledge',
      'ticker-detail',
      preview.data?.releaseId,
      activeEntry?.entry.knowledgeId,
    ],
    queryFn: () => {
      if (!preview.data || !activeEntry) throw new Error('未选择知识条目')
      return readKnowledgeEntry({
        knowledgeId: activeEntry.entry.knowledgeId,
        releaseId: preview.data.releaseId,
      })
    },
    enabled: Boolean(preview.data && activeEntry),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  function cancelClose() {
    if (closeTimerRef.current !== undefined) {
      window.clearTimeout(closeTimerRef.current)
      closeTimerRef.current = undefined
    }
  }

  function scheduleClose() {
    cancelClose()
    closeTimerRef.current = window.setTimeout(() => setActiveEntry(null), 130)
  }

  function showEntry(entry: KnowledgeEntrySummary, anchorKey: string, anchor: HTMLElement) {
    cancelClose()
    const ticker = tickerRef.current
    if (!ticker) return
    const tickerRect = ticker.getBoundingClientRect()
    const anchorRect = anchor.getBoundingClientRect()
    const cardWidth = Math.min(360, tickerRect.width - 32)
    const centeredLeft = anchorRect.left - tickerRect.left + anchorRect.width / 2 - cardWidth / 2
    const left = Math.min(
      Math.max(centeredLeft, 16),
      Math.max(16, tickerRect.width - cardWidth - 16),
    )
    setActiveEntry({ anchorKey, entry, left })
  }

  useEffect(() => {
    const track = trackRef.current
    if (!track || preview.data?.entries.length === 0) return

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    let lastScrollY = window.scrollY
    let travel = 0

    function followPageScroll() {
      const currentScrollY = window.scrollY
      const delta = currentScrollY - lastScrollY
      lastScrollY = currentScrollY
      if (reduceMotion || delta === 0) return

      setActiveEntry(null)

      const loopWidth = track.scrollWidth / 2
      if (loopWidth <= 0) return

      travel = (travel + delta * 3.2) % loopWidth
      if (travel < 0) travel += loopWidth
      track.style.transform = `translate3d(${-travel}px, 0, 0)`
    }

    window.addEventListener('scroll', followPageScroll, { passive: true })
    return () => window.removeEventListener('scroll', followPageScroll)
  }, [preview.data?.entries.length])

  useEffect(() => () => cancelClose(), [])

  if (preview.isPending) {
    return <div className="knowledge-ticker knowledge-ticker--loading" role="status">正在展开知识索引</div>
  }
  if (preview.isError || preview.data.entries.length === 0) return null

  const titles = preview.data.entries.map((entry) => entry.title)
  const activeHref = activeEntry
    ? `/knowledge/${encodeURIComponent(activeEntry.entry.knowledgeId)}?knowledge_release_id=${encodeURIComponent(preview.data.releaseId)}`
    : ''
  const cardStyle = activeEntry
    ? { '--knowledge-card-left': `${activeEntry.left}px` } as CSSProperties
    : undefined

  function explanation() {
    if (detail.isPending) return '正在从知识库读取解释…'
    if (detail.isError || !detail.data) return '解释暂时未载入，可以进入知识库查看完整条目。'
    return knowledgeExcerpt(detail.data.content, detail.data.title)
  }

  return (
    <div
      className="knowledge-ticker"
      role="region"
      aria-label={`知识索引流：${titles.join('、')}`}
      ref={tickerRef}
    >
      <div className="knowledge-ticker__viewport">
        <div className="knowledge-ticker__track" ref={trackRef}>
          {[0, 1].map((group) => (
            <div className="knowledge-ticker__group" key={group}>
              {preview.data.entries.map((entry, index) => {
                const anchorKey = `${group}:${entry.knowledgeId}`
                const href = `/knowledge/${encodeURIComponent(entry.knowledgeId)}?knowledge_release_id=${encodeURIComponent(preview.data.releaseId)}`
                return (
                  <LinkComponent
                    className={`knowledge-ticker__term knowledge-ticker__term--${index % 4}`}
                    href={href}
                    key={anchorKey}
                    aria-controls={activeEntry?.anchorKey === anchorKey ? 'knowledge-ticker-card' : undefined}
                    aria-expanded={activeEntry?.anchorKey === anchorKey}
                    onPointerEnter={(event) => showEntry(entry, anchorKey, event.currentTarget)}
                    onPointerLeave={scheduleClose}
                    onFocus={(event) => showEntry(entry, anchorKey, event.currentTarget)}
                    onBlur={scheduleClose}
                  >
                    {entry.title}<i aria-hidden="true" />
                  </LinkComponent>
                )
              })}
            </div>
          ))}
        </div>
      </div>
      {activeEntry ? (
        <aside
          className="knowledge-ticker__card"
          id="knowledge-ticker-card"
          style={cardStyle}
          aria-label={`${activeEntry.entry.title}知识解释`}
          onPointerEnter={cancelClose}
          onPointerLeave={scheduleClose}
          onFocus={cancelClose}
          onBlur={scheduleClose}
        >
          <span className="knowledge-ticker__card-kicker">
            知识库条目
          </span>
          <h3>{activeEntry.entry.title}</h3>
          <p className="knowledge-ticker__card-path">
            {activeEntry.entry.dimension} / {activeEntry.entry.category}
          </p>
          <p className="knowledge-ticker__card-copy">{explanation()}</p>
          <LinkComponent className="knowledge-ticker__card-link" href={activeHref}>
            查看完整解释 <span aria-hidden="true">↗</span>
          </LinkComponent>
        </aside>
      ) : null}
    </div>
  )
}
