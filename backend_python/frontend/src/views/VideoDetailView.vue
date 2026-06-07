<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon.vue'
import AppShell from '../components/AppShell.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { ApiError } from '../api/client'
import * as likeApi from '../api/like'
import type { FeedVideoItem, Video } from '../api/types'
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
const drawerVideo = ref<FeedVideoItem | null>(null)

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

function openComments() { if (state.video) { drawerVideo.value = state.video as unknown as FeedVideoItem } }
function closeDrawer() { drawerVideo.value = null }

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
            <button class="act" type="button" :class="{ liked: !!state.isLiked }" :disabled="state.busy" @click.stop="toggleLike">
              <AppIcon :name="state.isLiked ? 'heart-filled' : 'heart'" :size="22" />
              <span class="count">{{ state.video.likes_count }}</span>
            </button>
            <button class="act" type="button" @click.stop="openComments">
              <AppIcon name="chat" :size="21" /><span class="count">评论</span>
            </button>
            <button v-if="!auth.claims?.account_id || auth.claims.account_id !== state.video.author_id" class="act" type="button" :class="{ following: social.isFollowing(state.video.author_id) }" :disabled="state.busy" @click.stop="toggleFollow">
              <AppIcon :name="social.isFollowing(state.video.author_id) ? 'check' : 'follow'" :size="21" /><span class="count">{{ social.isFollowing(state.video.author_id) ? '已关注' : '关注' }}</span>
            </button>
            <button class="act" type="button" @click.stop="share">
              <AppIcon name="share" :size="19" /><span class="count">分享</span>
            </button>
          </div>

          <div class="hint">
            <span class="chip mono">点击 暂停/播放</span>
            <span class="chip mono">双击 点赞</span>
          </div>
        </div>
      </div>

      <CommentDrawer v-if="drawerVideo" :video="drawerVideo" @close="closeDrawer" />
    </div>
  </AppShell>
</template>

<style scoped>
.page { height: 100%; display: flex; flex-direction: column; background: var(--surface); }
.top { height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-bottom: 1px solid var(--border); background: var(--surface); }
.back-btn { color: var(--pink); font-weight: 700; text-decoration: none; font-size: 0.875rem; }
.back-btn:hover { opacity: 0.8; }
.wrap { flex: 1; min-height: 0; display: grid; place-items: center; background: #000; }
.center-hint { color: #999; }
.center-hint.bad { color: var(--danger); }

.stage { width: 100%; height: calc(100dvh - 56px - 48px); position: relative; overflow: hidden; background: oklch(0.06 0.01 6); }
.video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.grad { position: absolute; inset: 0; background: linear-gradient(to top, oklch(0.06 0.012 6 / 0.85), oklch(0.06 0.012 6 / 0.15) 45%, transparent 70%); pointer-events: none; }
.meta { position: absolute; left: 16px; bottom: 18px; max-width: min(620px, calc(100% - 96px)); }
.author-link { display: inline-flex; align-items: center; gap: 10px; font-weight: 700; margin-bottom: 6px; color: oklch(0.95 0.005 6); text-decoration: none; }
.author-name { color: oklch(0.95 0.005 6); text-shadow: 0 2px 8px oklch(0 0 0 / 0.5); }
.stage .title { font-size: 16px; font-weight: 700; margin-bottom: 4px; color: oklch(0.95 0.005 6); }
.desc { color: oklch(0.85 0.005 6 / 0.8); font-size: 13px; }
.stage .chip { background: oklch(0.14 0.01 6 / 0.55); border-color: oklch(0.3 0.01 270 / 0.2); color: oklch(0.8 0.01 270); font-size: 11px; }
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
.hint { position: absolute; left: 14px; top: 14px; display: flex; gap: 6px; }
.hint .chip { background: oklch(0.14 0.01 6 / 0.55); border-color: oklch(0.3 0.01 270 / 0.2); color: oklch(0.8 0.01 270); font-size: 11px; }

@media (max-width: 640px) {
  .stage { height: calc(100dvh - 56px - 48px - 24px); border-radius: var(--r-md); }
  .act { min-height: 44px; }
}

@media (hover: none) {
  .hint { display: none; }
}

@media (max-width: 640px) and (orientation: landscape) {
  .stage { height: 100dvh; }
}
</style>
