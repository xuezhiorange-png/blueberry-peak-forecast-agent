import { test as base, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { startHeldCanonicalGet } from "./support/held-canonical-response";

// SYNTHETIC=true. Independent correction regression using the committed S5 server.
const test = base.extend<
  Record<string, never>,
  { authority: { url: string; identities: Record<string, string | number>[] } }
>({
  authority: [
    async ({ playwright }, use, worker) => {
      const url = `http://127.0.0.1:${45800 + worker.workerIndex}`;
      const child = spawn(
        process.env.DASHBOARD_TEST_PYTHON ?? "python3",
        [
          "-m",
          "uvicorn",
          "frontend.e2e.support.dashboard_api:app",
          "--host",
          "127.0.0.1",
          "--port",
          String(45800 + worker.workerIndex),
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
    for (const surface of ["auth", "business-access", "forecast-intelligence", "decision-support"])
      await page.route(`**/api/v1/${surface}/**`, async (route) => {
        const incoming = new URL(route.request().url());
        await route.continue({
          url: authority.url + incoming.pathname + incoming.search,
        });
      });
    await use(page);
    await page.unrouteAll({ behavior: "wait" });
  },
});

for (const closeWay of ["button", "escape", "native"] as const) {
  test(`cancelled saved-run validation can be retried after reopening: ${closeWay}`, async ({
    page,
    authority,
  }, info) => {
    await page.setViewportSize(
      info.project.name === "chromium-mobile"
        ? { width: 390, height: 844 }
        : { width: 1440, height: 900 },
    );
    await page.goto("/dashboard/overview");
    await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
    const dialog = page.getByRole("dialog");
    const selectedRow = dialog.locator(
      `article[data-run-id="${authority.identities[0].run_id}"][data-source-kind="${authority.identities[0].source_kind}"]`,
    );
    await expect(selectedRow).toBeVisible();
    const gate = await startHeldCanonicalGet(authority.url);
    const pattern = "**/api/v1/forecast-intelligence/curve?**";
    const targetRun = String(authority.identities[0].run_id);
    await page.route(pattern, async (route) => {
      const incoming = new URL(route.request().url());
      if (incoming.searchParams.get("run_id") !== targetRun) {
        await route.fallback();
        return;
      }
      await route.continue({ url: gate.url + incoming.pathname + incoming.search });
    });
    try {
      await selectedRow.getByRole("button", { name: "核验并使用保存预测" }).click();
      await gate.started;
      await expect(selectedRow.getByRole("button", { name: "正在核验…" })).toBeDisabled();
      if (closeWay === "button")
        await dialog.getByRole("button", { name: "关闭", exact: true }).click();
      else if (closeWay === "escape") await page.keyboard.press("Escape");
      else await dialog.evaluate((element: HTMLDialogElement) => element.close());
      await expect(dialog).not.toBeVisible();
      await expect(
        page.getByRole("button", { name: "选择已保存预测", exact: true }).first(),
      ).toBeFocused();
      gate.release();
      await gate.finished;
      expect(gate.errors).toEqual([]);
      await page.unroute(pattern);
      await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
      await expect(dialog).toBeVisible();
      await expect(page.locator(".d-context-title")).toHaveText("请选择已保存预测");
      await dialog.getByRole("button", { name: "查询授权记录" }).scrollIntoViewIfNeeded();
      await page.evaluate(() => {
        const caption = document.createElement("p");
        caption.textContent =
          "SYNTHETIC S6 ACCEPTANCE — NOT PRODUCTION DATA · cancelled verification reopened";
        document.body.prepend(caption);
      });
      await page.screenshot({
        path: info.outputPath("cancel-reopen-SYNTHETIC.png"),
        fullPage: true,
      });
      await expect(dialog.getByRole("button", { name: "查询授权记录" })).toBeEnabled();
      await selectedRow.getByRole("button", { name: "核验并使用保存预测" }).click();
      await expect(dialog).not.toBeVisible();
      await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_1");
      await expect(page.locator(".d-kpis").first()).toContainText("1820");
      await expect(page.locator('[data-state="LOADING"]')).toHaveCount(0);
    } finally {
      gate.release();
      await gate.close();
      expect(gate.errors).toEqual([]);
    }
  });
}
