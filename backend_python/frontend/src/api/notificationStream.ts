import { createSseStream } from './sseStream'
import type { Notification } from './types'

/**
 * The notification feed's live stream.
 *
 * The transport (frame parsing, backoff, 401-refresh) lives in sseStream.ts and
 * is shared with the agent panel -- this module is only the notification-specific
 * part: which URL to open and what to do with each frame.
 */

export type NotificationStreamHandlers = {
  onNotification: (notification: Notification) => void
  /** Fires true once the stream is live, false when it drops. */
  onStatus?: (connected: boolean) => void
}

export type NotificationStream = {
  start: () => void
  stop: () => void
}

export function createNotificationStream(
  handlers: NotificationStreamHandlers,
): NotificationStream {
  const stream = createSseStream(
    () => ({
      path: '/notification/stream',
      init: { method: 'GET' },
    }),
    {
      onEvent(payload) {
        const frame = payload as { event?: string; notification?: Notification }
        if (frame?.event === 'notification' && frame.notification) {
          handlers.onNotification(frame.notification)
        }
      },
      onStatus: (connected) => handlers.onStatus?.(connected),
    },
  )

  return { start: stream.start, stop: stream.stop }
}
