import { CaretDownIcon, ArrowCounterClockwiseIcon, ArrowUpRightIcon, BrainIcon, ClockCounterClockwiseIcon, PencilSimpleIcon, PlusIcon, QuotesIcon, SlidersHorizontalIcon, TrashIcon, XIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { loadMemoryOverview, loadMemories, loadMemoryHistory, removeMemory, saveMemory, saveMemorySettings, type ResearchMemory, type ResearchMemorySettings } from '../../modules/research-memory'
import { ResearchHubToolbar } from './ResearchHubToolbar'
import { memoryPreview } from './researchMemoryPreview'
import './research-memory-panel.css'

const originLabels = { manual: '手动记录', explicit: '对话中记住', learned: '自动整理' }
const date = (value: string) => new Date(value).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
const message = (error: unknown) => error instanceof Error ? error.message : '操作未完成，请重试。'

export function ResearchMemoryPanel({ taskId, projectName, preview = false }: { taskId: string | null; projectName?: string; preview?: boolean }) {
  const [params] = useSearchParams()
  const exitParams = new URLSearchParams(params); exitParams.delete('preview')
  const [items, setItems] = useState<ResearchMemory[]>(() => preview ? memoryPreview(taskId) : [])
  const [settings, setSettings] = useState<ResearchMemorySettings | null>(() => preview ? { task_id: taskId, version: 0, use_memory: true, learn_memory: true } : null)
  const [loading, setLoading] = useState(!preview)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [summary, setSummary] = useState('')
  const [summaryBusy, setSummaryBusy] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  const [summaryReload, setSummaryReload] = useState(0)
  const [origin, setOrigin] = useState('all')
  const [sort, setSort] = useState('recent')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [editor, setEditor] = useState<ResearchMemory | 'new' | null>(null)
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<string, ResearchMemory[]>>({})
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    if (preview) return
    const controller = new AbortController()
    setLoading(true); setError('')
    void loadMemories(taskId, controller.signal).then(result => {
      if (!controller.signal.aborted) { setItems(result.items); setSettings(result.settings) }
    }).catch(cause => { if (!controller.signal.aborted) setError(message(cause)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [taskId, preview, reload])
  useEffect(() => { if (editor) editorRef.current?.focus() }, [editor])
  useEffect(() => {
    const controller = new AbortController()
    setSummary(''); setSummaryError('')
    if (loading || !settings || !items.length) { setSummaryBusy(false); return }
    if (preview) {
      setSummary(items.map(item => item.content).join(' '))
      setSummaryBusy(false)
      return
    }
    setSummaryBusy(true)
    void loadMemoryOverview(taskId, settings.version, controller.signal).then(value => {
      if (!controller.signal.aborted) setSummary(value)
    }).catch(cause => {
      if (!controller.signal.aborted) setSummaryError(message(cause))
    }).finally(() => { if (!controller.signal.aborted) setSummaryBusy(false) })
    return () => controller.abort()
  }, [taskId, settings, items, loading, preview, summaryReload])


  function edit(item: ResearchMemory | 'new') { setDetailsOpen(true); setSelectedId(item === 'new' ? null : item.memory_id); setEditor(item); setContent(item === 'new' ? '' : item.content); setError(''); setNotice('') }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!editor || busy || !content.trim()) return
    if (new TextEncoder().encode(content.trim()).length > 2000) { setError('内容较长，请拆成更简短的记忆条目。'); return }
    setBusy(true); setError('')
    try {
      const existing = editor === 'new' ? undefined : editor
      const updated: ResearchMemory = preview ? {
        memory_id: existing?.memory_id ?? `preview-${crypto.randomUUID()}`, task_id: taskId, key: existing?.key ?? 'preview.note',
        content: content.trim(), origin: 'manual', version: (existing?.version ?? 0) + 1,
        created_at: existing?.created_at ?? new Date().toISOString(), updated_at: new Date().toISOString(),
        source_conversation_id: null, source_message_id: null, source_quote: null,
      } : await saveMemory(taskId, content.trim(), existing)
      if (!alive.current) return
      if (preview) setHistory(current => ({ ...current, [updated.memory_id]: [updated, ...(current[updated.memory_id] ?? (existing ? [existing] : []))] }))
      else setHistory(current => { const next = { ...current }; delete next[updated.memory_id]; return next })
      setItems(current => [updated, ...current.filter(item => item.memory_id !== updated.memory_id)])
      setSettings(current => current ? { ...current, version: current.version + 1 } : current)
      setEditor(null); setSelectedId(updated.memory_id); setNotice(preview ? '示例已更新，仅保留在当前预览。' : '记忆已保存。')
    } catch (cause) { if (alive.current) setError(message(cause)) }
    finally { if (alive.current) setBusy(false) }
  }
  async function remove(item: ResearchMemory) {
    setBusy(true); setError('')
    try {
      if (!preview) await removeMemory(item)
      if (!alive.current) return
      setItems(current => current.filter(entry => entry.memory_id !== item.memory_id)); setDeleteId(null); setSelectedId(null); setEditor(null)
      setSettings(current => current ? { ...current, version: current.version + 1 } : current)
      setNotice(preview ? '示例已删除，刷新可恢复。' : '记忆已删除。')
    } catch (cause) { if (alive.current) setError(message(cause)) }
    finally { if (alive.current) setBusy(false) }
  }
  async function toggle(field: 'use_memory' | 'learn_memory') {
    if (!settings || busy) return
    setBusy(true); setError('')
    try {
      const updated = preview ? { ...settings, [field]: !settings[field], version: settings.version + 1 } : await saveMemorySettings(settings, field, !settings[field])
      if (alive.current) { setSettings(updated); setNotice(preview ? '示例设置已更新。' : '记忆设置已保存。') }
    } catch (cause) { if (alive.current) setError(message(cause)) }
    finally { if (alive.current) setBusy(false) }
  }
  async function showHistory(item: ResearchMemory) {
    if (historyId === item.memory_id) { setHistoryId(null); return }
    setHistoryId(item.memory_id)
    if (history[item.memory_id]) return
    setHistoryBusy(true); setError('')
    try {
      const records = preview ? [item] : await loadMemoryHistory(item.memory_id)
      if (alive.current) setHistory(current => ({ ...current, [item.memory_id]: records }))
    } catch (cause) { if (alive.current) setError(message(cause)) }
    finally { if (alive.current) setHistoryBusy(false) }
  }
  const visible = items.filter(item => (origin === 'all' || item.origin === origin) && `${item.content} ${item.source_quote ?? ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())).sort((a, b) => sort === 'recent' ? b.updated_at.localeCompare(a.updated_at) : a.updated_at.localeCompare(b.updated_at))
  const selected = items.find(item => item.memory_id === selectedId)
  const detailOpen = Boolean(selected || editor === 'new')

  const editorForm = editor ? <form className="research-memory__editor" onSubmit={event => void submit(event)}>
      <header><strong>{editor === 'new' ? '添加记忆' : '编辑记忆'}</strong><button type="button" aria-label="关闭编辑" disabled={busy} onClick={() => { setEditor(null); if (editor === 'new') setSelectedId(null) }}><XIcon size={17} /></button></header>
      <label htmlFor="memory-content">{taskId ? '希望在这个项目里记住什么？' : '希望 Agent 记住什么？'}</label>
      <textarea ref={editorRef} id="memory-content" rows={4} value={content} onChange={event => setContent(event.target.value)} maxLength={2000} placeholder="例如：比较不同解释时，先回到原始材料核验。" disabled={busy} required />
      <footer><span>{taskId ? '保存到项目记忆' : '保存到个人记忆'}</span><button type="button" disabled={busy} onClick={() => setEditor(null)}>取消</button><button className="research-memory__primary" type="submit" disabled={busy || !content.trim()}>{busy ? '保存中…' : '保存记忆'}</button></footer>
    </form> : null

  return <div className="research-memory">
    <section className="research-memory__overview" aria-label="记忆概览" aria-busy={loading || summaryBusy}>
      <header className="research-memory__heading">
        <div><h2>{taskId ? '关于这个项目' : 'Agent 记住了什么'}</h2><p>{taskId ? projectName ?? '项目记忆' : '个人记忆'}<span>·</span><span>{loading ? '正在读取…' : `${items.length} 条记忆`}</span></p></div>
        <button type="button" aria-expanded={settingsOpen} aria-controls="memory-settings" onClick={() => setSettingsOpen(open => !open)}><SlidersHorizontalIcon size={16} />记忆设置</button>
      </header>
      {loading || summaryBusy ? <p className="research-memory__summary-status" role="status">{loading ? '正在读取记忆…' : 'Agent 正在整理记忆概览…'}</p>
        : summary ? <p className="research-memory__summary">{summary}</p>
        : summaryError ? <div className="research-memory__summary-status"><p>{summaryError}</p><button type="button" onClick={() => setSummaryReload(value => value + 1)}>重新整理</button></div>
        : <p className="research-memory__summary-status">{error ? '暂时无法读取记忆。' : '这里会逐渐形成 Agent 对你的了解。你可以先添加一条记忆，也可以在对话中让它记住。'}</p>}
      <footer className="research-memory__overview-footer">
        <button className="research-memory__disclosure" type="button" aria-expanded={detailsOpen} aria-controls="memory-records" onClick={() => setDetailsOpen(open => !open)}><CaretDownIcon size={15} />{detailsOpen ? '收起记忆明细' : '查看记忆明细'}</button>
        <button type="button" disabled={loading || busy || !settings} onClick={() => edit('new')}><PlusIcon size={15} />添加记忆</button>
        {!preview && summary ? <span>根据已保存的记忆整理</span> : null}
      </footer>
      {settings && !settings.use_memory ? <p className="research-memory__notice">已暂停在对话中使用{taskId ? '项目' : '个人'}记忆，保存的内容仍可查看。</p> : null}
    </section>
    {preview ? <div className="research-memory__preview"><span>示例预览 · 修改不会写入真实记忆</span><Link to={`?${exitParams}`}>查看真实记忆</Link><button type="button" onClick={() => { setItems(memoryPreview(taskId)); setHistory({}); setEditor(null); setDeleteId(null); setHistoryId(null); setSelectedId(null); setNotice('示例已恢复。') }}><ArrowCounterClockwiseIcon size={14} />恢复示例</button></div> : null}
    {settingsOpen ? <section className="research-memory__settings" id="memory-settings" aria-label="记忆设置">
      <div><div><strong>使用{taskId ? '项目' : '个人'}记忆</strong><p>{taskId ? '在当前项目的对话中参考这些记忆。' : '在对话中参考你的个人记忆。'}</p></div><button type="button" role="switch" aria-label={`使用${taskId ? '项目' : '个人'}记忆`} aria-checked={settings?.use_memory ?? false} disabled={!settings || busy} onClick={() => void toggle('use_memory')} /></div>
      <div><div><strong>自动整理记忆</strong><p>从后续对话中整理值得保留的信息，随时可以修正或删除。</p></div><button type="button" role="switch" aria-label="自动整理记忆" aria-checked={settings?.learn_memory ?? false} disabled={!settings || busy} onClick={() => void toggle('learn_memory')} /></div>
    </section> : null}
    {error ? <p className="research-memory__error" role="alert">{error} {!preview ? <button type="button" onClick={() => { setReload(value => value + 1); setEditor(null) }}>刷新记录</button> : null}</p> : null}
    {notice ? <p className="research-memory__notice" role="status">{notice}</p> : null}
    {detailsOpen ? <section className="research-memory__details" id="memory-records" aria-label="记忆明细">
    <ResearchHubToolbar query={query} onQueryChange={setQuery} searchLabel="搜索记忆" placeholder="搜索记忆内容">
      <div className="research-memory__filters">
        <select aria-label="记忆来源" value={origin} onChange={event => setOrigin(event.target.value)}><option value="all">全部来源</option>{Object.entries(originLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
        <select aria-label="记忆排序" value={sort} onChange={event => setSort(event.target.value)}><option value="recent">最近更新</option><option value="oldest">最早更新</option></select>
      </div>
    </ResearchHubToolbar>
    <div className={`research-memory__workspace${detailOpen ? ' has-detail' : ''}`}>
      <div className="research-memory__records">
        <table className="research-memory__table" aria-label={taskId ? '项目记忆列表' : '个人记忆列表'}>
          <thead><tr><th>记忆内容</th><th>来源</th><th>更新于</th></tr></thead>
          <tbody>{visible.map(item => <tr key={item.memory_id} className={selectedId === item.memory_id ? 'is-selected' : ''}>
            <td><button className="research-memory__open" type="button" aria-label={`查看记忆：${item.content}`} aria-expanded={selectedId === item.memory_id} disabled={busy || Boolean(editor)} onClick={() => { setSelectedId(item.memory_id); setDeleteId(null); setHistoryId(null); setError('') }}><span>{item.content}</span><ArrowUpRightIcon size={14} aria-hidden="true" /></button></td>
            <td>{originLabels[item.origin]}</td><td><time dateTime={item.updated_at}>{date(item.updated_at)}</time></td>
          </tr>)}</tbody>
        </table>
        {!loading && !visible.length && !error ? <div className="research-hub__empty"><BrainIcon size={26} /><h2>{query || origin !== 'all' ? '没有匹配的记忆' : '还没有记忆'}</h2><p>{query || origin !== 'all' ? '换一个关键词，或查看全部来源。' : '手动添加，或在对话中让 Agent 记住。'}</p></div> : null}
      </div>
      {detailOpen ? <aside className="research-memory__detail" aria-label="记忆详情">
        {editor ? editorForm : selected ? <>
          <header><h2>记忆详情</h2><button type="button" aria-label="关闭记忆详情" disabled={busy} onClick={() => setSelectedId(null)}><XIcon size={17} /></button></header>
          <p className="research-memory__content">{selected.content}</p>
          <div className="research-memory__detail-actions"><button type="button" disabled={busy} onClick={() => edit(selected)}><PencilSimpleIcon size={15} />编辑</button><button type="button" disabled={busy} onClick={() => setDeleteId(selected.memory_id)}><TrashIcon size={15} />删除</button></div>
          <dl><div><dt>范围</dt><dd>{taskId ? projectName ?? '当前项目' : '个人记忆'}</dd></div><div><dt>来源</dt><dd>{originLabels[selected.origin]}</dd></div><div><dt>创建于</dt><dd>{date(selected.created_at)}</dd></div><div><dt>更新于</dt><dd>{date(selected.updated_at)}</dd></div></dl>
          {selected.source_quote ? <section className="research-memory__source"><h3><QuotesIcon size={14} />来源原话</h3><blockquote>{selected.source_quote}</blockquote>{selected.source_conversation_id ? <Link to={`/agent?conversation_id=${encodeURIComponent(selected.source_conversation_id)}`}>打开来源对话</Link> : null}</section> : null}
          <button type="button" className="research-memory__history-trigger" aria-expanded={historyId === selected.memory_id} disabled={historyBusy} onClick={() => void showHistory(selected)}><ClockCounterClockwiseIcon size={15} />修改历史<span>{selected.version} 个版本</span></button>
          {historyId === selected.memory_id ? <div className="research-memory__history" aria-label="修改历史">{historyBusy && !history[selected.memory_id] ? <p role="status">正在读取修改历史…</p> : history[selected.memory_id]?.slice().sort((a, b) => b.version - a.version).map(revision => <div key={revision.version}><small>第 {revision.version} 版 · {date(revision.updated_at)} · {originLabels[revision.origin]}</small><p>{revision.content}</p>{revision.source_quote ? <blockquote>{revision.source_quote}</blockquote> : null}</div>)}</div> : null}
          {deleteId === selected.memory_id ? <div className="research-memory__delete" role="group" aria-label="确认删除记忆"><p>{preview ? '删除这条示例记忆？刷新预览可以恢复。' : '删除这条记忆及其修改历史？原始对话仍保留。'}</p><button type="button" disabled={busy} onClick={() => setDeleteId(null)}>取消</button><button type="button" className="research-memory__danger" disabled={busy} onClick={() => void remove(selected)}>确认删除</button></div> : null}
        </> : null}
      </aside> : null}
    </div>
    </section> : null}
  </div>
}
