import './course-home-layout.css'
import { CourseWorkshop } from './CourseWorkshop'
import { courseWorkshops } from './courseWorkshops'
import { courseArtwork, courseTemplates } from './courseTemplates'
import { useEffect, useState } from 'react'
import { ArrowRightIcon, BookOpenIcon, CheckCircleIcon, FileTextIcon } from '@phosphor-icons/react'
import type { SharedCourse } from '../../modules/shared-knowledge'
import { getTeachingSettings, listTeachingActivities, type TeachingActivity, type TeachingSettings } from '../../modules/teaching-assistant'

export function CourseHome({ course, onRead, onMaterials, onTeaching }: { course: SharedCourse; onRead: (id: string) => void; onMaterials: () => void; onTeaching: () => void }) {
  const [settings, setSettings] = useState<TeachingSettings | null>(null)
  const [activities, setActivities] = useState<TeachingActivity[]>([])
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    let current = true
    void Promise.all([getTeachingSettings(course.id), listTeachingActivities(course.id)]).then(([nextSettings, nextActivities]) => { if (current) { setSettings(nextSettings); setActivities(nextActivities); setLoaded(true) } }).catch((reason) => { if (current) setError(reason instanceof Error ? reason.message : '教学记录暂时无法读取。') })
    return () => { current = false }
  }, [course.id])
  const teacher = course.access === 'owner'
  const template = course.description?.includes('基于群学致知示范课程创建') ? courseTemplates.find((item) => item.title === course.name) : undefined
  const objectiveLines = (settings?.objectives || template?.outcomes.join('；') || '').split(/[；;\n]/).map((line) => line.trim()).filter(Boolean)
  const orderedDocuments = [...course.documents].sort((a, b) => a.filename.localeCompare(b.filename, 'zh-CN', { numeric: true }))
  const ready = course.documents.filter((document) => document.status === 'ready')
  const pending = activities.filter((activity) => teacher ? activity.kind === 'assignment_review' && activity.state !== 'published' : activity.kind === 'learning_check' && activity.result?.stage !== 'feedback' && activity.result?.stage !== 'complete')
  return <div className="course-home course-home--dense">
    <header className="course-brief">
      <div className="course-brief__copy"><span className="course-catalog__eyebrow">课程总览 / {teacher ? '教学空间' : '学习空间'}</span><h3>{template?.subtitle || course.name}</h3><p>{template?.description || course.description || '阅读课程材料，完成练习，并依据反馈修订成果。'}</p><div className="course-brief__facts"><span><strong>{ready.length}</strong> 份课程资料</span><span><strong>{loaded ? activities.filter((a) => a.kind === 'assignment_review').length : '—'}</strong> 份作业记录</span>{template && <span><strong>{template.chapters.length}</strong> 个方法单元</span>}</div></div>
      <img src={courseArtwork[template?.id ?? 'library']} alt="" />
    </header>
    <section className="course-command-bar" aria-label="课程操作"><div><span className="course-command-bar__dot" /><span>{loaded ? `${pending.length} ${teacher ? '份作业待处理' : '条学习记录未完成'}` : '正在读取教学记录'}</span></div><div><button className="qx-button" onClick={onMaterials}><FileTextIcon size={16} />{teacher ? '管理资料' : '课程资料'}</button><button className="research-hub__new" onClick={onTeaching}>{teacher ? '备课与批改' : '学习与作业'}<ArrowRightIcon size={16} /></button></div></section>
    <section className="course-objectives-strip" aria-label="课程目标与评价">
      <div><h3>学习目标</h3>{objectiveLines.length ? <ul>{objectiveLines.map((outcome) => <li key={outcome}><CheckCircleIcon size={14} />{outcome}</li>)}</ul> : <p>{settings?.objectives || '课程目标尚未单独设置，请结合课程资料阅读。'}</p>}</div>
      <div><h3>评价维度</h3>{settings?.rubric?.length ? <dl>{settings.rubric.map((dimension) => <div key={dimension.id}><dt>{dimension.title}</dt><dd>{dimension.max_score}<small> 分</small></dd></div>)}</dl> : <p>评价要求待教师设置</p>}<small>正式成绩以教师复核发布为准</small></div>
    </section>
    <section className="course-syllabus" aria-label="课程单元与训练成果">
      <div className="course-section-heading"><div><span className="course-catalog__eyebrow">课程内容</span><h3>单元资料与学习任务</h3></div><span>{orderedDocuments.length} 份材料 · 按单元阅读</span></div>
      <div className="course-syllabus__grid">{orderedDocuments.map((document, index) => {
        const title = document.filename.replace(/^\d+[-_. ]/, '').replace(/\.md$/, '')
        const chapterIndex = template?.chapters.findIndex((chapter) => chapter.title === title) ?? -1
        const chapter = template?.chapters[chapterIndex]
        const stage = template ? courseWorkshops[template.id]?.stages[chapterIndex] : undefined
        return <article className="course-syllabus__unit" key={document.id}>
          <div className="course-syllabus__unit-top"><span className="course-unit-number">{String(index + 1).padStart(2, '0')}</span><span>{chapter ? `${chapter.duration} 分钟 · 阅读与讨论` : '课程材料'}</span><span>{document.status === 'ready' ? '可阅读' : document.status === 'failed' ? '解析失败' : '解析中'}</span></div>
          <h4>{title}</h4><p>{chapter?.objective || document.knowledge?.summary || '阅读原文，记录关键概念、论据与待讨论的问题。'}</p>
          {stage && <div className="course-syllabus__deliverable"><span>单元产出</span><strong>{stage.deliverable}</strong></div>}
          <div className="course-syllabus__unit-bottom"><span><BookOpenIcon size={14} />{chapter ? '讲义 · 练习 · 自查' : '原文与资料问答'}</span><button disabled={document.status !== 'ready'} onClick={() => onRead(document.id)}>阅读材料<ArrowRightIcon size={15} /></button></div>
        </article>
      })}</div>
      {!orderedDocuments.length && <div className="course-catalog__empty"><FileTextIcon size={24} /><div><strong>课程资料待添加</strong><p>{teacher ? '上传讲义或阅读材料，建立课程目录。' : '教师添加资料后，将在这里展示。'}</p>{teacher && <button className="qx-button" onClick={onMaterials}>管理课程资料</button>}</div></div>}
    </section>
    <CourseWorkshop templateId={template?.id} courseTitle={course.name} onTeaching={onTeaching} expanded />
    {error && <p className="qx-message is-error" role="alert">{error}</p>}
  </div>
}
