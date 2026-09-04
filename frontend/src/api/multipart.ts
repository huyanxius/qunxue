export type MultipartPart =
  | { name: string; value: string }
  | { name: string; file: File }

export type MultipartBody = {
  body: Uint8Array<ArrayBuffer>
  contentType: string
}

const encoder = new TextEncoder()

function headerValue(value: string): string {
  return value.replace(/[\r\n]/g, ' ').replace(/["\\]/g, (match) => `\\${match}`)
}

async function readFile(file: File): Promise<Uint8Array<ArrayBuffer>> {
  if (typeof file.arrayBuffer === 'function') {
    return new Uint8Array(await file.arrayBuffer())
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error ?? new Error('无法读取上传文件。'))
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.readAsArrayBuffer(file)
  })
}

/**
 * Serialize multipart bytes without passing File objects between DOM realms.
 * Embedded browsers and jsdom can expose mutually incompatible File/FormData
 * constructors even though both implement the web platform contract.
 */
export async function createMultipartBody(parts: MultipartPart[]): Promise<MultipartBody> {
  const token = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
  const boundary = `----qunxue-${token}`
  const chunks: Uint8Array<ArrayBuffer>[] = []

  for (const part of parts) {
    const name = headerValue(part.name)
    if ('file' in part) {
      chunks.push(encoder.encode(
        `--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${headerValue(part.file.name)}"\r\nContent-Type: ${part.file.type || 'application/octet-stream'}\r\n\r\n`,
      ))
      chunks.push(await readFile(part.file))
      chunks.push(encoder.encode('\r\n'))
    } else {
      chunks.push(encoder.encode(
        `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${part.value}\r\n`,
      ))
    }
  }
  chunks.push(encoder.encode(`--${boundary}--\r\n`))

  const body = new Uint8Array(chunks.reduce((total, chunk) => total + chunk.byteLength, 0))
  let offset = 0
  for (const chunk of chunks) {
    body.set(chunk, offset)
    offset += chunk.byteLength
  }
  return { body, contentType: `multipart/form-data; boundary=${boundary}` }
}
