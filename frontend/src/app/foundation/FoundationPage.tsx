import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { KnowledgePreview, KnowledgeTicker } from '../../modules/knowledge-explorer'
import { KnowledgeGraphPreview } from '../../modules/knowledge-graph'
import brandMark from '../../assets/qunxue-brand-mark.svg'
import { RouterLinkAdapter } from '../ui/RouterLinkAdapter'
import { FoundationAgentReveal } from './FoundationAgentReveal'
import { FoundationLightPaperShader } from './FoundationLightPaperShader'
import { FoundationModelDemo, FoundationQuestionFlow } from './FoundationModelDemo'
import './foundation.css'

const researchOrigins = [
  '真实困惑',
  '未完成的研究',
  '已有理论框架',
]

function ResearchOriginLine() {
  const [originIndex, setOriginIndex] = useState(0)
  const [visibleLength, setVisibleLength] = useState(0)
  const [phase, setPhase] = useState<'typing' | 'holding' | 'deleting'>('typing')
  const origin = researchOrigins[originIndex] ?? researchOrigins[0]

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVisibleLength(Array.from(origin).length)
      setPhase('holding')
      return
    }

    const characterCount = Array.from(origin).length
    let delay = 82
    if (phase === 'typing' && visibleLength >= characterCount) delay = 1450
    if (phase === 'holding') delay = 360
    if (phase === 'deleting') delay = visibleLength > 0 ? 46 : 240

    const timer = window.setTimeout(() => {
      if (phase === 'typing' && visibleLength < characterCount) {
        setVisibleLength((length) => length + 1)
        return
      }
      if (phase === 'typing') {
        setPhase('holding')
        return
      }
      if (phase === 'holding') {
        setPhase('deleting')
        return
      }
      if (visibleLength > 0) {
        setVisibleLength((length) => length - 1)
        return
      }
      setOriginIndex((index) => (index + 1) % researchOrigins.length)
      setPhase('typing')
    }, delay)

    return () => window.clearTimeout(timer)
  }, [origin, phase, visibleLength])

  const visibleOrigin = Array.from(origin).slice(0, visibleLength)
  return (
    <span className="foundation-origin" data-phase={phase} aria-hidden="true">
      <span className="foundation-origin__word">
        {visibleOrigin.length > 0 ? visibleOrigin.map((character, index) => (
          <span
            className="foundation-origin__glyph"
            key={`${originIndex}:${index}`}
            style={{ animationDelay: `${index * 24}ms` }}
          >
            {character}
          </span>
        )) : '\u00A0'}
      </span>
      <i />
    </span>
  )
}

function ClosingStatement() {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [visible, setVisible] = useState(false)
  const lines = ['先比较解释，', '再形成自己的研究判断。']

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const heading = headingRef.current
    if (!heading) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setVisible(true)
        observer.disconnect()
      },
      { threshold: 0.42 },
    )
    observer.observe(heading)
    return () => observer.disconnect()
  }, [])

  let characterIndex = 0
  return (
    <h2
      id="closing-title"
      className={`foundation-closing__statement${visible ? ' is-visible' : ''}`}
      aria-label={lines.join('')}
      ref={headingRef}
    >
      {lines.map((line) => (
        <span className="foundation-closing__line" aria-hidden="true" key={line}>
          {Array.from(line).map((character) => {
            const delay = characterIndex * 52
            characterIndex += 1
            return (
              <span
                className="foundation-closing__glyph"
                key={`${line}:${characterIndex}`}
                style={{ animationDelay: `${delay}ms` }}
              >
                {character}
              </span>
            )
          })}
        </span>
      ))}
      <i className="foundation-closing__caret" aria-hidden="true" />
    </h2>
  )
}

function ClosingSignature() {
  const signatureRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }

    const signature = signatureRef.current
    if (!signature) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setVisible(true)
        observer.disconnect()
      },
      { threshold: 0.32 },
    )

    observer.observe(signature)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      className={`foundation-closing__signature${visible ? ' is-visible' : ''}`}
      ref={signatureRef}
    >
      <div className="foundation-closing__signature-words" aria-hidden="true">
        <span className="foundation-closing__signature-word foundation-closing__signature-word--observe">观察</span>
        <span className="foundation-closing__signature-word foundation-closing__signature-word--compare">比较</span>
        <span className="foundation-closing__signature-word foundation-closing__signature-word--judge">判断</span>
      </div>
      <p>最终判断由研究者完成。</p>
    </div>
  )
}

function DeferredGraphPreview() {
  const navigate = useNavigate()
  const boundaryRef = useRef<HTMLDivElement>(null)
  const [ready, setReady] = useState(false)
  const [nearby, setNearby] = useState(true)
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const boundary = boundaryRef.current
    if (!boundary) return
    const observer = new IntersectionObserver(
      ([entry]) => setNearby(entry?.isIntersecting ?? false),
      { rootMargin: '480px 0px', threshold: 0.01 },
    )
    observer.observe(boundary)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setReady(true)
      return
    }
    const boundary = boundaryRef.current
    if (!boundary) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setReady(true)
        observer.disconnect()
      },
      { rootMargin: '320px 0px' },
    )
    observer.observe(boundary)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setRevealed(true)
      return
    }
    const boundary = boundaryRef.current
    if (!boundary) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setRevealed(true)
        observer.disconnect()
      },
      { threshold: 0.16 },
    )
    observer.observe(boundary)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      className={`foundation-graph__preview${revealed ? ' is-visible' : ''}`}
      ref={boundaryRef}
    >
      {ready && nearby ? (
        <KnowledgeGraphPreview
          onSelectKnowledge={(knowledgeId) => {
            navigate(`/knowledge/${encodeURIComponent(knowledgeId)}`)
          }}
        />
      ) : (
        <div className="foundation-graph__placeholder" role="status">
          图谱预览将在接近视口时加载
        </div>
      )}
    </div>
  )
}

function FoundationDarkFieldController() {
  useEffect(() => {
    let frame = 0
    let darkFieldFixed = false
    let lightFieldFixed = false
    let lastPaperEdge = Number.NaN
    let transitionStart = window.innerHeight
    const page = document.querySelector('.public-site')
    const method = document.querySelector<HTMLElement>('#method')
    const knowledge = document.querySelector<HTMLElement>('#knowledge-preview')
    const paperField = document.querySelector<HTMLElement>('.foundation-knowledge__paper-field')

    const updateGeometry = () => {
      transitionStart = knowledge
        ? knowledge.getBoundingClientRect().top + window.scrollY
        : (method?.getBoundingClientRect().bottom ?? window.innerHeight) + window.scrollY
    }

    const update = () => {
      frame = 0
      const paperEdge = Math.round(Math.max(-340, Math.min(
        window.innerHeight + 340,
        transitionStart - window.scrollY,
      )))
      if (paperEdge !== lastPaperEdge) {
        lastPaperEdge = paperEdge
        paperField?.style.setProperty('--foundation-paper-edge', `${paperEdge}px`)
      }

      const nextDarkFixed = window.scrollY >= window.innerHeight * 0.62
        && window.scrollY < transitionStart + 340
      if (nextDarkFixed !== darkFieldFixed) {
        darkFieldFixed = nextDarkFixed
        page?.classList.toggle('is-dark-backdrop-active', nextDarkFixed)
      }

      const nextLightFixed = window.scrollY >= transitionStart + 340
      if (nextLightFixed !== lightFieldFixed) {
        lightFieldFixed = nextLightFixed
        page?.classList.toggle('is-light-backdrop-active', nextLightFixed)
      }
    }
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }
    const onResize = () => {
      updateGeometry()
      schedule()
    }

    updateGeometry()
    update()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', onResize)
      page?.classList.remove('is-dark-backdrop-active')
      page?.classList.remove('is-light-backdrop-active')
      paperField?.style.removeProperty('--foundation-paper-edge')
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  return null
}

export function FoundationPage({ authenticated = false }: { authenticated?: boolean }) {
  const methodStepsRef = useRef<HTMLOListElement>(null)
  const [methodStepsVisible, setMethodStepsVisible] = useState(false)

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setMethodStepsVisible(true)
      return
    }
    if (typeof IntersectionObserver === 'undefined') {
      setMethodStepsVisible(true)
      return
    }

    const steps = methodStepsRef.current
    if (!steps) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setMethodStepsVisible(true)
        observer.disconnect()
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.22 },
    )
    observer.observe(steps)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="public-site">
      <FoundationDarkFieldController />
      <header className="public-header">
        <div className="public-header__inner">
          <Link className="public-wordmark" to="/welcome" aria-label="群学致知介绍页">
            <img src={brandMark} alt="" />
            <span>
              <strong>群学致知</strong>
              <small>COLLECTIVE INQUIRY</small>
            </span>
          </Link>
          <nav className="public-navigation" aria-label="介绍页导航">
            <a href="#method">研究方法</a>
            <Link to="/knowledge">知识库</Link>
            {authenticated ? (
              <Link className="public-navigation__account" to="/my">我的研究</Link>
            ) : (
              <Link className="public-navigation__account" to="/login">登录</Link>
            )}
          </nav>
        </div>
      </header>

      <main>
        <section className="foundation-hero" aria-labelledby="foundation-title">
          <div className="foundation-hero__inner">
            <div className="foundation-hero__copy">
              <p className="foundation-kicker"><span>01</span> 社会学理论发现与研究设计</p>
              <h1
                id="foundation-title"
                aria-label="从真实困惑、未完成的研究或已有理论框架，找到可研究的问题。"
              >
                <span className="foundation-origin-prefix" aria-hidden="true">从</span>
                <ResearchOriginLine />
                <span className="foundation-origin-suffix" aria-hidden="true">，</span><br />
                <span className="foundation-outcome" aria-hidden="true">
                  找到<span>可研究的<br className="foundation-mobile-break" />问题。</span>
                </span>
              </h1>
              <p className="foundation-hero__lede">
                群学致知帮助初次独立研究的学生梳理现象、比较理论与追踪证据。系统展开选择，研究判断仍然属于你。
              </p>
              <div className="foundation-hero__actions">
                {authenticated ? (
                  <Link className="public-action public-action--primary" to="/app">进入工作台</Link>
                ) : (
                  <a className="public-action public-action--primary" href="#research-agent">体验研究流程</a>
                )}
                {authenticated ? (
                  <Link className="public-action public-action--text" to="/knowledge">浏览知识库</Link>
                ) : (
                  <Link className="public-action public-action--text" to="/register">创建研究档案</Link>
                )}
              </div>
            </div>

            <div className="foundation-hero__demo" id="research-agent">
              <FoundationAgentReveal />
            </div>
          </div>
          <a className="foundation-hero__scroll" href="#method">
            <span aria-hidden="true" />
            向下了解方法
          </a>
        </section>

        <section className="foundation-method" id="method" aria-labelledby="method-title" data-reveal>
          <div className="foundation-section-heading foundation-section-heading--split">
            <div>
              <h2 id="method-title">把模糊的“为什么”，拆成可以核对的研究路径。</h2>
              <p>每一步都留下你的确认。系统提供候选、差异与证据线索，但不会替你选定理论或写下结论。</p>
            </div>
          </div>
          <ol
            className={`foundation-method__steps${methodStepsVisible ? ' is-visible' : ''}`}
            data-sequence-ready="true"
            ref={methodStepsRef}
          >
            <li>
              <span>01</span>
              <h3>确认现象</h3>
              <p>从材料中提炼候选描述，由你修改并确认真正想研究的现象。</p>
            </li>
            <li>
              <span>02</span>
              <h3>比较解释</h3>
              <p>并置理论的解释重点、适用前提与盲区，不把相似度当答案。</p>
            </li>
            <li>
              <span>03</span>
              <h3>形成框架</h3>
              <p>把选择转成可继续验证的问题、概念关系和材料计划。</p>
            </li>
          </ol>
        </section>

        <section className="foundation-knowledge" id="knowledge-preview" aria-labelledby="knowledge-preview-title" data-reveal>
          <FoundationLightPaperShader />
          <KnowledgeTicker LinkComponent={RouterLinkAdapter} />
          <div className="foundation-section-heading">
            <p className="foundation-kicker"><span>03</span> 真实理论知识</p>
            <h2 id="knowledge-preview-title">先理解一个理论，<br />再决定是否用它解释现象。</h2>
            <p>这里直接读取当前知识内容。待核验条目会如实标记，收录不等于已经审核。</p>
          </div>
          <KnowledgePreview LinkComponent={RouterLinkAdapter} />
          <Link className="foundation-text-link" to="/knowledge">继续浏览知识库 <span aria-hidden="true">↗</span></Link>
        </section>

        <section className="foundation-graph" aria-labelledby="graph-preview-title" data-reveal>
          <div className="foundation-graph__composition">
            <DeferredGraphPreview />
            <div className="foundation-graph__copy">
              <p className="foundation-kicker"><span>04</span> 知识之间的路径</p>
              <div>
                <h2 id="graph-preview-title">让理论的位置和关系，成为一张可探索的地图。</h2>
                <div className="foundation-graph__details">
                  <p>预览使用真实知识目录。正式关系与待审核发现分开呈现，不把相邻位置误写成理论关系。</p>
                  <Link className="public-action public-action--text" to="/knowledge/graph">进入完整图谱</Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="foundation-trust" aria-labelledby="trust-title" data-reveal>
          <FoundationQuestionFlow />
          <div className="foundation-trust__inner">
            <header>
              <p className="foundation-kicker"><span>05</span> 学科垂直模型</p>
              <h2 id="trust-title">让模型展开问题，<br />把判断留给研究者。</h2>
              <p className="foundation-trust__lede">
                面向社会科学研究的对话界面。它先追问对象、范围与证据，再展开可以比较的理论解释。
              </p>
              <ul className="foundation-trust__capabilities" aria-label="模型参与边界">
                <li>识别研究现象</li>
                <li>比较理论解释</li>
                <li>追问证据边界</li>
              </ul>
            </header>
            <FoundationModelDemo />
          </div>
        </section>

        <section className="foundation-closing" aria-labelledby="closing-title" data-reveal>
          <div className="foundation-closing__inner">
            <div className="foundation-closing__copy">
              <p className="foundation-kicker"><span>06</span> 从你的问题开始</p>
              <ClosingStatement />
              <p className="foundation-closing__lede">
                从一个具体观察开始，保留每一次理论选择与证据判断。
              </p>
              <div className="foundation-closing__actions">
                {authenticated ? (
                  <Link className="public-action public-action--primary" to="/research/new">开始一项新研究</Link>
                ) : (
                  <Link className="public-action public-action--primary" to="/register">创建账号并开始研究</Link>
                )}
                <span>无需预设答案</span>
              </div>
            </div>
            <ClosingSignature />
          </div>
        </section>
      </main>

      <footer className="public-footer">
        <Link className="public-wordmark public-wordmark--footer" to="/welcome">
          <img src={brandMark} alt="" />
          <span><strong>群学致知</strong><small>COLLECTIVE INQUIRY</small></span>
        </Link>
        <p>为初次独立研究，保留判断的位置。</p>
        <div>
          <Link to="/knowledge">知识库</Link>
          <Link to="/login">登录</Link>
        </div>
      </footer>
    </div>
  )
}
