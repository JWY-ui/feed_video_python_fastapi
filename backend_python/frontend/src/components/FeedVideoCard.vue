<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { FeedVideoItem } from '../api/types'
import AppIcon from './AppIcon.vue'
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
      <div class="play-overlay"><AppIcon name="play" :size="28" /></div>
    </RouterLink>

    <div class="card-body">
      <RouterLink :to="`/video/${item.id}`" class="card-title">{{ item.title }}</RouterLink>

      <div class="card-meta-row">
        <RouterLink :to="`/u/${item.author.id}`" class="card-author">
          <UserAvatar :username="item.author.username" :id="item.author.id" size="24" />
          <span class="author-name">{{ item.author.username }}</span>
        </RouterLink>
        <span class="card-date subtle">{{ new Date(item.create_time * 1000).toLocaleDateString('zh-CN') }}</span>
      </div>

      <div class="card-actions">
        <button
          class="action-btn"
          :class="{ liked: item.is_liked }"
          :disabled="!canLike || busy"
          @click="onToggle"
        >
          <AppIcon :name="item.is_liked ? 'heart-filled' : 'heart'" :size="16" />
          <span class="action-num">{{ item.likes_count }}</span>
        </button>
        <button class="action-btn" @click="onComment">
          <AppIcon name="chat" :size="16" />
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

.play-overlay {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  background: rgba(0,0,0,0.15);
  color: #fff; opacity: 0;
  transition: opacity 200ms var(--ease-out);
  pointer-events: none;
}
.video-card:hover .play-overlay { opacity: 1; }

.card-body {
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
}

.card-title {
  font-size: 15px; font-weight: 700; line-height: 1.35;
  color: var(--ink);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; text-decoration: none;
}
.card-title:hover { color: var(--pink); }

.card-meta-row {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.card-author {
  display: flex; align-items: center; gap: 8px;
  text-decoration: none; color: var(--ink-soft);
  min-width: 0; flex: 1;
}
.card-author:hover { color: var(--pink); }
.author-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-date { font-size: 12px; white-space: nowrap; flex-shrink: 0; }

.card-actions {
  display: flex; gap: 8px;
  padding-top: 10px; border-top: 1px solid var(--bg);
}

.action-btn {
  display: inline-flex; align-items: center; gap: 5px;
  border: none; background: none;
  padding: 6px 10px; border-radius: var(--r-sm);
  cursor: pointer; font-size: 13px; font-weight: 600;
  color: var(--ink-soft); transition: all 140ms var(--ease-out);
}
.action-btn:hover { background: var(--pink-light); color: var(--pink); }
.action-btn:active { transform: scale(0.96); }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.action-btn.liked { color: var(--pink); }
.action-num { min-width: 16px; text-align: left; font-variant-numeric: tabular-nums; }
.action-label { font-size: 13px; }

/* Responsive */
@media (max-width: 640px) {
  .card-body { padding: 12px; gap: 8px; }
  .card-title { font-size: 14px; }
  .play-overlay { opacity: 0.15; }
}

@media (hover: none) {
  .video-card:hover .card-cover img { transform: none; }
  .video-card:hover .play-overlay { opacity: 0.15; }
}
</style>
