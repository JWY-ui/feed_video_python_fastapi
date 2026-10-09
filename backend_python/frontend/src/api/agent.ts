import { postJson } from './client'
import { createSseStream, type SseHandlers, type SseStream } from './sseStream'

export type AgentEventName =
  | 'token'
  | 'tool_start'
  | 'tool_end'
  | 'confirm_required'
  | 'done'
  | 'error'

export type AgentEvent = {
  event: AgentEventName
  data: Record<string, any>
}

export type Conversation = {
  id: number
  thread_id: string
  title: string
  created_at: string
  updated_at: string
}

export type HistoryMessage = {
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_calls: { tool: string; args: Record<string, unknown> }[]
}

/**
 * All non-streaming agent calls are POST, matching the rest of this backend
 * (/notification/list, /notification/markRead). That keeps them on client.ts's
 * postJson, which already owns the 401-refresh handshake.
 */
export function createConversation(): Promise<Conversation> {
  return postJson<Conversation>('/agent/conversations', {}, { authRequired: true })
}

export function listConversations(): Promise<Conversation[]> {
  return postJson<Conversation[]>('/agent/conversations/list', {}, {
    authRequired: true,
  })
}

export function deleteConversation(threadId: string): Promise<unknown> {
  return postJson('/agent/conversations/delete', { thread_id: threadId }, {
    authRequired: true,
  })
}

export function getHistory(threadId: string): Promise<HistoryMessage[]> {
  return postJson<HistoryMessage[]>('/agent/conversations/history', {
    thread_id: threadId,
  }, { authRequired: true })
}

/**
 * One-shot streams: reconnect is OFF for both of these.
 *
 * They are POSTs that carry a turn. Auto-reconnecting would resend the request
 * and run the turn a second time -- for /confirm that means a second approval
 * prompt, and for /chat a duplicate message.
 */
export function streamChat(
  body: { message: string; thread_id?: string | null },
  handlers: SseHandlers,
): SseStream {
  return createSseStream(
    () => ({
      path: '/agent/chat',
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    }),
    handlers,
    { reconnect: false },
  )
}

export function streamConfirm(
  body: { thread_id: string; approved: boolean },
  handlers: SseHandlers,
): SseStream {
  return createSseStream(
    () => ({
      path: '/agent/confirm',
      init: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    }),
    handlers,
    { reconnect: false },
  )
}
