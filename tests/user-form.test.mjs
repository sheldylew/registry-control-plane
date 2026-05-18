import test from "node:test";
import assert from "node:assert/strict";

import {
  hasNonEmptyValue,
  isValidPassword,
  isValidPublicOrigin,
  isValidUserEmail,
  normalizeTextInput,
  readApiErrorDetail,
  USER_EMAIL_PATTERN,
} from "../app/lib/user-form.js";

test("normalizeTextInput trims surrounding whitespace", () => {
  assert.equal(normalizeTextInput("  example  "), "example");
  assert.equal(normalizeTextInput("   "), "");
});

test("hasNonEmptyValue rejects whitespace-only input", () => {
  assert.equal(hasNonEmptyValue("token-name"), true);
  assert.equal(hasNonEmptyValue("   "), false);
});

test("isValidUserEmail rejects addresses without a dotted domain", () => {
  assert.equal(isValidUserEmail("john@man"), false);
  assert.equal(isValidUserEmail("john@localhost"), false);
  assert.equal(isValidUserEmail("john@example.com"), true);
  assert.equal(isValidUserEmail("john@sub.example"), true);
});

test("USER_EMAIL_PATTERN accepts dotted domains with s characters", () => {
  const emailPattern = new RegExp(USER_EMAIL_PATTERN);
  assert.equal(emailPattern.test("majimusprime@gmail.com"), true);
  assert.equal(emailPattern.test("john@man"), false);
  assert.equal(emailPattern.test("name@example.com "), false);
});

test("isValidPassword rejects whitespace-only passwords", () => {
  assert.equal(isValidPassword("password-123"), true);
  assert.equal(isValidPassword("        "), false);
  assert.equal(isValidPassword("short"), false);
});

test("isValidPublicOrigin accepts only URL origins", () => {
  assert.equal(isValidPublicOrigin("https://registry.example.com"), true);
  assert.equal(isValidPublicOrigin("https://registry.example.com/path"), false);
  assert.equal(isValidPublicOrigin("registry.example.com"), false);
});

test("readApiErrorDetail unwraps FastAPI validation payloads", () => {
  assert.equal(
    readApiErrorDetail(
      {
        detail: [{ msg: "value is not a valid email address" }],
      },
      "Could not create user.",
    ),
    "value is not a valid email address",
  );

  assert.equal(
    readApiErrorDetail(
      {
        detail: "A user with that username or email already exists.",
      },
      "Could not create user.",
    ),
    "A user with that username or email already exists.",
  );
});
