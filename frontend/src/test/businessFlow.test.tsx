import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { Dashboard } from "../dashboard/app/Dashboard";
import { invalidateSecurity } from "../dashboard/api/security";
import { request } from "../dashboard/api/client";
import { authEnvelope, userSchema, listSchema } from "../dashboard/schemas/business";
import { auth, business, user, scope, listing, selection, reply } from "./businessFixtures";
import fixture from "./fixtures/dashboard-synthetic.json";
import { z } from "zod";
import { ForecastProvider, useForecast } from "../dashboard/context/ForecastContext";
import { forecastQuery, readSchemas } from "../dashboard/schemas/contracts";

afterEach(() => vi.restoreAllMocks());
function mount() {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    if (!this.open) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={["/dashboard/overview"]}>
        <Dashboard />
      </MemoryRouter>
    </StrictMode>,
  );
}
function fetcher() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input).split("?")[0];
    if (path.endsWith("/me")) return reply(auth(user));
    if (path.endsWith("/csrf")) return reply(auth({ csrf_token: "SYNTHETIC", expires_in: 300 }));
    if (path.endsWith("/scope")) return reply(business(scope));
    if (path.endsWith("/saved-runs")) return reply(business(listing));
    if (path.endsWith("/selection")) return reply(business(selection));
    const kind = path.split("/").pop() as keyof typeof fixture.reads;
    return reply(fixture.reads[kind]);
  });
}
async function select() {
  fireEvent.click(await screen.findByRole("button", { name: "选择已保存预测" }));
  fireEvent.click(await screen.findByRole("button", { name: "核验并使用保存预测" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
}
it("fresh session restore never restores a forecast; revocation physically unmounts all data", async () => {
  fetcher();
  mount();
  await screen.findByRole("navigation");
  expect(document.querySelector(".d-context-title")?.textContent).toBe("请选择已保存预测");
  await select();
  await waitFor(() => expect(document.querySelector(".d-kpis")?.textContent).toContain("1820"));
  act(() => invalidateSecurity("session"));
  expect(screen.getByLabelText("用户名")).toBeTruthy();
  expect(document.querySelector(".d-kpis")).toBeNull();
  expect(document.querySelector("svg")).toBeNull();
  expect(document.body.textContent).not.toContain(fixture.query.entity_id);
});
it("grant/hash conflict clears curve/KPIs and requires a new explicit selection", async () => {
  fetcher();
  mount();
  await select();
  await waitFor(() => expect(document.querySelector(".d-kpis")).toBeTruthy());
  act(() => invalidateSecurity("access"));
  expect(document.querySelector(".d-kpis")).toBeNull();
  expect(document.querySelector(".d-context-title")?.textContent).toBe("请选择已保存预测");
  expect(screen.getByRole("alert").textContent).toContain("旧结果已清除");
});
it("handoff projection mismatch never commits a record", async () => {
  const fetch = fetcher();
  const normal = fetch.getMockImplementation()!;
  fetch.mockImplementation((input, init) =>
    String(input).endsWith("/selection")
      ? Promise.resolve(reply(business({ ...selection, projection_hash: "0".repeat(64) })))
      : normal(input, init),
  );
  mount();
  await select();
  expect(document.querySelector(".d-kpis")).toBeNull();
  expect(document.querySelector(".d-context-title")?.textContent).toBe("请选择已保存预测");
});
it("filter edit invalidates cursor; only a server-issued next cursor is submitted", async () => {
  const fetch = fetcher();
  const normal = fetch.getMockImplementation()!;
  fetch.mockImplementation((input, init) =>
    String(input).includes("/saved-runs")
      ? Promise.resolve(reply(business({ ...listing, next_cursor: "SYNTHETIC_SIGNED_CURSOR" })))
      : normal(input, init),
  );
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "选择已保存预测" }));
  fireEvent.click(await screen.findByRole("button", { name: "下一页" }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([url]) => String(url).includes("cursor=SYNTHETIC_SIGNED_CURSOR")),
    ).toBe(true),
  );
  await waitFor(() =>
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "查询授权记录" }).disabled).toBe(
      false,
    ),
  );
  fireEvent.change(screen.getByLabelText("产季"), { target: { value: "2025-2026" } });
  fireEvent.click(screen.getByRole("button", { name: "查询授权记录" }));
  await waitFor(() => {
    const last = fetch.mock.calls.filter(([url]) => String(url).includes("/saved-runs")).at(-1)!;
    expect(String(last[0])).toContain("target_season=2025-2026");
    expect(String(last[0])).not.toContain("cursor=");
  });
});
it("late login/user response cannot overwrite a newer session boundary", async () => {
  let resolve!: (value: Response) => void;
  vi.spyOn(globalThis, "fetch").mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const pending = request(
    "/api/v1/auth/me",
    authEnvelope(userSchema),
    new AbortController().signal,
  );
  invalidateSecurity("session");
  resolve(reply(auth(user)));
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
});

it("leaving Dashboard aborts the active login, not only the initial me request", async () => {
  let loginSignal: AbortSignal | undefined;
  let finish!: (value: Response) => void;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (String(input).endsWith("/me")) return reply({}, 401);
    if (String(input).endsWith("/csrf"))
      return reply(auth({ csrf_token: "SYNTHETIC", expires_in: 300 }));
    loginSignal = init?.signal as AbortSignal;
    return new Promise((done) => {
      finish = done;
    });
  });
  const view = mount();
  fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "synthetic-user" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "SYNTHETIC-password-123" } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await waitFor(() => expect(loginSignal).toBeDefined());
  view.unmount();
  try {
    expect(loginSignal?.aborted).toBe(true);
  } finally {
    await act(async () => {
      finish(reply(auth(user)));
    });
  }
  expect(screen.queryByRole("navigation")).toBeNull();
});
it("S2 list retains all identity/hash bytes and rejects injected actor or unsafe run IDs", () => {
  expect(listSchema.parse(listing)).toEqual(listing);
  expect(
    listSchema.safeParse({
      ...listing,
      items: [
        {
          ...listing.items[0],
          forecast_identity: {
            ...listing.items[0].forecast_identity,
            run_id: Number.MAX_SAFE_INTEGER + 1,
          },
        },
      ],
    }).success,
  ).toBe(false);
  expect(listSchema.safeParse({ ...listing, actor: "ADMIN" }).success).toBe(false);
});

it("serializes CSRF rotation together with each concurrent POST", async () => {
  const calls: string[] = [];
  let release!: () => void;
  const held = new Promise<void>((done) => {
    release = done;
  });
  let posts = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push(String(input));
    if (String(input).endsWith("/csrf"))
      return reply(auth({ csrf_token: "SYNTHETIC", expires_in: 300 }));
    posts++;
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("SYNTHETIC");
    expect(new Headers(init?.headers).has("Origin")).toBe(false);
    if (posts === 1) await held;
    return reply(auth({ logged_out: true }));
  });
  const schema = authEnvelope(z.object({ logged_out: z.literal(true) }));
  const first = request("/api/v1/auth/logout", schema, new AbortController().signal, undefined, {});
  const second = request(
    "/api/v1/auth/logout",
    schema,
    new AbortController().signal,
    undefined,
    {},
  );
  await waitFor(() => expect(posts).toBe(1));
  expect(calls).toEqual(["/api/v1/auth/csrf", "/api/v1/auth/logout"]);
  release();
  await Promise.all([first, second]);
  expect(calls).toEqual([
    "/api/v1/auth/csrf",
    "/api/v1/auth/logout",
    "/api/v1/auth/csrf",
    "/api/v1/auth/logout",
  ]);
});

it("handoff expiry clears context/date and unmounts sensitive children", () => {
  vi.useFakeTimers();
  function Probe() {
    const context = useForecast();
    return (
      <>
        <button
          onClick={() => {
            context.commit({
              query: forecastQuery.parse(fixture.query),
              curve: readSchemas.curve.parse(fixture.reads.curve),
              key: "SYNTHETIC",
              handoff: { token: "SYNTHETIC", expiresAt: Date.now() + 300000 },
            });
            context.selectDate("2026-01-02");
          }}
        >
          seed expiry
        </button>
        <output>
          {context.verified ? "SENSITIVE" : "CLEARED"}:{context.selectedDate}
        </output>
      </>
    );
  }
  try {
    render(
      <ForecastProvider>
        <Probe />
      </ForecastProvider>,
    );
    fireEvent.click(screen.getByText("seed expiry"));
    expect(screen.getByText("SENSITIVE:2026-01-02")).toBeTruthy();
    act(() => vi.advanceTimersByTime(300001));
    expect(screen.getByText("CLEARED:")).toBeTruthy();
    expect(screen.queryByText("SENSITIVE:2026-01-02")).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});
