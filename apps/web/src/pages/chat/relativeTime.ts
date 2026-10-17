/** 会话行的相对时间：以调用方注入的 now 为基准，纯函数，展示口径稳定可测。 */
export function formatRelativeTime(iso: string, now: number): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const diff = now - then;
  if (diff < minute) return "刚刚";
  if (diff < hour) return Math.floor(diff / minute) + " 分钟前";
  if (diff < day) return Math.floor(diff / hour) + " 小时前";
  if (diff < 7 * day) return Math.floor(diff / day) + " 天前";
  return iso.slice(0, 10);
}
