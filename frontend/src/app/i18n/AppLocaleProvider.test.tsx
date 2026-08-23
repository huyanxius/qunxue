import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'

import { AppLocaleProvider, useAppLocale } from './AppLocaleProvider'

afterEach(() => {
  cleanup()
  localStorage.clear()
})

function LocaleProbe() {
  const { locale, setLocale, text } = useAppLocale()
  return (
    <>
      <span>{text('工作台', 'Workbench')}</span>
      <span>{locale}</span>
      <button type="button" onClick={() => setLocale('en-US')}>English</button>
    </>
  )
}

it('shares one locale across the app and updates the document language', () => {
  render(<AppLocaleProvider><LocaleProbe /></AppLocaleProvider>)

  fireEvent.click(screen.getByRole('button', { name: 'English' }))

  expect(screen.getByText('Workbench')).toBeVisible()
  expect(screen.getByText('en-US')).toBeVisible()
  expect(document.documentElement).toHaveAttribute('lang', 'en')
})
