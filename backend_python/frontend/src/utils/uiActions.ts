/**
 * Readers for the `ui` instructions that tools attach to their results.
 *
 * Two layers of defence, on purpose:
 *   1. the backend builds `ui` in tool code -- the model cannot emit it, so
 *      prompt injection cannot steer the interface;
 *   2. these helpers re-validate every path anyway, in case a future tool
 *      forgets.
 *
 * Unknown actions are ignored (fail closed).
 *
 * Note there is deliberately no "run it now" function: the store collects
 * navigations across a whole turn and applies only the last one, so a turn that
 * touches three tools does not yank the user through three pages.
 */

export type UiAction = {
  action?: unknown
  to?: unknown
  level?: unknown
  text?: unknown
}

export type ToastRequest = {
  level: string
  text: string
}

/**
 * Accept only same-origin absolute paths.
 *
 * `//evil.com` is a protocol-relative URL -- browsers treat it as an external
 * host, so it must be rejected to prevent an open redirect.
 */
export function safePath(to: unknown): string | null {
  if (typeof to !== 'string') return null
  if (!to.startsWith('/') || to.startsWith('//')) return null
  return to
}

/** The last *safe* navigate instruction in this batch, or null. */
export function lastNavigation(actions: unknown): string | null {
  if (!Array.isArray(actions)) return null
  let target: string | null = null
  for (const action of actions as UiAction[]) {
    if (action?.action !== 'navigate') continue
    const path = safePath(action.to)
    if (path) target = path
  }
  return target
}

/** All well-formed toast instructions in this batch. */
export function toastsFrom(actions: unknown): ToastRequest[] {
  if (!Array.isArray(actions)) return []
  const out: ToastRequest[] = []
  for (const action of actions as UiAction[]) {
    if (action?.action !== 'toast') continue
    if (typeof action.text !== 'string' || !action.text) continue
    out.push({
      level: typeof action.level === 'string' ? action.level : 'info',
      text: action.text,
    })
  }
  return out
}
