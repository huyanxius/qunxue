import { CaretDownIcon, CaretRightIcon, FolderIcon, FolderOpenIcon, PencilLineIcon } from '@phosphor-icons/react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { groupProjectConversations } from '../../modules/research-projects'
import type { AgentConversationSummary } from '../../modules/research-agent'
import { useAppLocale } from '../i18n/AppLocaleProvider'
import './project-conversation-list.css'

export function ProjectConversationList({ projects, conversations, activeTaskId, onStart, renderConversation }: {
  projects: { task_id: string; project_title: string; status: string }[]
  conversations: AgentConversationSummary[]
  activeTaskId: string | null
  onStart: (taskId: string) => void
  renderConversation: (conversation: AgentConversationSummary) => ReactNode
}) {
  const { text } = useAppLocale()
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(activeTaskId ? [activeTaskId] : []))
  useEffect(() => {
    if (activeTaskId) setExpanded((current) => new Set([...current, activeTaskId]))
  }, [activeTaskId])
  const groups = groupProjectConversations(projects, conversations)
  return <div className="project-conversation-list">
    {groups.projects.map(({ project, conversations: items }) => {
      const open = expanded.has(project.task_id)
      return <section role="group" aria-label={project.project_title} key={project.task_id} className="project-conversation-list__project">
        <div className="project-conversation-list__heading" data-current={activeTaskId === project.task_id || undefined}>
          <button type="button" aria-expanded={open} onClick={() => setExpanded((current) => {
            const next = new Set(current)
            if (open) next.delete(project.task_id)
            else next.add(project.task_id)
            return next
          })} title={project.project_title}>
            {open ? <CaretDownIcon size={12} /> : <CaretRightIcon size={12} />}
            {open ? <FolderOpenIcon size={18} /> : <FolderIcon size={18} />}
            <span>{project.project_title}</span>
          </button>
          {project.status !== 'archived' ? <button type="button" className="project-conversation-list__new" aria-label={text(`在${project.project_title}中新建对话`, `New conversation in ${project.project_title}`)} onClick={() => onStart(project.task_id)}><PencilLineIcon size={17} /></button> : null}
        </div>
        {open ? <div className="project-conversation-list__children">
          <div className="project-conversation-list__resources">
            <Link to={`/research/${project.task_id}/workspace/materials`}>{text('项目材料', 'Materials')}</Link>
            <Link to={`/research/${project.task_id}/workspace/map`}>{text('研究上下文', 'Research context')}</Link>
          </div>
          {items.map(renderConversation)}
          {!items.length ? <p>{text('还没有对话', 'No conversations yet')}</p> : null}
        </div> : null}
      </section>
    })}
    <section role="group" aria-label={text('独立对话', 'Independent conversations')}>
      <h3>{text('独立对话', 'Independent conversations')}</h3>
      {groups.unassigned.map(renderConversation)}
      {!groups.unassigned.length ? <p>{text('未归属项目的对话会显示在这里', 'Conversations without a project appear here')}</p> : null}
    </section>
    {groups.unavailable.length ? <section role="group" aria-label={text('项目暂不可用', 'Project unavailable')}>
      <h3>{text('项目暂不可用', 'Project unavailable')}</h3>
      {groups.unavailable.map(renderConversation)}
    </section> : null}
  </div>
}
