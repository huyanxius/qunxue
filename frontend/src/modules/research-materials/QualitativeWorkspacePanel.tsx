import { useMemo, useState } from 'react'

import type {
  CodebookLifecycle,
  ConfigureCodebookEntryInput,
  CreateAnalysisMemoLinkInput,
  CreateAnalysisThemeInput,
  MatrixSubjectKind,
  ResearchAnalysisSnapshot,
  SaveAnalysisCaseProfileInput,
  SaveCaseThemeMatrixCellInput,
  SetQualitativeMethodInput,
  TransitionCodebookEntryInput,
} from './researchAnalysisModel'

type QualitativeWorkspacePanelProps = {
  readonly snapshot: ResearchAnalysisSnapshot
  readonly onConfigureCodebook: (codeId: string, body: ConfigureCodebookEntryInput) => void | Promise<void>
  readonly onTransitionCodebook: (codeId: string, body: TransitionCodebookEntryInput) => void | Promise<void>
  readonly onCreateTheme: (body: CreateAnalysisThemeInput) => void | Promise<void>
  readonly onConfirmTheme: (themeId: string, reason: string, expectedVersion: number) => void | Promise<void>
  readonly onAttachMemo: (body: CreateAnalysisMemoLinkInput) => void | Promise<void>
  readonly onSaveCaseProfile: (body: SaveAnalysisCaseProfileInput) => void | Promise<void>
  readonly onSaveMatrixCell: (body: SaveCaseThemeMatrixCellInput) => void | Promise<void>
  readonly onSetMethod: (body: SetQualitativeMethodInput) => void | Promise<void>
}

type WorkspaceTab = 'codebook' | 'themes' | 'cases' | 'matrix'

const lifecycleLabels: Record<CodebookLifecycle, string> = {
  active: '使用中', merged: '已合并', split: '已拆分', retired: '已停用',
}

const findingLabels: Record<string, string> = {
  support: '支持', counterexample: '反例', contradict: '矛盾', competing_explanation: '竞争解释', evidence_gap: '缺口',
}

function toggle(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}

function lines(value: string): string[] {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

export function QualitativeWorkspacePanel({
  snapshot,
  onConfigureCodebook,
  onTransitionCodebook,
  onCreateTheme,
  onConfirmTheme,
  onAttachMemo,
  onSaveCaseProfile,
  onSaveMatrixCell,
  onSetMethod,
}: QualitativeWorkspacePanelProps) {
  const workspace = snapshot.workspace
  const methodPresets = snapshot.method_presets ?? []
  const [tab, setTab] = useState<WorkspaceTab>('codebook')
  const [selectedMethod, setSelectedMethod] = useState(workspace?.method_preset.method ?? methodPresets[0]?.method)
  const [error, setError] = useState<string | null>(null)

  if (!workspace || !selectedMethod) return null
  const preset = methodPresets.find((item) => item.method === selectedMethod)

  async function run(operation: () => void | Promise<void>, fallback: string): Promise<boolean> {
    setError(null)
    try {
      await operation()
      return true
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : fallback)
      return false
    }
  }

  async function report(operation: () => void | Promise<void>, fallback: string): Promise<void> {
    await run(operation, fallback)
  }

  async function setMethod(method: typeof selectedMethod) {
    const previousMethod = selectedMethod
    setSelectedMethod(method)
    const saved = await run(
      () => onSetMethod({
        method,
        expected_version: workspace.method_preset.version || null,
      }),
      '方法取向未保存。',
    )
    if (!saved) setSelectedMethod(previousMethod)
  }

  return (
    <section className="qual-workspace" aria-label="社会学质性分析工作区">
      <header className="qual-workspace__method">
        <label>
          <span>方法取向</span>
          <select aria-label="方法取向" value={selectedMethod} onChange={(event) => { void setMethod(event.target.value as typeof selectedMethod) }}>
            {methodPresets.map((item) => <option key={item.method} value={item.method}>{item.label}</option>)}
          </select>
        </label>
        {preset ? <div><strong>{preset.matrix_axes.join(' × ')}</strong><p>{preset.prompts}</p><small>{preset.guardrails}</small></div> : null}
      </header>
      {error ? <p role="alert" className="qual-workspace__error">{error}</p> : null}

      {workspace.candidate_themes.length ? (
        <section className="qual-workspace__theme-candidates" aria-label="待确认主题">
          <span>Agent 主题候选 · 待确认</span>
          {workspace.candidate_themes.map((theme) => <ThemeCandidate key={theme.theme_id} theme={theme} onConfirm={(themeId, reason, expectedVersion) => report(() => onConfirmTheme(themeId, reason, expectedVersion), '主题确认未保存。')} />)}
        </section>
      ) : null}

      <nav className="qual-workspace__tabs" aria-label="质性分析对象">
        <button type="button" aria-pressed={tab === 'codebook'} onClick={() => setTab('codebook')}>代码本</button>
        <button type="button" aria-pressed={tab === 'themes'} onClick={() => setTab('themes')}>主题与备忘</button>
        <button type="button" aria-pressed={tab === 'cases'} onClick={() => setTab('cases')}>个案档案</button>
        <button type="button" aria-pressed={tab === 'matrix'} onClick={() => setTab('matrix')}>个案 × 主题矩阵</button>
      </nav>

      {tab === 'codebook' ? <CodebookPanel snapshot={snapshot} onConfigure={(codeId, body) => report(() => onConfigureCodebook(codeId, body), '代码本边界未保存。')} onTransition={(codeId, body) => report(() => onTransitionCodebook(codeId, body), '代码本状态未保存。')} /> : null}
      {tab === 'themes' ? <ThemesAndMemosPanel snapshot={snapshot} onCreateTheme={(body) => report(() => onCreateTheme(body), '分析主题未保存。')} onAttachMemo={(body) => report(() => onAttachMemo(body), '备忘挂接未保存。')} /> : null}
      {tab === 'cases' ? <CaseProfilesPanel snapshot={snapshot} onSave={(body) => report(() => onSaveCaseProfile(body), '个案档案未保存。')} /> : null}
      {tab === 'matrix' ? <CaseThemeMatrixPanel snapshot={snapshot} onSave={(body) => report(() => onSaveMatrixCell(body), '比较矩阵单元未保存。')} /> : null}
    </section>
  )
}

function ThemeCandidate({ theme, onConfirm }: {
  theme: NonNullable<ResearchAnalysisSnapshot['workspace']>['candidate_themes'][number]
  onConfirm: QualitativeWorkspacePanelProps['onConfirmTheme']
}) {
  const [reason, setReason] = useState('')
  return (
    <article>
      <strong>{theme.label}</strong>
      <p>{theme.central_concept}</p>
      <label><span>确认依据</span><input aria-label={`主题确认依据：${theme.label}`} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <button type="button" disabled={!reason.trim()} onClick={() => { void onConfirm(theme.theme_id, reason.trim(), theme.version) }}>确认主题</button>
    </article>
  )
}

function CodebookPanel({ snapshot, onConfigure, onTransition }: {
  snapshot: ResearchAnalysisSnapshot
  onConfigure: QualitativeWorkspacePanelProps['onConfigureCodebook']
  onTransition: QualitativeWorkspacePanelProps['onTransitionCodebook']
}) {
  const [editingCodeId, setEditingCodeId] = useState<string | null>(null)
  const entries = snapshot.workspace?.codebook_entries ?? []
  const confirmedCodes = snapshot.codes.filter((item) => item.status === 'confirmed')
  return (
    <section className="qual-codebook" aria-label="代码本">
      {confirmedCodes.map((code) => {
        const entry = entries.find((item) => item.code_id === code.code_id)
        return (
          <article key={code.code_id}>
            <header><div><strong>{code.label}</strong><p>{code.definition}</p></div><span>{entry ? `v${entry.version} · ${lifecycleLabels[entry.lifecycle]}` : '边界待补全'}</span></header>
            {entry ? <><dl><dt>纳入</dt><dd>{entry.inclusion_rules.join('；')}</dd><dt>排除</dt><dd>{entry.exclusion_rules.join('；')}</dd><dt>例证</dt><dd>{entry.positive_example_annotation_ids.length} 个正例 · {entry.negative_example_annotation_ids.length} 个反例</dd></dl><CodeLifecycleEditor codeId={code.code_id} entry={entry} codes={confirmedCodes} onTransition={onTransition} /></> : null}
            <button type="button" aria-label={`${entry ? '修订' : '补全'}代码本：${code.label}`} onClick={() => setEditingCodeId(code.code_id)}>{entry ? '修订边界' : '补全代码本'}</button>
            {editingCodeId === code.code_id ? <CodebookForm code={code} entry={entry} annotations={snapshot.annotations} codes={confirmedCodes} onCancel={() => setEditingCodeId(null)} onSave={onConfigure} /> : null}
          </article>
        )
      })}
      {!confirmedCodes.length ? <p>确认编码后，代码本会在这里形成。</p> : null}
    </section>
  )
}

function CodebookForm({ code, entry, annotations, codes, onCancel, onSave }: {
  code: ResearchAnalysisSnapshot['codes'][number]
  entry: NonNullable<ResearchAnalysisSnapshot['workspace']>['codebook_entries'][number] | undefined
  annotations: ResearchAnalysisSnapshot['annotations']
  codes: ResearchAnalysisSnapshot['codes']
  onCancel: () => void
  onSave: QualitativeWorkspacePanelProps['onConfigureCodebook']
}) {
  const [included, setIncluded] = useState(entry?.inclusion_rules.join('\n') ?? '')
  const [excluded, setExcluded] = useState(entry?.exclusion_rules.join('\n') ?? '')
  const [parent, setParent] = useState(entry?.parent_code_id ?? '')
  const [positive, setPositive] = useState(entry?.positive_example_annotation_ids ?? [])
  const [negative, setNegative] = useState(entry?.negative_example_annotation_ids ?? [])
  const canSave = lines(included).length && lines(excluded).length && positive.length && negative.length
  return (
    <form aria-label={`编辑代码本：${code.label}`} onSubmit={(event) => { event.preventDefault(); if (!canSave) return; void onSave(code.code_id, { expected_version: entry?.version ?? null, inclusion_rules: lines(included), exclusion_rules: lines(excluded), parent_code_id: parent || null, positive_example_annotation_ids: positive, negative_example_annotation_ids: negative }) }}>
      <label><span>纳入规则 <small>每行一条</small></span><textarea aria-label="纳入规则" value={included} onChange={(event) => setIncluded(event.target.value)} /></label>
      <label><span>排除规则 <small>每行一条</small></span><textarea aria-label="排除规则" value={excluded} onChange={(event) => setExcluded(event.target.value)} /></label>
      <label><span>上位代码</span><select aria-label="上位代码" value={parent} onChange={(event) => setParent(event.target.value)}><option value="">无</option>{codes.filter((item) => item.code_id !== code.code_id).map((item) => <option key={item.code_id} value={item.code_id}>{item.label}</option>)}</select></label>
      <fieldset><legend>正例</legend>{annotations.map((item) => <label key={item.annotation_id}><input type="checkbox" aria-label={`正例：${item.quote}`} checked={positive.includes(item.annotation_id)} onChange={() => setPositive(toggle(positive, item.annotation_id))} /><span>{item.quote}</span></label>)}</fieldset>
      <fieldset><legend>反例</legend>{annotations.map((item) => <label key={item.annotation_id}><input type="checkbox" aria-label={`反例：${item.quote}`} checked={negative.includes(item.annotation_id)} onChange={() => setNegative(toggle(negative, item.annotation_id))} /><span>{item.quote}</span></label>)}</fieldset>
      <footer><button type="button" onClick={onCancel}>取消</button><button type="submit" disabled={!canSave}>保存代码本边界</button></footer>
    </form>
  )
}

function CodeLifecycleEditor({ codeId, entry, codes, onTransition }: {
  codeId: string
  entry: NonNullable<ResearchAnalysisSnapshot['workspace']>['codebook_entries'][number]
  codes: ResearchAnalysisSnapshot['codes']
  onTransition: QualitativeWorkspacePanelProps['onTransitionCodebook']
}) {
  const [open, setOpen] = useState(false)
  const [lifecycle, setLifecycle] = useState<CodebookLifecycle>('retired')
  const [related, setRelated] = useState<string[]>([])
  const [reason, setReason] = useState('')
  return <div className="qual-codebook__lifecycle"><button type="button" onClick={() => setOpen(!open)}>合并、拆分或停用</button>{open ? <form aria-label="变更代码生命周期" onSubmit={(event) => { event.preventDefault(); void onTransition(codeId, { expected_version: entry.version, lifecycle, related_code_ids: related, reason: reason.trim() }) }}><select aria-label="代码状态" value={lifecycle} onChange={(event) => setLifecycle(event.target.value as CodebookLifecycle)}><option value="merged">合并</option><option value="split">拆分</option><option value="retired">停用</option></select>{lifecycle !== 'retired' ? <fieldset><legend>关联代码</legend>{codes.filter((item) => item.code_id !== codeId).map((item) => <label key={item.code_id}><input type="checkbox" checked={related.includes(item.code_id)} onChange={() => setRelated(toggle(related, item.code_id))} />{item.label}</label>)}</fieldset> : null}<input aria-label="变更依据" value={reason} onChange={(event) => setReason(event.target.value)} /><button type="submit" disabled={!reason.trim() || (lifecycle !== 'retired' && !related.length)}>保存状态</button></form> : null}</div>
}

function ThemesAndMemosPanel({ snapshot, onCreateTheme, onAttachMemo }: {
  snapshot: ResearchAnalysisSnapshot
  onCreateTheme: QualitativeWorkspacePanelProps['onCreateTheme']
  onAttachMemo: QualitativeWorkspacePanelProps['onAttachMemo']
}) {
  const [mode, setMode] = useState<'theme' | 'memo' | null>(null)
  return <section className="qual-themes" aria-label="主题与备忘"><div className="qual-workspace__actions"><button type="button" onClick={() => setMode('theme')}>建立主题</button><button type="button" onClick={() => setMode('memo')}>挂接备忘</button></div>{snapshot.workspace?.formal_themes.map((theme) => <article key={theme.theme_id}><span>研究者确认 · 主题</span><strong>{theme.label}</strong><p>{theme.central_concept}</p><small>{theme.annotation_ids.length} 处原文 · {theme.code_ids.length} 个代码</small></article>)}{mode === 'theme' ? <ThemeForm snapshot={snapshot} onSave={onCreateTheme} /> : null}{mode === 'memo' ? <MemoLinkForm snapshot={snapshot} onSave={onAttachMemo} /> : null}</section>
}

function ThemeForm({ snapshot, onSave }: { snapshot: ResearchAnalysisSnapshot; onSave: QualitativeWorkspacePanelProps['onCreateTheme'] }) {
  const [label, setLabel] = useState(''); const [concept, setConcept] = useState(''); const [codes, setCodes] = useState<string[]>([]); const [annotations, setAnnotations] = useState<string[]>([])
  return <form aria-label="建立主题" onSubmit={(event) => { event.preventDefault(); void onSave({ label: label.trim(), central_concept: concept.trim(), code_ids: codes, annotation_ids: annotations }) }}><label><span>主题名称</span><input value={label} onChange={(event) => setLabel(event.target.value)} /></label><label><span>中心组织概念</span><textarea value={concept} onChange={(event) => setConcept(event.target.value)} /></label><fieldset><legend>关联代码</legend>{snapshot.codes.filter((item) => item.status === 'confirmed').map((item) => <label key={item.code_id}><input type="checkbox" checked={codes.includes(item.code_id)} onChange={() => setCodes(toggle(codes, item.code_id))} />{item.label}</label>)}</fieldset><fieldset><legend>主题原文</legend>{snapshot.annotations.map((item) => <label key={item.annotation_id}><input type="checkbox" checked={annotations.includes(item.annotation_id)} onChange={() => setAnnotations(toggle(annotations, item.annotation_id))} />{item.quote}</label>)}</fieldset><button type="submit" disabled={!label.trim() || !concept.trim() || !codes.length || !annotations.length}>保存主题</button></form>
}

function MemoLinkForm({ snapshot, onSave }: { snapshot: ResearchAnalysisSnapshot; onSave: QualitativeWorkspacePanelProps['onAttachMemo'] }) {
  const [memoId, setMemoId] = useState(''); const [kind, setKind] = useState<CreateAnalysisMemoLinkInput['target_kind']>('project'); const [target, setTarget] = useState(snapshot.task_id); const [annotations, setAnnotations] = useState<string[]>([])
  return <form aria-label="挂接备忘" onSubmit={(event) => { event.preventDefault(); void onSave({ memo_id: memoId, target_kind: kind, target_ref: target.trim(), annotation_ids: annotations }) }}><select aria-label="备忘" value={memoId} onChange={(event) => setMemoId(event.target.value)}><option value="">选择备忘</option>{snapshot.memos.filter((item) => item.status === 'confirmed').map((item) => <option key={item.memo_id} value={item.memo_id}>{item.title}</option>)}</select><select aria-label="挂接对象" value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>{['project', 'material', 'source', 'code', 'case', 'comparison', 'draft'].map((item) => <option key={item} value={item}>{item}</option>)}</select><input aria-label="对象引用" value={target} onChange={(event) => setTarget(event.target.value)} /><fieldset><legend>备忘原文</legend>{snapshot.annotations.map((item) => <label key={item.annotation_id}><input type="checkbox" checked={annotations.includes(item.annotation_id)} onChange={() => setAnnotations(toggle(annotations, item.annotation_id))} />{item.quote}</label>)}</fieldset><button type="submit" disabled={!memoId || !target.trim() || !annotations.length}>保存挂接</button></form>
}

function CaseProfilesPanel({ snapshot, onSave }: { snapshot: ResearchAnalysisSnapshot; onSave: QualitativeWorkspacePanelProps['onSaveCaseProfile'] }) {
  const [open, setOpen] = useState(false)
  return <section className="qual-cases" aria-label="个案档案"><button type="button" onClick={() => setOpen(true)}>建立个案档案</button>{snapshot.workspace?.case_profiles.map((profile) => <article key={profile.profile_id}><strong>{profile.display_label}</strong><span>{profile.attributes.map((item) => `${item.name}：${item.value}`).join(' · ')}</span><p>{profile.summary}</p><small>{profile.annotation_ids.length} 处原文 · {profile.memo_ids.length} 则备忘</small></article>)}{open ? <CaseProfileForm snapshot={snapshot} onSave={onSave} /> : null}</section>
}

function CaseProfileForm({ snapshot, onSave }: { snapshot: ResearchAnalysisSnapshot; onSave: QualitativeWorkspacePanelProps['onSaveCaseProfile'] }) {
  const [caseRef, setCaseRef] = useState(''); const [label, setLabel] = useState(''); const [attributeName, setAttributeName] = useState(''); const [attributeValue, setAttributeValue] = useState(''); const [summary, setSummary] = useState(''); const [annotations, setAnnotations] = useState<string[]>([]); const [memos, setMemos] = useState<string[]>([])
  return <form aria-label="建立个案档案" onSubmit={(event) => { event.preventDefault(); void onSave({ expected_version: null, case_ref: caseRef.trim(), display_label: label.trim(), attributes: attributeName.trim() && attributeValue.trim() ? [{ name: attributeName.trim(), value: attributeValue.trim() }] : [], summary: summary.trim(), annotation_ids: annotations, memo_ids: memos }) }}><p>个案引用只接收上游稳定标识，本工作区不从显示名称推断身份。</p><label><span>个案引用</span><input aria-label="个案引用" value={caseRef} onChange={(event) => setCaseRef(event.target.value)} /></label><label><span>显示名称</span><input aria-label="显示名称" value={label} onChange={(event) => setLabel(event.target.value)} /></label><div><label><span>属性名称</span><input aria-label="属性名称" value={attributeName} onChange={(event) => setAttributeName(event.target.value)} /></label><label><span>属性值</span><input aria-label="属性值" value={attributeValue} onChange={(event) => setAttributeValue(event.target.value)} /></label></div><label><span>个案摘要</span><textarea aria-label="个案摘要" value={summary} onChange={(event) => setSummary(event.target.value)} /></label><fieldset><legend>原文证据</legend>{snapshot.annotations.map((item) => <label key={item.annotation_id}><input type="checkbox" aria-label={`个案原文：${item.quote}`} checked={annotations.includes(item.annotation_id)} onChange={() => setAnnotations(toggle(annotations, item.annotation_id))} />{item.quote}</label>)}</fieldset><fieldset><legend>关联备忘</legend>{snapshot.memos.filter((item) => item.status === 'confirmed').map((item) => <label key={item.memo_id}><input type="checkbox" aria-label={`个案备忘：${item.title}`} checked={memos.includes(item.memo_id)} onChange={() => setMemos(toggle(memos, item.memo_id))} />{item.title}</label>)}</fieldset><button type="submit" disabled={!caseRef.trim() || !label.trim() || !summary.trim() || !annotations.length}>保存个案档案</button></form>
}

function CaseThemeMatrixPanel({ snapshot, onSave }: { snapshot: ResearchAnalysisSnapshot; onSave: QualitativeWorkspacePanelProps['onSaveMatrixCell'] }) {
  const workspace = snapshot.workspace
  const [open, setOpen] = useState(false)
  const subjects = useMemo(() => [
    ...snapshot.codes.filter((item) => item.status === 'confirmed').map((item) => ({ kind: 'code' as MatrixSubjectKind, id: item.code_id, label: item.label })),
    ...(workspace?.formal_themes ?? []).map((item) => ({ kind: 'theme' as MatrixSubjectKind, id: item.theme_id, label: item.label })),
  ], [snapshot.codes, workspace?.formal_themes])
  return <section className="qual-matrix" aria-label="个案主题矩阵"><button type="button" onClick={() => setOpen(true)}>补充矩阵单元</button><div className="qual-matrix__table" role="table"><div role="row" className="qual-matrix__row"><span role="columnheader">个案</span>{subjects.map((item) => <span role="columnheader" key={`${item.kind}:${item.id}`}>{item.label}</span>)}</div>{workspace?.case_profiles.map((profile) => <div role="row" className="qual-matrix__row" key={profile.profile_id}><strong role="rowheader">{profile.display_label}</strong>{subjects.map((subject) => { const cell = workspace.matrix_cells.find((item) => item.case_profile_id === profile.profile_id && item.subject_kind === subject.kind && item.subject_id === subject.id); return <article role="cell" key={`${profile.profile_id}:${subject.kind}:${subject.id}`}>{cell ? <><p>{cell.summary}</p><small>{cell.annotation_ids.length} 处原文 · {cell.memo_ids.length} 则备忘</small><div>{cell.finding_kinds.map((kind) => <span key={kind}>{findingLabels[kind]}</span>)}</div></> : <span>尚未分析</span>}</article> })}</div>)}</div>{open ? <MatrixCellForm snapshot={snapshot} subjects={subjects} onSave={onSave} /> : null}</section>
}

function MatrixCellForm({ snapshot, subjects, onSave }: { snapshot: ResearchAnalysisSnapshot; subjects: { kind: MatrixSubjectKind; id: string; label: string }[]; onSave: QualitativeWorkspacePanelProps['onSaveMatrixCell'] }) {
  const [profile, setProfile] = useState(''); const [subjectKey, setSubjectKey] = useState(''); const [summary, setSummary] = useState(''); const [annotations, setAnnotations] = useState<string[]>([]); const [memos, setMemos] = useState<string[]>([]); const [findings, setFindings] = useState<string[]>([])
  const subject = subjects.find((item) => `${item.kind}:${item.id}` === subjectKey)
  return <form aria-label="补充矩阵单元" onSubmit={(event) => { event.preventDefault(); if (!subject) return; void onSave({ expected_version: null, case_profile_id: profile, subject_kind: subject.kind, subject_id: subject.id, summary: summary.trim(), annotation_ids: annotations, memo_ids: memos, finding_kinds: findings as SaveCaseThemeMatrixCellInput['finding_kinds'] }) }}><select aria-label="矩阵个案" value={profile} onChange={(event) => setProfile(event.target.value)}><option value="">选择个案</option>{snapshot.workspace?.case_profiles.map((item) => <option key={item.profile_id} value={item.profile_id}>{item.display_label}</option>)}</select><select aria-label="矩阵代码或主题" value={subjectKey} onChange={(event) => setSubjectKey(event.target.value)}><option value="">选择代码或主题</option>{subjects.map((item) => <option key={`${item.kind}:${item.id}`} value={`${item.kind}:${item.id}`}>{item.label}</option>)}</select><textarea aria-label="矩阵摘要" value={summary} onChange={(event) => setSummary(event.target.value)} /><fieldset><legend>原文</legend>{snapshot.annotations.map((item) => <label key={item.annotation_id}><input type="checkbox" checked={annotations.includes(item.annotation_id)} onChange={() => setAnnotations(toggle(annotations, item.annotation_id))} />{item.quote}</label>)}</fieldset><fieldset><legend>备忘</legend>{snapshot.memos.filter((item) => item.status === 'confirmed').map((item) => <label key={item.memo_id}><input type="checkbox" checked={memos.includes(item.memo_id)} onChange={() => setMemos(toggle(memos, item.memo_id))} />{item.title}</label>)}</fieldset><fieldset><legend>判断</legend>{Object.entries(findingLabels).map(([kind, label]) => <label key={kind}><input type="checkbox" checked={findings.includes(kind)} onChange={() => setFindings(toggle(findings, kind))} />{label}</label>)}</fieldset><button type="submit" disabled={!profile || !subject || !summary.trim() || !annotations.length}>保存矩阵单元</button></form>
}

export type { QualitativeWorkspacePanelProps }
