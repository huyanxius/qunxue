import { DotsThreeIcon, TrashIcon } from '@phosphor-icons/react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useAppLocale } from '../i18n/AppLocaleProvider'

export function ProjectActionsMenu({ taskId, title, onDelete }: {
  taskId: string
  title: string
  onDelete: (taskId: string) => Promise<void>
}) {
  const { text } = useAppLocale()
  const anchor = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const [mode, setMode] = useState<'menu' | 'delete' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [position, setPosition] = useState({ left: 0, top: 0 })
  useLayoutEffect(() => {
    if (!mode || !anchor.current) return
    const rect = anchor.current.getBoundingClientRect()
    setPosition({
      left: Math.max(8, Math.min(rect.right + 8, window.innerWidth - (panel.current?.offsetWidth ?? 240) - 8)),
      top: Math.max(8, Math.min(rect.top, window.innerHeight - (panel.current?.offsetHeight ?? 180) - 8)),
    })
  }, [mode, error])
  useEffect(() => {
    if (!mode) return
    panel.current?.querySelector('button')?.focus()
    const outside = (event: PointerEvent) => {
      if (!busy && !panel.current?.contains(event.target as Node) && !anchor.current?.contains(event.target as Node)) setMode(null)
    }
    const dismiss = () => { if (!busy) setMode(null) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) { setMode(null); anchor.current?.focus() } }
    const scroll = (event: Event) => { if (!panel.current?.contains(event.target as Node)) dismiss() }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    window.addEventListener('resize', dismiss)
    window.addEventListener('scroll', scroll, true)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
      window.removeEventListener('resize', dismiss)
      window.removeEventListener('scroll', scroll, true)
    }
  }, [mode, busy])
  async function remove() {
    if (busy) return
    setBusy(true); setError(null)
    try { await onDelete(taskId); setMode(null) }
    catch (cause) { setError(cause instanceof Error ? cause.message : text('项目删除失败', 'Project could not be deleted')) }
    finally { setBusy(false) }
  }
  return <>
    <button ref={anchor} type="button" className="project-conversation-list__actions"
      aria-label={text(`${title}的项目操作`, `Project actions for ${title}`)} aria-haspopup="menu" aria-expanded={Boolean(mode)}
      onClick={() => { if (!busy) { setError(null); setMode(mode ? null : 'menu') } }}>
      <DotsThreeIcon size={18} weight="bold" aria-hidden="true" />
    </button>
    {mode ? createPortal(<div ref={panel} className={`agent-conversation-history__popover is-${mode}`} style={position}>
      {mode === 'menu' ? <div role="menu" aria-label={text('项目操作', 'Project actions')}>
        <button type="button" role="menuitem" className="is-danger" onClick={() => setMode('delete')}><TrashIcon size={14} />{text('删除项目', 'Delete project')}</button>
      </div> : <div role="dialog" aria-label={text('删除项目', 'Delete project')}>
        <strong className="project-conversation-list__delete-title" title={title}>{text(`删除“${title}”？`, `Delete “${title}”?`)}</strong>
        <p className="project-conversation-list__delete-description">{text('项目材料和研究内容将被删除，所属对话会保留为独立对话。', 'Project materials and research will be deleted. Conversations will remain as independent conversations.')}</p>
        <div>
          <button type="button" disabled={busy} onClick={() => { setMode(null); anchor.current?.focus() }}>{text('取消', 'Cancel')}</button>
          <button type="button" className="is-danger" aria-label={text('确认删除项目', 'Confirm delete project')} disabled={busy} onClick={() => { void remove() }}>{busy ? text('删除中…', 'Deleting…') : text('删除', 'Delete')}</button>
        </div>
      </div>}
      {error ? <p role="alert">{error}</p> : null}
    </div>, anchor.current?.closest('.app-frame') ?? document.body) : null}
  </>
}
