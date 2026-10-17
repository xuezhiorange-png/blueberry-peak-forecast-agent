import { test as base, expect, type Page } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

// All accounts/data are explicit SYNTHETIC fixtures. No credential enters the
// production bundle; this driver types a test password into the real login UI.
const test = base.extend<Record<string, never>, { https: string }>({
  https: [
    async ({ playwright }, use, worker) => {
      if (process.env.S4_HTTPS_URL) {
        await use(process.env.S4_HTTPS_URL);
        return;
      }
      const directory = mkdtempSync(resolve(tmpdir(), "s4-https-browser-"));
      const url = `https://127.0.0.1:${47200 + worker.workerIndex}`;
      execFileSync(
        "openssl",
        [
          "req",
          "-x509",
          "-newkey",
          "rsa:2048",
          "-nodes",
          "-keyout",
          directory + "/key.pem",
          "-out",
          directory + "/cert.pem",
          "-days",
          "2",
          "-subj",
          "/CN=127.0.0.1",
        ],
        { stdio: "pipe" },
      );
      execFileSync("npm", ["run", "build"], { stdio: "pipe" });
      const child = spawn(
        process.env.DASHBOARD_TEST_PYTHON ?? "python3",
        [
          "-m",
          "uvicorn",
          "frontend.e2e.support.option_b_binding_pg:app",
          "--host",
          "127.0.0.1",
          "--port",
          new URL(url).port,
          "--ssl-keyfile",
          directory + "/key.pem",
          "--ssl-certfile",
          directory + "/cert.pem",
        ],
        {
          cwd: resolve(process.cwd(), ".."),
          env: { ...process.env, PYTHONPATH: ".", S4_SYNTHETIC_ONLY: "1", S4_HTTPS_ORIGIN: url },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      let logs = "";
      child.stdout.on("data", (v) => {
        logs = (logs + v).slice(-32768);
      });
      child.stderr.on("data", (v) => {
        logs = (logs + v).slice(-32768);
      });
      const api = await playwright.request.newContext({ ignoreHTTPSErrors: true });
      try {
        await expect
          .poll(
            async () => {
              if (child.exitCode !== null) throw new Error(logs);
              try {
                return (await api.get(url + "/__s4_test__/ready")).status();
              } catch {
                return 0;
              }
            },
            { timeout: 60000 },
          )
          .toBe(200);
        await use(url);
        expect(
          (await (await api.get(url + "/__s4_test__/ready")).json()).post_seed_business_dml_count,
        ).toBe(0);
      } finally {
        const stopped = new Promise<void>((resolveExit) =>
          child.once("close", () => resolveExit()),
        );
        child.kill("SIGTERM");
        await stopped;
        await api.dispose();
        if (child.exitCode !== 0 && child.signalCode !== "SIGTERM") throw new Error(logs);
        expect(logs).toContain("Application shutdown complete.");
      }
    },
    { scope: "worker" },
  ],
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

test("OPTION_B real directory snapshot conflict clears forecast, simulation and draft", async ({
  page,
  https,
}, info) => {
  await login(page, https);
  await select(page);
  await page.getByRole("link", { name: /产能模拟$/ }).click();
  await page.getByLabel("显式选择成本合同（无默认）").selectOption("SYNTHETIC_UNDER_4X_R1");
  await page.getByLabel("情景 ID", { exact: true }).fill("SYNTHETIC_OLD_DRAFT");
  await page.getByLabel("情景版本", { exact: true }).fill("R1");
  await page.getByLabel("直接处理能力 kg/日", { exact: true }).fill("140");
  await page.getByRole("button", { name: "将本日产能输入应用到全部日期…" }).click();
  await page.getByRole("button", { name: "确认复制至这些日期" }).click();
  const result = page.waitForResponse((r) => r.url().endsWith("/simulate-capacity"));
  await page.getByRole("button", { name: "模拟当前情景", exact: true }).click();
  const previous = await (await result).json();
  await expect(page.locator("main")).toContainText(previous.engine_result_hash);
  expect(
    (await page.request.post(https + "/__option_b_test__/change-directory-after-scope")).status(),
  ).toBe(200);
  const scopeReply = page.waitForResponse((r) => r.url().endsWith("/business-access/scope"));
  const listReply = page.waitForResponse((r) => r.url().includes("/business-access/saved-runs"));
  await page.getByRole("button", { name: "选择已保存预测", exact: true }).click();
  const scopeResponse = await scopeReply,
    listResponse = await listReply;
  expect(scopeResponse.status()).toBe(200);
  expect(listResponse.status()).toBe(200);
  const scopeData = (await scopeResponse.json()).data;
  const listData = (await listResponse.json()).data;
  expect(scopeData.catalog_snapshot).not.toBe(listData.catalog_snapshot);
  await expect(page.locator(".d-context-title")).toContainText("请选择已保存预测");
  await expect(page.locator(".d-kpis, main svg, .d-rank-list")).toHaveCount(0);
  await expect(page.locator("main")).not.toContainText(previous.engine_result_hash);
  await select(page);
  await expect(page.getByLabel("情景 ID", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("情景版本", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("直接处理能力 kg/日", { exact: true })).toHaveValue("");
  await info.attach("OPTION_B-real-directory-conflict-SYNTHETIC", {
    body: JSON.stringify({
      scope_snapshot: scopeData.catalog_snapshot,
      list_snapshot: listData.catalog_snapshot,
      previous_engine_hash: previous.engine_result_hash,
      cleared: true,
    }),
    contentType: "application/json",
  });
});
