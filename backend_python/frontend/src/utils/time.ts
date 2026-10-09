/**
 * Server-time parsing.
 *
 * Every DateTime column in the backend stores a naive UTC wall clock, and the
 * repositories serialize those values without an offset -- so the API returns
 * "2026-06-05T08:58:13" for an instant that was 08:58:13 UTC.
 *
 * `new Date()` treats a date-time string without an offset as LOCAL time
 * (per ES2016+), so on a UTC+8 machine every timestamp rendered from the API was
 * 8 hours off. This is the same defect as the backend cursor bug, mirrored on
 * the client.
 *
 * Note the API is not perfectly consistent: values that go through a push
 * payload carry "+00:00" while values read back from MySQL do not. Appending
 * "Z" only when there is no existing offset handles both.
 */
export function parseServerTime(value: string): Date {
  if (!value) return new Date(NaN)
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasOffset ? value : `${value}Z`)
}

/** Compact relative time in Chinese, e.g. "刚刚" / "3 分钟前" / "2 天前". */
export function relativeTime(value: string): string {
  const date = parseServerTime(value)
  const ms = date.getTime()
  if (Number.isNaN(ms)) return ''

  const diff = Date.now() - ms
  if (diff < 0) return '刚刚'
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return date.toLocaleDateString()
}
