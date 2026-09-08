import { CourseIconButton } from './CourseIconButton'
import { XIcon, ArrowRightIcon, BooksIcon, ChatCircleTextIcon, TreeStructureIcon } from '@phosphor-icons/react'

export function CourseWelcome({ onStart }: { onStart: () => void }) {
  return <section className="course-welcome">
    <header className="course-welcome__hero">
      <p className="course-welcome__eyebrow">课程</p>
      <h1>课件、知识点和学习对话，在同一门课程里</h1>
      <p className="course-welcome__description">老师把课件整理成可以共享的课程知识库。学生加入后，既能阅读原文，也能带着课程资料向 Agent 提问。</p>
    </header>
    <div className="course-welcome__roles">
      <section><h2>教师：把资料组织成一门课</h2><p>创建课堂，上传课件和补充阅读。系统整理知识点与课程导图，再由你决定何时分享给学生。</p></section>
      <section><h2>学生：沿着知识点读懂原文</h2><p>通过老师的链接加入课堂。在资料与导图之间切换，需要讨论时，自行选择是否让 Agent 参考这门课。</p></section>
    </div>
    <div className="course-welcome__start"><button type="button" className="research-hub__new" onClick={onStart}>开始使用课程<ArrowRightIcon size={17} /></button><span>下一步选择身份，之后会为你记住。</span></div>
    <ol className="course-welcome__flow">
      <li><BooksIcon size={23} weight="light" /><div><h3>资料放在一起</h3><p>课件与文档集中阅读，切换文件不必离开课程。</p></div></li>
      <li><TreeStructureIcon size={23} weight="light" /><div><h3>知识点连回原文</h3><p>从课程导图查看关联，再打开对应的课件段落。</p></div></li>
      <li><ChatCircleTextIcon size={23} weight="light" /><div><h3>带着依据继续问</h3><p>选用课程资料提问，回答中的引用可以回到原文。</p></div></li>
    </ol>
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
