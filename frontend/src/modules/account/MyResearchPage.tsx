import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DotsThreeIcon, FlaskIcon, TrashIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'

import { deleteMyResearchViaApi, listMyResearchViaApi } from './accountApi'
import type { MyResearchItem } from './types'
import './my-research.css'

const researchQueryKey = ['account', 'research-tasks'] as const
const dialogFocusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function formattedDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function MyResearchPage() {
  const queryClient = useQueryClient()
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const deleteDialogRef = useRef<HTMLElement | null>(null)
  const deleteCancelRef = useRef<HTMLButtonElement | null>(null)
  const deleteTriggerRef = useRef<HTMLButtonElement | null>(null)
  const research = useQuery({
    queryKey: researchQueryKey,
    queryFn: listMyResearchViaApi,
    retry: false,
    refetchOnMount: 'always',
  })
  const deletion = useMutation({
    mutationFn: deleteMyResearchViaApi,
    onSuccess: (_data, taskId) => {
      queryClient.setQueryData<MyResearchItem[]>(
        researchQueryKey,
        (items = []) => items.filter((item) => item.taskId !== taskId),
      )
      setPendingDeleteId(null)
      setOpenMenuId(null)
    },
  })

  useEffect(() => {
    if (!pendingDeleteId) return undefined

    deleteCancelRef.current?.focus()
    function handleDialogKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setPendingDeleteId(null)
        return
      }
      if (event.key !== 'Tab') return

      const dialog = deleteDialogRef.current
      if (!dialog) return
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(dialogFocusableSelector),
      )
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleDialogKeyDown)
    return () => {
      document.removeEventListener('keydown', handleDialogKeyDown)
      if (deleteTriggerRef.current && document.contains(deleteTriggerRef.current)) {
        deleteTriggerRef.current.focus()
      }
    }
  }, [pendingDeleteId])

  if (research.isPending) {
    return (
      <div className="research-library-state research-library-state--loading" role="status">
        <span />
        <span />
        <span />
        <p>正在读取研究任务</p>
      </div>
    )
  }

  if (research.isError) {
    return (
      <div className="research-library-state" role="alert">
        <h2>暂时无法读取研究任务</h2>
        <p>研究内容仍然保留。重新连接后即可继续。</p>
        <button
          type="button"
          disabled={research.isFetching}
          onClick={() => research.refetch()}
        >
          {research.isFetching ? '正在重试…' : '重试'}
        </button>
      </div>
    )
  }

  if (research.data.length === 0) {
    return (
      <div className="research-library-state research-library-state--empty">
        <span className="research-library-state__icon" aria-hidden="true">
          <FlaskIcon size={21} weight="regular" />
        </span>
        <h2>还没有研究任务</h2>
        <p>从一个具体的社会现象开始，研究过程会持续保存在这里。</p>
        <a href="/research/new">新建研究</a>
      </div>
    )
  }

  const pendingDelete = research.data.find((item) => item.taskId === pendingDeleteId)

  return (
    <>
      <div className="research-table" role="table" aria-label="研究任务">
        <div className="research-table__header" role="row">
          <span role="columnheader">研究问题</span>
          <span role="columnheader">阶段</span>
          <span role="columnheader">下一步</span>
          <span role="columnheader">更新时间</span>
          <span role="columnheader" aria-label="操作" />
        </div>
        <div className="research-table__body" role="rowgroup">
          {research.data.map((item) => {
            const menuOpen = openMenuId === item.taskId
            return (
              <article
                className="research-row"
                role="row"
                aria-label={item.phenomenonSummary}
                key={item.taskId}
              >
                <div className="research-row__question" role="cell">
                  <a href={item.entryPath} title={item.phenomenonSummary}>
                    {item.phenomenonSummary}
                  </a>
                  <span>{item.adoptedTheoryCount} 个理论</span>
                </div>
                <div role="cell">
                  <span className="research-row__stage">{item.stageLabel}</span>
                </div>
                <span className="research-row__next" role="cell">
                  {item.blocker ? (
                    <>
                      <span>{item.blocker.message}</span>{' '}
                      {item.retry
                        ? <a href={item.retry.method === 'GET' ? item.retry.href : item.entryPath}>{item.retry.label}</a>
                        : <span>{item.nextActionLabel}</span>}
                    </>
                  ) : <>下一步：{item.nextActionLabel}</>}
                </span>
                <time role="cell" dateTime={item.updatedAt}>
                  {formattedDate(item.updatedAt)}
                </time>
                <div className="research-row__actions" role="cell">
                  <button
                    type="button"
                    aria-label={`打开研究操作：${item.phenomenonSummary}`}
                    aria-expanded={menuOpen}
                    onClick={(event) => {
                      deleteTriggerRef.current = event.currentTarget
                      setOpenMenuId(menuOpen ? null : item.taskId)
                    }}
                  >
                    <DotsThreeIcon size={19} weight="bold" aria-hidden="true" />
                  </button>
                  {menuOpen ? (
                    <div className="research-row__menu" role="menu">
                      <a role="menuitem" href={item.entryPath}>继续研究</a>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setPendingDeleteId(item.taskId)
                          setOpenMenuId(null)
                        }}
                      >
                        <TrashIcon size={15} weight="regular" aria-hidden="true" />
                        删除研究
                      </button>
                    </div>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>
      </div>

      {pendingDelete ? (
        <div className="delete-dialog-backdrop">
          <section
            className="delete-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-research-title"
            aria-describedby="delete-research-description"
            ref={deleteDialogRef}
            tabIndex={-1}
          >
            <span className="delete-dialog__icon" aria-hidden="true">
              <TrashIcon size={19} weight="regular" />
            </span>
            <h2 id="delete-research-title">永久删除这项研究？</h2>
            <p className="delete-dialog__question">{pendingDelete.phenomenonSummary}</p>
            <p id="delete-research-description">删除后，任务及其派生内容无法恢复。</p>
            {deletion.isError ? (
              <p className="delete-dialog__error" role="alert">删除失败，研究内容仍然保留。</p>
            ) : null}
            <div className="delete-dialog__actions">
              <button
                type="button"
                disabled={deletion.isPending}
                ref={deleteCancelRef}
                onClick={() => setPendingDeleteId(null)}
              >
                取消
              </button>
              <button
                className="delete-dialog__confirm"
                type="button"
                disabled={deletion.isPending}
                onClick={() => deletion.mutate(pendingDelete.taskId)}
              >
                {deletion.isPending ? '正在删除…' : '确认永久删除'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
