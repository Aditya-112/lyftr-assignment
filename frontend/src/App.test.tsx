import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

const metadata = {
  resolution_source: 'LIVE_INFERENCE',
  model: 'gemini/gemini-3.1-flash-lite',
  input_tokens: 28,
  output_tokens: 6,
  latency_ms: 37,
  key_id: 'key_1',
  fallback_attempts: 0,
}

const fetchMock = vi.fn<typeof fetch>()
const requests: { session_id: string; message: string; system_prompt?: string }[] = []

function reply(sessionId: string, cached = false) {
  return Response.json({
    session_id: sessionId,
    reply: 'A **fixture** answer.',
    metadata: cached ? { ...metadata, resolution_source: 'LLM_CACHE', key_id: null } : metadata,
  })
}

function mockChat(handle: (sessionId: string) => Response | Promise<Response> = reply) {
  fetchMock.mockImplementation(async (url, options) => {
    if (String(url).endsWith('/health')) return Response.json({ status: 'ok' })
    if (String(url).endsWith('/chat')) {
      const body = JSON.parse(String(options?.body))
      requests.push(body)
      return handle(body.session_id)
    }
    return Response.json({
      messages: [
        { role: 'user', content: 'Tell me a joke.' },
        { role: 'assistant', content: 'A **fixture** answer.', metadata },
      ],
    })
  })
}

async function setup() {
  const user = userEvent.setup()
  const view = render(<App />)
  await screen.findByText('Backend connected')
  return { ...view, user, input: screen.getByTestId('chat-input') }
}

beforeEach(() => {
  requests.length = 0
  vi.stubGlobal('fetch', fetchMock)
  mockChat()
})

afterEach(() => {
  cleanup()
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('chat workspace', () => {
  it('sends only the new turn and renders each reply with its own metadata', async () => {
    const { user, input } = await setup()
    await user.type(input, 'Tell me a joke.{Enter}')
    const first = await screen.findByTestId('assistant-message')
    expect(within(first).getByText('fixture')).toBeVisible()
    expect(within(first).getByTestId('meta-source')).toHaveTextContent(/^LIVE_INFERENCE$/)
    expect(within(first).getByTestId('meta-model')).toHaveTextContent(metadata.model)
    expect(within(first).getByTestId('meta-latency')).toHaveTextContent(/^37 ms$/)
    expect(within(first).getByTestId('meta-input-tokens')).toHaveTextContent(/^28$/)
    expect(within(first).getByTestId('meta-output-tokens')).toHaveTextContent(/^6$/)
    expect(input).toHaveValue('')
    await user.type(input, 'One more.')
    await user.click(screen.getByTestId('send-button'))
    await waitFor(() => expect(screen.getAllByTestId('assistant-message')).toHaveLength(2))
    expect(requests[1]).toEqual({ session_id: requests[0].session_id, message: 'One more.' })
  })

  it('uses fresh session IDs for new chats and page loads and can reopen history', async () => {
    const { user, input, unmount } = await setup()
    await user.type(input, 'Tell me a joke.{Enter}')
    await screen.findByTestId('assistant-message')
    await user.click(screen.getByRole('button', { name: 'New chat' }))
    expect(screen.queryByTestId('assistant-message')).toBeNull()
    await user.click(screen.getByRole('button', { name: /learn a concept/i }))
    await user.click(screen.getByTestId('send-button'))
    await screen.findByTestId('assistant-message')
    expect(requests[1].session_id).not.toBe(requests[0].session_id)
    await user.click(screen.getByRole('button', { name: 'Tell me a joke.' }))
    expect(await screen.findByText('Tell me a joke.', { selector: 'article' })).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/' + requests[0].session_id + '/messages'))).toBe(true)
    unmount()
    const reloaded = await setup()
    await reloaded.user.type(reloaded.input, 'Fresh page.{Enter}')
    await screen.findByTestId('assistant-message')
    expect(requests[2].session_id).not.toBe(requests[1].session_id)
    expect(requests[2].session_id).not.toBe(requests[0].session_id)
  })

  it('applies an edited system prompt and exposes cached metadata', async () => {
    mockChat(sessionId => reply(sessionId, true))
    const { user, input } = await setup()
    await user.click(screen.getByRole('button', { name: 'System prompt' }))
    await user.type(screen.getByTestId('system-prompt-input'), 'Be concise')
    await user.type(input, 'First turn.{Enter}')
    expect(await screen.findByTestId('meta-source')).toHaveTextContent(/^LLM_CACHE$/)
    await user.type(input, 'Next turn.{Enter}')
    await waitFor(() => expect(requests).toHaveLength(2))
    expect(requests[0].system_prompt).toBe('Be concise')
    expect(requests[1]).not.toHaveProperty('system_prompt')
  })

  it.each([
    [422, /check your message/i],
    [503, /temporarily unavailable/i],
    [0, /server couldn’t be reached/i],
  ])('shows an in-chat error and preserves the draft for status %i', async (status, message) => {
    mockChat(() => {
      if (status === 0) throw new TypeError('Network error')
      return Response.json({ detail: 'raw error' }, { status })
    })
    const { user, input } = await setup()
    await user.type(input, 'Keep my draft.{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(input).toHaveValue('Keep my draft.')
    expect(screen.queryByTestId('assistant-message')).toBeNull()
    expect(screen.getByTestId('send-button')).toBeEnabled()
  })

  it('blocks duplicate submissions until the outstanding turn finishes', async () => {
    let resolve!: (response: Response) => void
    mockChat(() => new Promise<Response>(done => { resolve = done }))
    const { user, input } = await setup()
    await user.type(input, 'Only once.{Enter}{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('Lyftr is thinking')
    expect(screen.getByTestId('send-button')).toBeDisabled()
    expect(requests).toHaveLength(1)
    resolve(reply(requests[0].session_id))
    expect(await screen.findByTestId('assistant-message')).toBeVisible()
  })

  it('handles an incompatible success response without losing the conversation', async () => {
    const { user, input } = await setup()
    await user.type(input, 'First turn.{Enter}')
    await screen.findByTestId('assistant-message')
    mockChat(() => Response.json({ reply: 'Response with missing metadata' }))
    await user.type(input, 'Preserve this draft.{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(/unexpected reply/i)
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1)
    expect(input).toHaveValue('Preserve this draft.')
  })

  it('counts Unicode characters after trimming and allows Shift + Enter', async () => {
    const { user, input } = await setup()
    await user.type(input, 'First{Shift>}{Enter}{/Shift}Second')
    expect(input).toHaveValue('First\nSecond')
    fireEvent.change(input, { target: { value: ' ' + '🌱'.repeat(4000) + ' ' } })
    expect(screen.getByTestId('send-button')).toBeEnabled()
    fireEvent.change(input, { target: { value: '🌱'.repeat(4001) } })
    expect(screen.getByTestId('send-button')).toBeDisabled()
    expect(screen.getByText(/exceeds 4,000/i)).toBeVisible()
    expect(requests).toHaveLength(0)
  })
})
