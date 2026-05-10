import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("nginx routes app, auth, and registry paths to the expected upstreams", async () => {
  const nginxConf = await readFile(new URL("../docker/nginx.conf", import.meta.url), "utf8");

  assert.match(nginxConf, /client_max_body_size 300m;/);
  assert.match(nginxConf, /location = \/_internal\/registry-maintenance \{/);
  assert.match(nginxConf, /proxy_pass_request_body off;/);
  assert.match(nginxConf, /proxy_set_header Content-Length "";/);
  assert.match(nginxConf, /location \/v2\/ \{/);
  assert.match(nginxConf, /proxy_pass http:\/\/registry:5000;/);
  assert.match(nginxConf, /location \/api\/ \{/);
  assert.match(nginxConf, /proxy_pass http:\/\/api:8000\/api\/;/);
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
  const [adminShell, reposPage, repoPage, tagPage, historyPage] = await Promise.all([
    readFile(new URL("../app/components/admin-shell.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/page.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/repos/[repo]/tags/[tag]/history/page.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(adminShell, /prefetch=\{false\}/);
  assert.match(reposPage, /prefetch=\{false\}/);
  assert.match(repoPage, /prefetch=\{false\}/);
  assert.match(tagPage, /prefetch=\{false\}/);
  assert.match(historyPage, /prefetch=\{false\}/);
});
