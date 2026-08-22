import { ArrowUp } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router'

import { FoundationAgentShader } from './FoundationAgentShader'

const researchQuestions = [
  '为什么同一课堂里有人总是沉默？',
  '为什么短视频越刷越难停下来？',
  '为什么年轻人越来越害怕求助？',
  '为什么同一种规则对不同人效果不同？',
  '为什么社区里的熟人关系正在变淡？',
  '为什么加班会被理解成敬业？',
  '为什么算法推荐会让观点越来越相似？',
  '为什么毕业后同学之间的差距迅速扩大？',
  '为什么人们明知焦虑仍持续比较？',
  '为什么公共空间里陌生人很少交谈？',
  '为什么家庭期待会影响职业选择？',
  '为什么网络争论很快变成身份对立？',
  '为什么一些传统在城市里重新流行？',
  '为什么照护劳动常常被忽视？',
  '为什么同伴评价会改变自我判断？',
  '为什么组织中的规则总有例外？',
  '为什么搬到大城市后反而更孤独？',
  '为什么某些知识更容易被相信？',
  '为什么人们会为不公平寻找合理解释？',
  '为什么技术进步没有减少所有人的负担？',
] as const

type CopyPhase = 'entering' | 'resting' | 'exiting'

const COPY_ENTER_DURATION_MS = 960
const COPY_EXIT_DURATION_MS = 460
const COPY_CYCLE_MS = 4_200

function glyphStyle(index: number, count: number) {
  return {
    '--foundation-glyph-index': index,
    '--foundation-glyph-reverse-index': count - index - 1,
    '--foundation-glyph-drift-x': `${((index * 17) % 15) - 7}px`,
    '--foundation-glyph-drift-y': `${10 + ((index * 11) % 14)}px`,
    '--foundation-glyph-rotate': `${((index * 13) % 9) - 4}deg`,
  } as CSSProperties
}

function ResearchQuestionField({ active }: { active: boolean }) {
  const [questionIndex, setQuestionIndex] = useState(0)
  const [copyPhase, setCopyPhase] = useState<CopyPhase>('entering')
  const [value, setValue] = useState('')
  const [scrollOffset, setScrollOffset] = useState(0)

  useEffect(() => {
    if (!active) {
      setCopyPhase('resting')
      return
    }

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    if (reduceMotion) {
      setCopyPhase('resting')
      return
    }

    if (value) {
      setCopyPhase('entering')
      const inputTimer = window.setTimeout(
        () => setCopyPhase('resting'),
        COPY_ENTER_DURATION_MS,
      )
      return () => window.clearTimeout(inputTimer)
    }

    setCopyPhase('entering')
    const restTimer = window.setTimeout(
      () => setCopyPhase('resting'),
      COPY_ENTER_DURATION_MS,
    )
    const exitTimer = window.setTimeout(
      () => setCopyPhase('exiting'),
      COPY_CYCLE_MS - COPY_EXIT_DURATION_MS,
    )
    const swapTimer = window.setTimeout(() => {
      setQuestionIndex((index) => (index + 1) % researchQuestions.length)
      setCopyPhase('entering')
    }, COPY_CYCLE_MS)

    return () => {
      window.clearTimeout(restTimer)
      window.clearTimeout(exitTimer)
      window.clearTimeout(swapTimer)
    }
  }, [active, questionIndex, value])

  const copy = value || researchQuestions[questionIndex]
  const characters = Array.from(copy)
  const copyMode = value ? 'input' : 'questions'

  return (
    <span className="foundation-agent__copy">
      <span className="foundation-agent__question-field" data-copy-mode={copyMode}>
        <input
          aria-label="输入你的研究困惑"
          autoComplete="off"
          maxLength={80}
          onChange={(event) => {
            const nextValue = event.currentTarget.value
            setValue(nextValue)
            setScrollOffset(nextValue ? event.currentTarget.scrollLeft : 0)
          }}
          onScroll={(event) => setScrollOffset(event.currentTarget.scrollLeft)}
          spellCheck={false}
          value={value}
        />
        <strong
          aria-hidden="true"
          data-copy-mode={copyMode}
          data-copy-phase={copyPhase}
          data-research-question
          style={copyMode === 'input'
            ? { transform: `translate3d(${-scrollOffset}px, 0, 0)` }
            : undefined}
        >
          {characters.map((character, index) => (
            <span
              className="foundation-agent__glyph"
              key={`${copyMode}:${questionIndex}:${index}:${character}`}
              style={glyphStyle(index, characters.length)}
            >
              {character === ' ' ? '\u00a0' : character}
            </span>
          ))}
        </strong>
      </span>
    </span>
  )
}

export function FoundationAgentReveal() {
  const rootRef = useRef<HTMLElement>(null)
  const [effectsActive, setEffectsActive] = useState(true)
  const [pageBackdropActive, setPageBackdropActive] = useState(false)

  useEffect(() => {
    const page = rootRef.current?.closest('.public-site')
    if (!page || typeof MutationObserver === 'undefined') return
    const update = () => setPageBackdropActive(page.classList.contains('is-dark-backdrop-active'))
    update()
    const observer = new MutationObserver(update)
    observer.observe(page, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const root = rootRef.current
    if (!root || typeof IntersectionObserver === 'undefined') return

    const observer = new IntersectionObserver(
      ([entry]) => setEffectsActive(entry?.isIntersecting ?? false),
      { rootMargin: '320px 0px', threshold: 0.01 },
    )
    observer.observe(root)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return

    let frame = 0
    let lastProgress = -1
    let scrolling = false
    let expanded = false
    let headerInverted = false
    let agentDocumentTop = 0
    let darkCoverDocumentBottom = 0
    const page = root.closest('.public-site')

    const updateGeometry = () => {
      const parentWidth = root.parentElement?.getBoundingClientRect().width ?? window.innerWidth
      const inlineInset = Math.max(0, (window.innerWidth - parentWidth) / 2)
      agentDocumentTop = root.getBoundingClientRect().top + window.scrollY
      const method = page?.querySelector<HTMLElement>('#method')
      darkCoverDocumentBottom = method
        ? method.getBoundingClientRect().bottom + window.scrollY
        : agentDocumentTop + window.innerHeight
      root.style.setProperty('--agent-inline-inset', `${inlineInset.toFixed(2)}px`)
    }

    const updateProgress = () => {
      frame = 0
      const distance = Math.max(window.innerHeight * 0.72, 1)
      const progress = Math.min(1, Math.max(0, window.scrollY / distance))
      if (Math.abs(progress - lastProgress) > 0.0001) {
        root.style.setProperty('--agent-progress', progress.toFixed(4))
        lastProgress = progress
      }

      const nextScrolling = progress > 0.02
      const nextExpanded = progress >= 0.98
      if (nextScrolling !== scrolling) {
        page?.classList.toggle('is-agent-scrolling', nextScrolling)
        scrolling = nextScrolling
      }
      if (nextExpanded !== expanded) {
        page?.classList.toggle('is-agent-expanded', nextExpanded)
        expanded = nextExpanded
      }
      const nextHeaderInverted = nextExpanded
        && window.scrollY + 84 < darkCoverDocumentBottom
      if (nextHeaderInverted !== headerInverted) {
        page?.classList.toggle('is-agent-header-inverted', nextHeaderInverted)
        headerInverted = nextHeaderInverted
      }
    }
    const onScroll = () => {
      if (frame) return
      frame = window.requestAnimationFrame(updateProgress)
    }
    const onResize = () => {
      updateGeometry()
      onScroll()
    }

    updateGeometry()
    updateProgress()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onResize)
      page?.classList.remove('is-agent-scrolling', 'is-agent-expanded', 'is-agent-header-inverted')
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <section ref={rootRef} className="foundation-agent" aria-label="群学研究 Agent 演示">
      <div className="foundation-agent__field" data-dynamic aria-hidden="true">
        {effectsActive || pageBackdropActive ? <FoundationAgentShader /> : null}
      </div>

      <article className="foundation-agent__dialog">
        <div className="foundation-agent__composer">
          <ResearchQuestionField active={effectsActive} />
          <Link to="/register" aria-label="进入研究 Agent">
            <ArrowUp weight="bold" aria-hidden="true" />
          </Link>
        </div>
      </article>
    </section>
  )
}
