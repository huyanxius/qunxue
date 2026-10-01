import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PageShell } from './PageShell'

vi.mock('../../modules/account', () => ({
  useAccount: () => ({
    sessionState: {
      status: 'authenticated' as const,
      session: { user: { displayName: '研究者' } },
    },
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    retrySession: vi.fn(),
  }),
}))

afterEach(cleanup)

describe('PageShell global chrome', () => {
  it.each([
    ['/agent?conversation_id=conversation-b&task_id=task-1&knowledge_release_id=release-1', '研究画布', '/research/new?conversation_id=conversation-b&task_id=task-1&knowledge_release_id=release-1'],
    ['/research/new?conversation_id=conversation-b&task_id=task-1', '对话视图', '/agent?conversation_id=conversation-b&task_id=task-1'],
  ])('keeps the same conversation when switching views from %s', (path, label, destination) => {
    render(<MemoryRouter initialEntries={[path]}><PageShell><h1>研究</h1></PageShell></MemoryRouter>)
    const views = screen.getByRole('navigation', { name: '对话视图' })
    expect(within(views).getByRole('link', { name: label })).toHaveAttribute('href', destination)
    expect(within(screen.getByRole('navigation', { name: '桌面主导航' })).getByRole('link', { name: '新建研究' })).toHaveAttribute('href', '/research/new')
    const identityQuery = path.slice(path.indexOf('?'))
    expect(within(screen.getByRole('navigation', { name: '桌面主导航' })).getByRole('link', { name: '研究 Agent' })).toHaveAttribute('href', `/agent${identityQuery}`)
  })

  it('does not inject the retired help and boundary trigger', () => {
    render(
      <MemoryRouter>
        <PageShell immersive>
          <h1>登录</h1>
        </PageShell>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: '帮助与边界' })).not.toBeInTheDocument()
  })

  it('shows the research deep-dive update in the updates tab', () => {
    render(
      <MemoryRouter>
        <PageShell>
          <h1>工作台</h1>
        </PageShell>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: '通知' }))
    fireEvent.click(screen.getByRole('tab', { name: '更新日志' }))

    expect(screen.getByText('深度研究现已上线')).toBeInTheDocument()
    expect(screen.getByText(/自动让 Agent 规划任务/)).toBeInTheDocument()
  })
})

it('exposes courses in desktop navigation and mobile more menu', () => {
  render(<MemoryRouter><PageShell><h1>课程测试</h1></PageShell></MemoryRouter>)
  expect(within(screen.getByRole('navigation', { name: '桌面主导航' })).getByRole('link', { name: '课程' })).toHaveAttribute('href', '/courses')
  fireEvent.click(screen.getByRole('button', { name: '更多' }))
  expect(within(screen.getByRole('navigation', { name: '更多功能' })).getByRole('link', { name: '课程' })).toHaveAttribute('href', '/courses')
})

describe('expandable knowledge folder', () => {
  it('expands to exactly three child destinations without navigating the folder', () => {
    render(<MemoryRouter initialEntries={['/app']}><PageShell><h1>工作台</h1></PageShell></MemoryRouter>)
    const nav = within(screen.getByRole('navigation', { name: '桌面主导航' }))
    const folder = nav.getByRole('button', { name: '知识库' })
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    expect(nav.queryByRole('link', { name: '学术前沿' })).not.toBeInTheDocument()
    fireEvent.click(folder)
    expect(folder).toHaveAttribute('aria-expanded', 'true')
    const children = document.getElementById(folder.getAttribute('aria-controls')!)!
    expect(within(children).getAllByRole('link')).toHaveLength(3)
    expect(nav.getByRole('link', { name: '学科知识库' })).toHaveAttribute('href', '/knowledge')
    expect(nav.getByRole('link', { name: '课程知识库' })).toHaveAttribute('href', '/knowledge?scope=courses')
    expect(nav.getByRole('link', { name: '学术前沿' })).toHaveAttribute('href', '/knowledge?scope=frontier')
    fireEvent.click(folder)
    expect(folder).toHaveAttribute('aria-expanded', 'false')
  })

  it.each([
    ['/knowledge?query=test', '学科知识库'],
    ['/knowledge/entry-1?knowledge_release_id=r1', '学科知识库'],
    ['/knowledge?scope=courses&kb_id=course-1', '课程知识库'],
    ['/knowledge?scope=frontier&q=test&record=record-1', '学术前沿'],
  ])('selects only the correct child for deep link %s', (path, selected) => {
    render(<MemoryRouter initialEntries={[path]}><PageShell><h1>页面</h1></PageShell></MemoryRouter>)
    const nav = within(screen.getByRole('navigation', { name: '桌面主导航' }))
    expect(nav.getByRole('button', { name: '知识库' })).toHaveAttribute('aria-expanded', 'true')
    expect(nav.getAllByRole('link', { current: 'page' })).toHaveLength(1)
    expect(nav.getByRole('link', { name: selected })).toHaveAttribute('aria-current', 'page')
  })

  it('opens the compact sidebar before exposing the children', () => {
    render(<MemoryRouter initialEntries={['/knowledge?scope=frontier']}><PageShell defaultRailCollapsed><h1>页面</h1></PageShell></MemoryRouter>)
    const nav = within(screen.getByRole('navigation', { name: '桌面主导航' }))
    expect(nav.getByRole('button', { name: '知识库' })).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(nav.getByRole('button', { name: '知识库' }))
    expect(screen.getByRole('button', { name: '收起侧栏' })).toBeInTheDocument()
    expect(nav.getByRole('link', { name: '学术前沿' })).toHaveAttribute('aria-current', 'page')
  })

  it('reveals the same three links from mobile Knowledge and dismisses after selection or Escape', () => {
    render(<MemoryRouter initialEntries={['/knowledge?scope=frontier']}><PageShell><h1>页面</h1></PageShell></MemoryRouter>)
    const nav = within(screen.getByRole('navigation', { name: '移动主导航' }))
    const folder = nav.getByRole('button', { name: '知识库' })
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(folder)
    expect(nav.getByRole('link', { name: '学术前沿' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(nav.getByRole('link', { name: '课程知识库' }))
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(folder)
    expect(nav.getByRole('link', { name: '课程知识库' })).toHaveAttribute('aria-current', 'page')
    fireEvent.keyDown(nav.getByRole('link', { name: '课程知识库' }), { key: 'Escape' })
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    expect(folder).toHaveFocus()
  })
})

function NavigationHistory() {
  const navigate = useNavigate()
  return <><button onClick={() => navigate(-1)}>后退</button><button onClick={() => navigate(1)}>前进</button></>
}

it('restores the selected knowledge child through Back and Forward', () => {
  render(<MemoryRouter initialEntries={['/knowledge?scope=frontier&q=企业']}><PageShell><NavigationHistory /></PageShell></MemoryRouter>)
  const nav = within(screen.getByRole('navigation', { name: '桌面主导航' }))
  fireEvent.click(nav.getByRole('link', { name: '课程知识库' }))
  expect(nav.getByRole('link', { name: '课程知识库' })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(screen.getByRole('button', { name: '后退' }))
  expect(nav.getByRole('link', { name: '学术前沿' })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(screen.getByRole('button', { name: '前进' }))
  expect(nav.getByRole('link', { name: '课程知识库' })).toHaveAttribute('aria-current', 'page')
})

it('keeps the standalone graph selection outside the library folder', () => {
  render(<MemoryRouter initialEntries={['/knowledge/graph']}><PageShell><h1>图谱</h1></PageShell></MemoryRouter>)
  const nav = within(screen.getByRole('navigation', { name: '桌面主导航' }))
  fireEvent.click(nav.getByRole('button', { name: '知识库' }))
  expect(nav.getAllByRole('link', { current: 'page' })).toHaveLength(1)
  expect(nav.getByRole('link', { name: '知识图谱' })).toHaveAttribute('aria-current', 'page')
  expect(nav.getByRole('link', { name: '学科知识库' })).not.toHaveAttribute('aria-current')
})

it('keeps the mobile knowledge folder and More panel mutually exclusive', () => {
  render(<MemoryRouter><PageShell><h1>页面</h1></PageShell></MemoryRouter>)
  const nav = within(screen.getByRole('navigation', { name: '移动主导航' }))
  fireEvent.click(nav.getByRole('button', { name: '更多' }))
  expect(screen.getByRole('dialog', { name: '更多功能' })).toBeInTheDocument()
  fireEvent.click(nav.getByRole('button', { name: '知识库' }))
  expect(screen.queryByRole('dialog', { name: '更多功能' })).not.toBeInTheDocument()
  expect(nav.getByRole('link', { name: '学术前沿' })).toBeInTheDocument()
  fireEvent.click(nav.getByRole('button', { name: '更多' }))
  expect(nav.queryByRole('link', { name: '学术前沿' })).not.toBeInTheDocument()
})
