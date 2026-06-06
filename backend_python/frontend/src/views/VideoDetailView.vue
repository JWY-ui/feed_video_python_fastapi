<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { ApiError } from '../api/client'
import * as commentApi from '../api/comment'
import * as likeApi from '../api/like'
import type { Comment, Video } from '../api/types'
import * as videoApi from '../api/video'
import { useAuthStore } from '../stores/auth'
import { useSocialStore } from '../stores/social'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const social = useSocialStore()
const toast = useToastStore()

const id = computed(() => Number(route.params.id))

const state = reactive({
  loading: false, error: '',
  video: null as Video | null,
  isLiked: null as boolean | null, busy: false,
})

const muted = ref(true)
const videoEl = ref<HTMLVideoElement | null>(null)

const drawer = reactive({
  open: false, loading: false, error: '',
  comments: [] as Comment[], content: '',
})

async function needLogin() { toast.error('请先登录'); await router.push('/account') }

async function loadVideo() {
  if (!Number.isFinite(id.value) || id.value <= 0) { state.error = '无效的 video id'; return }
  state.loading = true; state.error = ''
  try { state.video = await videoApi.getDetail(id.value) }
  catch (e) { state.error = e instanceof ApiError ? e.message : String(e) }
  finally { state.loading = false }
}

async function loadIsLiked() {
  if (!auth.isLoggedIn) { state.isLiked = null; return }
  try { const res = await likeApi.isLiked(id.value); state.isLiked = res.is_liked }
  catch { state.isLiked = null }
}

async function play() {
  if (!videoEl.value) return
  videoEl.value.muted = muted.value
  try { await videoEl.value.play() } catch {}
}

function toggleMute() { muted.value = !muted.value; if (videoEl.value) videoEl.value.muted = muted.value; toast.info(muted.value ? '已静音' : '已取消静音') }
function togglePlayPause() { const v = videoEl.value; if (!v) return; if (v.paused) void v.play(); else v.pause() }

async function toggleLike() {
  if (!state.video || !auth.isLoggedIn) return needLogin()
  if (state.busy) return
  state.busy = true
  try {
    if (state.isLiked) { await likeApi.unlike(id.value); state.isLiked = false; state.video.likes_count = Math.max(0, state.video.likes_count - 1) }
    else { await likeApi.like(id.value); state.isLiked = true; state.video.likes_count += 1 }
  } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { state.busy = false }
}

async function toggleFollow() {
  if (!state.video || !auth.isLoggedIn || state.busy) return
  if (auth.claims?.account_id && auth.claims.account_id === state.video.author_id) return
  state.busy = true
  try {
    if (social.isFollowing(state.video.author_id)) { await social.unfollow(state.video.author_id); toast.info('已取关') }
    else { await social.follow(state.video.author_id); toast.success('已关注') }
  } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { state.busy = false }
}

async function share() {
  if (!state.video) return
  const url = `${location.origin}/video/${state.video.id}`
  try { await navigator.clipboard.writeText(url); toast.success('链接已复制') }
  catch { window.prompt('复制链接', url) }
}

function closeDrawer() { drawer.open = false; drawer.comments = []; drawer.content = ''; drawer.error = '' }

async function loadComments() {
  if (!state.video) return
  drawer.loading = true; drawer.error = ''
  try { drawer.comments = await commentApi.listAll(state.video.id) }
  catch (e) { drawer.error = e instanceof ApiError ? e.message : String(e) }
  finally { drawer.loading = false }
}

async function openComments() { drawer.open = true; drawer.content = ''; await loadComments() }

async function publishComment() {
  if (!state.video || !auth.isLoggedIn) return needLogin()
  const content = drawer.content.trim(); if (!content) return
  drawer.loading = true; drawer.error = ''
  try { await commentApi.publish(state.video.id, content); drawer.content = ''; await loadComments(); toast.success('评论已发布') }
  catch (e) { drawer.error = e instanceof ApiError ? e.message : String(e); toast.error(drawer.error) }
  finally { drawer.loading = false }
}

function canDeleteComment(c: Comment) { return !!auth.claims?.account_id && auth.claims.account_id === c.author_id }

async function deleteComment(commentId: number) {
  if (!state.video || !auth.isLoggedIn) return needLogin()
  if (!window.confirm('确认删除这条评论？')) return
  drawer.loading = true; drawer.error = ''
  try { await commentApi.remove(commentId); await loadComments(); toast.info('评论已删除') }
  catch (e) { drawer.error = e instanceof ApiError ? e.message : String(e); toast.error(drawer.error) }
  finally { drawer.loading = false }
}

watch(() => id.value, async () => { closeDrawer(); await loadVideo(); await loadIsLiked(); await nextTick(); await play() })
watch(() => auth.isLoggedIn, async () => { await loadIsLiked() })
onMounted(async () => { await loadVideo(); await loadIsLiked(); await nextTick(); await play() })
</script>

<template>
  <AppShell full>
    <div class="page">
      <div class="top">
        <RouterLink class="back-btn" to="/">← 返回推荐</RouterLink>
        <button class="chip" type="button" @click="toggleMute">{{ muted ? '静音' : '有声' }}</button>
      </div>

      <div class="wrap">
        <div v-if="state.loading" class="center-hint">加载中…</div>
        <div v-else-if="state.error" class="center-hint bad">{{ state.error }}</div>

        <div v-else-if="state.video" class="stage" @click="togglePlayPause">
          <video ref="videoEl" class="video" :src="state.video.play_url" :poster="state.video.cover_url" playsinline preload="metadata" loop />
          <div class="grad" />

          <div class="meta">
            <RouterLink class="author-link" :to="`/u/${state.video.author_id}`" @click.stop>
              <UserAvatar :username="state.video.username" :id="state.video.author_id" :size="34" />
              <span class="author-name">@{{ state.video.username }}</span>
            </RouterLink>
            <div class="title">{{ state.video.title }}</div>
            <div v-if="state.video.description" class="desc">{{ state.video.description }}</div>
            <div class="row" style="margin-top:8px">
              <a class="chip mono" :href="state.video.play_url" target="_blank" rel="noreferrer">play_url</a>
              <a class="chip mono" :href="state.video.cover_url" target="_blank" rel="noreferrer">cover_url</a>
            </div>
          </div>

          <div class="actions">
            <button class="act" type="button" :disabled="state.busy" @click.stop="toggleLike">
              <span class="icon" :class="{ liked: !!state.isLiked }">♥</span>
              <span class="count">{{ state.video.likes_count }}</span>
            </button>
            <button class="act" type="button" @click.stop="openComments">
              <span class="icon">💬</span><span class="count">评论</span>
            </button>
            <button v-if="!auth.claims?.account_id || auth.claims.account_id !== state.video.author_id" class="act" type="button" :disabled="state.busy" @click.stop="toggleFollow">
              <span class="icon">＋</span><span class="count">{{ social.isFollowing(state.video.author_id) ? '已关注' : '关注' }}</span>
            </button>
            <button class="act" type="button" @click.stop="share">
              <span class="icon">↗</span><span class="count">分享</span>
            </button>
          </div>

          <div class="hint">
            <span class="chip mono">点击 暂停/播放</span>
            <span class="chip mono">双击 点赞</span>
          </div>
        </div>
      </div>

      <!-- Inline comment drawer -->
      <div v-if="drawer.open" class="backdrop" @click.self="closeDrawer">
        <div class="drawer">
          <div class="drawer-head"><h3>评论</h3><button class="close-btn" @click="closeDrawer">✕</button></div>
          <div class="drawer-body">
            <div v-if="drawer.loading" class="state-msg">加载中…</div>
            <div v-else-if="drawer.error" class="state-msg err">{{ drawer.error }}</div>
            <div v-else-if="drawer.comments.length === 0" class="state-msg">暂无评论</div>
            <div v-for="c in drawer.comments" :key="c.id" class="comment">
              <div class="comment-top"><strong>{{ c.username }}</strong><span class="ctime">{{ new Date(c.created_at).toLocaleString('zh-CN') }}</span></div>
              <div class="comment-body">{{ c.content }}</div>
              <button v-if="canDeleteComment(c)" class="del-btn" :disabled="drawer.loading" @click="deleteComment(c.id)">删除</button>
            </div>
          </div>
          <div class="drawer-foot">
            <div class="input-row">
              <textarea v-model="drawer.content" placeholder="写下你的评论…" :disabled="drawer.loading" rows="2" @keydown.enter.exact.prevent="publishComment" />
              <button class="primary send-btn" :disabled="drawer.loading || !drawer.content.trim()" @click="publishComment">发送</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.page { height: 100%; display: flex; flex-direction: column; background: #000; }
.top { height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-bottom: 1px solid var(--border); background: var(--surface); }
.back-btn { color: var(--pink); font-weight: 700; text-decoration: none; font-size: 14px; }
.back-btn:hover { opacity: 0.8; }
.wrap { flex: 1; min-height: 0; display: grid; place-items: center; }
.center-hint { color: #eee; }
.center-hint.bad { color: var(--danger); }

.stage { width: min(980px, 100vw); height: calc(100dvh - 56px - 48px); position: relative; overflow: hidden; background: #000; }
.video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.grad { position: absolute; inset: 0; background: linear-gradient(to top, rgba(0,0,0,0.65), rgba(0,0,0,0.1) 45%, transparent 70%); pointer-events: none; }
.meta { position: absolute; left: 16px; bottom: 18px; max-width: min(620px, calc(100% - 96px)); }
.author-link { display: inline-flex; align-items: center; gap: 10px; font-weight: 700; margin-bottom: 6px; color: #fff; text-decoration: none; }
.author-name { color: #fff; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }
.stage .title { font-size: 16px; font-weight: 700; margin-bottom: 4px; color: #fff; }
.desc { color: rgba(255,255,255,0.8); font-size: 13px; }
.stage .chip { background: rgba(0,0,0,0.4); border-color: rgba(255,255,255,0.15); color: rgba(255,255,255,0.85); font-size: 11px; }
.actions { position: absolute; right: 10px; bottom: 18px; display: grid; gap: 10px; }
.act { width: 64px; border-radius: var(--r-md); border: 1px solid rgba(255,255,255,0.2); background: rgba(0,0,0,0.35); color: #fff; padding: 10px 6px; cursor: pointer; display: grid; gap: 4px; justify-items: center; backdrop-filter: blur(6px); }
.act:hover { background: rgba(255,255,255,0.15); transform: scale(1.05); }
.act:disabled { opacity: 0.5; transform: none; }
.icon { font-size: 22px; }
.icon.liked { color: var(--pink); filter: drop-shadow(0 0 6px oklch(0.62 0.21 4 / 0.5)); }
.count { font-size: 11px; }
.hint { position: absolute; left: 14px; top: 14px; display: flex; gap: 6px; }
.hint .chip { background: rgba(0,0,0,0.4); border-color: rgba(255,255,255,0.15); color: rgba(255,255,255,0.85); font-size: 11px; }

/* drawer */
.backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.35); z-index: 120; display: grid; justify-items: end; }
.drawer { width: min(400px, 100vw); height: 100dvh; background: var(--surface); display: grid; grid-template-rows: auto 1fr auto; box-shadow: -8px 0 40px rgba(0,0,0,0.08); }
.drawer-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; border-bottom: 1px solid var(--border); }
.drawer-head h3 { font-size: 16px; font-weight: 800; }
.close-btn { width: 32px; height: 32px; border-radius: var(--r-sm); border: none; background: var(--bg); color: var(--muted); cursor: pointer; font-size: 16px; display: grid; place-items: center; }
.drawer-body { overflow-y: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.state-msg { padding: 32px 0; text-align: center; color: var(--muted); font-size: 14px; }
.state-msg.err { color: var(--danger); }
.comment { padding: 14px; background: var(--bg); border-radius: var(--r-md); }
.comment-top { display: flex; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.ctime { font-size: 12px; color: var(--muted); margin-left: auto; }
.comment-body { font-size: 14px; line-height: 1.5; white-space: pre-wrap; }
.del-btn { margin-top: 8px; border: none; background: none; color: var(--muted); font-size: 12px; cursor: pointer; }
.del-btn:hover { color: var(--danger); }
.drawer-foot { padding: 14px 18px; border-top: 1px solid var(--border); padding-bottom: calc(14px + env(safe-area-inset-bottom, 0)); }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row textarea { flex: 1; min-height: 44px; resize: none; background: var(--bg); border: 1.5px solid var(--border); border-radius: var(--r-md); padding: 10px 12px; font: inherit; font-size: 14px; outline: none; }
.send-btn { flex-shrink: 0; padding: 10px 20px; }

@media (max-width: 640px) {
  .stage { height: calc(100dvh - 56px - 48px - 24px); border-radius: var(--r-md); }
  .backdrop { justify-items: center; align-items: end; }
  .drawer { width: 100vw; height: min(70dvh, 500px); border-radius: var(--r-lg) var(--r-lg) 0 0; }
}
</style>
