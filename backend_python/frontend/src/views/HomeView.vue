<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon.vue'
import AppShell from '../components/AppShell.vue'
import type { FeedVideoItem } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useVideoFeed } from '../composables/useVideoFeed'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const { tab, following, currentState, loadFollowing, ensureTabLoaded, loadMoreIfNeeded } = useVideoFeed()

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

// Scroll-based infinite loading
const gridEl = ref<HTMLDivElement | null>(null)
const loadingMore = ref(false)
async function onScroll() {
  const el = gridEl.value
  if (!el || loadingMore.value) return
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 300
  if (nearBottom && currentState.value.hasMore) {
    loadingMore.value = true
    try {
      await loadMoreIfNeeded()
    } finally {
      loadingMore.value = false
    }
  }
}

watch(() => tab.value, async () => {
  if (gridEl.value) gridEl.value.scrollTop = 0
  await ensureTabLoaded()
})

watch(() => auth.isLoggedIn, async (v) => {
  if (tab.value === 'following' && v && following.items.length === 0) await loadFollowing(true)
})

async function goDetail(item: FeedVideoItem) {
  await router.push(`/video/${item.id}`)
}

onMounted(async () => {
  await ensureTabLoaded()
})
</script>

<template>
  <AppShell full>
    <div class="page">
      <!-- Tab bar -->
      <div class="tabs">
        <div class="tabs-left">
          <button class="tab" :class="{ on: tab === 'recommend' }" type="button" @click="tab = 'recommend'">推荐</button>
          <button class="tab" :class="{ on: tab === 'following' }" type="button" @click="tab = 'following'">关注</button>
          <button class="tab" :class="{ on: tab === 'hot' }" type="button" @click="tab = 'hot'">点赞榜</button>
          <div class="tab-indicator" :class="tab" />
        </div>
        <div class="tabs-search">
          <AppIcon name="search" :size="15" class="search-icon" />
          <input class="search-input" type="text" placeholder="搜索视频或作者…" :value="searchQuery" @input="onSearchInput" />
          <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''; router.replace({ query: {} })" aria-label="清除搜索">
            <AppIcon name="close" :size="13" />
          </button>
        </div>
      </div>

      <!-- Content area -->
      <div ref="gridEl" class="grid-scroll" @scroll="onScroll">
        <!-- Loading -->
        <div v-if="currentState.loading && currentState.items.length === 0" class="center-hint">
          <div class="empty-state">
            <div class="skeleton" style="width:280px;height:16px;margin:0 auto" />
            <div class="skeleton" style="width:180px;height:16px;margin:8px auto 0" />
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="currentState.error && currentState.items.length === 0" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">加载失败</p>
            <p class="empty-desc">{{ currentState.error }}</p>
            <button class="primary" style="margin-top:12px" @click="ensureTabLoaded()">重试</button>
          </div>
        </div>

        <!-- Empty: following, not logged in -->
        <div v-else-if="filteredItems.length === 0 && tab === 'following' && !auth.isLoggedIn" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">关注你喜欢的创作者</p>
            <p class="empty-desc">登录后关注创作者，这里会展示他们的最新视频</p>
            <RouterLink class="primary" style="margin-top:12px;display:inline-flex;text-decoration:none" to="/account">去登录</RouterLink>
          </div>
        </div>

        <!-- Empty: following, no follows -->
        <div v-else-if="filteredItems.length === 0 && tab === 'following'" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">还没有关注任何人</p>
            <p class="empty-desc">去热榜发现有趣的创作者，点击关注即可在这里看到他们的视频</p>
            <button class="primary" style="margin-top:12px" @click="tab = 'hot'">探索热榜</button>
          </div>
        </div>

        <!-- Empty: search no results -->
        <div v-else-if="filteredItems.length === 0 && q" class="center-hint">
          <div class="empty-state">
            <p class="empty-title">没有匹配内容</p>
            <p class="empty-desc">换个关键词试试</p>
          </div>
        </div>

        <!-- Video grid -->
        <div v-else class="video-grid">
          <div
            v-for="item in filteredItems"
            :key="`${tab}-${item.id}`"
            class="grid-card"
            @click="goDetail(item)"
          >
            <div class="card-img-wrap">
              <img :src="item.cover_url" :alt="item.title" loading="lazy" class="card-img" />
              <div class="card-overlay">
                <AppIcon name="play" :size="28" class="play-icon" />
              </div>
              <div class="card-duration" v-if="false">03:21</div>
            </div>
            <div class="card-info">
              <div class="card-title">{{ item.title }}</div>
              <div class="card-meta">
                <span class="card-author">@{{ item.author.username }}</span>
                <span class="card-stats">
                  <AppIcon name="heart" :size="13" />
                  {{ item.likes_count }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Load more -->
        <div v-if="currentState.items.length > 0" class="load-more">
          <template v-if="currentState.loading">
            <div class="skeleton" style="height:40px;max-width:300px;margin:0 auto" />
          </template>
          <template v-else-if="currentState.hasMore">
            <button
              class="ghost"
              style="margin:0 auto"
              :disabled="currentState.loading || loadingMore"
              @click="loadMoreIfNeeded()"
            >加载更多</button>
          </template>
          <p v-else class="subtle text-center">— 已经到底了 —</p>
        </div>
      </div>

    </div>
  </AppShell>
</template>

<style scoped>
.page { height: 100%; display: flex; flex-direction: column; background: var(--bg); }

/* ═══ Tab bar ═══ */
.tabs { display: flex; align-items: center; gap: 0; padding: 0 16px; height: 52px; border-bottom: 1px solid var(--border); background: var(--surface); flex-shrink: 0; }
.tabs-left { display: flex; gap: 0; position: relative; }
.tab { border: none; background: none; color: var(--muted); padding: 14px 16px; cursor: pointer; font-weight: 600; font-size: 0.875rem; transition: color 160ms var(--ease-out); position: relative; }
.tab:hover { color: var(--ink-soft); }
.tab.on { color: var(--pink); }
.tab-indicator { position: absolute; bottom: 0; height: 2.5px; border-radius: 2px; background: var(--pink); transition: left 250ms var(--ease-out), width 250ms var(--ease-out); }
.tab-indicator.recommend { left: 4px; width: 44px; }
.tab-indicator.following { left: 72px; width: 44px; }
.tab-indicator.hot { left: 140px; width: 60px; }
.tabs-search { display: flex; align-items: center; gap: 6px; margin-left: auto; flex: 0 1 260px; background: var(--bg); border-radius: var(--r-full); padding: 6px 12px; border: 1px solid var(--border); }
.search-icon { color: var(--muted); flex-shrink: 0; }
.search-input { flex: 1; min-width: 0; background: none; border: none; outline: none; color: var(--ink); font-size: 0.8125rem; font-family: inherit; padding: 2px 0; }
.search-input::placeholder { color: var(--muted); }
.search-clear { background: none; border: none; color: var(--muted); cursor: pointer; padding: 2px; display: grid; place-items: center; }
.search-clear:hover { color: var(--ink-soft); }

/* ═══ Content ═══ */
.grid-scroll { flex: 1; overflow-y: auto; padding: 20px 24px; }

/* ═══ Grid ═══ */
.video-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.grid-card {
  background: var(--surface);
  border-radius: var(--r-md);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: all 200ms var(--ease-out);
}
.grid-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--pink-soft);
}

/* Card image */
.card-img-wrap {
  position: relative;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: var(--faint);
}
.card-img {
  width: 100%; height: 100%;
  object-fit: cover;
  transition: transform 300ms var(--ease-out);
}
.grid-card:hover .card-img { transform: scale(1.04); }

.card-overlay {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  background: rgba(0,0,0,0.08);
  opacity: 0; transition: opacity 200ms var(--ease-out);
}
.grid-card:hover .card-overlay { opacity: 1; }
.play-icon { color: #fff; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); }
.card-duration {
  position: absolute; right: 8px; bottom: 8px;
  background: rgba(0,0,0,0.7); color: #fff;
  font-size: 0.6875rem; font-weight: 600;
  padding: 3px 6px; border-radius: 4px;
}

/* Card info */
.card-info { padding: 10px 12px 12px; display: grid; gap: 6px; }
.card-title {
  font-size: 0.8125rem; font-weight: 700; line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; color: var(--ink);
}
.card-meta {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.card-author { font-size: 0.75rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.card-stats { font-size: 0.75rem; color: var(--muted); display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; flex-shrink: 0; }

/* ═══ Empty / Loading ═══ */
.center-hint { display: grid; place-items: center; min-height: 50vh; }
.empty-state { text-align: center; padding: 24px; max-width: 320px; }
.empty-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; color: var(--ink-soft); }
.empty-desc { font-size: 0.875rem; color: var(--muted); line-height: 1.5; }

.load-more { padding: 24px 0; display: grid; place-items: center; }

/* ═══ Responsive ═══ */
@media (max-width: 1200px) {
  .video-grid { grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .grid-scroll { padding: 16px 20px; }
}
@media (max-width: 900px) {
  .video-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .grid-scroll { padding: 12px 14px; }
  .card-info { padding: 8px 10px 10px; }
}
@media (max-width: 640px) {
  .video-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .grid-scroll { padding: 10px; }
  .tabs { padding: 0 10px; }
  .tab { padding: 12px 10px; font-size: 0.8125rem; }
  .tabs-search { flex: 1; max-width: none; }
  .card-img-wrap { aspect-ratio: 2 / 3; }
}

@media (hover: none) {
  .grid-card:hover { transform: none; box-shadow: none; border-color: var(--border); }
  .grid-card:hover .card-img { transform: none; }
  .card-overlay { opacity: 0.08; }
}
</style>
