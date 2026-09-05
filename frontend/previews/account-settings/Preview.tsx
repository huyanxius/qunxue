import { useEffect, useRef, useState } from 'react'
import {
  XIcon,
  PlusIcon,
  ChatsCircleIcon,
  BooksIcon,
  ArrowRightIcon,
} from '@phosphor-icons/react'
import { AccountSettingsPage } from '../../src/modules/account/AccountSettingsPage'
import { AppLocaleProvider } from '../../src/i18n/AppLocaleProvider'
import { previewApi } from './fixture'
import '../../src/styles/tokens.css'
import '../../src/styles/app.css'
import './style.css'

export function Preview() {
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(true)
  const [notice, setNotice] = useState('')
  const [name, setName] = useState('胡言')
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal()
    if (!open) {
      dialog.current?.close()
      trigger.current?.focus()
    }
  }, [open])
  return (
    <div className="app-frame account-preview-frame">
      <div className="workspace">
        <aside className="workspace-rail">
          <div className="brand">
            群学致知<span>让研究逐步成形</span>
          </div>
          <div className="background-action">
            <PlusIcon />
            开启研究
          </div>
          <p>
            <ChatsCircleIcon />
            研究
          </p>
          <p>
            <BooksIcon />
            材料库
          </p>
          <div className="recent">
            <small>最近研究</small>
            <p>青年社区参与的动力机制</p>
            <p>城市空间与日常生活</p>
          </div>
          <button
            ref={trigger}
            onClick={() => setOpen(true)}
            className="open-settings"
          >
            <span className="preview-avatar">
              {Array.from(name.trim())[0] ?? '研'}
            </span>
            {name}
            <span>设置</span>
          </button>
        </aside>
        <main className="workspace-main">
          <small>我的研究</small>
          <h1>从一个问题开始。</h1>
          <div className="composer">
            描述你正在思考的社会现象…
            <span>
              <PlusIcon />
              <ArrowRightIcon />
            </span>
          </div>
          {notice && <p role="status">{notice}</p>}
        </main>
      </div>
      <dialog
        ref={dialog}
        className="settings-modal"
        aria-label="账户设置预览"
        onCancel={(event) => {
          event.preventDefault()
          if (dialog.current?.querySelector('[role="dialog"]')) return
          setOpen(false)
        }}
      >
        <button
          className="close-settings"
          aria-label="关闭设置"
          onClick={() => setOpen(false)}
        >
          <XIcon size={19} />
        </button>
        <AppLocaleProvider>
          <AccountSettingsPage
            api={previewApi}
            onProfileUpdated={(account) =>
              setName(account.displayName ?? '研究者')
            }
            onLogout={() => {
              setOpen(false)
              setNotice('已演示退出登录；真实账户未改变。')
            }}
            onAccountDeactivated={() => {
              setOpen(false)
              setNotice('已演示停用；真实账户未改变。')
            }}
            onAccountDeleted={() => {
              setOpen(false)
              setNotice('已演示删除；真实账户未改变。')
            }}
          />
        </AppLocaleProvider>
        <div className="preview-note">
          Mock · 真实接口契约 · 示例数据
        </div>
      </dialog>
    </div>
  )
}
