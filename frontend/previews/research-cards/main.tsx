/* eslint-disable react/only-export-components -- 独立预览入口在本文件挂载。 */
import { useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowUpRightIcon, CaretRightIcon, CompassIcon, PathIcon, QuotesIcon } from '@phosphor-icons/react'
import { ResearchMapCanvas } from '../../src/app/research-workspace/ResearchMapCanvas'
import type { ResearchCanvasNode, ResearchCanvasProjection } from '../../src/modules/research-workspace'
import '../../src/styles/tokens.css'
import '../../src/styles/app.css'
import '../../src/app/agent/research-agent-conversation.css'
import '../../src/app/agent/new-research-workspace.css'
import './preview.css'

// 同一份示例内容用于左右两侧；旧侧直接加载当前主线样式，新侧只在 .after 下覆盖。
const cards: (ResearchCanvasNode & { label: string; state: string })[] = [
  { id: 'question', kind: 'question', label: '研究问题', title: '青年为什么选择留在大城市？', summary: '从职业机会、社会关系与归属感出发，理解青年留城的日常选择。', status: 'developing', state: '形成中', citationIds: [], provenance: 'user' },
  { id: 'phenomenon', kind: 'phenomenon', label: '核心现象', title: '高流动中的长期停留', summary: '工作与居所频繁变动，但受访者仍持续把未来安排在这座城市。', status: 'grounded', state: '已有依据', citationIds: ['1', '2'], provenance: 'agent' },
  { id: 'theory', kind: 'theory', label: '理论视角', title: '社会嵌入与地方依恋', summary: '考察关系网络如何把短期的机会选择转化为持续的生活安排。', status: 'grounded', state: '已有依据', citationIds: ['3', '4'], provenance: 'knowledge' },
  { id: 'claim', kind: 'claim', label: '核心主张', title: '关系支持降低了留城的不确定性', summary: '熟人网络提供情感支持与实际帮助，逐渐成为留城决策的支点。', status: 'developing', state: '形成中', citationIds: ['1', '2', '3'], provenance: 'agent' },
  { id: 'evidence', kind: 'evidence', label: '经验依据', title: '“在这里，总有人能搭把手”', summary: '受访者提到，朋友协助找房与介绍工作，让生活的转换更容易。', status: 'verified', state: '已核验', citationIds: ['1'], provenance: 'user' },
  { id: 'gap', kind: 'gap', label: '证据缺口', title: '离开城市的青年怎么说？', summary: '现有材料主要来自留城者，需要补充离开者的经历作为对照。', status: 'open', state: '待处理', citationIds: [], provenance: 'agent' },
  { id: 'synthesis', kind: 'synthesis', label: '阶段综合', title: '从机会选择到关系性扎根', summary: '留城不只是经济权衡，也是在日常互助中不断累积的关系承诺。', status: 'complete', state: '已完成', citationIds: ['1', '2', '3', '4'], provenance: 'agent' },
  { id: 'document', kind: 'document', label: '研究章节', title: '研究发现：留城的日常机制', summary: '围绕关系支持、生活安排与未来想象，整理本阶段研究发现。', status: 'developing', state: '形成中', citationIds: [], provenance: 'agent' },
]
const projection: ResearchCanvasProjection = { status: 'ready', question: cards[0].title, nodes: cards, edges: [
  ['question', 'phenomenon', 'refines'], ['phenomenon', 'theory', 'explains'], ['theory', 'claim', 'derives'],
  ['evidence', 'claim', 'supports'], ['gap', 'claim', 'challenges'], ['claim', 'synthesis', 'derives'], ['synthesis', 'document', 'derives'],
].map(([source, target, relation], i) => ({ id: String(i), source, target, relation: relation as ResearchCanvasProjection['edges'][number]['relation'] })) }

function NodeCard({ node, after }: { node: typeof cards[number]; after: boolean }) {
  const [selected, setSelected] = useState(false)
  return <article tabIndex={0} role="button" aria-pressed={selected} aria-label={`${node.label}：${node.title}`}
    onClick={() => setSelected(!selected)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(!selected) } }}
    className={`research-argument-node is-${node.kind}${selected ? ' is-selected' : ''}`}>
    {node.kind !== 'document' || after ? <div className="research-argument-node__meta"><span>{node.kind === 'evidence' ? <QuotesIcon size={13} /> : <PathIcon size={13} />}{node.label}</span><i className={`is-${node.status}`}>{node.state}</i></div> : null}
    <h3>{node.title}</h3><p>{node.summary}</p>
    {node.kind !== 'document' || after ? <footer><span>{node.citationIds.length ? `${node.citationIds.length} 条依据` : node.kind === 'gap' ? '等待补证' : after ? node.kind === 'document' ? '打开文稿' : '研究中' : 'Agent 结构化'}</span>{after ? <ArrowUpRightIcon size={14} /> : <b />}</footer> : null}
  </article>
}

// 原有对话卡片只作参照：复用主线 DOM 与 CSS，不叠加新版样式。
function OriginalConversationCard() {
  const [notice, setNotice] = useState('')
  return <div className="original-conversation-reference">
    <div className="research-agent-conversation">
      <section className="deep-research-mock-card research-flow-card new-research__start-proposal" aria-label="研究建立确认">
        <header className="research-flow-card__heading"><CompassIcon size={22} weight="regular" aria-hidden="true" /><h2>青年为什么选择留在大城市？</h2></header>
        <dl className="new-research__start-fields">
          <div><dt>意图</dt><dd>理解社会关系如何影响青年留城选择</dd></div>
          <div><dt>情境</dt><dd>大城市中的青年工作与日常生活</dd></div>
        </dl>
        <div className="deep-research-mock-card__actions new-research__start-actions">
          <button type="button" className="deep-research-mock-card__continue" onClick={() => setNotice('此处仅展示原卡片，不建立研究。')}>确认研究起点<CaretRightIcon size={14} /></button>
          <button type="button" onClick={() => setNotice('此处仅展示原卡片，不修改研究。')}>继续修改</button>
        </div>
      </section>
    </div>
    {notice ? <p className="section-note" role="status">{notice}</p> : null}
  </div>
}

function Pair({ children }: { children: (after: boolean) => ReactNode }) {
  return <div className="pair">{[false, true].map(after => <div key={String(after)} className={`sample ${after ? 'after' : 'before'}`}><span className="sample-label">{after ? '改之后' : '改之前'}</span>{children(after)}</div>)}</div>
}
function Preview() {
  const [tab, setTab] = useState('canvas')
  const [version, setVersion] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  return <div className="app-frame preview"><header className="preview-header"><a href="#">群学致知</a><span>新建研究 / 卡片样式预览</span><small>Mock · v3</small></header>
    <main><div className="intro"><div><p>研究工作区</p><h1>让研究卡片回到同一种语言。</h1><p>沿用原有对话卡片的字体、细边线与留白，为画布保留不同类型的颜色。</p></div><div className="reference"><div className="radius-sample" /><span>16px 内容圆角<br />12px 控件圆角 · 保留类型配色</span></div></div>
    <nav className="tabs" aria-label="预览内容">{[['canvas', '画布卡片 · 8 类'], ['reference', '原有对话卡片 · 参照'], ['scene', '放回画布看看']].map(([key, label]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}</nav>
    {tab === 'canvas' ? <><p className="section-note">同一内容左右对照。点击卡片可查看选中状态；研究章节的新稿补回类型与文稿入口。</p>{cards.map(node => <section className="comparison" key={node.id}><h2>{node.label}</h2><Pair>{after => <NodeCard node={node} after={after} />}</Pair></section>)}</> : null}
    {tab === 'reference' ? <><p className="section-note">原有研究确认卡，仅作样式参照。直接使用主线的结构与样式，没有改版。</p><OriginalConversationCard /></> : null}
    {tab === 'scene' ? <><div className="scene-toolbar"><p>真实画布组件 + 示例研究内容，可拖动、缩放、选择节点。</p><button aria-pressed={version} onClick={() => setVersion(!version)}>{version ? '正在看改之后 · 切换旧版' : '正在看改之前 · 切换新版'}</button></div><div className={`scene ${version ? 'after' : 'before'}`}><ResearchMapCanvas projection={projection} selectedNodeId={selected} onSelectNode={node => setSelected(node.id)} onClearSelection={() => setSelected(null)} onContinueNode={node => setSelected(node.id)} /></div><p className="section-note">此处演示卡片样式与画布交互，不调用研究服务；章节的内容补充方案见逐卡对照。</p></> : null}
    <footer className="preview-footer">基于 main · 1dfc765。旧版读取当前主线 CSS；新版样式仅作用于本预览。示例内容不代表真实研究结论。</footer></main></div>
}
createRoot(document.getElementById('root')!).render(<Preview />)
