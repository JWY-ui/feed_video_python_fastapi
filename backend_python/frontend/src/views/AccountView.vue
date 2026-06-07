<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import AppShell from '../components/AppShell.vue'
import SlideDrawer from '../components/SlideDrawer.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { ApiError } from '../api/client'
import * as accountApi from '../api/account'
import * as likeApi from '../api/like'
import type { Video } from '../api/types'
import * as videoApi from '../api/video'
import { useAuthStore } from '../stores/auth'
import { useSocialStore } from '../stores/social'
import { useToastStore } from '../stores/toast'

const router = useRouter()
const auth = useAuthStore()
const social = useSocialStore()
const toast = useToastStore()
const busy = ref(false)
const loginErr = ref('')
const loginForm = reactive({ username: '', password: '' })

const me = computed(() => ({ id: auth.claims?.account_id ?? 0, username: auth.claims?.username ?? '' }))
const myVideos = reactive({ loading: false, error: '', items: [] as Video[] })
type VideoTab = 'works' | 'likes'
const videoTab = ref<VideoTab>('works')

let myVideosReq = 0
async function loadMyVideos() {
  const id = me.value.id
  if (!auth.isLoggedIn || !id) { myVideos.items = []; myVideos.error = ''; myVideos.loading = false; return }
  if (myVideos.loading) return
  const req = ++myVideosReq; myVideos.loading = true; myVideos.error = ''
  try { const vids = await videoApi.listByAuthorId(id); if (req !== myVideosReq) return; myVideos.items = vids }
  catch (e) { if (req !== myVideosReq) return; myVideos.error = e instanceof ApiError ? e.message : String(e); myVideos.items = [] }
  finally { if (req === myVideosReq) myVideos.loading = false }
}

const likedVideos = reactive({ loading: false, loaded: false, error: '', items: [] as Video[] })
let likedVideosReq = 0
async function loadLikedVideos() {
  if (!auth.isLoggedIn || !me.value.id) { likedVideosReq += 1; likedVideos.loading = false; likedVideos.loaded = false; likedVideos.error = ''; likedVideos.items = []; return }
  if (likedVideos.loading) return
  const req = ++likedVideosReq; likedVideos.loading = true; likedVideos.error = ''
  try { const vids = await likeApi.listMyLikedVideos(); if (req !== likedVideosReq) return; likedVideos.items = vids; likedVideos.loaded = true }
  catch (e) { if (req !== likedVideosReq) return; likedVideos.error = e instanceof ApiError ? e.message : String(e); likedVideos.items = []; likedVideos.loaded = true }
  finally { if (req === likedVideosReq) likedVideos.loading = false }
}

async function goVideo(id: number) { await router.push(`/video/${id}`) }
function openWorksVideos() { videoTab.value = 'works'; void loadMyVideos() }
function openLikedVideos() { videoTab.value = 'likes'; void loadLikedVideos() }

async function onLogin() {
  if (busy.value) return
  const username = loginForm.username.trim(); const password = loginForm.password.trim()
  if (!username || !password) { loginErr.value = !username ? '请输入用户名' : '请输入密码'; return }
  busy.value = true; loginErr.value = ''
  try { const res = await accountApi.login(username, password); auth.setTokens(res.token, res.refresh_token ?? ''); toast.success('登录成功'); await social.refreshMine(); await loadMyVideos() }
  catch (e) { loginErr.value = e instanceof ApiError ? e.message : String(e) }
  finally { busy.value = false }
}

async function goRegister() { await router.push('/account/register') }
async function goChangePassword() { await router.push('/account/change-password') }
async function goSettings() { await router.push('/settings') }

type ListTab = 'followers' | 'following'
const drawer = reactive({ open: false, tab: 'followers' as ListTab })
function openFollowers() { drawer.tab = 'followers'; drawer.open = true }
function openFollowing() { drawer.tab = 'following'; drawer.open = true }
function closeDrawer() { drawer.open = false }

const listTitle = computed(() => drawer.tab === 'followers' ? '粉丝' : '关注')
const listItems = computed(() => drawer.tab === 'followers' ? social.followers : social.vloggers)
const drawerLoading = computed(() => drawer.tab === 'followers' ? social.followersLoading : social.vloggersLoading)
const drawerError = computed(() => drawer.tab === 'followers' ? social.followersError : social.vloggersError)
const socialErrorHint = computed(() => social.followersError || social.vloggersError)

async function goUser(id: number) { drawer.open = false; await router.push(`/u/${id}`) }

watch(() => auth.isLoggedIn, (v) => {
  if (!v) { drawer.open = false; myVideosReq += 1; myVideos.loading = false; myVideos.items = []; myVideos.error = ''; likedVideosReq += 1; likedVideos.loading = false; likedVideos.loaded = false; likedVideos.items = []; likedVideos.error = ''; videoTab.value = 'works' }
})
watch(() => me.value.id, (id) => { if (auth.isLoggedIn && id) { void loadMyVideos(); void loadLikedVideos() } }, { immediate: true })
</script>

<template>
  <AppShell>
    <!-- Login -->
    <div v-if="!auth.isLoggedIn" class="login-wrap">
      <div class="login-card">
        <h2>登录</h2>
        <div class="vstack" style="margin-top:16px">
          <div>
            <label>用户名</label>
            <input v-model.trim="loginForm.username" autocomplete="username" placeholder="输入用户名"
              :class="{ 'input-err': loginErr && !loginForm.username }"
              @keydown.enter="onLogin" @input="loginErr = ''" />
            <span v-if="loginErr && !loginForm.username" class="field-err">请输入用户名</span>
          </div>
          <div>
            <label>密码</label>
            <input v-model.trim="loginForm.password" type="password" autocomplete="current-password" placeholder="输入密码"
              :class="{ 'input-err': loginErr && !loginForm.password }"
              @keydown.enter="onLogin" @input="loginErr = ''" />
            <span v-if="loginErr && !loginForm.password" class="field-err">请输入密码</span>
          </div>
          <button class="primary" :disabled="busy" @click="onLogin" style="width:100%;padding:14px;font-size:16px">登录</button>
          <p v-if="loginErr && loginForm.username && loginForm.password" class="field-err text-center">{{ loginErr }}</p>
        </div>
        <div class="row" style="justify-content:space-between;margin-top:16px">
          <button class="ghost" :disabled="busy" @click="goRegister">注册账号</button>
          <button class="ghost" :disabled="busy" @click="goChangePassword">修改密码</button>
        </div>
      </div>
    </div>

    <!-- Profile -->
    <template v-else>
      <div class="profile-card">
        <div class="profile-top">
          <UserAvatar :username="me.username" :id="me.id" :size="72" />
          <div style="flex:1;min-width:0">
            <h2 style="margin:0">@{{ me.username }}</h2>
            <p class="subtle mono">#{{ me.id }}</p>
          </div>
          <button class="ghost" @click="goSettings">设置</button>
        </div>

        <div class="stats">
          <button class="stat" :disabled="social.followersLoading" @click="openFollowers">
            <span class="stat-num">{{ social.followersLoading ? '…' : social.followerCount }}</span>
            <span class="stat-label">粉丝</span>
          </button>
          <button class="stat" :disabled="social.vloggersLoading" @click="openFollowing">
            <span class="stat-num">{{ social.vloggersLoading ? '…' : social.followingCount }}</span>
            <span class="stat-label">关注</span>
          </button>
          <button class="stat" :class="{ active: videoTab === 'works' }" @click="openWorksVideos">
            <span class="stat-num">{{ myVideos.loading ? '…' : myVideos.items.length }}</span>
            <span class="stat-label">作品</span>
          </button>
          <button class="stat" :class="{ active: videoTab === 'likes' }" @click="openLikedVideos">
            <span class="stat-num">{{ likedVideos.loading ? '…' : likedVideos.loaded ? likedVideos.items.length : '—' }}</span>
            <span class="stat-label">点赞</span>
          </button>
        </div>
        <div v-if="socialErrorHint" class="subtle" style="margin-top:8px">社交信息加载失败：{{ socialErrorHint }}</div>
      </div>

      <!-- Video grid -->
      <div class="card" style="margin-top:14px">
        <h3 style="margin:0">{{ videoTab === 'works' ? '作品' : '点赞视频' }}</h3>
        <template v-if="videoTab === 'works'">
          <div v-if="myVideos.loading" class="hint">加载中…</div>
          <div v-else-if="myVideos.error" class="hint bad">{{ myVideos.error }}</div>
          <div v-else-if="myVideos.items.length === 0" class="hint">暂无作品</div>
          <div v-else class="video-grid">
            <button v-for="v in myVideos.items" :key="v.id" class="vid-card" @click="goVideo(v.id)">
              <img :src="v.cover_url" :alt="v.title" loading="lazy" />
              <div class="vid-info"><div class="vid-title">{{ v.title }}</div><div class="subtle"><AppIcon name="heart" :size="13" style="vertical-align:middle;margin-right:2px" /> {{ v.likes_count }}</div></div>
            </button>
          </div>
        </template>
        <template v-else>
          <div v-if="likedVideos.loading" class="hint">加载中…</div>
          <div v-else-if="likedVideos.error" class="hint bad">{{ likedVideos.error }}</div>
          <div v-else-if="likedVideos.items.length === 0" class="hint">暂无点赞视频</div>
          <div v-else class="video-grid">
            <button v-for="v in likedVideos.items" :key="v.id" class="vid-card" @click="goVideo(v.id)">
              <img :src="v.cover_url" :alt="v.title" loading="lazy" />
              <div class="vid-info"><div class="vid-title">{{ v.title }}</div><div class="subtle"><AppIcon name="heart" :size="13" style="vertical-align:middle;margin-right:2px" /> {{ v.likes_count }}</div></div>
            </button>
          </div>
        </template>
      </div>
    </template>

    <!-- Drawer -->
    <SlideDrawer :title="listTitle" :open="drawer.open" @close="closeDrawer">
      <div v-if="drawerLoading" class="state-msg">加载中…</div>
      <div v-else-if="drawerError" class="state-msg err">{{ drawerError }}</div>
      <div v-else-if="listItems.length === 0" class="state-msg">暂无</div>
      <button v-for="u in listItems" :key="u.id" class="user-row" @click="goUser(u.id)">
        <UserAvatar :username="u.username" :id="u.id" :size="40" /><span>@{{ u.username }}</span>
      </button>
    </SlideDrawer>
  </AppShell>
</template>

<style scoped>
.login-wrap { display: grid; justify-items: center; align-content: start; padding: clamp(40px, 12vh, 120px) 16px 40px; }
.login-card { width: min(420px, 100%); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 28px 24px; box-shadow: var(--shadow); }
.login-card h2 { margin: 0; font-size: 22px; font-weight: 800; }
.input-err { border-color: var(--danger) !important; }
.field-err { display: block; font-size: 12px; color: var(--danger); margin-top: 4px; }

.profile-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 24px; box-shadow: var(--shadow-sm); }
.profile-top { display: flex; align-items: center; gap: 16px; }
.stats { display: flex; gap: 8px; margin-top: 20px; flex-wrap: wrap; }
.stat { flex: 1; min-width: 90px; border: 1px solid var(--border); background: var(--bg); border-radius: var(--r-md); padding: 14px 10px; cursor: pointer; display: grid; gap: 4px; text-align: left; font: inherit; }
.stat:hover { background: var(--pink-bg); border-color: var(--pink-soft); }
.stat.active { background: var(--pink-light); border-color: var(--pink); }
.stat:disabled { opacity: 0.5; cursor: not-allowed; }
.stat-num { font-size: 22px; font-weight: 900; }
.stat-label { font-size: 12px; color: var(--muted); }

.hint { color: var(--muted); padding: 16px 0; }
.hint.bad { color: var(--danger); }

.video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-top: 12px; }
.vid-card { border: 1px solid var(--border); background: var(--surface); border-radius: var(--r-md); overflow: hidden; cursor: pointer; padding: 0; text-align: left; box-shadow: var(--shadow-sm); transition: box-shadow 160ms; }
.vid-card:hover { box-shadow: var(--shadow); }
.vid-card img { width: 100%; aspect-ratio: 9/12; object-fit: cover; }
.vid-info { padding: 10px 12px; }
.vid-title { font-weight: 700; font-size: 13px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.state-msg { padding: 24px 0; text-align: center; color: var(--muted); }
.state-msg.err { color: var(--danger); }
.user-row { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: var(--r-md); border: 1px solid var(--border); background: var(--bg); cursor: pointer; font: inherit; text-align: left; }
.user-row:hover { background: var(--surface-hover); }
</style>
