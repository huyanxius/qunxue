import { courseArtwork } from './courseTemplates'
import { useEffect, useState } from 'react'
import { ArrowRightIcon, BookOpenIcon, CheckCircleIcon, ClipboardTextIcon, FileTextIcon, ListChecksIcon } from '@phosphor-icons/react'
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
  const orderedDocuments = [...course.documents].sort((a, b) => a.filename.localeCompare(b.filename, 'zh-CN', { numeric: true }))
  const ready = course.documents.filter((document) => document.status === 'ready')
  const pending = activities.filter((activity) => teacher ? activity.kind === 'assignment_review' && activity.state !== 'published' : activity.kind === 'learning_check' && activity.result?.stage !== 'feedback' && activity.result?.stage !== 'complete')
  return <div className="course-home">
    <main className="course-home__main"><section className="course-home__welcome"><img className="course-home__image" src={courseArtwork['sociological-thinking']} alt="" /><span className="course-catalog__eyebrow">课程概览</span><h3>{teacher ? '课程内容与教学安排' : '课程内容与学习安排'}</h3><p>{course.description || '在这里阅读课程材料，完成学习与作业，并回看每次反馈。'}</p><div className="course-catalog__metadata"><span><FileTextIcon size={16} />{ready.length} 份可用资料</span><span><ClipboardTextIcon size={16} />{loaded ? `${activities.filter((a) => a.kind === 'assignment_review').length} 份作业记录` : '正在读取教学记录'}</span><span><BookOpenIcon size={16} />{teacher ? '教师工作区' : '学生工作区'}</span></div></section>
      <section className="course-home__section"><div className="course-section-heading"><h3>课程目标</h3><ListChecksIcon size={20} /></div><p>{settings?.objectives || '课程目标尚未单独设置。可先阅读课程说明与单元材料。'}</p>{settings?.rubric?.length ? <div className="course-rubric-overview">{settings.rubric.map((dimension) => <div key={dimension.id}><span>{dimension.title}</span><strong>{dimension.max_score}<small> 分</small></strong></div>)}</div> : null}<p className="courses-page__hint">评价维度用于作业反馈，正式成绩以教师复核发布为准。</p></section>
      <section className="course-home__section"><div className="course-section-heading"><div><h3>课程内容</h3><p>按资料目录逐一阅读，随时回到原文</p></div><button className="courses-page__text-button" onClick={onMaterials}>全部资料<ArrowRightIcon size={15} /></button></div><div className="course-unit-list">{orderedDocuments.map((document, index) => <button key={document.id} disabled={document.status !== 'ready'} onClick={() => onRead(document.id)}><span className="course-unit-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{document.filename.replace(/^\d+[-_. ]/, '').replace(/\.md$/, '')}</strong><small>{document.knowledge?.summary || (document.status === 'ready' ? '课程材料 · 阅读原文与结合资料提问' : document.status === 'failed' ? '解析失败，请联系教师处理' : '正在解析，完成后可阅读')}</small></span><FileTextIcon size={18} /><ArrowRightIcon size={16} /></button>)}</div>{!course.documents.length && <div className="course-catalog__empty"><FileTextIcon size={24} /><div><strong>课程资料待添加</strong><p>{teacher ? '上传讲义、课件或阅读材料，建立这门课的内容目录。' : '教师添加资料后，将在这里展示。'}</p>{teacher && <button className="qx-button" onClick={onMaterials}>管理课程资料</button>}</div></div>}</section>
    </main><aside className="course-home__rail"><section className="course-home__next"><span className="course-catalog__eyebrow">{teacher ? '教学待办' : '继续学习'}</span><h3>{teacher ? '让反馈进入下一次课堂' : '把理解带进新的情境'}</h3><p>{loaded ? `${pending.length} ${teacher ? '份作业等待处理' : '条学习记录尚未完成'}。` : '正在读取任务状态。'}{teacher ? '在教学工作区复核建议分，确认后发布反馈。' : '从目标、诊断到练习，保留每一次回答。'}</p><button className="research-hub__new" onClick={onTeaching}>{teacher ? '进入教学工作区' : '进入学习工作区'}<ArrowRightIcon size={16} /></button></section><section className="course-home__section"><div className="course-section-heading"><h3>课堂使用路径</h3></div><ol className="course-home__path">{(teacher ? ['整理课程资料与教学目标', '结合讲义生成并修订教案', '复核作业并发布反馈', '将共性问题带入下一次备课'] : ['阅读课程目标与单元材料', '通过诊断问答梳理困难', '提交练习或课程作业', '查看反馈并形成修改稿']).map((step) => <li key={step}><CheckCircleIcon size={17} /><span>{step}</span></li>)}</ol></section>{error && <p className="qx-message is-error" role="alert">{error}</p>}</aside>
  </div>
}
