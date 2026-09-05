import { createElement } from 'react'
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { AccountPaperShader } from './AccountPaperShader'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('keeps the background mounted and updates its palette with system appearance', () => {
  let dark = false
  const subscribers = new Set<() => void>()
  vi.stubGlobal('WebGL2RenderingContext', class {})
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() { return query === '(prefers-color-scheme: dark)' && dark },
    addEventListener: (_: string, fn: () => void) => subscribers.add(fn),
    removeEventListener: (_: string, fn: () => void) => subscribers.delete(fn),
  }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  const screen = render(createElement(AccountPaperShader))
  const shader = screen.container.querySelector('canvas')!
  const light = shader.getAttribute('data-color-scheme')
  act(() => { dark = true; subscribers.forEach(fn => fn()) })
  expect(screen.container.querySelector('canvas')!).toBe(shader)
  expect(shader.getAttribute('data-color-scheme')).not.toBe(light)
  act(() => { dark = false; subscribers.forEach(fn => fn()) })
  expect(shader.getAttribute('data-color-scheme')).toBe(light)
})
