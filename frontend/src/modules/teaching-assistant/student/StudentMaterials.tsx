import { useEffect, useRef, useState } from 'react'
import { addResearchLibraryMaterial, getAgentAttachmentMaterial, listAgentMaterials, prepareAgentMaterialContext, materialStatusLabel, RESEARCH_MATERIAL_ACCEPT, type ResearchMaterial } from '../../research-materials'

export function StudentMaterials({ selectedIds, onChange, disabled = false, onBusyChange }: {
  selectedIds: string[]; onChange: (ids: string[]) => void; disabled?: boolean; onBusyChange?: (busy: boolean) => void
}) {
  const [materials, setMaterials] = useState<ResearchMaterial[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const task = useRef<Promise<Awaited<ReturnType<typeof prepareAgentMaterialContext>>> | null>(null)
  const lock = useRef(false)
  useEffect(() => {
    const controller = new AbortController()
    void listAgentMaterials(controller.signal).then((list) => setMaterials((current) => [...list, ...current.filter((item) => !list.some((loaded) => loaded.materialId === item.materialId))])).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [reload])
  useEffect(() => {
    const pending = materials.filter((m) => m.status === 'processing' || m.status === 'uploaded')
    if (!pending.length) return
    let active = true
    const timer = window.setTimeout(() => {
      void Promise.all(pending.map((m) => getAgentAttachmentMaterial(m.taskId, m.materialId))).then((updated) => {
        if (active) setMaterials((current) => current.map((m) => updated.find((next) => next.materialId === m.materialId) ?? m))
      }).catch((e: Error) => { if (active) setError(e.message) })
    }, 3000)
    return () => { active = false; window.clearTimeout(timer) }
  }, [materials])
  async function upload(files: File[]) {
    if (lock.current) return
    lock.current = true; setBusy(true); onBusyChange?.(true); setError('')
    const added: ResearchMaterial[] = []
    try {
      task.current ??= prepareAgentMaterialContext(null, crypto.randomUUID()).catch((e) => { task.current = null; throw e })
      const context = await task.current
      for (const file of files) {
        const result = await addResearchLibraryMaterial(context.task_id, file)
        added.push(result)
        setMaterials((current) => [...current.filter((m) => m.materialId !== result.materialId), result])
        if (result.status === 'failed') setError(`${file.name} 解析失败，请重新上传。`)
      }
    } catch (e) { setError(e instanceof Error ? e.message : '上传失败，请重试。') }
    finally {
      onChange([...new Set([...selectedIds, ...added.filter((m) => m.status === 'ready').map((m) => m.materialId)])])
      lock.current = false; setBusy(false); onBusyChange?.(false)
    }
  }
  return <fieldset className="student-materials" disabled={disabled || busy}>
    <legend>本次使用的个人材料</legend>
    <label>上传个人材料<input type="file" multiple accept={RESEARCH_MATERIAL_ACCEPT} onChange={(event) => {
      const files = Array.from(event.target.files ?? []); event.target.value = ''
      if (files.length) void upload(files)
    }} /></label>
    {busy ? <p role="status">正在上传并解析个人材料…</p> : null}
    {error ? <p className="qx-message is-error" role="alert">{error}</p> : null}
    {materials.map((material) => <label key={material.materialId} className="student-materials__item">
      <input type="checkbox" aria-label={material.filename} disabled={material.status !== 'ready'} checked={selectedIds.includes(material.materialId)} onChange={() => onChange(selectedIds.includes(material.materialId) ? selectedIds.filter((id) => id !== material.materialId) : [...selectedIds, material.materialId])} />
      <span>{material.filename} · {materialStatusLabel(material.status)}</span>
    </label>)}
    {!materials.length ? <p className="courses-page__hint">可上传材料，也可直接填写内容。</p> : null}
    <button type="button" className="qx-button" onClick={() => { setError(''); setReload((n) => n + 1) }}>刷新材料</button>
  </fieldset>
}
