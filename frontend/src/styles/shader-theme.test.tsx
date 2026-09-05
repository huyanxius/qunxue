import { createElement } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResearchMapIdleShader } from '../app/research-workspace/ResearchMapIdleShader'
import { ResearchMaterialsShader } from '../app/research/ResearchMaterialsShader'
import { ResearchToolsShader } from '../app/research-tools/ResearchToolsShader'
import { ResearchAgentShader } from '../app/agent/ResearchAgentShader'
import { FoundationLightPaperShader } from '../app/foundation/FoundationLightPaperShader'
import { FoundationAgentShader } from '../app/foundation/FoundationAgentShader'

// Assert the colors passed across the WebGL boundary; real canvas rendering is checked in Chrome.
vi.mock('@paper-design/shaders-react', () => {
  const Shader = ({ colors, colorBack, colorFront, colorMid, uniforms }: Record<string, unknown>) => createElement('div', {
    'data-testid': 'shader',
    'data-palette': JSON.stringify({ colors, colorBack, colorFront, colorMid, uniforms }),
  })
  return { warpPresets: [{ name: 'Nectar', params: {} }], GrainGradient: Shader, MeshGradient: Shader, NeuroNoise: Shader, Warp: Shader, PaperTexture: Shader, ShaderMount: Shader }
})

let dark = false
const subscribers = new Set<() => void>()
beforeEach(() => {
  dark = false
  subscribers.clear()
  vi.stubGlobal('WebGL2RenderingContext', class {})
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() { return query === '(prefers-color-scheme: dark)' && dark },
    addEventListener: (_: string, fn: () => void) => subscribers.add(fn),
    removeEventListener: (_: string, fn: () => void) => subscribers.delete(fn),
  }))
})
afterEach(() => { cleanup(); document.documentElement.style.removeProperty('color-scheme'); vi.unstubAllGlobals() })

const shaders = { ResearchMapIdleShader, ResearchMaterialsShader, ResearchToolsShader, ResearchAgentShader, FoundationLightPaperShader, FoundationAgentShader }
describe.each(Object.entries(shaders))('%s', (_, Component) => {
  it('updates every shader palette in place when system appearance changes and restores the light palette', () => {
    const screen = render(createElement('section', { id: 'knowledge-preview' }, createElement(Component)))
    const elements = screen.getAllByTestId('shader')
    const light = elements.map(el => el.getAttribute('data-palette'))
    act(() => { dark = true; subscribers.forEach(fn => fn()) })
    elements.forEach((el, i) => {
      expect(screen.getAllByTestId('shader')[i]).toBe(el)
      expect(el.getAttribute('data-palette')).not.toBe(light[i])
    })
    act(() => { dark = false; subscribers.forEach(fn => fn()) })
    expect(elements.map(el => el.getAttribute('data-palette'))).toEqual(light)
  })
})

it('keeps the shader consistent with an explicitly selected preview appearance', async () => {
  const screen = render(createElement(ResearchMapIdleShader))
  const el = screen.getByTestId('shader')
  const light = el.getAttribute('data-palette')
  document.documentElement.style.colorScheme = 'dark'
  await waitFor(() => expect(el.getAttribute('data-palette')).not.toBe(light))
  document.documentElement.style.colorScheme = 'light'
  await waitFor(() => expect(el.getAttribute('data-palette')).toBe(light))
})
