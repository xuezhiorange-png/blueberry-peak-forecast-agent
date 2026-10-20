import { test as base, expect, type Page } from "@playwright/test";
import { httpsFixture } from "./support/https-fixture";

// Real HTTPS/PG and unchanged production ASGI, with independent bounded setup.
const test = base.extend<object, { https: string }>({
  https: httpsFixture("acceptance_s6_pg"),
});
test.use({ ignoreHTTPSErrors: true });

async function login(page: Page, url: string, username = "synthetic-user") {
  await page.goto(url + "/dashboard/overview");
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Dashboard 主导航" })).toBeVisible();
}
async function select(page: Page, level = "BASE", entity = "SYNTHETIC_BASE_1") {
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
  const listing = await page.request.get(
    new URL("/api/v1/business-access/saved-runs", page.url()).href,
  );
  expect(listing.status()).toBe(200);
  const item = (await listing.json()).data.items.find(
    (i: { forecast_identity: { hierarchy_level: string; entity_id: string } }) =>
      i.forecast_identity.hierarchy_level === level && i.forecast_identity.entity_id === entity,
  );
  expect(item).toBeTruthy();
  const row = page
    .getByRole("dialog")
    .getByRole("article")
    .filter({
      has: page.getByRole("heading", { name: `${item.entity_name} · ${level}`, exact: true }),
    });
  await row.getByRole("button", { name: "核验并使用保存预测" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator(".d-context-title")).toContainText(item.entity_name);
}

for (const [width, height] of [
  [1440, 900],
  [1280, 800],
  [1024, 768],
  [834, 1112],
  [390, 844],
  [360, 800],
]) {
  test(`S6 canonical HTTP SDK DOM five pages ${width}x${height}`, async ({ page, https }, info) => {
    await page.setViewportSize({ width, height });
    const proof = await (await page.request.get(https + "/__s6_test__/parity")).json();
    expect(proof.SYNTHETIC).toBe(true);
    await login(page, https);
    await select(page);
    const overview = proof.overview.data;
    const kpiValues = [
      overview.forecast_7d_total_kg,
      overview.forecast_15d_total_kg,
      overview.peak_date,
      overview.peak_daily_quantity_kg,
    ];
    for (const [index, value] of kpiValues.entries()) {
      // The approved KPI trims display-only trailing zeros/date year, but its
      // title preserves the exact server string. Assert both, no Number math.
      const kpi = page.getByLabel("核心四项指标").locator(".d-kpi-value").nth(index);
      await expect(kpi).toHaveAttribute("title", value);
      await expect(kpi).toContainText(
        index === 2 ? value.slice(5) : value.replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1"),
      );
    }
    const states: Record<string, unknown> = {};
    for (const [label, method] of [
      ["总览", "overview"],
      ["预测", "curve"],
      ["影响因素", "attribution"],
      ["产能模拟", "capacity"],
      ["预测质量", "quality"],
    ]) {
      await page.getByRole("link", { name: new RegExp(label + "$") }).click();
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator('[data-state="LOADING"]')).toHaveCount(0);
      if (method === "curve") {
        for (const row of proof.curve.data.daily_rows) {
          await expect(page.locator("main")).toContainText(row.point_forecast_kg);
        }
        await expect(page.locator("main svg").first()).toBeVisible();
        expect(await page.locator("main table").count()).toBeGreaterThan(0);
      }
      if (method === "attribution")
        await expect(page.locator("main")).toContainText("NOT_AVAILABLE");
      if (method === "quality") {
        await expect(page.locator("main")).toContainText(proof.quality.data.source_split);
        await expect(page.locator("main")).toContainText(proof.quality.data.current_actual_message);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.evaluate(() => {
        const caption =
          document.getElementById("s6-synthetic-caption") ?? document.createElement("p");
        caption.id = "s6-synthetic-caption";
        caption.textContent = "SYNTHETIC S6 ACCEPTANCE — NOT PRODUCTION DATA";
        document.body.prepend(caption);
      });
      states[method] = await page
        .locator("[data-state]")
        .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-state")));
      const screenshot = info.outputPath(`S6-${method}-${width}x${height}-SYNTHETIC.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      await info.attach(`S6-${method}-${width}x${height}-SYNTHETIC`, {
        path: screenshot,
        contentType: "image/png",
      });
    }
    await info.attach("S6-authority-and-module-states", {
      body: JSON.stringify({ SYNTHETIC: true, proof, states, viewport: { width, height } }),
      contentType: "application/json",
    });
  });
}

test("S6 BASE REGION COMPANY exact selection and HTTP SDK values", async ({
  page,
  https,
}, info) => {
  await login(page, https);
  const identity = (await (await page.request.get(https + "/__s4_test__/ready")).json()).identities;
  for (const level of ["BASE", "REGION", "COMPANY"]) {
    const query = identity.find((q: { hierarchy_level: string }) => q.hierarchy_level === level);
    const proof = await (
      await page.request.get(https + "/__s6_test__/parity?level=" + level)
    ).json();
    await select(page, level, query.entity_id);
    if (proof.overview.data.forecast_15d_total_kg !== null)
      await expect(page.getByLabel("核心四项指标").locator(".d-kpi-value").nth(1)).toHaveAttribute(
        "title",
        proof.overview.data.forecast_15d_total_kg,
      );
    else await expect(page.locator("main")).toContainText("部分数据");
    await info.attach("S6-" + level + "-authority", {
      body: JSON.stringify(proof),
      contentType: "application/json",
    });
  }
});

test("S6 short saved window stays PARTIAL and H1 H3 H7 H15 never pad missing dates", async ({
  page,
  https,
}, info) => {
  await login(page, https);
  await select(page, "BASE", "SYNTHETIC_SHORT_BASE");
  await expect(page.locator("main")).toContainText("部分数据");
  await page.getByRole("link", { name: /预测$/ }).click();
  await expect(page.locator("main")).toContainText("可用 2 日");
  for (const h of [1, 3, 7, 15]) {
    await page.getByRole("button", { name: "H" + h, exact: true }).click();
    await expect(page.locator("table").last().locator("tbody tr")).toHaveCount(h === 1 ? 1 : 2);
  }
  const path = info.outputPath("S6-PARTIAL-short-window-SYNTHETIC.png");
  await page.evaluate(() => {
    const caption = document.createElement("p");
    caption.textContent = "SYNTHETIC S6 ACCEPTANCE — NOT PRODUCTION DATA";
    document.body.prepend(caption);
  });
  await page.screenshot({ path, fullPage: true });
  await info.attach("S6-PARTIAL-short-window-SYNTHETIC", { path, contentType: "image/png" });
});

test("S6 no-grant account, keyboard focus, reduced motion, large text and logout cleanup", async ({
  page,
  https,
}, info) => {
  await login(page, https);
  await select(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const opener = page.getByRole("button", { name: "选择已保存预测", exact: true });
  await opener.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await page.evaluate(() => {
    document.querySelector<HTMLElement>(".dashboard")!.style.fontSize = "30px";
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  await expect(page.locator(".d-kpis, main svg")).toHaveCount(0);
  await login(page, https, "synthetic-admin");
  await opener.click();
  await expect(page.getByRole("dialog")).toContainText("当前身份没有读取权限");
  await expect(page.getByRole("dialog").getByRole("article")).toHaveCount(0);
  await info.attach("S6-accessibility-scope", {
    body: JSON.stringify({
      keyboard_focus: "PASS",
      reduced_motion_css_preference: "PASS",
      large_text: "PASS",
      real_iOS: "NOT_VALIDATED",
      screen_reader: "NOT_VALIDATED",
      soft_keyboard: "NOT_VALIDATED",
    }),
    contentType: "application/json",
  });
});

test("S6 submitted DIRECT WORKFORCE and comparison match canonical SDK and clear stale results", async ({
  page,
  https,
}, info) => {
  await login(page, https);
  await select(page);
  await page.getByRole("link", { name: /产能模拟$/ }).click();
  await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
  for (const id of ["B", "C"]) {
    if (id === "C") await page.getByRole("button", { name: "新增空情景" }).click();
    await page.getByLabel("情景 ID", { exact: true }).fill(id);
    await page.getByLabel("情景版本", { exact: true }).fill("R1");
    if (id === "B") await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill("140");
    else {
      await page
        .getByRole("combobox", { name: "产能模式", exact: true })
        .selectOption("WORKFORCE_DERIVED");
      await page.getByLabel("人数（非负整数）", { exact: true }).fill("10");
      await page.getByLabel("显式人效 kg/人·日", { exact: true }).fill("14");
    }
    await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
    await page.getByRole("button", { name: "确认复制至这些日期" }).click();
    const pending = page.waitForResponse((r) => r.url().endsWith("/simulate-capacity"));
    await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
    const response = await pending;
    expect(response.status()).toBe(200);
    const actual = await response.json();
    const authority = await (
      await page.request.post(https + "/__s6_test__/decision-parity/simulate", {
        data: response.request().postDataJSON(),
      })
    ).json();
    expect(actual).toEqual(authority.canonical_and_sdk);
    await expect(page.locator("main")).toContainText(actual.engine_result_hash);
    await expect(page.locator("main")).toContainText(actual.data.total_business_loss);
    await info.attach("S6-scenario-" + id + "-parity", {
      body: JSON.stringify(actual),
      contentType: "application/json",
    });
  }
  const pending = page.waitForResponse((r) => r.url().endsWith("/compare-capacity-scenarios"));
  await page.getByRole("button", { name: "比较全部情景", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const actual = await response.json();
  const authority = await (
    await page.request.post(https + "/__s6_test__/decision-parity/compare", {
      data: response.request().postDataJSON(),
    })
  ).json();
  expect(actual).toEqual(authority.canonical_and_sdk);
  await expect(page.locator("main")).toContainText(actual.engine_result_hash);
  await expect(page.locator(".d-rank-list")).toBeVisible();
  await page.getByLabel("人数（非负整数）", { exact: true }).fill("11");
  await expect(page.locator(".d-rank-list")).toHaveCount(0);
  await info.attach("S6-comparison-parity", {
    body: JSON.stringify(actual),
    contentType: "application/json",
  });
});

test("S6 real loading database outage retry and catalog conflict clear old results", async ({
  page,
  https,
}, info) => {
  await login(page, https);
  await expect(page.locator(".d-context-title")).toContainText("请选择已保存预测");
  await select(page);
  await page.request.post(https + "/__s4_test__/hold-next-curve");
  try {
    await page.getByRole("link", { name: /预测$/ }).click();
    await expect(page.locator('[data-state="LOADING"]').first()).toBeVisible();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(https + "/__s4_test__/ready")).json()).hold_arrived,
      )
      .toBe(true);
  } finally {
    await page.request.post(https + "/__s4_test__/release-curve");
  }
  await expect(page.locator('[data-state="LOADING"]')).toHaveCount(0);
  await page.getByRole("link", { name: /总览$/ }).click();
  await expect(page.getByLabel("核心四项指标")).toBeVisible();
  expect((await page.request.post(https + "/__s6_test__/database/unavailable")).status()).toBe(200);
  try {
    await page.getByRole("link", { name: /预测$/ }).click();
    await expect(page.locator('[data-state="ERROR"]').first()).toBeVisible();
    await expect(page.locator("main")).not.toContainText("postgresql");
  } finally {
    expect((await page.request.post(https + "/__s6_test__/database/restore")).status()).toBe(200);
  }
  await page.getByRole("button", { name: "重试", exact: true }).first().click();
  await expect(page.locator("main svg").first()).toBeVisible();
  await page.getByRole("link", { name: /总览$/ }).click();
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("article")).toHaveCount(5);
  expect((await page.request.post(https + "/__s6_test__/catalog-drift")).status()).toBe(200);
  const conflict = page.waitForResponse((r) => r.url().endsWith("/business-access/selection"));
  const row = page
    .getByRole("dialog")
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "SYNTHETIC_BASE_1 · BASE", exact: true }) });
  await row.getByRole("button", { name: "核验并使用保存预测" }).click();
  expect((await conflict).status()).toBe(409);
  await expect(page.locator(".d-context-title")).toContainText("请选择已保存预测");
  await expect(page.locator(".d-kpis, main svg, .d-rank-list")).toHaveCount(0);
  await info.attach("S6-real-state-transitions", {
    body: JSON.stringify({
      SYNTHETIC: true,
      EMPTY: "PASS",
      LOADING: "PASS",
      ERROR_503_RETRY: "PASS",
      AUTHORITY_MISMATCH_409_CLEAR: "PASS",
    }),
    contentType: "application/json",
  });
});
