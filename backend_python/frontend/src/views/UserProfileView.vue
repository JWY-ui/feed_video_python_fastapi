<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import AppShell from '../components/AppShell.vue'
import SlideDrawer from '../components/SlideDrawer.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { ApiError } from '../api/client'
import * as accountApi from '../api/account'
import * as socialApi from '../api/social'
import type { Account, Video } from '../api/types'
import * as videoApi from '../api/video'
import { useAuthStore } from '../stores/auth'
import { useSocialStore } from '../stores/social'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const social = useSocialStore()
const toast = useToastStore()

const userId = computed(() => Number(route.params.id))
const myId = computed(() => auth.claims?.account_id ?? 0)
const isMe = computed(() => myId.value > 0 && myId.value === userId.value)

const state = reactive({
  loading: false, error: '', user: null as Account | null, videos: [] as Video[],
  followers: [] as Account[], vloggers: [] as Account[], socialLoading: false, socialError: '',
})
const isFollowing = computed(() => auth.isLoggedIn ? social.isFollowing(userId.value) : false)

async function loadProfile() {
  if (!Number.isFinite(userId.value) || userId.value <= 0) { state.error = '无效的用户 id'; return }
  state.loading = true; state.error = ''
  try { const [u, vids] = await Promise.all([accountApi.findById(userId.value), videoApi.listByAuthorId(userId.value)]); state.user = u; state.videos = vids }
  catch (e) { state.error = e instanceof ApiError ? e.message : String(e); state.user = null; state.videos = [] }
  finally { state.loading = false }
  await loadSocialCounts()
}

async function loadSocialCounts() {
  state.socialError = ''; state.followers = []; state.vloggers = []
  if (!auth.isLoggedIn || !Number.isFinite(userId.value) || userId.value <= 0) return
  state.socialLoading = true
  try { const [fr, vr] = await Promise.all([socialApi.getAllFollowers(userId.value), socialApi.getAllVloggers(userId.value)]); state.followers = fr.followers; state.vloggers = vr.vloggers }
  catch (e) { state.socialError = e instanceof ApiError ? e.message : String(e) }
  finally { state.socialLoading = false }
}

async function toggleFollow() {
  if (isMe.value || !auth.isLoggedIn) { toast.error('请先登录'); await router.push('/account'); return }
  try { if (isFollowing.value) { await social.unfollow(userId.value); toast.info('已取关') } else { await social.follow(userId.value); toast.success('已关注') }; await loadSocialCounts() }
  catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
}

async function goMessage() {
  if (isMe.value || !auth.isLoggedIn) return
  await router.push(`/messages/${userId.value}`)
}

type ListTab = 'followers' | 'following'
const drawer = reactive({ open: false, tab: 'followers' as ListTab })
function openFollowers() { drawer.tab = 'followers'; drawer.open = true }
function openFollowing() { drawer.tab = 'following'; drawer.open = true }
function closeDrawer() { drawer.open = false }
const listTitle = computed(() => drawer.tab === 'followers' ? '粉丝' : '关注')
const listItems = computed(() => drawer.tab === 'followers' ? state.followers : state.vloggers)
async function goUser(id: number) { drawer.open = false; await router.push(`/u/${id}`) }
async function goVideo(videoId: number) { await router.push(`/video/${videoId}`) }

watch(() => route.params.id, async () => { drawer.open = false; await loadProfile() })
watch(() => auth.isLoggedIn, async () => { await loadSocialCounts() })
onMounted(loadProfile)
</script>

<template>
  <AppShell>
    <div class="card">
      <div class="row" style="justify-content:space-between;align-items:flex-start">
        <div class="row" style="gap:14px;align-items:center">
          <UserAvatar :username="state.user?.username ?? 'User'" :id="state.user?.id ?? userId" :size="64" />
          <div><h2 style="margin:0">@{{ state.user?.username ?? '-' }}</h2><p class="subtle mono">#{{ state.user?.id ?? userId }}</p></div>
        </div>
        <div class="row">
          <button v-if="isMe" class="ghost" @click="router.push('/account')">我的账号</button>
          <template v-else>
            <button class="ghost" :disabled="!state.user || state.loading" @click="goMessage">私信</button>
            <button class="primary" :disabled="!state.user || state.loading" @click="toggleFollow">{{ isFollowing ? '已关注' : '关注' }}</button>
          </template>
        </div>
      </div>

      <div v-if="state.loading" class="hint">加载中…</div>
      <div v-else-if="state.error" class="hint bad">{{ state.error }}</div>

      <div v-else class="stats" style="margin-top:16px">
        <button class="stat" :disabled="!auth.isLoggedIn || state.socialLoading" @click="openFollowers">
          <span class="stat-num">{{ auth.isLoggedIn ? (state.socialLoading ? '…' : state.followers.length) : '—' }}</span>
          <span class="stat-label">粉丝</span>
        </button>
        <button class="stat" :disabled="!auth.isLoggedIn || state.socialLoading" @click="openFollowing">
          <span class="stat-num">{{ auth.isLoggedIn ? (state.socialLoading ? '…' : state.vloggers.length) : '—' }}</span>
          <span class="stat-label">关注</span>
        </button>
        <div class="stat static"><span class="stat-num">{{ state.videos.length }}</span><span class="stat-label">作品</span></div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0">作品</h3>
      <div v-if="state.videos.length === 0" class="hint">暂无作品</div>
      <div v-else class="video-grid" style="margin-top:12px">
        <button v-for="v in state.videos" :key="v.id" class="vid-card" @click="goVideo(v.id)">
          <img :src="v.cover_url" :alt="v.title" loading="lazy" />
          <div class="vid-info"><div class="vid-title">{{ v.title }}</div><div class="subtle"><AppIcon name="heart" :size="13" style="vertical-align:middle;margin-right:2px" /> {{ v.likes_count }}</div></div>
        </button>
      </div>
    </div>

    <!-- Drawer -->
    <SlideDrawer :title="listTitle" :open="drawer.open" @close="closeDrawer">
      <div v-if="state.socialLoading" class="state-msg">加载中…</div>
      <div v-else-if="state.socialError" class="state-msg err">{{ state.socialError }}</div>
      <div v-else-if="listItems.length === 0" class="state-msg">暂无</div>
      <button v-for="u in listItems" :key="u.id" class="user-row" @click="goUser(u.id)">
        <UserAvatar :username="u.username" :id="u.id" :size="40" /><span>@{{ u.username }}</span>
      </button>
    </SlideDrawer>
  </AppShell>
</template>

<style scoped>
.stats { display: flex; gap: 8px; flex-wrap: wrap; }
.stat { flex:1; min-width:90px; border:1.5px solid var(--border); background:var(--surface); border-radius:var(--r-md); padding:14px 10px; cursor:pointer; display:grid; gap:4px; text-align:left; font:inherit; transition:all 160ms var(--ease-out); box-shadow:var(--shadow-sm); }
.stat:hover { border-color:var(--pink-soft); transform:translateY(-1px); box-shadow:var(--shadow); }
.stat.static { cursor:default; }
.stat.static:hover { transform:none; box-shadow:var(--shadow-sm); border-color:var(--border); }
.stat:disabled { opacity:0.5; cursor:not-allowed; }
.stat-num { font-size:20px; font-weight:900; color:var(--ink); }
.stat-label { font-size:12px; color:var(--muted); font-weight:500; }
.hint { color:var(--muted); padding:16px 0; }
.hint.bad { color:var(--danger); }

.video-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; }
.vid-card { border:1px solid var(--border); background:var(--surface); border-radius:var(--r-md); overflow:hidden; cursor:pointer; padding:0; text-align:left; box-shadow:var(--shadow-sm); transition:all 200ms var(--ease-out); }
.vid-card:hover { transform:translateY(-2px); box-shadow:var(--shadow); border-color:var(--pink-soft); }
.vid-card img { width:100%; aspect-ratio:9/12; object-fit:cover; background:var(--bg); }
.vid-info { padding:10px 12px; }
.vid-title { font-weight:700; font-size:13px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }

.state-msg { padding:24px 0; text-align:center; color:var(--muted); }
.state-msg.err { color:var(--danger); }
.user-row { display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:var(--r-sm);border:1px solid var(--border);background:var(--surface);cursor:pointer;font:inherit;text-align:left;transition:all 140ms; }
.user-row:hover { background:var(--surface-hover); border-color:var(--pink-soft); }
</style>
