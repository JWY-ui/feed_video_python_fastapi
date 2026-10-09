<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import AppShell from '../components/AppShell.vue'
import type { Notification, NotificationType } from '../api/types'
import { useNotificationStore } from '../stores/notifications'
import { relativeTime } from '../utils/time'

const router = useRouter()
const notifications = useNotificationStore()

const items = computed(() => notifications.items)

/** type -> icon. Colours are assigned in CSS so the row reads at a glance. */
const ICONS: Record<NotificationType, 'heart' | 'chat' | 'follow' | 'bell'> = {
  like: 'heart',
  comment: 'chat',
  follow: 'follow',
  mention: 'bell',
}

/**
 * Where a row navigates to.
 * like/comment/mention carry a video_id; follow carries the follower's id
 * (the same value as sender_id).
 */
function targetOf(item: Notification): string | null {
  if (!item.target_id || item.target_id <= 0) return null
  return item.type === 'follow' ? `/u/${item.target_id}` : `/video/${item.target_id}`
}

async function openItem(item: Notification) {
  // Mark first so the row doesn't stay bold if navigation is slow.
  await notifications.markRead(item.id)
  const to = targetOf(item)
  if (to) await router.push(to)
}

onMounted(() => {
  // The SSE stream is started globally in App.vue; this just loads the backlog.
  void notifications.refresh()
})
</script>

<template>
  <AppShell>
    <div class="notif-shell">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 style="margin:0">通知</h2>
            <p class="subtle">
              <template v-if="notifications.unread > 0">{{ notifications.unread }} 条未读</template>
              <template v-else>暂无未读</template>
              <span v-if="notifications.connected" class="live-dot" title="实时推送已连接" />
            </p>
          </div>
          <button
            class="ghost"
            :disabled="notifications.unread === 0 || notifications.loading"
            @click="notifications.markAllRead()"
          >全部已读</button>
        </div>

        <div class="panel-body">
          <template v-if="notifications.loading && items.length === 0">
            <div v-for="i in 5" :key="i" class="skeleton" style="height:64px" />
          </template>
          <div v-else-if="notifications.error && items.length === 0" class="state-msg err">
            {{ notifications.error }}
          </div>
          <div v-else-if="items.length === 0" class="state-msg">
            还没有通知 — 有人点赞、评论、关注你时会出现在这里
          </div>
          <button
            v-for="item in items"
            :key="item.id"
            class="notif-row"
            :class="{ unread: !item.is_read }"
            @click="openItem(item)"
          >
            <span class="notif-icon" :class="`t-${item.type}`">
              <AppIcon :name="ICONS[item.type]" :size="18" />
            </span>
            <span class="notif-body">
              <span class="notif-text">{{ item.content || '你有一条新通知' }}</span>
              <span class="notif-time">{{ relativeTime(item.created_at) }}</span>
            </span>
            <span v-if="!item.is_read" class="notif-unread-dot" />
          </button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.notif-shell { height: 100%; display: grid; padding: 16px; }

.panel {
  border: 1px solid var(--border); background: var(--surface);
  border-radius: var(--r-lg); display: grid; grid-template-rows: auto 1fr;
  box-shadow: var(--shadow-sm); overflow: hidden; height: 100%;
}
.panel-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg);
}
.panel-head h2 { font-size: 18px; font-weight: 800; }
.panel-body { overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 6px; }

.state-msg { text-align: center; color: var(--muted); padding: 48px 16px; font-size: 14px; }
.state-msg.err { color: var(--danger); }

/* Live-push indicator: a small green dot next to the unread count. */
.live-dot {
  display: inline-block; width: 7px; height: 7px; margin-left: 6px;
  border-radius: var(--r-full); background: var(--ok); vertical-align: middle;
}

.notif-row {
  display: grid; grid-template-columns: 36px 1fr auto; align-items: center; gap: 12px;
  padding: 12px; border: 1px solid transparent; border-radius: var(--r-md);
  background: var(--surface); cursor: pointer; font: inherit; text-align: left;
  transition: background 140ms var(--ease-out), border-color 140ms var(--ease-out);
}
.notif-row:hover { background: var(--surface-hover); border-color: var(--border); }
.notif-row.unread { background: var(--pink-bg); }

.notif-icon {
  width: 36px; height: 36px; border-radius: var(--r-full);
  display: grid; place-items: center; flex-shrink: 0;
  background: var(--bg); color: var(--ink-soft);
}
.notif-icon.t-like { background: oklch(0.95 0.04 4); color: var(--pink); }
.notif-icon.t-follow { background: oklch(0.95 0.04 150); color: var(--ok); }
.notif-icon.t-mention { background: oklch(0.95 0.04 320); color: oklch(0.55 0.16 320); }

.notif-body { display: grid; gap: 3px; min-width: 0; }
.notif-text { font-size: 14px; color: var(--ink); line-height: 1.45; word-break: break-word; }
.notif-row.unread .notif-text { font-weight: 600; }
.notif-time { font-size: 12px; color: var(--muted); }

.notif-unread-dot {
  width: 8px; height: 8px; border-radius: var(--r-full);
  background: var(--pink); flex-shrink: 0;
}

@media (max-width: 640px) {
  .notif-shell { padding: 0; }
  .panel { border-radius: 0; border-left: none; border-right: none; }
}
</style>
