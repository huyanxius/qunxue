import {
  ArrowRightIcon,
  CircleNotchIcon,
  FileTextIcon,
  FolderOpenIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import {
  isSupportedResearchMaterialFile,
  RESEARCH_MATERIAL_ACCEPT,
  uploadInitialResearchMaterials,
} from '../../modules/research-materials'
import { createExistingResearchProject } from '../../modules/socio-match-workspace'
import { PageContent, PageShell } from '../ui/PageShell'
import './existing-research-entry.css'

const PROJECT_STAGES = ['材料整理', '研究设计', '田野进行中', '分析与编码', '写作与修订'] as const

function entryRequestKey() {
  return globalThis.crypto?.randomUUID?.()
    ? `existing:${globalThis.crypto.randomUUID()}`
    : `existing:${Date.now()}`
}

export function ExistingResearchEntryPage() {
  const navigate = useNavigate()
  const requestKey = useRef<string | null>(null)
  const [projectTitle, setProjectTitle] = useState('')
  const [projectStage, setProjectStage] = useState<(typeof PROJECT_STAGES)[number]>('材料整理')
  const [methodOrientation, setMethodOrientation] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function establishProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !projectTitle.trim() || files.length === 0) return
    const unsupported = files.find((file) => !isSupportedResearchMaterialFile(file))
    if (unsupported) {
      setError(`${unsupported.name} 不是可导入的 PDF、DOCX、TXT 或 Markdown 文件。`)
      return
    }

    setBusy(true)
    setError(null)
    try {
      requestKey.current ??= entryRequestKey()
      const taskId = createdTaskId ?? (await createExistingResearchProject(requestKey.current, {
        projectTitle: projectTitle.trim(),
        projectStage,
        methodOrientation: methodOrientation.trim() || undefined,
      })).taskId
      setCreatedTaskId(taskId)
      await uploadInitialResearchMaterials(taskId, files)
      navigate(`/research/materials?task_id=${encodeURIComponent(taskId)}`, { replace: true })
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '项目暂时无法建立，请重试。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PageShell>
      <PageContent>
        <main className="research-entry" aria-labelledby="research-entry-title">
          <header className="research-entry__heading">
            <Link to="/research/new">返回从零开始</Link>
            <span><FolderOpenIcon size={15} />已有研究</span>
            <h1 id="research-entry-title">把正在进行的研究接进来</h1>
            <p>建立一个项目，再把已有的访谈、田野记录或文献作为首批材料导入。它们会继续留在同一项研究里。</p>
          </header>

          <div className="research-entry__layout">
            <form className="research-entry__form" noValidate onSubmit={establishProject}>
              <label htmlFor="research-project-title">
                <span>项目名称</span>
                <input
                  id="research-project-title"
                  autoFocus
                  required
                  maxLength={300}
                  value={projectTitle}
                  onChange={(event) => setProjectTitle(event.target.value)}
                  placeholder="例如：社区照护田野研究"
                />
              </label>

              <div className="research-entry__form-row">
                <label htmlFor="research-project-stage">
                  <span>当前阶段</span>
                  <select
                    id="research-project-stage"
                    value={projectStage}
                    onChange={(event) => setProjectStage(event.target.value as (typeof PROJECT_STAGES)[number])}
                  >
                    {PROJECT_STAGES.map((stage) => <option key={stage}>{stage}</option>)}
                  </select>
                </label>
                <label htmlFor="research-method-orientation">
                  <span>方法取向 <small aria-hidden="true">可选</small></span>
                  <input
                    id="research-method-orientation"
                    maxLength={300}
                    value={methodOrientation}
                    onChange={(event) => setMethodOrientation(event.target.value)}
                    placeholder="例如：质性访谈"
                  />
                </label>
              </div>

              <label className="research-entry__drop" htmlFor="research-initial-materials">
                <FileTextIcon size={23} />
                <strong>选择初始材料</strong>
                <span>可一次选择多份 PDF、DOCX、TXT 或 Markdown</span>
                <input
                  id="research-initial-materials"
                  aria-label="选择初始材料"
                  type="file"
                  multiple
                  required
                  accept={RESEARCH_MATERIAL_ACCEPT}
                  onChange={(event) => {
                    setFiles(Array.from(event.target.files ?? []))
                    setError(null)
                  }}
                />
              </label>

              {error ? <p className="research-entry__error" role="alert">{error}</p> : null}
              <button className="research-entry__submit" type="submit" disabled={busy || !projectTitle.trim() || files.length === 0}>
                {busy ? <><CircleNotchIcon size={16} />正在建立并导入…</> : <>建立项目并导入材料 <ArrowRightIcon size={16} /></>}
              </button>
            </form>

            <aside className="research-entry__manifest" aria-label="待导入材料">
              <header><span>初始材料</span><strong>{files.length ? `${files.length} 份` : '尚未选择'}</strong></header>
              {files.length ? (
                <ol>
                  {files.map((file, index) => (
                    <li key={`${file.name}:${file.size}:${index}`}>
                      <FileTextIcon size={15} />
                      <span><strong>{file.name}</strong><small>{Math.max(1, Math.ceil(file.size / 1024))} KB</small></span>
                      <button type="button" aria-label={`移除 ${file.name}`} onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}><XIcon size={13} /></button>
                    </li>
                  ))}
                </ol>
              ) : <p>选择文件后，这里会列出即将归入项目的材料。</p>}
              <footer>建立后会直接进入这项研究的材料工作台。</footer>
            </aside>
          </div>
        </main>
      </PageContent>
    </PageShell>
  )
}
