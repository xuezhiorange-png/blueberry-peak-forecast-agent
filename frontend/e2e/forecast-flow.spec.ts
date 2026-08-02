import { expect, test } from "@playwright/test";

const authorityValues = {
  factory: "S2-FIXTURE",
  season: "2026-DEMO",
  farm: "s2-fixture-farm",
  subfarm: "s2-fixture-east",
  variety: "S2-VAR-A",
};

async function selectForecastAuthority(page: import("@playwright/test").Page) {
  await expect(page.getByLabel("加工厂")).toHaveValue(authorityValues.factory);
  await page.getByLabel("产季").selectOption(authorityValues.season);
  await page.getByLabel("农场").selectOption(authorityValues.farm);
  await page.getByLabel("分场").selectOption(authorityValues.subfarm);
  await page.getByLabel("品种").selectOption(authorityValues.variety);
  await expect(page.getByLabel("权威种植面积（亩）")).toHaveValue("10.000000");
  await page.getByLabel("我确认使用服务端权威面积").check();
}

async function createForecast(page: import("@playwright/test").Page) {
  await page.goto("/trial/forecast");
  await selectForecastAuthority(page);

  const createRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/trial/forecasts",
  );
  await page.getByRole("button", { name: "生成预测" }).click();
  const request = await createRequest;
  const body = request.postDataJSON() as Record<string, unknown>;
  expect(body).toMatchObject({
    farm_business_key: authorityValues.farm,
    subfarm_business_key_or_null: authorityValues.subfarm,
    season_business_key: authorityValues.season,
    variety_business_key: authorityValues.variety,
    destination_factory_business_key: authorityValues.factory,
    planting_area_mu: "10.000000",
    flowering_date_or_null: null,
    maturity_stage_or_null: null,
    already_picked_quantity_kg_or_null: null,
  });
  expect(body.forecast_input_authority_hash).toMatch(/^[0-9a-f]{64}$/);
  expect(body.plan_row_hash).toMatch(/^[0-9a-f]{64}$/);

  await expect(page.getByTestId("forecast-run-id")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(page.getByTestId("daily-curve")).toContainText("P50 / P80 / P90 日曲线");
  await expect(page.getByText("单日峰值", { exact: true })).toBeVisible();
  await expect(page.getByText("连续 7 日累计", { exact: true })).toBeVisible();
  await expect(page.getByText("成熟库存（开 / 闭）", { exact: true })).toBeVisible();
  await expect(page.getByText("未采 backlog", { exact: true })).toBeVisible();
  return page.getByTestId("forecast-run-id").innerText();
}

test.describe("production Forecast Trial integration", () => {
  test("uses authority, creates persisted readback, and downloads server CSV", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const apiRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith("/api/")) apiRequests.push(pathname);
    });

    const runId = await createForecast(page);
    expect(runId).toMatch(/^[0-9a-f]{64}$/);
    expect(apiRequests).toContain("/api/v1/trial/forecast-input-authority");
    expect(apiRequests).toContain("/api/v1/trial/forecasts");
    expect(apiRequests.some((path) => path === `/api/v1/trial/forecasts/${runId}`)).toBe(true);
    expect(
      apiRequests.some((path) => path === `/api/v1/trial/forecasts/${runId}/daily-curve`),
    ).toBe(true);
    expect(apiRequests.every((path) => path.startsWith("/api/v1/trial/"))).toBe(true);

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出 Forecast CSV" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^[0-9a-f]{64}\.csv$/);
    const downloadedPath = await download.path();
    expect(downloadedPath).not.toBeNull();

    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);

    const replayRunIdPromise = page.getByTestId("forecast-run-id").innerText();
    await page.getByRole("button", { name: "生成预测" }).click();
    await expect(page.getByTestId("forecast-run-id")).toHaveText(runId);
    expect(await replayRunIdPromise).toBe(runId);
  });

  test("renders a safe unavailable state when authority cannot be reached", async ({ page }) => {
    await page.route("**/api/v1/trial/forecast-input-authority", (route) => route.abort());
    await page.goto("/trial/forecast");
    await expect(page.getByText("输入权威不可用", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "生成预测" })).toBeDisabled();
    await expect(page.locator("body")).not.toContainText("Error:");
  });

  test("keeps the Forecast page usable on the mobile project", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await createForecast(page);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });
});
