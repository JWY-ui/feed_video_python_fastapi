<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { ApiError } from '../api/client'
import * as feedApi from '../api/feed'
import * as likeApi from '../api/like'
import type { FeedVideoItem } from '../api/types'
import AppShell from '../components/AppShell.vue'
import FeedVideoCard from '../components/FeedVideoCard.vue'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'

const auth = useAuthStore()
const toast = useToastStore()
const canLike = computed(() => auth.isLoggedIn)

const state = reactive({
  loading: false, error: '', items: [] as FeedVideoItem[],
  hasMore: false, limit: 10, asOf: 0, nextOffset: 0,
})
const likeBusy = reactive<Record<string, boolean>>({})

async function loadHot(reset: boolean) {
  if (state.loading) return
  state.loading = true; state.error = ''
  try {
    const res = await feedApi.listByPopularity({ limit: state.limit, as_of: reset ? 0 : state.asOf, offset: reset ? 0 : state.nextOffset })
    state.hasMore = res.has_more; state.asOf = res.as_of; state.nextOffset = res.next_offset
    state.items = reset ? res.video_list : state.items.concat(res.video_list)
  } catch (e) { state.error = e instanceof ApiError ? e.message : String(e) }
  finally { state.loading = false }
}

async function toggleLike(item: FeedVideoItem) {
  if (!auth.isLoggedIn) { toast.error('请先登录'); return }
  const key = String(item.id); if (likeBusy[key]) return
  likeBusy[key] = true
  try {
    if (item.is_liked) await likeApi.unlike(item.id)
    else await likeApi.like(item.id)
    item.is_liked = !item.is_liked
    item.likes_count = Math.max(0, item.likes_count + (item.is_liked ? 1 : -1))
  } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { likeBusy[key] = false }
}

onMounted(async () => { await loadHot(true) })
</script>

<template>
  <AppShell>
    <div class="page">
      <div class="header">
        <div>
          <h2 style="margin:0">热榜</h2>
          <p class="subtle">按热度排序</p>
        </div>
        <div class="header-actions">
          <input v-model.number="state.limit" type="number" min="1" max="50" class="limit-input" :disabled="state.loading" />
          <button class="primary" :disabled="state.loading" @click="loadHot(true)">刷新</button>
          <button :disabled="state.loading || !state.hasMore" @click="loadHot(false)">加载更多</button>
        </div>
      </div>

      <div v-if="state.error" class="pill bad" style="margin-top:12px">错误：{{ state.error }}</div>

      <div v-if="state.items.length" class="rank-list">
        <div v-for="(item, idx) in state.items" :key="`hot-${item.id}`" class="rank-row">
          <div class="rank-num" :class="idx === 0 ? 'gold' : idx === 1 ? 'silver' : idx === 2 ? 'bronze' : ''">{{ idx + 1 }}</div>
          <FeedVideoCard :item="item" :can-like="canLike" :busy="!!likeBusy[String(item.id)]" @toggle-like="toggleLike" />
        </div>
      </div>

      <div v-if="state.loading" class="load-hint">
        <div class="skeleton" style="height:40px" />
      </div>
      <p v-else-if="!state.hasMore && state.items.length > 0" class="subtle text-center mt-md">— 已经到底了 —</p>
    </div>
  </AppShell>
</template>

<style scoped>
.page { padding-bottom: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.limit-input { width: 70px; }

.rank-list { display: grid; gap: 12px; }
.rank-row { display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: 12px; align-items: start; }
.rank-num {
  height: 48px; width: 48px; border-radius: var(--r-md);
  display: grid; place-items: center;
  font-weight: 900; font-size: 18px;
  background: var(--bg); color: var(--muted); border: 1px solid var(--border);
}
.rank-num.gold   { background: linear-gradient(135deg, #FFD700, #FFA000); color: #fff; border-color: transparent; box-shadow: 0 2px 8px rgba(255,165,0,0.3); }
.rank-num.silver { background: linear-gradient(135deg, #C0C0C0, #909090); color: #fff; border-color: transparent; }
.rank-num.bronze { background: linear-gradient(135deg, #CD7F32, #A0522D); color: #fff; border-color: transparent; }

.load-hint { margin-top: 16px; }
</style>
