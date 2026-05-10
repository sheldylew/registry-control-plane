const FALLBACK_TIME_ZONE = "America/Los_Angeles";

function resolveTimeZone(timeZone) {
  return timeZone || FALLBACK_TIME_ZONE;
}

export function formatDateTime(value, { timeZone, fallback = "Unknown" } = {}) {
  if (!value) {
    return fallback;
  }
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return fallback;
  }
  return target.toLocaleString("en-US", {
    timeZone: resolveTimeZone(timeZone),
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatShortDate(value, { timeZone, fallback = "Unknown" } = {}) {
  if (!value) {
    return fallback;
  }
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return fallback;
  }
  return target.toLocaleDateString("en-US", {
    timeZone: resolveTimeZone(timeZone),
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatRelativeTime(value, { timeZone, fallback = "Unknown" } = {}) {
  if (!value) {
    return fallback;
  }
  const target = new Date(value);
  const diffMs = Date.now() - target.getTime();
  if (Number.isNaN(diffMs)) {
    return fallback;
  }
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }
  return formatShortDate(value, { timeZone, fallback });
}
