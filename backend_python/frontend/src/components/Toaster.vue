<script setup lang="ts">
import { useToastStore } from '../stores/toast'

const toast = useToastStore()
</script>

<template>
  <div class="toast-wrap" aria-live="polite">
    <div v-for="t in toast.toasts" :key="t.id" class="toast" :class="t.type" @click="toast.remove(t.id)">
      <span class="toast-icon">{{ t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : '·' }}</span>
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
.toast.success { border-left: 3px solid var(--ok); }
.toast.error   { border-left: 3px solid var(--danger); }
.toast.info    { border-left: 3px solid var(--pink-soft); }
.toast-icon {
  width: 24px; height: 24px; border-radius: var(--r-full);
  display: grid; place-items: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.toast.success .toast-icon { background: oklch(0.95 0.04 150); color: var(--ok); }
.toast.error   .toast-icon { background: oklch(0.95 0.04 22); color: var(--danger); }
.toast.info    .toast-icon { background: var(--pink-light); color: var(--pink); }
.toast-msg { font-size: 14px; line-height: 1.4; color: var(--ink); }

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-12px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
