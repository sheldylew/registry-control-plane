import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("login form posts credentials to the session API", async () => {
  const form = await readFile(new URL("../app/components/login-form.jsx", import.meta.url), "utf8");
  const panel = await readFile(new URL("../app/components/ui/panel.jsx", import.meta.url), "utf8");

  assert.match(form, /fetch\("\/api\/session\/login"/);
  assert.match(form, /method: "POST"/);
  assert.match(form, /JSON\.stringify\(\{ username: normalizedUsername, password \}\)/);
  assert.match(form, /router\.push\("\/admin"\)/);
  assert.match(form, /router\.refresh\(\)/);
  assert.match(panel, /\.\.\.props/);
});

test("login form enables submit only after username and password input", async () => {
  const form = await readFile(new URL("../app/components/login-form.jsx", import.meta.url), "utf8");

  assert.match(form, /hasNonEmptyValue\(username\) && isValidPassword\(password, 1\)/);
  assert.match(form, /disabled=\{pending \|\| !canSubmit\}/);
  assert.match(form, /loading=\{pending\}/);
  assert.match(form, /Username is required\./);
  assert.match(form, /Password is required\./);
});
