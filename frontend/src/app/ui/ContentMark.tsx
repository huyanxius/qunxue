import type { PropsWithChildren } from 'react'

export type ContentKind = 'verified' | 'analysis' | 'external' | 'user'

const contentKindLabels: Record<ContentKind, string> = {
  verified: '知识库内容',
  analysis: '系统分析',
  external: '库外线索',
  user: '用户内容',
}

export function ContentMark({
  kind,
  children,
}: PropsWithChildren<{ kind: ContentKind }>) {
  return (
    <article className={`content-mark content-mark--${kind}`}>
      <span className="content-mark__label">{contentKindLabels[kind]}</span>
      {children ? <p>{children}</p> : null}
    </article>
  )
}
