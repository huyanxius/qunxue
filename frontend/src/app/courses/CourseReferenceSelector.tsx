import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { listCourses, type SharedCourse } from '../../modules/shared-knowledge'
import './courses.css'

export function CourseReferenceSelector({ value, hasConversation, disabled, onChange }: {
  value: string
  hasConversation: boolean
  disabled: boolean
  onChange: (value: string) => void
}) {
  const [courses, setCourses] = useState<SharedCourse[]>([])
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let active = true
    void listCourses().then((items) => { if (active) { setCourses(items); setFailed(false) } }).catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [value])
  const found = courses.find((course) => course.id === value)
  return <div className="course-reference-selector">
    <label>课程参考 <select aria-label="参考课程资料" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      <option value="">不使用课程资料</option>
      {value && !found ? <option value={value}>当前课程资料{failed ? '暂不可用' : ''}</option> : null}
      {courses.map((course) => <option key={course.id} value={course.id} disabled={course.access === 'unavailable'}>{course.name ?? '课程资料不可用'}{course.access === 'unavailable' ? '（不可用）' : ''}</option>)}
    </select></label>
    {hasConversation ? <span>切换将开启新对话</span> : value ? <span>作为补充参考</span> : null}
    {(failed || found?.access === 'unavailable') ? <Link to="/courses?view=student">查看课程状态</Link> : null}
  </div>
}
