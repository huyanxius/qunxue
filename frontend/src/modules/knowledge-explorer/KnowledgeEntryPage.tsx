import { useEffect, useState, type ReactNode } from 'react'
import { ArrowLeftIcon } from '@phosphor-icons/react'

import './knowledge-ui.css'
import './knowledge-reader.css'
import { KnowledgeEntryDetail } from './KnowledgeEntryDetail'
import { readCurrentKnowledgeRelease, readKnowledgeEntry } from './knowledgeApi'
import type { KnowledgeEntryDetail as KnowledgeEntryDetailModel } from './types'

interface KnowledgeEntryPageProps {
  knowledgeId: string
  releaseId?: string
  onReleaseResolved: (releaseId: string) => void
  onReturnToResearch?: () => void
  onReturnToKnowledge?: () => void
  returnToKnowledgeLabel?: string
  onStartResearch: (input: { theoryId: string; theoryName: string }) => void
  renderAfterDetail?: (detail: KnowledgeEntryDetailModel) => ReactNode
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '知识服务暂时不可用'
}

export function KnowledgeEntryPage({
  knowledgeId,
  releaseId,
  onReleaseResolved,
  onReturnToResearch,
  onReturnToKnowledge,
  returnToKnowledgeLabel = '返回知识库',
  onStartResearch,
  renderAfterDetail,
}: KnowledgeEntryPageProps) {
  const [detail, setDetail] = useState<KnowledgeEntryDetailModel>()
  const [resolvedReleaseId, setResolvedReleaseId] = useState<string>()
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadDetail() {
      setDetail(undefined)
      setResolvedReleaseId(undefined)
      setError('')
      try {
        let selectedReleaseId = releaseId
        if (!selectedReleaseId) {
          const currentRelease = await readCurrentKnowledgeRelease()
          if (cancelled) return
          onReleaseResolved(currentRelease.knowledgeReleaseId)
          return
        }
        const nextDetail = await readKnowledgeEntry({
          knowledgeId,
          releaseId: selectedReleaseId,
        })
        if (cancelled) return
        setResolvedReleaseId(selectedReleaseId)
        setDetail(nextDetail)
      } catch (nextError) {
        if (!cancelled) setError(errorMessage(nextError))
      }
    }

    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [knowledgeId, onReleaseResolved, releaseId])

  return (
    <article
      className="knowledge-surface knowledge-reader-page"
      role="region"
      aria-label="知识条目正文"
      tabIndex={0}
    >
      <header className="knowledge-reader__actions">
        {onReturnToResearch ? (
          <button type="button" aria-label="返回研究任务" onClick={onReturnToResearch}>
            <ArrowLeftIcon size={14} weight="bold" aria-hidden="true" />
            返回研究任务
          </button>
        ) : null}
        {onReturnToKnowledge ? (
          <button type="button" aria-label={returnToKnowledgeLabel} onClick={onReturnToKnowledge}>
            <ArrowLeftIcon size={14} weight="bold" aria-hidden="true" />
            {returnToKnowledgeLabel}
          </button>
        ) : null}
        {resolvedReleaseId ? <span>固定发布 · {resolvedReleaseId.slice(0, 22)}</span> : null}
      </header>
      {!detail && !error ? <div className="knowledge-ui__loading" role="status"><span />正在整理正文与来源</div> : null}
      {error ? <div className="knowledge-ui__state" role="alert"><strong>知识条目暂时无法读取</strong><p>{error}</p></div> : null}
      {detail ? (
        <>
          <KnowledgeEntryDetail detail={detail} onStartResearch={onStartResearch} />
          {renderAfterDetail?.(detail)}
        </>
      ) : null}
    </article>
  )
}
