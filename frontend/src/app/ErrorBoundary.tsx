import type { ErrorInfo, PropsWithChildren, ReactNode } from 'react'
import { Component } from 'react'

type State = {
  error: Error | null
}

export class ErrorBoundary extends Component<PropsWithChildren, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Uncaught application error', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <main className="fatal-error">
          <p className="eyebrow">SYSTEM / RECOVERY</p>
          <h1>页面没有安全地完成渲染。</h1>
          <p>请刷新页面；若问题持续存在，保留当前地址用于排查。</p>
        </main>
      )
    }
    return this.props.children
  }
}
