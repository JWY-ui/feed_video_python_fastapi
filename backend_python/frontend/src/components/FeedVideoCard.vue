<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { FeedVideoItem } from '../api/types'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{
  item: FeedVideoItem
  canLike: boolean
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-like', item: FeedVideoItem): void
  (e: 'open-comments', item: FeedVideoItem): void
}>()

function onToggle() { emit('toggle-like', props.item) }
function onComment() { emit('open-comments', props.item) }
</script>

<template>
  <div class="video-card">
    <RouterLink :to="`/video/${item.id}`" class="card-cover">
      <img :src="item.cover_url" :alt="item.title" loading="lazy" />
      <div class="play-icon">▶</div>
    </RouterLink>

    <div class="card-body">
      <RouterLink :to="`/video/${item.id}`" class="card-title">{{ item.title }}</RouterLink>

      <RouterLink :to="`/u/${item.author.id}`" class="card-author">
        <UserAvatar :username="item.author.username" :id="item.author.id" size="24" />
        <span class="author-name">{{ item.author.username }}</span>
      </RouterLink>

      <div class="card-meta subtle">
        {{ new Date(item.create_time * 1000).toLocaleDateString('zh-CN') }}
      </div>

      <div class="card-actions">
        <button
          class="action-btn"
          :class="{ liked: item.is_liked }"
          :disabled="!canLike || busy"
          @click="onToggle"
        >
          <span class="action-icon">{{ item.is_liked ? '❤️' : '🤍' }}</span>
          <span class="action-count">{{ item.likes_count }}</span>
        </button>
        <button class="action-btn" @click="onComment">
          <span class="action-icon">💬</span>
          <span class="action-label">评论</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.video-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 200ms var(--ease-out);
}
.video-card:hover {
  box-shadow: var(--shadow);
}

.card-cover {
  display: block; position: relative;
  aspect-ratio: 16/9;
  background: var(--faint);
  overflow: hidden;
}
.card-cover img {
  width: 100%; height: 100%; object-fit: cover;
  transition: transform 300ms var(--ease-out);
}
.video-card:hover .card-cover img { transform: scale(1.03); }

.play-icon {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  background: rgba(0,0,0,0.12);
  opacity: 0; transition: opacity 200ms;
  font-size: 32px; color: #fff;
  pointer-events: none;
}
.video-card:hover .play-icon { opacity: 1; }

.card-body {
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 8px;
}

.card-title {
  font-size: 15px; font-weight: 700; line-height: 1.3;
  color: var(--ink);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; text-decoration: none;
}
.card-title:hover { color: var(--pink); }

.card-author {
  display: flex; align-items: center; gap: 8px;
  text-decoration: none; color: var(--ink-soft);
}
.card-author:hover { color: var(--pink); }
.author-name { font-size: 13px; font-weight: 600; }

.card-actions {
  display: flex; gap: 6px;
  padding-top: 6px; border-top: 1px solid var(--bg);
}

.action-btn {
  flex: 1; border: none; background: var(--bg);
  border-radius: var(--r-sm); padding: 10px 8px;
  display: flex; align-items: center; justify-content: center; gap: 6px;
  cursor: pointer; font-size: 13px; font-weight: 600;
  color: var(--ink-soft); transition: all 140ms var(--ease-out);
}
.action-btn:hover { background: var(--pink-light); color: var(--pink); }
.action-btn:active { transform: scale(0.95); }
.action-btn:disabled { opacity: 0.4; }

.action-btn.liked { background: oklch(0.93 0.04 4); color: var(--pink); }
.action-icon { font-size: 15px; }
.action-count { min-width: 18px; text-align: left; }

/* Responsive */
@media (max-width: 640px) {
  .card-body { padding: 12px; gap: 6px; }
  .card-title { font-size: 14px; }
}
</style>
