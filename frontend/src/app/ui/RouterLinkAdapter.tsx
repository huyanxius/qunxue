import type { AnchorHTMLAttributes, ComponentType, PropsWithChildren } from 'react'
import { Link } from 'react-router'

export type LinkAdapterProps = PropsWithChildren<Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & {
  href: string
}>

export const RouterLinkAdapter: ComponentType<LinkAdapterProps> = ({
  children,
  href,
  ...props
}) => (
  <Link {...props} to={href}>{children}</Link>
)
