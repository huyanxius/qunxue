import { MagnifyingGlassIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

export function ResearchHubToolbar({ query, onQueryChange, searchLabel, placeholder, children }: {
  query: string
  onQueryChange: (query: string) => void
  searchLabel: string
  placeholder: string
  children: ReactNode
}) {
  return <div className="research-hub__toolbar">
    <label className="research-hub__search"><MagnifyingGlassIcon size={17} /><input type="search" aria-label={searchLabel} placeholder={placeholder} value={query} onChange={(event) => onQueryChange(event.target.value)} /></label>
    {children}
  </div>
}
