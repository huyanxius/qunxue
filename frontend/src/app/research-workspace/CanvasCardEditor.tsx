import { useEffect, useState } from 'react'
import { canvasSuggestions, getAgentConversation, saveCanvasNode, type AgentConversation, type AgentResearchMapNode } from '../../modules/research-agent'

export type CanvasCardDraft = { title: string; summary: string; original: AgentResearchMapNode; version: number }

export function CanvasCardEditor({ conversation, node, onSaved, draftCache }: {
  draftCache?: Map<string, CanvasCardDraft>
  conversation: AgentConversation
  node: AgentResearchMapNode
  onSaved: (conversation: AgentConversation) => void
}) {
  const cacheKey = `${conversation.conversation_id}:${node.id}`
  const [draft, setDraft] = useState<CanvasCardDraft | null>(draftCache?.get(cacheKey) ?? null)
  useEffect(() => { if (draft) draftCache?.set(cacheKey, draft); else draftCache?.delete(cacheKey) }, [draft, draftCache, cacheKey])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dismissed, setDismissed] = useState<string[]>([])
  const suggestion = canvasSuggestions(conversation, node).find(item => !dismissed.includes(item.key))

  async function save() {
    if (!draft || pending) return
    setPending(true); setError('')
    try {
      const updated = await saveCanvasNode(conversation.conversation_id, node.id, {
        title: draft.title, summary: draft.summary, expected_title: draft.original.title,
        expected_summary: draft.original.summary, expected_version: draft.version,
      })
      onSaved(updated); setDraft(null); setNotice('已保存，等待进一步验证。')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败，请重试。') }
    finally { setPending(false) }
  }

  async function reload() {
    setPending(true)
    try {
      const updated = await getAgentConversation(conversation.conversation_id)
      const latest = updated.research_map?.nodes.find(item => item.id === node.id)
      onSaved(updated)
      if (latest) setDraft(current => current ? { ...current, original: latest, version: updated.canvas_edit_version ?? 0 } : null)
      setError(''); setNotice('已载入最新原文。请与下面的草稿核对后再保存。')
    } catch { setError('载入失败，草稿仍保留。') }
    finally { setPending(false) }
  }

  return <div className="canvas-card-editor">
    {draft ? <form onSubmit={event => { event.preventDefault(); void save() }}>
      <label>标题<input aria-label="标题" value={draft.title} required maxLength={240} disabled={pending} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>说明<textarea aria-label="说明" value={draft.summary} maxLength={1200} rows={6} disabled={pending} onChange={event => setDraft({ ...draft, summary: event.target.value })} /></label>
      <p>引用保留；改写后的判断需要重新验证。</p>
      <div className="canvas-card-editor__actions"><button type="submit" disabled={pending || !draft.title.trim()}>{pending ? '正在保存…' : '保存修改'}</button><button type="button" disabled={pending} onClick={() => { setDraft(null); setError('') }}>取消</button></div>
    </form> : <button type="button" onClick={() => { setDraft({ title: node.title, summary: node.summary ?? '', original: node, version: conversation.canvas_edit_version ?? 0 }); setNotice('') }}>编辑卡片</button>}
    {error ? <div role="alert"><p>{error}</p><button type="button" disabled={pending} onClick={() => void reload()}>载入最新版本，保留草稿</button></div> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {!draft && suggestion ? <section className="canvas-card-editor__suggestion" aria-label="Agent 修改建议"><span>Agent 建议 · 等待你确认</span><h4>{suggestion.title}</h4><p>{suggestion.summary}</p><div className="canvas-card-editor__actions"><button type="button" onClick={() => setDraft({ title: suggestion.title, summary: suggestion.summary ?? '', original: node, version: conversation.canvas_edit_version ?? 0 })}>核对并采纳</button><button type="button" onClick={() => setDismissed([...dismissed, suggestion.key])}>暂不采纳</button></div></section> : null}
  </div>
}
