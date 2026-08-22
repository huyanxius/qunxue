import '@testing-library/jest-dom/vitest'
import { createElement } from 'react'
import { vi } from 'vitest'

const ShaderFallback = ({ className }: { className?: string }) => (
  createElement('div', { 'aria-hidden': true, className })
)

// Paper shaders require a real WebGL canvas and decoded image uniforms. Keeping
// that browser-only lifecycle out of jsdom prevents rejected shader promises
// from leaking across otherwise unrelated route tests.
vi.mock('@paper-design/shaders-react', () => ({
  GrainGradient: ShaderFallback,
  NeuroNoise: ShaderFallback,
  PaperTexture: ShaderFallback,
  ShaderMount: ShaderFallback,
}))

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
