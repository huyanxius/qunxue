import lessonArtwork from '../../../assets/classroom/humanist-seminar.webp'
import assignmentArtwork from '../../../assets/classroom/civic-observation.webp'
import { BookOpenIcon, ClipboardTextIcon, ArrowUpRightIcon, ClockIcon, LockSimpleIcon, CheckCircleIcon, FilesIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import type { SharedCourse } from '../../shared-knowledge'
import { createTeachingActivity, getTeachingActivity, listTeachingActivities, runTeachingActivity, updateTeachingActivity } from '../teachingApi'
import { StudentMaterials } from './StudentMaterials'
import { StudentActivityDetail } from './StudentActivityDetail'
import './student-learning.css'
import '../classroom-workspace.css'

type Activity = Awaited<ReturnType<typeof getTeachingActivity>>
type Input = Activity['input']
const stateLabels: Record<Activity['state'], string> = { draft: '已保存', running: '生成中', ready: '可继续', reviewed: '已复核', published: '已发布', failed: '生成失败' }

export function StudentLearningPanel({ course, onDirtyChange }: { course: SharedCourse; onDirtyChange?: (dirty: boolean) => void }) {
  return course.access === 'reader' ? <StudentWorkspace key={course.id} course={course} onDirtyChange={onDirtyChange} /> : <p className="courses-page__hint">请在已加入且仍可访问的课程中使用学生学习功能。</p>
}

function StudentWorkspace({ course, onDirtyChange }: { course: SharedCourse; onDirtyChange?: (dirty: boolean) => void }) {
  const [records, setRecords] = useState<Activity[]>([])
  const [selected, setSelected] = useState<Activity | null>(null)
  const [kind, setKind] = useState<'learning_check' | 'assignment_review'>('learning_check')
  const [input, setInput] = useState<Input>({ objectives: '', difficulties: '', title: '', requirements: '', submission_text: '', material_ids: [], course_document_ids: [] })
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [share, setShare] = useState(false)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dirty, setDirty] = useState(false)
  useEffect(() => { onDirtyChange?.(dirty); return () => onDirtyChange?.(false) }, [dirty, onDirtyChange])
  const [reload, setReload] = useState(0)
  const lock = useRef(false)
  const mounted = useRef(true)
  const requestKeys = useRef(new Map<string, string>())
  const selectedId = useRef<string | null>(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    let active = true
    setLoading(true)
    void listTeachingActivities(course.id).then((list) => { if (active) { setRecords(list.filter((a) => a.kind !== 'lesson_plan')); setError('') } })
      .catch((e: Error) => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [course.id, reload])
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  function accept(record: Activity) {
    if (!mounted.current) return
    selectedId.current = record.id; setSelected(record)
    setRecords((current) => [record, ...current.filter((a) => a.id !== record.id)])
  }
  // A failed response keeps the same key for the same payload, including creates.
  async function write<T>(operation: string, body: unknown, work: (key: string) => Promise<T>) {
    const signature = JSON.stringify([operation, body])
    const key = requestKeys.current.get(signature) ?? crypto.randomUUID()
    requestKeys.current.set(signature, key)
    const result = await work(key)
    requestKeys.current.delete(signature)
    return result
  }
  async function action(work: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await work() } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : '操作失败，请重试。') }
    finally { lock.current = false; if (mounted.current) setBusy(false) }
  }
  useEffect(() => {
    const pending = records.filter((record) => record.state === 'running' || (record.kind === 'assignment_review' && record.state !== 'published'))
    if (!pending.length || busy) return
    let active = true
    const timer = window.setTimeout(() => {
      void Promise.all(pending.map((record) => getTeachingActivity(record.id))).then((updated) => {
        if (!active) return
        setRecords((current) => current.map((record) => updated.find((a) => a.id === record.id) ?? record))
        const current = updated.find((a) => a.id === selectedId.current)
        if (current) setSelected(current)
      }).catch((e: Error) => { if (active) setError(e.message) })
    }, 2500)
    return () => { active = false; window.clearTimeout(timer) }
  }, [records, busy])
  function leave() { return !dirty || window.confirm('还有未保存的输入，离开会丢失。继续吗？') }
  function fresh(nextKind: typeof kind, source: Activity | null = null) {
    if (!leave()) return
    setKind(nextKind); setSelected(null); selectedId.current = null; setSourceId(source?.id ?? null); setShare(false); setError(''); setDirty(false)
    setInput({ objectives: '', difficulties: '', title: source?.input.title ?? '', requirements: source?.input.requirements ?? '', submission_text: '', material_ids: [], course_document_ids: [] })
  }
  function change(patch: Partial<Input>) { setInput((current) => ({ ...current, ...patch })); setDirty(true) }
  async function start(run: boolean) {
    const body = { kind, input, shared_with_teacher: kind === 'assignment_review' && share, source_activity_id: sourceId }
    const record = await write(`create:${course.id}`, body, (key) => createTeachingActivity(course.id, body, key))
    accept(record); setDirty(false)
    if (run) accept(await write(`run:${record.id}`, { version: record.version }, (key) => runTeachingActivity(record.id, { version: record.version }, key)))
  }
  async function saveInput(record: Activity, next: Input, run: boolean) {
    const body = { version: record.version, input: next }
    const saved = await write(`update:${record.id}`, body, (key) => updateTeachingActivity(record.id, body, key))
    accept(saved); setDirty(false)
    if (run) accept(await write(`run:${saved.id}`, { version: saved.version }, (key) => runTeachingActivity(saved.id, { version: saved.version }, key)))
  }
  const valid = kind === 'learning_check' ? Boolean(input.objectives?.trim()) : Boolean(input.title?.trim() && input.requirements?.trim() && (input.submission_text?.trim() || input.material_ids?.length) && share)
  return <section className="student-learning" aria-label="学生学习与作业">
    <header className="classroom-heading"><div><span className="classroom-eyebrow">我的学习工作区</span><h3>学习任务与作业反馈</h3><p>从一次诊断开始，回到课程原文，在新的情境中练习。</p></div><span className="classroom-privacy"><LockSimpleIcon size={16} />学习记录默认私有</span></header>
    <div className="classroom-overview" aria-label="学习概览">
      <div><BookOpenIcon size={20} /><span>学习记录<strong>{records.filter((r) => r.kind === 'learning_check').length}<small>次</small></strong></span></div>
      <div><ClipboardTextIcon size={20} /><span>已提交作业<strong>{records.filter((r) => r.kind === 'assignment_review' && r.shared_with_teacher).length}<small>份</small></strong></span></div>
      <div><CheckCircleIcon size={20} /><span>正式反馈<strong>{records.filter((r) => r.kind === 'assignment_review' && r.state === 'published').length}<small>份</small></strong></span></div>
      <div><FilesIcon size={20} /><span>可用课程资料<strong>{course.documents.filter((d) => d.status === 'ready').length}<small>份</small></strong></span></div>
    </div>
    <div className="classroom-launchers">
      <button type="button" aria-label="学习助手" disabled={busy || uploading} onClick={() => fresh('learning_check')}><img className="classroom-launcher-art" src={lessonArtwork} alt="" /><span className="classroom-launcher-icon"><BookOpenIcon size={24} /></span><span><strong>学习助手</strong><small>诊断问题 · 推荐阅读 · 情境练习</small></span><ArrowUpRightIcon size={20} /></button>
      <button type="button" aria-label="提交作业" disabled={busy || uploading} onClick={() => fresh('assignment_review')}><img className="classroom-launcher-art" src={assignmentArtwork} alt="" /><span className="classroom-launcher-icon"><ClipboardTextIcon size={24} /></span><span><strong>提交作业</strong><small>保留原稿 · 教师反馈 · 修改记录</small></span><ArrowUpRightIcon size={20} /></button>
    </div>
    <div className="classroom-layout"><div className="classroom-main">
    {(selected?.kind ?? kind) === 'learning_check' && <ol className="classroom-learning-stages" aria-label="学习阶段">{['明确目标', '诊断问答', '情境练习', '反馈与改进'].map((label, index) => { const stage = selected?.result?.stage; const current = stage === 'feedback' || stage === 'complete' ? 3 : stage === 'practice' ? 2 : stage === 'diagnostic' ? 1 : 0; return <li key={label} aria-current={index === current ? 'step' : undefined} data-complete={index < current}><span>{index < current ? <CheckCircleIcon size={17} /> : index + 1}</span>{label}</li> })}</ol>}
    {error ? <p role="alert" className="qx-message is-error">{error} <button type="button" className="qx-button" disabled={busy} onClick={() => void action(async () => { if (selected) accept(await getTeachingActivity(selected.id)); setReload((n) => n + 1) })}>刷新记录</button></p> : null}
    {loading ? <p role="status">正在读取学习记录…</p> : null}
    {selected ? <StudentActivityDetail key={selected.id} activity={selected} records={records} busy={busy} onDirty={setDirty}
      onSave={(next, run) => void action(() => saveInput(selected, next, run))}
      onRun={() => void action(async () => accept(await write(`run:${selected.id}`, { version: selected.version }, (key) => runTeachingActivity(selected.id, { version: selected.version }, key))))}
      onShare={(value) => void action(async () => { const body = { version: selected.version, shared_with_teacher: value }; accept(await write(`update:${selected.id}`, body, (key) => updateTeachingActivity(selected.id, body, key))) })}
      onRevision={() => fresh('assignment_review', selected)} onOpen={(record) => { if (leave()) void action(async () => { accept(await getTeachingActivity(record.id)); setDirty(false) }) }} /> :
      <form className="courses-page__form" onSubmit={(event) => { event.preventDefault(); if (valid && !uploading) void action(() => start(kind === 'learning_check')) }}>
        <h3>{kind === 'learning_check' ? '开始一次学习' : sourceId ? '提交修改稿' : '提交自己的作业'}</h3>
        {sourceId ? <p className="courses-page__hint">修改稿会保留与上一版的关联，原稿和正式反馈仍可查看。</p> : null}
        {kind === 'learning_check' ? <><label>学习目标<textarea maxLength={10000} required value={input.objectives ?? ''} onChange={(e) => change({ objectives: e.target.value })} disabled={busy} /></label><label>当前困难<textarea maxLength={10000} value={input.difficulties ?? ''} onChange={(e) => change({ difficulties: e.target.value })} disabled={busy} /></label></> : <><label>作业标题<input required maxLength={200} value={input.title ?? ''} onChange={(e) => change({ title: e.target.value })} disabled={busy} /></label><label>作业要求<textarea required maxLength={20000} value={input.requirements ?? ''} onChange={(e) => change({ requirements: e.target.value })} disabled={busy} /></label><label>作业内容<textarea rows={6} maxLength={50000} value={input.submission_text ?? ''} onChange={(e) => change({ submission_text: e.target.value })} disabled={busy} /></label></>}
        <StudentMaterials selectedIds={input.material_ids ?? []} onChange={(ids) => change({ material_ids: ids })} disabled={busy} onBusyChange={setUploading} />
        {kind === 'learning_check' && course.documents.length ? <fieldset disabled={busy}><legend>本次参考的课程资料</legend>{course.documents.map((doc) => <label className="student-materials__item" key={doc.id}><input type="checkbox" disabled={doc.status !== 'ready'} checked={input.course_document_ids?.includes(doc.id) ?? false} onChange={(e) => change({ course_document_ids: e.target.checked ? [...(input.course_document_ids ?? []), doc.id] : input.course_document_ids?.filter((id) => id !== doc.id) })} />{doc.filename}{doc.status !== 'ready' ? '（暂不可用）' : ''}</label>)}</fieldset> : null}
        {kind === 'assignment_review' ? <label className="student-materials__item"><input type="checkbox" checked={share} disabled={busy} onChange={(e) => setShare(e.target.checked)} />同意将本次作业及选中的材料提交给课程教师</label> : <p className="courses-page__hint">学习记录默认仅自己可见，完成后可单独分享给课程教师。</p>}
        <div className="courses-page__actions"><button className="research-hub__new" type="submit" disabled={busy || uploading || !valid}>{busy ? '正在保存…' : kind === 'learning_check' ? '生成诊断题' : '提交给课程教师'}</button>{kind === 'learning_check' ? <button type="button" className="qx-button" disabled={busy || uploading || !valid} onClick={() => void action(() => start(false))}>保存草稿</button> : null}</div>
      </form>}
    </div><aside className="classroom-rail"><section className="classroom-history" aria-label="我的记录"><div className="classroom-section-title"><span><ClockIcon size={18} />我的记录</span><small>{records.length} 条</small></div>{!loading && !records.length ? <p className="courses-page__hint">还没有学习或作业记录。</p> : null}<ul className="student-learning__records">{records.map((record) => <li key={record.id}><button type="button" className="courses-page__text-button" disabled={busy || uploading} aria-current={selected?.id === record.id ? 'true' : undefined} onClick={() => { if (leave()) void action(async () => { accept(await getTeachingActivity(record.id)); setDirty(false) }) }}><span className="classroom-record-title">{record.kind === 'assignment_review' ? <ClipboardTextIcon size={17} /> : <BookOpenIcon size={17} />}<strong>{record.input.title || record.input.objectives || '学习记录'}</strong></span><span className="classroom-record-meta"><span>{record.kind === 'assignment_review' ? '作业' : '学习'}</span><span className="classroom-state" data-state={record.state}>{stateLabels[record.state]}</span></span></button></li>)}</ul></section><section className="classroom-insights"><div className="classroom-section-title"><span><LockSimpleIcon size={18} />你的学习档案</span></div><h3>探索的过程，由你掌握</h3><p>学习记录仅自己可见。你可以选择某一次记录分享给教师，让反馈更有针对性。</p><div className="classroom-brief-footer"><span>作业原稿与修改稿分别保留</span></div></section></aside></div>
  </section>
}
