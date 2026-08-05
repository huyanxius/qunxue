import {
  type FormEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from 'react'

import './KnowledgeExplorer.css'
import type {
  KnowledgeExplorerDetail as KnowledgeExplorerDetailContract,
  KnowledgeExplorerEntry,
  KnowledgeExplorerProps,
  KnowledgeExplorerRelease,
} from './types'
import { KnowledgeEntryDetail } from './KnowledgeEntryDetail'
import { KnowledgeEntryList } from './KnowledgeEntryList'

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '知识服务暂时不可用'
}

export function KnowledgeExplorer({
  dataSource,
  initialKnowledgeId,
  dataNotice,
  homeHref,
  onNavigateHome,
}: KnowledgeExplorerProps) {
  const [query, setQuery] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [release, setRelease] = useState<KnowledgeExplorerRelease>()
  const [entries, setEntries] = useState<readonly KnowledgeExplorerEntry[]>([])
  const [nextCursor, setNextCursor] = useState<string>()
  const [selectedKnowledgeId, setSelectedKnowledgeId] =
    useState(initialKnowledgeId)
  const [detail, setDetail] = useState<KnowledgeExplorerDetailContract>()
  const [listState, setListState] = useState<
    'loading' | 'ready' | 'error'
  >('loading')
  const [detailState, setDetailState] = useState<
    'idle' | 'loading' | 'ready' | 'error'
  >(initialKnowledgeId ? 'loading' : 'idle')
  const [listError, setListError] = useState('')
  const [detailError, setDetailError] = useState('')
  const listRequestId = useRef(0)
  const detailRequestId = useRef(0)

  async function openEntry(knowledgeId: string, releaseId: string) {
    const requestId = ++detailRequestId.current
    setSelectedKnowledgeId(knowledgeId)
    setDetail(undefined)
    setDetailError('')
    setDetailState('loading')

    try {
      const nextDetail = await dataSource.getEntry({
        knowledgeId,
        releaseId,
      })
      if (requestId !== detailRequestId.current) return
      setDetail(nextDetail)
      setDetailState('ready')
    } catch (error) {
      if (requestId !== detailRequestId.current) return
      setDetailError(errorMessage(error))
      setDetailState('error')
    }
  }

  async function loadEntries(input: {
    searchQuery?: string
    cursor?: string
    append?: boolean
  }) {
    if (!release) {
      setListError('尚未取得可浏览的知识发布')
      setListState('error')
      return
    }
    const requestId = ++listRequestId.current
    setListError('')
    setListState('loading')
    if (!input.append) {
      setEntries([])
      setNextCursor(undefined)
    }

    try {
      const page = await dataSource.search({
        releaseId: release.knowledgeReleaseId,
        query: input.searchQuery || undefined,
        cursor: input.cursor,
      })
      if (requestId !== listRequestId.current) return
      if (page.release.knowledgeReleaseId !== release.knowledgeReleaseId) {
        throw new Error('知识服务返回了不同发布版本，请重新进入知识库')
      }

      setRelease(page.release)
      setEntries((current) =>
        input.append ? [...current, ...page.entries] : page.entries,
      )
      setNextCursor(page.nextCursor)
      setListState('ready')
    } catch (error) {
      if (requestId !== listRequestId.current) return
      setListError(errorMessage(error))
      setListState('error')
    }
  }

  useEffect(() => {
    const requestId = ++listRequestId.current
    const initialDetailRequestId = ++detailRequestId.current
    setQuery('')
    setActiveQuery('')
    setRelease(undefined)
    setEntries([])
    setNextCursor(undefined)
    setSelectedKnowledgeId(initialKnowledgeId)
    setDetail(undefined)
    setListError('')
    setDetailError('')
    setListState('loading')
    setDetailState(initialKnowledgeId ? 'loading' : 'idle')

    void (async () => {
      try {
        const currentRelease = await dataSource.currentRelease()
        if (requestId !== listRequestId.current) return
        setRelease(currentRelease)
        const page = await dataSource.search({
          releaseId: currentRelease.knowledgeReleaseId,
        })
        if (requestId !== listRequestId.current) return
        if (
          page.release.knowledgeReleaseId !==
          currentRelease.knowledgeReleaseId
        ) {
          throw new Error('知识服务返回了不同发布版本，请重新进入知识库')
        }

        setEntries(page.entries)
        setNextCursor(page.nextCursor)
        setListState('ready')

        if (!initialKnowledgeId) return
        try {
          const initialDetail = await dataSource.getEntry({
            knowledgeId: initialKnowledgeId,
            releaseId: page.release.knowledgeReleaseId,
          })
          if (initialDetailRequestId !== detailRequestId.current) return
          setDetail(initialDetail)
          setDetailState('ready')
        } catch (error) {
          if (initialDetailRequestId !== detailRequestId.current) return
          setDetailError(errorMessage(error))
          setDetailState('error')
        }
      } catch (error) {
        if (requestId !== listRequestId.current) return
        setListError(errorMessage(error))
        setListState('error')
        if (initialKnowledgeId) {
          setDetailError(errorMessage(error))
          setDetailState('error')
        }
      }
    })()

    return () => {
      listRequestId.current += 1
      detailRequestId.current += 1
    }
  }, [dataSource, initialKnowledgeId])

  function resetDetail() {
    detailRequestId.current += 1
    setSelectedKnowledgeId(undefined)
    setDetail(undefined)
    setDetailError('')
    setDetailState('idle')
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextQuery = query.trim()
    setActiveQuery(nextQuery)
    resetDetail()
    void loadEntries({ searchQuery: nextQuery })
  }

  function clearSearch() {
    setQuery('')
    setActiveQuery('')
    resetDetail()
    void loadEntries({})
  }

  return (
    <section
      className="knowledge-explorer"
      aria-labelledby="knowledge-explorer-title"
    >
      <header className="knowledge-explorer__header">
        <div>
          <p className="knowledge-explorer__eyebrow">版本化知识浏览</p>
          <h1 id="knowledge-explorer-title">可视化知识库</h1>
          <p>
            这里只呈现发布数据中的来源、审核状态与显式关系，不从文本相似度推断学术关系。
          </p>
        </div>
        {homeHref ? (
          <a
            href={homeHref}
            onClick={(event: MouseEvent<HTMLAnchorElement>) => {
              if (!onNavigateHome) return
              event.preventDefault()
              onNavigateHome()
            }}
          >
            返回首页
          </a>
        ) : null}
      </header>

      {dataNotice ? (
        <aside className="knowledge-explorer__notice" role="note">
          <strong>演示数据</strong>
          <span>{dataNotice}</span>
        </aside>
      ) : null}

      <form
        className="knowledge-explorer__search"
        aria-label="搜索知识库"
        onSubmit={submitSearch}
      >
        <label htmlFor="knowledge-query">关键词</label>
        <input
          id="knowledge-query"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="输入理论、概念或方法"
        />
        <button
          type="submit"
          disabled={listState === 'loading' || !release}
        >
          搜索
        </button>
        {query ? (
          <button
            className="knowledge-explorer__plain-action"
            type="button"
            disabled={listState === 'loading'}
            onClick={clearSearch}
          >
            清除
          </button>
        ) : null}
      </form>

      {release ? (
        <p className="knowledge-explorer__release">
          发布 {release.knowledgeReleaseId} · {release.level} · 内容校验{' '}
          <code>{release.contentHash}</code>
        </p>
      ) : null}

      <div className="knowledge-explorer__columns">
        <KnowledgeEntryList
          entries={entries}
          state={listState}
          error={listError}
          selectedKnowledgeId={selectedKnowledgeId}
          hasNextPage={Boolean(nextCursor)}
          onSelect={(knowledgeId) => {
            if (!release) return
            void openEntry(knowledgeId, release.knowledgeReleaseId)
          }}
          onLoadMore={() => {
            if (!nextCursor) return
            void loadEntries({
              searchQuery: activeQuery,
              cursor: nextCursor,
              append: true,
            })
          }}
        />

        <article
          className="knowledge-explorer__detail"
          aria-live="polite"
          aria-busy={detailState === 'loading'}
        >
          {detailState === 'idle' ? <p>选择一个条目查看详情。</p> : null}
          {detailState === 'loading' ? <p role="status">正在读取详情……</p> : null}
          {detailState === 'error' ? (
            <p className="knowledge-explorer__error" role="alert">
              {detailError}
            </p>
          ) : null}
          {detailState === 'ready' && detail ? (
            <KnowledgeEntryDetail
              detail={detail}
              onSelectRelated={(knowledgeId) => {
                if (!release) return
                void openEntry(knowledgeId, release.knowledgeReleaseId)
              }}
            />
          ) : null}
        </article>
      </div>
    </section>
  )
}
