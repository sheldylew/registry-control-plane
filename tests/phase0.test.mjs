import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("nginx routes app, auth, and registry paths to the expected upstreams", async () => {
  const nginxConf = await readFile(new URL("../docker/nginx.conf", import.meta.url), "utf8");

  assert.match(nginxConf, /client_max_body_size 300m;/);
  assert.match(nginxConf, /map \$http_x_forwarded_proto \$rcp_forwarded_proto \{/);
  assert.match(nginxConf, /"" \$scheme;/);
  assert.match(nginxConf, /location = \/_internal\/registry-maintenance \{/);
  assert.match(nginxConf, /proxy_pass_request_body off;/);
  assert.match(nginxConf, /proxy_set_header Content-Length "";/);
  assert.match(nginxConf, /location \/v2\/ \{/);
  assert.match(nginxConf, /client_max_body_size 1g;/);
  assert.match(nginxConf, /proxy_pass http:\/\/registry:5000;/);
  assert.match(nginxConf, /location \/api\/ \{/);
  assert.match(nginxConf, /proxy_pass http:\/\/api:8000\/api\/;/);
  assert.doesNotMatch(nginxConf, /\$proxy_add_x_forwarded_for/);
  assert.match(nginxConf, /proxy_set_header X-Forwarded-For \$remote_addr;/);
  assert.match(nginxConf, /proxy_set_header X-Forwarded-Proto \$rcp_forwarded_proto;/);
  assert.match(nginxConf, /location \/healthz \{/);
  assert.match(nginxConf, /proxy_pass http:\/\/api:8000\/healthz;/);
  assert.match(nginxConf, /location \/auth\/token \{/);
  assert.match(nginxConf, /proxy_pass http:\/\/api:8000\/auth\/token;/);
  assert.match(nginxConf, /location \/ \{/);
  assert.match(nginxConf, /proxy_pass http:\/\/web:3000;/);
});

test("dashboard page references API and registry paths", async () => {
  const page = await readFile(new URL("../app/page.jsx", import.meta.url), "utf8");

  assert.match(page, /NEXT_PUBLIC_API_BASE_PATH/);
  assert.match(page, /NEXT_PUBLIC_AUTH_TOKEN_PATH/);
  assert.match(page, /NEXT_PUBLIC_REGISTRY_BASE_PATH/);
});

test("protected repo navigation disables automatic prefetch", async () => {
  const [
    adminShell,
    adminPage,
    usersPanel,
    robotsPanel,
    auditPage,
    pagination,
    reposPanel,
    repoPage,
    tagPage,
    historyPage,
  ] = await Promise.all([
    readFile(new URL("../app/components/admin-shell.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/users-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/robots-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/audit/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/pagination.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/repositories-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/history/page.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(adminShell, /prefetch=\{false\}/);
  assert.match(adminPage, /prefetch=\{false\}/);
  assert.match(usersPanel, /prefetch=\{false\}/);
  assert.match(robotsPanel, /prefetch=\{false\}/);
  assert.match(auditPage, /prefetch=\{false\}/);
  assert.match(pagination, /prefetch=\{false\}/);
  assert.match(reposPanel, /prefetch=\{false\}/);
  assert.match(repoPage, /prefetch=\{false\}/);
  assert.match(tagPage, /prefetch=\{false\}/);
  assert.match(historyPage, /prefetch=\{false\}/);
});

test("repository tag page shows the paginated total count", async () => {
  const tagsPanel = await readFile(new URL("../app/components/repository-tags-panel.jsx", import.meta.url), "utf8");

  assert.match(tagsPanel, /payload\.pagination\.total/);
  assert.match(tagsPanel, /formatRelativeTime/);
  assert.match(tagsPanel, /formatDigest/);
  assert.match(tagsPanel, /tag\.architectures/);
  assert.match(tagsPanel, /ClockIcon/);
  assert.doesNotMatch(tagsPanel, /payload\.tags\.length} total/);
});

test("repository tag deletes redirect to the remaining tag page", async () => {
  const tagsPanel = await readFile(new URL("../app/components/repository-tags-panel.jsx", import.meta.url), "utf8");

  assert.match(tagsPanel, /function buildTagDeleteRedirectPath\(repoPath, pagination\)/);
  assert.match(tagsPanel, /return buildBulkTagDeleteRedirectPath\(repoPath, pagination, 1\)/);
  assert.match(tagsPanel, /function buildBulkTagDeleteRedirectPath\(repoPath, pagination, deleteCount\)/);
  assert.match(tagsPanel, /const remainingTags = Math\.max\(Number\(pagination\?\.total \|\| 0\) - deleteCount, 0\)/);
  assert.match(tagsPanel, /if \(remainingTags === 0\) \{\s*return "\/repos";\s*\}/);
  assert.match(tagsPanel, /const lastPageAfterDelete = Math\.max\(Math\.ceil\(remainingTags \/ pageSize\), 1\)/);
  assert.match(tagsPanel, /redirectPath=\{buildTagDeleteRedirectPath\(payload\.repo, payload\.pagination\)\}/);
});

test("repository tag deletes warn when a manifest is shared", async () => {
  const [deletePanel, tagsPanel, tagPage, routes] = await Promise.all([
    readFile(new URL("../app/components/repo-delete-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/repository-tags-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../backend/api/routes.py", import.meta.url), "utf8"),
  ]);

  assert.match(deletePanel, /warning,/);
  assert.match(deletePanel, /border-amber-300\/30 bg-amber-300\/10/);
  assert.match(tagsPanel, /function buildSharedManifestWarning\(item\)/);
  assert.match(tagsPanel, /warning=\{buildSharedManifestWarning\(tag\)\}/);
  assert.match(tagPage, /function buildSharedManifestWarning\(item\)/);
  assert.match(tagPage, /warning=\{buildSharedManifestWarning\(manifest\)\}/);
  assert.match(routes, /shared_manifest_tag_count/);
  assert.match(routes, /shared_manifest_tags/);
});

test("repository tag list exposes bulk delete selection", async () => {
  const [tagsPanel, routes] = await Promise.all([
    readFile(new URL("../app/components/repository-tags-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../backend/api/routes.py", import.meta.url), "utf8"),
  ]);

  assert.match(tagsPanel, /ActionMenu/);
  assert.match(tagsPanel, /type="checkbox"/);
  assert.match(tagsPanel, /Select all tags/);
  assert.match(tagsPanel, /Delete selected/);
  assert.match(tagsPanel, /\/api\/repos\/\$\{encodeURIComponent\(payload\.repo\)\}\/tags\/delete/);
  assert.match(routes, /class DeleteTagsPayload\(BaseModel\)/);
  assert.match(routes, /@router\.post\("\/repos\/\{repo_name:path\}\/tags\/delete"\)/);
});

test("high-density lists expose mobile card layouts without dropping desktop tables", async () => {
  const [tableUi, tagsPanel, usersPanel, permissionsPanel, pagination, reposPanel, adminShell] = await Promise.all([
    readFile(new URL("../app/components/ui/table.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/repository-tags-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/users-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/permissions-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/pagination.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/repositories-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/admin-shell.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(tableUi, /mobileCards/);
  assert.match(tableUi, /lg:hidden/);
  assert.match(tableUi, /hidden lg:block/);
  assert.match(tableUi, /export function MobileDisclosureCard/);
  assert.match(tableUi, /<details className=\{`group rounded-lg/);
  assert.match(tableUi, /group-open:hidden/);
  assert.match(tableUi, /group-open:inline-flex/);
  for (const source of [tagsPanel, usersPanel, permissionsPanel]) {
    assert.match(source, /mobileCards=\{/);
    assert.match(source, /MobileCardList/);
    assert.match(source, /MobileDisclosureCard/);
    assert.match(source, /<Table>/);
  }
  assert.match(pagination, /Showing <span className="font-medium text-white">\{start\}/);
  assert.match(reposPanel, /Showing <span className="font-medium text-white">\{start\}/);
  assert.match(adminShell, /px-4 py-6 sm:px-6 sm:py-10/);
  assert.match(adminShell, /text-3xl font-semibold tracking-tight text-white sm:text-4xl/);
  assert.match(adminShell, /Command menu/);
  assert.match(adminShell, /translate-y-0/);
  assert.match(adminShell, /-translate-y-full/);
  assert.match(adminShell, /renderMobileNavItems/);
  assert.doesNotMatch(adminShell, /-translate-x-full/);
});

test("maintenance page keeps desktop layout while adding mobile affordances", async () => {
  const [maintenancePage, maintenancePanel, statCard, floatingButtonGroup] = await Promise.all([
    readFile(new URL("../app/admin/maintenance/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/maintenance-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/stat-card.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/floating-button-group.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(maintenancePage, /FloatingButtonGroup/);
  assert.match(maintenancePage, /href: "#maintenance-actions"/);
  assert.match(maintenancePage, /href: "#maintenance-jobs"/);
  assert.match(maintenancePage, /href: "#maintenance-rebuilds"/);
  assert.match(maintenancePage, /title="Registry health and state"/);
  assert.match(maintenancePage, /Review storage, manifest cache, registry state, and recent maintenance outcomes before running jobs\./);
  assert.match(maintenancePage, /function summarizeModeTone\(job\)/);
  assert.match(maintenancePage, /detailBadge=\{Boolean\(payload\.last_job\)\}/);
  assert.match(maintenancePage, /detailBadgeTone=\{payload\.last_job \? summarizeModeTone\(payload\.last_job\) : "slate"\}/);
  assert.match(maintenancePage, /openLabel="Open job history"/);
  assert.match(maintenancePage, /hideLabel="Hide job history"/);
  assert.match(maintenancePage, /openLabel="Open rebuild jobs"/);
  assert.doesNotMatch(maintenancePage, /overflow-x-auto rounded-xl border border-white\/10 bg-slate-950\/85 p-2/);
  assert.match(maintenancePage, /xl:grid-cols-5/);
  assert.match(maintenancePage, /max-h-72 overflow-auto whitespace-pre-wrap/);
  assert.match(floatingButtonGroup, /sticky top-3/);
  assert.match(floatingButtonGroup, /lg:hidden/);
  assert.match(floatingButtonGroup, /rounded-full/);
  assert.match(floatingButtonGroup, /shadow-2xl shadow-cyan-950\/30/);
  assert.match(maintenancePanel, /id="maintenance-actions"/);
  assert.match(maintenancePanel, /mt-5 w-full justify-center sm:w-auto/);
  assert.doesNotMatch(maintenancePanel, /sticky bottom-3/);
  assert.match(maintenancePanel, /hidden space-y-6 lg:block/);
  assert.match(maintenancePanel, /Open rebuild action/);
  assert.match(maintenancePanel, /Open prune action/);
  assert.match(statCard, /p-4/);
  assert.match(statCard, /sm:p-6/);
  assert.match(statCard, /detailBadge = false/);
  assert.match(statCard, /badgeTones\[detailBadgeTone\]/);
});

test("overview dashboard stats are grouped in a titled container", async () => {
  const adminPage = await readFile(new URL("../app/admin/page.jsx", import.meta.url), "utf8");

  assert.match(adminPage, /title="Control-plane snapshot"/);
  assert.match(adminPage, /At-a-glance identity, credential, and registry counts for the current control plane\./);
  assert.match(adminPage, /<Panel as="section" className='p-4 sm:p-6'>/);
  assert.match(adminPage, /xl:grid-cols-5/);
});

test("remaining app sections keep desktop layout while tightening mobile shells", async () => {
  const [
    panel,
    dialog,
    formDialog,
    repoDeletePanel,
    adminPage,
    auditPage,
    sessionsPanel,
    tokensPanel,
    robotsPanel,
    userProfile,
    robotProfile,
    tagPage,
    tagHistoryPage,
    settingsPanel,
    publicHome,
    loginPage,
    setupPage,
    loginForm,
    setupForm,
    emptyState,
  ] = await Promise.all([
    readFile(new URL("../app/components/ui/panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/dialog.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/form-dialog.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/repo-delete-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/audit/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/sessions-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/tokens-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/robots-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/user-profile-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/robot-profile-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/history/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/settings-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/login/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/setup/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/login-form.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/setup-form.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/empty-state.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(panel, /w-full shrink-0 sm:w-auto/);
  assert.match(dialog, /max-h-\[calc\(100vh-2rem\)\]/);
  assert.match(formDialog, /grid gap-3 sm:flex sm:items-center sm:justify-end/);
  assert.match(repoDeletePanel, /grid gap-3 sm:flex sm:items-center sm:justify-end/);
  for (const source of [adminPage, auditPage, sessionsPanel, tokensPanel, robotsPanel, userProfile, robotProfile, tagPage, tagHistoryPage, settingsPanel]) {
    assert.match(source, /p-4 sm:p-6/);
  }
  assert.match(auditPage, /max-h-72 overflow-auto whitespace-pre-wrap/);
  assert.match(sessionsPanel, /grid-cols-2 gap-3/);
  assert.match(tagPage, /w-full shrink-0 self-start sm:w-auto/);
  assert.match(settingsPanel, /break-all text-sm text-white/);
  assert.match(publicHome, /px-4 py-6 sm:px-6 sm:py-10/);
  assert.match(publicHome, /text-3xl font-semibold tracking-tight text-white sm:text-6xl/);
  assert.match(loginPage, /px-4 py-6 sm:px-6 sm:py-10/);
  assert.match(setupPage, /px-4 py-6 sm:px-6 sm:py-10/);
  assert.match(loginForm, /p-5 shadow-2xl shadow-slate-950\/30 sm:p-8/);
  assert.match(setupForm, /p-5 shadow-2xl shadow-slate-950\/30 sm:p-8/);
  assert.match(emptyState, /px-4 py-8/);
});

test("long mobile lists collapse to summaries with on-demand details", async () => {
  const [
    panel,
    maintenancePage,
    auditPage,
    sessionsPanel,
    tokensPanel,
    robotsPanel,
    userProfile,
    robotProfile,
    adminPage,
    tagPage,
    tagHistoryPage,
  ] = await Promise.all([
    readFile(new URL("../app/components/ui/panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/maintenance/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/audit/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/sessions-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/tokens-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/robots-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/user-profile-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/robot-profile-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/history/page.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(panel, /export function MobileCollapsiblePanel/);
  assert.match(panel, /openLabel = "Open details"/);
  assert.match(panel, /mt-3 inline-flex text-sm font-medium text-cyan-200 group-open:hidden/);
  assert.match(panel, /group-open:hidden/);
  assert.match(panel, /lg:hidden/);
  assert.match(panel, /hidden lg:block/);

  for (const source of [
    maintenancePage,
    auditPage,
    sessionsPanel,
    tokensPanel,
    robotsPanel,
    userProfile,
    robotProfile,
    adminPage,
    tagPage,
    tagHistoryPage,
  ]) {
    assert.match(source, /MobileDisclosureCard/);
  }

  for (const source of [
    maintenancePage,
    auditPage,
    sessionsPanel,
    tokensPanel,
    robotsPanel,
    userProfile,
    robotProfile,
    adminPage,
    tagPage,
    tagHistoryPage,
  ]) {
    assert.match(source, /MobileCollapsiblePanel/);
  }

  for (const source of [
    maintenancePage,
    sessionsPanel,
    tokensPanel,
    robotsPanel,
    userProfile,
    robotProfile,
    adminPage,
    tagPage,
    tagHistoryPage,
  ]) {
    assert.match(source, /lg:hidden/);
    assert.match(source, /hidden .*lg:block|hidden .*lg:flex/);
  }
});

test("web healthchecks use the static root page", async () => {
  const [compose, bindCompose, dockerSave] = await Promise.all([
    readFile(new URL("../docker-compose.yml", import.meta.url), "utf8"),
    readFile(new URL("../docker-compose.bind-local.yml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/docker-save.sh", import.meta.url), "utf8"),
  ]);

  for (const source of [compose, bindCompose, dockerSave]) {
    assert.match(source, /http:\/\/\\?\$\(hostname\):3000\//);
    assert.match(source, /interval: 1m/);
    assert.doesNotMatch(source, /3000\/login/);
  }
});

test("shared default page size stays at 10 through admin settings", async () => {
  const [setup, routes, settingsPanel, sessionsPage, compose, bindCompose, dockerSave] = await Promise.all([
    readFile(new URL("../backend/setup.py", import.meta.url), "utf8"),
    readFile(new URL("../backend/api/routes.py", import.meta.url), "utf8"),
    readFile(new URL("../app/components/settings-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/sessions/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../docker-compose.yml", import.meta.url), "utf8"),
    readFile(new URL("../docker-compose.bind-local.yml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/docker-save.sh", import.meta.url), "utf8"),
  ]);

  assert.match(setup, /REPOSITORY_TAGS_PAGE_SIZE_KEY = "repository_tags_page_size"/);
  assert.match(setup, /DEFAULT_REPOSITORY_TAGS_PAGE_SIZE = 10/);
  assert.match(routes, /repository_tags_page_size: int = Field\(default=DEFAULT_REPOSITORY_TAGS_PAGE_SIZE, ge=1, le=100\)/);
  assert.match(settingsPanel, /Default items per page/);
  assert.match(settingsPanel, /function DefaultPageSizePicker/);
  assert.match(sessionsPage, /pageSizeParam === undefined\s*\?\s*null/);
  for (const source of [compose, bindCompose, dockerSave]) {
    assert.doesNotMatch(source, /REPOSITORY_TAGS_MAX_ITEMS/);
  }
});

test("audit pruning retention stays runtime-configurable through admin settings", async () => {
  const [setup, routes, settingsPanel] = await Promise.all([
    readFile(new URL("../backend/setup.py", import.meta.url), "utf8"),
    readFile(new URL("../backend/api/routes.py", import.meta.url), "utf8"),
    readFile(new URL("../app/components/settings-panel.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(setup, /AUDIT_LOG_RETENTION_DAYS_KEY = "audit_log_retention_days"/);
  assert.match(setup, /DEFAULT_AUDIT_LOG_RETENTION_DAYS = 30/);
  assert.match(routes, /audit_log_retention_days: int = Field\(default=DEFAULT_AUDIT_LOG_RETENTION_DAYS, ge=1\)/);
  assert.match(routes, /"audit_log_retention_days": effective_audit_log_retention_days/);
  assert.match(settingsPanel, /Audit pruning retention/);
  assert.match(settingsPanel, /function AuditLogRetentionPicker/);
  assert.match(settingsPanel, /5 days/);
  assert.match(settingsPanel, /15 days/);
  assert.match(settingsPanel, /30 days/);
  assert.match(settingsPanel, /60 days/);
});

test("release compose files keep internal service DNS aliases explicit", async () => {
  const [bindCompose, dockerSave] = await Promise.all([
    readFile(new URL("../docker-compose.bind-local.yml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/docker-save.sh", import.meta.url), "utf8"),
  ]);

  for (const source of [bindCompose, dockerSave]) {
    assert.match(source, /REGISTRY_NOTIFICATIONS_TOKEN_PATH: \/data\/registry-events-token/);
    assert.match(source, /INTERNAL_API_BASE_URL: .*http:\/\/api:8000/);
    assert.match(source, /aliases:\n\s+- api/);
    assert.match(source, /aliases:\n\s+- web/);
    assert.match(source, /aliases:\n\s+- registry/);
  }
});

test("compose builds pass runtime build metadata into app images", async () => {
  const [compose, bindCompose, dockerfile, rebuildStack, smokeTest, upgradeStack] = await Promise.all([
    readFile(new URL("../docker-compose.yml", import.meta.url), "utf8"),
    readFile(new URL("../docker-compose.bind-local.yml", import.meta.url), "utf8"),
    readFile(new URL("../Dockerfile", import.meta.url), "utf8"),
    readFile(new URL("../scripts/rebuild-stack.sh", import.meta.url), "utf8"),
    readFile(new URL("../scripts/smoke-test.sh", import.meta.url), "utf8"),
    readFile(new URL("../scripts/upgrade-stack.sh", import.meta.url), "utf8"),
  ]);

  for (const source of [compose, bindCompose]) {
    assert.match(source, /APP_BUILD_TIME: \$\{APP_BUILD_TIME:-\}/);
    assert.match(source, /APP_REVISION: \$\{APP_REVISION:-dev\}/);
    assert.match(source, /APP_IMAGE_TAG:/);
  }
  assert.equal([...dockerfile.matchAll(/ARG APP_VERSION=dev/g)].length, 3);
  assert.equal([...dockerfile.matchAll(/ARG APP_REVISION=dev/g)].length, 3);
  assert.equal([...dockerfile.matchAll(/ARG APP_BUILD_TIME=/g)].length, 3);
  assert.equal([...dockerfile.matchAll(/ARG APP_IMAGE_TAG=/g)].length, 3);
  assert.match(dockerfile, /FROM --platform=\$BUILDPLATFORM alpine:3\.20 AS build-metadata/);
  assert.match(dockerfile, /COPY --from=build-metadata --chown=10001:10001 \/out\/srv\/build-info\.env \/srv\/build-info\.env/);
  assert.match(dockerfile, /COPY --from=build-metadata --chown=10001:10001 \/out\/web\/build-info\.env \/web\/build-info\.env/);
  assert.match(dockerfile, /printf 'APP_BUILD_TIME=%s\\n' "\$APP_BUILD_TIME"/);
  for (const source of [rebuildStack, smokeTest, upgradeStack]) {
    assert.match(source, /APP_BUILD_TIME="\$\{APP_BUILD_TIME:-\$\(date -u '\+%Y-%m-%dT%H:%M:%SZ'\)\}"/);
    assert.match(source, /APP_REVISION="\$\{APP_REVISION:-\$\(git rev-parse HEAD 2>\/dev\/null \|\| true\)\}"/);
    assert.match(source, /APP_VERSION="\$\{APP_VERSION:-\$\(git branch --show-current 2>\/dev\/null \|\| true\)\}"/);
  }
});

test("settings page opens separate API and web image metadata from header", async () => {
  const [settingsPage, settingsPanel, buildInfo, buildDialog] = await Promise.all([
    readFile(new URL("../app/admin/settings/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/settings-panel.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/lib/build-info.js", import.meta.url), "utf8"),
    readFile(new URL("../app/components/build-info-dialog.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(settingsPage, /readWebBuildInfo\(\)/);
  assert.match(settingsPage, /api: payload\.build/);
  assert.match(settingsPage, /web: webBuild/);
  assert.match(settingsPage, /action=\{<BuildInfoDialog build=\{build\} \/>\}/);
  assert.doesNotMatch(settingsPanel, /Build information/);
  assert.match(buildDialog, /InformationCircleIcon/);
  assert.match(buildDialog, /aria-label="Show build information"/);
  assert.match(buildDialog, /Build information/);
  assert.match(buildDialog, /API image/);
  assert.match(buildDialog, /Web image/);
  assert.match(buildInfo, /\/web\/build-info\.env/);
  assert.match(buildInfo, /buildInfo\.APP_VERSION \|\| process\.env\.APP_VERSION/);
});

test("forgejo docker workflow exports build time into bake metadata", async () => {
  const [workflow, dockerBake] = await Promise.all([
    readFile(new URL("../.forgejo/workflows/docker.yml", import.meta.url), "utf8"),
    readFile(new URL("../docker-bake.hcl", import.meta.url), "utf8"),
  ]);

  assert.match(workflow, /build_time="\$\(date -u '\+%Y-%m-%dT%H:%M:%SZ'\)"/);
  assert.match(workflow, /echo "build_time=\$\{build_time\}"/);
  assert.match(workflow, /name: Log image build metadata/);
  assert.match(workflow, /echo "Build information:"/);
  assert.match(workflow, /echo "  Built at: \$\{\{ steps\.meta\.outputs\.build_time \}\}"/);
  assert.match(workflow, /echo "  Image tag: \$\{\{ steps\.meta\.outputs\.image_tag \}\}"/);
  assert.match(workflow, /export BUILD_TIME="\$\{\{ steps\.meta\.outputs\.build_time \}\}"/);
  assert.match(dockerBake, /"org\.opencontainers\.image\.created" = BUILD_TIME/);
  assert.match(dockerBake, /"org\.opencontainers\.image\.ref\.name" = IMAGE_TAG/);
});

test("server auth skips session API calls when no session cookie exists", async () => {
  const serverApi = await readFile(new URL("../app/lib/server-api.js", import.meta.url), "utf8");

  assert.match(serverApi, /process\.env\.INTERNAL_API_BASE_URL \|\| "http:\/\/127\.0\.0\.1:8000"/);
  assert.doesNotMatch(serverApi, /process\.env\.INTERNAL_API_BASE_URL \|\| "http:\/\/api:8000"/);
  assert.match(serverApi, /const sessionCookieName = "rcr_session";/);
  assert.match(serverApi, /if \(!store\.has\(sessionCookieName\)\) \{/);
  assert.match(serverApi, /apiFetch\("\/api\/session\/me"\)/);
});
