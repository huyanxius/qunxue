import { useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from '@tiptap/markdown'
import { downloadTeachingDocument } from './teachingExport'
import type { TeachingActivity } from '../teachingApi'


export function LessonEditor({ activity, busy, onSave, onRevise, onDirty }: {
  activity: TeachingActivity; busy: boolean; onSave: (markdown: string) => Promise<void>
  onRevise: (markdown: string, instruction: string, selected: string) => Promise<void>
  onDirty: (value: boolean) => void
}) {
  const [dirty, setDirty] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const markdown = activity.result?.markdown ?? ''
  const editor = useEditor({ extensions: [StarterKit, Markdown], content: markdown, contentType: 'markdown',
    immediatelyRender: false,
    editorProps: { attributes: { 'aria-label': '教案正文', class: 'research-document-editor' } },
    onUpdate: () => { setDirty(true); onDirty(true) },
    onSelectionUpdate: ({ editor: value }) => {
      const { from, to } = value.state.selection
      if (from !== to) setSelected(value.state.doc.textBetween(from, to, '\n'))
    },
  })
  useEffect(() => {
    editor?.commands.setContent(markdown, { contentType: 'markdown', emitUpdate: false })
    setDirty(false); onDirty(false); setSelected('')
  }, [activity.id, markdown, editor, onDirty])
  const content = () => editor?.getMarkdown() ?? markdown
  async function action(operation: () => Promise<void>) {
    setError('')
    try { await operation() } catch (reason) { setError(reason instanceof Error ? reason.message : '操作失败，请重试。') }
  }
  const minuteMatches = [...markdown.matchAll(/(\d+)\s*分钟/g)].map((match) => Number(match[1]))
  const total = minuteMatches.reduce((sum, value) => sum + value, 0)
  return <section aria-label="教案编辑器" className="teaching-manuscript">
    <div className="courses-page__actions" role="toolbar" aria-label="文稿格式">
      <button type="button" className="courses-page__text-button" onClick={() => editor?.chain().focus().toggleBold().run()}>加粗</button>
      <button type="button" className="courses-page__text-button" onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}>小标题</button>
      <button type="button" className="courses-page__text-button" onClick={() => editor?.chain().focus().toggleBulletList().run()}>列表</button>
      <button type="button" className="research-hub__new" disabled={busy || !dirty} onClick={() => void action(() => onSave(content()))}>保存文稿</button>
      <button type="button" className="qx-button" disabled={busy || dirty} onClick={() => void action(() => downloadTeachingDocument(activity.input.title || '课堂教案', markdown))}>下载 Word</button>
    </div>
    <p className="courses-page__hint">{dirty ? '有未保存修改，保存后可下载。' : `已保存 · 活动版本 ${activity.version}`} · 拖选正文可指定局部修改。</p>
    {minuteMatches.length > 0 && total !== activity.input.duration_minutes && <p role="status">检测到的分钟数合计 {total}，课时为 {activity.input.duration_minutes} 分钟，请核对环节安排（正文重复提及时也可能计入）。</p>}
    <EditorContent editor={editor} />
    <div className="courses-page__form">
      <label>局部修改要求<textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="例如：为这段讨论增加一个具体案例" /></label>
      {selected && <p>已选中：{selected.slice(0, 160)} <button type="button" className="courses-page__text-button" onClick={() => setSelected('')}>清除选择</button></p>}
      <button type="button" className="qx-button" disabled={busy || !instruction.trim()} onClick={() => void action(() => onRevise(content(), instruction, selected))}>保存并请助手修改</button>
    </div>
    {error && <p role="alert">{error}</p>}
  </section>
}
