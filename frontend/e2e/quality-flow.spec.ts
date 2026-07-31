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
});
