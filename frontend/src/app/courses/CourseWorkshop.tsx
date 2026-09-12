import { ArrowDownIcon, ArrowRightIcon, BookOpenIcon, ChatCircleTextIcon, FileTextIcon } from '@phosphor-icons/react'
import { courseWorkshops, generalWorkshop } from './courseWorkshops'

export function CourseWorkshop({ templateId, courseTitle, onTeaching }: { templateId?: string; courseTitle: string; onTeaching?: () => void }) {
  const plan = templateId ? courseWorkshops[templateId] ?? generalWorkshop : generalWorkshop
  const workbook = `# ${courseTitle} · 集训练习手册\n\n建议安排，不代表教师已布置的作业。\n\n${plan.brief}\n\n${plan.stages.map((stage, i) => `## 第 ${i + 1} 阶段：${stage.title}\n\n课前准备：${stage.preparation}\n\n练习任务：${stage.task}\n\n本轮成果：${stage.deliverable}\n\n${stage.fields.map((field) => `### ${field}\n\n请在这里记录。\n`).join('\n')}\n讨论问题：${stage.discussion}\n\n检查标准：${stage.review}`).join('\n\n')}\n\n## 最终成果\n${plan.finalWork}\n\n## 修订记录\n收到的反馈：\n采纳或保留的理由：\n修改内容：\n`
  return <section className="course-workshop" aria-label="集训安排与成果要求">
    <header className="course-workshop__heading">
      <div><span className="course-catalog__eyebrow">方法训练 / 建议安排</span><h3>{plan.title}</h3><p>{plan.brief}</p></div>
      <a className="qx-button" download={`${courseTitle}-集训练习手册.md`} href={`data:text/markdown;charset=utf-8,${encodeURIComponent(workbook)}`}><ArrowDownIcon size={16} />下载练习手册</a>
    </header>
    <div className="course-workshop__format"><span><BookOpenIcon size={17} />课前阅读与问题准备</span><span><ChatCircleTextIcon size={17} />每轮建议练习 45 分钟</span><span><FileTextIcon size={17} />四份阶段成果 · 一次综合修订</span></div>
    <div className="course-workshop__stages">{plan.stages.map((stage, index) => <details key={stage.title} open={index === 0}>
      <summary><span className="course-workshop__number">{String(index + 1).padStart(2, '0')}</span><span><strong>{stage.title}</strong><small>{stage.deliverable}</small></span><span className="course-workshop__expand" aria-hidden="true">展开练习</span></summary>
      <div className="course-workshop__stage-body"><div><h4>课前准备</h4><p>{stage.preparation}</p><h4>本轮任务</h4><p>{stage.task}</p><div className="course-workshop__question"><ChatCircleTextIcon size={19} /><p>{stage.discussion}</p></div></div><aside><h4>成果需要包含</h4><ul>{stage.fields.map((field) => <li key={field}>{field}</li>)}</ul><h4>完成后检查</h4><p>{stage.review}</p></aside></div>
    </details>)}</div>
    <div className="course-workshop__final"><span className="course-catalog__eyebrow">综合成果</span><h4>保留证据，也保留思路改变的过程</h4><p>{plan.finalWork}</p><ol><li><strong>初稿</strong><span>先呈现自己的判断及其依据</span></li><li><strong>反馈</strong><span>指出具体问题与可执行的修改</span></li><li><strong>修订</strong><span>保留修改理由与尚未解决的问题</span></li></ol>{onTeaching && <button className="research-hub__new" onClick={onTeaching}>打开学习与教学任务<ArrowRightIcon size={16} /></button>}</div>
    <p className="course-workshop__notice">以上为原创示范训练建议，不是已发布作业或固定课表。正式任务、提交方式与评价标准以教师要求为准。</p>
  </section>
}
