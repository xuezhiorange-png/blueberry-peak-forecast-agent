import { test as base, expect, type Page } from "@playwright/test";
import { httpsFixture } from "./support/https-fixture";

// Real HTTPS/PG and unchanged production ASGI, with independent bounded setup.
const test = base.extend<object, { https: string }>({
  https: httpsFixture("business_pg", () => process.env.S4_HTTPS_URL),
});
test.use({ ignoreHTTPSErrors: true });
test.describe.configure({ mode: "serial" });
async function login(page: Page, url: string, username = "synthetic-user") {
  await page.goto(url + "/dashboard/overview");
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Dashboard 主导航" })).toBeVisible();
}
async function select(page: Page, entity = "SYNTHETIC_BASE_1") {
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
  const row = page
    .getByRole("dialog")
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: `${entity} · BASE`, exact: true }) });
  const selected = page.waitForResponse(
    (r) => r.url().endsWith("/business-access/selection") && r.request().method() === "POST",
  );
  await row.getByRole("button", { name: "核验并使用保存预测" }).click();
  expect((await selected).status()).toBe(200);
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator(".d-context-title")).toContainText(entity);
}

test("actual HTTPS Cookie CSRF login list selection canonical values and logout", async ({
  page,
  https,
  context,
}) => {
  await login(page, https);
  const cookie = (await context.cookies()).find((c) => c.name === "__Host-blueberry-session");
  expect(cookie).toMatchObject({ secure: true, httpOnly: true, sameSite: "Lax", path: "/" });
  const posts: Promise<Record<string, string>>[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") posts.push(r.allHeaders());
  });
  await select(page);
  await expect(page.locator(".d-kpis").first()).toContainText("1820");
  await page.getByRole("link", { name: /预测$/ }).click();
  await expect(page.locator("main")).toContainText("POINT");
  await page.getByRole("link", { name: /影响因素$/ }).click();
  await expect(page.locator("main")).toContainText("NOT_AVAILABLE");
  await page.getByRole("link", { name: /预测质量$/ }).click();
  await expect(page.locator("main")).toContainText("EXPOSED_OOT");
  await expect(page.locator("main")).toContainText("当前产季暂无可用于正式评分的实际采收数据");
  await page.getByRole("link", { name: /产能模拟$/ }).click();
  await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
  await page.getByLabel("情景 ID", { exact: true }).fill("B");
  await page.getByLabel("情景版本", { exact: true }).fill("R1");
  await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill("140");
  await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
  await page.getByRole("button", { name: "确认复制至这些日期" }).click();
  const simulation = page.waitForResponse((r) => r.url().endsWith("/simulate-capacity"));
  await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
  const result = await (await simulation).json();
  expect(result.data.total_business_loss).toBe("980");
  await expect(page.locator("main")).toContainText(result.engine_result_hash);
  await page.getByRole("button", { name: "新增空情景" }).click();
  await page.getByLabel("情景 ID", { exact: true }).fill("C");
  await page.getByLabel("情景版本", { exact: true }).fill("R1");
  await page
    .getByRole("combobox", { name: "产能模式", exact: true })
    .selectOption("WORKFORCE_DERIVED");
  await page.getByLabel("人数（非负整数）", { exact: true }).fill("10");
  await page.getByLabel("显式人效 kg/人·日", { exact: true }).fill("14");
  await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
  await page.getByRole("button", { name: "确认复制至这些日期" }).click();
  const comparison = page.waitForResponse((r) => r.url().endsWith("/compare-capacity-scenarios"));
  await page.getByRole("button", { name: "比较全部情景", exact: true }).click();
  const compared = await (await comparison).json();
  expect(
    compared.data.comparison.rankings.map((r: { scenario_id: string }) => r.scenario_id),
  ).toEqual(["B", "C"]);
  await expect(page.locator("main")).toContainText(compared.engine_result_hash);
  await page.getByLabel("人数（非负整数）", { exact: true }).fill("11");
  await expect(page.locator(".d-rank-list")).not.toBeVisible();
  await page.getByRole("combobox", { name: "产能模式", exact: true }).selectOption("DIRECT");
  await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill("0");
  await expect(page.getByText("情景 B · 服务端结果", { exact: true })).not.toBeVisible();
  page.on("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  expect(posts.length).toBeGreaterThan(1);
  for (const post of await Promise.all(posts)) {
    expect(post["x-csrf-token"]).toBeTruthy();
    expect(post.origin).toBe(https);
  }
  await login(page, https, "synthetic-other");
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("dialog").getByRole("article")).toContainText("SYNTHETIC_BASE_2");
  await expect(page.locator(".d-kpis")).toHaveCount(0);
});
for (const way of ["button", "escape", "native"] as const) {
  test(`HTTPS actual canonical cancel/reopen ${way}, late response and previous context`, async ({
    page,
    https,
  }) => {
    await login(page, https);
    await select(page);
    await page.request.post(https + "/__s4_test__/hold-next-curve");
    await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
    const dialog = page.getByRole("dialog");
    const row = dialog.locator('article[data-source-kind="HIERARCHICAL"]').first();
    try {
      await row.getByRole("button", { name: "核验并使用保存预测" }).click();
      await expect
        .poll(
          async () =>
            (await (await page.request.get(https + "/__s4_test__/ready")).json()).hold_arrived,
        )
        .toBe(true);
      if (way === "button") await dialog.getByRole("button", { name: "关闭", exact: true }).click();
      else if (way === "escape") await page.keyboard.press("Escape");
      else await dialog.evaluate((element: HTMLDialogElement) => element.close());
      await expect(dialog).not.toBeVisible();
      await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_1");
      await select(page, "SYNTHETIC_BASE_2");
      await page.request.post(https + "/__s4_test__/release-curve");
      await expect(page.locator(".d-context-title")).toContainText("SYNTHETIC_BASE_2");
      await expect(page.getByLabel("核心四项指标")).toContainText("1820");
    } finally {
      await page.request.post(https + "/__s4_test__/release-curve");
    }
  });
}
test("forced first password change and ADMIN no implicit grant", async ({ page, https }) => {
  await page.goto(https + "/dashboard/overview");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-first");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "首次登录 · 修改密码" })).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await page.getByLabel("当前密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByLabel("新密码", { exact: true }).fill("SYNTHETIC-new-password-123");
  await page.getByRole("button", { name: "修改密码并继续" }).click();
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  await login(page, https, "synthetic-admin");
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("当前身份没有读取权限");
  await expect(page.getByRole("dialog").getByRole("article")).toHaveCount(0);
});
for (const [width, height] of [
  [1440, 900],
  [1280, 800],
  [1024, 768],
  [834, 1112],
  [390, 844],
  [360, 800],
]) {
  test(`HTTPS five pages no overflow ${width}x${height}`, async ({ page, https }, info) => {
    await page.setViewportSize({ width, height });
    await login(page, https);
    await select(page);
    for (const label of ["总览", "预测", "影响因素", "产能模拟", "预测质量"]) {
      await page.getByRole("link", { name: new RegExp(label + "$") }).click();
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator('[data-state="LOADING"]')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.evaluate(() => {
        let caption = document.getElementById("s4-synthetic-caption");
        if (!caption) {
          caption = document.createElement("p");
          caption.id = "s4-synthetic-caption";
          document.body.prepend(caption);
        }
        caption.textContent = "SYNTHETIC DESIGN/ACCEPTANCE FIXTURE — NOT PRODUCTION DATA";
      });
      await page.screenshot({
        path: info.outputPath(`${label}-${width}x${height}-SYNTHETIC.png`),
        fullPage: true,
      });
    }
  });
}

test("real revoked PG session removes old sensitive DOM and refresh never restores selection", async ({
  page,
  https,
}) => {
  await login(page, https, "synthetic-other");
  await select(page, "SYNTHETIC_BASE_2");
  await expect(page.getByLabel("核心四项指标")).toBeVisible();
  const revoked = await page.request.post(https + "/__s4_test__/revoke-other");
  expect(revoked.status()).toBe(200);
  await page.getByRole("link", { name: /预测$/ }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  await expect(page.locator(".d-kpis")).toHaveCount(0);
  await expect(page.locator("svg")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("SYNTHETIC_BASE_2");
  await login(page, https, "synthetic-other");
  await page.reload();
  await expect(page.locator(".d-context-title")).toContainText("请选择已保存预测");
});

test("login error, authorized selector and keyboard large-text visual evidence", async ({
  page,
  https,
}, info) => {
  await page.setViewportSize(
    info.project.name === "chromium-mobile"
      ? { width: 390, height: 844 }
      : { width: 1440, height: 900 },
  );
  async function capture(name: string) {
    await page.evaluate(() => {
      let label = document.getElementById("s4-synthetic-caption");
      if (!label) {
        label = document.createElement("p");
        label.id = "s4-synthetic-caption";
        document.body.prepend(label);
      }
      label.textContent = "SYNTHETIC ACCEPTANCE FIXTURE — NOT PRODUCTION DATA";
    });
    await page.screenshot({ path: info.outputPath(`${name}-SYNTHETIC.png`), fullPage: true });
  }
  await page.goto(https + "/dashboard/overview");
  await expect(page.getByLabel("用户名", { exact: true })).toBeVisible();
  await capture("login");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-user");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-wrong-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("用户名或密码不正确");
  await capture("login-error");
  await page.getByLabel("密码", { exact: true }).fill("SYNTHETIC-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const opener = page.getByRole("button", { name: "选择已保存预测", exact: true });
  await opener.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog").getByRole("article")).toHaveCount(4);
  await expect(page.getByRole("dialog").locator('[name="run_id"]')).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(() => {
    document.querySelector<HTMLElement>(".dashboard")!.style.fontSize = "30px";
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await capture("authorized-selector");
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
});
