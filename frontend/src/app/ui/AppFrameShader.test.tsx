import { createElement } from 'react'
import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

// 只断言工作台传过界的值，真实渲染在 Chrome 里看。
const props: Record<string, unknown>[] = []
vi.mock('../../styles/SurfaceShader', () => ({
  SurfaceShader: (given: Record<string, unknown>) => {
    props.push(given)
    return createElement('canvas')
  },
}))

const { AppFrameShader } = await import('./AppFrameShader')

afterEach(() => { cleanup(); props.length = 0 })

it('工作台用自己的浅色取景，蓝退到画面下沿之外', () => {
  render(createElement(AppFrameShader))
  expect(props).toHaveLength(1)
  expect(props[0].lightPalette).toEqual(['#fafcfe', '#edf1f7', '#c2ccdb', '#8c94a4'])
  // 登录注册那处不传这两个参数，沿用组件默认值，不受这里影响
  expect(props[0].lightYshift).toBe(-0.32)
})
