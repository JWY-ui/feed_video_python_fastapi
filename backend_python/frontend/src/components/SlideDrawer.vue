<script setup lang="ts">
import AppIcon from './AppIcon.vue'

defineProps<{
  title: string
  open: boolean
}>()

defineEmits<{
  (e: 'close'): void
}>()
</script>

<template>
  <div v-if="open" class="backdrop" @click.self="$emit('close')">
    <div class="drawer">
      <div class="drawer-head">
        <h3 class="drawer-title">{{ title }}</h3>
        <button class="close-btn" type="button" @click="$emit('close')" aria-label="关闭"><AppIcon name="close" :size="16" /></button>
      </div>
      <div class="drawer-body">
        <slot />
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
  display: grid; grid-template-rows: auto 1fr;
  box-shadow: var(--shadow-lg);
}
.drawer-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px; border-bottom: 1px solid var(--border);
}
.drawer-title { font-size: 16px; font-weight: 800; margin: 0; }
.close-btn {
  width: 32px; height: 32px; border-radius: var(--r-sm); border: none;
  background: var(--bg); color: var(--muted); cursor: pointer;
  font-size: 16px; display: grid; place-items: center;
  transition: all 140ms var(--ease-out);
}
.close-btn:hover { background: var(--surface-hover); color: var(--ink); }
.drawer-body {
  overflow-y: auto; padding: 16px 18px;
  display: flex; flex-direction: column; gap: 8px;
}

/* Loading / error / empty states */
.state-msg { padding: 24px 0; text-align: center; color: var(--muted); font-size: 14px; }
.state-msg.err { color: var(--danger); }

/* User row (shared pattern for follower/following lists) */
.user-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: var(--r-md);
  border: 1px solid var(--border); background: var(--surface);
  cursor: pointer; font: inherit; text-align: left;
  transition: all 140ms var(--ease-out);
}
.user-row:hover { background: var(--surface-hover); border-color: var(--pink-soft); }

@media (max-width: 640px) {
  .backdrop { justify-items: center; align-items: end; }
  .drawer {
    width: 100vw; height: min(70dvh, 500px);
    border-radius: var(--r-lg) var(--r-lg) 0 0;
    box-shadow: 0 -4px 30px rgba(0,0,0,0.1);
  }
}
</style>
