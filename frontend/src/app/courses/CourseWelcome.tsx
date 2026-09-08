import { CourseIconButton } from './CourseIconButton'
import { XIcon, ArrowRightIcon, BooksIcon, ChatCircleTextIcon, TreeStructureIcon } from '@phosphor-icons/react'
import { ResearchLibraryBot } from '../research/ResearchLibraryBot'

export function CourseWelcome({ onStart }: { onStart: () => void }) {
  return <section className="course-welcome">
    <header className="course-welcome__hero">
      <ResearchLibraryBot graduationCap />
      <h1>课程</h1>
      <p className="course-welcome__description">阅读课堂资料，梳理知识脉络，带着依据提问。</p>
    </header>
    <ul className="course-welcome__flow" aria-label="课程功能">
      <li><BooksIcon size={26} weight="light" aria-hidden="true" /><h2>课程资料</h2><p>课件与补充阅读，集中查阅</p></li>
      <li><TreeStructureIcon size={26} weight="light" aria-hidden="true" /><h2>知识导图</h2><p>梳理知识关联，回到原文</p></li>
      <li><ChatCircleTextIcon size={26} weight="light" aria-hidden="true" /><h2>学习对话</h2><p>结合课程提问，核对引用</p></li>
    </ul>
    <div className="course-welcome__start"><button type="button" className="research-hub__new" onClick={onStart}>开始使用课程<ArrowRightIcon size={17} aria-hidden="true" /></button><p>教师创建与分享<span aria-hidden="true"> · </span>学生加入与学习</p></div>
  </section>
}

export function CourseGuide({ role, hasCourse, hasDocuments, shared, onCreate, onUpload, onShare, onJoin, onRead, onDismiss }: {
  role: 'teacher' | 'student'
  hasCourse: boolean
  hasDocuments: boolean
  shared: boolean
  onCreate: () => void
  onUpload: () => void
  onShare: () => void
  onJoin: () => void
  onRead: () => void
  onDismiss: () => void
}) {
  const teacher = role === 'teacher'
  const title = teacher ? !hasCourse ? '先创建你的第一门课程' : !hasDocuments ? '接下来，上传课程资料' : !shared ? '资料准备好后，邀请学生加入' : '课程已可以与学生共享' : !hasCourse ? '先加入老师分享的课堂' : '从阅读课程资料开始'
  return <section className="course-guide" aria-label="课程使用引导">
    <div className="course-guide__heading"><div><span>开始使用</span><h2>{title}</h2></div><CourseIconButton label="收起引导" onClick={onDismiss}><XIcon size={18} /></CourseIconButton></div>
    <ol>{(teacher ? ['创建课堂', '上传资料，等待知识整理', '分享链接给学生'] : ['粘贴老师的分享链接', '阅读资料与课程导图', '选择课程资料，开始对话']).map((step, i) => <li key={step}><span>{i + 1}</span>{step}</li>)}</ol>
    {teacher ? !hasCourse ? <button className="qx-button" type="button" onClick={onCreate}>创建第一门课程</button> : !hasDocuments ? <button className="qx-button" type="button" onClick={onUpload}>上传第一份课件</button> : !shared ? <button className="qx-button" type="button" onClick={onShare}>查看分享设置</button> : <p>新增资料也会在这门课程中更新。你可以随时关闭共享或移除文件。</p> : !hasCourse ? <button className="qx-button" type="button" onClick={onJoin}>粘贴课程链接</button> : <button className="qx-button" type="button" onClick={onRead}>打开已加入的课堂</button>}
  </section>
}
