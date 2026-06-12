/** Compact relative time, e.g. "just now", "4m", "2h", "3d". */
export function relativeTime(iso, { short = false } = {}) {
  if (!iso) return null;
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return null;

  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  const min = Math.floor(sec / 60);
  const hr = Math.floor(min / 60);
  const day = Math.floor(hr / 24);

  if (sec < 45) return short ? "now" : "just now";
  if (min < 60) return short ? `${min}m` : `${min}m ago`;
  if (hr < 24) return short ? `${hr}h` : `${hr}h ago`;
  if (day < 7) return short ? `${day}d` : `${day}d ago`;
  return short ? `${Math.floor(day / 7)}w` : `${Math.floor(day / 7)}w ago`;
}

/** Full timestamp for tooltips. */
export function absoluteTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
}
