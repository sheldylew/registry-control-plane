export const FORM_NAME_MAX_LENGTH = 255;
export const FORM_EMAIL_MAX_LENGTH = 320;
export const FORM_DESCRIPTION_MAX_LENGTH = 2000;

export function normalizeTextInput(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function hasNonEmptyValue(value) {
  return normalizeTextInput(value).length > 0;
}

export function isValidUserEmail(value) {
  const email = normalizeTextInput(value);
  if (!email) {
    return false;
  }

  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function isValidPassword(value, minimumLength = 8) {
  return typeof value === "string" && value.length >= minimumLength && value.trim().length > 0;
}

export function isValidPublicOrigin(value) {
  const origin = normalizeTextInput(value);
  if (!origin) {
    return false;
  }

  try {
    const url = new URL(origin);
    return ["http:", "https:"].includes(url.protocol) && url.origin === origin.replace(/\/$/, "");
  } catch {
    return false;
  }
}

export function readApiErrorDetail(payload, fallbackMessage) {
  if (typeof payload?.detail === "string" && payload.detail.trim()) {
    return payload.detail;
  }

  if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
    const firstDetail = payload.detail[0];
    if (typeof firstDetail?.msg === "string" && firstDetail.msg.trim()) {
      return firstDetail.msg;
    }
  }

  return fallbackMessage;
}
