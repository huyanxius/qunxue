import type { KnowledgeReadingLinks } from './readingInsightsApi';
import './frontier-reading-insights.css';

export function FrontierKnowledgeLinks({ links }: { links: KnowledgeReadingLinks }) {
  const empty = { no_release: '暂无可用知识发布', no_topics: '当前文献没有可检索主题', no_matches: '当前知识发布没有匹配的阅读线索' };
  return <section className="frontier-reading-insights" aria-label="知识阅读线索">
    <h3>知识阅读线索</h3>
    {links.state in empty && <p>{empty[links.state as keyof typeof empty]}</p>}
    {links.state === 'low_evidence' && <p>仅凭主题元数据提供线索，尚缺文献内容依据。</p>}
    {links.release && <>
      <p>知识发布：{links.release.id} · {links.release.level === 'preview' ? '预览' : links.release.level === 'final' ? '正式' : '工作版本'}</p>
      <ul>{links.matches.map(item => <li key={item.id}>
        <a href={`/knowledge/${encodeURIComponent(item.id)}?${new URLSearchParams({ knowledge_release_id: links.release!.id })}`}>{item.title}</a>
        <span>内容版本 {item.version}</span><small>主题词：{item.topics.join('、')}</small>
      </li>)}</ul>
    </>}
    {links.limitations.map(note => <p className="frontier-reading-note" key={note}>{note}</p>)}
  </section>;
}
