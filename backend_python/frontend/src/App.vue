<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'

import AgentPanel from './components/AgentPanel.vue'
import { useAgentStore } from './stores/agent'
import { useAuthStore } from './stores/auth'
import { useNotificationStore } from './stores/notifications'

const auth = useAuthStore()
const notifications = useNotificationStore()
const agent = useAgentStore()

/**
 * The notification SSE stream lives here on purpose.
 *
 * Every view wraps itself in AppShell, so putting the stream there would tear it
 * down and reconnect on every navigation -- losing events and reopening a
 * connection constantly. App.vue is mounted once for the life of the session.
 *
 * <AgentPanel /> is mounted here for the same reason: it must survive route
 * changes, because the agent navigates the app while a conversation is open.
 */
watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      notifications.connect()
    } else {
      notifications.disconnect()
      agent.reset()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  notifications.disconnect()
  agent.reset()
})
</script>

<template>
  <RouterView />
  <AgentPanel />
</template>
