import { Link, useSearchParams } from 'react-router'
import { PlusIcon } from '@phosphor-icons/react'

import { MyResearchPage, RecentResearchPanel } from '../../modules/account'
import { PageContent, PageShell } from '../ui/PageShell'
import { RouterLinkAdapter } from '../ui/RouterLinkAdapter'
import { WorkbenchDestinations } from './WorkbenchDestinations'
import { useAppLocale } from '../i18n/AppLocaleProvider'
import './app-home.css'

export function AppHomePage() {
  const { text } = useAppLocale()
  const [searchParams] = useSearchParams()
  const showingAllResearch = searchParams.get('research') === 'all'

  return (
    <PageShell wide shader>
      <PageContent>
        <div className="work-home">
          <div className="work-home__canvas">
            <header className="work-home__hero">
              <div className="work-home__hero-copy">
                <h1>{text('工作台', 'Workbench')}</h1>
                <p>{text('继续一项正在形成的研究，或从一个具体现象开始。', 'Continue a developing study, or begin with a concrete social phenomenon.')}</p>
              </div>
              <Link className="work-home__start" to="/research/new">
                <PlusIcon size={17} weight="regular" aria-hidden="true" />
                {text('新建研究', 'New research')}
              </Link>
            </header>

            <div className="work-home__workspace">
              <WorkbenchDestinations />

              <section className="work-home__section work-home__section--recent" aria-labelledby="work-home-recent-title">
                <div className="work-home__section-heading">
                  <div>
                    <p>{text('正在进行', 'In progress')}</p>
                    <h2 id="work-home-recent-title">
                      {showingAllResearch ? text('全部研究', 'All research') : text('继续研究', 'Continue research')}
                    </h2>
                  </div>
                  <nav
                    className="work-home__views"
                    aria-label={text('研究视图', 'Research view')}
                    data-view={showingAllResearch ? 'all' : 'recent'}
                  >
                    {showingAllResearch
                      ? <Link to="/app">{text('最近', 'Recent')}</Link>
                      : <span aria-current="page">{text('最近', 'Recent')}</span>}
                    {showingAllResearch
                      ? <span aria-current="page">{text('查看全部', 'View all')}</span>
                      : <Link to="/app?research=all">{text('查看全部', 'View all')}</Link>}
                  </nav>
                </div>

                <div
                  className={`work-home__recent${showingAllResearch ? ' work-home__research--all' : ''}`}
                  role={showingAllResearch ? undefined : 'region'}
                  aria-label={showingAllResearch ? undefined : text('最近研究', 'Recent research')}
                >
                  {showingAllResearch
                    ? <MyResearchPage />
                    : <RecentResearchPanel LinkComponent={RouterLinkAdapter} />}
                </div>
              </section>
            </div>
          </div>
        </div>
      </PageContent>
    </PageShell>
  )
}
