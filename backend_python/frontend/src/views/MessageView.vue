<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { ApiError } from '../api/client'
import * as accountApi from '../api/account'
import * as messageApi from '../api/message'
import type { Account, DirectMessage } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useSocialStore } from '../stores/social'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const social = useSocialStore()
const toast = useToastStore()

const peerId = computed(() => { const raw = route.params.peerId; return typeof raw === 'string' ? Number(raw) : 0 })
const myId = computed(() => auth.claims?.account_id ?? 0)
const hasPeer = computed(() => Number.isFinite(peerId.value) && peerId.value > 0)
const listEl = ref<HTMLDivElement | null>(null)
const content = ref('')

const state = reactive({ loading: false, sending: false, error: '', peer: null as Account | null, messages: [] as DirectMessage[] })
const orderedMessages = computed(() => [...state.messages].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()))
const canSend = computed(() => content.value.trim().length > 0 && !state.sending && !!state.peer && peerId.value > 0)
const contactItems = computed(() => { const map = new Map<number, Account>(); for (const u of social.vloggers) map.set(u.id, u); for (const u of social.followers) map.set(u.id, u); return [...map.values()].filter(u => u.id !== myId.value) })
const contactLoading = computed(() => social.vloggersLoading || social.followersLoading)
const contactError = computed(() => social.vloggersError || social.followersError)

function formatTime(value: string) { const d = new Date(value); if (Number.isNaN(d.getTime())) return ''; return d.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }

async function scrollToBottom() { await nextTick(); if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight }

async function loadChat() {
  if (!auth.isLoggedIn) { await router.push({ path: '/account', query: { redirect: route.fullPath } }); return }
  if (!hasPeer.value) { await social.refreshMine(); state.loading = false; state.error = ''; state.peer = null; state.messages = []; return }
  if (!Number.isFinite(peerId.value) || peerId.value <= 0) { state.error = '无效的用户 id'; return }
  if (peerId.value === myId.value) { state.error = '请选择其他用户发送私信'; return }
  state.loading = true; state.error = ''
  try { const [peer, res] = await Promise.all([accountApi.findById(peerId.value), messageApi.listMessages(peerId.value)]); state.peer = peer; state.messages = res.messages ?? []; await scrollToBottom() }
  catch (e) { state.error = e instanceof ApiError ? e.message : String(e); state.peer = null; state.messages = [] }
  finally { state.loading = false }
}

async function send() {
  const text = content.value.trim(); if (!text || state.sending || !state.peer) return
  state.sending = true
  try { const msg = await messageApi.sendMessage(peerId.value, text); state.messages = [msg, ...state.messages]; content.value = ''; await scrollToBottom() }
  catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { state.sending = false }
}

async function goPeerProfile() { if (state.peer) await router.push(`/u/${state.peer.id}`) }
async function openChat(userId: number) { await router.push(`/messages/${userId}`) }

watch(() => route.params.peerId, () => { state.peer = null; state.messages = []; content.value = ''; void loadChat() })
onMounted(loadChat)
</script>

<template>
  <AppShell>
    <div class="chat-shell">
      <!-- Contact list -->
      <div v-if="!hasPeer" class="panel contact-panel">
        <div class="panel-head">
          <div><h2 style="margin:0">私信</h2><p class="subtle">选择关注或粉丝里的用户开始聊天。</p></div>
          <button class="ghost" :disabled="contactLoading" @click="social.refreshMine">刷新</button>
        </div>
        <div class="panel-body">
          <div v-if="contactLoading" class="state-msg">加载中…</div>
          <div v-else-if="contactError" class="state-msg err">{{ contactError }}</div>
          <div v-else-if="contactItems.length === 0" class="state-msg">暂无可聊天用户</div>
          <button v-for="user in contactItems" :key="user.id" class="contact-row" @click="openChat(user.id)">
            <UserAvatar :username="user.username" :id="user.id" :size="44" />
            <div style="flex:1;min-width:0"><div style="font-weight:700">@{{ user.username }}</div><div class="subtle mono">#{{ user.id }}</div></div>
            <span class="pill" style="font-size:12px">聊天</span>
          </button>
        </div>
      </div>

      <!-- Chat -->
      <div v-else class="panel chat-panel">
        <div class="panel-head" style="grid-template-columns:auto 1fr auto">
          <button class="ghost" style="font-size:22px;padding:4px 12px" @click="router.back()">‹</button>
          <button class="peer-btn" :disabled="!state.peer" @click="goPeerProfile">
            <UserAvatar :username="state.peer?.username ?? 'User'" :id="state.peer?.id ?? peerId" :size="38" />
            <span><strong>@{{ state.peer?.username ?? '加载中' }}</strong><br /><span class="subtle mono">#{{ state.peer?.id ?? peerId }}</span></span>
          </button>
          <button class="ghost" :disabled="state.loading" @click="loadChat">刷新</button>
        </div>

        <div ref="listEl" class="msg-list">
          <div v-if="state.loading" class="state-msg">加载中…</div>
          <div v-else-if="state.error" class="state-msg err">{{ state.error }}</div>
          <div v-else-if="orderedMessages.length === 0" class="state-msg">开始聊天吧</div>

          <div v-for="msg in orderedMessages" :key="msg.id" class="bubble-row" :class="{ mine: msg.from_id === myId }">
            <UserAvatar v-if="msg.from_id !== myId" :username="state.peer?.username ?? 'User'" :id="state.peer?.id ?? msg.from_id" :size="30" />
            <div class="bubble-wrap">
              <div class="bubble">{{ msg.content }}</div>
              <div class="bubble-time">{{ formatTime(msg.created_at) }}</div>
            </div>
          </div>
        </div>

        <div class="composer">
          <textarea v-model="content" placeholder="输入私信内容" :disabled="!!state.error || state.loading || state.sending" @keydown.enter.exact.prevent="send" />
          <button class="primary send-btn" :disabled="!canSend" @click="send">{{ state.sending ? '发送中' : '发送' }}</button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.chat-shell { display: grid; height: calc(100dvh - 56px - 56px); }

.panel { border: 1px solid var(--border); background: var(--surface); border-radius: var(--r-lg); overflow: hidden; display: grid; box-shadow: var(--shadow-sm); }
.contact-panel { grid-template-rows: auto 1fr; }
.chat-panel { grid-template-rows: auto 1fr auto; }

.panel-head { display: grid; gap: 10px; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg); }
.panel-head h2 { font-size: 18px; font-weight: 800; }
.panel-body { overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }

.contact-row { display: flex; align-items: center; gap: 12px; padding: 12px; border: 1px solid var(--border); border-radius: var(--r-md); background: var(--surface); cursor: pointer; font: inherit; text-align: left; transition: all 140ms; }
.contact-row:hover { background: var(--surface-hover); border-color: var(--pink-soft); }

.peer-btn { display: flex; align-items: center; gap: 10px; padding: 4px 10px; border-radius: var(--r-sm); border: none; background: none; cursor: pointer; font: inherit; text-align: left; }
.peer-btn:hover { background: var(--surface-hover); }

.msg-list { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.state-msg { text-align: center; color: var(--muted); padding: 32px 0; }
.state-msg.err { color: var(--danger); }

.bubble-row { display: grid; grid-template-columns: auto 1fr; gap: 10px; align-items: end; }
.bubble-row.mine { grid-template-columns: 1fr; justify-items: end; }
.bubble-wrap { max-width: min(68%, 560px); display: grid; gap: 4px; }
.bubble { padding: 10px 14px; border-radius: var(--r-md); line-height: 1.5; white-space: pre-wrap; word-break: break-word; font-size: 14px; background: var(--bg); }
.mine .bubble { background: var(--pink-bg); color: var(--ink); }
.bubble-time { font-size: 11px; color: var(--muted); }
.mine .bubble-time { text-align: right; }

.composer { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--border); background: var(--bg); align-items: end; }
.composer textarea { min-height: 44px; max-height: 120px; resize: vertical; }
.send-btn { min-width: 80px; height: 44px; }

@media (max-width: 640px) {
  .chat-shell { height: calc(100dvh - 56px - 56px); }
  .composer { grid-template-columns: 1fr; }
  .send-btn { width: 100%; }
}
</style>
