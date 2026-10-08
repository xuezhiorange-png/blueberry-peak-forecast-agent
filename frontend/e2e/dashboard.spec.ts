import { test as base, expect, type Page } from "@playwright/test";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

type Selection = Record<string, string | number>;
const test = base.extend<
  Record<string, never>,
  { authority: { url: string; identities: Selection[] } }
>({
  authority: [
    async ({ playwright }, use, worker) => {
      const port = 43800 + worker.workerIndex;
      const url = `http://127.0.0.1:${port}`;
      const child = spawn(
        process.env.DASHBOARD_TEST_PYTHON ?? "python3",
        [
          "-m",
          "uvicorn",
          "frontend.e2e.support.dashboard_api:app",
          "--host",
          "127.0.0.1",
          "--port",
          String(port),
        ],
        {
          cwd: resolve(process.cwd(), ".."),
          env: { ...process.env, PYTHONPATH: "." },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      let logs = "";
      child.stderr.on("data", (v) => {
        logs += String(v);
      });
      const api = await playwright.request.newContext();
      try {
        await expect
          .poll(
            async () => {
              if (child.exitCode !== null)
                throw new Error(`Synthetic integration server exited: ${logs}`);
              try {
                return (await api.get(url + "/__dashboard_test__/authority")).status();
              } catch {
                return 0;
              }
            },
            { timeout: 30000 },
          )
          .toBe(200);
        const state = await (await api.get(url + "/__dashboard_test__/authority")).json();
        expect(state.SYNTHETIC).toBe(true);
        await use({ url, identities: state.identities });
        expect(
          (await (await api.get(url + "/__dashboard_test__/authority")).json()).read_dml_count,
        ).toBe(0);
      } finally {
        child.kill("SIGTERM");
        await api.dispose();
      }
    },
    { scope: "worker" },
  ],
  page: async ({ page, authority }, use) => {
    // Forward to unchanged real HTTP services backed by isolated synthetic saved runs.
    for (const surface of ["forecast-intelligence", "decision-support"])
      await page.route(`**/api/v1/${surface}/**`, async (route) => {
        const incoming = new URL(route.request().url());
        const response = await route.fetch({
          url: authority.url + incoming.pathname + incoming.search,
        });
        await route.fulfill({ response });
      });
    await use(page);
  },
});
async function select(page: Page, identity: Selection) {
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
  const dialog = page.getByRole("dialog");
  for (const [key, value] of Object.entries(identity)) {
    const field = dialog.locator(`[name="${key}"]`);
    if (["source_kind", "hierarchy_level"].includes(key)) await field.selectOption(String(value));
    else await field.fill(String(value));
  }
  await dialog.getByRole("button", { name: "核验并使用保存预测" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator(".d-context-title")).toContainText(String(identity.entity_id));
}
async function scenario(page: Page, id: string, workforce = false) {
  await page.getByLabel("情景 ID", { exact: true }).fill(id);
  await page.getByLabel("情景版本", { exact: true }).fill("R1");
  if (workforce) {
    await page
      .getByRole("combobox", { name: "产能模式", exact: true })
      .selectOption("WORKFORCE_DERIVED");
    await page.getByLabel("人数（非负整数）", { exact: true }).fill("10");
    await page.getByLabel("显式人效 kg/人·日", { exact: true }).fill("12");
    await page.getByLabel("同日额外处理能力 kg/日", { exact: true }).fill("20");
  } else {
    await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill(id === "A" ? "120" : "140");
    await page.getByLabel("同日额外处理能力 kg/日", { exact: true }).fill("0");
  }
  await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
  await page.getByRole("button", { name: "确认复制至这些日期" }).click();
}
test("real saved authority BASE/REGION/COMPANY, six reads and unchanged service strings", async ({
  page,
  authority,
}) => {
  await page.goto("/dashboard/overview");
  for (const identity of authority.identities.filter((i) => i.entity_id !== "SYNTHETIC_BASE_2")) {
    await select(page, identity);
    await expect(page.locator(".d-kpis").first()).toContainText(
      identity.hierarchy_level === "BASE" ? "1820" : "3640",
    );
    await expect(page.getByRole("img", { name: /逐日预测/ }).first()).toBeVisible();
    await page.getByRole("link", { name: /影响因素$/ }).click();
    await expect(page.locator("main")).toContainText("NOT_AVAILABLE");
    await page.getByRole("link", { name: /总览$/ }).click();
  }
  await page.getByRole("link", { name: /预测质量$/ }).click();
  await expect(page.locator("main")).toContainText("EXPOSED_OOT");
  await expect(page.locator("main")).toContainText("当前产季暂无可用于正式评分的实际采收数据");
});
test("real simulation and comparison parity; explicit costs, daily workforce and stale ranks", async ({
  page,
  authority,
}) => {
  await page.goto("/dashboard/capacity");
  await select(page, authority.identities[0]);
  await expect(page.getByLabel("显式选择成本合同（无默认）")).toHaveValue("");
  await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
  await scenario(page, "B");
  const responsePromise = page.waitForResponse((r) => r.url().includes("/simulate-capacity"));
  await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
  const response = await (await responsePromise).json();
  expect(response.data.total_business_loss).toBe("980");
  await expect(page.locator("main")).toContainText(response.engine_result_hash);
  await expect(page.getByText("情景 B · 服务端结果", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "新增空情景" }).click();
  await expect(page.getByText("情景 B · 服务端结果", { exact: true })).not.toBeVisible();
  await scenario(page, "A");
  await page.getByRole("button", { name: "新增空情景" }).click();
  await scenario(page, "C", true);
  const comparisonPromise = page.waitForResponse((r) =>
    r.url().includes("/compare-capacity-scenarios"),
  );
  await page.getByRole("button", { name: "比较全部情景", exact: true }).click();
  const comparison = await (await comparisonPromise).json();
  const b = comparison.data.scenario_results.find(
    (r: { scenario_id: string }) => r.scenario_id === "B",
  );
  const c = comparison.data.scenario_results.find(
    (r: { scenario_id: string }) => r.scenario_id === "C",
  );
  for (const key of [
    "total_business_loss",
    "max_backlog_kg",
    "cumulative_shortfall_kg",
    "ending_backlog_kg",
    "total_effective_capacity_kg",
    "total_processed_kg",
    "aggregate_capacity_utilization_numerator_kg",
    "aggregate_capacity_utilization_denominator_kg",
    "aggregate_capacity_utilization_decimal",
  ])
    expect(b[key]).toEqual(c[key]);
  for (let day = 0; day < b.daily_rows.length; day++)
    for (const key of [
      "planning_demand_kg",
      "processed_kg",
      "opening_backlog_kg",
      "closing_backlog_kg",
      "daily_overload_kg",
      "scenario_business_loss",
      "capacity_utilization_numerator_kg",
      "capacity_utilization_denominator_kg",
      "capacity_utilization_decimal",
    ])
      expect(b.daily_rows[day][key]).toEqual(c.daily_rows[day][key]);
  expect(
    comparison.data.comparison.rankings.map((r: { scenario_id: string }) => r.scenario_id),
  ).toEqual(["B", "C", "A"]);
  await expect(page.locator(".d-rank-list")).toContainText("B");
  await expect(page.locator("main")).toContainText(comparison.engine_result_hash);
  if (process.env.DASHBOARD_CAPTURE_DIR)
    await page.screenshot({
      path: resolve(process.env.DASHBOARD_CAPTURE_DIR, "capacity-abc-comparison.jpg"),
      type: "jpeg",
      quality: 80,
      fullPage: true,
    });
  await page.getByLabel("人数（非负整数）", { exact: true }).fill("11");
  await expect(page.locator(".d-rank-list")).not.toBeVisible();
  await expect(page.locator("main")).toContainText("已过期");
  for (const level of ["UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"]) {
    await expect(
      page
        .getByRole("combobox", { name: "规划水平", exact: true })
        .locator(`option[value="${level}"]`),
    ).toHaveAttribute("disabled", "");
    const { expected_source_result_hash, ...forecast_selection } = authority.identities[0];
    const result = await page.request.post(
      authority.url + "/api/v1/decision-support/simulate-capacity",
      {
        data: {
          forecast_selection,
          expected_source_result_hash,
          planning_level: level,
          cost_contract_id: "SYNTHETIC_UNDER_4X_R1",
          expected_cost_contract_hash: comparison.cost_contract_hash,
          scenario_id: "BOUND_MUST_NOT_FALL_BACK",
          scenario_version: "R1",
          capacity_rows: b.dates.map((date: string) => ({
            date,
            capacity_mode: "DIRECT",
            daily_handling_capacity_kg: "140",
          })),
        },
      },
    );
    expect(result.status()).toBe(200);
    expect(await result.json()).toMatchObject({ status: "NOT_AVAILABLE", data: null });
  }
  await page.getByRole("combobox", { name: "产能模式", exact: true }).selectOption("DIRECT");
  await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill("0");
  await page.getByLabel("同日额外处理能力 kg/日", { exact: true }).fill("0");
  await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
  await page.getByRole("button", { name: "确认复制至这些日期" }).click();
  await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
  await expect(page.locator("main")).toContainText("NOT_COMPUTABLE_ZERO_CAPACITY");
  await expect(page.locator("main")).not.toContainText("Infinity");
});
test("hash mismatch never replaces validated context; keyboard dialog focus returns", async ({
  page,
  authority,
}) => {
  await page.goto("/dashboard/forecast");
  await select(page, authority.identities[0]);
  const opener = page.getByRole("button", { name: "选择已保存预测", exact: true }).first();
  await opener.click();
  await page
    .getByRole("dialog")
    .locator('[name="expected_source_result_hash"]')
    .fill("0".repeat(64));
  await page.getByRole("button", { name: "核验并使用保存预测" }).click();
  await expect(page.getByRole("dialog")).toContainText("来源身份不一致");
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_1");
});
const viewports = [
  [1440, 900],
  [1280, 800],
  [1024, 768],
  [834, 1112],
  [390, 844],
  [360, 800],
];
for (const [width, height] of viewports) {
  test(`five pages render without overflow ${width}x${height}`, async ({
    page,
    authority,
  }, info) => {
    page.on("dialog", (dialog) => dialog.accept());
    await page.setViewportSize({ width, height });
    await page.goto("/dashboard/overview");
    await select(page, authority.identities[0]);
    for (const [route, label] of [
      ["overview", "总览"],
      ["forecast", "预测"],
      ["attribution", "影响因素"],
      ["capacity", "产能模拟"],
      ["quality", "预测质量"],
    ]) {
      await page
        .getByRole("navigation", { name: "Dashboard 主导航" })
        .getByRole("link", { name: new RegExp(label + "$") })
        .click();
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator('[data-state="LOADING"]')).toHaveCount(0);
      const overflow = await page.evaluate(() => ({
        ok: document.documentElement.scrollWidth <= window.innerWidth,
        sw: document.documentElement.scrollWidth,
        vw: innerWidth,
        elements: [...document.querySelectorAll("body *")]
          .filter(
            (e) =>
              e.getBoundingClientRect().right > innerWidth ||
              (e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1),
          )
          .slice(0, 20)
          .map((e) => ({
            tag: e.tagName,
            cls: e.className,
            text: e.textContent?.slice(0, 50),
            right: e.getBoundingClientRect().right,
            scroll: e.scrollWidth,
            client: e.clientWidth,
          })),
      }));
      expect(overflow, JSON.stringify(overflow)).toMatchObject({ ok: true });
      if (route === "capacity") {
        await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
        await scenario(page, "B");
        await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
        await expect(page.getByText("情景 B · 服务端结果", { exact: true })).toBeVisible();
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      if (process.env.DASHBOARD_CAPTURE_DIR) {
        // Test-only provenance caption, never shipped in the production bundle.
        await page.evaluate(() => {
          document.getElementById("synthetic-capture-caption")?.remove();
          const caption = document.createElement("p");
          caption.id = "synthetic-capture-caption";
          caption.textContent =
            "SYNTHETIC SAVED FORECAST FIXTURE — NOT PRODUCTION DATA · QUALITY: FROZEN HISTORICAL EVIDENCE";
          caption.style.cssText =
            "margin:0;padding:8px 16px;background:#fff4df;color:#172d27;font:13px sans-serif;overflow-wrap:anywhere";
          document.body.prepend(caption);
        });
      }
      await page.screenshot({
        path: process.env.DASHBOARD_CAPTURE_DIR
          ? resolve(process.env.DASHBOARD_CAPTURE_DIR, `${route}-${width}x${height}.jpg`)
          : info.outputPath(`${route}-${width}x${height}-SYNTHETIC.jpg`),
        type: "jpeg",
        quality: 80,
        fullPage: true,
      });
    }
  });
}
test("safe unavailable/error modules recover without losing validated context", async ({
  page,
  authority,
}) => {
  await page.goto("/dashboard/overview");
  await expect(page.locator("main")).toContainText("请选择已保存预测");
  if (process.env.DASHBOARD_CAPTURE_DIR)
    await page.screenshot({
      path: resolve(process.env.DASHBOARD_CAPTURE_DIR, "state-empty.jpg"),
      type: "jpeg",
      quality: 80,
      fullPage: true,
    });
  await select(page, authority.identities[0]);
  for (const code of [401, 403, 404, 409, 422, 413, 503]) {
    await page.route("**/api/v1/forecast-intelligence/overview?**", async (route) => {
      await route.fulfill({
        status: code,
        contentType: "application/json",
        body: JSON.stringify({ detail: "SYNTHETIC_PRIVATE_SQL_TOKEN_PATH_MUST_NOT_RENDER" }),
      });
    });
    await page.getByRole("link", { name: /预测$/ }).click();
    await page.getByRole("link", { name: /总览$/ }).click();
    await expect(
      page.locator(`[data-state="${code === 409 ? "AUTHORITY_MISMATCH" : "ERROR"}"]`).first(),
    ).toBeVisible();
    await expect(page.locator("main")).not.toContainText("PRIVATE_SQL_TOKEN_PATH");
    await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_1");
    if (process.env.DASHBOARD_CAPTURE_DIR && [409, 503].includes(code))
      await page.screenshot({
        path: resolve(process.env.DASHBOARD_CAPTURE_DIR, `state-${code}.jpg`),
        type: "jpeg",
        quality: 80,
        fullPage: true,
      });
    await page.unroute("**/api/v1/forecast-intelligence/overview?**");
  }
  await page.locator('[data-state="ERROR"]').first().getByRole("button").click();
  await expect(page.locator(".d-kpis")).toContainText("1820");
});
test("date keyboard/table linkage, large text and reduced motion", async ({ page, authority }) => {
  await page.goto("/dashboard/forecast");
  await select(page, authority.identities[0]);
  // The chart controls are genuine keyboard targets, not hover-only tooltips.
  const controls = page.locator(".d-date-strip button");
  await controls.first().click();
  await controls.first().press("ArrowRight");
  await expect(controls.nth(1)).toBeFocused();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(() => {
    document.querySelector<HTMLElement>(".dashboard")!.style.fontSize = "30px";
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
