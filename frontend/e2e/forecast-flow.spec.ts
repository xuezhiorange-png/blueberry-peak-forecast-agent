import { expect, test } from "@playwright/test";

test.describe("frontend-first forecast route smoke", () => {
  test("renders on desktop and does not call internal APIs", async ({ page }) => {
    const apiRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith("/api/")) apiRequests.push(pathname);
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/trial/forecast");
    await expect(page.getByTestId("forecast-page")).toBeVisible();
    await expect(page.getByRole("button", { name: "生成预测" })).toBeDisabled();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect(
      apiRequests.every((path) => path.startsWith("/api/v1/trial/")),
      `unexpected API paths: ${apiRequests.join(", ")}`,
    ).toBe(true);
  });

  test("supports mobile navigation", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/trial/forecast");
    await page.getByRole("link", { name: "质量" }).click();
    await expect(page.getByTestId("quality-page")).toBeVisible();
  });
});
