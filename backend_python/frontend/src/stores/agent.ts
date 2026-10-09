import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError } from '../api/client'
import * as agentApi from '../api/agent'
import type { AgentEvent, Conversation, HistoryMessage } from '../api/agent'
import type { SseStream } from '../api/sseStream'
import { lastNavigation, toastsFrom } from '../utils/uiActions'
import { useAuthStore } from './auth'
import { useToastStore } from './toast'

/**
 * The floating assistant's state.
 *
 * The panel is mounted in App.vue, outside <RouterView>, so a `navigate` during
 * a turn only swaps the page underneath -- the conversation stays on screen.
 * That is the whole reason this is a floating panel rather than a /agent page.
 */

export type ChatEntry =
  | { kind: 'user'; key: string; text: string }
  | { kind: 'assistant'; key: string; text: string }
  | {
      kind: 'tool'
      key: string
      tool: string
      status: 'running' | 'ok' | 'failed'
      summary: string
    }

export type PendingConfirm = {
  calls: {
    call_id: string
    tool: string
    args: Record<string, unknown>
    preview: string
  }[]
}

const AUTO_NAVIGATE_KEY = 'agent.autoNavigate'

let keySeq = 0
function nextKey() {
  keySeq += 1
  return `e${keySeq}`
}

function messageOf(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e)
}

function toastType(level: string): 'success' | 'error' | 'info' {
  if (level === 'ok' || level === 'success') return 'success'
  if (level === 'error') return 'error'
  return 'info'
}

export const useAgentStore = defineStore('agent', () => {
  const auth = useAuthStore()
  const toast = useToastStore()

  const open = ref(false)
  const busy = ref(false)
  const connected = ref(false)
  const error = ref('')
  const conversations = ref<Conversation[]>([])
  const conversationsLoading = ref(false)
  const currentThread = ref<string | null>(null)
  const entries = ref<ChatEntry[]>([])
  const pending = ref<PendingConfirm | null>(null)

  /**
   * Set when a turn finished with a navigate instruction. The panel watches it
   * and pushes the route, then clears it -- the store never touches the router.
   */
  const navigation = ref<string | null>(null)

  const autoNavigate = ref(
    window.localStorage.getItem(AUTO_NAVIGATE_KEY) !== 'off',
  )

  /** Navigations seen so far in the current turn (last one wins). */
  let turnNavigations: string[] = []
  let stream: SseStream | null = null

  const hasPending = computed(() => (pending.value?.calls.length ?? 0) > 0)

  function setAutoNavigate(value: boolean) {
    autoNavigate.value = value
    window.localStorage.setItem(AUTO_NAVIGATE_KEY, value ? 'on' : 'off')
  }

  function toggleOpen(value?: boolean) {
    open.value = value ?? !open.value
  }

  function clearNavigation() {
    navigation.value = null
  }

  async function loadConversations() {
    if (!auth.isLoggedIn) {
      conversations.value = []
      return
    }
    conversationsLoading.value = true
    try {
      conversations.value = await agentApi.listConversations()
    } catch (e) {
      error.value = messageOf(e)
    } finally {
      conversationsLoading.value = false
    }
  }

  function startNewConversation() {
    stream?.stop()
    stream = null
    currentThread.value = null
    entries.value = []
    pending.value = null
    error.value = ''
    busy.value = false
  }

  async function openConversation(threadId: string) {
    stream?.stop()
    stream = null
    currentThread.value = threadId
    pending.value = null
    error.value = ''
    busy.value = false
    try {
      const history = await agentApi.getHistory(threadId)
      entries.value = historyToEntries(history)
    } catch (e) {
      entries.value = []
      error.value = messageOf(e)
    }
  }

  async function removeConversation(threadId: string) {
    try {
      await agentApi.deleteConversation(threadId)
      conversations.value = conversations.value.filter(
        (c) => c.thread_id !== threadId,
      )
      if (currentThread.value === threadId) startNewConversation()
    } catch (e) {
      error.value = messageOf(e)
    }
  }

  function appendToken(text: string) {
    if (!text) return
    const last = entries.value[entries.value.length - 1]
    if (last && last.kind === 'assistant') {
      last.text += text
      return
    }
    entries.value.push({ kind: 'assistant', key: nextKey(), text })
  }

  function handleEvent(event: AgentEvent) {
    const data = event.data ?? {}
    switch (event.event) {
      case 'token':
        appendToken(String(data.text ?? ''))
        break

      case 'tool_start':
        entries.value.push({
          kind: 'tool',
          key: `call-${data.call_id}`,
          tool: String(data.tool ?? ''),
          status: 'running',
          summary: '正在执行…',
        })
        break

      case 'tool_end': {
        const entry = entries.value.find(
          (e) => e.kind === 'tool' && e.key === `call-${data.call_id}`,
        )
        if (entry && entry.kind === 'tool') {
          entry.status = data.ok ? 'ok' : 'failed'
          entry.summary = String(data.summary ?? '')
        }
        for (const t of toastsFrom(data.ui)) {
          toast.push(toastType(t.level), t.text)
        }
        const target = lastNavigation(data.ui)
        if (target) turnNavigations.push(target)
        break
      }

      case 'confirm_required':
        pending.value = {
          calls: Array.isArray(data.calls) ? data.calls : [],
        }
        break

      case 'error':
        error.value = String(data.message ?? '出错了')
        break

      case 'done':
        busy.value = false
        // A brand-new conversation is created server-side, so this is where its
        // thread_id first reaches the client. Without capturing it here every
        // message would start a fresh conversation.
        if (typeof data.thread_id === 'string' && data.thread_id) {
          currentThread.value = data.thread_id
        }
        // Last-win, and only once the turn is over: a turn that touches three
        // tools should not yank the user through three pages.
        const target = turnNavigations[turnNavigations.length - 1]
        if (target && autoNavigate.value) {
          navigation.value = target
        }
        turnNavigations = []
        void loadConversations()
        break
    }
  }

  /** Runs one SSE stream to completion. Resolves on done / error / disconnect. */
  function runStream(make: (handlers: Parameters<typeof agentApi.streamChat>[1]) => SseStream) {
    return new Promise<void>((resolve) => {
      let settled = false
      const finish = () => {
        if (settled) return
        settled = true
        resolve()
      }
      stream?.stop()
      stream = make({
        onEvent: (payload) => {
          const event = payload as AgentEvent
          handleEvent(event)
          if (event?.event === 'done' || event?.event === 'error') finish()
        },
        onStatus: (value) => {
          connected.value = value
          // Stream dropped before finishing: don't leave the UI stuck "thinking".
          if (!value && !settled) {
            busy.value = false
            finish()
          }
        },
        onError: (message) => {
          error.value = message
          busy.value = false
          finish()
        },
      })
      stream.start()
    })
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim()
    if (!trimmed || busy.value) return
    error.value = ''
    pending.value = null
    turnNavigations = []
    entries.value.push({ kind: 'user', key: nextKey(), text: trimmed })
    busy.value = true

    await runStream((handlers) =>
      agentApi.streamChat(
        { message: trimmed, thread_id: currentThread.value },
        handlers,
      ),
    )
  }

  async function resolveConfirm(approved: boolean) {
    const target = pending.value
    if (!target) return
    const threadId = currentThread.value
    pending.value = null
    if (!threadId) return

    busy.value = true
    if (!approved) {
      entries.value.push({
        kind: 'assistant',
        key: nextKey(),
        text: '好的，已取消该操作。',
      })
    }
    await runStream((handlers) =>
      agentApi.streamConfirm(
        { thread_id: threadId, approved },
        handlers,
      ),
    )
  }

  function reset() {
    stream?.stop()
    stream = null
    open.value = false
    busy.value = false
    connected.value = false
    error.value = ''
    conversations.value = []
    currentThread.value = null
    entries.value = []
    pending.value = null
    navigation.value = null
    turnNavigations = []
  }

  return {
    open,
    busy,
    connected,
    error,
    conversations,
    conversationsLoading,
    currentThread,
    entries,
    pending,
    hasPending,
    navigation,
    autoNavigate,
    setAutoNavigate,
    toggleOpen,
    clearNavigation,
    loadConversations,
    startNewConversation,
    openConversation,
    removeConversation,
    sendMessage,
    resolveConfirm,
    reset,
  }
})

/** Transcript for the read-only view. Tool traffic stays live-only. */
function historyToEntries(history: HistoryMessage[]): ChatEntry[] {
  const out: ChatEntry[] = []
  for (const message of history) {
    if (message.role === 'user') {
      out.push({ kind: 'user', key: nextKey(), text: message.content })
    } else if (message.role === 'assistant' && message.content) {
      out.push({ kind: 'assistant', key: nextKey(), text: message.content })
    }
  }
  return out
}
