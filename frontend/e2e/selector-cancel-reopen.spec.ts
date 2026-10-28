import { withOwnedAuthority, type OwnedAuthority } from "./support/owned-authority";
import { test as base, expect } from "@playwright/test";
import { startHeldCanonicalGet } from "./support/held-canonical-response";

// SYNTHETIC=true. Independent correction regression using the committed S5 server.
const test = base.extend<Record<never, never>, { authority: OwnedAuthority }>({
  authority: [
    async ({ playwright }, use) => {
      await withOwnedAuthority(playwright.request, "frontend.e2e.support.dashboard_api:app", use);
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
    authority.owned.mark("PAGE_USE_BEGIN");
    await use(page);
    authority.owned.mark("PAGE_UNROUTE_BEGIN");
    await page.unrouteAll({ behavior: "wait" });
    authority.owned.mark("PAGE_UNROUTE_END");
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
