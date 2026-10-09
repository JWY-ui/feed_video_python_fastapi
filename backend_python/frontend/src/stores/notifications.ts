import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError } from '../api/client'
import * as notificationApi from '../api/notification'
import { createNotificationStream, type NotificationStream } from '../api/notificationStream'
import type { Notification } from '../api/types'
import { useAuthStore } from './auth'

/**
 * Notification list + unread badge + the live SSE stream.
 *
 * The stream is started from App.vue (mounted once), NOT from AppShell -- every
 * view wraps itself in AppShell, so connecting there would tear the stream down
 * and rebuild it on each navigation.
 */
export const useNotificationStore = defineStore('notifications', () => {
  const auth = useAuthStore()

  const items = ref<Notification[]>([])
  const unread = ref(0)
  const loading = ref(false)
  const error = ref('')
  const connected = ref(false)

  let stream: NotificationStream | null = null

  const hasUnread = computed(() => unread.value > 0)

  function clear() {
    items.value = []
    unread.value = 0
    error.value = ''
    loading.value = false
    connected.value = false
  }

  async function refresh() {
    if (!auth.isLoggedIn) {
      clear()
      return
    }
    loading.value = true
    error.value = ''
    try {
      items.value = await notificationApi.listNotifications()
      unread.value = items.value.filter((n) => !n.is_read).length
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : String(e)
      items.value = []
    } finally {
      loading.value = false
    }
  }

  /** Cheap badge-only refresh, for reconciling after a failed optimistic update. */
  async function refreshUnread() {
    if (!auth.isLoggedIn) {
      unread.value = 0
      return
    }
    try {
      unread.value = (await notificationApi.unreadCount()).count
    } catch {
      /* keep the previous count rather than flashing a wrong one */
    }
  }

  async function markRead(id: number) {
    const item = items.value.find((n) => n.id === id)
    if (!item || item.is_read) return
    item.is_read = true
    unread.value = Math.max(0, unread.value - 1)
    try {
      await notificationApi.markRead(id)
    } catch {
      await refreshUnread()
    }
  }

  async function markAllRead() {
    if (unread.value === 0) return
    const previous = items.value.map((n) => n.is_read)
    items.value.forEach((n) => { n.is_read = true })
    unread.value = 0
    try {
      await notificationApi.markRead()
    } catch {
      items.value.forEach((n, i) => { n.is_read = previous[i] ?? n.is_read })
      await refreshUnread()
    }
  }

  /** A notification arrived over SSE. */
  function onPush(notification: Notification) {
    if (items.value.some((n) => n.id === notification.id)) return
    items.value.unshift(notification)
    if (!notification.is_read) unread.value += 1
  }

  function connect() {
    if (stream || !auth.isLoggedIn) return
    stream = createNotificationStream({
      onNotification: onPush,
      onStatus: (value) => { connected.value = value },
    })
    stream.start()
    void refresh()
  }

  function disconnect() {
    stream?.stop()
    stream = null
    clear()
  }

  return {
    items,
    unread,
    hasUnread,
    loading,
    error,
    connected,
    refresh,
    refreshUnread,
    markRead,
    markAllRead,
    connect,
    disconnect,
    clear,
  }
})
