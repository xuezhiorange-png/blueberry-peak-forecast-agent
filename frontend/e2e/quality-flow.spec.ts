import { basename, join } from "node:path";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

type ProjectScopedIdentity = {
  externalBatchId: string;
  externalLogicalRecordId: string;
  externalRevisionId: string;
  sourceNote: string;
  actualQuantityKg: string;
  harvestBusinessDate: string;
};

function safeSlug(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  if (!slug) throw new Error(`Unable to create a safe test identity from ${value}`);
  return slug;
}

function projectScopedIdentity(testInfo: TestInfo, scenario: string): ProjectScopedIdentity {
  const project = safeSlug(testInfo.project.name);
  const scenarioSlug = safeSlug(scenario);
  const projectOrder = project === "chromium-mobile" ? "0" : "1";
  const executionSuffix = `${project}-w${testInfo.workerIndex}-r${testInfo.retry}`;
  return {
    externalBatchId: `trial-harvest-${scenarioSlug}-${executionSuffix}`,
    externalLogicalRecordId: `frontend-e2e-${scenarioSlug}-${projectOrder}-${executionSuffix}-row-1`,
    externalRevisionId: `frontend-e2e-${scenarioSlug}-${projectOrder}-${executionSuffix}-rev-1`,
    sourceNote: `frontend-e2e-${scenarioSlug}-${project}`,
    actualQuantityKg: project === "chromium-mobile" ? "6.000000" : "5.000000",
    harvestBusinessDate: project === "chromium-mobile" ? "2026-03-14" : "2026-03-08",
  };
}

function xlsxPathForProject(testInfo: TestInfo): string {
  const directory = process.env.FRONTEND_E2E_XLSX_DIR;
  if (!directory) throw new Error("FRONTEND_E2E_XLSX_DIR is required for real XLSX acceptance");
  return join(directory, `frontend-e2e-${safeSlug(testInfo.project.name)}.xlsx`);
}

function xlsxExternalBatchIdForProject(testInfo: TestInfo): string {
  return `trial-harvest-xlsx-${safeSlug(testInfo.project.name)}`;
}

function qualityObservationCutoffForProject(testInfo: TestInfo, offsetDays = 0): string {
  const day = (safeSlug(testInfo.project.name) === "chromium-mobile" ? 2 : 1) + offsetDays;
  return `2030-01-${String(day).padStart(2, "0")}T00:00`;
}

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

function qualityCsv(identity: ProjectScopedIdentity) {
  return [
    csvHeaders,
    [
      identity.externalLogicalRecordId,
      identity.externalRevisionId,
      "trial-api",
      identity.externalBatchId,
      identity.harvestBusinessDate,
      "farm-1",
      "sub-1",
      "var-1",
      identity.actualQuantityKg,
      `${identity.harvestBusinessDate}T10:00:00+00:00`,
      "TRUSTED_SOURCE_TIMESTAMP",
      "farm-source",
      "1",
      "ACTIVE",
      "",
      "2026-DEMO",
      "Asia/Shanghai",
      `${identity.harvestBusinessDate}T10:00:00+00:00`,
      "",
      identity.sourceNote,
    ].join(","),
  ].join("\n");
}

function validationFailureCsv(identity: ProjectScopedIdentity, rowCount = 101) {
  const rows = Array.from({ length: rowCount }, (_, index) => {
    const logicalId = `${identity.externalLogicalRecordId}-${index + 1}`;
    const revisionId = `${identity.externalRevisionId}-${index + 1}`;
    return [
      logicalId,
      revisionId,
      "trial-api",
      identity.externalBatchId,
      identity.harvestBusinessDate,
      `unknown-farm-${safeSlug(identity.externalBatchId)}-${index + 1}`,
      `unknown-subfarm-${index + 1}`,
      `unknown-variety-${index + 1}`,
      "5.000000",
      `${identity.harvestBusinessDate}T10:00:00+00:00`,
      "TRUSTED_SOURCE_TIMESTAMP",
      "farm-source",
      "1",
      "ACTIVE",
      "",
      "2026-DEMO",
      "Asia/Shanghai",
      `${identity.harvestBusinessDate}T10:00:00+00:00`,
      "",
      `${identity.sourceNote}-${index + 1}`,
    ].join(",");
  });
  return [csvHeaders, ...rows].join("\n");
}

async function selectCsvFile(
  page: Page,
  identity: ProjectScopedIdentity,
  contents = qualityCsv(identity),
  fileName = `${identity.externalBatchId}.csv`,
) {
  await page.getByLabel("选择 CSV 或 XLSX 文件").setInputFiles({
    name: fileName,
    mimeType: "text/csv",
    buffer: Buffer.from(contents, "utf8"),
  });
  await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();
  await page.getByLabel("external batch id").fill(identity.externalBatchId);
  await expect(page.getByLabel("external batch id")).toHaveValue(identity.externalBatchId);
}

async function uploadAndCommitCsv(page: Page, identity: ProjectScopedIdentity, testInfo: TestInfo) {
  const contents = qualityCsv(identity);
  const project = safeSlug(testInfo.project.name);
  expect(identity.externalBatchId).toContain(project);
  expect(identity.sourceNote).toContain(project);
  expect(contents).toContain(identity.externalBatchId);
  expect(contents).toContain(identity.externalLogicalRecordId);
  expect(contents).toContain(identity.externalRevisionId);
  await selectCsvFile(page, identity, contents);
  await page.getByRole("button", { name: "上传并校验" }).click();
  const lifecycle = page.locator('[aria-label="实际采摘导入生命周期"]');
  await expect(lifecycle).toContainText("VALIDATED", { timeout: 30_000 });
  const commitButton = page.getByRole("button", { name: "提交导入" });
  await expect(commitButton).toBeEnabled({ timeout: 30_000 });
  await commitButton.click();
  await expect(lifecycle.locator(".lifecycle-step.active")).toContainText("COMMITTED", {
    timeout: 30_000,
  });
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

async function createQualityReport(page: Page, runId: string, testInfo: TestInfo) {
  await page.goto("/trial/quality");
  await uploadAndCommitCsv(page, projectScopedIdentity(testInfo, "quality-csv"), testInfo);
  await page.getByLabel("Forecast public run ID").fill(runId);
  await page.getByRole("button", { name: "读取 Forecast" }).click();
  await expect(page.getByLabel("Persisted Forecast cutoff")).not.toHaveValue("—");
  const labelObservationCutoff = qualityObservationCutoffForProject(testInfo);
  await page.getByLabel("Label observation cutoff").fill(labelObservationCutoff);
  await expect(page.getByLabel("Label observation cutoff")).toHaveValue(labelObservationCutoff);
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
  for (const horizon of [7, 14, 21]) {
    await page.getByRole("tab", { name: `${horizon} 天` }).click();
    await expect(page.getByLabel(`质量指标 ${horizon} 天`)).toBeVisible();
    await expect(page.getByText(`${horizon} 天`, { exact: true })).toBeVisible();
  }
  return page.locator('[aria-label="质量报告身份"] .hash-value').innerText();
}

test.describe("production Actual Harvest and Quality Trial integration", () => {
  test("uploads raw CSV, commits it, creates persisted Quality, and exports CSV", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const apiRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith("/api/")) apiRequests.push(pathname);
    });

    const runId = await createForecastForQuality(page);
    const reportId = await createQualityReport(page, runId, testInfo);
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

    const firstIdempotencyEntry = await page.evaluate(() => {
      const entry = Object.entries(sessionStorage).find(([key]) =>
        key.startsWith("trial:idempotency:quality-report|"),
      );
      if (!entry) throw new Error("Quality idempotency key was not persisted");
      return entry;
    });
    const changedLabelCutoff = qualityObservationCutoffForProject(testInfo, 2);
    const conflictingScopeKey = await page.evaluate(
      ({ firstKey, nextLabelCutoff }) => {
        const parts = firstKey.split("|");
        if (parts.length !== 6) throw new Error("Unexpected Quality idempotency scope");
        parts[4] = new Date(nextLabelCutoff).toISOString();
        return parts.join("|");
      },
      { firstKey: firstIdempotencyEntry[0], nextLabelCutoff: changedLabelCutoff },
    );
    await page.getByLabel("Label observation cutoff").fill(changedLabelCutoff);
    await page.evaluate(({ storageKey, value }) => sessionStorage.setItem(storageKey, value), {
      storageKey: conflictingScopeKey,
      value: firstIdempotencyEntry[1],
    });
    await page.getByRole("button", { name: "生成质量报告" }).click();
    await expect(page.getByRole("alert")).toContainText("相同请求标识对应了不同内容");
    await expect(page.locator('[aria-label="质量报告身份"] .hash-value')).toHaveCount(0);
    await expect(page.getByRole("button", { name: "导出质量 CSV" })).toBeDisabled();

    await page.evaluate((storageKey) => sessionStorage.removeItem(storageKey), conflictingScopeKey);
    await page.getByRole("button", { name: "生成质量报告" }).click();
    const secondReportId = page.locator('[aria-label="质量报告身份"] .hash-value');
    await expect(secondReportId).toHaveText(/^[0-9a-f]{64}$/);
    await expect(secondReportId).not.toHaveText(firstReportId);

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出质量 CSV" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`${await secondReportId.innerText()}.csv`);
    expect(await download.path()).not.toBeNull();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });

  test("accepts and commits a real XLSX upload", async ({ page }, testInfo) => {
    const xlsxPath = xlsxPathForProject(testInfo);
    await page.goto("/trial/quality");
    await page.getByLabel("选择 CSV 或 XLSX 文件").setInputFiles(xlsxPath);
    await expect(
      page.getByRole("region", { name: "实际采摘文件导入" }).getByRole("strong"),
    ).toHaveText(basename(xlsxPath));
    await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();
    const externalBatchId = xlsxExternalBatchIdForProject(testInfo);
    await page.getByLabel("external batch id").fill(externalBatchId);
    await expect(page.getByLabel("external batch id")).toHaveValue(externalBatchId);
    await page.getByRole("button", { name: "上传并校验" }).click();
    const lifecycle = page.locator('[aria-label="实际采摘导入生命周期"]');
    await expect(lifecycle).toContainText("VALIDATED", { timeout: 30_000 });
    const commitButton = page.getByRole("button", { name: "提交导入" });
    await expect(commitButton).toBeEnabled({ timeout: 30_000 });
    await commitButton.click();
    await expect(lifecycle.locator(".lifecycle-step.active")).toContainText("COMMITTED", {
      timeout: 30_000,
    });
  });

  test("keeps the import and quality surfaces within a mobile viewport", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/trial/quality");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    const identity = projectScopedIdentity(testInfo, "quality-mobile-preview");
    await page.getByLabel("选择 CSV 或 XLSX 文件").setInputFiles({
      name: `${identity.externalBatchId}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from(qualityCsv(identity), "utf8"),
    });
    await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });

  test("rejects an unsafe filename through the real upload endpoint", async ({
    page,
  }, testInfo) => {
    const identity = projectScopedIdentity(testInfo, "unsafe-filename");
    await page.goto("/trial/quality");
    await selectCsvFile(page, identity);
    await page.route("**/api/v1/trial/actual-harvest/imports/*/upload", async (route) => {
      const headers = { ...route.request().headers(), "x-file-name": "../unsafe.csv" };
      await route.continue({ headers });
    });
    await page.getByRole("button", { name: "上传并校验" }).click();
    await expect(page.getByRole("alert")).toContainText("文件名不符合安全要求");
  });

  test("rejects an unsupported MIME through the real upload endpoint", async ({
    page,
  }, testInfo) => {
    const identity = projectScopedIdentity(testInfo, "unsupported-mime");
    await page.goto("/trial/quality");
    await selectCsvFile(page, identity);
    await page.route("**/api/v1/trial/actual-harvest/imports/*/upload", async (route) => {
      const headers = { ...route.request().headers(), "content-type": "application/octet-stream" };
      await route.continue({ headers });
    });
    await page.getByRole("button", { name: "上传并校验" }).click();
    await expect(page.getByRole("alert")).toContainText("文件类型不受支持");
  });

  test("rejects an oversized upload through the real server", async ({ page }, testInfo) => {
    const identity = projectScopedIdentity(testInfo, "oversized-upload");
    await page.goto("/trial/quality");
    await selectCsvFile(
      page,
      identity,
      "external_logical_record_id,\n" + "x".repeat(10 * 1024 * 1024 + 1),
    );
    await page.getByRole("button", { name: "上传并校验" }).click();
    await expect(page.getByRole("alert")).toContainText("文件超过允许大小", { timeout: 30_000 });
  });

  test("reads all validation-failed rows across real server pages and disables commit", async ({
    page,
  }, testInfo) => {
    const identity = projectScopedIdentity(testInfo, "validation-failed-pages");
    const errorRequests: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.endsWith("/errors")) errorRequests.push(request.url());
    });
    await page.goto("/trial/quality");
    await selectCsvFile(page, identity, validationFailureCsv(identity));
    await page.getByRole("button", { name: "上传并校验" }).click();
    const lifecycle = page.locator('[aria-label="实际采摘导入生命周期"]');
    await expect(lifecycle).toContainText("VALIDATION_FAILED", { timeout: 60_000 });
    const invalidRows = page.locator('[aria-label="服务端 invalid rows"] .result-line');
    await expect(invalidRows).toHaveCount(101, { timeout: 60_000 });
    expect(errorRequests.length).toBeGreaterThanOrEqual(2);
    for (const url of errorRequests) {
      expect(new URL(url).searchParams.get("page_size")).toBe("100");
    }
    await expect(page.getByRole("button", { name: "提交导入" })).toBeDisabled();
  });

  test("keeps concealed import not-found responses safe for a public ID", async ({ page }) => {
    await page.goto("/trial/quality");
    const publicId = "e".repeat(64);
    const result = await page.evaluate(async (importId) => {
      const response = await fetch(`/api/v1/trial/actual-harvest/imports/${importId}`);
      return { status: response.status, body: (await response.json()) as Record<string, unknown> };
    }, publicId);
    expect(result.status).toBe(404);
    expect(result.body.code).toBe("RESOURCE_NOT_FOUND");
    const encoded = JSON.stringify(result.body);
    expect(encoded).not.toMatch(/owner|database|traceback|exception|stack/i);
    expect(encoded).not.toContain(publicId);
  });
});
