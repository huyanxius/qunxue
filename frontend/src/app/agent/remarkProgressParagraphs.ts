import type { Root, RootContent } from 'mdast'

// 只拆顶层纯文字段落，链接、代码、列表等 Markdown 结构保持完整。
export function remarkProgressParagraphs() {
  const segmenter = new Intl.Segmenter('zh', { granularity: 'sentence' })
  return (tree: Root) => {
    tree.children = tree.children.flatMap((node): RootContent[] => {
      if (node.type !== 'paragraph' || node.children.some((child) => child.type !== 'text')) return [node]
      const value = node.children.map((child) => child.type === 'text' ? child.value : '').join('')
      return Array.from(segmenter.segment(value), ({ segment }) => ({
        type: 'paragraph',
        children: [{ type: 'text', value: segment.trim() }],
      }))
    })
  }
}
