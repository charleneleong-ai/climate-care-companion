'use client'

import { useEffect, useRef, useState } from 'react'

import type { Profile } from '@/lib/profile'

interface Turn {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  profile: Profile
  /** Prompts seeded from the current risk band, so the first tap is useful. */
  suggestions: string[]
}

/**
 * Streaming chat with the assistant.
 *
 * Phase 2 (voice) wraps this without redesign: replace the textarea with a mic
 * button that fills `input` from the Web Speech API, and pipe the same streamed
 * chunks into speechSynthesis. `send()` already takes the text and streams the
 * reply — that is the whole integration point.
 */
export default function Assistant({ profile, suggestions }: Props) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Keep the newest message in view as it streams in.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  // Don't leave a request hanging if the user navigates away mid-stream.
  useEffect(() => () => abortRef.current?.abort(), [])

  async function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || streaming) return

    setError(null)
    setInput('')

    const history: Turn[] = [...turns, { role: 'user', content: trimmed }]
    // Push the user turn plus an empty assistant turn we stream into.
    setTurns([...history, { role: 'assistant', content: '' }])
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch('/api/assistant', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ profile, messages: history, mode: 'text' }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error ?? `The assistant is unavailable (${res.status}).`)
      }
      if (!res.body) throw new Error('The assistant returned an empty response.')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })

        setTurns((prev) => {
          const next = [...prev]
          const last = next.at(-1)
          if (last?.role === 'assistant') {
            next[next.length - 1] = { ...last, content: last.content + chunk }
          }
          return next
        })
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      setError((e as Error).message)
      // Drop the empty assistant bubble so the transcript isn't left dangling.
      setTurns((prev) => (prev.at(-1)?.content === '' ? prev.slice(0, -1) : prev))
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-[16px] muted">
              Ask about staying safe today. I know your region&apos;s conditions and what you told
              us about yourself.
            </p>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="btn btn-secondary px-3.5 text-[15px]"
                  style={{ minHeight: '40px' }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div
            key={i}
            className={turn.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              style={
                turn.role === 'user'
                  ? { background: 'var(--ink)', color: 'var(--paper)' }
                  : undefined
              }
              className={
                turn.role === 'user'
                  ? 'max-w-[85%] rounded-2xl rounded-br-sm px-3.5 py-2.5 text-[16px]'
                  : 'card max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-[16px]'
              }
            >
              {turn.content ||
                (streaming && (
                  <span className="inline-flex gap-1" aria-label="Thinking">
                    <Dot delay="0ms" />
                    <Dot delay="150ms" />
                    <Dot delay="300ms" />
                  </span>
                ))}
            </div>
          </div>
        ))}

        {error && (
          <p role="alert" className="text-[15px] font-medium"
            style={{ color: 'var(--danger)' }}>
            {error}
          </p>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
        className="flex items-end gap-2 border-t px-3 py-3"
        style={{ borderColor: 'var(--line)' }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter makes a new line.
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(input)
            }
          }}
          rows={1}
          placeholder="Ask about today…"
          aria-label="Message the assistant"
          className="field max-h-32 flex-1 resize-none"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="btn btn-primary px-5"
        >
          {streaming ? '…' : 'Send'}
        </button>
      </form>
    </div>
  )
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-50"
      style={{ animationDelay: delay }}
    />
  )
}
