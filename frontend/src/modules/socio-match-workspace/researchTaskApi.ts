import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  confirmPhenomenonCandidate,
  createResearchTask as createResearchTaskRequest,
  extractPhenomenonCandidates,
  getMaterialIntakeRun,
  getPhenomenonCandidate,
  getResearchTask as getResearchTaskRequest,
  getResearchTaskNavigation,
  listPhenomenonExamples,
  listPhenomenonSnapshots,
  submitDirectInput,
  submitMaterialIntake,
  updatePhenomenonCandidate,
  type PhenomenonCandidateResponse,
  type PhenomenonSnapshotResponse,
  type ResearchTaskResponse,
} from '../../api/generated'
import type {
  MaterialStartInput,
  PhenomenonCandidate,
  PhenomenonExample,
  PhenomenonSnapshot,
  ResearchTask,
  ResearchTaskAction,
  ResearchTaskEntryType,
  RestoredPhenomenon,
  SeedTheoryClue,
  StartedPhenomenon,
} from './researchTaskModel'

const entryTypes = {
  direct_input: 'direct_input',
  material_input: 'material_input',
} satisfies Record<ResearchTaskResponse['entry_type'], ResearchTaskEntryType>

const taskActions = {
  submit_phenomenon: 'submit_phenomenon',
} satisfies Record<ResearchTaskResponse['allowed_actions'][number], ResearchTaskAction>

function seedTheory(id: string | null, name: string | null): SeedTheoryClue | null {
  return id && name ? { theoryId: id, name } : null
}

function toResearchTask(response: ResearchTaskResponse): ResearchTask {
  return {
    taskId: response.task_id,
    entryType: entryTypes[response.entry_type],
    status: response.status,
    version: response.version,
    allowedActions: response.allowed_actions.map((action) => taskActions[action]),
    seedTheory: seedTheory(response.seed_theory_id, response.seed_theory_name),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function idempotencyKey() {
  return globalThis.crypto.randomUUID()
}

function toCandidate(response: PhenomenonCandidateResponse): PhenomenonCandidate {
  return {
    candidateId: response.candidate_id,
    taskId: response.task_id,
    version: response.version,
    status: response.status,
    contentOrigin: response.content_origin,
    phenomenon: response.phenomenon,
    researchIntent: response.research_intent,
    context: response.context,
    missingInformation: response.missing_information,
    sourceTraceability: response.source_traceability,
    evidence: response.evidence_refs.map((item) => ({
      evidenceRefId: item.evidence_ref_id,
      excerpt: item.excerpt,
      locator: item.locator,
      sourceDescription: item.source_description,
      useBoundary: item.use_boundary,
    })),
    modelLabel: `演示 AI · ${response.model.provider}`,
  }
}

function toSnapshot(response: PhenomenonSnapshotResponse): PhenomenonSnapshot {
  return {
    phenomenonQueryId: response.phenomenon_query_id,
    phenomenon: response.phenomenon,
    researchIntent: response.research_intent,
    context: response.context,
    contentHash: response.content_hash,
    confirmedAt: response.confirmed_at,
  }
}

export async function createResearchTaskViaApi(
  requestKey: string,
  options: {
    entryType?: ResearchTaskEntryType
    seedTheory?: SeedTheoryClue | null
  } = {},
): Promise<ResearchTask> {
  const { data, response } = await createResearchTaskRequest({
    client: apiClient,
    body: {
      entry_type: options.entryType ?? 'direct_input',
      seed_theory_id: options.seedTheory?.theoryId ?? null,
      seed_theory_name: options.seedTheory?.name ?? null,
    },
    headers: { 'Idempotency-Key': requestKey },
  })
  if (!data) throw new ApiRequestError('研究任务创建失败。', response?.status)
  return toResearchTask(data)
}

export async function getResearchTaskViaApi(taskId: string): Promise<ResearchTask> {
  const { data, response } = await getResearchTaskRequest({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!data) throw new ApiRequestError('研究任务恢复失败。', response?.status)
  return toResearchTask(data)
}

export async function listPhenomenonExamplesViaApi(): Promise<PhenomenonExample[]> {
  const { data, response } = await listPhenomenonExamples({ client: apiClient })
  if (!data) throw new ApiRequestError('内置案例加载失败。', response?.status)
  return data.items.map((item) => ({
    exampleId: item.example_id,
    title: item.title,
    phenomenon: item.phenomenon,
    researchIntent: item.research_intent,
    context: item.context,
    sourceType: 'built_in_example',
  }))
}

export async function startPhenomenonViaApi(
  input: string | {
    phenomenon: string
    researchIntent: string
    context: string
    seedTheory?: SeedTheoryClue | null
  },
): Promise<StartedPhenomenon> {
  const values = typeof input === 'string'
    ? { phenomenon: input, researchIntent: '', context: '', seedTheory: null }
    : input
  const task = await createResearchTaskViaApi(idempotencyKey(), {
    seedTheory: values.seedTheory,
  })
  const direct = await submitDirectInput({
    client: apiClient,
    path: { task_id: task.taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      phenomenon: values.phenomenon,
      research_intent: values.researchIntent || null,
      context: values.context || null,
    },
  })
  if (!direct.data) throw new ApiRequestError('现象输入保存失败。', direct.response?.status)
  const extracted = await extractPhenomenonCandidates({
    client: apiClient,
    path: { task_id: task.taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { expected_task_version: task.version, requested_count: 1 },
  })
  const candidate = extracted.data?.candidates[0]
  if (!candidate) throw new ApiRequestError('演示候选生成失败。', extracted.response?.status)
  return { taskId: task.taskId, candidate: toCandidate(candidate) }
}

async function fileContent(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

export async function startMaterialViaApi(input: MaterialStartInput): Promise<{ taskId: string }> {
  const task = await createResearchTaskViaApi(idempotencyKey(), {
    entryType: 'material_input',
    seedTheory: input.seedTheory,
  })
  const isDocx = input.file?.name.toLowerCase().endsWith('.docx') ?? false
  const result = await submitMaterialIntake({
    client: apiClient,
    path: { task_id: task.taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      filename: input.file?.name ?? 'pasted-material.txt',
      media_type: isDocx
        ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        : 'text/plain',
      pasted_text: input.file ? null : input.pastedText,
      content_base64: input.file ? await fileContent(input.file) : null,
      research_intent: input.researchIntent || null,
      context: input.context || null,
      deidentification_confirmed: true,
      processing_rights_confirmed: true,
      external_processing_acknowledged: true,
      processing_policy_version: input.processingPolicyVersion,
    },
  })
  if (!result.data) throw new ApiRequestError('材料处理失败。', result.response?.status)
  return { taskId: task.taskId }
}

export async function restorePhenomenonViaApi(taskId: string): Promise<RestoredPhenomenon> {
  const navigation = await getResearchTaskNavigation({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!navigation.data) throw new ApiRequestError('研究进度恢复失败。', navigation.response?.status)

  let candidates: PhenomenonCandidate[]
  if (navigation.data.current_material_intake_run_id) {
    const run = await getMaterialIntakeRun({
      client: apiClient,
      path: { run_id: navigation.data.current_material_intake_run_id },
    })
    if (!run.data) throw new ApiRequestError('材料候选恢复失败。', run.response?.status)
    candidates = run.data.candidates.map(toCandidate)
  } else {
    const candidateId = navigation.data.current_phenomenon_candidate_id
    if (!candidateId) throw new ApiRequestError('这项研究还没有现象候选。')
    const result = await getPhenomenonCandidate({
      client: apiClient,
      path: { task_id: taskId, candidate_id: candidateId },
    })
    if (!result.data) throw new ApiRequestError('现象候选恢复失败。', result.response?.status)
    candidates = [toCandidate(result.data)]
  }
  const snapshots = await listPhenomenonSnapshots({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!snapshots.data) throw new ApiRequestError('现象确认状态恢复失败。', snapshots.response?.status)
  const selectedId = navigation.data.current_phenomenon_candidate_id
  const selected = candidates.find((item) => item.candidateId === selectedId) ?? candidates[0]
  if (!selected) throw new ApiRequestError('这项研究还没有现象候选。')
  return {
    candidates,
    candidate: selected,
    snapshot: snapshots.data.snapshots[0] ? toSnapshot(snapshots.data.snapshots[0]) : null,
    seedTheory: seedTheory(
      navigation.data.seed_theory_id,
      navigation.data.seed_theory_name,
    ),
  }
}

export async function confirmEditedPhenomenonViaApi(
  candidate: PhenomenonCandidate,
  values: { phenomenon: string; researchIntent: string; context: string },
): Promise<PhenomenonSnapshot> {
  const updated = await updatePhenomenonCandidate({
    client: apiClient,
    path: { task_id: candidate.taskId, candidate_id: candidate.candidateId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_version: candidate.version,
      phenomenon: values.phenomenon,
      research_intent: values.researchIntent || null,
      context: values.context || null,
    },
  })
  if (!updated.data) throw new ApiRequestError('候选修改保存失败。', updated.response?.status)
  const confirmed = await confirmPhenomenonCandidate({
    client: apiClient,
    path: { task_id: candidate.taskId, candidate_id: candidate.candidateId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { expected_version: updated.data.version },
  })
  if (!confirmed.data) throw new ApiRequestError('现象确认失败。', confirmed.response?.status)
  return toSnapshot(confirmed.data)
}
