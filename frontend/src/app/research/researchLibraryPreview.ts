import type { ResearchMaterial } from '../../modules/research-materials'

/** Development-only file metadata for checking the library layout. */
export function researchLibraryPreview(taskId: string): ResearchMaterial[] {
  return [
    { filename: '访谈 01 — 研究参与者 A.docx', mediaType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', sizeBytes: 48640, materialKind: 'interview_transcript', status: 'ready' },
    { filename: '访谈 02 — 研究参与者 B.docx', mediaType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', sizeBytes: 62464, materialKind: 'interview_transcript', status: 'ready' },
    { filename: '田野观察记录 — 第一周.md', mediaType: 'text/markdown', sizeBytes: 12320, materialKind: 'field_note', status: 'ready' },
    { filename: '相关研究文献与阅读笔记.pdf', mediaType: 'application/pdf', sizeBytes: 1843200, materialKind: 'paper', status: 'ready' },
    { filename: '访谈录音 — 参与者 A.m4a', mediaType: 'audio/mp4', sizeBytes: 25480320, materialKind: 'other', status: 'ready' },
    { filename: '现场观察 — 小组讨论.mp4', mediaType: 'video/mp4', sizeBytes: 98566144, materialKind: 'observation_record', status: 'processing' },
  ].map((file, index) => ({
    ...file,
    materialId: `preview-file-${index + 1}`,
    taskId,
    version: 1,
    parseVersion: file.status === 'ready' ? 1 : null,
    segmentCount: file.status === 'ready' ? 24 + index * 8 : 0,
    updatedAt: `2026-09-0${5 - Math.floor(index / 2)}T0${9 - index}:30:00Z`,
    errorCode: null,
  })) as ResearchMaterial[]
}
