import { Link } from 'react-router'

import knowledgeLibraryHero from '../../assets/workbench/knowledge-library-hero.webp'
import researchAgentHero from '../../assets/workbench/research-agent-hero.webp'
import { useAppLocale } from '../i18n/AppLocaleProvider'

export function WorkbenchDestinations() {
  const { text } = useAppLocale()
  const destinations = [
    {
      to: '/knowledge',
      title: text('知识库', 'Knowledge base'),
      description: text('查找知识条目，回到来源与版本', 'Find knowledge entries and trace them to sources and versions'),
      image: knowledgeLibraryHero,
    },
    {
      to: '/agent',
      title: text('研究 Agent', 'Research Agent'),
      description: text('提出问题，让研究从材料开始推进', 'Ask a question and move research forward from evidence'),
      image: researchAgentHero,
    },
  ]
  return (
    <section className="workbench-destinations" aria-labelledby="workbench-destinations-title">
      <div className="work-home__section-heading">
        <div>
          <p>{text('知识与研究', 'Knowledge & research')}</p>
          <h2 id="workbench-destinations-title">{text('进入工作空间', 'Enter a workspace')}</h2>
        </div>
      </div>
      <nav aria-label={text('工作空间入口', 'Workspace destinations')}>
        <div className="workbench-destinations__list">
          {destinations.map((destination) => (
            <Link className="workbench-destination" key={destination.to} to={destination.to}>
              <img
                className="workbench-destination__image"
                src={destination.image}
                alt=""
                aria-hidden="true"
              />
              <span className="workbench-destination__shade" aria-hidden="true" />
              <span className="workbench-destination__copy">
                <strong>{destination.title}</strong>
                <small>{destination.description}</small>
              </span>
              <span className="workbench-destination__arrow" aria-hidden="true">↗</span>
            </Link>
          ))}
        </div>
      </nav>
    </section>
  )
}
