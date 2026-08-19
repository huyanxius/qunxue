import { Link } from 'react-router'

import { RecentResearchPanel } from '../../modules/account'
import { PageContent, PageShell } from '../ui/PageShell'
import { RouterLinkAdapter } from '../ui/RouterLinkAdapter'
import { ResearchStartGuide } from './ResearchStartGuide'
import './app-home.css'

export function AppHomePage() {
  return (
    <PageShell wide>
      <PageContent>
        <div className="work-home">
          <header className="work-home__header">
            <h1>工作台</h1>
          </header>

          <div className="work-home__toolbar">
            <nav className="work-home__views" aria-label="研究视图">
              <span aria-current="page">最近</span>
              <Link to="/my">全部研究</Link>
            </nav>
          </div>

          <div className="work-home__recent" role="region" aria-label="最近研究">
            <RecentResearchPanel
              LinkComponent={RouterLinkAdapter}
              emptyIntro={<ResearchStartGuide />}
            />
          </div>
        </div>
      </PageContent>
    </PageShell>
  )
}
