import { test as base, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

// SYNTHETIC=true. Browser HTTP and server-side real MCP SDK share one SQLite DB.
const test = base.extend<
  Record<string, never>,
  { authority: { url: string; identities: Record<string, string | number>[] } }
>({
  authority: [
    async ({ playwright }, use, worker) => {
      const url = `http://127.0.0.1:${44800 + worker.workerIndex}`;
      const child = spawn(
        process.env.DASHBOARD_TEST_PYTHON ?? "python3",
        [
          "-m",
          "uvicorn",
          "frontend.e2e.support.s6_api:app",
          "--host",
          "127.0.0.1",
          "--port",
          String(44800 + worker.workerIndex),
        ],
        {
          cwd: resolve(process.cwd(), ".."),
          env: { ...process.env, PYTHONPATH: "." },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      let logs = "";
      const drain = (v: Buffer) => {
        logs = (logs + String(v)).slice(-32768);
      };
      child.stdout.on("data", drain);
      child.stderr.on("data", drain);
      const api = await playwright.request.newContext();
      try {
        await expect
          .poll(
            async () => {
              if (child.exitCode !== null) throw new Error(logs);
              try {
                return (await api.get(url + "/__dashboard_test__/authority")).status();
              } catch {
                return 0;
              }
            },
            { timeout: 30000 },
          )
          .toBe(200);
        const state = await (await api.get(url + "/__dashboard_test__/authority")).json();
        expect(state.SYNTHETIC).toBe(true);
        await use({ url, identities: state.identities });
        expect(
          (await (await api.get(url + "/__dashboard_test__/authority")).json()).read_dml_count,
        ).toBe(0);
      } finally {
        child.kill("SIGTERM");
        await api.dispose();
      }
    },
    { scope: "worker" },
  ],
  page: async ({ page, authority }, use) => {
    for (const surface of ["forecast-intelligence", "decision-support"])
      await page.route(`**/api/v1/${surface}/**`, async (route) => {
        const incoming = new URL(route.request().url());
        await route.fulfill({
          response: await route.fetch({ url: authority.url + incoming.pathname + incoming.search }),
        });
      });
    await use(page);
    await page.unrouteAll({ behavior: "wait" });
  },
});

test("cancelled saved-run validation can be retried after reopening", async ({
  page,
  authority,
}, info) => {
  await page.goto("/dashboard/overview");
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
  const dialog = page.getByRole("dialog");
  for (const [key, value] of Object.entries(authority.identities[0])) {
    const field = dialog.locator(`[name="${key}"]`);
    if (["source_kind", "hierarchy_level"].includes(key)) await field.selectOption(String(value));
    else await field.fill(String(value));
  }
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  // Delay a REAL canonical HTTP result; no substituted business JSON.
  await page.route("**/api/v1/forecast-intelligence/curve?**", async (route) => {
    const incoming = new URL(route.request().url());
    const response = await route.fetch({
      url: authority.url + incoming.pathname + incoming.search,
    });
    requested();
    await held;
    await route.fulfill({ response });
  });
  try {
    await dialog.getByRole("button", { name: "核验并使用保存预测" }).click();
    await started;
    await expect(dialog.getByRole("button", { name: "正在核验…" })).toBeDisabled();
    await dialog.getByRole("button", { name: "关闭", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    release();
    await page.unroute("**/api/v1/forecast-intelligence/curve?**");
    await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
    await expect(dialog).toBeVisible();
    await expect(page.locator(".d-context-title")).toHaveText("请选择已保存预测");
    await dialog.locator('button[type="submit"]').scrollIntoViewIfNeeded();
    await page.evaluate(() => {
      const caption = document.createElement("p");
      caption.textContent =
        "SYNTHETIC S6 ACCEPTANCE — NOT PRODUCTION DATA · cancelled verification reopened";
      document.body.prepend(caption);
    });
    await page.screenshot({ path: info.outputPath("cancel-reopen-SYNTHETIC.png"), fullPage: true });
    // A cancelled operation must not permanently disable retry. No field edit
    // should be necessary to recover an already valid complete identity.
    await expect(dialog.locator('button[type="submit"]')).toBeEnabled();
  } finally {
    release();
  }
});
