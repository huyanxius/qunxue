import { getSchema } from '@tiptap/core'
import { Markdown, MarkdownManager } from '@tiptap/markdown'
import { Slice } from '@tiptap/pm/model'
import { ReplaceStep } from '@tiptap/pm/transform'
import StarterKit from '@tiptap/starter-kit'
import { ChangeSet, simplifyChanges } from 'prosemirror-changeset'

export type DocumentDiffPart = {
  kind: 'unchanged' | 'deleted' | 'inserted'
  text: string
}

const extensions = [StarterKit, Markdown]
const schema = getSchema(extensions)
const markdown = new MarkdownManager({ extensions })

function textBetween(document: ReturnType<typeof schema.nodeFromJSON>, from: number, to: number) {
  return from < to ? document.textBetween(from, to, '\n') : ''
}

function append(parts: DocumentDiffPart[], kind: DocumentDiffPart['kind'], text: string) {
  if (!text) return
  const previous = parts.at(-1)
  if (previous?.kind === kind) previous.text += text
  else parts.push({ kind, text })
}

export function createDocumentDiff(baseMarkdown: string, proposedMarkdown: string): DocumentDiffPart[] {
  const base = schema.nodeFromJSON(markdown.parse(baseMarkdown))
  const proposed = schema.nodeFromJSON(markdown.parse(proposedMarkdown))
  if (base.eq(proposed)) return [{ kind: 'unchanged', text: proposed.textBetween(0, proposed.content.size, '\n') }]

  const step = new ReplaceStep(
    0,
    base.content.size,
    new Slice(proposed.content, 0, 0),
  )
  const applied = step.apply(base)
  if (applied.failed || !applied.doc) throw new Error(applied.failed ?? '文稿差异无法计算。')
  const rawChanges = ChangeSet.create(base).addSteps(applied.doc, [step.getMap()], null).changes
  const changes = rawChanges.some((change) => /[A-Za-z]/.test(
    textBetween(base, change.fromA, change.toA) + textBetween(proposed, change.fromB, change.toB),
  )) ? simplifyChanges(rawChanges, proposed) : rawChanges
  const parts: DocumentDiffPart[] = []
  let baseCursor = 0
  let proposedCursor = 0

  for (const change of changes) {
    append(parts, 'unchanged', textBetween(proposed, proposedCursor, change.fromB))
    append(parts, 'deleted', textBetween(base, change.fromA, change.toA))
    append(parts, 'inserted', textBetween(proposed, change.fromB, change.toB))
    baseCursor = change.toA
    proposedCursor = change.toB
  }
  append(parts, 'unchanged', textBetween(proposed, proposedCursor, proposed.content.size))
  void baseCursor
  return parts
}
