import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LoginPage, RegisterPage } from './AccountPages'

afterEach(cleanup)

describe('account pages', () => {
  it('shows one neutral message for every rejected login', async () => {
    const login = vi.fn(async () => {
      throw new Error('account does not exist')
    })
    render(
      <LoginPage
        onLogin={login}
        onAuthenticated={() => undefined}
        registerHref="/register"
      />,
    )

    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'unknown@example.com' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录并继续' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('邮箱或密码不正确')
    expect(screen.queryByText('account does not exist')).not.toBeInTheDocument()
  })

  it('does not submit registration while passwords differ', async () => {
    const register = vi.fn(async () => undefined)
    render(
      <RegisterPage
        onRegister={register}
        onAuthenticated={() => undefined}
        loginHref="/login"
      />,
    )

    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.change(screen.getByLabelText('确认密码'), {
      target: { value: 'different-passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('两次输入的密码不一致')
    await waitFor(() => expect(register).not.toHaveBeenCalled())
  })
})
