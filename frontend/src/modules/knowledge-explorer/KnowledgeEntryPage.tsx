import { useEffect, useState } from 'react'

import './KnowledgeExplorer.css'
import { KnowledgeEntryDetail } from './KnowledgeEntryDetail'
import { readCurrentKnowledgeRelease, readKnowledgeEntry } from './knowledgeApi'
import type { KnowledgeEntryDetail as KnowledgeEntryDetailModel } from './types'

interface KnowledgeEntryPageProps {
  knowledgeId: string
  releaseId?: string
  onReleaseResolved: (releaseId: string) => void
  onReturnToResearch?: () => void
  onStartResearch: (input: { theoryId: string; theoryName: string }) => void
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '知识服务暂时不可用'
}

export function KnowledgeEntryPage({
  knowledgeId,
  releaseId,
  onReleaseResolved,
  onReturnToResearch,
  onStartResearch,
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
  }, [knowledgeId, releaseId])

  return (
    <article className="knowledge-explorer knowledge-explorer--entry">
      <header className="knowledge-explorer__header">
        <div>
          <p className="knowledge-explorer__eyebrow">KNOWLEDGE / ENTRY</p>
          <h1>知识条目</h1>
        </div>
        {onReturnToResearch ? (
          <button type="button" className="knowledge-explorer__plain-action" onClick={onReturnToResearch}>
            返回研究任务
          </button>
        ) : null}
      </header>
      {resolvedReleaseId ? <p className="knowledge-explorer__release">当前发布 {resolvedReleaseId}</p> : null}
      {!detail && !error ? <p role="status">正在读取详情……</p> : null}
      {error ? <p className="knowledge-explorer__error" role="alert">{error}</p> : null}
      {detail ? <KnowledgeEntryDetail detail={detail} onStartResearch={onStartResearch} /> : null}
    </article>
  )
}
