import { test as base, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { httpsFixture } from "./support/https-fixture";

const test = base.extend<object, { https: string }>({ https: httpsFixture("pre_data_pg") });
test.use({ ignoreHTTPSErrors: true });
async function enter(page: Page, https: string) {
  await page.goto(https + "/dashboard/forecast");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-user");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("button", { name: "电子表格准备", exact: true }).click();
  await page.getByRole("tab", { name: "历史农事数据" }).click();
}
async function sample(page: Page, scenario = "wide", format = "xlsx") {
  await page.getByLabel("农事合成场景").selectOption(scenario);
  await page.getByLabel("农事示例格式").selectOption(format);
  await page.getByRole("button", { name: "加载农事合成示例" }).click();
  await expect(page.getByRole("button", { name: "应用农事合成映射建议" })).toBeEnabled();
  await page.getByRole("button", { name: "应用农事合成映射建议" }).click();
  await expect(page.getByRole("button", { name: "规范化并检查农事数据" })).toBeEnabled();
}
async function prepare(page: Page) {
  await page.getByRole("button", { name: "规范化并检查农事数据" }).click();
  await expect(page.getByRole("button", { name: "下载 agronomic-preparation.json" })).toBeVisible();
}
async function jsonDownload(page: Page) {
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 agronomic-preparation.json" }).click();
  const d = await waiting;
  return { download: d, data: JSON.parse(await readFile((await d.path())!, "utf8")) };
}

test("V0_20 wide XLSX normalizes three real sheets and exports reproducible five-file package locally", async ({
  page,
  https,
}, info) => {
  await enter(page, https);
  const posted: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") posted.push(r.url());
  });
  await sample(page);
  await expect(page.getByLabel("农事工作表")).toContainText("说明");
  await expect(page.getByLabel("农事表头行")).toHaveValue("3");
  await page.screenshot({ path: info.outputPath("V0_20-SYNTHETIC-mapping.png"), fullPage: true });
  await prepare(page);
  const first = await jsonDownload(page),
    p = first.data;
  expect(p.summary.kind_counts).toEqual({ AREA: 18, EVENT: 36, PHENOLOGY: 36 });
  expect(p.summary.base_count).toBe(2);
  expect(p.summary.variety_count).toBe(2);
  expect(p.summary.season_counts).toEqual({ "2023-2024": 45, "2024-2025": 45 });
  expect(p.data_class).toBe("SYNTHETIC_TEST_FIXTURE");
  expect(
    p.records
      .filter(
        (r: { phenology?: { production_plan_field?: string; canonical_stage?: string } }) =>
          r.phenology?.production_plan_field,
      )
      .every((r: { phenology: { canonical_stage: null } }) => r.phenology.canonical_stage === null),
  ).toBe(true);
  expect(p.restrictions.model_use_authorized).toBe(false);
  await first.download.saveAs(info.outputPath("agronomic-preparation.json"));
  for (const name of [
    "agronomic-area.csv",
    "agronomic-events.csv",
    "agronomic-phenology.csv",
    "agronomic-quality-report.html",
  ]) {
    const waiting = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载 " + name, exact: true }).click();
    const d = await waiting,
      bytes = await readFile((await d.path())!);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(p.artifact_sha256[name]);
    await d.saveAs(info.outputPath(name));
  }
  await expect(
    page.frameLocator("iframe").getByRole("heading", { name: "V0.20 蓝莓历史农事数据准备报告" }),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("V0_20-SYNTHETIC-overview.png"), fullPage: true });
  await prepare(page);
  expect((await jsonDownload(page)).data).toEqual(p);
  await expect(page.getByLabel("选择准备版本").locator("option")).toHaveCount(2);
  expect(posted).toEqual([]);
});

test("V0_20 English long XLSX and CSV preserve two-season area kinds without uploading", async ({
  page,
  https,
}, info) => {
  await enter(page, https);
  await sample(page, "long");
  await expect(page.getByLabel("农事表头行")).toHaveValue("1");
  await prepare(page);
  expect((await jsonDownload(page)).data.summary.kind_counts).toEqual({
    AREA: 18,
    EVENT: 36,
    PHENOLOGY: 36,
  });
  await sample(page, "long", "csv");
  await expect(
    page.getByRole("button", { name: "下载 agronomic-preparation.json" }),
  ).not.toBeVisible();
  await prepare(page);
  const p = (await jsonDownload(page)).data;
  expect(p.summary.kind_counts).toEqual({ AREA: 18, EVENT: 0, PHENOLOGY: 0 });
  expect(
    p.records.filter((r: { area: { basis: string } }) => r.area.basis === "PRODUCTIVE"),
  ).toHaveLength(6);
  await page.screenshot({ path: info.outputPath("V0_20-SYNTHETIC-long-csv.png"), fullPage: true });
});

test("V0_20 arbitrary Chinese CSV manual mapping retains missing area and source identities without authority", async ({
  page,
  https,
}, info) => {
  await enter(page, https);
  const posted: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") posted.push(r.url());
  });
  await page.getByLabel("选择农事电子表格").setInputFiles({
    name: "V0_20-合成人工列.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "合成说明\n哪个基地,哪个农场,分场键,原地块,哪个品种,哪一季,面积是什么,多少,什么单位,何时开始,何时结束\n测试基地,测试农场,分场甲,来源地块甲,测试品种,2023-2024,PLANTED,100,亩,2023-07-01,2024-06-30\n测试基地,测试农场,分场甲,来源地块甲,测试品种,2023-2024,PRODUCTIVE,,亩,2023-07-01,2024-06-30",
    ),
  });
  await expect(page.getByLabel("农事表头行")).toBeVisible();
  await page.getByLabel("农事表头行").fill("2");
  await page.getByLabel("表格布局").selectOption("LONG");
  for (const [label, index] of [
    ["基地来源编码", 0],
    ["农场来源编码", 1],
    ["分场来源编码", 2],
    ["原始地块标识", 3],
    ["品种来源编码", 4],
    ["产季", 5],
    ["长表面积口径", 6],
    ["长表面积数值", 7],
    ["面积单位", 8],
    ["面积生效开始", 9],
    ["面积生效结束", 10],
  ] as const)
    await page
      .getByRole("region", { name: "V0.20 历史农事准备" })
      .getByLabel(label, { exact: true })
      .selectOption(String(index));
  await page.getByRole("button", { name: "加入或更新本表映射" }).click();
  await prepare(page);
  const p = (await jsonDownload(page)).data;
  expect(p.data_class).toBe("USER_FILE_PREVIEW_UNVERIFIED");
  expect(p.records.map((r: { area: { value: string | null } }) => r.area.value)).toEqual([
    "100.000000",
    null,
  ]);
  expect(
    p.records.every(
      (r: { scope: { resolved: null; plot_authority_id: null } }) =>
        r.scope.resolved === null && r.scope.plot_authority_id === null,
    ),
  ).toBe(true);
  expect(p.summary.issue_counts.AREA_VALUE_MISSING).toBe(1);
  expect(posted).toEqual([]);
  await page.screenshot({
    path: info.outputPath("V0_20-UNVERIFIED-manual-mapping.png"),
    fullPage: true,
  });
});

test("V0_20 negative records remain visible, version edits invalidate results and explicit old versions stay immutable", async ({
  page,
  https,
}, info) => {
  await enter(page, https);
  await sample(page, "negative");
  await prepare(page);
  const p = (await jsonDownload(page)).data;
  for (const code of [
    "FORCING_METHOD_UNRESOLVED",
    "DUPLICATE_REVISION",
    "AREA_BASIS_CONFLICT",
    "AREA_INTERVAL_CONFLICT",
    "PLANNED_OBSERVED_CONFLICT",
    "DATE_PRECISION_INSUFFICIENT",
  ])
    expect(p.summary.issue_counts[code], code).toBeGreaterThan(0);
  await page.screenshot({ path: info.outputPath("V0_20-SYNTHETIC-conflicts.png"), fullPage: true });
  const old = await page.getByLabel("选择准备版本").inputValue();
  await page.getByLabel("品种来源编码", { exact: true }).selectOption("");
  await expect(
    page.getByRole("button", { name: "下载 agronomic-preparation.json" }),
  ).not.toBeVisible();
  await expect(page.getByRole("button", { name: "规范化并检查农事数据" })).toBeDisabled();
  await page.getByRole("button", { name: "加入或更新本表映射" }).click();
  await prepare(page);
  expect((await jsonDownload(page)).data.package_id).not.toBe(p.package_id);
  await page.getByLabel("选择准备版本").selectOption(old);
  expect((await jsonDownload(page)).data).toEqual(p);
  await page.getByRole("button", { name: "清空农事文件与所有版本" }).click();
  await expect(page.getByLabel("选择准备版本")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "下载 agronomic-preparation.json" }),
  ).not.toBeVisible();
});

test("V0_20 Excel clock keeps timezone unproven and logout removes local data", async ({
  page,
  https,
}) => {
  await enter(page, https);
  await sample(page);
  await page.getByLabel("农事工作表").selectOption("4");
  await page.getByLabel("农事表头行").fill("1");
  await expect(
    page.getByRole("table", { name: "农事原表预览 · 前50行，原值不修改" }),
  ).toContainText("2024-09-01T12:00:00.000");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  await expect(page.getByLabel("V0.20 历史农事准备")).not.toBeVisible();
});
