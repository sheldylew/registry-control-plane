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
  const repoPage = await readFile(new URL("../app/repos/[repo]/page.jsx", import.meta.url), "utf8");

  assert.match(repoPage, /payload\.pagination\.total/);
  assert.match(repoPage, /formatRelativeTime/);
  assert.match(repoPage, /formatDigest/);
  assert.match(repoPage, /tag\.architectures/);
  assert.match(repoPage, /ClockIcon/);
  assert.doesNotMatch(repoPage, /payload\.tags\.length} total/);
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

test("server auth skips session API calls when no session cookie exists", async () => {
  const serverApi = await readFile(new URL("../app/lib/server-api.js", import.meta.url), "utf8");

  assert.match(serverApi, /process\.env\.INTERNAL_API_BASE_URL \|\| "http:\/\/127\.0\.0\.1:8000"/);
  assert.doesNotMatch(serverApi, /process\.env\.INTERNAL_API_BASE_URL \|\| "http:\/\/api:8000"/);
  assert.match(serverApi, /const sessionCookieName = "rcr_session";/);
  assert.match(serverApi, /if \(!store\.has\(sessionCookieName\)\) \{/);
  assert.match(serverApi, /apiFetch\("\/api\/session\/me"\)/);
});
