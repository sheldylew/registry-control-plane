import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { authenticatedLandingPath } from "../app/lib/session-routing.js";

test("login form posts credentials to the session API", async () => {
  const form = await readFile(new URL("../app/components/login-form.jsx", import.meta.url), "utf8");
  const panel = await readFile(new URL("../app/components/ui/panel.jsx", import.meta.url), "utf8");

  assert.match(form, /fetch\("\/api\/session\/login"/);
  assert.match(form, /method: "POST"/);
  assert.match(form, /JSON\.stringify\(\{ username: normalizedUsername, password \}\)/);
  assert.match(form, /const payload = await response\.json\(\)\.catch\(\(\) => \(\{\}\)\)/);
  assert.match(form, /router\.push\(authenticatedLandingPath\(payload\.user\)\)/);
  assert.match(form, /router\.refresh\(\)/);
  assert.match(panel, /\.\.\.props/);
});

test("login page sends existing sessions to the role-appropriate landing page", async () => {
  const page = await readFile(new URL("../app/login/page.jsx", import.meta.url), "utf8");

  assert.match(page, /if \(user\) \{/);
  assert.match(page, /redirect\(authenticatedLandingPath\(user\)\)/);
});

test("authenticated landing path keeps admin users on the admin dashboard", () => {
  assert.equal(authenticatedLandingPath({ is_admin: true }), "/admin");
});

test("authenticated landing path sends regular users to repositories", () => {
  assert.equal(authenticatedLandingPath({ is_admin: false }), "/repos");
  assert.equal(authenticatedLandingPath({}), "/repos");
});

test("login form enables submit only after username and password input", async () => {
  const form = await readFile(new URL("../app/components/login-form.jsx", import.meta.url), "utf8");

  assert.match(form, /hasNonEmptyValue\(username\) && isValidPassword\(password, 1\)/);
  assert.match(form, /disabled=\{pending \|\| !canSubmit\}/);
  assert.match(form, /loading=\{pending\}/);
  assert.match(form, /Username is required\./);
  assert.match(form, /Password is required\./);
});
