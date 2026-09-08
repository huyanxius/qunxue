export interface CourseKnowledge {
  summary: string
  topics: Array<{ title: string; summary: string; segmentIds: string[] }>
  relations: Array<{ source: string; target: string; label: string; segmentIds: string[] }>
}

export interface SharedDocument {
  id: string
  filename: string
  mediaType: string
  sizeBytes: number
  parseId: string
  status: 'processing' | 'ready' | 'failed'
  knowledgeStatus: 'queued' | 'running' | 'ready' | 'failed'
  indexStatus: 'queued' | 'running' | 'ready' | 'failed'
  knowledge: CourseKnowledge | null
  knowledgeError: string | null
  indexError: string | null
  errorMessage: string | null
  warnings: string[]
  createdAt: string
}

export interface SharedCourse {
  id: string
  name: string | null
  description: string | null
  access: 'owner' | 'reader' | 'unavailable'
  sharingEnabled: boolean
  shareToken: string | null
  readyDocumentCount: number
  documents: SharedDocument[]
}

export interface SharedSource {
  document: SharedDocument
  knowledgeBaseId: string
  knowledgeBaseName: string
  segments: Array<{
    id: string
    parseId: string
    ordinal: number
    kind: string
    text: string
    location: {
      page: number | null
      headingPath: string[]
      paragraph: number | null
      lineStart: number | null
      lineEnd: number | null
      charStart: number | null
      charEnd: number | null
      blockIndex: number | null
    }
  }>
}

export const COURSE_DOCUMENT_ACCEPT = '.pdf,.docx,.pptx,.txt,.md,.markdown'
