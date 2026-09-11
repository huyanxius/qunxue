import { useEffect, useRef, useState } from 'react'
import { DocumentSourceSegment, DocumentSourceView, DocumentWorkspace, DocumentWorkspaceToolbar, type ResearchMaterialSegment } from '../../research-materials'
import { getTeachingSource, type getTeachingActivity } from '../teachingApi'
import '../../research-materials/research-materials.css'

type Activity = Awaited<ReturnType<typeof getTeachingActivity>>
type Result = NonNullable<Activity['result']>
type Citation = NonNullable<Result['citations']>[number]
type Source = Awaited<ReturnType<typeof getTeachingSource>>
export function StudentActivityDetail({ activity, records, busy, onSave, onRun, onShare, onRevision, onOpen, onDirty }: {
  activity: Activity; records: Activity[]; busy: boolean
  onSave: (input: Activity['input'], run: boolean) => void; onRun: () => void; onShare: (value: boolean) => void
  onRevision: () => void; onOpen: (activity: Activity) => void; onDirty: (dirty: boolean) => void
}) {
  const [input, setInput] = useState(activity.input)
  const inputSignature = JSON.stringify(activity.input)
  useEffect(() => { setInput(JSON.parse(inputSignature) as Activity['input']) }, [inputSignature])
  const [source, setSource] = useState<Source | null>(null)
  const [citation, setCitation] = useState<Citation | null>(null)
  const [sourceError, setSourceError] = useState('')
  const [reading, setReading] = useState(false)
  const sourceRequest = useRef(0)
  useEffect(() => () => { sourceRequest.current++ }, [])
  const assignment = activity.kind === 'assignment_review'
  const result = assignment && activity.state !== 'published' ? null : activity.result
  const running = activity.state === 'running'
  const disabled = busy || running
  function change(patch: Partial<Activity['input']>) { setInput((value) => ({ ...value, ...patch })); onDirty(true) }
  async function readSource(value: Citation | null) {
    const request = ++sourceRequest.current
    setCitation(value); setReading(true); setSourceError(''); setSource(null)
    try {
      const loaded = await getTeachingSource(activity.id)
      if (request !== sourceRequest.current) return
      if (value && !loaded.items.some((item) => (!value.material_id || item.material_id === value.material_id) && (!value.document_id || item.document_id === value.document_id) && item.segments.some((segment) => segment.segment_id === value.segment_id))) throw new Error('当前原文中找不到这个引用位置，请刷新记录后重试。')
      setSource(loaded)
    } catch (e) { if (request === sourceRequest.current) setSourceError(e instanceof Error ? e.message : '原文读取失败。') }
    finally { if (request === sourceRequest.current) setReading(false) }
  }
  function citationButton(value: Citation, index: number) {
    return <button type="button" className="qx-button" key={`${value.segment_id}:${index}`} disabled={reading} onClick={() => void readSource(value)}>查看原文：{value.title || `依据 ${index + 1}`}</button>
  }
  const questions = result?.diagnostic_questions ?? []
  const answersComplete = questions.length > 0 && questions.every((q) => input.diagnostic_answers?.find((a) => a.question_id === q.id)?.answer.trim())
  const prior = records.find((record) => record.id === activity.source_activity_id)
  const revisions = records.filter((record) => record.source_activity_id === activity.id)
  const sourceItems = source?.items.filter((item) => !citation || ((!citation.material_id || item.material_id === citation.material_id) && (!citation.document_id || item.document_id === citation.document_id))) ?? []
  return <article className="student-learning__result">
    <h3>{activity.input.title || activity.input.objectives || '学习记录'}</h3>
    {activity.input.difficulties ? <p>开始时的困难：{activity.input.difficulties}</p> : null}
    {running ? <p role="status">正在生成，离开后可从这条记录继续。</p> : null}
    {activity.state === 'failed' ? <p role="alert" className="qx-message is-error">{activity.error_message || '生成失败，已保留输入。'}</p> : null}
    {assignment ? <>
      <p>{activity.shared_with_teacher ? '本次作业及所选材料已提交给课程教师。' : '本次作业尚未分享给课程教师。'}</p>
      {activity.input.requirements ? <><h4>作业要求</h4><p>{activity.input.requirements}</p></> : null}
      {activity.input.submission_text ? <><h4>提交内容</h4><p>{activity.input.submission_text}</p></> : null}
      {!result ? <p>等待教师复核并发布正式反馈。</p> : <><h4>正式反馈</h4><p>{result.teacher_feedback || '教师未填写文字反馈。'}</p>
        {result.teacher_scores?.length ? <table aria-label="教师确认评分"><thead><tr><th>评价维度</th><th>教师确认分</th><th>反馈依据</th></tr></thead><tbody>{result.teacher_scores.map((score) => <tr key={score.dimension_id}><td>{activity.input.rubric?.find((dimension) => dimension.id === score.dimension_id)?.title ?? score.dimension_id}</td><td>{score.score === null ? '需要教师判断' : score.score}</td><td>{score.rationale}{score.citations?.map(citationButton)}</td></tr>)}</tbody></table> : null}
        {result.citations?.map(citationButton)}<div className="courses-page__actions"><button type="button" className="qx-button" disabled={busy} onClick={onRevision}>提交修改稿</button></div>
      </>}
      {prior ? <button type="button" className="qx-button" disabled={busy} onClick={() => onOpen(prior)}>查看上一版及反馈</button> : null}
      {revisions.map((revision) => <button type="button" className="qx-button" disabled={busy} key={revision.id} onClick={() => onOpen(revision)}>查看修改稿：{revision.input.title || revision.id}</button>)}
    </> : <>
      <label className="student-materials__item"><input type="checkbox" checked={activity.shared_with_teacher} disabled={disabled} onChange={(e) => onShare(e.target.checked)} />仅分享本次学习记录及所选材料给课程教师</label>
      <p className="courses-page__hint">私人聊天和个人记忆不随本记录分享。</p>
      {!result && !running ? <form className="courses-page__form" onSubmit={(e) => { e.preventDefault(); if (input.objectives?.trim()) onSave(input, true) }}>
        <label>学习目标<textarea value={input.objectives ?? ''} required disabled={disabled} onChange={(e) => change({ objectives: e.target.value })} /></label>
        <label>当前困难<textarea value={input.difficulties ?? ''} disabled={disabled} onChange={(e) => change({ difficulties: e.target.value })} /></label>
        <div className="courses-page__actions"><button className="research-hub__new" disabled={disabled || !input.objectives?.trim()} type="submit">生成诊断题</button><button className="qx-button" disabled={disabled || !input.objectives?.trim()} type="button" onClick={() => onSave(input, false)}>保存草稿</button></div>
      </form> : null}
      {result ? <>
        {questions.length ? <section aria-label="诊断问答"><h4>诊断问答</h4>{result.stage === 'diagnostic' ? <form className="courses-page__form" onSubmit={(e) => { e.preventDefault(); if (answersComplete) onSave(input, true) }}>{questions.map((question) => <label key={question.id}>{question.prompt}<textarea disabled={disabled} required value={input.diagnostic_answers?.find((answer) => answer.question_id === question.id)?.answer ?? ''} onChange={(e) => change({ diagnostic_answers: questions.map((q) => ({ question_id: q.id, answer: q.id === question.id ? e.target.value : input.diagnostic_answers?.find((answer) => answer.question_id === q.id)?.answer ?? '' })) })} /></label>)}<div className="courses-page__actions"><button className="research-hub__new" disabled={disabled || !answersComplete} type="submit">提交回答并继续</button><button className="qx-button" disabled={disabled} type="button" onClick={() => onSave(input, false)}>保存回答</button></div></form> : questions.map((question) => <div key={question.id}><strong>{question.prompt}</strong><p>{activity.input.diagnostic_answers?.find((answer) => answer.question_id === question.id)?.answer || '尚未回答'}</p></div>)}</section> : null}
        {result.stage !== 'diagnostic' ? <>
          <h4>根据回答发现的困难</h4>{result.difficulties?.length ? result.difficulties.map((difficulty, index) => <div key={index}><p>{difficulty.description}</p><blockquote>{difficulty.evidence}</blockquote></div>) : <p>当前回答中没有足够依据判断困难。</p>}
          <h4>推荐阅读</h4>{(result.recommendations?.length ?? 0) < 3 ? <p className="courses-page__hint">本次仅找到 {result.recommendations?.length ?? 0} 项有原文依据的资料。</p> : null}
          {result.recommendations?.map((item, index) => <article key={index}><strong>{item.title}</strong><p>{item.reason}</p>{citationButton(item.source, index)}</article>)}
          {result.practice ? <section aria-label="新情境练习"><h4>新情境练习</h4><p>{result.practice.prompt}</p>{result.stage === 'practice' ? <form className="courses-page__form" onSubmit={(e) => { e.preventDefault(); if (input.practice_answer?.trim()) onSave(input, true) }}><label>练习回答<textarea rows={5} required disabled={disabled} value={input.practice_answer ?? ''} onChange={(e) => change({ practice_answer: e.target.value })} /></label><div className="courses-page__actions"><button className="research-hub__new" type="submit" disabled={disabled || !input.practice_answer?.trim()}>提交练习并查看反馈</button><button className="qx-button" type="button" disabled={disabled} onClick={() => onSave(input, false)}>保存回答</button></div></form> : <><h4>我的练习回答</h4><p>{activity.input.practice_answer || '尚未回答'}</p></>}</section> : null}
          {result.stage === 'feedback' || result.stage === 'complete' ? <section aria-label="练习反馈"><h4>反馈与待改进之处</h4><p>{result.feedback}</p><h4>下一步任务</h4><ul>{result.next_steps?.map((step, index) => <li key={index}>{step}</li>)}</ul></section> : null}
        </> : <p className="courses-page__hint">回答后才会分析困难并推荐练习。</p>}
        {result.citations?.length ? <div className="courses-page__actions">{result.citations.map(citationButton)}</div> : null}
      </> : null}
      {activity.state === 'failed' ? <button type="button" className="qx-button" disabled={disabled} onClick={onRun}>重试当前阶段</button> : null}
    </>}
    <div className="courses-page__actions"><button type="button" className="qx-button" disabled={reading} onClick={() => void readSource(null)}>阅读本次材料</button></div>
    {reading ? <p role="status">正在读取原文…</p> : null}
    {sourceError ? <p className="qx-message is-error" role="alert">{sourceError}</p> : null}
    {source ? <DocumentWorkspace workspace={false}><DocumentWorkspaceToolbar workspace={false}><strong>{citation?.title || '本次材料原文'}</strong><button type="button" className="qx-button" onClick={() => { sourceRequest.current++; setSource(null) }}>收起原文</button></DocumentWorkspaceToolbar><DocumentSourceView railLabel="" empty={!sourceItems.some((item) => item.segments.length)} onPageChange={() => undefined}>
      {sourceItems.map((item, itemIndex) => <section key={itemIndex}><h4>{item.title}</h4>{item.segments.map((segment, index) => {
        const normalized: ResearchMaterialSegment = { segmentId: segment.segment_id, materialId: item.material_id || item.document_id || '', parseId: '', ordinal: index, kind: 'paragraph', text: segment.text, locator: { page: null, headingPath: [], paragraph: null, lineStart: null, lineEnd: null, charStart: null, charEnd: null } }
        return <DocumentSourceSegment key={segment.segment_id} segment={normalized} selected={citation?.segment_id === segment.segment_id} line={String(index + 1)} register={(_id, node) => { if (node && citation?.segment_id === segment.segment_id) node.scrollIntoView?.({ block: 'nearest' }) }} onSelect={() => setCitation({ material_id: item.material_id, document_id: item.document_id, segment_id: segment.segment_id, title: item.title, quote: segment.text })}>{segment.text}</DocumentSourceSegment>
      })}</section>)}
    </DocumentSourceView></DocumentWorkspace> : null}
  </article>
}
