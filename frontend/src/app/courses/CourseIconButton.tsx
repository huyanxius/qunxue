import type { ComponentProps, ReactNode } from 'react'

export function CourseIconButton({ label, children, className = '', ...props }: Omit<ComponentProps<'button'>, 'children'> & { label: string; children: ReactNode }) {
  return <button type="button" aria-label={label} title={label} className={`course-icon-button ${className}`} {...props}>{children}</button>
}
