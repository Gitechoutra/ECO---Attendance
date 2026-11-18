import { Component } from 'react'

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('UI error', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
        <p className="text-lg font-semibold">This page ran into a problem</p>
        <p className="mt-1 max-w-md text-sm text-muted">Reload to try again. If it keeps happening, let your administrator know what you were doing.</p>
        <button onClick={() => window.location.reload()} className="mt-5 h-10 rounded-lg bg-brand px-4 text-sm font-semibold text-[#03211D]">Reload</button>
      </div>
    )
  }
}
