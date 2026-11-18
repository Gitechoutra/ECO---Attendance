import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { api } from '../api/client'
import { AuthProvider } from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext'
import LoginPage from '../features/auth/LoginPage'

/** Stub the HTTP layer (axios adapter) so the real client, interceptors and error mapping are exercised. */
const calls = []
function respond(handler) {
  api.defaults.adapter = async (config) => {
    calls.push({ url: config.url, body: config.data ? JSON.parse(config.data) : null })
    return handler(config)
  }
}
const httpError = (status, detail, config) => {
  const err = new Error(`Request failed with status code ${status}`)
  Object.assign(err, { config, response: { status, data: { detail }, headers: {}, config } })
  throw err
}

function renderLogin() {
  return render(<MemoryRouter><ToastProvider><AuthProvider><LoginPage /></AuthProvider></ToastProvider></MemoryRouter>)
}

describe('LoginPage', () => {
  afterEach(() => { calls.length = 0; vi.restoreAllMocks() })

  it('validates empty input before calling the API', async () => {
    respond(() => { throw new Error('should not be called') })
    renderLogin()
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your work email and password.')
    expect(calls).toHaveLength(0)
  })

  it('shows the server message on failed sign-in', async () => {
    respond((config) => httpError(401, 'Invalid email or password', config))
    renderLogin()
    await userEvent.type(screen.getByLabelText('Work email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
    expect(calls[0]).toEqual({ url: '/auth/login', body: { email: 'a@example.com', password: 'wrong' } })
  })

  it('shows lockout messages from the server', async () => {
    respond((config) => httpError(423, 'Account temporarily locked. Try again in 15 minute(s).', config))
    renderLogin()
    await userEvent.type(screen.getByLabelText('Work email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily locked')
  })

  it('explains network failures', async () => {
    respond(() => { const e = new Error('Network Error'); e.code = 'ERR_NETWORK'; throw e })
    renderLogin()
    await userEvent.type(screen.getByLabelText('Work email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Cannot reach the server|offline/)
  })
})
