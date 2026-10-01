import { useState } from 'react'
import { ArrowUpRightIcon } from '@phosphor-icons/react'
import type { FrontierMedia } from './model'

/** The ingestion service validates source ownership and meaningful article media. */
export function FrontierSourceFigure({ media }: { media: FrontierMedia }) {
  const [failedUrl, setFailedUrl] = useState('')
  if (failedUrl === media.url || !media.url.startsWith('https://') || !media.source_url.startsWith('https://')) return null
  return <figure className="frontier-source-figure">
    <a href={media.source_url} target="_blank" rel="noopener noreferrer">
      <img src={media.url} alt={media.alt || media.caption} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailedUrl(media.url)} />
    </a>
    <figcaption><span>{media.caption}</span><a href={media.source_url} target="_blank" rel="noopener noreferrer">图片来源 <ArrowUpRightIcon size={11} aria-hidden="true" /></a></figcaption>
  </figure>
}
