import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { Fragment, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as researchApi from '../../api/researchWorkspace'
import * as researchAnalysisApi from '../../modules/research-materials'
import type { AgentConversation } from '../../modules/research-agent'
import { ResearchDocumentWorkbench } from './ResearchDocumentWorkbench'

vi.mock('../../api/client', () => ({ apiClient: {} }))
vi.mock('./ResearchMapCanvas', () => ({
  ResearchMapCanvas: ({ projection, expandedNodeContent, onSelectNode }: {
    projection: { nodes: Array<{ id: string; kind: string; title: string }> }
    expandedNodeContent: Readonly<Record<string, ReactNode>>
    onSelectNode: (node: { id: string; kind: string; title: string }) => void
  }) => (
    <section aria-label="研究论证地图">
      {projection.nodes.map((node) => <button type="button" key={node.id} aria-label={`${node.kind === 'document' ? '研究章节' : '研究节点'}：${node.title}`} onClick={() => onSelectNode(node)}>{node.title}</button>)}
      {Object.entries(expandedNodeContent).map(([id, content]) => <Fragment key={id}>{content}</Fragment>)}
    </section>
  ),
}))
vi.mock('../agent/ResearchAgentConversationPage', () => ({
  ResearchAgentConversationPage: ({ taskId, workspace, onTurnCompleted }: { taskId: string | null; workspace: string; onTurnCompleted?: () => void }) => (
    <aside aria-label="研究 Agent 对话栏" data-task-id={taskId ?? ''} data-workspace={workspace}>
      <button type="button" onClick={onTurnCompleted}>完成 Agent 回合</button>
    </aside>
  ),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('ResearchDocumentWorkbench', () => {
  it('shows a local proposal diff and blocks acceptance when its baseline is stale', async () => {
    const document = {
      document_id: 'document-1',
      task_id: 'task-1',
      theory_plan_id: 'plan-1',
      knowledge_release_id: 'release-1',
      revision_id: 'revision-3',
      version: 3,
      title: '迁移与照护',
      sections: [{
        section_id: 'research_question',
        key: 'research_question',
        title: '研究问题',
        content: '迁移后的照护主要由**祖辈**承担。',
        status: 'reviewed',
        evidence_refs: [],
        citation_refs: [],
      }],
      status: 'draft',
      change_summary: '用户直接编辑正文',
      actor: 'user',
      restored_from_version: null,
      created_at: '2026-08-31T10:00:00Z',
      confirmed_at: null,
      research_analysis: null,
      formatting: {
        template_id: 'chinese-social-science',
        csl_style_id: 'china-national-standard-gb-t-7714-2015-author-date',
        locale: 'zh-CN',
      },
    }
    const proposal = {
      proposal_id: 'proposal-1',
      kind: 'revise',
      status: 'pending',
      user_id: 'user-1',
      conversation_id: 'conversation-1',
      agent_run_id: 'run-1',
      model_provider: 'provider',
      model_name: 'model',
      task_id: 'task-1',
      theory_plan_id: 'plan-1',
      knowledge_release_id: 'release-1',
      title: '迁移与照护',
      proposed_sections: [{
        ...document.sections[0],
        content: '迁移后的照护主要由**社区**承担，并依赖邻里互助。',
      }],
      rationale: '把笼统主体改成分析中确认的社区照护网络。',
      document_id: 'document-1',
      base_document_version: 2,
      target_section_id: 'research_question',
      decision_reason: null,
      result_document_id: null,
      result_document_version: null,
      requires_user_approval: true,
      research_analysis: null,
      created_at: '2026-08-31T09:00:00Z',
      decided_at: null,
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({
      data: {
        task_id: 'task-1',
        allowed_actions: [],
        current_match_run_id: null,
        current_theory_plan_id: 'plan-1',
        current_framework_id: null,
        knowledge_release_id: 'release-1',
        phenomenon_summary: { phenomenon: '迁移如何改变照护？' },
        resume_path: '/research/task-1/match',
      },
    } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [document] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [proposal] } } as never)
    vi.spyOn(researchApi, 'listResearchDocumentVersions').mockResolvedValue({ data: { items: [document] } } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：研究问题' }))
    expect(await screen.findByText('建议基线 v2')).toBeVisible()
    expect(screen.getByText('当前文稿已是 v3，建议基线发生冲突。')).toBeVisible()
    expect(screen.getByRole('button', { name: '接受局部修改' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '按当前版本重新比较' }))
    const diff = screen.getByLabelText('研究问题局部差异')
    expect(within(diff).getByText('祖辈').tagName).toBe('DEL')
    expect(within(diff).getByText('社区').tagName).toBe('INS')
    expect(within(diff).getByText('，并依赖邻里互助').tagName).toBe('INS')
  })

  it('pins template and CSL selections by creating a new document version', async () => {
    const document = {
      document_id: 'document-1', task_id: 'task-1', theory_plan_id: 'plan-1', knowledge_release_id: 'release-1',
      revision_id: 'revision-1', version: 1, title: '跨语言研究', status: 'draft', change_summary: '创建文稿', actor: 'user',
      restored_from_version: null, created_at: '2026-08-31T10:00:00Z', confirmed_at: null,
      research_analysis: { schema_version: 'research-analysis-v1', task_id: 'task-1', content_hash: 'analysis-confirmed-1', annotations: [], codes: [], memos: [], comparisons: [], unavailable_annotation_ids: [] },
      formatting: { template_id: 'chinese-social-science', csl_style_id: 'china-national-standard-gb-t-7714-2015-author-date', locale: 'zh-CN' },
      sections: [{ section_id: 'research_question', key: 'research_question', title: '研究问题', content: '照护实践 combines family duty.', status: 'reviewed', evidence_refs: [], citation_refs: [{ citation_id: 'citation-1', kind: 'scholarly', source_id: 'literature-entry-1', source_version: 'v2', locator: { label: 'page', value: '42' }, state: 'needs_verification' }] }],
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: { task_id: 'task-1', allowed_actions: [], current_match_run_id: null, current_theory_plan_id: 'plan-1', current_framework_id: null, knowledge_release_id: 'release-1', phenomenon_summary: { phenomenon: '照护实践' }, resume_path: '/research/task-1/match' } } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [document] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchDocumentVersions').mockResolvedValue({ data: { items: [document] } } as never)
    const update = vi.spyOn(researchApi, 'updateResearchDocument').mockResolvedValue({ data: { ...document, version: 2, formatting: { template_id: 'asa', csl_style_id: 'american-sociological-association', locale: 'en-US' } } } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes><Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} /></Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：研究问题' }))
    expect(screen.getByRole('complementary', { name: '结构化引用' })).toHaveTextContent('literature-entry-1')
    expect(screen.getByRole('complementary', { name: '结构化引用' })).toHaveTextContent('待核实')
    expect(screen.getByRole('note', { name: '分析依据' })).toHaveTextContent('analysis-confirmed-1')
    fireEvent.change(screen.getByRole('combobox', { name: '论文模板' }), { target: { value: 'asa' } })
    fireEvent.change(screen.getByRole('combobox', { name: '引用样式' }), { target: { value: 'american-sociological-association' } })
    fireEvent.change(screen.getByRole('combobox', { name: '引用语言' }), { target: { value: 'en-US' } })
    fireEvent.click(screen.getByRole('button', { name: '应用格式并形成新版本' }))

    await waitFor(() => expect(update).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        expected_version: 1,
        formatting: { template_id: 'asa', csl_style_id: 'american-sociological-association', locale: 'en-US' },
      }),
    })))
    fireEvent.click(screen.getByLabelText('导出研究文档'))
    expect(screen.getByRole('button', { name: '下载 Markdown' })).toBeVisible()
    expect(screen.getByRole('button', { name: '下载 DOCX' })).toBeVisible()
    expect(screen.getByRole('button', { name: '打印或另存 PDF' })).toBeVisible()
    expect(screen.getByRole('button', { name: '下载审计 JSON' })).toBeVisible()
  })

  it('keeps document research on the canvas as editable section nodes beside the shared Agent', async () => {
    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    const questionCard = await screen.findByRole('button', { name: '研究章节：研究问题' })
    expect(screen.getByRole('region', { name: '研究论证地图' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '研究章节：核心现象' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '研究章节：候选理论' })).toBeInTheDocument()
    fireEvent.click(questionCard)
    expect(screen.getByRole('region', { name: '研究文档节点' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '文档结构' })).not.toBeInTheDocument()
    const agent = screen.getByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(agent).toHaveAttribute('data-task-id', 'task-1')
    expect(agent).toHaveAttribute('data-workspace', 'research')
    expect(screen.getByText(/这一部分会随着研究推进形成可编辑内容/)).toBeInTheDocument()
    expect(document.querySelector('.research-document-editor .ProseMirror')).not.toBeInTheDocument()
  })

  it('restores confirmed case comparisons into the M4 argument map', async () => {
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({
      data: {
        task_id: 'task-1',
        allowed_actions: [],
        current_match_run_id: null,
        current_theory_plan_id: null,
        current_framework_id: null,
        knowledge_release_id: 'release-1',
        phenomenon_summary: { phenomenon: '迁移如何改变家庭照护分工？' },
      },
    } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchAnalysisApi, 'getAnalysisSnapshot').mockResolvedValue({
      task_id: 'task-1',
      annotations: [],
      codes: [],
      memos: [],
      comparisons: [
        {
          comparison_id: 'comparison-confirmed',
          status: 'confirmed',
          title: '迁移前后的照护责任',
          question: '迁移如何改变家庭照护分工？',
          findings: [{ kind: 'support', statement: '跨城务工后日常照护转向祖辈。', annotation_ids: ['annotation-1'] }],
          competing_explanations: [],
          evidence_gaps: ['缺少留守家庭的长期观察。'],
          next_steps: [],
          theory_implication: '迁移对照护责任的影响受家庭资源条件约束。',
        },
        {
          comparison_id: 'comparison-candidate',
          status: 'candidate',
          title: 'Agent 尚未确认的比较',
          question: '候选问题',
          findings: [],
          competing_explanations: [],
          evidence_gaps: [],
          next_steps: [],
          theory_implication: '不得进入 M4',
        },
      ],
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: '研究节点：迁移前后的照护责任' })).toBeVisible()
    expect(screen.getByRole('button', { name: '研究节点：跨城务工后日常照护转向祖辈。' })).toBeVisible()
    expect(screen.getByRole('button', { name: '研究节点：缺少留守家庭的长期观察。' })).toBeVisible()
    expect(screen.getByRole('button', { name: '研究节点：案例比较形成的理论判断' })).toBeVisible()
    expect(screen.queryByRole('button', { name: /尚未确认/ })).not.toBeInTheDocument()
    expect(researchAnalysisApi.getAnalysisSnapshot).toHaveBeenCalledWith('task-1')
  })

  it('lets the Agent panel be resized from the divider', async () => {
    const page = render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    const workspace = page.container.querySelector<HTMLElement>('.research-document-workbench__workspace')!
    Object.defineProperty(workspace, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 1000, height: 800, top: 0, right: 1000, bottom: 800, left: 0, x: 0, y: 0, toJSON: () => ({}) }),
    })
    const separator = screen.getByRole('separator', { name: '调整 Agent 对话栏宽度' })
    Object.defineProperty(separator, 'setPointerCapture', { configurable: true, value: vi.fn() })
    Object.defineProperty(separator, 'releasePointerCapture', { configurable: true, value: vi.fn() })

    fireEvent.pointerDown(separator, { pointerId: 1, clientX: 570 })
    fireEvent.pointerMove(separator, { pointerId: 1, clientX: 500 })
    fireEvent.pointerUp(separator, { pointerId: 1 })

    expect(separator).toHaveAttribute('aria-valuenow', '500')
    expect(workspace.style.getPropertyValue('--rdw-agent-width')).toBe('500px')
  })

  it('keeps mouse dragging available when pointer events are not emitted', () => {
    const page = render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    const workspace = page.container.querySelector<HTMLElement>('.research-document-workbench__workspace')!
    Object.defineProperty(workspace, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 1000, height: 800, top: 0, right: 1000, bottom: 800, left: 0, x: 0, y: 0, toJSON: () => ({}) }),
    })
    const separator = screen.getByRole('separator', { name: '调整 Agent 对话栏宽度' })

    fireEvent.mouseDown(separator, { button: 0, clientX: 570 })
    fireEvent.mouseMove(window, { clientX: 460 })
    fireEvent.mouseUp(window)

    expect(separator).toHaveAttribute('aria-valuenow', '540')
    expect(window.localStorage.getItem('qunxue.research.agent-panel-width')).toBe('540')
  })

  it('states the preview boundary when the research agent is not available', async () => {
    render(
      <MemoryRouter initialEntries={['/research/task-1/framework']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：研究问题' }))
    expect(await screen.findByText(/当前 Agent 运行环境未连接/)).toBeInTheDocument()
    expect(screen.getAllByText(/不会把静态示例当作真实研究结果/).length).toBeGreaterThan(0)
  })

  it('starts M4 matching from the server navigation snapshot', async () => {
    const navigation = {
      task_id: 'task-1',
      version: 3,
      allowed_actions: ['start_matching'],
      blocker: null,
      retry: null,
      current_match_run_id: null,
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: '解释互助变化机制',
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    const createMatchRun = vi.spyOn(researchApi, 'createMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-1',
        status: 'awaiting_decision',
        knowledge_release_id: 'release-pinned-1',
        retrieval: {
          retrieval_index_id: 'retrieval-index-1',
          mode: 'hybrid_reranked',
          embedding_model: 'Pro/BAAI/bge-m3',
          reranker_model: 'Pro/BAAI/bge-reranker-v2-m3',
          degraded_reason: null,
          retrieved_chunk_ids: ['theory-profile:theory:social-capital:v1'],
        },
        candidate_page: {
          candidates: [{
            candidate_id: 'candidate-1',
            version: 1,
            title: '社会资本理论',
            applicability_rationale: '可解释稳定关系如何支持互助。',
          }],
        },
        failed_candidate_ids: [],
      },
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '开始理论匹配' }))

    expect(await screen.findByRole('heading', { name: '社会资本理论' })).toBeVisible()
    const provenance = screen.getByRole('group', { name: '匹配发布与检索证据链' })
    expect(provenance).toHaveTextContent('release-pinned-1')
    expect(provenance).toHaveTextContent('retrieval-index-1')
    expect(provenance).toHaveTextContent('hybrid_reranked')
    expect(provenance).toHaveTextContent('Pro/BAAI/bge-m3')
    expect(provenance).toHaveTextContent('Pro/BAAI/bge-reranker-v2-m3')
    expect(createMatchRun).toHaveBeenCalledWith({
      path: { task_id: 'task-1' },
      headers: { 'Idempotency-Key': expect.any(String) },
      body: {
        expected_task_version: 3,
        phenomenon_query_id: 'phenomenon-1',
        phenomenon_version: 2,
        knowledge_release_id: 'release-pinned-1',
      },
    })
  })

  it('projects an Agent-started match without reloading the page', async () => {
    const initialNavigation = {
      task_id: 'task-1',
      version: 3,
      allowed_actions: ['start_matching'],
      blocker: null,
      retry: null,
      current_match_run_id: null,
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: '解释互助变化机制',
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    const refreshedNavigation = {
      ...initialNavigation,
      version: 4,
      allowed_actions: [],
      current_match_run_id: 'match-from-agent',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation')
      .mockResolvedValueOnce({ data: initialNavigation } as never)
      .mockResolvedValueOnce({ data: refreshedNavigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listTheoryDecisions').mockResolvedValue({ data: { decision_sets: [] } } as never)
    const getMatchRun = vi.spyOn(researchApi, 'getMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-from-agent',
        status: 'awaiting_decision',
        knowledge_release_id: 'release-pinned-1',
        candidate_page: {
          candidates: [{
            candidate_id: 'candidate-agent-1',
            version: 1,
            title: '社会资本理论',
            applicability_rationale: '解释稳定关系与互惠规范。',
          }],
        },
        failed_candidate_ids: [],
      },
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    await screen.findByRole('button', { name: '开始理论匹配' })
    fireEvent.click(screen.getByRole('button', { name: '完成 Agent 回合' }))

    expect(await screen.findByRole('heading', { name: '社会资本理论' })).toBeVisible()
    expect(getMatchRun).toHaveBeenCalledWith({ path: { match_run_id: 'match-from-agent' } })
  })

  it('clears decisions from a superseded match after an Agent turn', async () => {
    const initialNavigation = {
      task_id: 'task-1',
      version: 4,
      allowed_actions: [],
      blocker: null,
      retry: null,
      current_match_run_id: 'match-old',
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: '解释互助变化机制',
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation')
      .mockResolvedValueOnce({ data: initialNavigation } as never)
      .mockResolvedValueOnce({
        data: { ...initialNavigation, version: 5, current_match_run_id: 'match-new' },
      } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'getMatchRun')
      .mockResolvedValueOnce({
        data: {
          match_run_id: 'match-old',
          status: 'awaiting_decision',
          knowledge_release_id: 'release-pinned-1',
          candidate_page: { candidates: [{ candidate_id: 'candidate-old', version: 1, title: '旧理论', applicability_rationale: '旧判断' }] },
          failed_candidate_ids: [],
        },
      } as never)
      .mockResolvedValueOnce({
        data: {
          match_run_id: 'match-new',
          status: 'awaiting_decision',
          knowledge_release_id: 'release-pinned-1',
          candidate_page: { candidates: [{ candidate_id: 'candidate-new', version: 1, title: '新理论', applicability_rationale: '新判断' }] },
          failed_candidate_ids: [],
        },
      } as never)
    vi.spyOn(researchApi, 'listTheoryDecisions')
      .mockResolvedValueOnce({
        data: {
          decision_sets: [{
            decision_set_id: 'decision-old',
            version: 1,
            allowed_actions: ['confirm_theory_plan'],
            decisions: [{ candidate_id: 'candidate-old', candidate_version: 1, action: 'adopt' }],
          }],
        },
      } as never)
      .mockResolvedValueOnce({ data: { decision_sets: [] } } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    expect(await screen.findByRole('heading', { name: '旧理论' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '完成 Agent 回合' }))

    expect(await screen.findByRole('heading', { name: '新理论' })).toBeVisible()
    expect(screen.queryByRole('button', { name: '确认理论方案，进入 M5' })).not.toBeInTheDocument()
  })

  it('executes the server retry contract after an empty matching run', async () => {
    const navigation = {
      task_id: 'task-1',
      version: 4,
      allowed_actions: ['start_matching'],
      blocker: {
        code: 'no_reliable_candidate',
        message: '固定知识发布中没有可正式采用的理论候选，请调整研究现象后重试。',
        recoverable: true,
        action: 'start_matching',
      },
      retry: {
        method: 'POST',
        href: '/api/research-tasks/task-1/match-runs',
        action: 'start_matching',
        label: '重新匹配',
      },
      current_match_run_id: 'match-empty',
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: null,
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listTheoryDecisions').mockResolvedValue({ data: { decision_sets: [] } } as never)
    vi.spyOn(researchApi, 'getMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-empty',
        status: 'no_reliable_candidate',
        knowledge_release_id: 'release-pinned-1',
        candidate_page: { candidates: [] },
        failed_candidate_ids: [],
      },
    } as never)
    const createMatchRun = vi.spyOn(researchApi, 'createMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-retry',
        status: 'no_reliable_candidate',
        knowledge_release_id: 'release-pinned-1',
        candidate_page: { candidates: [] },
        failed_candidate_ids: [],
      },
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '重新匹配' }))

    await waitFor(() => expect(createMatchRun).toHaveBeenCalledTimes(1))
    expect(createMatchRun.mock.calls[0]?.[0].body.expected_task_version).toBe(4)
  })

  it('reuses one matching idempotency key after a network failure', async () => {
    const navigation = {
      task_id: 'task-1',
      version: 3,
      allowed_actions: ['start_matching'],
      blocker: null,
      retry: null,
      current_match_run_id: null,
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: null,
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    const createMatchRun = vi.spyOn(researchApi, 'createMatchRun')
      .mockRejectedValueOnce(new Error('网络连接中断'))
      .mockResolvedValueOnce({
        data: {
          match_run_id: 'match-after-retry',
          status: 'awaiting_decision',
          knowledge_release_id: 'release-pinned-1',
          candidate_page: { candidates: [] },
          failed_candidate_ids: [],
        },
      } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '开始理论匹配' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('网络连接中断')
    fireEvent.click(screen.getByRole('button', { name: '开始理论匹配' }))

    await waitFor(() => expect(createMatchRun).toHaveBeenCalledTimes(2))
    expect(createMatchRun.mock.calls.map(([options]) => options.headers['Idempotency-Key'])).toEqual([
      createMatchRun.mock.calls[0]?.[0].headers['Idempotency-Key'],
      createMatchRun.mock.calls[0]?.[0].headers['Idempotency-Key'],
    ])
  })

  it('enters M5 only through the latest server resume path after theory-plan confirmation', async () => {
    const navigation = {
      task_id: 'task-1',
      current_match_run_id: 'match-1',
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-formal-1',
      phenomenon_summary: { phenomenon: '社区互助为何减少？' },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'getMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-1',
        knowledge_release_id: 'release-formal-1',
        candidate_page: { candidates: [] },
      },
    } as never)
    vi.spyOn(researchApi, 'listTheoryDecisions').mockResolvedValue({
      data: {
        decision_sets: [{
          decision_set_id: 'decision-set-1',
          version: 1,
          allowed_actions: ['confirm_theory_plan'],
          decisions: [],
        }],
      },
    } as never)
    vi.spyOn(researchApi, 'confirmTheoryPlan').mockResolvedValue({ data: { theory_plan_id: 'plan-1' } } as never)
    vi.spyOn(researchApi, 'readResearchTaskNavigationViaApi').mockResolvedValue({
      ...navigation,
      resume_path: '/research/task-1/framework',
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
          <Route path="/research/:task_id/framework" element={<h1>M5 服务端恢复目标</h1>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByText('release-formal-1')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认理论方案，进入 M5' }))

    expect(await screen.findByRole('heading', { name: 'M5 服务端恢复目标' })).toBeVisible()
    await waitFor(() => expect(researchApi.readResearchTaskNavigationViaApi).toHaveBeenCalledWith('task-1'))
  })

  it('embeds the requested document section without mounting a second page shell or Agent', async () => {
    const navigation = {
      task_id: 'task-1',
      conversation_id: 'conversation-1',
      allowed_actions: [],
      current_match_run_id: null,
      current_theory_plan_id: 'theory-plan-1',
      current_framework_id: 'document-1',
      knowledge_release_id: 'release-1',
      phenomenon_summary: { phenomenon: '社区照护如何分配？' },
    }
    const document = {
      document_id: 'document-1',
      theory_plan_id: 'theory-plan-1',
      knowledge_release_id: 'release-1',
      revision_id: 'revision-3',
      title: '社区照护研究框架',
      version: 3,
      actor: 'user',
      status: 'draft',
      sections: [
        { section_id: 'research_question', key: 'research_question', title: '研究问题', content: '谁承担照护？', status: 'reviewed', evidence_refs: [] },
        { section_id: 'methodology', key: 'methodology', title: '研究方法', content: '半结构访谈', status: 'needs_user_decision', evidence_refs: [] },
      ],
    }
    const conversation: AgentConversation = {
      conversation_id: 'conversation-1',
      title: '社区照护',
      created_at: '2026-08-31T00:00:00Z',
      updated_at: '2026-08-31T00:01:00Z',
      turn_count: 0,
      research_map: {
        schema_version: 1,
        nodes: [{ id: 'claim-care', kind: 'claim', title: '照护责任向家庭回流', summary: '公共供给不足时家庭承担更多照护。', status: 'developing', citation_ids: [] }],
        relations: [],
      },
      turns: [],
    }
    const onWorkspaceContextChange = vi.fn()
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [document] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchDocumentVersions').mockResolvedValue({ data: { items: [document] } } as never)

    const { container } = render(
      <MemoryRouter initialEntries={['/research/task-1/workspace/writing?section_id=methodology']}>
        <Routes>
          <Route
            path="/research/:task_id/workspace/:tool"
            element={(
              <ResearchDocumentWorkbench
                embedded
                workspaceMode="framework"
                focusDocument
                initialSectionId="methodology"
                conversation={conversation}
                onWorkspaceContextChange={onWorkspaceContextChange}
              />
            )}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('region', { name: '研究文档节点' })).toBeVisible()
    expect(screen.getByRole('heading', { name: '研究文档正文' })).toHaveTextContent('研究方法')
    expect(screen.getByRole('button', { name: '研究节点：照护责任向家庭回流' })).toBeVisible()
    expect(screen.queryByRole('complementary', { name: '研究 Agent 对话栏' })).not.toBeInTheDocument()
    expect(screen.queryByRole('separator', { name: '调整 Agent 对话栏宽度' })).not.toBeInTheDocument()
    expect(container.querySelector('.page-shell')).not.toBeInTheDocument()
    await waitFor(() => expect(onWorkspaceContextChange).toHaveBeenLastCalledWith({
      mode: 'framework',
      documentId: 'document-1',
      sectionId: 'methodology',
      documentVersion: 3,
      theoryPlanId: 'theory-plan-1',
    }))
  })

  it('refreshes the embedded document context in place when the shared Agent completes a turn', async () => {
    const navigation = {
      task_id: 'task-1',
      conversation_id: 'conversation-1',
      allowed_actions: [],
      current_match_run_id: null,
      current_theory_plan_id: 'theory-plan-1',
      current_framework_id: null,
      knowledge_release_id: 'release-1',
      phenomenon_summary: { phenomenon: '社区照护如何分配？' },
    }
    const document = (version: number) => ({
      document_id: 'document-1',
      theory_plan_id: 'theory-plan-1',
      knowledge_release_id: 'release-1',
      revision_id: `revision-${version}`,
      title: '理论判断文档',
      version,
      actor: 'agent',
      status: 'draft',
      sections: [{ section_id: 'theory_fit', key: 'theory_fit', title: '理论适配与张力', content: `第 ${version} 版`, status: 'reviewed', evidence_refs: [] }],
    })
    const onWorkspaceContextChange = vi.fn()
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments')
      .mockResolvedValueOnce({ data: { items: [document(1)] } } as never)
      .mockResolvedValue({ data: { items: [document(2)] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchDocumentVersions').mockImplementation(async ({ path }) => ({
      data: { items: [path.document_id === 'document-1' ? document(2) : document(1)] },
    }) as never)
    vi.spyOn(researchAnalysisApi, 'getAnalysisSnapshot').mockResolvedValue(null)

    const view = render(
      <MemoryRouter initialEntries={['/research/task-1/workspace/theory']}>
        <Routes>
          <Route
            path="/research/:task_id/workspace/:tool"
            element={(
              <ResearchDocumentWorkbench
                embedded
                workspaceMode="match"
                focusDocument
                initialSectionId="theory_fit"
                refreshKey={0}
                onWorkspaceContextChange={onWorkspaceContextChange}
              />
            )}
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(onWorkspaceContextChange).toHaveBeenLastCalledWith(expect.objectContaining({ documentVersion: 1 })))
    view.rerender(
      <MemoryRouter initialEntries={['/research/task-1/workspace/theory']}>
        <Routes>
          <Route
            path="/research/:task_id/workspace/:tool"
            element={(
              <ResearchDocumentWorkbench
                embedded
                workspaceMode="match"
                focusDocument
                initialSectionId="theory_fit"
                refreshKey={1}
                onWorkspaceContextChange={onWorkspaceContextChange}
              />
            )}
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(onWorkspaceContextChange).toHaveBeenLastCalledWith(expect.objectContaining({
      documentId: 'document-1',
      sectionId: 'theory_fit',
      documentVersion: 2,
    })))
    expect(screen.getAllByRole('region', { name: '研究文档节点' })).toHaveLength(1)
  })
})
