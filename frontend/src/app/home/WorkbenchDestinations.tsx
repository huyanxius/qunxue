import { Link } from 'react-router'

const destinations = [
  {
    to: '/research/new',
    title: '研究',
  },
  {
    to: '/knowledge',
    title: '知识库',
  },
  {
    to: '/knowledge/graph',
    title: '知识图谱',
  },
] as const

export function WorkbenchDestinations() {
  return (
    <nav className="workbench-destinations" aria-label="继续探索">
      <div className="workbench-destinations__list">
        {destinations.map((destination) => (
          <Link className="workbench-destination" key={destination.to} to={destination.to}>
            <span className="workbench-destination__image" aria-hidden="true" />
            <strong>{destination.title}</strong>
          </Link>
        ))}
      </div>
    </nav>
  )
}
