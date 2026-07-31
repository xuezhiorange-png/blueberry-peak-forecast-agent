import { expect, test } from "@playwright/test";

test.describe("frontend-first quality route smoke", () => {
  test("renders import and unavailable quality states", async ({ page }) => {
    const apiRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith("/api/")) apiRequests.push(pathname);
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/trial/quality");
    await expect(page.getByTestId("quality-page")).toBeVisible();
    await expect(page.getByRole("button", { name: "上传并校验" })).toBeDisabled();
    await expect(page.getByText("Quality 生产适配器与逐日 overlay 尚未就绪")).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect(
      apiRequests.every((path) => path.startsWith("/api/v1/trial/")),
      `unexpected API paths: ${apiRequests.join(", ")}`,
    ).toBe(true);
  });

  test("renders without horizontal overflow on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/trial/quality");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });

  test("renders selected file hash without horizontal overflow on mobile", async ({ page }) => {
    const apiRequests: string[] = [];

    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith("/api/")) apiRequests.push(pathname);
    });

    for (const viewport of [
      { width: 390, height: 844 },
      { width: 360, height: 800 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/trial/quality");

      const fileInput = page.getByLabel("选择 CSV 或 XLSX 文件");

      await expect(fileInput).toBeEnabled();

      await fileInput.setInputFiles({
        name: "actual-harvest-mobile.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          [
            "farm_code,variety_code,harvest_date,quantity_kg",
            "FARM-001,DUKE,2026-07-30,125.50",
          ].join("\n"),
          "utf8",
        ),
      });

      await expect(page.getByText("SHA-256 已完成", { exact: true })).toBeVisible();

      const hashValue = page
        .locator('dl[aria-label="文件元数据"]')
        .locator("div")
        .filter({ hasText: "SHA-256" })
        .locator("dd");

      await expect(hashValue).toHaveText(/^[0-9a-f]{64}$/);

      const dimensions = await page.evaluate(() => ({
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
        bodyWidth: document.body.scrollWidth,
      }));

      expect(
        dimensions.documentWidth,
        `${viewport.width}x${viewport.height}: document overflow`,
      ).toBeLessThanOrEqual(dimensions.viewportWidth);

      expect(
        dimensions.bodyWidth,
        `${viewport.width}x${viewport.height}: body overflow`,
      ).toBeLessThanOrEqual(dimensions.viewportWidth);

      await expect(page.getByRole("button", { name: "上传并校验" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "提交导入" })).toBeDisabled();
    }

    expect(apiRequests, `unexpected API requests: ${apiRequests.join(", ")}`).toEqual([]);
  });
});
