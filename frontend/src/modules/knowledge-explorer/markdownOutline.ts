export interface MarkdownHeading {
  depth: number
  id: string
  title: string
}

export interface MarkdownOutline {
  headings: readonly MarkdownHeading[]
}

function plainText(value: string) {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_`~]/g, '')
    .replace(/<[^>]+>/g, '')
    .trim()
}

export function headingId(title: string) {
  return plainText(title)
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, '')
    .trim()
    .replace(/[\s_-]+/g, '-') || 'section'
}

export function buildMarkdownOutline(content: string): MarkdownOutline {
  const counts = new Map<string, number>()
  const headings: MarkdownHeading[] = []

  for (const line of content.split('\n')) {
    const match = /^(#{1,6})\s+(.+?)\s*$/.exec(line)
    if (!match) continue
    const title = plainText(match[2])
    const baseId = headingId(title)
    const occurrence = (counts.get(baseId) ?? 0) + 1
    counts.set(baseId, occurrence)
    headings.push({
      depth: match[1].length,
      id: occurrence === 1 ? baseId : `${baseId}-${occurrence}`,
      title,
    })
  }

  return { headings }
}
