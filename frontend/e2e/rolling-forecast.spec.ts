import { test as base, expect } from "@playwright/test";
import { httpsFixture } from "./support/https-fixture";

const test = base.extend<object, { https: string }>({ https: httpsFixture("rolling_pg") });
test.use({ ignoreHTTPSErrors: true });

test("real login issue immutable saved curves two origins comparison and logout", async ({
  page,
  https,
}, info) => {
  await page.goto(https + "/dashboard/forecast");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-user");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("button", { name: "查询研究预测" }).click();
  await expect(page.getByLabel("研究基地")).toContainText("SYNTHETIC_BASE");
  await page.getByLabel("Origin 日期").fill("2026-11-05");
  let response = page.waitForResponse(
    (r) => r.url().endsWith("/rolling-forecast-runs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "生成并保存研究预测" }).click();
  const firstResponse = await response;
  expect(firstResponse.status()).toBe(200);
  const first = (await firstResponse.json()).data;
  const result = page.getByRole("region", { name: "滚动预测结果" });
  await expect(result).toContainText(first.result.models.M1.H15.forecast_total_kg);
  await expect(result).toContainText("特征观测口径：FIELD_HARVEST_WEIGHT");
  await expect(result).toContainText("训练目标口径：FIELD_HARVEST_WEIGHT");
  await expect(result).toContainText("预测目标口径：FIELD_HARVEST_WEIGHT");
  await expect(result).toContainText("SYNTHETIC_TEST_FIXTURE");
  expect(first.result.models.M1.H7.forecast_total_kg).toBe("538.941049");
  expect(first.result.models.M1.H15.forecast_total_kg).toBe("1031.362335");
  await expect(result.getByRole("table").nth(1).locator("tbody tr")).toHaveCount(15);
  await expect(result.getByRole("table").nth(1)).toContainText(
    first.result.models.M1.daily_forecast_kg[0].kg,
  );
  await page.screenshot({
    path: info.outputPath("SYNTHETIC-rolling-prediction.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "查询研究预测" }).click();
  await page.getByLabel("Origin 日期").fill("2026-11-06");
  await page.getByLabel("观测快照").selectOption("1");
  response = page.waitForResponse(
    (r) => r.url().endsWith("/rolling-forecast-runs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "生成并保存研究预测" }).click();
  const secondResponse = await response;
  expect(secondResponse.status()).toBe(200);
  const second = (await secondResponse.json()).data;
  expect(second.result.models.M1.H7.forecast_total_kg).toBe("526.137595");
  expect(second.result.models.M1.H15.forecast_total_kg).toBe("1002.702182");
  expect(second.input_hash).not.toBe(first.input_hash);
  await page.getByRole("button", { name: "查询研究预测" }).click();
  await page.getByLabel("比较起点").selectOption(String(first.run_id));
  await page.getByLabel("比较终点").selectOption(String(second.run_id));
  await page.getByRole("button", { name: "比较两个研究 Origin" }).click();
  const comparison = page.getByRole("region", { name: "研究 Origin 对比" });
  await expect(comparison).toContainText("COMPARABLE");
  await expect(comparison.getByRole("table").nth(1).locator("tbody tr")).toHaveCount(14);
  await page.screenshot({
    path: info.outputPath("SYNTHETIC-rolling-comparison.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(comparison).not.toBeVisible();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
});

test("admin has no default research data permission", async ({ page, https }) => {
  await page.goto(https + "/dashboard/forecast");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const response = page.waitForResponse((r) => r.url().includes("/rolling-forecast-runs"));
  await page.getByRole("button", { name: "查询研究预测" }).click();
  expect((await response).status()).toBe(403);
  await expect(page.getByRole("region", { name: "滚动预测结果" })).not.toBeVisible();
});
