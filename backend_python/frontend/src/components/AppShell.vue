<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useSocialStore } from '../stores/social'
import AppIcon from './AppIcon.vue'
import Toaster from './Toaster.vue'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{ full?: boolean }>()

const auth = useAuthStore()
const social = useSocialStore()
const router = useRouter()
const route = useRoute()

const isOnline = ref(navigator.onLine)
function onOnline() { isOnline.value = true }
function onOffline() { isOnline.value = false }
onMounted(() => { window.addEventListener('online', onOnline); window.addEventListener('offline', onOffline) })
onBeforeUnmount(() => { window.removeEventListener('online', onOnline); window.removeEventListener('offline', onOffline) })

watch(
  () => auth.isLoggedIn,
  (v) => { if (v) void social.refreshMine(); else social.clear() },
  { immediate: true },
)

const userLabel = computed(() => {
  if (!auth.isLoggedIn) return '登录'
  return auth.claims?.username ?? '我'
})

const tabs = computed(() => {
  const base = [
    { to: '/', label: '推荐', icon: 'home' as const },
    { to: '/hot', label: '热榜', icon: 'fire' as const },
    { to: '/video', label: '发布', icon: 'plus' as const },
    { to: '/messages', label: '私信', icon: 'chat' as const, auth: true },
    { to: '/account', label: '我的', icon: 'user' as const },
  ]
  return base.filter(t => !t.auth || auth.isLoggedIn)
})

function isTabActive(to: string) {
  if (to === '/') return route.path === '/' || route.path.startsWith('/feed')
  return route.path.startsWith(to)
}
</script>

<template>
  <div class="shell">
    <!-- Offline banner -->
    <div v-if="!isOnline" class="offline-bar">离线模式 — 部分功能不可用</div>

    <!-- Desktop sidebar -->
    <aside class="sidebar">
      <RouterLink class="logo" to="/">
        <AppIcon name="play" :size="14" class="logo-icon" />
        <span class="logo-text">ShortVideo</span>
      </RouterLink>

      <nav class="side-nav">
        <RouterLink
          v-for="t in tabs" :key="t.to"
          :to="t.to"
          class="side-link"
          :class="{ active: isTabActive(t.to) }"
        >
          <AppIcon :name="t.icon" :size="20" class="side-icon" />
          <span>{{ t.label }}</span>
        </RouterLink>
      </nav>

      <div class="side-foot">
        <div class="side-user" @click="router.push('/account')">
          <UserAvatar :username="userLabel" size="32" />
          <span class="side-username">{{ userLabel }}</span>
          <span class="side-dot" :class="auth.isLoggedIn ? 'on' : 'off'" />
        </div>
      </div>
    </aside>

    <!-- Main content -->
    <div class="main-area">
      <div class="content" :class="props.full ? 'full' : 'scroll'">
        <template v-if="props.full">
          <slot />
        </template>
        <template v-else>
          <div class="container">
            <slot />
          </div>
        </template>
      </div>
    </div>

    <!-- Mobile bottom tab bar -->
    <nav class="bottom-tabs">
      <RouterLink
        v-for="t in tabs" :key="t.to"
        :to="t.to"
        class="tab-item"
        :class="{ active: isTabActive(t.to) }"
      >
        <AppIcon :name="t.icon" :size="22" class="tab-icon" />
        <span class="tab-label">{{ t.label }}</span>
      </RouterLink>
    </nav>

    <Toaster />
  </div>
</template>

<style scoped>
/* ═══ Offline banner ═══ */
.offline-bar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 300;
  padding: 10px 16px; text-align: center;
  background: oklch(0.92 0.06 80); color: oklch(0.45 0.12 80);
  font-size: 13px; font-weight: 600;
}

/* ═══ Shell layout ═══ */
.shell {
  height: 100dvh;
  display: grid;
  grid-template-columns: 220px 1fr;
  background: var(--bg);
}

/* ═══ Sidebar (desktop) ═══ */
.sidebar {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--surface);
  padding: 16px 12px;
  gap: 8px;
  height: 100dvh;
}

.logo {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 10px; border-radius: var(--r-md);
  background: var(--pink-gradient);
  color: #fff;
  font-weight: 900; font-size: 17px;
  letter-spacing: -0.01em;
  text-decoration: none;
  box-shadow: 0 2px 10px oklch(0.62 0.21 4 / 0.22);
}
.logo-icon { color: #fff; flex-shrink: 0; }
.logo-text { flex: 1; }

.side-nav {
  display: grid; gap: 4px;
  flex: 1;
}

.side-link {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 10px; border-radius: var(--r-sm);
  color: var(--ink-soft); font-size: 14px; font-weight: 500;
  text-decoration: none;
  transition: all 140ms var(--ease-out);
}
.side-link:hover { background: var(--surface-hover); color: var(--ink); }
.side-link.active {
  background: var(--pink-light); color: var(--pink); font-weight: 700;
}
.side-icon { flex-shrink: 0; opacity: 0.7; }
.side-link.active .side-icon { opacity: 1; }

.side-foot {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.side-user {
  display: flex; align-items: center; gap: 10px;
  padding: 10px; border-radius: var(--r-sm);
  cursor: pointer; transition: background 120ms;
}
.side-user:hover { background: var(--surface-hover); }
.side-username { font-size: 14px; font-weight: 600; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.side-dot { width: 8px; height: 8px; border-radius: var(--r-full); flex-shrink: 0; }
.side-dot.on  { background: var(--ok); box-shadow: 0 0 0 3px oklch(0.58 0.16 150 / 0.15); }
.side-dot.off { background: var(--faint); }

/* ═══ Main area ═══ */
.main-area {
  display: flex; flex-direction: column;
  min-width: 0; height: 100dvh;
}

.content { flex: 1; min-height: 0; }
.content.scroll { overflow-y: auto; padding-bottom: env(safe-area-inset-bottom, 0); }
.content.full { overflow: hidden; }

/* ═══ Bottom tabs (mobile) ═══ */
.bottom-tabs {
  display: none;
  height: 56px;
  border-top: 1px solid var(--border);
  background: var(--surface);
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  padding: 0 4px;
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.tab-item {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  color: var(--muted); text-decoration: none;
  font-size: 13px; font-weight: 500;
  position: relative;
}
.tab-item.active {
  color: var(--pink); font-weight: 700;
}
.tab-icon { opacity: 0.65; }
.tab-item.active .tab-icon { opacity: 1; }

/* ═══ Responsive ═══ */
@media (max-width: 768px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 56px;
  }
  .sidebar { display: none; }
  .bottom-tabs { display: grid; }
  .content.scroll { padding-bottom: 12px; }
}
</style>
