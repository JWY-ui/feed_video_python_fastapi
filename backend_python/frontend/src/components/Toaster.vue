<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import { useToastStore } from '../stores/toast'

const toast = useToastStore()
</script>

<template>
  <div class="toast-wrap" aria-live="polite">
    <div v-for="t in toast.toasts" :key="t.id" class="toast" :class="t.type" @click="toast.remove(t.id)">
      <AppIcon :name="t.type === 'success' ? 'check' : t.type === 'error' ? 'close' : 'more'" :size="14" class="toast-icon-svg" />
      <span class="toast-msg">{{ t.message }}</span>
    </div>
  </div>
</template>

<style scoped>
.toast-wrap {
  position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
  display: grid; gap: 8px; z-index: 200;
  width: min(420px, calc(100vw - 32px));
  pointer-events: none;
}
.toast {
  pointer-events: auto; cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  border-radius: var(--r-md); padding: 14px 16px;
  background: var(--surface); border: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  animation: slideDown 300ms var(--ease-out);
}
.toast.success { background: oklch(0.97 0.03 150); border-color: oklch(0.88 0.06 150); }
.toast.error   { background: oklch(0.97 0.03 22); border-color: oklch(0.90 0.05 22); }
.toast.info    { background: oklch(0.97 0.02 4); border-color: oklch(0.90 0.04 4); }
.toast-icon-svg {
  width: 24px; height: 24px; border-radius: var(--r-full);
  background: var(--bg); flex-shrink: 0;
  display: grid; place-items: center;
}
.toast.success .toast-icon-svg { background: oklch(0.90 0.08 150); color: var(--ok); }
.toast.error   .toast-icon-svg { background: oklch(0.92 0.06 22); color: var(--danger); }
.toast.info    .toast-icon-svg { background: var(--pink-light); color: var(--pink); }
.toast-msg { font-size: 14px; line-height: 1.4; color: var(--ink); }

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-12px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
