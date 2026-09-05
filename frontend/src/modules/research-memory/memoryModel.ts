/** Memory belongs to either the user or one project. Origin controls learning precedence. */
export interface ResearchMemory {
  memory_id: string
  task_id: string | null
  key: string
  content: string
  origin: 'manual' | 'explicit' | 'learned'
  version: number
  created_at: string
  updated_at: string
  source_conversation_id: string | null
  source_message_id: string | null
  source_quote: string | null
}
export interface ResearchMemorySettings {
  task_id: string | null
  version: number
  use_memory: boolean
  learn_memory: boolean
}
export interface ResearchMemoryLimits {
  max_entries: number
  max_content_bytes: number
}

export const memoryPreviewLimits: ResearchMemoryLimits = { max_entries: 100, max_content_bytes: 2000 }
