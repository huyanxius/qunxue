import {
  ArrowDownIcon,
  BookOpenTextIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  FileArrowUpIcon,
  FolderPlusIcon,
  LinkSimpleIcon,
  ShieldCheckIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

import {
  createLiteratureEntry,
  createMaterialBatch,
  createMaterialCollection,
  createMaterialRelation,
  createResearchCase,
  exportLiteratureEntries,
  getProfessionalMaterialArchive,
  importLiteratureEntries,
  resolveDoiMetadata,
  updateProfessionalMaterialProfile,
  uploadMaterialBatch,
} from './professionalMaterialsApi'
import {
  archiveLabel,
  CONSENT_SCOPES,
  DEIDENTIFICATION_STATUSES,
  MODEL_PROCESSING_SCOPES,
  profileUpdateFrom,
  RESEARCH_ROLES,
  RESEARCH_STAGES,
  SENSITIVITY_LEVELS,
  type LiteratureFormat,
  type MaterialKind,
  type MaterialRelationType,
  type ProfessionalMaterialArchive,
  type ProfessionalMaterialProfileUpdate,
} from './professionalMaterialsModel'
import type { ResearchMaterial } from './researchMaterialsModel'

type ProfessionalMaterialArchiveProps = {
  readonly taskId: string
  readonly selectedMaterial: ResearchMaterial
  readonly materials: readonly ResearchMaterial[]
  readonly onMaterialsChanged: () => void
}

const MATERIAL_RELATION_TYPES: readonly MaterialRelationType[] = [
  'derived_from', 'supplements', 'translation_of', 'version_of', 'describes', 'related',
]

const RELATION_LABELS: Record<MaterialRelationType, string> = {
  derived_from: '源自', supplements: '补充', translation_of: '译自',
  version_of: '另一版本', describes: '描述', related: '相关',
}

function parseAttributes(value: string): Record<string, string> {
  return Object.fromEntries(value.split(/[；;\n]/).map((part) => part.trim()).filter(Boolean)
    .map((part) => {
      const [key, ...rest] = part.split(/[=：:]/)
      return [key.trim(), rest.join('=').trim()]
    }).filter(([key, content]) => key && content))
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function ProfessionalMaterialArchivePanel({
  taskId,
  selectedMaterial,
  materials,
  onMaterialsChanged,
}: ProfessionalMaterialArchiveProps) {
  const [archive, setArchive] = useState<ProfessionalMaterialArchive | null>(null)
  const [draft, setDraft] = useState<ProfessionalMaterialProfileUpdate | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [batchName, setBatchName] = useState('')
  const [selectedBatchId, setSelectedBatchId] = useState('')
  const [batchKind, setBatchKind] = useState<MaterialKind>('other')
  const [uploadResults, setUploadResults] = useState<Array<{
    filename: string
    status: string
    message?: string | null
  }>>([])
  const [collectionName, setCollectionName] = useState('')
  const [collectionDescription, setCollectionDescription] = useState('')
  const [caseName, setCaseName] = useState('')
  const [caseAttributes, setCaseAttributes] = useState('')
  const [relationTarget, setRelationTarget] = useState('')
  const [relationType, setRelationType] = useState<MaterialRelationType>('related')
  const [relationNote, setRelationNote] = useState('')
  const [literatureFormat, setLiteratureFormat] = useState<LiteratureFormat>('bibtex')
  const [doi, setDoi] = useState('')
  const batchFileRef = useRef<HTMLInputElement>(null)
  const literatureFileRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setArchive(await getProfessionalMaterialArchive(taskId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '研究档案暂时无法加载。')
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => { void refresh() }, [refresh])

  const profile = archive?.profiles.find(
    (item) => item.material_id === selectedMaterial.materialId,
  ) ?? null

  useEffect(() => {
    setDraft(profile ? profileUpdateFrom(profile) : null)
  }, [profile])

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作暂时无法完成。')
    } finally {
      setBusy(null)
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    if (!draft) return
    await run('profile', async () => {
      await updateProfessionalMaterialProfile(
        taskId, selectedMaterial.materialId, draft,
      )
      await refresh()
      setNotice('材料档案已保存。')
    })
  }

  async function addBatch(event: FormEvent) {
    event.preventDefault()
    if (!batchName.trim()) return
    await run('batch', async () => {
      const created = await createMaterialBatch(taskId, batchName)
      setArchive((current) => current
        ? { ...current, batches: [...current.batches, created] }
        : current)
      setSelectedBatchId(created.batch_id)
      setBatchName('')
      setNotice('批次已建立，可以一次加入多份材料。')
    })
  }

  async function uploadBatchFiles(files: FileList | null) {
    if (!files?.length || !selectedBatchId) return
    await run('upload', async () => {
      const response = await uploadMaterialBatch(
        taskId, selectedBatchId, Array.from(files), batchKind,
      )
      setUploadResults(response.items)
      if (batchFileRef.current) batchFileRef.current.value = ''
      await refresh()
      onMaterialsChanged()
      const failed = response.items.filter((item) => item.status === 'failed').length
      setNotice(failed
        ? `${response.items.length - failed} 份已加入，${failed} 份需要处理。`
        : `${response.items.length} 份材料已加入批次。`)
    })
  }

  async function addCollection(event: FormEvent) {
    event.preventDefault()
    if (!collectionName.trim()) return
    await run('collection', async () => {
      const created = await createMaterialCollection(taskId, {
        name: collectionName, description: collectionDescription || null,
      })
      setArchive((current) => current
        ? { ...current, collections: [...current.collections, created] }
        : current)
      setCollectionName('')
      setCollectionDescription('')
      setNotice('材料集合已建立。')
    })
  }

  async function addCase(event: FormEvent) {
    event.preventDefault()
    if (!caseName.trim()) return
    await run('case', async () => {
      const created = await createResearchCase(taskId, {
        name: caseName,
        attributes: parseAttributes(caseAttributes),
        material_ids: [selectedMaterial.materialId],
      })
      setArchive((current) => current
        ? { ...current, cases: [...current.cases, created] }
        : current)
      setCaseName('')
      setCaseAttributes('')
      setNotice('个案已与当前材料关联。')
    })
  }

  async function addRelation(event: FormEvent) {
    event.preventDefault()
    if (!relationTarget) return
    await run('relation', async () => {
      const created = await createMaterialRelation(taskId, {
        source_material_id: selectedMaterial.materialId,
        target_material_id: relationTarget,
        relation_type: relationType,
        note: relationNote || null,
      })
      setArchive((current) => current
        ? { ...current, relations: [...current.relations, created] }
        : current)
      setRelationTarget('')
      setRelationNote('')
      setNotice('材料关系已记录。')
    })
  }

  async function importLiterature(file: File | null) {
    if (!file) return
    await run('literature-import', async () => {
      const created = await importLiteratureEntries(taskId, file, literatureFormat)
      if (literatureFileRef.current) literatureFileRef.current.value = ''
      await refresh()
      setNotice(`已导入 ${created.length} 条文献，疑似重复项会保留供核对。`)
    })
  }

  async function exportLiterature(format: LiteratureFormat) {
    await run(`export-${format}`, async () => {
      const blob = await exportLiteratureEntries(taskId, format)
      const extension = format === 'csl_json' ? 'json' : format === 'bibtex' ? 'bib' : 'ris'
      download(blob, `qunxue-literature.${extension}`)
      setNotice('文献条目已导出。')
    })
  }

  async function addByDoi(event: FormEvent) {
    event.preventDefault()
    if (!doi.trim()) return
    await run('doi', async () => {
      const candidate = await resolveDoiMetadata(taskId, doi)
      await createLiteratureEntry(taskId, {
        item_type: candidate.item_type,
        title: candidate.title,
        doi: candidate.doi,
        csl_data: candidate.csl_data,
        attachment_material_ids: [],
        collection_ids: [],
      })
      setDoi('')
      await refresh()
      setNotice('DOI 元数据已核对并加入文献条目。')
    })
  }

  if (loading && !archive) {
    return <p className="professional-archive__loading" role="status"><CircleNotchIcon className="is-spinning" size={16} />正在清点研究档案</p>
  }
  if (!archive || !draft) {
    return <p className="professional-archive__message is-error" role="alert"><WarningCircleIcon size={16} />{error || '当前材料档案暂时无法打开。'}</p>
  }

  const inventory = archive.inventory
  const currentRestricted = inventory.restricted_material_ids.includes(selectedMaterial.materialId)
  const currentPending = inventory.pending_deidentification_material_ids.includes(
    selectedMaterial.materialId,
  )
  const otherMaterials = materials.filter(
    (item) => item.materialId !== selectedMaterial.materialId,
  )

  return (
    <div className="professional-archive">
      <section className="professional-archive__ledger" aria-label="档案清点">
        <header><span>档案清点</span><strong>{archive.profiles.length} / {materials.length}</strong></header>
        <dl>
          <div><dt>待编目</dt><dd>{inventory.catalog_pending_material_ids.length}</dd></div>
          <div><dt>待去标识化</dt><dd>{inventory.pending_deidentification_material_ids.length}</dd></div>
          <div><dt>限制模型处理</dt><dd>{inventory.restricted_material_ids.length}</dd></div>
          <div><dt>疑似重复文献</dt><dd>{inventory.suspected_duplicate_literature_ids.length}</dd></div>
        </dl>
      </section>

      {currentRestricted || currentPending ? (
        <p className="professional-archive__guardrail" role="status">
          <ShieldCheckIcon size={17} />
          <span><strong>当前材料仍可人工阅读。</strong>{currentPending ? ' 完成去标识化，' : ''}{currentRestricted ? '明确模型处理范围后，才会进入 Agent 检索。' : ''}</span>
        </p>
      ) : null}
      {error ? <p className="professional-archive__message is-error" role="alert"><WarningCircleIcon size={15} />{error}</p> : null}
      {notice ? <p className="professional-archive__message is-success" role="status"><CheckCircleIcon size={15} />{notice}</p> : null}

      <form className="professional-archive__profile" onSubmit={saveProfile}>
        <header><div><span>当前材料</span><h4>身份、伦理与处理范围</h4></div><small>{selectedMaterial.filename}</small></header>
        <div className="professional-archive__form-grid">
          <label><span>研究角色</span><select value={draft.research_role} onChange={(event) => setDraft({ ...draft, research_role: event.target.value as typeof draft.research_role })}>{RESEARCH_ROLES.map((value) => <option key={value} value={value}>{archiveLabel(value)}</option>)}</select></label>
          <label><span>专业类型</span><input value={draft.specific_type} onChange={(event) => setDraft({ ...draft, specific_type: event.target.value })} placeholder="如：半结构访谈" /></label>
          <label><span>研究阶段</span><select value={draft.stage} onChange={(event) => setDraft({ ...draft, stage: event.target.value as typeof draft.stage })}>{RESEARCH_STAGES.map((value) => <option key={value} value={value}>{archiveLabel(value)}</option>)}</select></label>
          <label><span>敏感性</span><select value={draft.sensitivity} onChange={(event) => setDraft({ ...draft, sensitivity: event.target.value as typeof draft.sensitivity })}>{SENSITIVITY_LEVELS.map((value) => <option key={value} value={value}>{archiveLabel(value)}</option>)}</select></label>
          <label><span>同意范围</span><select value={draft.consent_scope} onChange={(event) => setDraft({ ...draft, consent_scope: event.target.value as typeof draft.consent_scope })}>{CONSENT_SCOPES.map((value) => <option key={value} value={value}>{archiveLabel(value)}</option>)}</select></label>
          <label><span>去标识化</span><select value={draft.deidentification_status} onChange={(event) => setDraft({ ...draft, deidentification_status: event.target.value as typeof draft.deidentification_status })}>{DEIDENTIFICATION_STATUSES.map((value) => <option key={value} value={value}>{archiveLabel(value)}</option>)}</select></label>
          <label><span>模型处理</span><select value={draft.model_processing_scope} onChange={(event) => setDraft({ ...draft, model_processing_scope: event.target.value as typeof draft.model_processing_scope })}>{MODEL_PROCESSING_SCOPES.map((value) => <option key={value} value={value}>{archiveLabel(value)}</option>)}</select></label>
          <label><span>批次</span><select value={draft.batch_id ?? ''} onChange={(event) => setDraft({ ...draft, batch_id: event.target.value || null })}><option value="">未归批次</option>{archive.batches.map((item) => <option key={item.batch_id} value={item.batch_id}>{item.name}</option>)}</select></label>
          <label className="professional-archive__wide"><span>标签 <small>用逗号分隔</small></span><input value={draft.tags.join('，')} onChange={(event) => setDraft({ ...draft, tags: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })} placeholder="迁移，照护" /></label>
        </div>
        {archive.collections.length ? <fieldset><legend>材料集合</legend>{archive.collections.map((item) => <label key={item.collection_id}><input type="checkbox" checked={(draft.collection_ids ?? []).includes(item.collection_id)} onChange={(event) => setDraft({ ...draft, collection_ids: event.target.checked ? [...(draft.collection_ids ?? []), item.collection_id] : (draft.collection_ids ?? []).filter((id) => id !== item.collection_id) })} />{item.name}</label>)}</fieldset> : null}
        <footer><button type="submit" disabled={busy === 'profile'}>{busy === 'profile' ? '正在保存' : '保存材料档案'}</button></footer>
      </form>

      <div className="professional-archive__operations">
        <section>
          <header><FileArrowUpIcon size={17} /><div><strong>批次与多文件</strong><small>每份文件独立返回结果</small></div></header>
          <form onSubmit={addBatch}><input aria-label="新批次名称" value={batchName} onChange={(event) => setBatchName(event.target.value)} placeholder="如：2026 春季田野" /><button disabled={!batchName.trim() || busy === 'batch'}>建立批次</button></form>
          <div className="professional-archive__inline-controls"><select aria-label="选择批次" value={selectedBatchId} onChange={(event) => setSelectedBatchId(event.target.value)}><option value="">选择批次</option>{archive.batches.map((item) => <option key={item.batch_id} value={item.batch_id}>{item.name}</option>)}</select><select aria-label="批量材料类型" value={batchKind} onChange={(event) => setBatchKind(event.target.value as MaterialKind)}><option value="paper">论文</option><option value="interview_transcript">访谈转录</option><option value="observation_record">观察记录</option><option value="field_note">田野笔记</option><option value="other">其他</option></select><button type="button" disabled={!selectedBatchId || busy === 'upload'} onClick={() => batchFileRef.current?.click()}>{busy === 'upload' ? '正在上传' : '选择多份文件'}</button><input ref={batchFileRef} hidden multiple type="file" onChange={(event) => { void uploadBatchFiles(event.target.files) }} /></div>
          {uploadResults.length ? <ul className="professional-archive__results">{uploadResults.map((item, index) => <li key={`${item.filename}:${index}`} data-status={item.status}><span>{item.filename}</span><small>{item.status === 'created' ? '已加入' : item.message || '未加入'}</small></li>)}</ul> : null}
        </section>

        <section>
          <header><FolderPlusIcon size={17} /><div><strong>集合与个案</strong><small>组织关系，不复制原材料</small></div></header>
          <form onSubmit={addCollection}><input aria-label="集合名称" value={collectionName} onChange={(event) => setCollectionName(event.target.value)} placeholder="集合名称" /><input aria-label="集合说明" value={collectionDescription} onChange={(event) => setCollectionDescription(event.target.value)} placeholder="说明（可选）" /><button disabled={!collectionName.trim() || busy === 'collection'}>新建集合</button></form>
          <form onSubmit={addCase}><input aria-label="个案名称" value={caseName} onChange={(event) => setCaseName(event.target.value)} placeholder="个案名称" /><input aria-label="个案属性" value={caseAttributes} onChange={(event) => setCaseAttributes(event.target.value)} placeholder="属性，如：地区=杭州；阶段=两年内" /><button disabled={!caseName.trim() || busy === 'case'}>关联当前材料</button></form>
          <div className="professional-archive__index"><span>{archive.collections.length} 个集合</span><span>{archive.cases.length} 个个案</span></div>
        </section>

        <section>
          <header><LinkSimpleIcon size={17} /><div><strong>材料关系</strong><small>只记录可解释的连接</small></div></header>
          <form onSubmit={addRelation}><select aria-label="关联材料" value={relationTarget} onChange={(event) => setRelationTarget(event.target.value)}><option value="">选择另一份材料</option>{otherMaterials.map((item) => <option key={item.materialId} value={item.materialId}>{item.filename}</option>)}</select><select aria-label="关系类型" value={relationType} onChange={(event) => setRelationType(event.target.value as MaterialRelationType)}>{MATERIAL_RELATION_TYPES.map((value) => <option key={value} value={value}>{RELATION_LABELS[value]}</option>)}</select><input aria-label="关系说明" value={relationNote} onChange={(event) => setRelationNote(event.target.value)} placeholder="说明（可选）" /><button disabled={!relationTarget || busy === 'relation'}>记录关系</button></form>
          <div className="professional-archive__index"><span>{archive.relations.length} 条关系</span></div>
        </section>

        <section>
          <header><BookOpenTextIcon size={17} /><div><strong>文献交换</strong><small>保留条目与疑似重复项</small></div></header>
          <form onSubmit={addByDoi}><input aria-label="DOI" value={doi} onChange={(event) => setDoi(event.target.value)} placeholder="输入 DOI 核对并加入" /><button disabled={!doi.trim() || busy === 'doi'}>核对 DOI</button></form>
          <div className="professional-archive__inline-controls"><select aria-label="文献交换格式" value={literatureFormat} onChange={(event) => setLiteratureFormat(event.target.value as LiteratureFormat)}><option value="bibtex">BibTeX</option><option value="ris">RIS</option><option value="csl_json">CSL-JSON</option></select><button type="button" onClick={() => literatureFileRef.current?.click()} disabled={busy === 'literature-import'}>导入条目</button><input ref={literatureFileRef} hidden type="file" onChange={(event) => { void importLiterature(event.target.files?.[0] ?? null) }} /><button type="button" onClick={() => { void exportLiterature(literatureFormat) }}><ArrowDownIcon size={14} />导出</button></div>
          <div className="professional-archive__index"><span>{archive.literature.length} 条文献</span><span>{archive.duplicate_hints.length} 组待核对</span></div>
          {archive.duplicate_hints.length ? <ul className="professional-archive__duplicates">{archive.duplicate_hints.map((item) => <li key={`${item.literature_id}:${item.candidate_id}`}>疑似重复：{item.reasons.join('、')}</li>)}</ul> : null}
        </section>
      </div>
    </div>
  )
}
