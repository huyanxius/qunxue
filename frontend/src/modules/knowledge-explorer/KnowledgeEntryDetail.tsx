import Markdown from 'react-markdown'

import type { KnowledgeEntryDetail } from './types'
import { reviewStatusLabels, verificationStatusLabels } from './labels'

interface KnowledgeEntryDetailProps {
  detail: KnowledgeEntryDetail
  onStartResearch: (input: { theoryId: string; theoryName: string }) => void
}

function sourceMetadata(source: KnowledgeEntryDetail['sources'][number]) {
  return [
    source.authorsOrInstitution.join('、'),
    source.year,
    source.publication,
    source.sourceType,
    source.locator,
  ].filter(Boolean).join(' · ')
}

export function KnowledgeEntryDetail({
  detail,
  onStartResearch,
}: KnowledgeEntryDetailProps) {
  const theory = detail.theoryProfile
  const canSeedTheory = theory?.relatedKnowledgeIds.includes(detail.knowledgeId)

  return (
    <div className="knowledge-explorer__detail">
      <header className="knowledge-explorer__detail-heading">
        <p>{detail.dimension} · {detail.category}</p>
        <h2>{detail.title}</h2>
        <span>{reviewStatusLabels[detail.reviewStatus]}</span>
      </header>
      <p className="knowledge-explorer__path">
        {detail.directoryPath.map((node) => node.title).join(' / ')}
      </p>
      <div className="knowledge-explorer__content"><Markdown>{detail.content}</Markdown></div>

      {detail.aliases.length > 0 ? (
        <section>
          <h3>别名</h3>
          <p>{detail.aliases.join('、')}</p>
        </section>
      ) : null}

      <section>
        <h3>来源</h3>
        {detail.sources.length > 0 ? (
          <ul className="knowledge-explorer__evidence-list">
            {detail.sources.map((source) => (
              <li key={source.sourceId}>
                <p>{source.url ? <a href={source.url}>{source.title}</a> : source.title}</p>
                <small>{sourceMetadata(source)}</small>
                <span>核验状态：{verificationStatusLabels[source.verificationStatus]}</span>
                <span>使用边界：{source.useBoundary}</span>
              </li>
            ))}
          </ul>
        ) : <p>当前发布未提供可展示来源。</p>}
      </section>

      <section>
        <h3>已审核显式关系</h3>
        {detail.relations.length > 0 ? (
          <ul className="knowledge-explorer__relation-list">
            {detail.relations.map((relation) => {
              const targetId = relation.sourceKnowledgeId === detail.knowledgeId
                ? relation.targetKnowledgeId
                : relation.sourceKnowledgeId
              return (
                <li key={relation.relationId}>
                  <p>{targetId}</p>
                  <span>
                    {relation.relationType} · {relation.direction} · {reviewStatusLabels[relation.reviewStatus]}
                  </span>
                  <span>{relation.description}</span>
                  {relation.evidenceSourceIds.length > 0 ? (
                    <span>依据来源：{relation.evidenceSourceIds.join('、')}</span>
                  ) : null}
                </li>
              )
            })}
          </ul>
        ) : <p>当前发布没有与此条目关联的已审核关系。</p>}
      </section>

      {theory ? (
        <section>
          <h3>理论身份</h3>
          <p>{theory.title}</p>
          <span>审核状态：{reviewStatusLabels[theory.reviewStatus]}</span>
          <span>{theory.matchEligible ? '可用于理论匹配' : '当前不用于理论匹配'}</span>
          {canSeedTheory ? (
            <button
              type="button"
              onClick={() => onStartResearch({ theoryId: theory.theoryId, theoryName: theory.title })}
            >
              以此理论开始研究
            </button>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
