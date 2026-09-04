export type ResearchBatchCodingRun = {
  runId: string
  taskId: string
  materialId: string
  parseId: string
  parseVersion: number
  status: 'queued' | 'processing' | 'completed' | 'failed'
  totalSegments: number
  processedSegments: number
  annotationIds: string[]
  codeIds: string[]
  lowConfidenceSegments: string[]
  errorCode: string | null
  retryCount: number
}
