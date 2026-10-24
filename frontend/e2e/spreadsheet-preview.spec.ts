import { test as base, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { httpsFixture } from "./support/https-fixture";

const test = base.extend<object, { https: string }>({ https: httpsFixture("pre_data_pg") });
test.use({ ignoreHTTPSErrors: true });

async function enter(page: Page, https: string) {
  await page.goto(https + "/dashboard/forecast");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-user");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("button", { name: "电子表格准备", exact: true }).click();
}
async function mappedExample(page: Page, format: "xlsx" | "csv" = "xlsx") {
  await page.getByLabel("示例格式").selectOption(format);
  await page.getByRole("button", { name: "加载合成示例", exact: true }).click();
  await expect(page.getByRole("table", { name: "本地列检查" })).toBeVisible();
  await page.getByRole("button", { name: "应用合成示例列建议" }).click();
  await page.getByLabel("声明重量单位").selectOption("kg");
  await page.getByLabel("声明业务口径").selectOption("RECORDED_INBOUND_WEIGHT");
  await expect(page.getByRole("button", { name: "核验固定合成来源" })).toBeEnabled();
}

test("local CSV mapping quality has no server upload and cannot issue arbitrary file", async ({
  page,
  https,
}, info) => {
  await enter(page, https);
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") requests.push(r.url());
  });
  await page.getByLabel("选择电子表格").setInputFiles({
    name: "用户自定列.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "说明\n哪一天,哪基地,几公斤,业务编号\n2026-11-01,测试基地,0,r1\n2026-11-02,,,r1\n2026-02-30,测试基地,abc,r2",
    ),
  });
  await expect(page.getByLabel("表头所在行")).toBeVisible();
  await page.getByLabel("表头所在行").fill("2");
  for (const [label, index] of [
    ["业务日期", 0],
    ["基地", 1],
    ["记录重量", 2],
    ["记录 ID（可选）", 3],
  ] as const)
    await page.getByLabel(label, { exact: true }).selectOption(String(index));
  await expect(
    page.getByText("本地文件预览，尚未核验来源权威。空白不是 0 kg；缺失日期不会补零。"),
  ).toBeVisible();
  await expect(page.getByRole("table", { name: "本地内容预览 · 最多50行" })).toContainText("abc");
  await expect(page.getByRole("button", { name: "核验固定合成来源" })).toBeDisabled();
  expect(requests).toEqual([]);
  await page.screenshot({
    path: info.outputPath("SYNTHETIC-local-mapping-quality.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "清空文件与预测" }).click();
  await expect(page.getByRole("table", { name: "本地列检查" })).not.toBeVisible();
});

test("bound multischeet XLSX computes saves reloads compares and exports actual forecast", async ({
  page,
  https,
}, info) => {
  await enter(page, https);
  await mappedExample(page);
  await expect(page.getByLabel("工作表")).toContainText("说明");
  await expect(page.getByLabel("工作表")).toContainText("合成入库明细");
  await expect(page.getByLabel("表头所在行")).toHaveValue("3");
  await page.getByLabel("工作表").selectOption("0");
  await expect(page.getByRole("table", { name: "本地列检查" })).toContainText(
    "SYNTHETIC_TEST_FIXTURE",
  );
  await expect(page.getByRole("button", { name: "核验固定合成来源" })).toBeDisabled();
  await page.getByLabel("工作表").selectOption("1");
  await page.getByLabel("表头所在行").fill("3");
  await page.getByRole("button", { name: "应用合成示例列建议" }).click();
  await expect(page.getByRole("button", { name: "核验固定合成来源" })).toBeEnabled();
  await page.screenshot({ path: info.outputPath("SYNTHETIC-xlsx-mapping.png"), fullPage: true });
  await page.getByRole("button", { name: "核验固定合成来源" }).click();
  await expect(page.getByLabel("合成来源检查结果")).toContainText("SYNTHETIC_FULL_VALIDATED");
  let response = page.waitForResponse((r) => r.url().endsWith("spreadsheet-demo/issue"));
  await page.getByRole("button", { name: "计算并保存合成预测" }).click();
  const first = (await (await response).json()).data;
  expect(first.result.models.M1.H7.forecast_total_kg).toBe("538.941049");
  expect(first.result.models.M1.H15.forecast_total_kg).toBe("1031.362335");
  const result = page.getByRole("region", { name: "滚动预测结果" });
  await expect(result).toContainText("1031.362335");
  await expect(result.getByRole("table").nth(1).locator("tbody tr")).toHaveCount(15);
  await page.screenshot({ path: info.outputPath("SYNTHETIC-saved-forecast.png"), fullPage: true });
  await page.getByLabel("合成预测 Origin").selectOption("2026-11-06");
  await expect(result).not.toBeVisible();
  response = page.waitForResponse((r) => r.url().endsWith("spreadsheet-demo/issue"));
  await page.getByRole("button", { name: "计算并保存合成预测" }).click();
  const second = (await (await response).json()).data;
  expect(second.result.models.M1.H7.forecast_total_kg).toBe("526.137595");
  expect(second.result.models.M1.H15.forecast_total_kg).toBe("1002.702182");
  const comparison = page.getByRole("region", { name: "研究 Origin 对比" });
  await expect(comparison.getByRole("table").nth(1).locator("tbody tr")).toHaveCount(14);
  await page.getByLabel("查看已保存合成 Origin").selectOption(String(second.run_id));
  await expect(result).toContainText("1002.702182");
  await page.getByLabel("查看已保存合成 Origin").selectOption(String(first.run_id));
  await expect(result).toContainText("1031.362335");
  for (const [label, expected] of [
    ["导出业务报告 HTML", "forecast-report.html"],
    ["导出每日预测 CSV", "forecast-daily.csv"],
  ]) {
    const downloading = page.waitForEvent("download");
    await page.getByRole("button", { name: label }).click();
    const download = await downloading;
    expect(download.suggestedFilename()).toBe(expected);
    const content = await readFile((await download.path())!, "utf8");
    expect(content).toContain(first.result_hash);
    expect(content).toContain("538.941049");
    expect(content).not.toContain("manifest_path");
    await download.saveAs(info.outputPath(expected));
  }
  await page.screenshot({
    path: info.outputPath("SYNTHETIC-origin-comparison.png"),
    fullPage: true,
  });
  // Changing any file/mapping context invalidates old quantities and exports.
  await page.getByLabel("业务日期", { exact: true }).selectOption("");
  await expect(result).not.toBeVisible();
  await expect(page.getByRole("button", { name: "导出业务报告 HTML" })).not.toBeVisible();
});

test("bound CSV works and missing late or wrong-basis packages do not issue M1", async ({
  page,
  https,
}) => {
  await enter(page, https);
  await mappedExample(page, "csv");
  await expect(page.getByLabel("表头所在行")).toHaveValue("1");
  await page.getByRole("button", { name: "核验固定合成来源" }).click();
  await expect(page.getByRole("button", { name: "计算并保存合成预测" })).toBeEnabled();
  for (const scenario of ["missing-day", "late-record", "basis-conflict"]) {
    await page.getByLabel("合成场景").selectOption(scenario);
    await mappedExample(page, "csv");
    await page.getByRole("button", { name: "核验固定合成来源" }).click();
    await expect(page.getByLabel("合成来源检查结果")).toContainText("NOT_COMPUTABLE");
    await expect(page.getByRole("button", { name: "计算并保存合成预测" })).toBeDisabled();
  }
});

test("late export is discarded after clear and logout removes preview state", async ({
  page,
  https,
}) => {
  await enter(page, https);
  await mappedExample(page, "csv");
  await page.getByRole("button", { name: "核验固定合成来源" }).click();
  await page.getByRole("button", { name: "计算并保存合成预测" }).click();
  await expect(page.getByRole("region", { name: "滚动预测结果" })).toBeVisible();
  let release!: () => void;
  const wait = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/rolling-forecast-runs/*/report?*", async (route) => {
    const response = await route.fetch();
    await wait;
    try {
      await route.fulfill({ response });
    } catch {
      /* cancelled request */
    }
  });
  let downloaded = false;
  page.on("download", () => {
    downloaded = true;
  });
  await page.getByRole("button", { name: "导出业务报告 HTML" }).click();
  await page.getByRole("button", { name: "清空文件与预测" }).click();
  release();
  await expect(page.getByRole("region", { name: "滚动预测结果" })).not.toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  expect(downloaded).toBe(false);
});
