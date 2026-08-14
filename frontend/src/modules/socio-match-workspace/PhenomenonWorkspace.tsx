import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'

import {
  confirmEditedPhenomenonViaApi,
  listPhenomenonExamplesViaApi,
  restorePhenomenonViaApi,
  startMaterialViaApi,
  startPhenomenonViaApi,
} from './researchTaskApi'
import type {
  PhenomenonCandidate,
  PhenomenonExample,
  PhenomenonSnapshot,
  SeedTheoryStart,
} from './researchTaskModel'
import './workspace.css'

type EntryMethod = 'direct' | 'material' | 'smart'

interface NewResearchPageProps {
  readonly onStarted: (taskId: string) => void
  readonly seedTheory?: SeedTheoryStart | null
}

export function NewResearchPage({ onStarted, seedTheory = null }: NewResearchPageProps) {
  const [method, setMethod] = useState<EntryMethod>('direct')
  const [phenomenon, setPhenomenon] = useState('')
  const [researchIntent, setResearchIntent] = useState('')
  const [context, setContext] = useState('')
  const [exampleSource, setExampleSource] = useState<string | null>(null)
  const [pastedText, setPastedText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [consents, setConsents] = useState([false, false, false, false])
  const examples = useQuery({
    queryKey: ['phenomenon-examples'],
    queryFn: listPhenomenonExamplesViaApi,
    retry: false,
  })
  const directStart = useMutation({
    mutationFn: startPhenomenonViaApi,
    onSuccess: (result) => onStarted(result.taskId),
  })
  const materialStart = useMutation({
    mutationFn: startMaterialViaApi,
    onSuccess: (result) => onStarted(result.taskId),
  })

  function fillExample(example: PhenomenonExample) {
    setPhenomenon(example.phenomenon)
    setResearchIntent(example.researchIntent ?? '')
    setContext(example.context ?? '')
    setExampleSource(example.exampleId)
  }

  function submitDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    directStart.mutate({
      phenomenon: phenomenon.trim(),
      researchIntent: researchIntent.trim(),
      context: context.trim(),
      seedTheory,
    })
  }

  function submitMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    materialStart.mutate({
      pastedText: pastedText.trim(),
      file,
      researchIntent: researchIntent.trim(),
      context: context.trim(),
      processingPolicyVersion: '2026-08-08',
      seedTheory,
    })
  }

  const setConsent = (index: number, checked: boolean) => {
    setConsents((current) => current.map((value, item) => item === index ? checked : value))
  }

  return (
    <section className="research-entry">
      {seedTheory?.name ? <p className="seed-clue">起始线索：{seedTheory.name}</p> : null}
      <nav className="entry-methods" aria-label="研究进入方式">
        <button type="button" aria-pressed={method === 'direct'} onClick={() => setMethod('direct')}>直接输入</button>
        <button type="button" aria-pressed={method === 'material'} onClick={() => setMethod('material')}>单份材料</button>
        <button type="button" aria-pressed={method === 'smart'} onClick={() => setMethod('smart')}>智能选题</button>
      </nav>

      {method === 'direct' ? (
        <form className="phenomenon-form" onSubmit={submitDirect}>
          <label htmlFor="direct-phenomenon">你观察到的现象</label>
          <textarea
            id="direct-phenomenon"
            value={phenomenon}
            onChange={(event) => {
              setPhenomenon(event.target.value)
              setExampleSource(null)
            }}
            placeholder="一句观察、一段描述、一个初步问题或研究困惑"
            required
            rows={6}
          />
          <label htmlFor="direct-intent">研究意图（可选）</label>
          <textarea id="direct-intent" value={researchIntent} onChange={(event) => setResearchIntent(event.target.value)} rows={2} />
          <label htmlFor="direct-context">语境（可选）</label>
          <textarea id="direct-context" value={context} onChange={(event) => setContext(event.target.value)} rows={2} />
          <article className={`content-mark content-mark--${exampleSource ? 'analysis' : 'user'}`}>
            <span className="content-mark__label">
              {exampleSource ? '系统分析' : '用户内容'}
            </span>
            <p>{exampleSource ? '当前内容来自内置案例' : '当前内容由你输入'}</p>
          </article>
          <button type="submit" disabled={directStart.isPending || !phenomenon.trim()}>
            {directStart.isPending ? '正在生成候选…' : '生成可编辑候选'}
          </button>
          {directStart.isError ? <p role="alert">暂时无法生成候选，输入内容仍未丢失。</p> : null}
          <section className="example-list" aria-label="内置案例">
            <h2>也可以从内置案例开始</h2>
            {examples.isPending ? <p role="status">正在加载案例…</p> : null}
            {examples.data?.map((example) => (
              <button key={example.exampleId} type="button" onClick={() => fillExample(example)}>{example.title}</button>
            ))}
          </section>
        </form>
      ) : null}

      {method === 'material' ? (
        <form className="phenomenon-form" onSubmit={submitMaterial}>
          <label htmlFor="material-text">粘贴去标识化材料</label>
          <textarea id="material-text" rows={8} value={pastedText} onChange={(event) => setPastedText(event.target.value)} disabled={file !== null} />
          <label htmlFor="material-file">或上传一份 TXT / DOCX</label>
          <input id="material-file" type="file" accept=".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <fieldset className="processing-consents">
            <legend>提交前确认</legend>
            <label><input type="checkbox" checked={consents[0]} onChange={(event) => setConsent(0, event.target.checked)} />我确认材料已去标识化</label>
            <label><input type="checkbox" checked={consents[1]} onChange={(event) => setConsent(1, event.target.checked)} />我有权处理并提交这份材料</label>
            <label><input type="checkbox" checked={consents[2]} onChange={(event) => setConsent(2, event.target.checked)} />我知悉材料可能由外部模型服务处理</label>
            <label><input type="checkbox" checked={consents[3]} onChange={(event) => setConsent(3, event.target.checked)} />我同意当前处理政策版本</label>
          </fieldset>
          <button type="submit" disabled={materialStart.isPending || (!pastedText.trim() && !file) || !consents.every(Boolean)}>
            {materialStart.isPending ? '正在提取候选…' : '提取现象候选'}
          </button>
          {materialStart.isError ? <p role="alert">材料处理失败，请检查文件与确认项。</p> : null}
        </form>
      ) : null}

      {method === 'smart' ? (
        <section className="smart-topic-placeholder">
          <h2>智能选题即将开放</h2>
          <p>当前模块只保留入口，不生成题目或研究结论。</p>
          <button type="button" disabled>暂未开放</button>
        </section>
      ) : null}
    </section>
  )
}

function originLabel(candidate: PhenomenonCandidate) {
  return candidate.contentOrigin === 'user_modified' ? '用户修改' : '系统生成'
}

export function PhenomenonWorkspace({ taskId }: { readonly taskId: string }) {
  const restored = useQuery({
    queryKey: ['phenomenon', taskId],
    queryFn: () => restorePhenomenonViaApi(taskId),
    retry: false,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [phenomenon, setPhenomenon] = useState('')
  const [researchIntent, setResearchIntent] = useState('')
  const [context, setContext] = useState('')
  const [confirmed, setConfirmed] = useState<PhenomenonSnapshot | null>(null)
  const [confirmedAsUserModified, setConfirmedAsUserModified] = useState(false)
  const selected = restored.data?.candidates.find((item) => item.candidateId === selectedId)
    ?? restored.data?.candidate

  useEffect(() => {
    if (!selected) return
    setSelectedId(selected.candidateId)
    setPhenomenon(selected.phenomenon)
    setResearchIntent(selected.researchIntent ?? '')
    setContext(selected.context ?? '')
    setConfirmed(restored.data?.snapshot ?? null)
  }, [selected, restored.data?.snapshot])

  const confirmation = useMutation({
    mutationFn: async () => {
      const values = { phenomenon, researchIntent, context }
      const modified = phenomenon.trim() !== selected!.phenomenon
        || (researchIntent.trim() || null) !== selected!.researchIntent
        || (context.trim() || null) !== selected!.context
      return {
        snapshot: await confirmEditedPhenomenonViaApi(selected!, values),
        modified,
      }
    },
    onSuccess: ({ snapshot, modified }) => {
      setConfirmedAsUserModified(modified)
      setConfirmed(snapshot)
    },
  })

  if (restored.isPending) return <p role="status">正在恢复现象候选…</p>
  if (restored.isError || !restored.data || !selected) return <p role="alert">暂时无法恢复这条现象候选。</p>

  const seed = restored.data.seedTheory
  if (confirmed) {
    return (
      <section className="confirmed-phenomenon">
        {seed ? <p className="seed-clue">起始线索：{seed.name}</p> : null}
        <p className="eyebrow">现象已经确认并保存</p>
        <p className="origin-badge">{confirmedAsUserModified ? '用户修改' : originLabel(selected)}</p>
        <h2>{confirmed.phenomenon}</h2>
        <p>刷新页面后仍会从后端快照恢复。</p>
        <p className="snapshot-hash">快照 {confirmed.contentHash.slice(0, 12)}</p>
        {selected.evidence.map((item) => (
          <p key={item.evidenceRefId}><strong>{item.sourceDescription ?? item.evidenceRefId}</strong>{item.locator ? ` · ${item.locator}` : ''} · {item.useBoundary}</p>
        ))}
        <a className="text-link" href={`/research/${taskId}/match`}>进入理论匹配</a>
        <span aria-hidden="true"> · </span>
        <a className="text-link" href="/my">返回我的研究</a>
      </section>
    )
  }

  return (
    <section className="phenomenon-workspace">
      {seed ? <p className="seed-clue">起始线索：{seed.name}</p> : null}
      {restored.data.candidates.length > 1 ? (
        <nav className="candidate-tabs" aria-label="现象候选">
          {restored.data.candidates.map((item, index) => (
            <button type="button" key={item.candidateId} aria-pressed={item.candidateId === selected.candidateId} onClick={() => setSelectedId(item.candidateId)}>候选 {index + 1}</button>
          ))}
        </nav>
      ) : null}
      <form className="phenomenon-form" onSubmit={(event) => { event.preventDefault(); confirmation.mutate() }}>
        <p className="origin-badge">{originLabel(selected)}</p>
        <p className="model-badge">{selected.modelLabel}</p>
        <label htmlFor="candidate-phenomenon">现象表述</label>
        <textarea id="candidate-phenomenon" rows={5} value={phenomenon} onChange={(event) => setPhenomenon(event.target.value)} required />
        <label htmlFor="research-intent">研究意图（可选）</label>
        <textarea id="research-intent" rows={3} value={researchIntent} onChange={(event) => setResearchIntent(event.target.value)} />
        <label htmlFor="phenomenon-context">语境（可选）</label>
        <textarea id="phenomenon-context" rows={3} value={context} onChange={(event) => setContext(event.target.value)} />
        <section className="evidence-card" aria-label="依据来源">
          <h2>依据来源</h2>
          {selected.evidence.map((item) => (
            <article key={item.evidenceRefId}>
              <strong>{item.sourceDescription ?? item.evidenceRefId}{item.locator ? ` · ${item.locator}` : ''}</strong>
              <p>{item.excerpt}</p>
              <small>{item.useBoundary}</small>
            </article>
          ))}
          {selected.missingInformation.length ? <p>仍缺：{selected.missingInformation.join('、')}</p> : null}
          <p>来源追溯：{selected.sourceTraceability === 'traceable' ? '可追溯' : '不完整'}</p>
        </section>
        <button type="submit" disabled={confirmation.isPending || !phenomenon.trim()}>{confirmation.isPending ? '正在确认…' : '确认这个现象'}</button>
        {confirmation.isError ? <p role="alert">确认失败，修改内容仍保留在页面中。</p> : null}
        <div className="next-step-gate">
          <button type="button" disabled>进入理论匹配</button>
          <p>确认现象后才能进入理论匹配</p>
        </div>
      </form>
    </section>
  )
}
