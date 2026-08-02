import { expect, test, type Page } from "@playwright/test";

const csvHeaders = [
  "external_logical_record_id",
  "external_revision_id",
  "source_system",
  "external_batch_id",
  "harvest_business_date",
  "farm_code",
  "subfarm_or_plot_code",
  "variety_code",
  "actual_harvest_quantity_kg",
  "source_recorded_at",
  "source_recorded_at_authority_status",
  "source_recorded_at_authority_reference_or_null",
  "revision_number",
  "record_status",
  "supersedes_external_revision_id",
  "season_code",
  "farm_timezone",
  "revised_at",
  "finalized_at",
  "source_note",
].join(",");

function qualityCsv(batchId = "trial-harvest-batch") {
  return [
    csvHeaders,
    [
      "frontend-e2e-row-1",
      "frontend-e2e-rev-1",
      "trial-api",
      batchId,
      "2026-03-08",
      "farm-1",
      "sub-1",
      "var-1",
      "5.000000",
      "2026-03-08T10:00:00+00:00",
      "TRUSTED_SOURCE_TIMESTAMP",
      "farm-source",
      "1",
      "ACTIVE",
      "",
      "2026-DEMO",
      "Asia/Shanghai",
      "2026-03-08T10:00:00+00:00",
      "",
      "frontend-e2e",
    ].join(","),
  ].join("\n");
}

async function uploadAndCommitCsv(page: Page, batchId = "trial-harvest-batch") {
  await page.getByLabel("选择 CSV 或 XLSX 文件").setInputFiles({
    name: `${batchId}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(qualityCsv(batchId), "utf8"),
  });
  await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();
  await page.getByLabel("external batch id").fill(batchId);
  await page.getByRole("button", { name: "上传并校验" }).click();
  const lifecycle = page.locator('[aria-label="实际采摘导入生命周期"]');
  await expect(lifecycle).toContainText("VALIDATED", { timeout: 30_000 });
  const commitButton = page.getByRole("button", { name: "提交导入" });
  await expect(commitButton).toBeEnabled({ timeout: 30_000 });
  await commitButton.click();
  await expect(lifecycle).toContainText("COMMITTED", { timeout: 30_000 });
}

async function createForecastForQuality(page: Page): Promise<string> {
  await page.goto("/trial/forecast");
  await expect(page.getByLabel("加工厂")).toHaveValue("S2-FIXTURE");
  await page.getByLabel("产季").selectOption("2026-DEMO");
  await page.getByLabel("农场").selectOption("s2-fixture-farm");
  await page.getByLabel("分场").selectOption("s2-fixture-east");
  await page.getByLabel("品种").selectOption("S2-VAR-A");
  await page.getByLabel("我确认使用服务端权威面积").check();
  await page.getByRole("button", { name: "生成预测" }).click();
  const runId = page.getByTestId("forecast-run-id");
  await expect(runId).toHaveText(/^[0-9a-f]{64}$/);
  return runId.innerText();
}

async function createQualityReport(page: Page, runId: string) {
  await page.goto("/trial/quality");
  await uploadAndCommitCsv(page);
  await page.getByLabel("Forecast public run ID").fill(runId);
  await page.getByRole("button", { name: "读取 Forecast" }).click();
  await expect(page.getByLabel("Persisted Forecast cutoff")).not.toHaveValue("—");
  await page.getByRole("button", { name: "生成质量报告" }).click();
  await expect(page.getByText("Quality report ID", { exact: true })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByRole("tab", { name: "7 天" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "14 天" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "21 天" })).toBeVisible();
  await expect(page.getByText("P80 状态 / 原因", { exact: true })).toBeVisible();
  await expect(page.getByText("P90 状态 / 原因", { exact: true })).toBeVisible();
  await expect(page.getByText("区间下界", { exact: true })).toBeVisible();
  await expect(page.getByText("Persisted baseline comparison", { exact: true })).toBeVisible();
  return page.locator('[aria-label="质量报告身份"] .hash-value').innerText();
}

test.describe("production Actual Harvest and Quality Trial integration", () => {
  test("uploads raw CSV, commits it, creates persisted Quality, and exports CSV", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const apiRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith("/api/")) apiRequests.push(pathname);
    });

    const runId = await createForecastForQuality(page);
    const reportId = await createQualityReport(page, runId);
    expect(reportId).toMatch(/^[0-9a-f]{64}$/);
    expect(apiRequests).toContain("/api/v1/trial/actual-harvest/imports");
    expect(apiRequests.some((path) => path.includes("/upload"))).toBe(true);
    expect(apiRequests.some((path) => path.includes("/commit"))).toBe(true);
    expect(apiRequests.some((path) => path === "/api/v1/trial/quality-reports")).toBe(true);
    expect(apiRequests.some((path) => path.includes(`/quality-reports/${reportId}`))).toBe(true);
    expect(apiRequests.every((path) => path.startsWith("/api/v1/trial/"))).toBe(true);

    const firstReportId = reportId;
    await page.getByRole("button", { name: "生成质量报告" }).click();
    await expect(page.locator('[aria-label="质量报告身份"] .hash-value')).toHaveText(firstReportId);

    await page.getByLabel("Label observation cutoff").fill("2026-03-11T12:00");
    await page.getByRole("button", { name: "生成质量报告" }).click();
    await expect(page.getByRole("alert")).toContainText("质量链路未完成");

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出质量 CSV" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`${firstReportId}.csv`);
    expect(await download.path()).not.toBeNull();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });

  test("accepts and commits a real XLSX upload", async ({ page }) => {
    const xlsxPath = process.env.FRONTEND_E2E_XLSX;
    if (!xlsxPath) throw new Error("FRONTEND_E2E_XLSX is required for the real XLSX acceptance");
    await page.goto("/trial/quality");
    await page.getByLabel("选择 CSV 或 XLSX 文件").setInputFiles(xlsxPath);
    await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "上传并校验" }).click();
    const lifecycle = page.locator('[aria-label="实际采摘导入生命周期"]');
    await expect(lifecycle).toContainText("VALIDATED", { timeout: 30_000 });
    const commitButton = page.getByRole("button", { name: "提交导入" });
    await expect(commitButton).toBeEnabled({ timeout: 30_000 });
    await commitButton.click();
    await expect(lifecycle).toContainText("COMMITTED", { timeout: 30_000 });
  });

  test("keeps the import and quality surfaces within a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/trial/quality");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.getByLabel("选择 CSV 或 XLSX 文件").setInputFiles({
      name: "mobile.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(qualityCsv("mobile-batch"), "utf8"),
    });
    await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });
});
