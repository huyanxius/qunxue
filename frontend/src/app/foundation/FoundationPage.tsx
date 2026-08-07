import { Link } from 'react-router'

import { ContentMark, type ContentKind } from '../ui/ContentMark'
import { DegradedState, LoadingState } from '../ui/States'
import { PageContent, PageShell } from '../ui/PageShell'
import { copy } from './copy'
import './foundation.css'
import { useSystemHealth } from './useSystemHealth'

type HomeEntranceProps = {
  description: string
  eyebrow: string
  href: string
  label: string
}

const entrances: HomeEntranceProps[] = [
  {
    eyebrow: '01 / RESEARCH',
    label: '开始一项研究',
    description: '写下现象与困惑，再确认问题、比较理论。',
    href: '/research/new',
  },
  {
    eyebrow: '02 / KNOWLEDGE',
    label: '浏览知识库',
    description: '查看已经整理的理论、概念、关系与来源边界。',
    href: '/knowledge',
  },
]

const contentMarks: Array<{ kind: ContentKind; description: string }> = [
  {
    kind: 'verified',
    description: '经过审核并归入当前知识发布的内容。',
  },
  {
    kind: 'analysis',
    description: '系统生成的比较、判断与框架草稿。',
  },
  {
    kind: 'external',
    description: '尚未纳入已审核知识库的参考线索。',
  },
  {
    kind: 'user',
    description: '由你输入、编辑或确认的研究内容。',
  },
]

function HomeEntrance({ eyebrow, label, description, href }: HomeEntranceProps) {
  return (
    <Link className="home-entrance" to={href} aria-label={label}>
      <span className="home-entrance__index">{eyebrow}</span>
      <strong>{label}</strong>
      <span>{description}</span>
      <span className="home-entrance__arrow" aria-hidden="true">↗</span>
    </Link>
  )
}

export function FoundationPage() {
  const health = useSystemHealth()

  return (
    <PageShell>
      <PageContent>
        <section className="foundation-hero" aria-labelledby="foundation-title">
          <div className="foundation-hero__copy">
            <p className="eyebrow">{copy.eyebrow}</p>
            <h1 id="foundation-title">{copy.title}</h1>
            <p className="foundation-hero__lede">{copy.lede}</p>
            <p className="foundation-boundary">
              <span aria-hidden="true">→</span>
              <strong>{copy.boundary}</strong>
              <span>；不代替田野、分析与结论。</span>
            </p>
          </div>

          <aside className="foundation-hero__status" aria-label="系统状态">
            {health.isPending ? <LoadingState message="正在确认系统状态" /> : null}
            {health.isError ? (
              <DegradedState
                title="接口暂不可用"
                detail="首页内容与两个入口仍可使用。"
              />
            ) : null}
            {health.data ? (
              <div className="runtime-card" aria-live="polite">
                <div className="runtime-card__heading">
                  <span className="runtime-card__signal" aria-hidden="true" />
                  <strong>系统可用</strong>
                  {health.data.runtimeMode === 'mock' ? (
                    <span className="demo-badge">演示数据</span>
                  ) : null}
                </div>
                <dl>
                  <div>
                    <dt>运行模式</dt>
                    <dd>{health.data.runtimeMode}</dd>
                  </div>
                  <div>
                    <dt>契约版本</dt>
                    <dd>{health.data.contractVersion}</dd>
                  </div>
                  <div>
                    <dt>知识发布</dt>
                    <dd>{health.data.knowledgeReleaseId ?? '暂无'}</dd>
                  </div>
                </dl>
              </div>
            ) : null}
          </aside>
        </section>

        <section className="home-entrances" aria-label="产品入口">
          {entrances.map((entrance) => (
            <HomeEntrance key={entrance.href} {...entrance} />
          ))}
        </section>

        <section className="content-language" aria-labelledby="content-language-title">
          <header>
            <p className="eyebrow">CONTENT LANGUAGE</p>
            <h2 id="content-language-title">看清每段内容从哪里来</h2>
            <p>下列四种标记会贯穿研究与知识页面，标记来源，不替内容背书。</p>
          </header>
          <div className="content-language__grid">
            {contentMarks.map(({ kind, description }) => (
              <ContentMark key={kind} kind={kind}>
                {description}
              </ContentMark>
            ))}
          </div>
        </section>
      </PageContent>
    </PageShell>
  )
}
