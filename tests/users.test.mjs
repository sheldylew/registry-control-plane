import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("admin users page passes the signed-in user id into the users panel", async () => {
  const page = await readFile(new URL("../app/admin/users/page.jsx", import.meta.url), "utf8");

  assert.match(page, /requireCurrentUser/);
  assert.match(page, /currentUserId=\{currentUser\?\.id \?\? null\}/);
});

test("users panel omits disable control for the signed-in admin row", async () => {
  const panel = await readFile(new URL("../app/components/users-panel.jsx", import.meta.url), "utf8");

  assert.match(panel, /user\.id === currentUserId && !nextActive/);
  assert.match(panel, /user\.id === currentUserId && user\.is_active/);
  assert.match(panel, /loading=\{pendingStatusUserId === user\.id\}/);
  assert.match(panel, /<Pagination/);
  assert.match(panel, /function buildPageHref\(page\)/);
});

test("users panel exposes admin password reset controls", async () => {
  const panel = await readFile(new URL("../app/components/users-panel.jsx", import.meta.url), "utf8");

  assert.match(panel, /openPasswordReset\(user\)/);
  assert.match(panel, /\/api\/admin\/users\/\$\{passwordResetUser\.id\}\/password/);
  assert.match(panel, /Current password/);
  assert.match(panel, /current_password: resettingOwnPassword \? currentPassword : undefined/);
  assert.match(panel, /Reset password/);
  assert.match(panel, /Passwords must match\./);
  assert.match(panel, /router\.push\("\/"\)/);
});

test("logout flows redirect signed-out operators to the public home page", async () => {
  const logoutButton = await readFile(new URL("../app/components/logout-button.jsx", import.meta.url), "utf8");
  const sessionsPanel = await readFile(new URL("../app/components/sessions-panel.jsx", import.meta.url), "utf8");
  const profilePanel = await readFile(new URL("../app/components/user-profile-panel.jsx", import.meta.url), "utf8");
  const logoutPage = await readFile(new URL("../app/logout/page.jsx", import.meta.url), "utf8");

  assert.match(logoutButton, /router\.push\("\/"\)/);
  assert.match(sessionsPanel, /router\.push\("\/"\)/);
  assert.match(profilePanel, /router\.push\("\/"\)/);
  assert.match(logoutPage, /redirect\("\/"\)/);
});

test("users panel exposes enable action for disabled users", async () => {
  const panel = await readFile(new URL("../app/components/users-panel.jsx", import.meta.url), "utf8");

  assert.match(panel, /async function setUserActive\(user, nextActive\)/);
  assert.match(panel, /\/api\/admin\/users\/\$\{user\.id\}\/\$\{nextActive \? "enable" : "disable"\}/);
  assert.match(panel, /user\.is_active \? "Enabled" : "Disabled"/);
});

test("admin users page builds pagination links", async () => {
  const page = await readFile(new URL("../app/admin/users/page.jsx", import.meta.url), "utf8");

  assert.doesNotMatch(page, /buildPageHref=\{buildPageHref\}/);
  assert.match(page, /pagination=\{payload\.pagination\}/);
});

test("repositories page shows visibility badges", async () => {
  const [page, panel] = await Promise.all([
    readFile(new URL("../app/repos/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/repositories-panel.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(page, /<RepositoriesPanel initialPayload=\{payload\} \/>/);
  assert.match(panel, /repo\.visibility === "public"/);
  assert.match(panel, /Public/);
  assert.match(panel, /Private/);
});

test("maintenance panel exposes registry state rebuild action", async () => {
  const [page, panel, statCard] = await Promise.all([
    readFile(new URL("../app/admin/maintenance/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/maintenance-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/stat-card.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(page, /\/api\/admin\/maintenance\?page=\$\{page\}/);
  assert.match(page, /payload\.storage_usage_measured_at/);
  assert.match(page, /payload\.storage_usage_stale/);
  assert.match(page, /badge=\{payload\.storage_usage_stale \? "Stale" : null\}/);
  assert.match(page, /payload\.registry_state\.active_repositories/);
  assert.match(page, /payload\.registry_state\.inbox_failed/);
  assert.match(page, /payload\.rebuild_jobs/);
  assert.match(statCard, /badge = null/);
  assert.match(statCard, /badgeTones/);
  assert.match(panel, /router\.refresh\(\)/);
  assert.match(panel, /\/api\/admin\/maintenance\/cache\/rebuild/);
  assert.match(panel, /Rebuild registry state/);
  assert.match(panel, /X-CSRF-Token/);
});

test("admin shell includes settings navigation", async () => {
  const shell = await readFile(new URL("../app/components/admin-shell.jsx", import.meta.url), "utf8");

  assert.match(shell, /href: "\/admin\/settings"/);
  assert.match(shell, /label: "Settings"/);
});

test("first boot setup page and settings panel use setup APIs", async () => {
  const setupPage = await readFile(new URL("../app/setup/page.jsx", import.meta.url), "utf8");
  const setupForm = await readFile(new URL("../app/components/setup-form.jsx", import.meta.url), "utf8");
  const settingsPanel = await readFile(new URL("../app/components/settings-panel.jsx", import.meta.url), "utf8");

  assert.match(setupPage, /\/api\/setup\/status/);
  assert.match(setupForm, /\/api\/setup\/complete/);
  assert.match(setupForm, /docker compose restart registry/);
  assert.match(setupForm, /Continue to sign in after restart/);
  assert.match(settingsPanel, /\/api\/admin\/settings/);
  assert.match(settingsPanel, /X-CSRF-Token/);
  assert.match(settingsPanel, /ComboboxInput/);
  assert.match(settingsPanel, /Intl\.supportedValuesOf\("timeZone"\)/);
  assert.match(settingsPanel, /automatic_registry_state_rebuild/);
  assert.match(settingsPanel, /Automatic registry state rebuild/);
  assert.match(settingsPanel, /audit_log_retention_days/);
  assert.match(settingsPanel, /Audit pruning retention/);
  assert.match(settingsPanel, /storage_usage_refresh_interval_seconds/);
  assert.match(settingsPanel, /Storage usage refresh interval/);
  assert.match(settingsPanel, /function AuditLogRetentionPicker/);
  assert.match(settingsPanel, /function StorageUsageIntervalPicker/);
  assert.match(settingsPanel, /function DefaultPageSizePicker/);
  assert.match(settingsPanel, /Presets cover the common sizes/);
  assert.match(settingsPanel, /Presets cover the common retention windows/);
  assert.match(settingsPanel, /className="absolute z-\[60\] mt-2 max-h-72 w-full/);
  assert.doesNotMatch(settingsPanel, /anchor="bottom"/);
});
