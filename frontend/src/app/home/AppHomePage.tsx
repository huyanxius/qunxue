import { Link } from 'react-router'

import { RecentResearchPanel } from '../../modules/account'
import { PageContent, PageShell } from '../ui/PageShell'
import { RouterLinkAdapter } from '../ui/RouterLinkAdapter'
import './app-home.css'

const spaces = [
  {
    href: '/my',
    label: '我的研究',
    description: '查看全部任务、阶段与更新时间。',
    className: 'work-home__space work-home__space--research',
  },
  {
    href: '/knowledge',
    label: '理论知识库',
    description: '搜索条目，核对来源与审核状态。',
    className: 'work-home__space',
  },
  {
    href: '/knowledge/graph',
    label: '知识图谱',
    description: '从目录位置和已审核关系浏览知识。',
    className: 'work-home__space',
  },
]

export function AppHomePage() {
  return (
    <PageShell>
      <PageContent>
        <div className="work-home">
          <header className="work-home__header">
            <div>
              <p className="eyebrow">工作台</p>
              <h1>继续你的研究</h1>
              <p>回到最近一步，或者从一个新现象开始。</p>
            </div>
            <Link className="primary-action" to="/research/new">开始新研究</Link>
          </header>

          <RecentResearchPanel LinkComponent={RouterLinkAdapter} />

          <section className="work-home__spaces" aria-labelledby="work-spaces-title">
            <header>
              <h2 id="work-spaces-title">研究空间</h2>
              <p>去完成一件具体的事。</p>
            </header>
            <div>
              {spaces.map((space) => (
                <Link key={space.href} className={space.className} to={space.href}>
                  <strong>{space.label}</strong>
                  <span>{space.description}</span>
                  <span aria-hidden="true">↗</span>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </PageContent>
    </PageShell>
  )
}
