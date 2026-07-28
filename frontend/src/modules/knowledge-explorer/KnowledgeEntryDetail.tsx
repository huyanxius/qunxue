import type {
  KnowledgeExplorerDetail,
  KnowledgeRelation,
  KnowledgeSource,
} from './types'
import { reviewStatusLabels, verificationStatusLabels } from './labels'

interface KnowledgeEntryDetailProps {
  detail: KnowledgeExplorerDetail
  onSelectRelated: (knowledgeId: string) => void
}

function relatedKnowledgeId(
  relation: KnowledgeRelation,
  currentKnowledgeId: string,
) {
  return relation.sourceKnowledgeId === currentKnowledgeId
    ? relation.targetKnowledgeId
    : relation.sourceKnowledgeId
}

function sourceMetadata(source: KnowledgeSource) {
  return [
    source.contributor,
    source.year,
    source.publication,
    source.sourceType,
    verificationStatusLabels[source.verificationStatus],
    source.locator,
  ]
    .filter(Boolean)
    .join(' · ')
}

export function KnowledgeEntryDetail({
  detail,
  onSelectRelated,
}: KnowledgeEntryDetailProps) {
  return (
    <>
      <header className="knowledge-explorer__detail-heading">
        <p>{detail.entry.category}</p>
        <h2>{detail.entry.title}</h2>
        <span>{reviewStatusLabels[detail.entry.reviewStatus]}</span>
      </header>
      <div className="knowledge-explorer__content">
        <p>{detail.content}</p>
      </div>

      <section>
        <h3>用途准入</h3>
        <dl className="knowledge-explorer__eligibility">
          <div>
            <dt>可视化浏览</dt>
            <dd>
              {detail.useEligibility.browseEligible ? '已准入' : '未准入'}
            </dd>
          </div>
          <div>
            <dt>RAG</dt>
            <dd>{detail.useEligibility.ragEligible ? '已准入' : '未准入'}</dd>
          </div>
          <div>
            <dt>训练候选</dt>
            <dd>
              {detail.useEligibility.trainingCandidateEligible
                ? '已准入'
                : '未准入'}
            </dd>
          </div>
          <div>
            <dt>理论匹配</dt>
            <dd>{detail.useEligibility.matchEligible ? '已准入' : '未准入'}</dd>
          </div>
        </dl>
        {detail.useEligibility.reviewRecordIds.length > 0 ? (
          <p className="knowledge-explorer__trace">
            审核记录：{detail.useEligibility.reviewRecordIds.join('、')}
          </p>
        ) : null}
      </section>

      <section>
        <h3>来源</h3>
        {detail.sources.length > 0 ? (
          <ul className="knowledge-explorer__evidence-list">
            {detail.sources.map((source) => (
              <li key={source.sourceId}>
                <p>
                  {source.url ? (
                    <a href={source.url}>{source.title}</a>
                  ) : (
                    source.title
                  )}
                </p>
                <small>{sourceMetadata(source)}</small>
                {source.usageBoundary ? (
                  <span>使用边界：{source.usageBoundary}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p>当前发布未提供可展示来源。</p>
        )}
      </section>

      <section>
        <h3>已审核显式关系</h3>
        {detail.relations.length > 0 ? (
          <ul className="knowledge-explorer__relation-list">
            {detail.relations.map((relation) => (
              <li key={relation.relationId}>
                <button
                  type="button"
                  onClick={() =>
                    onSelectRelated(
                      relatedKnowledgeId(relation, detail.entry.knowledgeId),
                    )
                  }
                >
                  {relation.relatedTitle}
                </button>
                <p>
                  {relation.relationType} ·{' '}
                  {relation.direction === 'bidirectional' ? '双向' : '有向'} ·{' '}
                  {reviewStatusLabels[relation.reviewStatus]}
                  {relation.evidenceGrade
                    ? ` · 证据 ${relation.evidenceGrade}`
                    : ''}
                </p>
                <span>{relation.description}</span>
                {relation.evidenceSourceIds.length > 0 ? (
                  <span>
                    依据来源：{relation.evidenceSourceIds.join('、')} · 关系版本 v
                    {relation.contentVersion}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p>当前发布没有与此条目关联的已审核关系。</p>
        )}
      </section>
    </>
  )
}
