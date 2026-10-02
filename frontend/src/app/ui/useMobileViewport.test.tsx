import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { useMobileViewport } from './useMobileViewport'

const previousViewport = Object.getOwnPropertyDescriptor(window, 'visualViewport')
afterEach(() => {
  cleanup()
  if (previousViewport) Object.defineProperty(window, 'visualViewport', previousViewport)
  else Reflect.deleteProperty(window, 'visualViewport')
})

it('tracks keyboard height and restores viewport variables when leaving mobile', async () => {
  const viewport = Object.assign(new EventTarget(), { height: 844, offsetTop: 0, scale: 1 })
  Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport })
  const style = document.documentElement.style
  const { rerender } = renderHook(({ active }) => useMobileViewport(active), { initialProps: { active: true } })
  expect(style.getPropertyValue('--qunxue-mobile-height')).toBe('844px')
  act(() => { viewport.height = 380; viewport.offsetTop = 12; viewport.dispatchEvent(new Event('resize')) })
  await waitFor(() => expect(style.getPropertyValue('--qunxue-mobile-height')).toBe('380px'))
  expect(style.getPropertyValue('--qunxue-mobile-offset-top')).toBe('12px')
  rerender({ active: false })
  expect(style.getPropertyValue('--qunxue-mobile-height')).toBe('')
  expect(style.getPropertyValue('--qunxue-mobile-offset-top')).toBe('')
})

it('does not reinterpret pinch zoom as a smaller phone layout', async () => {
  const viewport = Object.assign(new EventTarget(), { height: 844, offsetTop: 0, scale: 1 })
  Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport })
  const style = document.documentElement.style
  const { unmount } = renderHook(() => useMobileViewport(true))
  act(() => { viewport.scale = 2; viewport.height = 320; viewport.dispatchEvent(new Event('resize')) })
  await new Promise(resolve => window.requestAnimationFrame(resolve))
  expect(style.getPropertyValue('--qunxue-mobile-height')).toBe('844px')
  act(() => { viewport.scale = 1; viewport.dispatchEvent(new Event('scroll')) })
  unmount()
  await new Promise(resolve => window.requestAnimationFrame(resolve))
  expect(style.getPropertyValue('--qunxue-mobile-height')).toBe('')
})
