import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NetworkStatusNotice } from './NetworkStatusNotice'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('NetworkStatusNotice', () => {
  it('announces browser offline state and clears it after reconnecting', () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    render(<NetworkStatusNotice />)

    expect(screen.getByRole('status')).toHaveTextContent('浏览器当前处于离线状态')

    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    fireEvent(window, new Event('online'))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
