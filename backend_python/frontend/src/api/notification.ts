import { postJson } from './client'
import { normalizeNotificationList } from './normalize'
import type { MessageResponse, Notification, UnreadCountResponse } from './types'

/**
 * The backend returns a BARE ARRAY here (this endpoint has no response_model),
 * unlike every other list endpoint which wraps its payload as `{ xxx: [] }`.
 */
export async function listNotifications(): Promise<Notification[]> {
  const res = await postJson<Notification[]>('/notification/list', {}, { authRequired: true })
  return normalizeNotificationList(res)
}

export function unreadCount() {
  return postJson<UnreadCountResponse>('/notification/unreadCount', {}, { authRequired: true })
}

/** Omit `id` to mark everything read (`id` absent -> backend treats it as null). */
export function markRead(id?: number) {
  return postJson<MessageResponse>('/notification/markRead', id ? { id } : {}, { authRequired: true })
}
