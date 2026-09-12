import lessonArtwork from '../../../assets/research-tools/qualitative-coding.webp'
import assignmentArtwork from '../../../assets/research-tools/interview-notes.webp'
import { ArrowUpRightIcon, BookOpenIcon, FilesIcon, SlidersHorizontalIcon, ClipboardTextIcon, ChartBarIcon, ClockIcon, CheckCircleIcon } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { SharedCourse } from '../../shared-knowledge'
import { addResearchLibraryMaterial, getAgentAttachmentMaterial, listAgentMaterials, prepareAgentMaterialContext, RESEARCH_MATERIAL_ACCEPT, type ResearchMaterial } from '../../research-materials'
import { stopAgentRun } from '../../research-agent'
import { createTeachingActivity, getLearningSummary, getTeachingActivity, getTeachingSettings, getTeachingSource,
  listTeachingActivities, publishTeachingActivity, runTeachingActivity, updateTeachingActivity, updateTeachingSettings,
  type TeachingActivity, type TeachingInput, type TeachingSettings, type TeachingSource, type TeachingScore, type LearningSummary, type RubricDimension } from '../teachingApi'
import { LessonEditor } from './LessonEditor'
import { downloadTeachingDocument } from './teachingExport'
import { TeacherSources } from './TeacherSources'
import './teacher-teaching.css'
import '../classroom-workspace.css'

const defaultRubric: RubricDimension[] = [
  { id: 'argument', title: '论点与概念', max_score: 30 },
  { id: 'evidence', title: '材料与论证', max_score: 40 },
  { id: 'structure', title: '结构与表达', max_score: 30 },
]
const stateNames = { draft: '草稿', running: '执行中', ready: '待复核', reviewed: '已复核', published: '已发布', failed: '执行失败' }
const message = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试。'

export function TeacherTeachingPanel({ course, onDirtyChange }: { course: SharedCourse; onDirtyChange?: (dirty: boolean) => void }) {
  const [settings, setSettings] = useState<TeachingSettings | null>(null)
  const [items, setItems] = useState<TeachingActivity[]>([])
  const [summary, setSummary] = useState<LearningSummary | null>(null)
  const [active, setActive] = useState<TeachingActivity | null>(null)
  const [kind, setKind] = useState<'lesson_plan' | 'assignment_review'>('lesson_plan')
  const [form, setForm] = useState(false)
  const [input, setInput] = useState<TeachingInput>({})
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [materials, setMaterials] = useState<ResearchMaterial[]>([])
  const [source, setSource] = useState<TeachingSource | null>(null)
  const [selectedSource, setSelectedSource] = useState<string | null>(null)
  const [scores, setScores] = useState<TeachingScore[]>([])
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [tab, setTab] = useState<'source' | 'feedback'>('feedback')
  const [dirty, setDirty] = useState(false)
  useEffect(() => { onDirtyChange?.(dirty); return () => onDirtyChange?.(false) }, [dirty, onDirtyChange])
  const [showSettings, setShowSettings] = useState(false)
  const [workspaceView, setWorkspaceView] = useState<'overview' | 'lessons' | 'assignments' | 'shared'>('overview')
  const [recordQuery, setRecordQuery] = useState('')
  const requestKey = useRef(crypto.randomUUID())
  const generation = useRef(0)
  const canManage = course.access === 'owner'
  const reload = useCallback(async () => {
    const [nextItems, nextSummary] = await Promise.all([listTeachingActivities(course.id), getLearningSummary(course.id)])
    setItems(nextItems); setSummary(nextSummary)
  }, [course.id])
  useEffect(() => {
    if (!canManage) return
    const current = ++generation.current
    setActive(null); setForm(false); setDirty(false)
    Promise.all([getTeachingSettings(course.id), listTeachingActivities(course.id), getLearningSummary(course.id), listAgentMaterials()])
      .then(([nextSettings, nextItems, nextSummary, nextMaterials]) => {
        if (generation.current !== current) return
        setSettings(nextSettings); setItems(nextItems); setSummary(nextSummary); setMaterials(nextMaterials)
      }).catch((reason) => { if (generation.current === current) setError(message(reason)) })
    return () => { generation.current = current + 1 }
  }, [course.id, canManage])
  useEffect(() => {
    const prevent = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', prevent)
    return () => window.removeEventListener('beforeunload', prevent)
  }, [dirty])
  const activeId = active?.id
  const activeState = active?.state
  const activeResult = active?.result
  useEffect(() => {
    if (!activeId || activeState !== 'running') return
    let stopped = false
    const timer = setInterval(() => {
      getTeachingActivity(activeId).then((next) => {
        if (stopped) return
        setActive(next)
        if (next.state !== 'running') void reload().catch((reason) => setError(message(reason)))
      }).catch((reason) => { if (!stopped) setError(message(reason)) })
    }, 2000)
    return () => { stopped = true; clearInterval(timer) }
  }, [activeId, activeState, reload])
  useEffect(() => {
    const result = activeResult
    setScores(result?.teacher_scores?.length ? result.teacher_scores : (result?.suggested_scores ?? []).map((s) => ({ ...s })))
    setFeedback(result?.teacher_feedback || result?.feedback || result?.markdown || '')
  }, [activeId, activeResult])
  if (!canManage) return null
  function leave() { return !dirty || window.confirm('当前修改尚未保存，确定离开？') }
  function newForm(nextKind: 'lesson_plan' | 'assignment_review', activity?: TeachingActivity, improvement = '', improvementIds: string[] = []) {
    if (!leave()) return
    setWorkspaceView(nextKind === 'lesson_plan' ? 'lessons' : 'assignments'); setShowSettings(false);
    setKind(nextKind); setForm(true); setActive(null); setDirty(false); setSource(null); setError(''); setNotice('')
    setSourceId(activity?.id ?? null)
    requestKey.current = crypto.randomUUID()
    setInput(activity ? { ...activity.input } : { title: '', objectives: settings?.objectives ?? '', duration_minutes: 45,
      student_background: '', requirements: '', material_ids: [], course_document_ids: [], rubric: settings?.rubric.length ? settings.rubric : defaultRubric,
      improvement_context: improvement, source_activity_ids: improvementIds })
  }
  function change<K extends keyof TeachingInput>(name: K, value: TeachingInput[K]) {
    setInput((old) => ({ ...old, [name]: value })); setDirty(true)
  }
  async function action(operation: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await operation() } catch (reason) { setError(message(reason)) } finally { setBusy(false) }
  }
  async function open(activity: TeachingActivity) {
    if (!leave()) return
    await action(async () => {
      const next = await getTeachingActivity(activity.id)
      setShowSettings(false); setActive(next); setForm(false); setDirty(false); setInput(next.input)
      setSource(await getTeachingSource(activity.id)); setSelectedSource(null)
    })
  }
  async function saveDraft(run: boolean) {
    await action(async () => {
      const next = await createTeachingActivity(course.id, { kind, input, source_activity_id: sourceId, shared_with_teacher: false }, requestKey.current)
      setActive(next); setForm(false); setDirty(false); setNotice('草稿已保存')
      if (run) setActive(await runTeachingActivity(next.id, { version: next.version }))
      await reload()
    })
  }
  async function runActive() {
    if (!active) return
    await action(async () => { setActive(await runTeachingActivity(active.id, { version: active.version })); await reload() })
  }
  async function saveReview(reviewed: boolean) {
    if (!active) return
    await action(async () => {
      setActive(await updateTeachingActivity(active.id, { version: active.version, teacher_scores: scores, teacher_feedback: feedback, reviewed }))
      setDirty(false); setNotice(reviewed ? '复核已完成，可发布给学生。' : '教师反馈已保存。'); await reload()
    })
  }
  async function upload(file: File) {
    setUploading(true); setError('')
    const current = generation.current
    try {
      const context = await prepareAgentMaterialContext(null, crypto.randomUUID())
      let material = await addResearchLibraryMaterial(context.task_id, file)
      for (let attempt = 0; material.status !== 'ready' && material.status !== 'failed' && attempt < 90; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
        if (current !== generation.current) return
        material = await getAgentAttachmentMaterial(material.taskId, material.materialId)
      }
      if (current !== generation.current) return
      if (material.status !== 'ready') throw new Error(material.status === 'failed' ? '资料解析失败，请到个人资料重试。' : '资料仍在解析，稍后从个人材料选择。')
      setMaterials((old) => [material, ...old.filter((m) => m.materialId !== material.materialId)])
      setInput((old) => ({ ...old, material_ids: [...(old.material_ids ?? []), material.materialId] })); setDirty(true)
    } catch (reason) { setError(message(reason)) } finally { setUploading(false) }
  }
  const review = active?.kind === 'assignment_review'
  const rubric = input.rubric ?? defaultRubric
  const libraryItems = items.filter((item) => (workspaceView === 'lessons' ? item.kind === 'lesson_plan' : workspaceView === 'assignments' ? item.kind === 'assignment_review' : item.kind === 'learning_check') && (!recordQuery || (item.input.title || item.input.objectives || '').includes(recordQuery)))
  return <section className="teacher-teaching" aria-label="教师教学工作区">
    <header className="classroom-heading"><div><span className="classroom-eyebrow">教学工作区</span><h3>备课、批改与教学反馈</h3><p>从课程资料出发，把备课、作业反馈与下一次教学连在一起。</p></div><button type="button" className="qx-button" onClick={() => { if (leave()) { setShowSettings(!showSettings); setActive(null); setForm(false); setDirty(false) } }}><SlidersHorizontalIcon size={17} />课程教学要求</button></header>
    <div className="classroom-overview" aria-label="教学概览">
      <div><BookOpenIcon size={20} /><span>备课文稿<strong>{items.filter((item) => item.kind === 'lesson_plan').length}<small>份</small></strong></span></div>
      <div><ClipboardTextIcon size={20} /><span>待处理作业<strong>{items.filter((item) => item.kind === 'assignment_review' && item.state !== 'published').length}<small>份</small></strong></span></div>
      <div><CheckCircleIcon size={20} /><span>已发布反馈<strong>{items.filter((item) => item.kind === 'assignment_review' && item.state === 'published').length}<small>份</small></strong></span></div>
      <div><FilesIcon size={20} /><span>可用课程资料<strong>{course.documents.filter((doc) => doc.status === 'ready').length}<small>份</small></strong></span></div>
    </div>
    <div className="classroom-launchers">
      <button type="button" aria-label="新建备课" onClick={() => newForm('lesson_plan')}><img className="classroom-launcher-art" src={lessonArtwork} alt="" /><span className="classroom-launcher-icon"><BookOpenIcon size={24} /></span><span><strong>设计下一次课堂</strong><small>教学目标 · 课程讲义 · 可编辑教案</small></span><ArrowUpRightIcon size={20} /></button>
      <button type="button" aria-label="批改作业" onClick={() => newForm('assignment_review')}><img className="classroom-launcher-art" src={assignmentArtwork} alt="" /><span className="classroom-launcher-icon"><ClipboardTextIcon size={24} /></span><span><strong>开始一份作业批改</strong><small>原文依据 · 分项评价 · 教师复核</small></span><ArrowUpRightIcon size={20} /></button>
    </div>
    <nav className="classroom-workspace-tabs" aria-label="教师工作区导航">{([['overview', '教学总览'], ['lessons', '教案文稿'], ['assignments', '作业管理'], ['shared', '学生分享']] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={workspaceView === value} onClick={() => { if (leave()) { setWorkspaceView(value); setActive(null); setForm(false); setShowSettings(false); setDirty(false); setRecordQuery('') } }}>{label}</button>)}</nav>
    <div className="classroom-layout"><div className="classroom-main">
    {workspaceView !== 'overview' && !form && !active && !showSettings && <section className="classroom-library"><header><div><span className="classroom-eyebrow">{workspaceView === 'lessons' ? '课程教案库' : workspaceView === 'assignments' ? '作业处理队列' : '学生主动分享'}</span><h3>{workspaceView === 'lessons' ? '教案文稿' : workspaceView === 'assignments' ? '作业管理' : '学习记录'}</h3></div><label>搜索教学记录<input type="search" value={recordQuery} onChange={(event) => setRecordQuery(event.target.value)} placeholder="搜索主题或学习目标" /></label></header><div className="classroom-table-scroll"><table aria-label="教学记录列表"><thead><tr><th>名称</th><th>状态</th><th>更新日期</th><th>操作</th></tr></thead><tbody>{libraryItems.map((item) => <tr key={item.id}><td><strong>{item.input.title || item.input.objectives || '未命名记录'}</strong><small>{item.kind === 'lesson_plan' ? `${item.input.duration_minutes ?? '—'} 分钟 · 文稿版本 ${item.version}` : item.kind === 'assignment_review' ? item.shared_with_teacher ? '学生提交' : '教师上传' : '学生授权查看'}</small></td><td><span className="classroom-state" data-state={item.state}>{stateNames[item.state]}</span></td><td><time>{new Date(item.updated_at).toLocaleDateString()}</time></td><td><button className="courses-page__text-button" onClick={() => void open(item)}>{item.kind === 'lesson_plan' ? '打开文稿' : item.kind === 'assignment_review' ? '查看作业' : '查看记录'}<ArrowUpRightIcon size={14} /></button></td></tr>)}</tbody></table></div>{!libraryItems.length && <p className="classroom-library-empty">{recordQuery ? '没有找到匹配记录。' : workspaceView === 'lessons' ? '还没有教案。选择上方“设计下一次课堂”，开始准备课程内容。' : workspaceView === 'assignments' ? '还没有作业。可上传一份作业，或等待学生在课程中提交。' : '学生主动分享学习记录后，会出现在这里。'}</p>}</section>}

    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {showSettings && settings && <form className="courses-page__form" onSubmit={(e) => { e.preventDefault(); void action(async () => {
      setSettings(await updateTeachingSettings(course.id, { version: settings.version, objectives: settings.objectives, rubric: settings.rubric.length ? settings.rubric : defaultRubric })); setDirty(false); setNotice('课程要求已保存。')
    }) }}>
      <h3>课程教学要求</h3>
      <label>默认教学目标<textarea value={settings.objectives} onChange={(e) => { setSettings({ ...settings, objectives: e.target.value }); setDirty(true) }} /></label>
      <RubricFields rubric={settings.rubric.length ? settings.rubric : defaultRubric} onChange={(next) => { setSettings({ ...settings, rubric: next }); setDirty(true) }} />
      <button className="qx-button" disabled={busy}>保存课程要求</button>
    </form>}
    {workspaceView === 'overview' && !form && !active && !showSettings && <section className="classroom-brief"><div className="classroom-section-title"><span><BookOpenIcon size={18} />课堂准备</span><small>从目标到课堂成果</small></div><h4>{settings?.objectives ? '本课程的教学目标' : '为下一次教学做好准备'}</h4><p>{settings?.objectives || '确定教学目标，选择本次讲义，生成可继续编辑和导出的课堂教案。'}</p><ol className="classroom-process"><li><span>1</span><div><strong>明确目标</strong><small>设定课时与学生基础</small></div></li><li><span>2</span><div><strong>结合资料</strong><small>选择讲义与课堂案例</small></div></li><li><span>3</span><div><strong>形成教案</strong><small>编辑、修订与 Word 导出</small></div></li></ol><div className="classroom-brief-footer"><span><FilesIcon size={16} />{course.documents.length} 份课程资料</span><span>教学要求 · 版本 {settings?.version ?? 0}</span></div></section>}
    {form && <form className="courses-page__form" onSubmit={(e) => { e.preventDefault(); void saveDraft(true) }}>
      <h3>{sourceId ? '创建修订' : kind === 'lesson_plan' ? '备课' : '作业批改'}</h3>
      <label>主题<input value={input.title ?? ''} onChange={(e) => change('title', e.target.value)} /></label>
      {kind === 'lesson_plan' ? <>
        <label>教学目标<textarea required value={input.objectives ?? ''} onChange={(e) => change('objectives', e.target.value)} /></label>
        <label>课时（分钟）<input type="number" min={1} max={600} value={input.duration_minutes ?? 45} onChange={(e) => change('duration_minutes', Number(e.target.value))} /></label>
        <label>学生基础<textarea value={input.student_background ?? ''} onChange={(e) => change('student_background', e.target.value)} /></label>
        {input.improvement_context && <label>本次改进依据<textarea value={input.improvement_context} onChange={(e) => change('improvement_context', e.target.value)} /></label>}
      </> : <>
        <label>作业要求<textarea required value={input.requirements ?? ''} onChange={(e) => change('requirements', e.target.value)} /></label>
        <label>作业正文（也可上传文件）<textarea value={input.submission_text ?? ''} onChange={(e) => change('submission_text', e.target.value)} /></label>
        <RubricFields rubric={rubric} onChange={(next) => change('rubric', next)} />
        <p className="courses-page__hint">教师上传的作业仅自己可见，可导出反馈交付；学生提交按其账号关联。</p>
      </>}
      <fieldset><legend>本次课程资料</legend>
        {course.documents.length ? course.documents.map((doc) => <label key={doc.id} className="teaching-check"><input type="checkbox" disabled={doc.status !== 'ready'} checked={input.course_document_ids?.includes(doc.id) ?? false} onChange={(e) => change('course_document_ids', e.target.checked ? [...(input.course_document_ids ?? []), doc.id] : input.course_document_ids?.filter((id) => id !== doc.id))} />{doc.filename}{doc.status !== 'ready' && '（未解析完成）'}</label>) : <p>未结合课程资料，将生成通用内容。</p>}
      </fieldset>
      <fieldset><legend>本次个人材料</legend>
        <label>上传讲义或作业<input type="file" accept={RESEARCH_MATERIAL_ACCEPT} disabled={uploading} onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = '' }} /></label>
        {uploading && <p role="status">正在上传和解析资料…</p>}
        {materials.map((material) => <label key={material.materialId} className="teaching-check"><input type="checkbox" disabled={material.status !== 'ready'} checked={input.material_ids?.includes(material.materialId) ?? false} onChange={(e) => change('material_ids', e.target.checked ? [...(input.material_ids ?? []), material.materialId] : input.material_ids?.filter((id) => id !== material.materialId))} />{material.filename}{material.status !== 'ready' && '（尚不可用）'}</label>)}
      </fieldset>
      <div className="courses-page__actions"><button type="button" className="qx-button" disabled={busy || uploading} onClick={() => void saveDraft(false)}>保存草稿</button><button className="research-hub__new" disabled={busy || uploading}>保存并生成</button></div>
    </form>}
    {active && <section className="classroom-activity" aria-label="当前教学活动">
      <h3>{active.input.title || (review ? '作业批改' : active.kind === 'learning_check' ? '学生分享的学习记录' : '课堂教案')} · {stateNames[active.state]}</h3>
      {active.source_activity_id && <p>修订自记录 <button className="courses-page__text-button" onClick={() => void action(async () => { const old = await getTeachingActivity(active.source_activity_id!); setActive(old); setSource(await getTeachingSource(old.id)) })}>查看上一版</button></p>}
      {active.state === 'running' && <p role="status">助手正在执行，刷新后可继续查看。{active.agent_run_id && <button type="button" className="courses-page__text-button" onClick={() => void action(async () => { await stopAgentRun(active.agent_run_id!); setNotice('已请求停止，等待执行器保存终态。') })}>停止生成</button>}</p>}
      {active.state === 'failed' && <p role="alert">{active.error_message}</p>}
      {review && ['draft', 'failed'].includes(active.state) && <form className="courses-page__form" onSubmit={(e) => { e.preventDefault(); void action(async () => {
        const next = await updateTeachingActivity(active.id, { version: active.version, input: { ...active.input, requirements: input.requirements ?? active.input.requirements, rubric: input.rubric ?? active.input.rubric } })
        setActive(next); setInput(next.input); setDirty(false); setNotice('本次评价标准已保存。'); await reload()
      }) }}>
        <label>本次作业要求<textarea value={input.requirements ?? active.input.requirements ?? ''} onChange={(e) => change('requirements', e.target.value)} /></label>
        <RubricFields rubric={input.rubric ?? active.input.rubric ?? defaultRubric} onChange={(next) => change('rubric', next)} />
        <button className="qx-button" disabled={busy || !dirty}>保存本次评价标准</button>
      </form>}
      {['draft', 'failed'].includes(active.state) && active.kind !== 'learning_check' && <div className="courses-page__actions"><button className="research-hub__new" disabled={busy || dirty} onClick={() => void runActive()}>{active.state === 'failed' ? '重试生成' : '开始生成'}</button>{!review && <button className="qx-button" onClick={() => newForm(active.kind as 'lesson_plan' | 'assignment_review', active)}>修改输入并创建修订</button>}</div>}
      {active.kind === 'lesson_plan' && active.result?.markdown && active.state !== 'running' && <LessonEditor activity={active} busy={busy} onDirty={setDirty}
        onSave={async (markdown) => { const next = await updateTeachingActivity(active.id, { version: active.version, document_markdown: markdown }); setActive(next); setDirty(false); await reload() }}
        onRevise={async (markdown, instruction, selected) => { const next = await updateTeachingActivity(active.id, { version: active.version, document_markdown: markdown, revision_instruction: instruction, selected_text: selected }); setActive(await runTeachingActivity(next.id, { version: next.version })); setDirty(false) }} />}
      {active.kind === 'lesson_plan' && !!active.result?.citations?.length && <section aria-label="教案资料依据">
        <h4>资料依据</h4>{active.result.citations.map((cite, i) => <button key={i} className="courses-page__text-button" onClick={() => void action(async () => { setSource(await getTeachingSource(active.id)); setSelectedSource(cite.segment_id) })}>{cite.title} · {cite.quote}</button>)}
        {selectedSource && <TeacherSources source={source} selected={selectedSource} />}
      </section>}
      {review && active.result && <>
        <div className="teaching-mobile-tabs" role="tablist" aria-label="作业阅读切换"><button role="tab" aria-selected={tab === 'source'} onClick={() => setTab('source')}>作业原文</button><button role="tab" aria-selected={tab === 'feedback'} onClick={() => setTab('feedback')}>反馈复核</button></div>
        <div className="teaching-review" data-tab={tab}>
          <div className="teaching-review__source"><TeacherSources source={source} selected={selectedSource} /></div>
          <div className="teaching-review__feedback">
            {(active.result.suggested_scores ?? []).map((suggestion, index) => {
              const dimension = active.input.rubric?.find((d) => d.id === suggestion.dimension_id)
              return <article key={suggestion.dimension_id}>
                <h4>{dimension?.title} · 建议分 {suggestion.score ?? '需要教师判断'} / {dimension?.max_score}</h4>
                <p>{suggestion.rationale}</p>
                {suggestion.citations?.map((cite, i) => <button key={i} type="button" className="courses-page__text-button" onClick={() => void action(async () => { setSource(await getTeachingSource(active.id)); setSelectedSource(cite.segment_id); setTab('source') })}>“{cite.quote}” · 查看原文</button>)}
                <label>教师确认分<input aria-label={`${dimension?.title}教师确认分`} type="number" min={0} max={dimension?.max_score} disabled={active.state === 'published'} value={scores[index]?.score ?? ''} onChange={(e) => { setScores((old) => old.map((s, j) => j === index ? { ...s, score: e.target.value === '' ? null : Number(e.target.value) } : s)); setDirty(true) }} /></label>
                <label>教师评价<textarea disabled={active.state === 'published'} value={scores[index]?.rationale ?? ''} onChange={(e) => { setScores((old) => old.map((s, j) => j === index ? { ...s, rationale: e.target.value } : s)); setDirty(true) }} /></label>
              </article>
            })}
            <label>给学生的正式反馈<textarea disabled={active.state === 'published'} value={feedback} onChange={(e) => { setFeedback(e.target.value); setDirty(true) }} /></label>
            {active.state !== 'published' && <div className="courses-page__actions"><button className="qx-button" disabled={busy} onClick={() => void saveReview(false)}>保存反馈</button><button className="qx-button" disabled={busy} onClick={() => void saveReview(true)}>标记复核完成</button><button className="research-hub__new" disabled={busy || dirty || active.state !== 'reviewed'} onClick={() => void action(async () => { setActive(await publishTeachingActivity(active.id, { version: active.version })); await reload() })}>发布反馈</button></div>}
            <button className="qx-button" disabled={busy || dirty} onClick={() => void action(() => downloadTeachingDocument(active.input.title || '作业反馈', `${active.result?.teacher_feedback ?? ''}\n\n${(active.result?.teacher_scores ?? []).map((s) => `${active.input.rubric?.find((d) => d.id === s.dimension_id)?.title}：${s.score ?? '待判断'}\n${s.rationale}`).join('\n\n')}`))}>下载反馈 Word</button>
          </div>
        </div>
      </>}
      {active.kind === 'learning_check' && active.result && <article><p>学生仅分享本次学习记录。</p><p>目标：{active.input.objectives}</p>{active.input.diagnostic_answers?.map((answer) => <p key={answer.question_id}>{answer.answer}</p>)}<ReactMarkdown remarkPlugins={[remarkGfm]}>{active.result.feedback || active.result.markdown}</ReactMarkdown>{active.result.difficulties?.map((d, i) => <p key={i}>{d.description} · 依据：{d.evidence}</p>)}</article>}
    </section>}
    </div><aside className="classroom-rail"><section className="classroom-insights" aria-label="共性困难"><div className="classroom-section-title"><span><ChartBarIcon size={18} />教学观察</span><small>来自正式反馈</small></div><h3>已提交作业中的问题</h3><p>当前样本 {summary?.sample_count ?? 0} 份，仅代表已授权提交的作业，问题依据来自已发布反馈。</p>
      {!summary?.issues.length && <p className="courses-page__hint">暂时没有可汇总的原文依据。</p>}
      {summary?.issues.map((issue, i) => <article key={i}><p>{issue.description}</p><p>{issue.evidence.join('；')}</p>
        {issue.activity_ids.map((id) => <button key={id} className="courses-page__text-button" onClick={() => void action(async () => { const activity = await getTeachingActivity(id); setActive(activity); setSource(await getTeachingSource(id)); setForm(false) })}>打开依据作业</button>)}
        <button className="qx-button" onClick={() => newForm('lesson_plan', undefined, `${issue.description}\n依据：${issue.evidence.join('；')}\n活动：${issue.activity_ids.join(',')}`, issue.activity_ids)}>据此备课</button>
      </article>)}
    </section>
    <section className="classroom-history" aria-label="教学活动历史"><div className="classroom-section-title"><span><ClockIcon size={18} />教学记录</span><small>{items.length} 条</small></div>{!items.length && <p className="courses-page__hint">还没有教学记录，从备课或一份作业开始。</p>}
      <div className="teacher-teaching__history">{items.map((item) => <button key={item.id} type="button" className="courses-page__text-button" onClick={() => void open(item)} aria-current={active?.id === item.id ? 'true' : undefined}><span className="classroom-record-title">{item.kind === 'lesson_plan' ? <BookOpenIcon size={17} /> : <ClipboardTextIcon size={17} />}<strong>{item.input.title || (item.kind === 'lesson_plan' ? '课堂教案' : item.kind === 'assignment_review' ? '作业批改' : '学习记录')}</strong></span><span className="classroom-record-meta"><span className="classroom-state" data-state={item.state}>{stateNames[item.state]}</span><time>{new Date(item.updated_at).toLocaleDateString()}</time></span></button>)}</div>
    </section></aside></div>
  </section>
}

function RubricFields({ rubric, onChange }: { rubric: RubricDimension[]; onChange: (rubric: RubricDimension[]) => void }) {
  return <fieldset><legend>评价标准（3—5项）</legend>{rubric.map((dimension, i) => <div className="teaching-rubric" key={dimension.id}>
    <label>维度 {i + 1}<input required value={dimension.title} onChange={(e) => onChange(rubric.map((d, j) => j === i ? { ...d, title: e.target.value } : d))} /></label>
    <label>满分<input type="number" min={1} max={1000} value={dimension.max_score} onChange={(e) => onChange(rubric.map((d, j) => j === i ? { ...d, max_score: Number(e.target.value) } : d))} /></label>
    {rubric.length > 3 && <button type="button" className="courses-page__text-button" onClick={() => onChange(rubric.filter((_, j) => j !== i))}>移除</button>}
  </div>)}{rubric.length < 5 && <button type="button" className="courses-page__text-button" onClick={() => onChange([...rubric, { id: crypto.randomUUID(), title: '', max_score: 10 }])}>添加维度</button>}</fieldset>
}
