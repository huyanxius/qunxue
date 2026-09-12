import { useState } from 'react'
import { ChatCircleTextIcon, SlidersHorizontalIcon, GraphIcon } from '@phosphor-icons/react'
import { useNavigate } from 'react-router'
import type { RoadshowCase, RoadshowSettings } from '../../api/roadshow'
import { useRoadshowSettings } from './roadshowState'
import '../../modules/account/account-settings.css'
import './roadshow.css'

const partitions = [ ['answer','预设回答',ChatCircleTextIcon], ['flow','交互与检索',SlidersHorizontalIcon], ['canvas','研究画布',GraphIcon] ] as const

export function RoadshowPanel({ initial, onClose }: { initial: RoadshowSettings; onClose: () => void }) {
  const [draft, setDraft] = useState(() => structuredClone(initial))
  const [page, setPage] = useState<'answer' | 'flow' | 'canvas'>('answer')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const { save, reset } = useRoadshowSettings()
  const navigate = useNavigate()
  const index = draft.active_case ?? 0
  const current = draft.cases[index]
  function patchCase(patch: Partial<RoadshowCase>) {
    setDraft(value => ({ ...value, cases: value.cases.map((item, i) => i === index ? { ...item, ...patch } : item) }))
    setMessage('有未保存的修改')
  }
  async function persist(destination?: string) {
    setBusy(true); setMessage('正在保存…')
    try {
      const clean = (items: string[]) => items.map(item => item.trim()).filter(Boolean)
      const result = await save({ ...draft, cases: draft.cases.map(item => ({ ...item,
        keywords: clean(item.keywords), options: clean(item.options), steps: clean(item.steps),
        knowledge_queries: clean(item.knowledge_queries ?? []), web_queries: clean(item.web_queries ?? []),
      })) })
      setDraft(result); setMessage('已保存')
      if (destination) { onClose(); navigate(destination) }
    } catch { setMessage('保存失败，请检查必填项和网络后重试') }
    finally { setBusy(false) }
  }
  const multiline = (label: string, key: 'keywords' | 'options' | 'steps' | 'knowledge_queries' | 'web_queries', rows = 3) => <label>{label}<textarea rows={rows} value={(current[key] ?? []).join('\n')} onChange={e => patchCase({ [key]: e.target.value.split('\n') })} /></label>
  return <article className="qs-settings roadshow-panel">
    <aside className="qs-sidebar">
      <div className="qs-identity"><span className="qs-avatar" aria-hidden="true">叶</span><div><strong>叶知秋</strong><small>演示账户</small></div></div>
      <h1>开发者选项</h1>
      <nav aria-label="开发者设置分区">{partitions.map(([id,label,Icon]) => <button key={id} type="button" aria-current={page === id ? 'page' : undefined} onClick={() => setPage(id)}><Icon size={20} weight="regular" aria-hidden="true" />{label}</button>)}</nav>
      <div className="qs-sidebar-footer"><button type="button" disabled={busy} onClick={async () => { setBusy(true); try { setDraft(await reset()); setMessage('已恢复初始配置') } catch { setMessage('恢复失败，请重试') } finally { setBusy(false) } }}>恢复初始配置</button></div>
    </aside>
    <section className="qs-content roadshow-content" aria-label={partitions.find(([id]) => id === page)?.[1]}>
      <header className="qs-header"><h2>{partitions.find(([id]) => id === page)?.[1]}</h2></header>
      <div className="qs-row roadshow-case-row"><label htmlFor="roadshow-case">演示案例</label><select id="roadshow-case" value={index} onChange={e => setDraft({ ...draft, active_case: Number(e.target.value) })}>{draft.cases.map((item,i) => <option key={i} value={i}>{item.title}</option>)}</select></div>
      <div className="roadshow-fields qs-form">
        {page === 'answer' ? <>
          <div className="qs-row"><div><h3>启用预设回答</h3><p>仅在当前账户匹配案例时生效</p></div><input aria-label="启用预设回答" type="checkbox" checked={draft.enabled !== false} onChange={e => setDraft({ ...draft, enabled: e.target.checked })} /></div>
          <label>案例标题<input value={current.title} onChange={e => patchCase({ title: e.target.value })} /></label>
          <label>AI 预设回答<textarea className="roadshow-answer" aria-label="AI 预设回答" value={current.answer} onChange={e => patchCase({ answer: e.target.value })} /></label>
          <p className="qs-footnote">支持 Markdown · {current.answer.length.toLocaleString()} 字符</p>
          <div className="qs-row"><span>输出速度</span><select aria-label="输出速度" value={draft.chunk_delay ?? .025} onChange={e => setDraft({ ...draft, chunk_delay: Number(e.target.value) })}><option value={0}>立即输出</option><option value={.025}>快速</option><option value={.08}>自然</option><option value={.2}>慢速展示</option></select></div>
        </> : page === 'flow' ? <>
          {multiline('触发关键词（每行一个）','keywords',2)}
          <label>Agent 先询问什么<textarea rows={2} value={current.question} onChange={e => patchCase({ question: e.target.value })} /></label>
          {multiline('供用户选择的回答（每行一项）','options')}
          {multiline('研究提案步骤（每行一步）','steps',4)}
          {multiline('知识库搜索词（每行一次）','knowledge_queries')}
          {multiline('网页搜索词（每行一次）','web_queries')}
        </> : <>
          <div className="qs-row"><div><h3>由 Agent 自动生成画布</h3><p>根据研究回答组织节点与关系，沿用现有研究地图。</p></div><input type="checkbox" aria-label="由 Agent 自动生成画布" checked={draft.canvas_enabled !== false} onChange={e => setDraft({ ...draft, canvas_enabled: e.target.checked })} /></div>
          <p className="qs-footnote">研究结束后，切换到“新建研究”查看同一对话的画布。卡片内容继续使用画布中已有的编辑功能。</p>
        </>}
      </div>
      <footer className="qs-actions qs-actions--footer"><span className="roadshow-status" role="status">{message}</span><button className="qs-button" disabled={busy} onClick={() => void persist('/research/new')}>保存并进入研究</button><button className="qs-button qs-button--primary" disabled={busy} onClick={() => void persist()}>{busy ? '保存中…' : '保存修改'}</button></footer>
    </section>
  </article>
}
