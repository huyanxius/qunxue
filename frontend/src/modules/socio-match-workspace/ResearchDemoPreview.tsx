import {
  useEffect,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import './research-demo-preview.css'

type DemoStage = 'question' | 'compare' | 'framework'
type TheoryFocus = 'capital' | 'collective'
type TransitionDirection = 'forward' | 'backward'

const stageInterval = 3400

const stages: Array<{ id: DemoStage; label: string; displayLabel: string }> = [
  { id: 'question', label: '描述现象', displayLabel: '定位矛盾' },
  { id: 'compare', label: '比较候选', displayLabel: '比较机制' },
  { id: 'framework', label: '形成框架', displayLabel: '设计验证' },
]

const theoryDetails: Record<TheoryFocus, { title: string; mechanism: string; prediction: string; next: string }> = {
  capital: {
    title: '社会资本理论',
    mechanism: '关系持续时间缩短，信任与互惠期待难以积累。',
    prediction: '短住成员的互助网络更稀疏，即使正式规则相同。',
    next: '居住时长与互助网络密度是否同步变化。',
  },
  collective: {
    title: '集体行动理论',
    mechanism: '参与成本持续存在，个体收益不足时，共同利益也未必转化为行动。',
    prediction: '长住成员也会退出互助，而且退出与激励方式更相关。',
    next: '在居住时长相近时，不同激励条件是否仍导致互助差异。',
  },
}

function QuestionStage() {
  return (
    <div className="research-demo__scene research-demo__scene--question">
      <svg className="research-demo__trace" viewBox="0 0 760 330" preserveAspectRatio="none" aria-hidden="true">
        <path className="research-demo__trace-base" d="M112 164 C236 164 246 88 366 88 C494 88 510 166 650 166" />
        <path className="research-demo__trace-flow" pathLength="1" d="M112 164 C236 164 246 88 366 88 C494 88 510 166 650 166" />
      </svg>

      <aside className="research-demo__field-note">
        <span>田野记录</span>
        <blockquote>
          新成员越来越多，群里的互助请求却越来越少人回应。社区规则没有变。
        </blockquote>
        <small>合成材料，用于演示推演过程</small>
      </aside>

      <div className="research-demo__signals" aria-label="从材料中提取的观测">
        <p>系统先拆出三个观测</p>
        <ul>
          <li><span>成员更替</span><strong>持续加快</strong></li>
          <li><span>互助回应</span><strong>持续下降</strong></li>
          <li><span>正式规则</span><strong>暂未改变</strong></li>
        </ul>
      </div>

      <article className="research-demo__tension">
        <span>需要解释的矛盾</span>
        <h3>规则没有改变，互助为什么仍在减少？</h3>
        <p>不急着回答。先把时间、关系与制度拆开，保留多种可能解释。</p>
      </article>
    </div>
  )
}

function CompareStage() {
  const [focus, setFocus] = useState<TheoryFocus>('capital')
  const focusedTheory = theoryDetails[focus]

  return (
    <div className="research-demo__scene research-demo__scene--compare" data-focus={focus}>
      <p className="research-demo__note">同一组材料，两种机制给出不同预期。候选只展开分歧，选择仍由你完成。</p>

      <svg className="research-demo__trace research-demo__trace--fork" viewBox="0 0 760 330" preserveAspectRatio="none" aria-hidden="true">
        <path className="research-demo__trace-base" d="M86 165 C218 165 226 76 356 76 M86 165 C218 165 226 256 356 256 M356 76 C492 76 500 165 674 165 M356 256 C492 256 500 165 674 165" />
        <path className="research-demo__trace-flow" pathLength="1" d="M86 165 C218 165 226 76 356 76 M86 165 C218 165 226 256 356 256 M356 76 C492 76 500 165 674 165 M356 256 C492 256 500 165 674 165" />
      </svg>

      <div className="research-demo__theory-map">
        {(Object.keys(theoryDetails) as TheoryFocus[]).map((theoryId) => {
          const theory = theoryDetails[theoryId]
          const active = focus === theoryId
          return (
            <button
              className={`research-demo__theory research-demo__theory--${theoryId}`}
              key={theoryId}
              type="button"
              aria-pressed={active}
              onClick={() => setFocus(theoryId)}
              onFocus={() => setFocus(theoryId)}
              onPointerEnter={() => setFocus(theoryId)}
            >
              <span className="research-demo__theory-heading">
                <small>解释重点</small>
                <strong>{theory.title}</strong>
              </span>
              <span className="research-demo__theory-mechanism">{theory.mechanism}</span>
              <span className="research-demo__theory-prediction">
                <small>若它成立，应看到</small>
                {theory.prediction}
              </span>
            </button>
          )
        })}

        <div className="research-demo__discriminator" aria-live="polite">
          <span>理论分水岭</span>
          <strong>{focusedTheory.next}</strong>
        </div>
      </div>
    </div>
  )
}

function FrameworkStage() {
  return (
    <div className="research-demo__scene research-demo__scene--framework">
      <header className="research-demo__framework-question">
        <span>可证伪的研究问题</span>
        <h3>控制社区规则后，居住时长是否仍能解释互助网络的差异？</h3>
      </header>

      <ol className="research-demo__validation-paths">
        <li>
          <span>先比较</span>
          <strong>居住时长 × 互助网络</strong>
          <p>比较不同居住时长成员的联系密度与实际回应。</p>
        </li>
        <li>
          <span>再核对</span>
          <strong>正式规则 × 实际互惠</strong>
          <p>区分规则是否存在，与规则是否真正改变行动。</p>
        </li>
        <li>
          <span>主动寻找</span>
          <strong>能推翻解释的反例</strong>
          <p>查找长住却不互助，或短住却持续互助的成员。</p>
        </li>
      </ol>

      <p className="research-demo__boundary">系统把分歧转成可核对的材料计划，不会替你写下结论。</p>
    </div>
  )
}

const stageContent: Record<DemoStage, () => React.JSX.Element> = {
  question: QuestionStage,
  compare: CompareStage,
  framework: FrameworkStage,
}

export function ResearchDemoPreview() {
  const [stage, setStage] = useState<DemoStage>('question')
  const [previousStage, setPreviousStage] = useState<DemoStage | null>(null)
  const [transitionDirection, setTransitionDirection] = useState<TransitionDirection>('forward')
  const [playing, setPlaying] = useState(true)
  const [interactionPaused, setInteractionPaused] = useState(false)
  const stageIndex = stages.findIndex((item) => item.id === stage)

  useEffect(() => {
    const reducedMotion = typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!playing || interactionPaused || reducedMotion) return

    const timer = window.setTimeout(() => {
      setPreviousStage(stage)
      setTransitionDirection('forward')
      setStage(stages[(stageIndex + 1) % stages.length].id)
    }, stageInterval)
    return () => window.clearTimeout(timer)
  }, [interactionPaused, playing, stage, stageIndex])

  useEffect(() => {
    if (!previousStage) return
    const timer = window.setTimeout(() => setPreviousStage(null), 520)
    return () => window.clearTimeout(timer)
  }, [previousStage, stage])

  function changeStage(nextStage: DemoStage, direction: TransitionDirection) {
    if (nextStage === stage) return
    setPreviousStage(stage)
    setTransitionDirection(direction)
    setStage(nextStage)
  }

  function moveStage(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const direction = event.key === 'ArrowRight' ? 1 : -1
    const nextIndex = (stageIndex + direction + stages.length) % stages.length
    changeStage(stages[nextIndex].id, direction > 0 ? 'forward' : 'backward')
  }

  function pauseOverControls(event: ReactPointerEvent<HTMLElement>) {
    if (event.target instanceof Element && event.target.closest('button')) {
      setInteractionPaused(true)
    }
  }

  function resumeOutsideControls(event: ReactPointerEvent<HTMLElement>) {
    const nextTarget = event.relatedTarget
    if (!(nextTarget instanceof Element) || !nextTarget.closest('.research-demo button')) {
      setInteractionPaused(false)
    }
  }

  return (
    <section
      className={`research-demo${playing && !interactionPaused ? ' research-demo--playing' : ''}`}
      aria-labelledby="research-demo-title"
      onPointerOver={pauseOverControls}
      onPointerOut={resumeOutsideControls}
      onFocusCapture={() => setInteractionPaused(true)}
      onBlurCapture={() => setInteractionPaused(false)}
    >
      <header className="research-demo__header">
        <div>
          <span className="research-demo__live"><i aria-hidden="true" /> 可交互演示</span>
          <h2 id="research-demo-title">让竞争性解释产生可核对的分歧</h2>
        </div>
        <span>合成案例 / 演示推演</span>
      </header>

      <div className="research-demo__stages" role="tablist" aria-label="研究推演阶段">
        {stages.map((item, index) => (
          <button
            key={item.id}
            id={`research-demo-tab-${item.id}`}
            type="button"
            role="tab"
            aria-label={`${item.label}：${item.displayLabel}`}
            aria-selected={stage === item.id}
            aria-controls={`research-demo-panel-${item.id}`}
            tabIndex={stage === item.id ? 0 : -1}
            onKeyDown={moveStage}
            onClick={() => changeStage(
              item.id,
              index >= stageIndex ? 'forward' : 'backward',
            )}
          >
            <span>0{index + 1}</span>
            <strong>{item.displayLabel}</strong>
          </button>
        ))}
      </div>

      <div
        className="research-demo__body"
        data-direction={transitionDirection}
        aria-live={playing ? 'off' : 'polite'}
      >
        {stages.map((item) => {
          const StageContent = stageContent[item.id]
          const active = stage === item.id
          const previous = !active && previousStage === item.id
          return (
            <div
              key={item.id}
              id={`research-demo-panel-${item.id}`}
              className={`research-demo__panel${active ? ' research-demo__panel--active' : ''}${previous ? ' research-demo__panel--previous' : ''}`}
              role="tabpanel"
              aria-labelledby={`research-demo-tab-${item.id}`}
              aria-hidden={!active}
            >
              <StageContent />
            </div>
          )
        })}
      </div>

      <footer className="research-demo__footer">
        <button type="button" onClick={() => setPlaying((current) => !current)}>
          <i aria-hidden="true">{playing ? 'Ⅱ' : '▶'}</i>
          {playing ? '暂停推演' : '继续推演'}
        </button>
        <span>研究判断由你完成</span>
        <span>0{stageIndex + 1} / 03 · {stages[stageIndex].displayLabel}</span>
      </footer>
    </section>
  )
}
