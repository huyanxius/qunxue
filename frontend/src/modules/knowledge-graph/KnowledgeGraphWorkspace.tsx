import { useEffect, useMemo, useState } from 'react'

import { KnowledgeGraph } from './KnowledgeGraph'
import {
  mergeRelationCandidates,
  mergeReviewedRelations,
  mergeStructuralConnections,
} from './knowledgeGraphAdapter'
import {
  readIncidentCandidatePage,
  readIncidentRelationPage,
  readKnowledgeGraphEntry,
  readStructuralConnectionPage,
} from './knowledgeGraphApi'
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphFocusEntry,
  KnowledgeGraphProjection,
} from './types'

const dimensions = [
  ['D1', '本体论'],
  ['D2', '实践论'],
  ['D3', '方法论'],
  ['D4', '价值论'],
  ['D5', '认识论'],
  ['D6', '学派传统'],
  ['D7', '学科史'],
] as const

function initialProjection(releaseId: string): KnowledgeGraphProjection {
  return {
    releaseId,
    nodes: dimensions.map(([id, label]) => ({ id, label, nodeType: 'dimension' })),
    edges: [],
  }
}

function message(error: unknown) {
  return error instanceof Error ? error.message : '知识图谱暂时不可用'
}

function removeLayer(
  projection: KnowledgeGraphProjection,
  layer: KnowledgeGraphEdge['layer'],
): KnowledgeGraphProjection {
  return {
    ...projection,
    edges: projection.edges.filter((edge) => edge.layer !== layer),
  }
}

interface KnowledgeGraphWorkspaceProps {
  readonly releaseId: string
  readonly focusEntry?: KnowledgeGraphFocusEntry
  readonly onSelectKnowledge: (knowledgeId: string) => void
}

export function KnowledgeGraphWorkspace({
  releaseId,
  focusEntry,
  onSelectKnowledge,
}: KnowledgeGraphWorkspaceProps) {
  const [projection, setProjection] = useState(() => initialProjection(releaseId))
  const [childCursors, setChildCursors] = useState<Record<string, string | null>>({})
  const [candidateEnabled, setCandidateEnabled] = useState(false)
  const [candidateTotal, setCandidateTotal] = useState(0)
  const [relationTotal, setRelationTotal] = useState<number>()
  const [selectedEdgeId, setSelectedEdgeId] = useState<string>()
  const [error, setError] = useState('')
  const [loadingNodeId, setLoadingNodeId] = useState<string>()

  useEffect(() => {
    setProjection(initialProjection(releaseId))
    setChildCursors({})
    setCandidateEnabled(false)
    setCandidateTotal(0)
    setRelationTotal(undefined)
    setSelectedEdgeId(undefined)
    setError('')
  }, [releaseId])

  useEffect(() => {
    if (!focusEntry) {
      setRelationTotal(undefined)
      return
    }
    let cancelled = false

    async function restoreFocus() {
      setError('')
      try {
        setCandidateEnabled(false)
        setCandidateTotal(0)
        setSelectedEdgeId(undefined)
        setProjection({
          releaseId,
          nodes: [{
            id: focusEntry.knowledgeId,
            label: focusEntry.title,
            nodeType: 'entry',
            reviewStatus: focusEntry.reviewStatus,
          }],
          edges: [],
        })
        const path = [
          ...focusEntry.directoryPath,
          {
            nodeId: focusEntry.knowledgeId,
            nodeType: 'entry' as const,
            title: focusEntry.title,
          },
        ]
        for (let index = 0; index < path.length - 1; index += 1) {
          const source = path[index]
          const target = path[index + 1]
          if (!source || !target) continue
          let cursor: string | undefined
          let found = false
          do {
            const page = await readStructuralConnectionPage({
              releaseId,
              sourceNodeId: source.nodeId,
              cursor,
            })
            if (cancelled) return
            const connection = page.connections.find(
              (item) => item.target_node_id === target.nodeId,
            )
            if (connection) {
              setProjection((current) => mergeStructuralConnections(current, [connection]))
              found = true
              break
            }
            cursor = page.nextCursor
          } while (cursor)
          if (!found) throw new Error(`知识结构中缺少 ${target.title} 的目录路径`)
        }

        let relationCursor: string | undefined
        let total = 0
        do {
          const page = await readIncidentRelationPage({
            releaseId,
            knowledgeId: focusEntry.knowledgeId,
            cursor: relationCursor,
          })
          if (cancelled) return
          setProjection((current) => mergeReviewedRelations(current, page.relations))
          total = page.totalCount
          relationCursor = page.nextCursor
        } while (relationCursor)
        setRelationTotal(total)
      } catch (nextError) {
        if (!cancelled) setError(message(nextError))
      }
    }

    void restoreFocus()
    return () => {
      cancelled = true
    }
  }, [focusEntry, releaseId])

  async function expandNode(nodeId: string) {
    if (Object.hasOwn(childCursors, nodeId) && childCursors[nodeId] === null) return
    setLoadingNodeId(nodeId)
    setError('')
    try {
      const page = await readStructuralConnectionPage({
        releaseId,
        sourceNodeId: nodeId,
        cursor: childCursors[nodeId] ?? undefined,
      })
      setProjection((current) => mergeStructuralConnections(current, page.connections))
      setChildCursors((current) => ({
        ...current,
        [nodeId]: page.nextCursor ?? null,
      }))
    } catch (nextError) {
      setError(message(nextError))
    } finally {
      setLoadingNodeId(undefined)
    }
  }

  async function enableCandidates() {
    if (!focusEntry) return
    if (candidateEnabled) {
      setCandidateEnabled(false)
      setSelectedEdgeId(undefined)
      setProjection((current) => removeLayer(current, 'candidate'))
      return
    }
    setError('')
    try {
      let cursor: string | undefined
      let total = 0
      const candidates: Array<(
        Awaited<ReturnType<typeof readIncidentCandidatePage>>['candidates']
      )[number]> = []
      do {
        const page = await readIncidentCandidatePage({
          releaseId,
          knowledgeId: focusEntry.knowledgeId,
          cursor,
        })
        candidates.push(...page.candidates)
        cursor = page.nextCursor
        total = page.totalCount
      } while (cursor)
      const endpointTitles = new Map(
        projection.nodes
          .filter((node) => node.label !== node.id)
          .map((node) => [node.id, node.label]),
      )
      endpointTitles.set(focusEntry.knowledgeId, focusEntry.title)
      const missingEndpointIds = [...new Set(candidates.flatMap((candidate) => [
        candidate.source_knowledge_id,
        candidate.target_knowledge_id,
      ]))].filter((knowledgeId) => !endpointTitles.has(knowledgeId))
      const missingEndpoints = await Promise.all(missingEndpointIds.map((knowledgeId) => (
        readKnowledgeGraphEntry({ releaseId, knowledgeId })
      )))
      missingEndpoints.forEach((entry) => endpointTitles.set(entry.knowledgeId, entry.title))
      setProjection((current) => mergeRelationCandidates(current, candidates, endpointTitles))
      setCandidateTotal(total)
      setCandidateEnabled(true)
    } catch (nextError) {
      setError(message(nextError))
    }
  }

  const selectedEdge = useMemo(
    () => projection.edges.find((edge) => edge.id === selectedEdgeId),
    [projection.edges, selectedEdgeId],
  )

  return (
    <section className="knowledge-graph-workspace" aria-label="真实知识图谱">
      <div className="knowledge-graph-workspace__toolbar">
        <div>
          <strong>结构目录</strong>
          <span>点击维度或目录节点逐级加载；不会一次铺满全部条目。</span>
        </div>
        <button
          type="button"
          disabled={!focusEntry}
          aria-pressed={candidateEnabled}
          onClick={() => void enableCandidates()}
        >
          {candidateEnabled ? '关闭待审核发现' : '开启待审核发现'}
        </button>
      </div>

      {focusEntry ? <p>当前条目：{focusEntry.title}</p> : (
        <p>从搜索结果选择“在图中定位”，即可恢复完整目录路径。</p>
      )}
      {loadingNodeId ? <p role="status">正在展开 {loadingNodeId} 的直接子级……</p> : null}
      {error ? <p className="knowledge-graph-workspace__error" role="alert">{error}</p> : null}
      {focusEntry && relationTotal === 0 ? (
        <p>正式关系：当前条目没有已审核关系。</p>
      ) : null}
      {candidateEnabled ? (
        <p className="knowledge-graph-workspace__pending-note">
          待审核发现：{candidateTotal} 条。它们不是 reviewed，也不是正式知识事实。
        </p>
      ) : null}

      <KnowledgeGraph
        projection={projection}
        focusNodeId={focusEntry?.knowledgeId}
        onExpandNode={(nodeId) => void expandNode(nodeId)}
        onSelectEdge={setSelectedEdgeId}
        onSelectKnowledge={onSelectKnowledge}
      />

      {selectedEdge?.layer === 'candidate' ? (
        <aside className="knowledge-graph-workspace__edge-panel" aria-label="待审核发现关系详情">
          <p>pending · 待审核发现关系</p>
          <h3>{selectedEdge.relationType} · {selectedEdge.direction}</h3>
          <p>
            {selectedEdge.sourceTitle ?? selectedEdge.source}（{selectedEdge.source}）
            {' → '}
            {selectedEdge.targetTitle ?? selectedEdge.target}（{selectedEdge.target}）
          </p>
          <blockquote>{selectedEdge.evidenceExcerpt}</blockquote>
          <dl>
            <dt>证据位置</dt><dd>{selectedEdge.evidenceLocator}</dd>
            <dt>生产器</dt><dd>{selectedEdge.producer} · {selectedEdge.producerConfigVersion}</dd>
            <dt>触发说明</dt><dd>{selectedEdge.triggerReason}</dd>
            <dt>规则分数</dt>
            <dd>{selectedEdge.score === 1
              ? '1.0：确定性规则命中，不是校准置信度。'
              : (selectedEdge.score ?? '未提供')}</dd>
          </dl>
        </aside>
      ) : null}

      {selectedEdge?.layer === 'reviewed' ? (
        <aside className="knowledge-graph-workspace__edge-panel" aria-label="正式知识关系详情">
          <p>reviewed · 正式知识关系</p>
          <h3>{selectedEdge.relationType} · {selectedEdge.direction}</h3>
          <p>{selectedEdge.description}</p>
          <dl>
            <dt>证据来源 ID</dt><dd>{selectedEdge.evidenceSourceIds?.join('、') || '未提供'}</dd>
            <dt>内容版本</dt><dd>{selectedEdge.contentVersion}</dd>
          </dl>
        </aside>
      ) : null}
    </section>
  )
}
