import { FolderOpenIcon, PlusIcon } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { readResearchTaskNavigationViaApi } from '../../api/researchWorkspace'
import { listMyResearchViaApi, type MyResearchItem } from '../../modules/account'
import { ResearchMaterialsPanel } from '../../modules/research-materials'
import { ResearchAgentConversationPage } from '../agent/ResearchAgentConversationPage'
import { PageContent, PageShell, PageTitle } from '../ui/PageShell'
import './research-materials-page.css'

type ResearchNavigation = Awaited<ReturnType<typeof readResearchTaskNavigationViaApi>>

/**
 * 材料始终属于一个 ResearchTask；页面只负责让用户找到该研究的材料面板。
 * 不在这里复制上传、解析或分析逻辑，避免出现第二套材料系统。
 */
export function ResearchMaterialsPage({ userId = null }: { userId?: string | null }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const selectedTaskId = searchParams.get('task_id')
  const [research, setResearch] = useState<MyResearchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [navigation, setNavigation] = useState<ResearchNavigation | null>(null)
  const [navigationLoading, setNavigationLoading] = useState(false)

  useEffect(() => {
    let active = true
    void listMyResearchViaApi()
      .then((items) => {
        if (active) setResearch(items)
      })
      .catch(() => {
        if (active) setError('研究列表暂时无法加载，请稍后重试。')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedTaskId) {
      setNavigation(null)
      return undefined
    }
    let active = true
    setNavigationLoading(true)
    setNavigation(null)
    void readResearchTaskNavigationViaApi(selectedTaskId)
      .then((value) => {
        if (active) setNavigation(value)
      })
      .catch(() => {
        if (active) setError('这项研究的状态暂时无法恢复，请稍后重试。')
      })
      .finally(() => {
        if (active) setNavigationLoading(false)
      })
    return () => {
      active = false
    }
  }, [selectedTaskId])

  const selectedResearch = research.find((item) => item.taskId === selectedTaskId) ?? null

  return (
    <PageShell>
      <PageContent>
        <PageTitle
          eyebrow="研究材料"
          title="导入与管理材料"
          lede="把论文、访谈转录和田野记录放进对应研究，供 Agent 检索、引用与后续分析。"
        />
        {loading ? <p className="research-materials-page__status" role="status">正在读取你的研究</p> : null}
        {error ? <p className="research-materials-page__status is-error" role="alert">{error}</p> : null}

        {!loading && !error && !research.length ? (
          <section className="research-materials-page__empty" aria-label="还没有研究">
            <FolderOpenIcon size={25} aria-hidden="true" />
            <h2>先建立一项研究</h2>
            <p>研究材料需要绑定到具体研究，建立后就能在这里持续导入和管理。</p>
            <Link className="research-materials-page__primary" to="/research/new"><PlusIcon size={16} />新建研究</Link>
          </section>
        ) : null}

        {!loading && !error && research.length && !selectedResearch ? (
          <section className="research-materials-page__chooser" aria-label="选择研究">
            <header>
              <h2>选择一项研究</h2>
              <p>材料只会在所选研究的 Agent 对话和分析中使用。</p>
            </header>
            <div className="research-materials-page__research-list">
              {research.map((item) => (
                <button
                  type="button"
                  key={item.taskId}
                  onClick={() => navigate(`/research/materials?task_id=${encodeURIComponent(item.taskId)}`)}
                >
                  <strong>{item.phenomenonSummary || '未命名研究'}</strong>
                  <span>{item.stageLabel || '研究进行中'} · {item.nextActionLabel || '打开材料'}</span>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {selectedResearch ? (
          <section className="research-materials-workbench" aria-label="研究材料工作台" role="region">
            <header className="research-materials-workbench__header">
              <div>
                <Link to="/research/materials">返回研究选择</Link>
                <h2>{selectedResearch.phenomenonSummary || '未命名研究'}</h2>
                <p>材料、原文定位、分析记录和 Agent 都属于这项研究。</p>
              </div>
              <label>
                <span>当前研究</span>
                <select
                  aria-label="当前研究"
                  value={selectedResearch.taskId}
                  onChange={(event) => navigate(`/research/materials?task_id=${encodeURIComponent(event.target.value)}`)}
                >
                  {research.map((item) => <option key={item.taskId} value={item.taskId}>{item.phenomenonSummary || '未命名研究'}</option>)}
                </select>
              </label>
            </header>
            {navigationLoading ? <p className="research-materials-page__status" role="status">正在恢复研究上下文</p> : null}
            {!navigationLoading && navigation ? (
              <div className="research-materials-workbench__body">
                <ResearchMaterialsPanel taskId={selectedResearch.taskId} presentation="workspace" />
                <ResearchAgentConversationPage
                  embedded
                  userId={userId}
                  conversationId={navigation.conversation_id}
                  knowledgeReleaseId={navigation.knowledge_release_id}
                  workspace="research"
                  taskId={selectedResearch.taskId}
                  theoryPlanId={navigation.current_theory_plan_id}
                />
              </div>
            ) : null}
            {!navigationLoading && !navigation && !error ? <p className="research-materials-page__status is-error" role="alert">研究上下文暂时无法打开。</p> : null}
            {navigation ? <Link className="research-materials-workbench__resume" to={navigation.resume_path}>返回这项研究</Link> : null}
          </section>
        ) : null}
      </PageContent>
    </PageShell>
  )
}
