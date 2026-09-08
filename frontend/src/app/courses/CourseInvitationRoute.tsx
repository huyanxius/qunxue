import { useEffect, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router'

export const COURSE_INVITATION_KEY = 'qunxue.pending-course-invitation'

export function CourseInvitationRoute({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    if (!location.hash) return
    const token = new URLSearchParams(location.hash.slice(1)).get('token')
    if (token) sessionStorage.setItem(COURSE_INVITATION_KEY, token)
    navigate('/courses/join', { replace: true })
  }, [location.hash, navigate])
  // Clear the fragment before authentication can encode it into a login query string.
  return location.hash ? <p role="status">正在打开课程邀请…</p> : children
}
