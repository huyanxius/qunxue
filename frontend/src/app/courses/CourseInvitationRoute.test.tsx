import { render, screen } from '@testing-library/react'
import { MemoryRouter, Navigate, Route, Routes, useLocation } from 'react-router'
import { expect, it } from 'vitest'
import { COURSE_INVITATION_KEY, CourseInvitationRoute } from './CourseInvitationRoute'

function RequireLogin() {
  const location = useLocation()
  return <Navigate replace to={`/login?redirect=${encodeURIComponent(location.pathname + location.hash)}`} />
}
function Destination() {
  const location = useLocation()
  return <p>{location.pathname + location.search + location.hash}</p>
}
it('retains an invitation across login without copying its token into the login URL', async () => {
  render(<MemoryRouter initialEntries={['/courses/join#token=private-invitation']}><Routes>
    <Route path="/courses/join" element={<CourseInvitationRoute><RequireLogin /></CourseInvitationRoute>} />
    <Route path="/login" element={<Destination />} />
  </Routes></MemoryRouter>)
  expect(await screen.findByText('/login?redirect=%2Fcourses%2Fjoin')).toBeInTheDocument()
  expect(sessionStorage.getItem(COURSE_INVITATION_KEY)).toBe('private-invitation')
  sessionStorage.clear()
})
