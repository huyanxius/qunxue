import { DocumentSourceSegment, DocumentSourceView, DocumentWorkspace } from '../../research-materials'
import type { TeachingSource } from '../teachingApi'

export function TeacherSources({ source, selected }: { source: TeachingSource | null; selected: string | null }) {
  return <DocumentWorkspace workspace={false}>
    <DocumentSourceView empty={!source?.items.length} onPageChange={() => {}} railLabel="原文">
      {source?.items.map((item, i) => <section key={item.material_id ?? item.document_id ?? i}>
        <h3>{item.title}</h3>
        {item.segments.map((segment, ordinal) => <DocumentSourceSegment key={segment.segment_id}
          segment={{ segmentId: segment.segment_id, materialId: item.material_id ?? item.document_id ?? '', parseId: '', ordinal,
            kind: 'paragraph', text: segment.text, locator: { page: null, headingPath: [], paragraph: ordinal + 1, lineStart: null, lineEnd: null, charStart: null, charEnd: null } }}
          selected={selected === segment.segment_id} rail={null} railLabel="原文" line={String(ordinal + 1)}
          register={(id, node) => { if (id === selected) node?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }) }}
          onSelect={() => {}}>{segment.text}</DocumentSourceSegment>)}
      </section>)}
    </DocumentSourceView>
  </DocumentWorkspace>
}
