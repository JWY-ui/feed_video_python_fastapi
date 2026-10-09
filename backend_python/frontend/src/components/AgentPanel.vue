<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from './AppIcon.vue'
import { useAgentStore } from '../stores/agent'
import { useAuthStore } from '../stores/auth'

/**
 * The floating assistant.
 *
 * Mounted from App.vue, deliberately OUTSIDE <RouterView>. That is what makes
 * "the agent sends a DM, and the page slides to that conversation" work: the
 * route changes underneath while this panel -- and the conversation in it --
 * stays mounted. As its own /agent route, the first navigation would destroy it.
 *
 * z-index 185/190: above the drawers (120), below the toaster (200) so toasts
 * are never hidden.
 */

const auth = useAuthStore()
const agent = useAgentStore()
const router = useRouter()

const draft = ref('')
const showList = ref(false)
/** Where the last AI-triggered jump took us, so we can say so. */
const jumpedTo = ref('')
const messagesEl = ref<HTMLElement | null>(null)

// 有待确认的操作时，输入框也关掉：新一轮会让那次确认作废（后端也会拒绝，
// 这是第二道）。让用户先把确认卡处理掉。
const canSend = computed(
  () => draft.value.trim().length > 0 && !agent.busy && !agent.hasPending,
)

const scrollTick = computed(() => {
  const last = agent.entries[agent.entries.length - 1]
  const tail = last && last.kind === 'assistant' ? last.text.length : 0
  return `${agent.entries.length}:${tail}`
})

async function scrollToBottom() {
  await nextTick()
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(scrollTick, scrollToBottom)

function toggle() {
  agent.toggleOpen()
  if (agent.open) void agent.loadConversations()
  if (!agent.open) showList.value = false
}

async function submit() {
  if (!canSend.value) return
  const text = draft.value
  draft.value = ''
  jumpedTo.value = ''
  await agent.sendMessage(text)
}

async function newConversation() {
  agent.startNewConversation()
  showList.value = false
  jumpedTo.value = ''
  await nextTick()
}

async function openConversation(threadId: string) {
  showList.value = false
  jumpedTo.value = ''
  await agent.openConversation(threadId)
}

// A turn that ended with a navigate instruction. The store only records it;
// pushing the route is the panel's job (the store never touches the router).
watch(
  () => agent.navigation,
  (to) => {
    if (!to) return
    agent.clearNavigation()
    jumpedTo.value = to
    void router.push(to)
  },
)

function onKeydown(e: KeyboardEvent) {
  // Enter sends, Shift+Enter is a newline.
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    void submit()
  }
}
</script>

<template>
  <template v-if="auth.isLoggedIn">
    <button
      v-if="!agent.open"
      class="agent-ball"
      type="button"
      aria-label="打开 AI 助手"
      @click="toggle"
    >
      <AppIcon name="chat" :size="24" />
      <span v-if="agent.busy" class="agent-ball-dot" />
    </button>

    <aside v-else class="agent-panel" aria-label="AI 助手">
      <header class="agent-head">
        <div class="agent-title">
          <AppIcon name="chat" :size="17" />
          <span>AI 助手</span>
          <span v-if="agent.busy" class="pill">思考中…</span>
        </div>
        <div class="agent-head-actions">
          <label class="agent-switch" title="AI 操作页面跳转时是否自动跟随">
            <input
              type="checkbox"
              :checked="agent.autoNavigate"
              @change="agent.setAutoNavigate(($event.target as HTMLInputElement).checked)"
            />
            <span>自动跳转</span>
          </label>
          <button class="ghost" type="button" title="历史会话" @click="showList = !showList">
            <AppIcon name="more" :size="16" />
          </button>
          <button class="ghost" type="button" title="新对话" @click="newConversation">
            <AppIcon name="plus" :size="16" />
          </button>
          <button class="ghost" type="button" title="收起" @click="toggle">
            <AppIcon name="close" :size="16" />
          </button>
        </div>
      </header>

      <div v-if="showList" class="agent-list">
        <p v-if="agent.conversationsLoading" class="subtle">加载中…</p>
        <p v-else-if="!agent.conversations.length" class="subtle">还没有历史会话</p>
        <button
          v-for="c in agent.conversations"
          :key="c.thread_id"
          class="agent-list-item"
          :class="{ active: c.thread_id === agent.currentThread }"
          type="button"
          @click="openConversation(c.thread_id)"
        >
          <span class="agent-list-title">{{ c.title || '未命名会话' }}</span>
          <AppIcon name="close" :size="13" class="agent-list-del" @click.stop="agent.removeConversation(c.thread_id)" />
        </button>
      </div>

      <div ref="messagesEl" class="agent-messages">
        <p v-if="!agent.entries.length" class="agent-empty subtle">
          可以让我找视频、看评论、发私信。写操作我会先问你。
        </p>

        <template v-for="entry in agent.entries" :key="entry.key">
          <div v-if="entry.kind === 'user'" class="bubble user">{{ entry.text }}</div>

          <div v-else-if="entry.kind === 'assistant'" class="bubble assistant">
            {{ entry.text }}
          </div>

          <div
            v-else
            class="tool-chip"
            :class="entry.status"
            :title="entry.summary"
          >
            <span class="tool-dot" />
            <span class="tool-name">{{ entry.tool }}</span>
            <span class="tool-summary">{{ entry.summary }}</span>
          </div>
        </template>

        <div v-if="jumpedTo" class="agent-jumped">
          <AppIcon name="chevron-left" :size="13" />
          <span>已为你跳转到 {{ jumpedTo }}</span>
        </div>
      </div>

      <div v-if="agent.pending" class="agent-confirm">
        <p class="agent-confirm-title">需要你确认</p>
        <p v-for="call in agent.pending.calls" :key="call.call_id" class="agent-confirm-line">
          {{ call.preview }}
        </p>
        <div class="row">
          <button class="primary" type="button" @click="agent.resolveConfirm(true)">发送</button>
          <button type="button" @click="agent.resolveConfirm(false)">取消</button>
        </div>
      </div>

      <p v-if="agent.error" class="agent-error">{{ agent.error }}</p>

      <footer class="agent-input">
        <textarea
          v-model="draft"
          rows="1"
          :placeholder="agent.hasPending ? '请先处理上面的确认…' : '问点什么…（Enter 发送，Shift+Enter 换行）'"
          :disabled="agent.busy || agent.hasPending"
          @keydown="onKeydown"
        />
        <button class="primary" type="button" :disabled="!canSend" @click="submit">发送</button>
      </footer>
    </aside>
  </template>
</template>

<style scoped>
.agent-ball {
  position: fixed; right: 20px; bottom: 88px; z-index: 185;
  width: 52px; height: 52px; border-radius: var(--r-full);
  border: none; background: var(--pink-gradient); color: #fff;
  box-shadow: 0 6px 20px oklch(0.62 0.21 4 / 0.38);
}
.agent-ball:hover { transform: translateY(-2px); }
.agent-ball-dot {
  position: absolute; top: 8px; right: 8px;
  width: 9px; height: 9px; border-radius: var(--r-full);
  background: #fff; animation: agent-pulse 1.2s infinite;
}
@keyframes agent-pulse { 50% { opacity: 0.35; } }

.agent-panel {
  position: fixed; right: 20px; bottom: 88px; z-index: 190;
  width: 380px; max-height: min(640px, calc(100vh - 140px));
  display: flex; flex-direction: column;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-lg); box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.agent-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--border);
}
.agent-title { display: flex; align-items: center; gap: 7px; font-weight: 700; font-size: 0.9375rem; }
.agent-head-actions { display: flex; align-items: center; gap: 2px; }
.agent-head-actions button { padding: 7px; border-radius: var(--r-sm); min-height: 0; }
.agent-switch {
  display: flex; align-items: center; gap: 5px; margin: 0;
  font-size: 0.75rem; font-weight: 500; color: var(--muted);
}
.agent-switch input { width: auto; }

.agent-list {
  max-height: 190px; overflow-y: auto;
  border-bottom: 1px solid var(--border); padding: 6px;
  background: var(--bg);
}
.agent-list-item {
  width: 100%; justify-content: space-between; gap: 6px;
  background: transparent; border-color: transparent;
  padding: 9px 10px; font-weight: 500; font-size: 0.8125rem;
}
.agent-list-item.active { border-color: var(--pink-light); background: var(--surface); }
.agent-list-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agent-list-del { color: var(--faint); flex: none; }

.agent-messages {
  flex: 1; overflow-y: auto; padding: 14px;
  display: flex; flex-direction: column; gap: 9px;
}
.agent-empty { padding: 18px 6px; text-align: center; }

.bubble {
  max-width: 86%; padding: 9px 13px; border-radius: var(--r-md);
  font-size: 0.875rem; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
}
.bubble.user { align-self: flex-end; background: var(--pink-gradient); color: #fff; }
.bubble.assistant { align-self: flex-start; background: var(--bg); border: 1px solid var(--border); }

.tool-chip {
  align-self: flex-start; display: inline-flex; align-items: center; gap: 7px;
  max-width: 100%; padding: 5px 11px; border-radius: var(--r-full);
  background: var(--bg); border: 1px solid var(--border);
  font-size: 0.75rem; color: var(--muted);
}
.tool-chip .tool-name { font-weight: 600; color: var(--ink-soft); }
.tool-summary { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-dot { width: 7px; height: 7px; border-radius: var(--r-full); background: var(--faint); flex: none; }
.tool-chip.running .tool-dot { background: var(--pink-soft); animation: agent-pulse 1.2s infinite; }
.tool-chip.ok .tool-dot { background: var(--ok); }
.tool-chip.failed .tool-dot { background: var(--danger); }

.agent-jumped {
  display: flex; align-items: center; gap: 5px;
  font-size: 0.75rem; color: var(--muted); padding: 2px;
}

.agent-confirm {
  margin: 0 14px 10px; padding: 12px;
  border: 1px solid var(--pink-light); border-radius: var(--r-md);
  background: var(--pink-bg);
}
.agent-confirm-title { font-size: 0.75rem; font-weight: 700; color: var(--pink); margin-bottom: 6px; }
.agent-confirm-line { font-size: 0.875rem; margin-bottom: 6px; }

.agent-error {
  margin: 0 14px 10px; padding: 8px 11px; border-radius: var(--r-sm);
  background: oklch(0.97 0.02 22); color: var(--danger); font-size: 0.8125rem;
}

.agent-input {
  display: flex; gap: 8px; align-items: flex-end;
  padding: 11px 13px; border-top: 1px solid var(--border);
}
.agent-input textarea { flex: 1; resize: none; max-height: 110px; }
.agent-input button { flex: none; }

@media (max-width: 640px) {
  .agent-panel { right: 0; left: 0; bottom: 0; width: auto; max-height: 78vh; border-radius: var(--r-lg) var(--r-lg) 0 0; }
  .agent-ball { bottom: 78px; }
}
</style>
