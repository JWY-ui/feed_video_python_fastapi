<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  username: string
  id?: number
  size?: string | number
  src?: string
}>(), {
  username: '?',
  size: 40,
})

function hashToHue(input: string) {
  let h = 0
  for (let i = 0; i < input.length; i++) h = (h * 31 + input.charCodeAt(i)) >>> 0
  return h % 360
}

const initial = computed(() => {
  const s = props.username.trim()
  return s ? s.slice(0, 1).toUpperCase() : '?'
})

const sizePx = computed(() => {
  const s = props.size
  return typeof s === 'number' ? `${s}px` : s
})

const bg = computed(() => {
  const seed = typeof props.id === 'number' ? String(props.id) : props.username
  const hue = hashToHue(seed || '0')
  return `linear-gradient(135deg, oklch(0.62 0.18 ${hue}), oklch(0.55 0.22 ${(hue + 40) % 360}))`
})
</script>

<template>
  <div class="avatar-wrap" :style="{ width: sizePx, height: sizePx }">
    <img v-if="src" :src="src" class="avatar-img" alt="" />
    <div v-else class="avatar-txt" :style="{ backgroundImage: bg }">{{ initial }}</div>
  </div>
</template>

<style scoped>
.avatar-wrap {
  border-radius: var(--r-full);
  overflow: hidden;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.avatar-img {
  width: 100%; height: 100%; object-fit: cover;
}
.avatar-txt {
  width: 100%; height: 100%;
  display: grid; place-items: center;
  color: #fff; font-weight: 800; font-size: 55%;
  letter-spacing: -0.01em;
  user-select: none;
}
</style>
