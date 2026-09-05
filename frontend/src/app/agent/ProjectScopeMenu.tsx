import { CaretDownIcon, CheckIcon, FolderIcon, ChatCircleIcon } from '@phosphor-icons/react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useAppLocale } from '../../i18n/AppLocaleProvider'
import type { ResearchProject } from '../../modules/research-projects'

export function ProjectScopeMenu({ projects, taskId, disabled, onChange }: {
  projects: ResearchProject[]
  taskId: string | null
  disabled: boolean
  onChange: (taskId: string) => void
}) {
  const { text } = useAppLocale()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const entryRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const title = projects.find((project) => project.task_id === taskId)?.project_title
    ?? (taskId ? text('当前项目', 'Current project') : text('独立对话', 'Independent conversation'))
  const options = [{ id: '', title: text('独立对话', 'Independent conversation') },
    ...projects.filter((project) => project.status !== 'archived' || project.task_id === taskId)
      .map((project) => ({ id: project.task_id, title: project.project_title }))]
  if (taskId && !options.some((option) => option.id === taskId)) options.push({ id: taskId, title })
  const filteredOptions = options.filter((option) => option.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
  useLayoutEffect(() => {
    if (!open) return
    const left = entryRef.current?.getBoundingClientRect().left ?? 0
    const width = menuRef.current?.offsetWidth ?? 240
    setOffset(Math.min(0, window.innerWidth - left - width - 12))
    menuRef.current?.querySelector('input')?.focus()
  }, [open])
  useEffect(() => {
    if (!open) return
    const dismiss = (event: PointerEvent) => {
      if (!entryRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [open])
  return <div ref={entryRef} className="research-agent-composer__project-entry" onKeyDown={(event) => {
    if (event.key === 'Enter' && event.target instanceof HTMLInputElement) { event.preventDefault(); return }
    if (event.key === 'Escape') { setOpen(false); triggerRef.current?.focus(); event.stopPropagation() }
    if (event.key === 'Tab') setOpen(false)
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    if (!open) { setQuery(''); setOpen(true); return }
    const items = [...menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? []]
    if (!items.length) return
    const current = items.indexOf(document.activeElement as HTMLElement)
    items[(current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
  }}>
    <button ref={triggerRef} type="button" className="research-agent-composer__mode-button research-agent-composer__project-button"
      aria-label={text('对话所属项目', 'Conversation project')} title={title} aria-haspopup="dialog" aria-expanded={open}
      disabled={disabled} onClick={() => { setQuery(''); setOpen((current) => !current) }}>
      {taskId ? <FolderIcon size={15} /> : <ChatCircleIcon size={15} />}<span>{title}</span><CaretDownIcon size={11} />
    </button>
    {open && !disabled ? <div ref={menuRef} role="dialog" aria-label={text('切换项目', 'Switch project')}
      className="research-agent-composer__material-menu research-agent-composer__project-menu" style={{ left: offset }}>
      <input type="search" aria-label={text('搜索项目', 'Search projects')} placeholder={text('搜索项目', 'Search projects')}
        value={query} onChange={(event) => setQuery(event.target.value)} />
      <div role="menu" aria-label={text('选择项目', 'Choose project')} className="research-agent-composer__project-options">
      {filteredOptions.map((option) => <button key={option.id} type="button" role="menuitemradio" aria-checked={option.id === (taskId ?? '')}
        onClick={() => { setOpen(false); if (option.id !== (taskId ?? '')) onChange(option.id); else triggerRef.current?.focus() }}>
        {option.id ? <FolderIcon size={16} /> : <ChatCircleIcon size={16} />}<span>{option.title}</span>
        {option.id === (taskId ?? '') ? <CheckIcon size={14} /> : null}
      </button>)}
      {!filteredOptions.length ? <p>{text('没有匹配的项目', 'No matching projects')}</p> : null}
      </div>
    </div> : null}
  </div>
}
