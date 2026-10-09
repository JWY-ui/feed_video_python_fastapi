import { API_BASE, refreshAccessToken } from './client'
import { useAuthStore } from '../stores/auth'

/**
 * Server-Sent Events over fetch + ReadableStream, shared by the notification
 * stream and the agent.
 *
 * Not the browser's EventSource: our SSE endpoints authenticate with an
 * Authorization header, which EventSource cannot send. The alternative -- a
 * token in the query string -- would leak it into access logs and history.
 *
 * Extracted from notificationStream.ts so the agent does not grow a second copy
 * of the frame parser, the reconnect backoff, and the 401-refresh handshake.
 */

export type SseRequest = {
  path: string
  init?: RequestInit
}

export type SseHandlers = {
  onEvent: (payload: unknown) => void
  /** Fires true once the stream is live, false when it drops. */
  onStatus?: (connected: boolean) => void
  /** The server refused the stream (4xx/5xx other than 401). */
  onError?: (message: string) => void
}

export type SseOptions = {
  /**
   * Reconnect when the stream drops. Default true.
   *
   * Must be false for one-shot streams: reconnecting the agent's chat request
   * would re-POST the turn and run it twice.
   */
  reconnect?: boolean
}

export type SseStream = {
  start: () => void
  stop: () => void
}

const MAX_BACKOFF_MS = 30_000

/**
 * Split complete SSE frames off the front of `buffer`, returning what is left.
 *
 * The residual matters: a chunk boundary can fall in the middle of a frame, so
 * anything after the last blank line must be held until more bytes arrive.
 * Frames are separated by a blank line, which may be \n\n or \r\n\r\n.
 */
export function drainFrames(buffer: string, onFrame: (raw: string) => void): string {
  const boundary = /\r?\n\r?\n/
  let match = boundary.exec(buffer)
  while (match) {
    onFrame(buffer.slice(0, match.index))
    buffer = buffer.slice(match.index + match[0].length)
    match = boundary.exec(buffer)
  }
  return buffer
}

/**
 * Interpret one frame. Per the SSE spec:
 *   - `data:` lines concatenate with newlines to form the payload
 *   - a line starting with `:` is a comment (we use it for keepalives) -- ignore
 *   - a single space after the colon is optional
 */
export function readFrame(raw: string): unknown | null {
  const dataLines: string[] = []
  for (const line of raw.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'data') dataLines.push(value)
  }
  if (dataLines.length === 0) return null

  try {
    return JSON.parse(dataLines.join('\n'))
  } catch {
    return null
  }
}

export function createSseStream(
  makeRequest: () => SseRequest,
  handlers: SseHandlers,
  options: SseOptions = {},
): SseStream {
  const reconnect = options.reconnect ?? true

  let stopped = false
  let controller: AbortController | null = null
  let timer: number | null = null
  let attempt = 0

  function dispatch(raw: string) {
    const payload = readFrame(raw)
    if (payload !== null) handlers.onEvent(payload)
  }

  async function readLoop(body: ReadableStream<Uint8Array>) {
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      while (!stopped) {
        const { value, done } = await reader.read()
        if (done) break
        // stream:true keeps a multi-byte character split across chunks intact.
        buffer += decoder.decode(value, { stream: true })
        buffer = drainFrames(buffer, dispatch)
      }
      // Flush a trailing frame that never got its blank-line terminator.
      if (buffer.trim()) dispatch(buffer)
    } finally {
      reader.releaseLock()
    }
  }

  function scheduleReconnect(immediate = false) {
    if (stopped || !reconnect) return
    const backoff = immediate ? 0 : Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempt)
    // Jitter so a server restart doesn't bring every client back in lockstep.
    const delay = backoff + Math.floor(Math.random() * 500)
    attempt += 1
    timer = window.setTimeout(() => {
      timer = null
      void run()
    }, delay)
  }

  async function run(): Promise<void> {
    if (stopped) return
    const auth = useAuthStore()
    const token = auth.token
    if (!token) {
      handlers.onStatus?.(false)
      return
    }

    const { path, init } = makeRequest()
    controller = new AbortController()
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: {
          ...(init?.headers as Record<string, string> | undefined),
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        signal: controller.signal,
      })

      if (res.status === 401) {
        // Share client.ts's single-flight refresh instead of racing it.
        const newToken = await refreshAccessToken()
        if (newToken) {
          scheduleReconnect(true)
        } else {
          // Either the session is genuinely gone (token already cleared by the
          // refresh flow) or the network is down. Only give up in the former case.
          handlers.onStatus?.(false)
          if (!auth.isLoggedIn) stopped = true
          else scheduleReconnect()
        }
        return
      }

      if (!res.ok || !res.body) {
        handlers.onStatus?.(false)
        handlers.onError?.(`请求失败 (${res.status})`)
        scheduleReconnect()
        return
      }

      attempt = 0
      handlers.onStatus?.(true)
      await readLoop(res.body)
      handlers.onStatus?.(false)
      // The server or a proxy closed the stream -- reconnect rather than give up.
      scheduleReconnect()
    } catch (e) {
      if (stopped || (e as { name?: string })?.name === 'AbortError') return
      handlers.onStatus?.(false)
      scheduleReconnect()
    }
  }

  return {
    start() {
      if (!stopped && (controller || timer !== null)) return
      stopped = false
      attempt = 0
      void run()
    },
    stop() {
      stopped = true
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
      controller?.abort()
      controller = null
      handlers.onStatus?.(false)
    },
  }
}
