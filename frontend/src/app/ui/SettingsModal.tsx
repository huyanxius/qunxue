import { useEffect, useRef, type ReactNode } from 'react'
import './settings-modal.css'

export function SettingsModal({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      dialog?.close()
      document.body.style.overflow = overflow
    }
  }, [])

  return (
    <dialog ref={ref} className="settings-modal" aria-label="账户设置"
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return
        const rect = event.currentTarget.getBoundingClientRect()
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose()
      }}>
      <button type="button" className="settings-modal__close" aria-label="关闭账户设置" onClick={onClose}>×</button>
      {children}
    </dialog>
  )
}
