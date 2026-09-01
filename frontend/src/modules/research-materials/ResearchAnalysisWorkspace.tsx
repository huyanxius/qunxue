import { useMemo, useState } from 'react'

import type {
  AnalysisMemoKind,
  ConfigureCodebookEntryInput,
  CreateAnalysisCodeInput,
  CreateAnalysisMemoLinkInput,
  CreateAnalysisMemoInput,
  CreateAnalysisThemeInput,
  CreateCaseComparisonInput,
  ResearchAnalysisSnapshot,
  SaveAnalysisCaseProfileInput,
  SaveCaseThemeMatrixCellInput,
  SetQualitativeMethodInput,
  TransitionCodebookEntryInput,
} from './researchAnalysisModel'
import { QualitativeWorkspacePanel } from './QualitativeWorkspacePanel'
import {
  ResearchAnalysisCandidateCard,
  type ResearchAnalysisDecision,
} from './ResearchAnalysisCandidateCard'
import {
  ResearchCaseComparison,
  type CaseComparisonDecision,
} from './ResearchCaseComparison'
import { formatMaterialLocator } from './researchMaterialsModel'

type ResearchAnalysisWorkspaceProps = {
  readonly snapshot: ResearchAnalysisSnapshot
  readonly selectedMaterialId: string | null
  readonly materialNames?: Readonly<Record<string, string>>
  readonly onCreateCode: (body: CreateAnalysisCodeInput) => void | Promise<void>
  readonly onCreateMemo: (body: CreateAnalysisMemoInput) => void | Promise<void>
  readonly onDecideCode: (codeId: string, decision: ResearchAnalysisDecision, reason: string, expectedVersion: number) => void | Promise<void>
  readonly onDecideMemo: (memoId: string, decision: ResearchAnalysisDecision, reason: string, expectedVersion: number) => void | Promise<void>
  readonly onCreateComparison?: (body: CreateCaseComparisonInput) => void | Promise<void>
  readonly onDecideComparison?: (comparisonId: string, decision: CaseComparisonDecision, reason: string, expectedVersion: number) => void | Promise<void>
  readonly onConfigureCodebook?: (codeId: string, body: ConfigureCodebookEntryInput) => void | Promise<void>
  readonly onTransitionCodebook?: (codeId: string, body: TransitionCodebookEntryInput) => void | Promise<void>
  readonly onCreateTheme?: (body: CreateAnalysisThemeInput) => void | Promise<void>
  readonly onConfirmTheme?: (themeId: string, reason: string, expectedVersion: number) => void | Promise<void>
  readonly onAttachMemo?: (body: CreateAnalysisMemoLinkInput) => void | Promise<void>
  readonly onSaveCaseProfile?: (body: SaveAnalysisCaseProfileInput) => void | Promise<void>
  readonly onSaveMatrixCell?: (body: SaveCaseThemeMatrixCellInput) => void | Promise<void>
  readonly onSetMethod?: (body: SetQualitativeMethodInput) => void | Promise<void>
}

const memoKindLabels: Record<AnalysisMemoKind, string> = {
  descriptive: '描述备忘',
  reflexive: '反思备忘',
  analytic: '分析备忘',
  methodological: '方法备忘',
}

export function ResearchAnalysisWorkspace({
  snapshot,
  selectedMaterialId,
  materialNames,
  onCreateCode,
  onCreateMemo,
  onDecideCode,
  onDecideMemo,
  onCreateComparison,
  onDecideComparison,
  onConfigureCodebook,
  onTransitionCodebook,
  onCreateTheme,
  onConfirmTheme,
  onAttachMemo,
  onSaveCaseProfile,
  onSaveMatrixCell,
  onSetMethod,
}: ResearchAnalysisWorkspaceProps) {
  const [scope, setScope] = useState<'material' | 'task'>(selectedMaterialId ? 'material' : 'task')
  const [composer, setComposer] = useState<'code' | 'memo' | null>(null)
  const [selectedAnnotationIds, setSelectedAnnotationIds] = useState<string[]>([])
  const [selectedCodeIds, setSelectedCodeIds] = useState<string[]>([])
  const [codeLabel, setCodeLabel] = useState('')
  const [codeDefinition, setCodeDefinition] = useState('')
  const [codeRationale, setCodeRationale] = useState('')
  const [memoTitle, setMemoTitle] = useState('')
  const [memoContent, setMemoContent] = useState('')
  const [memoKind, setMemoKind] = useState<AnalysisMemoKind>('analytic')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const visibleAnnotations = useMemo(() => (
    scope === 'material' && selectedMaterialId
      ? snapshot.annotations.filter((annotation) => annotation.material_id === selectedMaterialId)
      : snapshot.annotations
  ), [scope, selectedMaterialId, snapshot.annotations])
  const confirmedCodes = snapshot.codes.filter((code) => code.status === 'confirmed')
  const candidateCodes = snapshot.codes.filter((code) => code.status === 'candidate' && code.source === 'agent')
  const confirmedMemos = snapshot.memos.filter((memo) => memo.status === 'confirmed')
  const candidateMemos = snapshot.memos.filter((memo) => memo.status === 'candidate' && memo.source === 'agent')

  function toggle(values: string[], value: string, setValues: (next: string[]) => void) {
    setValues(values.includes(value) ? values.filter((item) => item !== value) : [...values, value])
  }

  function resetComposer() {
    setComposer(null)
    setSelectedAnnotationIds([])
    setSelectedCodeIds([])
    setCodeLabel('')
    setCodeDefinition('')
    setCodeRationale('')
    setMemoTitle('')
    setMemoContent('')
    setMemoKind('analytic')
    setError(null)
  }

  async function submitCode() {
    if (!codeLabel.trim() || !codeDefinition.trim() || !codeRationale.trim() || !selectedAnnotationIds.length || pending) return
    setPending(true)
    setError(null)
    try {
      await onCreateCode({
        label: codeLabel.trim(),
        definition: codeDefinition.trim(),
        rationale: codeRationale.trim(),
        annotation_ids: selectedAnnotationIds,
      })
      resetComposer()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '编码未保存。')
    } finally {
      setPending(false)
    }
  }

  async function submitMemo() {
    if (!memoTitle.trim() || !memoContent.trim() || pending) return
    setPending(true)
    setError(null)
    try {
      await onCreateMemo({
        title: memoTitle.trim(),
        content: memoContent.trim(),
        memo_kind: memoKind,
        annotation_ids: selectedAnnotationIds,
        code_ids: selectedCodeIds,
      })
      resetComposer()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '分析备忘未保存。')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="research-analysis" role="region" aria-label="质性分析">
      <header className="research-analysis__header">
        <div>
          <strong>分析记录</strong>
          <span>{snapshot.annotations.length} 处标记 · {confirmedCodes.length} 个编码 · {confirmedMemos.length} 则备忘 · {snapshot.comparisons.filter((item) => item.status === 'confirmed').length} 组比较</span>
        </div>
        <div className="research-analysis__scope" aria-label="分析范围">
          {selectedMaterialId ? <button type="button" aria-pressed={scope === 'material'} onClick={() => setScope('material')}>当前材料</button> : null}
          <button type="button" aria-pressed={scope === 'task'} onClick={() => setScope('task')}>全部研究</button>
        </div>
      </header>

      <div className="research-analysis__annotations" aria-label="原文标记">
        {visibleAnnotations.map((annotation) => (
          <article key={annotation.annotation_id}>
            <blockquote>{annotation.quote}</blockquote>
            <p>{annotation.note}</p>
            {annotation.reflection ? <p className="is-reflection"><span>研究者反思</span>{annotation.reflection}</p> : null}
            <small>{[annotation.case_label, annotation.observed_at, formatMaterialLocator({
              page: annotation.locator.page,
              headingPath: annotation.locator.section_path,
              paragraph: annotation.locator.paragraph,
              lineStart: annotation.locator.line_start,
              lineEnd: annotation.locator.line_end,
              charStart: annotation.locator.char_start,
              charEnd: annotation.locator.char_end,
            })].filter(Boolean).join(' · ')}</small>
          </article>
        ))}
        {!visibleAnnotations.length ? <p className="research-analysis__empty">在原文中选中片段，建立第一处可追溯标记。</p> : null}
      </div>

      {candidateCodes.length || candidateMemos.length ? (
        <section className="research-analysis__candidates" aria-label="待确认的 Agent 建议">
          <h4>待你判断</h4>
          {candidateCodes.map((code) => (
            <ResearchAnalysisCandidateCard
              key={code.code_id}
              kindLabel="候选编码"
              title={code.label}
              detail={code.definition}
              rationale={code.rationale}
              version={code.version}
              onDecide={(decision, reason, version) => onDecideCode(code.code_id, decision, reason, version)}
            />
          ))}
          {candidateMemos.map((memo) => (
            <ResearchAnalysisCandidateCard
              key={memo.memo_id}
              kindLabel="备忘草稿"
              title={memo.title}
              detail={memo.content}
              version={memo.version}
              onDecide={(decision, reason, version) => onDecideMemo(memo.memo_id, decision, reason, version)}
            />
          ))}
        </section>
      ) : null}

      <section className="research-analysis__confirmed" aria-label="已确认分析">
        {confirmedCodes.map((code) => (
          <article key={code.code_id}>
            <span>研究者确认</span>
            <strong>{code.label}</strong>
            <p>{code.definition}</p>
          </article>
        ))}
        {confirmedMemos.map((memo) => (
          <article key={memo.memo_id}>
            <span>研究者确认 · {memoKindLabels[memo.memo_kind]}</span>
            <strong>{memo.title}</strong>
            <p>{memo.content}</p>
          </article>
        ))}
      </section>

      <ResearchCaseComparison
        annotations={snapshot.annotations}
        comparisons={snapshot.comparisons}
        materialNames={materialNames}
        onCreate={onCreateComparison}
        onDecide={onDecideComparison}
      />

      {snapshot.workspace
        && onConfigureCodebook
        && onTransitionCodebook
        && onCreateTheme
        && onConfirmTheme
        && onAttachMemo
        && onSaveCaseProfile
        && onSaveMatrixCell
        && onSetMethod ? (
          <QualitativeWorkspacePanel
            snapshot={snapshot}
            onConfigureCodebook={onConfigureCodebook}
            onTransitionCodebook={onTransitionCodebook}
            onCreateTheme={onCreateTheme}
            onConfirmTheme={onConfirmTheme}
            onAttachMemo={onAttachMemo}
            onSaveCaseProfile={onSaveCaseProfile}
            onSaveMatrixCell={onSaveMatrixCell}
            onSetMethod={onSetMethod}
          />
        ) : null}

      <div className="research-analysis__actions">
        <button type="button" onClick={() => { resetComposer(); setComposer('code') }}>建立编码</button>
        <button type="button" onClick={() => { resetComposer(); setComposer('memo') }}>写分析备忘</button>
      </div>

      {composer ? (
        <form className="research-analysis__composer" aria-label={composer === 'code' ? '建立编码' : '写分析备忘'} onSubmit={(event) => {
          event.preventDefault()
          if (composer === 'code') void submitCode()
          else void submitMemo()
        }}>
          <fieldset>
            <legend>关联原文标记{composer === 'code' ? '' : '（可选）'}</legend>
            {visibleAnnotations.map((annotation) => (
              <label key={annotation.annotation_id}>
                <input type="checkbox" checked={selectedAnnotationIds.includes(annotation.annotation_id)} onChange={() => toggle(selectedAnnotationIds, annotation.annotation_id, setSelectedAnnotationIds)} />
                <span>{annotation.quote}</span>
              </label>
            ))}
          </fieldset>
          {composer === 'code' ? (
            <>
              <label><span>编码名称</span><input aria-label="编码名称" value={codeLabel} onChange={(event) => setCodeLabel(event.target.value)} /></label>
              <label><span>编码定义</span><textarea aria-label="编码定义" value={codeDefinition} onChange={(event) => setCodeDefinition(event.target.value)} rows={2} /></label>
              <label><span>建立依据</span><textarea aria-label="建立依据" value={codeRationale} onChange={(event) => setCodeRationale(event.target.value)} rows={2} /></label>
            </>
          ) : (
            <>
              <label><span>备忘标题</span><input aria-label="备忘标题" value={memoTitle} onChange={(event) => setMemoTitle(event.target.value)} /></label>
              <label><span>备忘类型</span><select aria-label="备忘类型" value={memoKind} onChange={(event) => setMemoKind(event.target.value as AnalysisMemoKind)}>{Object.entries(memoKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span>备忘内容</span><textarea aria-label="备忘内容" value={memoContent} onChange={(event) => setMemoContent(event.target.value)} rows={4} /></label>
              {confirmedCodes.length ? <fieldset><legend>关联编码（可选）</legend>{confirmedCodes.map((code) => <label key={code.code_id}><input type="checkbox" checked={selectedCodeIds.includes(code.code_id)} onChange={() => toggle(selectedCodeIds, code.code_id, setSelectedCodeIds)} /><span>{code.label}</span></label>)}</fieldset> : null}
            </>
          )}
          {error ? <p role="alert">{error}</p> : null}
          <footer>
            <button type="button" onClick={resetComposer}>取消</button>
            <button type="submit" disabled={pending || (composer === 'code' ? !selectedAnnotationIds.length || !codeLabel.trim() || !codeDefinition.trim() || !codeRationale.trim() : !memoTitle.trim() || !memoContent.trim())}>{pending ? '正在保存' : composer === 'code' ? '保存编码' : '保存备忘'}</button>
          </footer>
        </form>
      ) : null}
    </section>
  )
}

export type { ResearchAnalysisWorkspaceProps }
