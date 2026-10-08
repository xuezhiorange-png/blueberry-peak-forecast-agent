import { test as base, expect, type Page, type TestInfo } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

async function capture(page: Page, info: TestInfo, name: string) {
  const path = info.outputPath(name);
  await page.screenshot({
    path,
    fullPage: true,
    ...(name.endsWith(".jpg") ? { type: "jpeg" as const, quality: 80 } : {}),
  });
  await info.attach(name, {
    path,
    contentType: name.endsWith(".jpg") ? "image/jpeg" : "image/png",
  });
  await info.attach(`provenance:${name}`, {
    body: JSON.stringify({
      execution_id: process.env.S6_SCREENSHOT_EXECUTION_ID ?? "CI_VALIDATION_NOT_ARCHIVED",
      test_id: info.testId,
      test_file: "e2e/dashboard-cross-surface.spec.ts",
      test_title: info.title,
      project: info.project.name,
      captured_at: new Date().toISOString(),
      name,
      sha256: createHash("sha256")
        .update(await readFile(path))
        .digest("hex"),
    }),
    contentType: "application/json",
  });
}

// SYNTHETIC=true. Browser HTTP and server-side real MCP SDK share one SQLite DB.
const test = base.extend<
  Record<string, never>,
  { authority: { url: string; identities: Record<string, string | number>[] } }
>({
  authority: [
    async ({ playwright }, use, worker) => {
      const url = `http://127.0.0.1:${44800 + worker.workerIndex}`;
      const child = spawn(
        process.env.DASHBOARD_TEST_PYTHON ?? "python3",
        [
          "-m",
          "uvicorn",
          "frontend.e2e.support.s6_api:app",
          "--host",
          "127.0.0.1",
          "--port",
          String(44800 + worker.workerIndex),
        ],
        {
          cwd: resolve(process.cwd(), ".."),
          env: { ...process.env, PYTHONPATH: "." },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      let logs = "";
      const drain = (v: Buffer) => {
        logs = (logs + String(v)).slice(-32768);
      };
      child.stdout.on("data", drain);
      child.stderr.on("data", drain);
      const api = await playwright.request.newContext();
      try {
        await expect
          .poll(
            async () => {
              if (child.exitCode !== null) throw new Error(logs);
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
    await page.addInitScript(() => {
      document.addEventListener("DOMContentLoaded", () => {
        const label = document.createElement("p");
        label.textContent = "SYNTHETIC S6 ACCEPTANCE — NOT PRODUCTION DATA";
        label.style.cssText = "margin:0;padding:8px;font:13px sans-serif;overflow-wrap:anywhere";
        document.body.prepend(label);
      });
    });
    for (const surface of ["forecast-intelligence", "decision-support"])
      await page.route(`**/api/v1/${surface}/**`, async (route) => {
        const incoming = new URL(route.request().url());
        const response = await route.fetch({
          url: authority.url + incoming.pathname + incoming.search,
        });
        if (route.request().method() === "POST") {
          const sdk = await page.request.post(authority.url + "/__s6_test__/sdk", {
            data: {
              name: incoming.pathname.endsWith("/simulate-capacity")
                ? "simulate_capacity"
                : "compare_capacity_scenarios",
              arguments: route.request().postDataJSON(),
            },
          });
          const value = await sdk.json();
          expect(value.isError).toBe(false);
          expect(value.payload).toEqual(await response.json());
        }
        await route.fulfill({ response });
      });
    await use(page);
    await page.unrouteAll({ behavior: "wait" });
  },
});

test("cancelled saved-run validation can be retried after reopening", async ({
  page,
  authority,
}, info) => {
  await page.setViewportSize(
    info.project.name === "chromium-mobile"
      ? { width: 390, height: 844 }
      : { width: 1440, height: 900 },
  );
  await page.goto("/dashboard/overview");
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
  const dialog = page.getByRole("dialog");
  for (const [key, value] of Object.entries(authority.identities[0])) {
    const field = dialog.locator(`[name="${key}"]`);
    if (["source_kind", "hierarchy_level"].includes(key)) await field.selectOption(String(value));
    else await field.fill(String(value));
  }
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  // Delay a REAL canonical HTTP result; no substituted business JSON.
  await page.route("**/api/v1/forecast-intelligence/curve?**", async (route) => {
    const incoming = new URL(route.request().url());
    const response = await route.fetch({
      url: authority.url + incoming.pathname + incoming.search,
    });
    requested();
    await held;
    await route.fulfill({ response });
  });
  try {
    await dialog.getByRole("button", { name: "核验并使用保存预测" }).click();
    await started;
    await expect(dialog.getByRole("button", { name: "正在核验…" })).toBeDisabled();
    await dialog.getByRole("button", { name: "关闭", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    release();
    await page.unroute("**/api/v1/forecast-intelligence/curve?**");
    await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
    await expect(dialog).toBeVisible();
    await expect(page.locator(".d-context-title")).toHaveText("请选择已保存预测");
    await dialog.locator('button[type="submit"]').scrollIntoViewIfNeeded();
    await page.evaluate(() => {
      const caption = document.createElement("p");
      caption.textContent =
        "SYNTHETIC S6 ACCEPTANCE — NOT PRODUCTION DATA · cancelled verification reopened";
      document.body.prepend(caption);
    });
    await dialog.locator('button[type="submit"]').scrollIntoViewIfNeeded();
    await capture(page, info, "cancel-reopen-SYNTHETIC.png");
    // A cancelled operation must not permanently disable retry. No field edit
    // should be necessary to recover an already valid complete identity.
    await expect(dialog.locator('button[type="submit"]')).toBeEnabled();
  } finally {
    release();
  }
});

async function select(page: Page, identity: Record<string, string | number>) {
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
  const dialog = page.getByRole("dialog");
  for (const [key, value] of Object.entries(identity)) {
    const field = dialog.locator(`[name="${key}"]`);
    if (["source_kind", "hierarchy_level"].includes(key)) await field.selectOption(String(value));
    else await field.fill(String(value));
  }
  await dialog.getByRole("button", { name: "核验并使用保存预测" }).click();
  await expect(dialog).not.toBeVisible();
}

for (const scope of [0, 2, 3])
  test(`same SQLite HTTP SDK DOM authority scope ${scope}`, async ({ page, authority }, info) => {
    const identity = authority.identities[scope];
    const params = new URLSearchParams(Object.entries(identity).map(([k, v]) => [k, String(v)]));
    const business: Record<string, ReturnType<typeof JSON.parse>> = {};
    for (const [path, name] of Object.entries({
      overview: "get_forecast_overview",
      curve: "get_forecast_curve",
      hierarchy: "get_hierarchical_forecast",
      uncertainty: "get_forecast_uncertainty",
      attribution: "get_forecast_attribution",
    })) {
      const http = await page.request.get(
        `${authority.url}/api/v1/forecast-intelligence/${path}?${params}`,
      );
      expect(http.status()).toBe(200);
      business[path] = await http.json();
      const sdk = await page.request.post(authority.url + "/__s6_test__/sdk", {
        data: { name, arguments: identity },
      });
      const result = await sdk.json();
      expect(result.isError).toBe(false);
      expect(result.payload).toEqual(business[path]);
    }
    await page.goto("/dashboard/overview");
    await select(page, identity);
    await expect(page.locator(".d-kpi-value").nth(0)).toHaveAttribute(
      "title",
      business.overview.data.forecast_7d_total_kg,
    );
    await expect(page.locator(".d-kpi-value").nth(1)).toHaveAttribute(
      "title",
      business.overview.data.forecast_15d_total_kg,
    );
    await expect(page.locator("main")).toContainText("NOT_AVAILABLE");
    await page.getByRole("link", { name: /预测$/ }).click();
    for (const horizon of [1, 3, 7, 15]) {
      await page.getByRole("button", { name: `H${horizon}`, exact: true }).click();
      for (const row of business.curve.data.daily_rows.slice(0, horizon))
        await expect(page.locator("main")).toContainText(row.point_forecast_kg);
    }
    await page.getByRole("link", { name: /影响因素$/ }).click();
    await expect(page.locator("main")).toContainText("NOT_AVAILABLE");
    await expect(page.getByRole("img")).toHaveCount(0);
    await page.getByRole("link", { name: /预测质量$/ }).click();
    for (const mode of ["HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY"]) {
      const http = await page.request.get(
        authority.url + "/api/v1/forecast-intelligence/quality?mode=" + mode,
      );
      const value = await http.json();
      const sdk = await page.request.post(authority.url + "/__s6_test__/sdk", {
        data: { name: "get_forecast_quality", arguments: { mode } },
      });
      expect((await sdk.json()).payload).toEqual(value);
      await expect(page.locator("main")).toContainText(
        mode === "HISTORICAL_VALIDATION" ? "EXPOSED_OOT" : value.unavailable_reason,
      );
      if (mode === "HISTORICAL_VALIDATION") {
        for (const horizon of value.data.horizons) {
          for (const key of ["wape", "mae_kg", "bias_kg", "cumulative_wape"])
            if (horizon[key] !== null)
              await expect(page.getByLabel(horizon[key], { exact: true }).first()).toHaveAttribute(
                "title",
                horizon[key],
              );
          for (const interval of horizon.interval_coverage) {
            await expect(
              page.getByLabel(interval.empirical_coverage, { exact: true }).first(),
            ).toHaveAttribute("title", interval.empirical_coverage);
            await expect(page.locator("main")).toContainText(
              `${interval.candidate_row_count} / ${interval.computable_row_count} / ${interval.not_computable_row_count} / ${interval.covered_row_count}`,
            );
          }
        }
      }
    }
    await expect(page.getByText("LOADING", { exact: true })).toHaveCount(0);
    await info.attach("authority-payloads.json", {
      body: JSON.stringify(business),
      contentType: "application/json",
    });
  });

test("simulation comparison HTTP SDK DOM and stale results", async ({ page, authority }, info) => {
  await page.goto("/dashboard/capacity");
  await select(page, authority.identities[0]);
  await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
  for (const id of ["B", "A", "C"]) {
    if (id !== "B") await page.getByRole("button", { name: "新增空情景" }).click();
    await page.getByLabel("情景 ID", { exact: true }).fill(id);
    await page.getByLabel("情景版本", { exact: true }).fill("R2");
    if (id === "C") {
      await page
        .getByRole("combobox", { name: "产能模式", exact: true })
        .selectOption("WORKFORCE_DERIVED");
      await page.getByLabel("人数（非负整数）", { exact: true }).fill("10");
      await page.getByLabel("显式人效 kg/人·日", { exact: true }).fill("12");
    } else
      await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill(id === "A" ? "120" : "140");
    await page.getByLabel("同日额外处理能力 kg/日", { exact: true }).fill(id === "C" ? "20" : "0");
    await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
    await page.getByRole("button", { name: "确认复制至这些日期" }).click();
    const pending = page.waitForResponse((r) => r.url().endsWith("/simulate-capacity"));
    await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
    const result = await (await pending).json();
    expect(result.data.total_business_loss).toBe(id === "A" ? "1280" : "980");
    await expect(page.locator("main")).toContainText(result.engine_result_hash);
    for (const key of [
      "cumulative_shortfall_kg",
      "max_backlog_kg",
      "ending_backlog_kg",
      "total_business_loss",
    ])
      await expect(page.locator("main")).toContainText(result.data[key]);
  }
  const pending = page.waitForResponse((r) => r.url().endsWith("/compare-capacity-scenarios"));
  await page.getByRole("button", { name: "比较全部情景", exact: true }).click();
  const result = await (await pending).json();
  expect(
    result.data.comparison.rankings.map((r: { scenario_id: string }) => r.scenario_id),
  ).toEqual(["B", "C", "A"]);
  await expect(page.locator("main")).toContainText(result.engine_result_hash);
  await expect(page.locator(".d-rank-list")).toBeVisible();
  await info.attach("comparison.json", {
    body: JSON.stringify(result),
    contentType: "application/json",
  });
  await capture(page, info, "comparison-SYNTHETIC.png");
  await page.getByLabel("人数（非负整数）", { exact: true }).fill("11");
  await expect(page.locator(".d-rank-list")).not.toBeVisible();
  await expect(page.locator("main")).toContainText("已过期");
});

for (const scope of [4, 5, 6])
  test(`rerun short incomplete canonical selection ${scope}`, async ({ page, authority }, info) => {
    await page.goto("/dashboard/overview");
    await select(page, authority.identities[0]);
    if (scope === 6) {
      await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
      const dialog = page.getByRole("dialog");
      for (const [key, value] of Object.entries(authority.identities[scope])) {
        const field = dialog.locator(`[name="${key}"]`);
        if (["source_kind", "hierarchy_level"].includes(key))
          await field.selectOption(String(value));
        else await field.fill(String(value));
      }
      await dialog.getByRole("button", { name: "核验并使用保存预测" }).click();
      await expect(dialog.locator('[data-state="AUTHORITY_MISMATCH"]')).toBeVisible();
      await capture(page, info, "incomplete-SYNTHETIC.png");
      await dialog.getByRole("button", { name: "关闭", exact: true }).click();
      await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_1");
      await expect(page.locator(".d-kpi-value").nth(1)).toHaveAttribute("title", "1820.000000");
    } else {
      await select(page, authority.identities[scope]);
      const query = new URLSearchParams(
        Object.entries(authority.identities[scope]).map(([k, v]) => [k, String(v)]),
      );
      const value = await (
        await page.request.get(authority.url + "/api/v1/forecast-intelligence/overview?" + query)
      ).json();
      if (scope === 5) {
        expect(value.status).toBe("PARTIAL");
        expect(value.data.forecast_15d_total_kg).toBeNull();
        await expect(page.locator('[data-state="PARTIAL"]').first()).toBeVisible();
        await expect(page.locator(".d-kpi-value").nth(1)).toHaveText("— kg");
        await expect(page.locator(".d-kpi-value").nth(1)).not.toHaveAttribute("title");
        await capture(page, info, "partial-SYNTHETIC.png");
      } else {
        expect(value.source_rerun_of_run_id).toBe(authority.identities[0].run_id);
        await expect(page.locator(".d-kpi-value").nth(1)).toHaveAttribute(
          "title",
          value.data.forecast_15d_total_kg,
        );
      }
    }
  });

test("diagnostic errors hide conflicted values and recover", async ({ page, authority }, info) => {
  await page.goto("/dashboard/overview");
  await capture(page, info, "empty-SYNTHETIC.png");
  await select(page, authority.identities[0]);
  for (const code of [409, 503]) {
    await page.route("**/api/v1/forecast-intelligence/overview?**", async (route) => {
      // Failure injection only; parity cases use unchanged canonical payloads.
      await route.fulfill({
        status: code,
        contentType: "application/json",
        body: JSON.stringify({ detail: "SYNTHETIC_PRIVATE_SQL_MUST_NOT_RENDER" }),
      });
    });
    await page.getByRole("link", { name: /预测$/ }).click();
    await page.getByRole("link", { name: /总览$/ }).click();
    await expect(
      page.locator(`[data-state="${code === 409 ? "AUTHORITY_MISMATCH" : "ERROR"}"]`).first(),
    ).toBeVisible();
    await expect(page.locator(".d-kpis")).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText("PRIVATE_SQL");
    await capture(page, info, `error-${code}-SYNTHETIC.png`);
    await page.unroute("**/api/v1/forecast-intelligence/overview?**");
  }
  await page.locator('[data-state="ERROR"]').first().getByRole("button").click();
  await expect(page.locator(".d-kpi-value").nth(1)).toHaveAttribute("title", "1820.000000");
});

for (const [width, height] of [
  [1440, 900],
  [1280, 800],
  [1024, 768],
  [834, 1112],
  [390, 844],
  [360, 800],
])
  test(`canonical S6 five page viewport evidence ${width}x${height}`, async ({
    page,
    authority,
  }, info) => {
    // Explicitly confirm leaving edited, in-memory scenarios (existing product contract).
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
      await expect(page.locator("main h1")).toHaveText(label);
      if (route === "overview")
        await expect(page.locator(".d-kpi-value").nth(1)).toHaveAttribute("title", "1820.000000");
      if (route === "forecast") await expect(page.locator("main")).toContainText("COMPLETE");
      if (route === "attribution")
        await expect(page.locator("main")).toContainText(
          "NO_EXACT_M1_MODEL_FEATURE_SEALED_PREDICTION_ATTRIBUTION_AUTHORITY",
        );
      if (route === "quality") {
        await expect(page.locator("main")).toContainText("UNDER_NOMINAL");
        await expect(page.locator("main")).toContainText("H15");
        await expect(page.locator("main")).toContainText(
          "当前产季暂无可用于正式评分的实际采收数据",
        );
      }
      if (route === "capacity") {
        await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
        await page.getByLabel("情景 ID", { exact: true }).fill("B");
        await page.getByLabel("情景版本", { exact: true }).fill("R2");
        await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill("140");
        await page.getByLabel("同日额外处理能力 kg/日", { exact: true }).fill("0");
        await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
        await page.getByRole("button", { name: "确认复制至这些日期" }).click();
        await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
        await expect(page.getByText("情景 B · 服务端结果", { exact: true })).toBeVisible();
      }
      await expect(page.locator('[data-state="LOADING"]')).toHaveCount(0);
      // Wait for post-navigation React layout before full-page height is sampled.
      await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        );
      });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await capture(page, info, `${route}-${width}x${height}-SYNTHETIC.jpg`);
    }
  });

test("late real HTTP validation cannot replace a newer verified run", async ({
  page,
  authority,
}) => {
  await page.goto("/dashboard/overview");
  await select(page, authority.identities[0]);
  let release!: () => void;
  let started!: () => void;
  let finished!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const pending = new Promise<void>((resolve) => {
    started = resolve;
  });
  const completed = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route("**/api/v1/forecast-intelligence/curve?**", async (route) => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: authority.url + url.pathname + url.search });
    if (url.searchParams.get("run_id") === String(authority.identities[4].run_id)) {
      started();
      await held;
    }
    await route.fulfill({ response });
    if (url.searchParams.get("run_id") === String(authority.identities[4].run_id)) finished();
  });
  try {
    await page.getByRole("button", { name: "选择已保存预测", exact: true }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.locator('[name="run_id"]').fill(String(authority.identities[4].run_id));
    await dialog.locator('button[type="submit"]').click();
    await pending;
    await dialog.getByRole("button", { name: "关闭", exact: true }).click();
    await select(page, authority.identities[1]);
    release();
    await completed;
    await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_2");
    await expect(page.locator("main")).not.toContainText("正在核验…");
  } finally {
    release();
  }
});
