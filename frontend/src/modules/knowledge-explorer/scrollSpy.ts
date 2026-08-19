export interface ScrollSpyHeading {
  id: string
  top: number
}

export function activeHeadingAtOffset(
  headings: readonly ScrollSpyHeading[],
  offset: number,
) {
  let activeId = headings[0]?.id
  for (const heading of headings) {
    if (heading.top > offset) break
    activeId = heading.id
  }
  return activeId
}
