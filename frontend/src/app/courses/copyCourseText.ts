/** Clipboard permission prompts may remain pending; the page must stay usable. */
export async function copyCourseText(value: string): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    await Promise.race([
      navigator.clipboard.writeText(value),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('clipboard unavailable')), 3000) }),
    ])
  } finally { if (timer) clearTimeout(timer) }
}
