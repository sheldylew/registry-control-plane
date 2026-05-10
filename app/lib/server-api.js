import { cookies } from "next/headers";

const internalApiBaseUrl =
  process.env.INTERNAL_API_BASE_URL || "http://api:8000";
const sessionCookieName = "rcr_session";

function buildCookieHeader(store) {
  return store
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
}

export async function apiFetch(path, options = {}) {
  const store = await cookies();
  const headers = new Headers(options.headers || {});
  const cookieHeader = buildCookieHeader(store);
  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }

  const response = await fetch(`${internalApiBaseUrl}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  return response;
}

export async function requireCurrentUser() {
  const store = await cookies();
  if (!store.has(sessionCookieName)) {
    return null;
  }

  const response = await apiFetch("/api/session/me");
  if (!response.ok) {
    return null;
  }
  const payload = await response.json();
  return payload.user;
}
