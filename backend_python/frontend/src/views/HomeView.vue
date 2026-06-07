<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon.vue'
import AppShell from '../components/AppShell.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import UserAvatar from '../components/UserAvatar.vue'
import type { FeedVideoItem } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useSocialStore } from '../stores/social'
import { useToastStore } from '../stores/toast'
import { useVideoFeed } from '../composables/useVideoFeed'
import { useVideoPlayer } from '../composables/useVideoPlayer'
import { useLikeFollow } from '../composables/useLikeFollow'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const social = useSocialStore()
const toast = useToastStore()

const { tab, following, currentState, loadFollowing, ensureTabLoaded, loadMoreIfNeeded } = useVideoFeed()
const scroller = ref<HTMLDivElement | null>(null)
const { muted, activeIndex, videoMap, setVideoRef, scrollToIndex, onScroll, playActive, toggleMute, togglePlayPause } = useVideoPlayer(scroller)

async function needLogin() {
  toast.error('请先登录')
  await router.push('/account')
}

const { likeBusy, followBusy, toggleLike, toggleFollow, share } = useLikeFollow(needLogin)

const drawerVideo = ref<FeedVideoItem | null>(null)
const drawerOpen = ref(false)

function openComments(item: FeedVideoItem) { drawerVideo.value = item; drawerOpen.value = true }
function closeDrawer() { drawerOpen.value = false; drawerVideo.value = null }

const searchQuery = ref((typeof route.query.q === 'string' ? route.query.q : ''))
const q = computed(() => searchQuery.value.trim().toLowerCase())
const filteredItems = computed(() => {
  const items = currentState.value.items
  if (!q.value) return items
  return items.filter((v) => v.title.toLowerCase().includes(q.value) || v.author.username.toLowerCase().includes(q.value))
})
function onSearchInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  searchQuery.value = val
  router.replace({ query: val ? { q: val } : {} })
}
const activeItem = computed(() => filteredItems.value[activeIndex.value] ?? null)
const visibleRange = computed(() => {
  const idx = activeIndex.value
  const len = filteredItems.value.length
  return { start: Math.max(0, idx - 1), end: Math.min(len - 1, idx + 1) }
})
const myAccountId = computed(() => auth.claims?.account_id ?? 0)

watch(activeItem, async () => {
  await nextTick()
  await playActive(activeItem.value?.id)
  await loadMoreIfNeeded(activeIndex.value)
})

watch(() => tab.value, async () => {
  activeIndex.value = 0
  videoMap.clear()
  if (scroller.value) scroller.value.scrollTop = 0
  await ensureTabLoaded()
  await nextTick()
  await playActive(activeItem.value?.id)
})

watch(() => q.value, async () => {
  activeIndex.value = 0
  if (scroller.value) scroller.value.scrollTop = 0
  await nextTick()
  await playActive(activeItem.value?.id)
})

watch(() => filteredItems.value.length, (len) => {
  if (len === 0) activeIndex.value = 0
  else if (activeIndex.value > len - 1) activeIndex.value = len - 1
})

watch(() => auth.isLoggedIn, async (v) => {
  if (tab.value === 'following' && v && following.items.length === 0) await loadFollowing(true)
})

async function onKeydown(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
  if (drawerOpen.value) return
  if (e.key === 'ArrowDown') { e.preventDefault(); scrollToIndex(activeIndex.value + 1, filteredItems.value.length) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); scrollToIndex(activeIndex.value - 1, filteredItems.value.length) }
  else if (e.key === ' ') { e.preventDefault(); togglePlayPause(activeItem.value?.id) }
  else if (e.key.toLowerCase() === 'm') { e.preventDefault(); toggleMute() }
  else if (e.key.toLowerCase() === 'c') { if (activeItem.value) { e.preventDefault(); openComments(activeItem.value) } }
}

const showHints = ref(true)

onMounted(async () => {
  await ensureTabLoaded()
  await nextTick()
  await playActive(activeItem.value?.id)
  window.addEventListener('keydown', onKeydown)
  setTimeout(() => { showHints.value = false }, 12000)
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <AppShell full>
    <div class="page">
      <div class="tabs">
        <div class="tabs-left">
          <button class="tab" :class="{ on: tab === 'recommend' }" type="button" @click="tab = 'recommend'">推荐</button>
          <button class="tab" :class="{ on: tab === 'following' }" type="button" @click="tab = 'following'">关注</button>
          <button class="tab" :class="{ on: tab === 'hot' }" type="button" @click="tab = 'hot'">点赞榜</button>
          <div class="tab-indicator" :class="tab" />
        </div>
        <div class="tabs-search">
          <AppIcon name="search" :size="15" class="search-icon" />
          <input
            class="search-input"
            type="text"
            placeholder="搜索视频或作者…"
            :value="searchQuery"
            @input="onSearchInput"
          />
          <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''; router.replace({ query: {} })" aria-label="清除搜索">
            <AppIcon name="close" :size="13" />
          </button>
        </div>
        <div class="tabs-right">
          <button class="tab-chip" type="button" @click="toggleMute">
            <AppIcon :name="muted ? 'mute' : 'unmute'" :size="15" />
            <span>{{ muted ? '静音' : '有声' }}</span>
          </button>
          <RouterLink class="tab-chip" :to="activeItem ? `/video/${activeItem.id}` : '/video'">
            <AppIcon name="play" :size="14" /><span>详情</span>
          </RouterLink>
        </div>
      </div>

      <div ref="scroller" class="scroller" @scroll="onScroll">
        <div v-if="currentState.loading && currentState.items.length === 0" class="center-hint">
          <div class="empty-state">
            <div class="skeleton" style="width:280px;height:16px;margin:0 auto" />
            <div class="skeleton" style="width:180px;height:16px;margin:8px auto 0" />
          </div>
        </div>
        <div v-else-if="currentState.error && currentState.items.length === 0" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">加载失败</p>
            <p class="empty-desc">{{ currentState.error }}</p>
            <button class="primary" style="margin-top:12px" @click="ensureTabLoaded()">重试</button>
          </div>
        </div>
        <div v-else-if="filteredItems.length === 0 && tab === 'following' && !auth.isLoggedIn" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">关注你喜欢的创作者</p>
            <p class="empty-desc">登录后关注创作者，这里会展示他们的最新视频</p>
            <RouterLink class="primary" style="margin-top:12px;display:inline-flex;text-decoration:none" to="/account">去登录</RouterLink>
          </div>
        </div>
        <div v-else-if="filteredItems.length === 0 && tab === 'following'" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">还没有关注任何人</p>
            <p class="empty-desc">去热榜发现有趣的创作者，点击关注即可在这里看到他们的视频</p>
            <button class="primary" style="margin-top:12px" @click="tab = 'hot'">探索热榜</button>
          </div>
        </div>
        <div v-else-if="filteredItems.length === 0" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">没有匹配内容</p>
            <p class="empty-desc">换个关键词试试，或者清空搜索</p>
          </div>
        </div>

        <section
          v-for="(item, idx) in filteredItems"
          :key="`${tab}-${item.id}`"
          v-show="idx >= visibleRange.start && idx <= visibleRange.end"
          class="slide"
          :class="{ active: idx === activeIndex }"
        >
          <div class="stage" @click="togglePlayPause(activeItem?.id)" @dblclick.prevent="toggleLike(item)">
            <video
              class="video"
              :ref="(el) => setVideoRef(item.id, el as HTMLVideoElement | null)"
              :src="item.play_url"
              :poster="item.cover_url"
              playsinline preload="metadata" loop
            />
            <div class="grad" />
            <div class="meta">
              <RouterLink class="author-link" :to="`/u/${item.author.id}`" @click.stop>
                <UserAvatar :username="item.author.username" :id="item.author.id" :size="34" />
                <span class="author-name">@{{ item.author.username }}</span>
              </RouterLink>
              <div class="title">{{ item.title }}</div>
              <div v-if="item.description" class="desc">{{ item.description }}</div>
            </div>
            <div class="actions">
              <button class="act" type="button" :class="{ liked: item.is_liked }" :disabled="!!likeBusy[String(item.id)]" @click.stop="toggleLike(item)">
                <AppIcon :name="item.is_liked ? 'heart-filled' : 'heart'" :size="22" />
                <span class="count">{{ item.likes_count }}</span>
              </button>
              <button class="act" type="button" @click.stop="openComments(item)">
                <AppIcon name="chat" :size="22" />
                <span class="count">评论</span>
              </button>
              <button
                v-if="!myAccountId || myAccountId !== item.author.id"
                class="act" type="button"
                :class="{ following: social.isFollowing(item.author.id) }"
                :disabled="!!followBusy[String(item.author.id)]"
                @click.stop="toggleFollow(item.author.id)">
                <AppIcon :name="social.isFollowing(item.author.id) ? 'check' : 'follow'" :size="22" />
                <span class="count">{{ social.isFollowing(item.author.id) ? '已关注' : '关注' }}</span>
              </button>
              <button class="act" type="button" @click.stop="share(item)">
                <AppIcon name="share" :size="20" />
                <span class="count">分享</span>
              </button>
            </div>
            <div class="hint" :class="{ fading: !showHints }">
              <span class="chip mono">↑ ↓ 切换</span>
              <span class="chip mono">空格 暂停</span>
              <span class="chip mono">M 静音</span>
              <span class="chip mono">C 评论</span>
            </div>
          </div>
        </section>
      </div>

      <CommentDrawer v-if="drawerOpen" :video="drawerVideo" @close="closeDrawer" />
    </div>
  </AppShell>
</template>

<style scoped>
.page { height: 100%; display: flex; flex-direction: column; background: var(--surface); }
.tabs { height: 52px; display: flex; align-items: center; gap: 0; padding: 0 14px; border-bottom: 1px solid var(--border); background: var(--surface); }
.tabs-left { display: flex; gap: 0; position: relative; }
.tab { border: none; background: none; color: var(--muted); padding: 14px 16px; cursor: pointer; font-weight: 600; font-size: 0.875rem; transition: color 160ms var(--ease-out); position: relative; }
.tab:hover { color: var(--ink-soft); }
.tab.on { color: var(--pink); }
.tab-indicator { position: absolute; bottom: 0; height: 2.5px; border-radius: 2px; background: var(--pink); transition: left 250ms var(--ease-out), width 250ms var(--ease-out); }
.tab-indicator.recommend { left: 4px; width: 44px; }
.tab-indicator.following { left: 72px; width: 44px; }
.tab-indicator.hot { left: 140px; width: 60px; }
.tabs-search { display: flex; align-items: center; gap: 6px; margin: 0 8px; flex: 1; max-width: 300px; background: var(--bg); border-radius: var(--r-full); padding: 6px 12px; border: 1px solid var(--border); }
.search-icon { color: var(--muted); flex-shrink: 0; }
.search-input {
  flex: 1; min-width: 0; background: none; border: none; outline: none;
  color: var(--ink); font-size: 0.8125rem; font-family: inherit;
  padding: 2px 0;
}
.search-input::placeholder { color: var(--muted); }
.search-clear {
  background: none; border: none; color: var(--muted); cursor: pointer;
  padding: 2px; display: grid; place-items: center;
}
.search-clear:hover { color: var(--ink-soft); }

.tabs-right { margin-left: auto; display: flex; gap: 8px; align-items: center; }
.tab-chip { display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border-radius: var(--r-full); border: 1px solid var(--border); background: var(--bg); color: var(--ink-soft); font-size: 0.75rem; font-weight: 500; cursor: pointer; text-decoration: none; transition: all 140ms var(--ease-out); }
.tab-chip:hover { border-color: var(--pink-soft); color: var(--pink); background: var(--surface); }

.scroller { flex: 1; min-height: 0; overflow-y: auto; scroll-snap-type: y mandatory; scroll-behavior: smooth; scrollbar-width: none; -ms-overflow-style: none; background: oklch(0.1 0.012 6); }
.scroller::-webkit-scrollbar { width: 0; height: 0; }
.center-hint { height: calc(100% - 60px); display: grid; place-items: center; color: var(--muted); }
.center-hint.bad { color: var(--danger); }
.empty-state { text-align: center; padding: 24px; max-width: 320px; }
.empty-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; color: var(--ink-soft); }
.empty-desc { font-size: 0.875rem; color: var(--muted); line-height: 1.5; }

.slide { height: 100%; scroll-snap-align: start; display: grid; place-items: center; animation: fadeSlideIn 350ms var(--ease-out); }

@keyframes fadeSlideIn {
  from { opacity: 0.6; transform: scale(0.97); }
  to { opacity: 1; transform: scale(1); }
}
.stage { width: 100%; height: calc(100dvh - 56px - 52px); position: relative; overflow: hidden; background: oklch(0.06 0.01 6); }
.video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.grad { position: absolute; inset: 0; background: linear-gradient(to top, oklch(0.06 0.012 6 / 0.85) 0%, oklch(0.06 0.012 6 / 0.15) 45%, transparent 70%); pointer-events: none; }
.meta { position: absolute; left: 16px; bottom: 18px; max-width: min(620px, calc(100% - 96px)); }
.author-link { display: inline-flex; align-items: center; gap: 10px; font-weight: 700; margin-bottom: 6px; text-decoration: none; color: oklch(0.95 0.005 6); }
.author-link:hover { text-decoration: none; }
.author-name { text-shadow: 0 2px 8px oklch(0 0 0 / 0.5); color: oklch(0.95 0.005 6); }
.stage .title { font-size: 16px; font-weight: 700; margin-bottom: 4px; color: oklch(0.95 0.005 6); }
.desc { color: oklch(0.85 0.005 6 / 0.8); font-size: 13px; line-height: 1.35; }
.actions { position: absolute; right: 12px; bottom: 24px; display: grid; gap: 12px; }
.act {
  display: grid; gap: 4px; justify-items: center;
  border: none; padding: 8px 4px; border-radius: var(--r-md);
  cursor: pointer; color: oklch(0.95 0.005 6);
  background: oklch(0.14 0.01 6 / 0.55);
  backdrop-filter: blur(10px);
  transition: all 160ms var(--ease-out);
  min-width: 56px;
}
.act:hover { background: oklch(0.22 0.015 6 / 0.6); color: oklch(0.98 0.002 6); transform: scale(1.06); }
.act:active { transform: scale(0.92); }
.act:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

.act.liked { color: var(--pink); }
.act.following { color: var(--pink-soft); }
.count { font-size: 11px; font-weight: 600; line-height: 1; white-space: nowrap; }

.hint { position: absolute; left: 14px; top: 14px; display: flex; gap: 6px; flex-wrap: wrap; }
.hint .chip { background: oklch(0.14 0.01 6 / 0.55); border-color: oklch(0.3 0.01 270 / 0.2); color: oklch(0.8 0.01 270); font-size: 11px; }

@media (max-width: 640px) {
  .stage { height: calc(100dvh - 56px - 52px); }
  .act { width: 56px; padding: 8px 4px; min-height: 44px; }
  .meta { left: 12px; bottom: 14px; }
  .actions { right: 6px; bottom: 14px; gap: 8px; }
}

@media (hover: none) {
  .hint { display: none; }
}

@media (max-width: 640px) and (orientation: landscape) {
  .stage { height: 100dvh; }
  .tabs { display: none; }
}
</style>
