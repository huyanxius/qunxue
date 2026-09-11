import { createDocxExport } from '../../research-document'

export async function downloadTeachingDocument(title: string, markdown: string) {
  const blob = await createDocxExport({ title, templateId: 'chinese-social-science',
    sections: [{ title: '正文', markdown }], citationAudit: [], bibliographyText: '' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${title.replace(/[\\/:*?"<>|]/g, '-')}.docx`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
