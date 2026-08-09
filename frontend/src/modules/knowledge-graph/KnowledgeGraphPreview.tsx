import { useQuery } from '@tanstack/react-query'

import { ObsidianKnowledgeGraph } from './ObsidianKnowledgeGraph'
import { mergeDirectoryPath } from './knowledgeGraphAdapter'
import {
  readCurrentKnowledgeGraphRelease,
  searchKnowledgeGraphEntries,
} from './knowledgeGraphApi'
import type { KnowledgeGraphProjection } from './types'

export function KnowledgeGraphPreview({
  onSelectKnowledge,
}: {
  onSelectKnowledge: (knowledgeId: string) => void
}) {
  const preview = useQuery({
    queryKey: ['knowledge-graph', 'home-preview'],
    queryFn: async () => {
      const releaseId = await readCurrentKnowledgeGraphRelease()
      const page = await searchKnowledgeGraphEntries({ releaseId, query: '' })
      return page.entries.slice(0, 32).reduce<KnowledgeGraphProjection>(
        (projection, entry) => mergeDirectoryPath(projection, entry),
        { releaseId, nodes: [], edges: [] },
      )
    },
    retry: false,
  })

  if (preview.isPending) {
    return <div className="graph-preview-state" role="status">正在整理知识位置</div>
  }
  if (preview.isError) {
    return (
      <div className="graph-preview-state" role="status">
        <p>暂时无法读取图谱预览。</p>
        <button type="button" onClick={() => preview.refetch()}>重新加载图谱</button>
      </div>
    )
  }

  return (
    <ObsidianKnowledgeGraph
      projection={preview.data}
      variant="preview"
      onSelectKnowledge={onSelectKnowledge}
    />
  )
}
