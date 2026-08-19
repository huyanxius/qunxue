import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export function SupportCenter({ accountEmail }: { accountEmail?: string | null }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!open) return undefined
    const previousFocus = document.activeElement as HTMLElement | null
    const restoreTarget = previousFocus ?? triggerRef.current
    const appFrame = triggerRef.current?.closest<HTMLElement>('.app-frame') ?? null
    const previousAriaHidden = appFrame?.getAttribute('aria-hidden')
    appFrame?.setAttribute('inert', '')
    appFrame?.setAttribute('aria-hidden', 'true')
    closeRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => !element.hidden)
      if (focusable.length === 0) return
      const first = focusable[0]!
      const last = focusable[focusable.length - 1]!
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      appFrame?.removeAttribute('inert')
      if (previousAriaHidden === null) appFrame?.removeAttribute('aria-hidden')
      else appFrame?.setAttribute('aria-hidden', previousAriaHidden)
      restoreTarget?.focus()
    }
  }, [open])

  return (
    <>
      <button
        ref={triggerRef}
        className="support-trigger"
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        帮助与边界
      </button>
      {open ? createPortal((
        <div className="support-dialog-backdrop" role="presentation">
          <section
            ref={dialogRef}
            className="support-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="support-dialog-title"
          >
            <header className="support-dialog__header">
              <div>
                <p className="eyebrow">HELP / SCOPE</p>
                <h2 id="support-dialog-title">帮助与产品边界</h2>
              </div>
              <button
                ref={closeRef}
                className="support-dialog__close"
                type="button"
                aria-label="关闭帮助"
                onClick={() => setOpen(false)}
              >
                关闭
              </button>
            </header>

            <div className="support-dialog__body">
              <section aria-labelledby="support-available-title">
                <h3 id="support-available-title">现在可以做什么</h3>
                <p>知识浏览与现象确认可以帮助你查看来源、整理输入并保留可恢复的研究任务。</p>
                <p>结构化研究从现象输入开始；确认前的候选不会被当成你的结论。</p>
              </section>
              <section aria-labelledby="support-unavailable-title">
                <h3 id="support-unavailable-title">仍在建设的部分</h3>
                <p>理论匹配与研究框架尚未开放，也不会用示例结果填充这些阶段。</p>
              </section>
              <section aria-labelledby="support-trust-title">
                <h3 id="support-trust-title">数据与运行提示</h3>
                <p>当前账号：{accountEmail ?? '未登录'}。研究删除后无法恢复，请在确认前保留必要记录。</p>
                <p>标注为预览或 mock 的对话只用于体验界面；只有真实 provider 运行记录、引用链和发布版本同时存在时，才可视为 Agent 结果。</p>
              </section>
              <nav className="support-dialog__links" aria-label="帮助快捷入口">
                <a href="/research/new">开始一项研究</a>
                <a href="/knowledge">浏览知识来源</a>
                <a href="/my">查看研究记录</a>
              </nav>
            </div>
          </section>
        </div>
      ), document.body) : null}
    </>
  )
}
