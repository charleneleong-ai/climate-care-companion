/**
 * The assistant's brain, behind one interface.
 *
 * Claude is the default because phone users out in the world need a model they
 * can actually reach. The Ollama path exists so the whole stack can still be
 * run locally with no external calls — set LLM_PROVIDER=ollama.
 */

import Anthropic from '@anthropic-ai/sdk'

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface LLMRequest {
  system: string
  messages: ChatTurn[]
}

export interface LLMProvider {
  name: string
  /** Streams plain text chunks. Voice wraps this unchanged — see assistant/route.ts. */
  stream(req: LLMRequest): AsyncIterable<string>
}

/** Thrown when the model declines the request, so the route can answer sensibly. */
export class ModelRefusalError extends Error {
  constructor(readonly category: string | null) {
    super('The assistant declined to answer that.')
    this.name = 'ModelRefusalError'
  }
}

const MODEL = process.env.CLAUDE_MODEL ?? 'claude-opus-5'

class ClaudeProvider implements LLMProvider {
  name = `claude (${MODEL})`
  private client: Anthropic

  constructor() {
    // Zero-arg constructor resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
    // or an `ant auth login` profile — so local dev needs no explicit key.
    this.client = new Anthropic()
  }

  async *stream(req: LLMRequest): AsyncIterable<string> {
    const stream = this.client.messages.stream({
      model: MODEL,
      max_tokens: 1500,
      // Low effort: this is a short conversational turn over context we have
      // already computed, not a reasoning problem. Thinking stays on (the
      // default) — disabling it on Opus 5 risks tool calls and <thinking>
      // tags leaking into the visible text.
      output_config: { effort: 'low' },
      system: [
        {
          type: 'text',
          text: req.system,
          // The system prompt is the stable prefix and is identical across
          // every user, so it caches once and is read cheaply thereafter.
          cache_control: { type: 'ephemeral' },
        },
      ],
      messages: req.messages.map((m) => ({ role: m.role, content: m.content })),
    })

    for await (const event of stream) {
      if (event.type === 'content_block_delta' && event.delta.type === 'text_delta') {
        yield event.delta.text
      }
    }

    const final = await stream.finalMessage()
    if (final.stop_reason === 'refusal') {
      throw new ModelRefusalError(final.stop_details?.category ?? null)
    }
  }
}

class OllamaProvider implements LLMProvider {
  name = `ollama (${process.env.OLLAMA_MODEL ?? 'llama3.1'})`

  async *stream(req: LLMRequest): AsyncIterable<string> {
    const host = process.env.OLLAMA_HOST ?? 'http://127.0.0.1:11434'
    const res = await fetch(`${host}/api/chat`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        model: process.env.OLLAMA_MODEL ?? 'llama3.1',
        stream: true,
        messages: [{ role: 'system', content: req.system }, ...req.messages],
      }),
    })

    if (!res.ok || !res.body) {
      throw new Error(`Ollama returned ${res.status} ${res.statusText}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Ollama streams newline-delimited JSON; a chunk can split mid-object.
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const parsed = JSON.parse(line)
          if (parsed.message?.content) yield parsed.message.content as string
        } catch {
          // Ignore a malformed line rather than killing the stream.
        }
      }
    }
  }
}

let cached: LLMProvider | undefined

export function getProvider(): LLMProvider {
  if (cached) return cached
  cached = process.env.LLM_PROVIDER === 'ollama' ? new OllamaProvider() : new ClaudeProvider()
  return cached
}
