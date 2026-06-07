<script setup lang="ts">
import { reactive, watch } from 'vue'
import { ApiError } from '../api/client'
import * as commentApi from '../api/comment'
import type { Comment, FeedVideoItem } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import AppIcon from './AppIcon.vue'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{ video: FeedVideoItem | null }>()
const emit = defineEmits<{ close: [] }>()

const auth = useAuthStore()
const toast = useToastStore()

const drawer = reactive({
  loading: false, error: '',
  comments: [] as Comment[], content: '',
})

// Auto-load comments when the drawer opens with a new video
watch(() => props.video?.id, (id) => {
  drawer.comments = []
  if (id) loadComments()
}, { immediate: true })

function needLogin() { toast.error('请先登录') }

function close() {
  drawer.comments = []; drawer.content = ''; drawer.error = ''
  emit('close')
}

async function loadComments() {
  if (!props.video) return
  drawer.loading = true; drawer.error = ''
  try { drawer.comments = await commentApi.listAll(props.video.id) }
  catch (e) { drawer.error = e instanceof ApiError ? e.message : String(e) }
  finally { drawer.loading = false }
}

async function publishComment() {
  if (!props.video) return
  if (!auth.isLoggedIn) return needLogin()
  const content = drawer.content.trim()
  if (!content) return
  drawer.loading = true; drawer.error = ''
  try {
    await commentApi.publish(props.video.id, content)
    drawer.content = ''; await loadComments(); toast.success('评论已发布')
  } catch (e) {
    drawer.error = e instanceof ApiError ? e.message : String(e)
    toast.error(drawer.error)
  } finally { drawer.loading = false }
}

function canDelete(c: Comment) {
  return !!auth.claims?.account_id && auth.claims.account_id === c.author_id
}

async function deleteComment(commentId: number) {
  if (!props.video || !auth.isLoggedIn) return needLogin()
  if (!window.confirm('删除这条评论？')) return
  drawer.loading = true; drawer.error = ''
  try { await commentApi.remove(commentId); await loadComments(); toast.info('评论已删除') }
  catch (e) {
    drawer.error = e instanceof ApiError ? e.message : String(e)
    toast.error(drawer.error)
  } finally { drawer.loading = false }
}

defineExpose({ loadComments })
</script>

<template>
  <div class="backdrop" @click.self="close">
    <div class="drawer">
      <div class="drawer-head">
        <h3 class="drawer-title">评论</h3>
        <button class="close-btn" type="button" @click="close" aria-label="关闭"><AppIcon name="close" :size="16" /></button>
      </div>

      <div class="drawer-body">
        <div v-if="drawer.loading" class="state-msg">加载中…</div>
        <div v-else-if="drawer.error" class="state-msg err">{{ drawer.error }}</div>
        <div v-else-if="drawer.comments.length === 0" class="state-msg">还没有评论，来说点什么吧</div>

        <div v-for="c in drawer.comments" :key="c.id" class="comment">
          <div class="comment-top">
            <UserAvatar :username="c.username" size="28" />
            <span class="comment-user">{{ c.username }}</span>
            <span class="comment-time">{{ new Date(c.created_at).toLocaleString('zh-CN') }}</span>
          </div>
          <div class="comment-body">{{ c.content }}</div>
          <button
            v-if="canDelete(c)"
            class="delete-btn" type="button"
            :disabled="drawer.loading" @click="deleteComment(c.id)"
          >删除</button>
        </div>
      </div>

      <div class="drawer-foot">
        <div class="input-row">
          <textarea
            v-model="drawer.content" placeholder="写下你的评论…"
            :disabled="drawer.loading" rows="2"
            @keydown.enter.exact.prevent="publishComment"
          />
          <button
            class="primary send-btn" type="button"
            :disabled="drawer.loading || !drawer.content.trim()"
            @click="publishComment"
          >发送</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.35);
  z-index: 120; display: grid; justify-items: end;
}
.drawer {
  width: min(400px, 100vw);
  height: 100dvh;
  background: var(--surface);
  display: grid; grid-template-rows: auto 1fr auto;
  box-shadow: -8px 0 40px rgba(0,0,0,0.08);
}

.drawer-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px; border-bottom: 1px solid var(--border);
}
.drawer-title { font-size: 16px; font-weight: 800; }
.close-btn {
  width: 32px; height: 32px; border-radius: var(--r-sm); border: none;
  background: var(--bg); color: var(--muted); cursor: pointer;
  font-size: 16px; display: grid; place-items: center;
}
.close-btn:hover { background: var(--surface-hover); color: var(--ink); }

.drawer-body {
  overflow-y: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px;
}
.state-msg { padding: 32px 0; text-align: center; color: var(--muted); font-size: 14px; }
.state-msg.err { color: var(--danger); }

.comment {
  padding: 14px; background: var(--bg); border-radius: var(--r-md);
}
.comment-top {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.comment-user { font-weight: 700; font-size: 13px; }
.comment-time { font-size: 12px; color: var(--muted); margin-left: auto; }
.comment-body { font-size: 14px; line-height: 1.5; color: var(--ink); white-space: pre-wrap; word-break: break-word; }
.delete-btn {
  margin-top: 8px; border: none; background: none; color: var(--muted);
  font-size: 12px; cursor: pointer; padding: 2px 0;
}
.delete-btn:hover { color: var(--danger); }

.drawer-foot {
  padding: 14px 18px; border-top: 1px solid var(--border);
  padding-bottom: calc(14px + env(safe-area-inset-bottom, 0));
}
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row textarea {
  flex: 1; min-height: 44px; resize: none;
  background: var(--bg); border: 1.5px solid var(--border);
  border-radius: var(--r-md); padding: 10px 12px;
  font: inherit; font-size: 14px; outline: none;
}
.input-row textarea:focus { border-color: var(--pink); }
.send-btn { flex-shrink: 0; padding: 10px 20px; }

@media (max-width: 640px) {
  .backdrop { justify-items: center; align-items: end; }
  .drawer {
    width: 100vw; height: min(70dvh, 500px);
    border-radius: var(--r-lg) var(--r-lg) 0 0;
    box-shadow: 0 -4px 30px rgba(0,0,0,0.1);
  }
}
</style>
