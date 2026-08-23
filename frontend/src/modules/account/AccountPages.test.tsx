import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { loginViaApi } from './accountApi'
import { LoginPage, RegisterPage } from './AccountPages'

vi.mock('@paper-design/shaders-react', () => ({
  GrainGradient: ({ className }: { className?: string }) => <div className={className} />,
  PaperTexture: ({ className }: { className?: string }) => <div className={className} />,
}))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

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

  it('distinguishes a login service failure from rejected credentials', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: {
        code: 'internal_server_error',
        message: 'login unavailable',
        trace_id: 'trace-login-503',
      },
    }), { status: 503, headers: { 'Content-Type': 'application/json' } })))
    render(
      <LoginPage
        onLogin={loginViaApi}
        onAuthenticated={() => undefined}
        registerHref="/register"
      />,
    )

    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'known@example.com' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录并继续' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '登录服务暂时不可用，请稍后重试',
    )
  })

  it('does not mislabel a disconnected API as rejected credentials', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    render(
      <LoginPage
        onLogin={loginViaApi}
        onAuthenticated={() => undefined}
        registerHref="/register"
      />,
    )

    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'known@example.com' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录并继续' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '登录服务暂时不可用，请稍后重试',
    )
  })

  it('does not submit registration while passwords differ', async () => {
    const register = vi.fn(async () => undefined)
    render(
      <RegisterPage
        onRegister={register}
        onSendRegistrationCode={vi.fn(async () => ({ resendAfterSeconds: 60 }))}
        onAuthenticated={() => undefined}
        loginHref="/login"
      />,
    )

    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))
    fireEvent.change(await screen.findByLabelText('验证码'), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: '继续设置密码' }))
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

  it('enforces the published registration length boundaries', async () => {
    const register = vi.fn(async () => undefined)
    render(
      <RegisterPage
        onRegister={register}
        onSendRegistrationCode={vi.fn(async () => ({ resendAfterSeconds: 60 }))}
        onAuthenticated={() => undefined}
        loginHref="/login"
      />,
    )

    expect(screen.getByLabelText('邮箱')).toHaveAttribute('maxlength', '320')
    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))
    fireEvent.change(await screen.findByLabelText('验证码'), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: '继续设置密码' }))
    expect(screen.getByText('8-128 个字符。')).toBeVisible()
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'p'.repeat(129) },
    })
    fireEvent.change(screen.getByLabelText('确认密码'), {
      target: { value: 'p'.repeat(129) },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('密码需要 8-128 个字符')
    expect(register).not.toHaveBeenCalled()
  })

  it('moves registration through email, code, and password steps', async () => {
    const sendCode = vi.fn(async () => ({ resendAfterSeconds: 60 }))
    const register = vi.fn(async () => undefined)
    render(
      <RegisterPage
        onRegister={register}
        onSendRegistrationCode={sendCode}
        onAuthenticated={() => undefined}
        loginHref="/login"
      />,
    )

    expect(screen.getByText('第 1 步，共 3 步')).toBeVisible()
    expect(screen.queryByLabelText('验证码')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('密码')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))

    await waitFor(() => expect(sendCode).toHaveBeenCalledWith('new@example.com'))
    expect(screen.getByText('第 2 步，共 3 步')).toBeVisible()
    fireEvent.change(screen.getByLabelText('验证码'), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: '继续设置密码' }))

    expect(screen.getByText('第 3 步，共 3 步')).toBeVisible()
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.change(screen.getByLabelText('确认密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }))

    await waitFor(() => {
      expect(register).toHaveBeenCalledWith(
        'new@example.com',
        'research-passphrase',
        '123456',
      )
    })
  })
})
