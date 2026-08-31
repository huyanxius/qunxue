import { apiClient } from '../../api/client'
import {
  configureResearchCodebookEntry,
  confirmResearchAnalysisTheme,
  createResearchAnalysisMemoLink,
  createResearchAnalysisAnnotation,
  createResearchAnalysisCode,
  createResearchAnalysisMemo,
  createResearchAnalysisTheme,
  createResearchCaseComparison,
  decideResearchAnalysisCode,
  decideResearchAnalysisMemo,
  decideResearchCaseComparison,
  getResearchAnalysis,
  saveResearchAnalysisCaseProfile,
  saveResearchCaseThemeMatrixCell,
  setResearchQualitativeMethod,
  transitionResearchCodebookEntry,
} from '../../api/generated'
import type {
  AnalysisCaseProfile,
  AnalysisAnnotation,
  AnalysisCode,
  AnalysisMemo,
  AnalysisMemoLink,
  AnalysisTheme,
  CaseComparison,
  CaseThemeMatrixCell,
  CodebookEntry,
  ConfigureCodebookEntryInput,
  CreateAnalysisAnnotationInput,
  CreateAnalysisCodeInput,
  CreateAnalysisMemoLinkInput,
  CreateAnalysisMemoInput,
  CreateAnalysisThemeInput,
  CreateCaseComparisonInput,
  DecideAnalysisRecordInput,
  MethodPresetSelection,
  ResearchAnalysisSnapshot,
  SaveAnalysisCaseProfileInput,
  SaveCaseThemeMatrixCellInput,
  SetQualitativeMethodInput,
  TransitionCodebookEntryInput,
} from './researchAnalysisModel'

export class ResearchAnalysisApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ResearchAnalysisApiError'
    this.status = status
  }
}

type GeneratedResult<T> = {
  readonly data?: T
  readonly error?: unknown
  readonly response?: Response
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function errorMessage(error: unknown, fallback: string): string {
  const raw = record(error)
  const nested = record(raw.error)
  if (typeof nested.message === 'string' && nested.message.trim()) return nested.message
  if (typeof raw.message === 'string' && raw.message.trim()) return raw.message
  return fallback
}

function requireData<T>(result: GeneratedResult<T>, fallback: string): T {
  if (result.error !== undefined && result.error !== null) {
    if (record(result.error).name === 'AbortError') throw result.error
    throw new ResearchAnalysisApiError(
      errorMessage(result.error, fallback),
      result.response?.status ?? 0,
    )
  }
  if (result.data === undefined || result.data === null) {
    throw new ResearchAnalysisApiError(fallback, result.response?.status ?? 0)
  }
  return result.data
}

function idempotencyKey(): string {
  const token = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}:${Math.random().toString(36).slice(2)}`
  return `research-analysis:${token}`
}

export async function getAnalysisSnapshot(
  taskId: string,
  signal?: AbortSignal,
): Promise<ResearchAnalysisSnapshot> {
  const result = await getResearchAnalysis({
    client: apiClient,
    path: { task_id: taskId },
    signal,
  })
  return requireData(result, '质性分析记录暂时无法加载。')
}

export async function createAnalysisAnnotation(
  taskId: string,
  body: CreateAnalysisAnnotationInput,
  signal?: AbortSignal,
): Promise<AnalysisAnnotation> {
  const result = await createResearchAnalysisAnnotation({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '片段标记未保存。')
}

export async function createAnalysisCode(
  taskId: string,
  body: CreateAnalysisCodeInput,
  signal?: AbortSignal,
): Promise<AnalysisCode> {
  const result = await createResearchAnalysisCode({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '编码未保存。')
}

export async function decideAnalysisCode(
  taskId: string,
  codeId: string,
  body: DecideAnalysisRecordInput,
  signal?: AbortSignal,
): Promise<AnalysisCode> {
  const result = await decideResearchAnalysisCode({
    client: apiClient,
    path: { task_id: taskId, code_id: codeId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '候选编码判断未保存。')
}

export async function createAnalysisMemo(
  taskId: string,
  body: CreateAnalysisMemoInput,
  signal?: AbortSignal,
): Promise<AnalysisMemo> {
  const result = await createResearchAnalysisMemo({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '分析备忘未保存。')
}

export async function decideAnalysisMemo(
  taskId: string,
  memoId: string,
  body: DecideAnalysisRecordInput,
  signal?: AbortSignal,
): Promise<AnalysisMemo> {
  const result = await decideResearchAnalysisMemo({
    client: apiClient,
    path: { task_id: taskId, memo_id: memoId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '备忘草稿判断未保存。')
}

export async function createCaseComparison(
  taskId: string,
  body: CreateCaseComparisonInput,
  signal?: AbortSignal,
): Promise<CaseComparison> {
  const result = await createResearchCaseComparison({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '案例比较未保存。')
}

export async function decideCaseComparison(
  taskId: string,
  comparisonId: string,
  body: DecideAnalysisRecordInput,
  signal?: AbortSignal,
): Promise<CaseComparison> {
  const result = await decideResearchCaseComparison({
    client: apiClient,
    path: { task_id: taskId, comparison_id: comparisonId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '案例比较判断未保存。')
}

export async function configureCodebookEntry(
  taskId: string,
  codeId: string,
  body: ConfigureCodebookEntryInput,
  signal?: AbortSignal,
): Promise<CodebookEntry> {
  const result = await configureResearchCodebookEntry({
    client: apiClient,
    path: { task_id: taskId, code_id: codeId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '代码本边界未保存。')
}

export async function transitionCodebookEntry(
  taskId: string,
  codeId: string,
  body: TransitionCodebookEntryInput,
  signal?: AbortSignal,
): Promise<CodebookEntry> {
  const result = await transitionResearchCodebookEntry({
    client: apiClient,
    path: { task_id: taskId, code_id: codeId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '代码本状态未保存。')
}

export async function createAnalysisTheme(
  taskId: string,
  body: CreateAnalysisThemeInput,
  signal?: AbortSignal,
): Promise<AnalysisTheme> {
  const result = await createResearchAnalysisTheme({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '分析主题未保存。')
}

export async function confirmAnalysisTheme(
  taskId: string,
  themeId: string,
  reason: string,
  expectedVersion: number,
  signal?: AbortSignal,
): Promise<AnalysisTheme> {
  const result = await confirmResearchAnalysisTheme({
    client: apiClient,
    path: { task_id: taskId, theme_id: themeId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { decision: 'confirmed', reason, expected_version: expectedVersion },
    signal,
  })
  return requireData(result, '主题确认未保存。')
}

export async function attachAnalysisMemo(
  taskId: string,
  body: CreateAnalysisMemoLinkInput,
  signal?: AbortSignal,
): Promise<AnalysisMemoLink> {
  const result = await createResearchAnalysisMemoLink({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '备忘挂接未保存。')
}

export async function saveAnalysisCaseProfile(
  taskId: string,
  body: SaveAnalysisCaseProfileInput,
  signal?: AbortSignal,
): Promise<AnalysisCaseProfile> {
  const result = await saveResearchAnalysisCaseProfile({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '个案档案未保存。')
}

export async function saveCaseThemeMatrixCell(
  taskId: string,
  body: SaveCaseThemeMatrixCellInput,
  signal?: AbortSignal,
): Promise<CaseThemeMatrixCell> {
  const result = await saveResearchCaseThemeMatrixCell({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '比较矩阵单元未保存。')
}

export async function setQualitativeMethod(
  taskId: string,
  body: SetQualitativeMethodInput,
  signal?: AbortSignal,
): Promise<MethodPresetSelection> {
  const result = await setResearchQualitativeMethod({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body,
    signal,
  })
  return requireData(result, '方法取向未保存。')
}
