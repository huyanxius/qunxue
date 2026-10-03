import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { useAppLocale } from '../../i18n/AppLocaleProvider'

export function ProjectCreatePopover({ anchor, title, saving, error, onTitleChange, onCancel, onSubmit }: {
  anchor: HTMLElement
  title: string
  saving: boolean
  error: string | null
  onTitleChange: (title: string) => void
  onCancel: () => void
  onSubmit: (event: FormEvent) => void
}) {
  const { text } = useAppLocale()
  const popoverRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: 0, top: 0 })
  useLayoutEffect(() => {
    const place = () => {
      const target = anchor
      if (!target) return
      const rect = target.getBoundingClientRect()
      const viewport = window.innerWidth <= 760 ? window.visualViewport : null
      const left = viewport?.offsetLeft ?? 0, top = viewport?.offsetTop ?? 0
      const width = viewport?.width ?? window.innerWidth, height = viewport?.height ?? window.innerHeight
      setPosition({
        left: Math.max(left + 8, Math.min(rect.right + 8, left + width - (popoverRef.current?.offsetWidth || 244) - 8)),
        top: Math.max(top + 8, Math.min(rect.top, top + height - (popoverRef.current?.offsetHeight || 180) - 8)),
      })
    }
    place()
    const viewport = window.visualViewport
    viewport?.addEventListener('resize', place)
    viewport?.addEventListener('scroll', place)
    window.addEventListener('resize', place)
    return () => { viewport?.removeEventListener('resize', place); viewport?.removeEventListener('scroll', place); window.removeEventListener('resize', place) }
  }, [anchor, error])
  useEffect(() => {
    popoverRef.current?.querySelector('input')?.focus()
  }, [])
  useEffect(() => {
    const dismissOutside = (event: PointerEvent) => {
      if (!saving && !popoverRef.current?.contains(event.target as Node) && !anchor.contains(event.target as Node)) onCancel()
    }
    const dismissOnResize = () => { if (!saving && window.innerWidth > 760) onCancel() }
    document.addEventListener('pointerdown', dismissOutside)
    window.addEventListener('resize', dismissOnResize)
    return () => {
      document.removeEventListener('pointerdown', dismissOutside)
      window.removeEventListener('resize', dismissOnResize)
    }
  }, [anchor, onCancel, saving])
  return createPortal(<div ref={popoverRef} className="agent-conversation-history__popover is-rename" style={position}>
    <form role="dialog" aria-label={text('新建项目', 'New project')} onSubmit={onSubmit}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !saving) { event.preventDefault(); event.stopPropagation(); onCancel(); anchor.focus() }
      }}>
      <strong>{text('新建项目', 'New project')}</strong>
      <input aria-label={text('项目名称', 'Project name')} value={title} maxLength={300} disabled={saving}
        placeholder={text('项目名称', 'Project name')} onChange={(event) => onTitleChange(event.target.value)} />
      <div>
        <button type="button" disabled={saving} onClick={() => { onCancel(); anchor.focus() }}>{text('取消', 'Cancel')}</button>
        <button className="is-primary" type="submit" disabled={saving || !title.trim()}>{saving ? text('创建中…', 'Creating…') : text('创建', 'Create')}</button>
      </div>
    </form>
    {error ? <p role="alert">{error}</p> : null}
  </div>, (window.innerWidth <= 760 ? anchor.closest('.desktop-rail') : null) ?? anchor.closest('.app-frame') ?? document.body)
}
