<script setup lang="ts">
defineProps<{
  name: 'home' | 'fire' | 'plus' | 'chat' | 'user' | 'heart' | 'heart-filled' | 'play' | 'close' | 'share' | 'follow' | 'mute' | 'unmute' | 'search' | 'chevron-down' | 'chevron-up' | 'chevron-left' | 'chevron-right' | 'check' | 'more'
  size?: number
}>()
</script>

<template>
  <svg
    :width="size ?? 20" :height="size ?? 20"
    viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round" stroke-linejoin="round"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- home -->
    <path v-if="name === 'home'" d="M3 12L12 3l9 9" /><path v-if="name === 'home'" d="M5 10v10a1 1 0 001 1h4v-5a2 2 0 014 0v5h4a1 1 0 001-1V10" />
    <!-- fire -->
    <path v-if="name === 'fire'" d="M12 21c4-2 6-5 6-8a6 6 0 00-8-5.6C8.5 5 6 7 6 11c0 3 2 6 6 10z" /><path v-if="name === 'fire'" d="M12 21c-1.5-1-3-3-3-5.5C9 13 10.5 11 12 9.5c1.5 1.5 3 3.5 3 6 0 2.5-1.5 4.5-3 5.5z" />
    <!-- plus -->
    <path v-if="name === 'plus'" d="M12 5v14M5 12h14" />
    <!-- chat / messages -->
    <path v-if="name === 'chat'" d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.5 8.5 0 01-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" />
    <!-- user -->
    <path v-if="name === 'user'" d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle v-if="name === 'user'" cx="12" cy="7" r="4" />
    <!-- heart -->
    <path v-if="name === 'heart'" d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
    <!-- heart-filled -->
    <path v-if="name === 'heart-filled'" d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" fill="currentColor" stroke="none" />
    <!-- play -->
    <polygon v-if="name === 'play'" points="6 4 20 12 6 20" fill="currentColor" stroke="none" />
    <!-- close / X -->
    <path v-if="name === 'close'" d="M18 6L6 18M6 6l12 12" />
    <!-- share -->
    <path v-if="name === 'share'" d="M18 8a3 3 0 100-6 3 3 0 000 6zM6 15a3 3 0 100-6 3 3 0 000 6zM18 22a3 3 0 100-6 3 3 0 000 6z" /><path v-if="name === 'share'" d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" />
    <!-- follow / user-plus -->
    <path v-if="name === 'follow'" d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle v-if="name === 'follow'" cx="8.5" cy="7" r="4" /><path v-if="name === 'follow'" d="M20 8v6M17 11h6" />
    <!-- mute -->
    <path v-if="name === 'mute'" d="M11 5L6 9H2v6h4l5 4V5z" /><path v-if="name === 'mute'" d="M23 9l-6 6M17 9l6 6" />
    <!-- unmute -->
    <path v-if="name === 'unmute'" d="M11 5L6 9H2v6h4l5 4V5z" /><path v-if="name === 'unmute'" d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07" />
    <!-- search -->
    <circle v-if="name === 'search'" cx="11" cy="11" r="8" /><path v-if="name === 'search'" d="M21 21l-4.3-4.3" />
    <!-- chevron-down -->
    <path v-if="name === 'chevron-down'" d="M6 9l6 6 6-6" />
    <!-- chevron-up -->
    <path v-if="name === 'chevron-up'" d="M18 15l-6-6-6 6" />
    <!-- chevron-left -->
    <path v-if="name === 'chevron-left'" d="M15 18l-6-6 6-6" />
    <!-- chevron-right -->
    <path v-if="name === 'chevron-right'" d="M9 18l6-6-6-6" />
    <!-- check -->
    <path v-if="name === 'check'" d="M20 6L9 17l-5-5" />
    <!-- more (horizontal dots) -->
    <circle v-if="name === 'more'" cx="12" cy="5" r="1.5" fill="currentColor" stroke="none" /><circle v-if="name === 'more'" cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle v-if="name === 'more'" cx="12" cy="19" r="1.5" fill="currentColor" stroke="none" />
  </svg>
</template>
