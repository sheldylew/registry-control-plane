import test from "node:test";
import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";

test("shared button and switch controls expose visible busy indicators", async () => {
  const [button, switchControl, formDialog] = await Promise.all([
    readFile(new URL("../app/components/ui/button.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/switch.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/form-dialog.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(button, /loading = false/);
  assert.match(button, /aria-busy=\{loading \|\| undefined\}/);
  assert.match(button, /animate-spin/);
  assert.match(switchControl, /loading = false/);
  assert.match(switchControl, /aria-busy=\{loading \|\| undefined\}/);
  assert.match(formDialog, /loading=\{pending\}/);
});

test("route navigation does not replace the current page with a loading page", async () => {
  await assert.rejects(
    stat(new URL("../app/loading.jsx", import.meta.url)),
    { code: "ENOENT" },
  );
});

test("client API fetches and internal navigation show a screen-level overlay", async () => {
  const [layout, apiOverlay, loadingOverlay] = await Promise.all([
    readFile(new URL("../app/layout.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/api-busy-overlay.jsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/ui/loading-overlay.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(layout, /<ApiBusyOverlay \/>/);
  assert.match(apiOverlay, /window\.fetch = trackedFetch/);
  assert.match(apiOverlay, /pathname\.startsWith\("\/api\/"\)/);
  assert.match(apiOverlay, /document\.addEventListener\("click", handleDocumentClick, true\)/);
  assert.match(apiOverlay, /setNavigationPending\(true\)/);
  assert.match(apiOverlay, /<LoadingOverlay \/>/);
  assert.match(loadingOverlay, /fixed inset-0/);
  assert.match(loadingOverlay, /z-\[100\]/);
  assert.match(loadingOverlay, /Waiting for API response/);
});
