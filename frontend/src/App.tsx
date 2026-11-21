import {
  AlignLeft, AlertCircle, Braces, Layers3, ListChecks, MessageSquare,
  PenLine, Plus, Send, SlidersHorizontal, X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import Markdown from 'react-markdown'
import { getHealth, getHistory, sendMessage } from './api'
import type { Message, Metadata } from './api'

const messageLimit = 4000

const suggestions = [
  {
    title: 'Learn a concept',
    description: 'Understand how a cache works',
    icon: Braces,
    prompt: 'Explain how a cache works using an everyday example.',
  },
  {
    title: 'Draft something',
    description: 'Write a thoughtful follow-up',
    icon: PenLine,
    prompt: 'Help me draft a short follow-up email after a job interview.',
  },
  {
    title: 'Make a plan',
    description: 'Get started on a new project',
    icon: ListChecks,
    prompt: 'Give me a practical one-week plan for starting a small software project.',
  },
]

interface Conversation {
  id: string
  title: string
}

function newSession(): Conversation {
  return { id: crypto.randomUUID(), title: 'New conversation' }
}

function ReplyMetadata({ metadata }: { metadata: Metadata }) {
  return (
    <dl className="metadata" aria-label="Response details">
      <div className="source">
        <dt className="sr-only">Resolution source</dt>
        <dd data-testid="meta-source" className={metadata.resolution_source === 'LLM_CACHE' ? 'cached' : ''}>
          {metadata.resolution_source}
        </dd>
      </div>
      <div className="model">
        <dt>Model</dt><dd data-testid="meta-model">{metadata.model}</dd>
      </div>
      <div>
        <dt>Latency</dt><dd data-testid="meta-latency">{metadata.latency_ms} ms</dd>
      </div>
      <div>
        <dt>Input</dt><dd data-testid="meta-input-tokens">{metadata.input_tokens}</dd>
      </div>
      <div>
        <dt>Output</dt><dd data-testid="meta-output-tokens">{metadata.output_tokens}</dd>
      </div>
    </dl>
  )
}

function UserMessage({ content }: { content: string }) {
  return <article className="user-message" aria-label="Your message">{content}</article>
}

function AssistantMessage({ message }: { message: Extract<Message, { role: 'assistant' }> }) {
  return (
    <article data-testid="assistant-message" className="assistant-message" aria-label="Assistant reply">
      <span className="assistant-avatar"><Layers3 size={18} aria-hidden="true" /></span>
      <div className="assistant-content">
        <div className="speaker">Lyftr</div>
        <div className="reply">
          <Markdown skipHtml disallowedElements={['img']} components={{
            a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
          }}>{message.content}</Markdown>
        </div>
        <ReplyMetadata metadata={message.metadata} />
      </div>
    </article>
  )
}

function Welcome({ choosePrompt }: { choosePrompt: (prompt: string) => void }) {
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <div className="welcome-icon"><Layers3 size={32} strokeWidth={1.6} aria-hidden="true" /></div>
      <h1 id="welcome-title">What’s on your mind?</h1>
      <p>Ask a question, work through an idea, or start with a prompt below.</p>
      <div className="suggestions">
        {suggestions.map(({ title, description, icon: Icon, prompt }) => (
          <button type="button" className="suggestion" key={title} onClick={() => choosePrompt(prompt)}>
            <span className="suggestion-icon"><Icon size={18} aria-hidden="true" /></span>
            <span className="suggestion-copy"><strong>{title}</strong><span>{description}</span></span>
          </button>
        ))}
      </div>
    </section>
  )
}

export function App() {
  const [session, setSession] = useState(newSession)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [promptEdited, setPromptEdited] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)
  const [showSidebar, setShowSidebar] = useState(false)
  const [pending, setPending] = useState<string>()
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<'checking' | 'online' | 'offline'>('checking')
  const activeRequest = useRef(false)
  const chatInput = useRef<HTMLTextAreaElement>(null)
  const scrollArea = useRef<HTMLDivElement>(null)

  const trimmedLength = Array.from(input.trim()).length
  const busy = pending !== undefined || loadingHistory
  const overLimit = trimmedLength > messageLimit

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then(() => setHealth('online'))
      .catch(() => { if (!controller.signal.aborted) setHealth('offline') })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const area = scrollArea.current
    if (area && (messages.length || pending || error)) area.scrollTop = area.scrollHeight
  }, [messages, pending, error])

  function resetComposer() {
    setInput('')
    setSystemPrompt('')
    setPromptEdited(false)
    setShowPrompt(false)
    setShowSidebar(false)
    setError('')
  }

  function startChat() {
    if (activeRequest.current) return
    setSession(newSession())
    setMessages([])
    resetComposer()
    chatInput.current?.focus()
  }

  async function openConversation(conversation: Conversation) {
    if (activeRequest.current || conversation.id === session.id) {
      setShowSidebar(false)
      return
    }
    activeRequest.current = true
    setLoadingHistory(true)
    resetComposer()
    try {
      setMessages(await getHistory(conversation.id))
      setSession(conversation)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Couldn’t load this conversation.')
    } finally {
      activeRequest.current = false
      setLoadingHistory(false)
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = input.trim()
    if (activeRequest.current || !message || overLimit) return

    activeRequest.current = true
    setPending(message)
    setError('')
    try {
      const response = await sendMessage(session.id, message, promptEdited ? systemPrompt : undefined)
      if (!messages.length) {
        const characters = Array.from(message.replace(/\s+/g, ' '))
        const title = characters.length > 45 ? characters.slice(0, 44).join('').trimEnd() + '…' : characters.join('')
        const conversation = { id: session.id, title }
        setSession(conversation)
        setConversations(previous => [conversation, ...previous])
      }
      setMessages(previous => [
        ...previous,
        { role: 'user', content: message },
        { role: 'assistant', content: response.reply, metadata: response.metadata },
      ])
      setInput('')
      setPromptEdited(false)
      setHealth('online')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Couldn’t send your message. Try again.')
    } finally {
      activeRequest.current = false
      setPending(undefined)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <div className="app-shell">
      {showSidebar && <button type="button" className="sidebar-overlay" aria-hidden="true" tabIndex={-1} onClick={() => setShowSidebar(false)} />}
      <aside id="conversation-sidebar" className={showSidebar ? 'sidebar open' : 'sidebar'} aria-label="Conversation sidebar">
        <div className="brand">
          <span className="brand-mark"><Layers3 size={21} strokeWidth={1.8} aria-hidden="true" /></span>
          <span>Lyftr <strong>Chat</strong></span>
          <button className="icon-button close-sidebar" type="button" aria-label="Close sidebar" onClick={() => setShowSidebar(false)}>
            <X size={19} aria-hidden="true" />
          </button>
        </div>
        <button type="button" className="new-chat" disabled={busy} onClick={startChat}>
          <Plus size={19} aria-hidden="true" /> New chat
        </button>
        <nav className="conversations" aria-label="Conversations">
          <h2>Conversations</h2>
          {!conversations.some(item => item.id === session.id) && (
            <button type="button" className="conversation current" aria-current="true" onClick={() => setShowSidebar(false)}>
              <MessageSquare size={16} aria-hidden="true" /><span>{session.title}</span>
            </button>
          )}
          {conversations.map(conversation => (
            <button
              type="button"
              key={conversation.id}
              className={conversation.id === session.id ? 'conversation current' : 'conversation'}
              aria-current={conversation.id === session.id ? 'true' : undefined}
              disabled={busy}
              onClick={() => { void openConversation(conversation) }}
            >
              <MessageSquare size={16} aria-hidden="true" /><span>{conversation.title}</span>
            </button>
          ))}
        </nav>
        <div className="connection">
          <span className={'status-dot ' + health} aria-hidden="true" />
          {health === 'online' ? 'Backend connected' : health === 'offline' ? 'Backend unavailable' : 'Checking connection'}
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="header-title">
            <button
              type="button" className="icon-button open-sidebar" aria-label="Open conversations"
              aria-expanded={showSidebar} aria-controls="conversation-sidebar" onClick={() => setShowSidebar(true)}
            >
              <AlignLeft size={21} aria-hidden="true" />
            </button>
            <span title={session.title}>{session.title}</span>
          </div>
          <button type="button" className="prompt-toggle" aria-expanded={showPrompt} onClick={() => setShowPrompt(!showPrompt)}>
            <SlidersHorizontal size={16} aria-hidden="true" /> <span>System prompt</span>
          </button>
        </header>

        {showPrompt && (
          <div className="prompt-panel">
            <label htmlFor="system-prompt">System prompt</label>
            <textarea
              id="system-prompt"
              data-testid="system-prompt-input"
              value={systemPrompt}
              placeholder="Set instructions for future replies"
              rows={2}
              disabled={busy}
              onChange={event => {
                setSystemPrompt(event.target.value)
                setPromptEdited(true)
              }}
            />
          </div>
        )}

        <div ref={scrollArea} className="scroll-area">
          {messages.length || pending || loadingHistory ? (
            <div className="transcript content-width" aria-live="polite" aria-label="Chat messages">
              {messages.map((message, index) => message.role === 'user'
                ? <UserMessage key={index} content={message.content} />
                : <AssistantMessage key={index} message={message} />)}
              {pending && (
                <>
                  <UserMessage content={pending} />
                  <div className="pending" role="status">
                    <span className="assistant-avatar"><Layers3 size={18} aria-hidden="true" /></span>
                    <span>Lyftr is thinking<span className="loading-ellipsis">…</span></span>
                  </div>
                </>
              )}
              {loadingHistory && <p role="status">Loading conversation…</p>}
            </div>
          ) : (
            <Welcome choosePrompt={prompt => {
              setInput(prompt)
              setError('')
              chatInput.current?.focus()
            }} />
          )}
          {error && (
            <div className="error-wrap content-width">
              <div className="chat-error" role="alert"><AlertCircle size={18} aria-hidden="true" />{error}</div>
            </div>
          )}
        </div>

        <div className="composer-area">
          <form className="composer content-width" onSubmit={submit}>
            <label className="sr-only" htmlFor="chat-input">Message</label>
            <textarea
              id="chat-input"
              data-testid="chat-input"
              ref={chatInput}
              value={input}
              rows={2}
              placeholder="Message Lyftr…"
              aria-invalid={overLimit || undefined}
              aria-describedby="composer-hint"
              readOnly={busy}
              onChange={event => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
            />
            <div className="composer-actions">
              <span id="composer-hint" className={overLimit ? 'limit-error' : ''}>
                {overLimit ? 'Message exceeds 4,000 characters' : <><kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for a new line</>}
              </span>
              <button type="submit" className="send-button" data-testid="send-button" aria-label="Send message"
                disabled={!trimmedLength || overLimit || busy}>
                <Send size={19} strokeWidth={2} aria-hidden="true" />
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  )
}
