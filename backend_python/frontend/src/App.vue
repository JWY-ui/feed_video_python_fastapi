<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useAuthStore } from './stores/auth'
import { useNotificationStore } from './stores/notifications'

const auth = useAuthStore()
const notifications = useNotificationStore()

/**
 * The notification SSE stream lives here on purpose.
 *
 * Every view wraps itself in AppShell, so putting the stream there would tear it
 * down and reconnect on every navigation -- losing events and reopening a
 * connection constantly. App.vue is mounted once for the life of the session.
 */
watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) notifications.connect()
    else notifications.disconnect()
  },
  { immediate: true },
)

onBeforeUnmount(() => notifications.disconnect())
</script>

<template>
  <RouterView />
</template>
