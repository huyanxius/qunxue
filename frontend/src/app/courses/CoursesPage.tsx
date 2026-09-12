import { CourseCatalog } from './CourseCatalog'
import { copyCourseText } from './copyCourseText'
import { useAccount } from '../../modules/account'
import { ResearchAgentConversationPage } from '../agent/ResearchAgentConversationPage'
import { CourseIconButton } from './CourseIconButton'
import { CourseWelcome, CourseGuide } from './CourseWelcome'
import { CourseShader } from './CourseShader'
import { ArrowClockwiseIcon, ArrowLeftIcon, ArrowRightIcon, ArrowUpRightIcon, ChalkboardTeacherIcon, StudentIcon, SpinnerGapIcon, CheckIcon, PencilSimpleIcon, QuestionIcon, SignOutIcon, ToggleLeftIcon, ToggleRightIcon, TreeStructureIcon, UserSwitchIcon, XIcon, FileTextIcon, GraduationCapIcon, LinkIcon, PlusIcon, TrashIcon, UploadSimpleIcon } from '@phosphor-icons/react'
import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { PageContent, PageShell } from '../ui/PageShell'
import { ResearchHubToolbar } from '../research/ResearchHubToolbar'
import { ReadOnlyMaterialReader } from './ReadOnlyMaterialReader'
import { formatMaterialSize } from '../../modules/research-materials'
import { COURSE_DOCUMENT_ACCEPT, readCourseProfile, saveCourseRole, retryCourseDocument, createCourse, deleteCourse, detachCourseDocument, getCourse, joinCourse, leaveCourse, listCourses, readCourseDocument, updateCourse, uploadCourseDocument, type SharedCourse, type SharedSource } from '../../modules/shared-knowledge'
import '../research/research-materials-page.css'
import './courses.css'
import { COURSE_INVITATION_KEY } from './CourseInvitationRoute'

const CourseHome = lazy(() => import('./CourseHome').then((module) => ({ default: module.CourseHome })))
const TeacherTeachingPanel = lazy(() => import('../../modules/teaching-assistant').then((module) => ({ default: module.TeacherTeachingPanel })))
const StudentLearningPanel = lazy(() => import('../../modules/teaching-assistant').then((module) => ({ default: module.StudentLearningPanel })))

export function CoursesPage() {
  const account = useAccount()
  const userId = account.sessionState.status === 'authenticated' ? account.sessionState.session.user.userId : null
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const routerNavigate = useNavigate()
  const [reload, setReload] = useState(0)
  const [role, setRole] = useState<'teacher' | 'student' | null | undefined>(undefined)
  const [choosingRole, setChoosingRole] = useState(false)
  const [onboardingStarted, setOnboardingStarted] = useState(false)
  const [guideDismissed, setGuideDismissed] = useState(true)
  const view = role ?? 'student'
  useEffect(() => {
    let active = true
    void readCourseProfile().then((value) => { if (active) { setRole(value.role); setGuideDismissed(value.guideDismissed) } })
      .catch((e: Error) => { if (active) setError(e.message) })
    return () => { active = false }
  }, [reload])
  const id = params.get('kb_id')
  const teachingOpen = params.get('teaching') === '1'
  const homeOpen = params.get('section') === 'overview' && !teachingOpen
  const [teachingDirty, setTeachingDirty] = useState(false)
  useEffect(() => {
    if (!teachingDirty) return
    const confirmLink = (event: MouseEvent) => {
      if ((event.target as Element)?.closest('a[href]') && !window.confirm('当前教学修改尚未保存，确定离开？')) { event.preventDefault(); event.stopPropagation() }
    }
    document.addEventListener('click', confirmLink, true)
    return () => document.removeEventListener('click', confirmLink, true)
  }, [teachingDirty])
  const documentId = params.get('document_id')
  const segmentId = params.get('segment_id')
  const [courses, setCourses] = useState<SharedCourse[]>([])
  const [detail, setDetail] = useState<SharedCourse | null>(null)
  const [source, setSource] = useState<SharedSource | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const deleteDialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (deleting) deleteDialog.current?.showModal()
    else deleteDialog.current?.close()
  }, [deleting])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [shareLink, setShareLink] = useState('')
  const [manualShareCopy, setManualShareCopy] = useState(false)
  const [joinOpen, setJoinOpen] = useState(location.pathname.endsWith('/join'))
  const uploadRef = useRef<HTMLInputElement>(null)
  const busyRef = useRef(false)
  const token = location.pathname.endsWith('/join') ? sessionStorage.getItem(COURSE_INVITATION_KEY) : null
  useEffect(() => {
    let active = true
    setLoading(true); setError(null); setDetail(null); setSource(null)
    void (async () => {
      const list = await listCourses()
      if (!active) return
      setCourses(list)
      if (id) {
        const value = await getCourse(id)
        if (!active) return
        setDetail(value)
        if (documentId) {
          const result = await readCourseDocument(id, documentId)
          if (active) setSource(result)
        }
      }
    })().catch((e: Error) => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id, documentId, reload])

  useEffect(() => {
    if (!detail?.documents.some((doc) => doc.status === 'ready' && [doc.knowledgeStatus, doc.indexStatus].some((status) => status === 'queued' || status === 'running'))) return
    let active = true
    const timer = window.setInterval(() => {
      void getCourse(detail.id).then((value) => { if (active) setDetail(value) })
        .catch((e: Error) => { if (active) { setError(e.message); window.clearInterval(timer) } })
    }, 3000)
    return () => { active = false; window.clearInterval(timer) }
  }, [detail])

  function navigate(viewName: string, courseId?: string, docId?: string) {
    if (teachingDirty && !window.confirm('当前教学修改尚未保存，确定离开？')) return
    setEditing(false); setNotice(null); setError(null)
    const next = new URLSearchParams({ view: viewName })
    if (courseId) { next.set('kb_id', courseId); next.set('section', 'overview') }
    if (docId) next.set('document_id', docId)
    if (courseId === id && params.get('conversation_id')) next.set('conversation_id', params.get('conversation_id')!)
    routerNavigate(`/courses?${next.toString()}`)
  }
  async function action(work: () => Promise<void>) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true); setError(null); setNotice(null)
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : '操作失败，请重试。') }
    finally { busyRef.current = false; setBusy(false) }
  }
  async function save(event: FormEvent) {
    event.preventDefault()
    await action(async () => {
      const result = detail ? await updateCourse(detail.id, { name, description }) : await createCourse({ name, description })
      setDetail(result); setEditing(false); setCourses(await listCourses())
      if (!detail) setParams({ view: 'teacher', kb_id: result.id })
    })
  }
  async function addSource(event: FormEvent) {
    event.preventDefault()
    await action(async () => {
      let value = token
      if (!value) {
        try { value = new URLSearchParams(new URL(shareLink).hash.slice(1)).get('token') } catch { throw new Error('请粘贴完整的课程分享链接。') }
      }
      if (!value) throw new Error('分享链接缺少添加标识。')
      const joined = await joinCourse(value)
      sessionStorage.removeItem(COURSE_INVITATION_KEY)
      setJoinOpen(false); setShareLink(''); setNotice('已添加课程')
      // Remove the invitation token once used; subsequent reads use the saved membership.
      routerNavigate(`/courses?view=student&kb_id=${encodeURIComponent(joined.knowledgeBaseId)}`, { replace: true })
      setReload((n) => n + 1)
    })
  }
  const owned = detail?.access === 'owner'
  const visible = courses.filter((course) => (view === 'teacher' ? course.access === 'owner' : course.access !== 'owner') && (!query || course.name?.includes(query)))

  const guideCourse = detail ?? courses.find((item) => role === 'teacher' ? item.access === 'owner' : item.access === 'reader')
  const welcome = role === null && !onboardingStarted && !choosingRole
  function openFirstCourse() { if (guideCourse) navigate(view, guideCourse.id) }

  if (source && role && !choosingRole) return <PageShell immersive wide>
    <section className="coding-workspace course-reading-workspace" aria-label="课程阅读工作区">
      <ReadOnlyMaterialReader key={source.document.id} source={{ ...source, document: detail?.documents.find((doc) => doc.id === source.document.id) ?? source.document }} selectedSegmentId={segmentId}
        agentPanel={<ResearchAgentConversationPage embedded userId={userId} referenceKnowledgeBaseId={source.knowledgeBaseId} conversationId={params.get('conversation_id')} composerAriaLabel="结合课程资料提问" onOpenCourseCitation={(citation) => {
          if (!citation.knowledge_base_id || !citation.material_id || !citation.segment_id) return
          setParams((current) => { const next = new URLSearchParams(current); next.set('kb_id', citation.knowledge_base_id!); next.set('document_id', citation.material_id!); next.set('segment_id', citation.segment_id!); return next })
        }} onConversationStarted={({ conversation_id }) => setParams((current) => { const next = new URLSearchParams(current); next.set('conversation_id', conversation_id); return next }, { replace: true })} />}
        onBack={() => navigate(view, source.knowledgeBaseId)}
        navigation={<div className="coding-workspace__navigation course-reading-workspace__navigation">
          <CourseIconButton label="返回课程" onClick={() => navigate(view, source.knowledgeBaseId)}><ArrowLeftIcon size={18} /></CourseIconButton>
          <span className="course-reading-workspace__title">{source.knowledgeBaseName}</span>
          <span aria-hidden="true">/</span>
          <select aria-label="切换课程文件" value={source.document.id} onChange={(event) => navigate(view, source.knowledgeBaseId, event.target.value)}>
            {detail?.documents.filter((doc) => doc.status === 'ready').map((doc) => <option key={doc.id} value={doc.id}>{doc.filename}</option>)}
          </select>
          <Link className="course-icon-button" aria-label="课程导图" title="课程导图" to={`/knowledge?scope=courses&kb_id=${encodeURIComponent(source.knowledgeBaseId)}`}><TreeStructureIcon size={18} /></Link>
        </div>} />
    </section>
  </PageShell>

  return <PageShell wide backdrop={<CourseShader />}><PageContent><section className="courses-page research-hub">
    {!welcome && role && !choosingRole ? <header className="courses-page__heading">
      <GraduationCapIcon size={32} weight="light" aria-hidden="true" />
      <h1>课程</h1><p>把课堂资料带进阅读与对话。</p>
    </header> : null}
    {role && !choosingRole ? <div className="courses-page__identity"><span>{role === 'teacher' ? '我的教学' : '我的学习'}</span><div><CourseIconButton label="使用引导" onClick={() => setGuideDismissed(false)}><QuestionIcon size={19} /></CourseIconButton><CourseIconButton label="更改身份" onClick={() => setChoosingRole(true)}><UserSwitchIcon size={19} /></CourseIconButton></div></div> : null}
    <div className="research-hub__body"><div className="research-hub__panel">
      {error ? <p className="qx-message is-error" role="alert">{error}<CourseIconButton label="重试" onClick={() => setReload((n) => n + 1)}><ArrowClockwiseIcon size={18} /></CourseIconButton></p> : null}
      {notice ? <p className="research-hub__notice" role="status">{notice}</p> : null}
      {uploadProgress ? <p className="research-hub__notice" role="status">{uploadProgress}</p> : null}
      {loading && role !== undefined ? <p role="status" className="research-hub__notice">正在读取课程资料…</p> : null}
      {role && !guideDismissed && !choosingRole && !source && !editing && !joinOpen ? <CourseGuide role={role} hasCourse={Boolean(guideCourse)} hasDocuments={Boolean(guideCourse?.readyDocumentCount || guideCourse?.documents.length)} shared={guideCourse?.sharingEnabled ?? false}
        onCreate={() => { setName(''); setDescription(''); setEditing(true) }}
        onUpload={() => { if (detail) uploadRef.current?.click(); else openFirstCourse() }} onShare={openFirstCourse}
        onJoin={() => setJoinOpen(true)} onRead={openFirstCourse}
        onDismiss={() => void action(async () => { await saveCourseRole(role, true); setGuideDismissed(true) })} /> : null}
      {welcome ? <><CourseWelcome onStart={() => setOnboardingStarted(true)} /><CourseCatalog courses={[]} role="student" query="" onOpen={() => setOnboardingStarted(true)} onRemove={() => undefined} /></> : role === undefined ? <p role="status">正在读取课程身份…</p> : !role || choosingRole ? <section className="courses-page__onboarding">
        <div className="courses-page__onboarding-nav"><CourseIconButton label={role ? "返回课程" : "返回介绍"} disabled={busy} onClick={() => { if (role) setChoosingRole(false); else setOnboardingStarted(false) }}><ArrowLeftIcon size={19} /></CourseIconButton><span>课程 <span aria-hidden="true">/</span> 选择身份</span></div>
        <h1>你将如何使用课程？</h1><p>选择你的角色，之后可随时更改。</p>
        <div className="courses-page__role-options">{(['teacher', 'student'] as const).map((choice) => <button key={choice} type="button" aria-label={choice === 'teacher' ? '我是教师' : '我是学生'} disabled={busy} aria-busy={busy} onClick={() => void action(async () => { setRole(await saveCourseRole(choice)); setGuideDismissed(false); setChoosingRole(false) })}>
          <span className="courses-page__role-icon" aria-hidden="true">{choice === 'teacher' ? <ChalkboardTeacherIcon size={30} weight="light" /> : <StudentIcon size={30} weight="light" />}</span>
          <span className="courses-page__role-copy"><strong>{choice === 'teacher' ? '教师' : '学生'}</strong><span>{choice === 'teacher' ? '创建课堂、整理课件、分享课程知识' : '加入课堂、阅读原文、带着资料提问'}</span></span>
          {busy ? <SpinnerGapIcon size={19} className="course-spinner" aria-hidden="true" /> : <ArrowRightIcon size={19} className="courses-page__role-arrow" aria-hidden="true" />}
        </button>)}</div>
      </section> : detail ? <>
        <CourseIconButton label="返回课程" className="courses-page__back" onClick={() => navigate(view)}><ArrowLeftIcon size={19} /></CourseIconButton>
        <header className="courses-page__detail course-detail-header"><div><h2>{detail.name}</h2><p>{detail.description || '课程参考资料'}</p></div><Link className="research-hub__new" to={`/agent?reference_knowledge_base_id=${encodeURIComponent(detail.id)}`}>{owned ? '使用资料提问' : '开始学习'}<ArrowUpRightIcon size={16} /></Link></header>
        <nav className="course-detail-nav" aria-label="课程功能">
          <button type="button" aria-pressed={homeOpen} onClick={() => { if (!teachingDirty || window.confirm('当前教学修改尚未保存，确定离开？')) setParams((current) => { const next = new URLSearchParams(current); next.delete('teaching'); next.set('section', 'overview'); return next }) }}>课程概览</button>
          <button type="button" className="qx-button" aria-pressed={!teachingOpen && !homeOpen} onClick={() => { if (!teachingDirty || window.confirm('当前教学修改尚未保存，确定离开？')) setParams((current) => { const next = new URLSearchParams(current); next.delete('teaching'); next.delete('section'); return next }) }}>课程资料</button>
          <button type="button" className="qx-button" aria-pressed={teachingOpen} onClick={() => setParams((current) => { const next = new URLSearchParams(current); next.set('teaching', '1'); return next })}>{owned ? '备课与作业' : '学习与作业'}</button>
        </nav>
        {homeOpen ? <Suspense fallback={<p role="status">正在读取课程概览…</p>}><CourseHome key={detail.id} course={detail} onRead={(documentId) => navigate(view, detail.id, documentId)} onMaterials={() => setParams((current) => { const next = new URLSearchParams(current); next.delete('section'); next.delete('teaching'); return next })} onTeaching={() => setParams((current) => { const next = new URLSearchParams(current); next.set('teaching', '1'); return next })} /></Suspense> : teachingOpen ? <Suspense fallback={<p role="status">正在打开课程工具…</p>}>
          {owned ? <TeacherTeachingPanel key={detail.id} course={detail} onDirtyChange={setTeachingDirty} /> : <StudentLearningPanel key={detail.id} course={detail} onDirtyChange={setTeachingDirty} />}
        </Suspense> : <>
        <div className="courses-page__actions"><Link className="qx-button" to={`/knowledge?scope=courses&kb_id=${encodeURIComponent(detail.id)}`}><TreeStructureIcon size={17} />浏览课程知识库</Link></div>
        {owned ? <div className="courses-page__sharing">
          <div><strong>{detail.sharingEnabled ? '已开启分享' : '仅你可使用'}</strong><p>{detail.sharingEnabled ? '学生通过链接加入，课程资料会同步更新。' : '开启后，学生可通过链接添加课程资料。'}</p></div>
          <CourseIconButton label={detail.sharingEnabled ? "关闭分享" : "开启分享"} aria-pressed={detail.sharingEnabled} disabled={busy} onClick={() => void action(async () => { setDetail(await updateCourse(detail.id, { sharing_enabled: !detail.sharingEnabled })) })}>{detail.sharingEnabled ? <ToggleRightIcon size={28} /> : <ToggleLeftIcon size={28} />}</CourseIconButton>
          {detail.sharingEnabled ? <CourseIconButton label="复制链接" disabled={busy} onClick={() => void action(async () => { try { await copyCourseText(`${window.location.origin}/courses/join#token=${detail.shareToken}`); setNotice("分享链接已复制。"); setManualShareCopy(false) } catch { setManualShareCopy(true); setNotice("浏览器未允许自动复制，请手动复制下方链接。") } })}>{notice === "分享链接已复制。" ? <CheckIcon size={19} /> : <LinkIcon size={19} />}</CourseIconButton> : null}
          {manualShareCopy && detail.sharingEnabled ? <label className="courses-page__manual-share">分享链接<input aria-label="手动复制分享链接" readOnly value={`${window.location.origin}/courses/join#token=${detail.shareToken}`} onFocus={(event) => event.currentTarget.select()} /></label> : null}
        </div> : <p className="research-hub__notice">资料作为学习参考，与你原有的知识来源一起使用。</p>}
        {owned ? <div className="courses-page__actions"><button type="button" className="research-hub__new" disabled={busy} onClick={() => uploadRef.current?.click()}><UploadSimpleIcon size={16} />{busy ? '正在处理…' : '上传资料'}</button><CourseIconButton label="编辑课程" disabled={busy} onClick={() => { setName(detail.name ?? ""); setDescription(detail.description ?? ""); setEditing(!editing) }}><PencilSimpleIcon size={19} /></CourseIconButton><button type="button" className="course-icon-button course-icon-button--danger" aria-label="删除课程" title="删除课程" disabled={busy} onClick={() => setDeleting(true)}><TrashIcon size={19} /></button></div> : <CourseIconButton label="移除已添加课程" disabled={busy} onClick={() => void action(async () => { await leaveCourse(detail.id); navigate(view); setReload((n) => n + 1) })}><SignOutIcon size={19} /></CourseIconButton>}
        <input ref={uploadRef} type="file" hidden multiple accept={COURSE_DOCUMENT_ACCEPT} onChange={(event) => {
          const files = Array.from(event.target.files ?? []); event.target.value = ''
          if (!files.length) return
          void action(async () => {
            const failed: string[] = []
            try {
              for (const [index, file] of files.entries()) {
                setUploadProgress(`正在上传 ${index + 1}/${files.length}：${file.name}`)
                try {
                  const result = await uploadCourseDocument(detail.id, file)
                  if (result.status === 'failed') failed.push(file.name)
                } catch { failed.push(file.name) }
              }
              setDetail(await getCourse(detail.id))
              setNotice(failed.length ? `${failed.length} 份资料上传或解析失败：${failed.join('、')}。请检查后重新上传。` : '资料可阅读，正在后台建立语义索引并整理课程知识。')
            } finally { setUploadProgress(null) }
          })
        }} />
        <div className="material-files courses-page__files"><div className="material-files__table-scroll"><table aria-label="课程资料列表"><thead><tr><th>文件名称</th><th>大小</th><th>状态</th>{owned ? <th>操作</th> : null}</tr></thead><tbody>{detail.documents?.map((doc) => <tr key={doc.id}><td><button type="button" className="material-files__filename courses-page__file" disabled={doc.status !== 'ready'} onClick={() => navigate(view, detail.id, doc.id)}><FileTextIcon size={22} /><strong>{doc.filename}</strong></button>{doc.warnings?.map((warning) => <small key={warning} className="courses-page__hint">{warning}</small>)}{doc.errorMessage ? <small className="courses-page__failure">{doc.errorMessage}</small> : null}</td><td>{formatMaterialSize(doc.sizeBytes)}</td><td><span>{doc.status === 'ready' ? '可阅读' : doc.status === 'failed' ? '解析失败' : '解析中'}</span>{doc.status === 'ready' ? <><small className="courses-page__hint">{({queued: '等待知识整理', running: '知识整理中', ready: '知识已整理', failed: '知识整理失败'})[doc.knowledgeStatus]}</small><small className="courses-page__hint">{({queued: '等待语义索引', running: '建立语义索引中', ready: '语义索引就绪', failed: '语义索引失败'})[doc.indexStatus]}</small>{doc.knowledgeError || doc.indexError ? <small className="courses-page__failure">{doc.knowledgeError || doc.indexError}</small> : null}</> : null}</td>{owned ? <td>{doc.status === 'ready' && (doc.knowledgeStatus === 'failed' || doc.indexStatus === 'failed') ? <button type="button" className="course-icon-button" title="重试处理" aria-label={`重试处理 ${doc.filename}`} disabled={busy} onClick={() => void action(async () => { await retryCourseDocument(detail.id, doc.id); setDetail(await getCourse(detail.id)) })}><ArrowClockwiseIcon size={18} /></button> : null}<button type="button" className="course-icon-button course-icon-button--danger" title="移出课程" aria-label={`移出 ${doc.filename}`} disabled={busy} onClick={() => void action(async () => { await detachCourseDocument(detail.id, doc.id); setDetail(await getCourse(detail.id)); setNotice('已从课程移出，原文件仍保留。') })}><TrashIcon size={16} /></button></td> : null}</tr>)}</tbody></table></div>{!detail.documents?.length ? <div className="material-files__empty"><FileTextIcon size={28} /><p>{owned ? '上传课件或文档，开始整理课程资料。' : '老师还没有添加可用资料。'}</p></div> : null}</div>
        {owned ? <p className="courses-page__hint">支持 PDF、DOCX、PPTX、Markdown、TXT，单份不超过 25 MB。PPTX 只读取可提取的正文，教师备注与隐藏页不会共享。</p> : null}
        </>}
      </> : <>
        <ResearchHubToolbar query={query} onQueryChange={setQuery} searchLabel="搜索课程" placeholder="搜索课程名称">
          <button type="button" className="research-hub__new" onClick={() => { if (view === 'teacher') { setName(''); setDescription(''); setEditing(!editing) } else setJoinOpen(!joinOpen) }}><PlusIcon size={17} />{view === 'teacher' ? '创建课程' : '添加课程'}</button>
        </ResearchHubToolbar>
        {joinOpen && view === 'student' ? <form className="courses-page__form" onSubmit={(e) => void addSource(e)}><h2>添加老师分享的课程</h2>{!token ? <label>课程分享链接<input type="url" required value={shareLink} onChange={(e) => setShareLink(e.target.value)} placeholder="粘贴老师提供的链接" /></label> : <p>添加后，可阅读课程资料，并在 AI 对话中选用。</p>}<button type="submit" className="research-hub__new" disabled={busy}>添加到我的知识来源</button><button type="button" className="course-icon-button" aria-label="取消" title="取消" disabled={busy} onClick={() => { sessionStorage.removeItem(COURSE_INVITATION_KEY); setJoinOpen(false); routerNavigate('/courses?view=student', { replace: true }) }}><XIcon size={19} /></button></form> : null}
        {!loading && <CourseCatalog courses={visible} role={view} query={query} onOpen={(courseId) => navigate(view, courseId)} onRemove={(courseId) => void action(async () => { await leaveCourse(courseId); setReload((n) => n + 1) })} />}

      </>}
      {editing ? <form className="courses-page__form" onSubmit={(e) => void save(e)}><h2>{detail ? '编辑课程' : '创建课程资料库'}</h2><label>课程名称<input value={name} required maxLength={100} onChange={(e) => setName(e.target.value)} autoFocus /></label><label>课程说明（选填）<textarea value={description} maxLength={1000} rows={3} onChange={(e) => setDescription(e.target.value)} /></label><div className="courses-page__actions"><button type="submit" className="research-hub__new" disabled={busy}>保存课程</button><CourseIconButton label="取消" disabled={busy} onClick={() => setEditing(false)}><XIcon size={19} /></CourseIconButton></div></form> : null}
      <dialog ref={deleteDialog} className="course-delete-dialog" aria-labelledby="course-delete-title" onCancel={(event) => { event.preventDefault(); if (!busy) setDeleting(false) }}>
        <h2 id="course-delete-title">删除课程？</h2>
        <p>删除后，学生将不能继续使用此课程资料。原文件仍会保留。</p>
        <div className="courses-page__actions">
          <button type="button" className="qx-button" disabled={busy} onClick={() => setDeleting(false)}>保留课程</button>
          <button type="button" className="qx-button" disabled={busy} onClick={() => void action(async () => {
            if (!detail) return
            await deleteCourse(detail.id); setDeleting(false); navigate(view); setReload((n) => n + 1)
          })}>{busy ? '正在删除…' : '确认删除'}</button>
        </div>
        {deleting && error ? <p role="alert" className="qx-message is-error">{error}</p> : null}
      </dialog>
    </div></div>
  </section></PageContent></PageShell>
}
