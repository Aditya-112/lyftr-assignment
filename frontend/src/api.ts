export interface Metadata {
  resolution_source: 'LIVE_INFERENCE' | 'LLM_CACHE'
  model: string
  latency_ms: number
  input_tokens: number
  output_tokens: number
  key_id: string | null
  fallback_attempts: number
}

export type Message =
  | { role: 'user'; content: string }
  | { role: 'assistant'; content: string; metadata: Metadata }

interface ChatResponse {
  session_id: string
  reply: string
  metadata: Metadata
}

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isMetadata(value: unknown): value is Metadata {
  return isObject(value)
    && (value.resolution_source === 'LIVE_INFERENCE' || value.resolution_source === 'LLM_CACHE')
    && typeof value.model === 'string'
    && Number.isInteger(value.latency_ms)
    && Number.isInteger(value.input_tokens)
    && Number.isInteger(value.output_tokens)
    && (value.key_id === null || typeof value.key_id === 'string')
    && Number.isInteger(value.fallback_attempts)
}

function isMessage(value: unknown): value is Message {
  return isObject(value) && typeof value.content === 'string'
    && (value.role === 'user' || (value.role === 'assistant' && isMetadata(value.metadata)))
}

function isChatResponse(value: unknown): value is ChatResponse {
  return isObject(value) && typeof value.session_id === 'string'
    && typeof value.reply === 'string' && isMetadata(value.metadata)
}

async function request(path: string, options?: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(apiBase + path, options)
  } catch {
    throw new Error('The server couldn’t be reached. Check your connection and try again.')
  }

  if (!response.ok) {
    if (response.status === 422) throw new Error('Check your message. It should contain 1 to 4,000 characters.')
    if (response.status === 503) throw new Error('The model is temporarily unavailable. Try again in a moment.')
    throw new Error('Something went wrong. Please try again.')
  }

  try {
    return await response.json()
  } catch {
    throw new Error('The server returned an unreadable response. Please try again.')
  }
}

export async function sendMessage(sessionId: string, message: string, systemPrompt?: string) {
  const result = await request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message, system_prompt: systemPrompt }),
  })
  if (!isChatResponse(result) || result.session_id !== sessionId) {
    throw new Error('The server returned an unexpected reply. Please try again.')
  }
  return result
}

export async function getHistory(sessionId: string) {
  const result = await request('/sessions/' + encodeURIComponent(sessionId) + '/messages')
  if (!isObject(result) || !Array.isArray(result.messages) || !result.messages.every(isMessage)) {
    throw new Error('The server returned an unreadable conversation.')
  }
  return result.messages as Message[]
}

export async function getHealth(signal: AbortSignal) {
  const result = await request('/health', { signal })
  if (!isObject(result) || result.status !== 'ok') throw new Error('Backend unavailable')
}
