<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import AppShell from '../components/AppShell.vue'
import FeedVideoCard from '../components/FeedVideoCard.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import { ApiError } from '../api/client'
import * as feedApi from '../api/feed'
import * as likeApi from '../api/like'
import type { FeedVideoItem } from '../api/types'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

type ListState<T = object> = {
  loading: boolean; error: string; items: FeedVideoItem[]; hasMore: boolean
} & T

const latest = reactive<ListState & { nextTime: number }>({
  loading: false, error: '', items: [], hasMore: false, nextTime: 0,
})
const hot = reactive<ListState & { nextLikes?: number; nextId?: number }>({
  loading: false, error: '', items: [], hasMore: false, nextLikes: undefined, nextId: undefined,
})
const following = reactive<ListState & { nextTime: number }>({
  loading: false, error: '', items: [], hasMore: false, nextTime: 0,
})

const tab = reactive({ active: 'latest' as 'latest' | 'hot' | 'following' })
const commentVideo = reactive<{ video: FeedVideoItem | null }>({ video: null })
const canLike = computed(() => auth.isLoggedIn)

async function loadLatest(reset: boolean) {
  latest.loading = true; latest.error = ''
  try {
    const res = await feedApi.listLatest({ limit: 10, latest_time: reset ? 0 : latest.nextTime })
    latest.hasMore = res.has_more
    latest.nextTime = res.next_time
    latest.items = reset ? res.video_list : latest.items.concat(res.video_list)
  } catch (e) { latest.error = e instanceof ApiError ? e.message : String(e) }
  finally { latest.loading = false }
}

async function loadHot(reset: boolean) {
  hot.loading = true; hot.error = ''
  try {
    const res = await feedApi.listLikesCount({
      limit: 10,
      likes_count_before: reset ? undefined : hot.nextLikes,
      id_before: reset ? undefined : hot.nextId,
    })
    hot.hasMore = res.has_more
    hot.nextLikes = res.next_likes_count_before
    hot.nextId = res.next_id_before
    hot.items = reset ? res.video_list : hot.items.concat(res.video_list)
  } catch (e) { hot.error = e instanceof ApiError ? e.message : String(e) }
  finally { hot.loading = false }
}

async function loadFollowing(reset: boolean) {
  following.loading = true; following.error = ''
  try {
    const res = await feedApi.listByFollowing({ limit: 10, latest_time: reset ? 0 : following.nextTime })
    following.hasMore = res.has_more
    following.nextTime = res.next_time
    following.items = reset ? res.video_list : following.items.concat(res.video_list)
  } catch (e) { following.error = e instanceof ApiError ? e.message : String(e) }
  finally { following.loading = false }
}

const current = computed(() => tab.active === 'hot' ? hot : tab.active === 'following' ? following : latest)

async function toggleLike(item: FeedVideoItem) {
  if (!auth.isLoggedIn) return
  try {
    if (item.is_liked) await likeApi.unlike(item.id)
    else await likeApi.like(item.id)
    item.is_liked = !item.is_liked
    item.likes_count = Math.max(0, item.likes_count + (item.is_liked ? 1 : -1))
  } catch (e) { /* toast in useLikeFollow */ }
}

function openComments(item: FeedVideoItem) {
  commentVideo.video = item
}

onMounted(() => { loadLatest(true); loadHot(true) })
watch(() => auth.isLoggedIn, (v) => {
  if (v && following.items.length === 0) loadFollowing(true)
})
</script>

<template>
  <AppShell>
    <!-- Tab bar -->
    <div class="feed-tabs">
      <button
        v-for="t in [
          { key: 'latest' as const, label: '最新' },
          { key: 'hot' as const, label: '热榜' },
          { key: 'following' as const, label: '关注' },
        ]"
        :key="t.key"
        class="feed-tab"
        :class="{ active: tab.active === t.key }"
        @click="tab.active = t.key"
      >{{ t.label }}</button>
    </div>

    <!-- Feed grid -->
    <div v-if="current.error" class="empty-msg err">{{ current.error }}</div>

    <div v-if="current.items.length > 0" class="feed-grid">
      <FeedVideoCard
        v-for="item in current.items"
        :key="`${tab.active}-${item.id}`"
        :item="item"
        :can-like="canLike"
        :busy="current.loading"
        @toggle-like="toggleLike"
        @open-comments="openComments"
      />
    </div>

    <div v-if="current.items.length === 0 && !current.loading" class="empty-msg">
      {{ tab.active === 'following' ? '还没有关注任何人，去看看热榜吧' : '暂无视频' }}
    </div>

    <!-- Load more -->
    <div class="load-more">
      <template v-if="current.loading">
        <div class="skeleton" style="height:40px;border-radius:var(--r-sm)" />
        <div class="skeleton" style="height:40px;border-radius:var(--r-sm);margin-top:8px" />
      </template>
      <button
        v-else-if="current.hasMore"
        class="ghost" style="width:100%"
        @click="
          tab.active === 'hot' ? loadHot(false)
          : tab.active === 'following' ? loadFollowing(false)
          : loadLatest(false)
        "
      >加载更多</button>
      <p v-else class="subtle text-center">— 已经到底了 —</p>
    </div>

    <!-- Comment drawer -->
    <CommentDrawer v-if="commentVideo.video" :video="commentVideo.video" @close="commentVideo.video = null" />
  </AppShell>
</template>

<style scoped>
.feed-tabs {
  display: flex; gap: 4px;
  padding: 12px 0 4px;
  position: sticky; top: 0; z-index: 10;
  background: var(--bg);
}
.feed-tab {
  border: none; background: none;
  padding: 10px 22px; border-radius: var(--r-full);
  font-weight: 600; font-size: 14px; color: var(--muted);
  cursor: pointer; transition: all 160ms var(--ease-out);
}
.feed-tab:hover { color: var(--ink); background: var(--surface-hover); }
.feed-tab.active {
  background: var(--pink-gradient);
  color: #fff; font-weight: 700;
  box-shadow: 0 2px 8px oklch(0.62 0.21 4 / 0.25);
}

.feed-grid {
  display: grid; gap: 14px;
  padding-top: 12px;
}

.load-more { margin-top: 20px; }

.empty-msg {
  padding: 60px 0; text-align: center;
  color: var(--muted); font-size: 15px;
}
.empty-msg.err { color: var(--danger); }

@media (min-width: 640px) {
  .feed-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}
</style>
