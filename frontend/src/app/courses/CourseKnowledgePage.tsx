import { CourseShader } from './CourseShader'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { BooksIcon, TreeStructureIcon } from '@phosphor-icons/react'
import { PageContent, PageShell } from '../ui/PageShell'
import { ObsidianKnowledgeGraph, type KnowledgeGraphProjection } from '../../modules/knowledge-graph'
import { getCourse, listCourses, type SharedCourse } from '../../modules/shared-knowledge'
import '../../modules/knowledge-explorer/knowledge-ui.css'
import '../../modules/knowledge-explorer/knowledge-library.css'
import './courses.css'

type TopicSource = {
  documentId: string
  filename: string
  summary: string
  segmentIds: string[]
}

function courseProjection(course: SharedCourse | null) {
  const nodes: KnowledgeGraphProjection['nodes'][number][] = []
  const edges: KnowledgeGraphProjection['edges'][number][] = []
  const topics = new Map<string, { title: string; sources: TopicSource[] }>()
  if (course) {
    const root = `course:${course.id}`
    nodes.push({ id: root, label: course.name ?? '课程', nodeType: 'dimension' })
    for (const doc of course.documents) {
      if (doc.knowledgeStatus !== 'ready' || !doc.knowledge) continue
      const documentNode = `document:${doc.id}`
      nodes.push({ id: documentNode, label: doc.filename, nodeType: 'category' })
      edges.push({ id: `contains:${doc.id}`, source: root, target: documentNode, relationType: '课件', direction: 'directed', layer: 'structure' })
      for (const topic of doc.knowledge.topics) {
        // Group identical names for navigation; source explanations remain separate evidence.
        const key = `topic:${topic.title.normalize('NFKC').trim()}`
        const value = topics.get(key) ?? { title: topic.title, sources: [] }
        value.sources.push({ documentId: doc.id, filename: doc.filename, summary: topic.summary, segmentIds: topic.segmentIds })
        topics.set(key, value)
        edges.push({ id: `${documentNode}:${key}`, source: documentNode, target: key, relationType: '涉及', direction: 'directed', layer: 'structure' })
      }
      for (const [index, relation] of (doc.knowledge.relations ?? []).entries()) {
        edges.push({ id: `relation:${doc.id}:${index}`, source: `topic:${relation.source.normalize('NFKC').trim()}`,
          target: `topic:${relation.target.normalize('NFKC').trim()}`, relationType: relation.label, direction: 'directed', layer: 'candidate',
          evidenceSourceIds: relation.segmentIds, evidenceLocator: doc.id, sourceTitle: relation.source, targetTitle: relation.target,
          description: doc.filename,
        })
      }
    }
    for (const [id, topic] of topics) nodes.push({ id, label: topic.title, nodeType: 'entry' })
  }
  return { projection: { releaseId: course?.id ?? '', nodes, edges }, topics }
}

function sourceLink(courseId: string, documentId: string, segmentId: string) {
  return `/courses?${new URLSearchParams({ kb_id: courseId, document_id: documentId, segment_id: segmentId })}`
}

export function CourseKnowledgePage() {
  const [params, setParams] = useSearchParams()
  const id = params.get('kb_id')
  const [courses, setCourses] = useState<SharedCourse[]>([])
  const [course, setCourse] = useState<SharedCourse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [query, setQuery] = useState('')
  const [focus, setFocus] = useState<string>()
  const [edgeId, setEdgeId] = useState<string>()
  const [graphOpen, setGraphOpen] = useState(true)
  useEffect(() => {
    let active = true
    setLoading(true); setError(null); setCourse(null); setFocus(undefined); setEdgeId(undefined)
    void (async () => {
      const values = await listCourses()
      if (!active) return
      setCourses(values)
      if (id) {
        const value = await getCourse(id)
        if (active) setCourse(value)
      }
    })().catch((e: Error) => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id, retry])
  useEffect(() => {
    if (!course?.documents.some((doc) => doc.status === 'ready' && ['queued', 'running'].includes(doc.knowledgeStatus))) return
    let active = true
    const timer = window.setInterval(() => {
      void getCourse(course.id).then((value) => { if (active) setCourse(value) })
        .catch((e: Error) => { if (active) { setCourse(null); setError(e.message); window.clearInterval(timer) } })
    }, 3000)
    return () => { active = false; window.clearInterval(timer) }
  }, [course])
  const { projection, topics } = useMemo(() => courseProjection(course), [course])
  const selectTopic = useCallback((key: string) => { setFocus(key); setEdgeId(undefined) }, [])
  const selected = focus ? topics.get(focus) : undefined
  const selectedEdge = projection.edges.find((edge) => edge.id === edgeId)
  const visibleTopics = [...topics].filter(([, topic]) => !query || `${topic.title} ${topic.sources.map((s) => s.summary).join(' ')}`.includes(query))

  return <PageShell workspace defaultRailCollapsed><PageContent>
    <section className="knowledge-surface knowledge-library course-knowledge">
      <div className="course-knowledge__background" aria-hidden="true"><CourseShader /></div>
      <aside className="knowledge-library__sidebar course-knowledge__sidebar" data-mobile-open="true">
        <header className="knowledge-library__identity"><BooksIcon size={18} /><h1>课程知识库</h1></header>
        <nav className="course-knowledge__scopes" aria-label="知识来源"><Link to="/knowledge">公共知识库</Link><Link to="/courses">管理我的课程</Link></nav>
        <label className="course-knowledge__search">搜索课程知识<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="知识点、概念或方法" /></label>
        <nav className="course-knowledge__courses" aria-label="课程目录">{courses.filter((item) => item.access !== 'unavailable').map((item) => <button type="button" key={item.id} aria-current={item.id === id ? 'page' : undefined} onClick={() => { setParams({ scope: 'courses', kb_id: item.id }); setQuery('') }}>{item.name}</button>)}</nav>
      </aside>
      <div className="knowledge-library__main">
        <header className="knowledge-library__topbar"><p><span>知识库</span><b>/</b>{course?.name ?? '课程'}</p><div className="knowledge-library__toolbar">{course ? <button type="button" aria-pressed={graphOpen} onClick={() => setGraphOpen(!graphOpen)}><TreeStructureIcon size={15} />{graphOpen ? '收起课程导图' : '展开课程导图'}</button> : null}</div></header>
        <div className="knowledge-library__content">
          {error ? <p className="qx-message is-error" role="alert">{error}<button type="button" className="courses-page__text-button" onClick={() => setRetry((n) => n + 1)}>重试</button><Link to="/courses">查看课程</Link></p> : null}
          {loading ? <p role="status">正在读取课程知识…</p> : !course && !error ? <div className="material-files__empty"><h2>从一门课程开始</h2><p>选择课程，查看课件中的知识点和原文。</p><Link to="/courses">进入课程</Link></div> : null}
          {course ? <>
            <header className="courses-page__detail"><div><h2>{course.name}</h2><p>{topics.size} 个知识点 · {course.documents.length} 份资料</p></div><Link className="qx-button" to={`/courses?kb_id=${encodeURIComponent(course.id)}`}>阅读课程资料</Link></header>
            {topics.size ? <>
              {graphOpen ? <div className="course-knowledge__graph"><ObsidianKnowledgeGraph projection={projection} focusNodeId={focus} onSelectKnowledge={selectTopic} onExpandNode={selectTopic} onSelectEdge={(key) => { setEdgeId(key); setFocus(undefined) }} /></div> : null}
              <p className="courses-page__hint">同名知识点集中展示，含义以各份原文为准。关系由资料整理产生，需结合原文核对。</p>
              <div className="course-knowledge__body"><nav className="course-knowledge__topics" aria-label="课程知识点">{visibleTopics.map(([key, topic]) => <button type="button" key={key} aria-label={`查看知识点 ${topic.title}`} aria-pressed={focus === key} onClick={() => selectTopic(key)}><strong>{topic.title}</strong><small>{topic.sources.length} 份来源</small></button>)}{!visibleTopics.length ? <p>没有找到相关知识点。</p> : null}</nav>
                <section className="course-knowledge__evidence" aria-label="知识点原文依据">
                  {selected ? <><h3>{selected.title}</h3>{selected.sources.map((source) => <article key={source.documentId}><p>{source.summary}</p><strong>{source.filename}</strong><div>{source.segmentIds.map((segment, index) => <Link key={segment} to={sourceLink(course.id, source.documentId, segment)}>阅读原文 · {source.filename}{source.segmentIds.length > 1 ? ` · ${index + 1}` : ''}</Link>)}</div></article>)}</> : selectedEdge?.evidenceLocator ? <><h3>{selectedEdge.sourceTitle} → {selectedEdge.targetTitle}</h3><p>{selectedEdge.relationType}</p>{selectedEdge.evidenceSourceIds?.map((segment, index) => <Link key={segment} to={sourceLink(course.id, selectedEdge.evidenceLocator!, segment)}>阅读关系依据 · {selectedEdge.description} · {index + 1}</Link>)}</> : <p>选择知识点或关系，查看说明和课件原文。</p>}
                </section>
              </div>
            </> : <p role="status">{course.documents.length ? '课程知识尚未整理完成。资料仍可打开阅读，处理状态可在课程中查看。' : '上传课程资料后，将在这里生成知识点和课程导图。'}</p>}
            {course.documents.filter((doc) => doc.knowledgeStatus === 'failed').map((doc) => <p key={doc.id} className="courses-page__failure">{doc.filename}：知识整理失败，可在课程资料页重试。</p>)}
          </> : null}
        </div>
      </div>
    </section>
  </PageContent></PageShell>
}
