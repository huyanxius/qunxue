function boundaryFrom(contentType: string | null): string {
  const match = contentType?.match(/boundary=(?:"([^"]+)"|([^;]+))/i)
  const boundary = match?.[1] ?? match?.[2]
  if (!boundary) throw new Error('multipart boundary is missing')
  return boundary
}

/** Parse test requests without mixing Node Request and jsdom File realms. */
export async function parseMultipartRequest(request: Request): Promise<FormData> {
  const boundary = boundaryFrom(request.headers.get('Content-Type'))
  const bytes = new Uint8Array(await request.clone().arrayBuffer())
  const source = new TextDecoder('latin1').decode(bytes)
  const delimiter = `--${boundary}`
  const form = new FormData()

  let cursor = source.indexOf(delimiter)
  while (cursor >= 0) {
    const partStart = cursor + delimiter.length
    if (source.startsWith('--', partStart)) break
    const contentStart = partStart + 2
    const nextBoundary = source.indexOf(`\r\n${delimiter}`, contentStart)
    if (nextBoundary < 0) break
    const part = source.slice(contentStart, nextBoundary)
    const headerEnd = part.indexOf('\r\n\r\n')
    if (headerEnd < 0) {
      cursor = nextBoundary + 2
      continue
    }
    const headers = new TextDecoder().decode(bytes.slice(contentStart, contentStart + headerEnd))
    const disposition = headers.match(
      /Content-Disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?/i,
    )
    if (!disposition) {
      cursor = nextBoundary + 2
      continue
    }
    const bodyStart = contentStart + headerEnd + 4
    const value = bytes.slice(bodyStart, nextBoundary)
    const name = disposition[1]
    const filename = disposition[2]
    if (filename !== undefined) {
      const mediaType = headers.match(/Content-Type:\s*([^\r\n]+)/i)?.[1] ?? ''
      form.append(name, new File([value], filename, { type: mediaType }))
    } else {
      form.append(name, new TextDecoder().decode(value))
    }
    cursor = nextBoundary + 2
  }
  return form
}
