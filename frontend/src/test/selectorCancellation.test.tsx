import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthorizedSavedRunSelector } from "../dashboard/components/AuthorizedSavedRunSelector";
import { ForecastProvider, useForecast } from "../dashboard/context/ForecastContext";
import * as api from "../dashboard/api/client";
import { forecastQuery, readSchemas } from "../dashboard/schemas/contracts";
import fixture from "./fixtures/dashboard-synthetic.json";
import { business, scope, listing, selection, auth, reply } from "./businessFixtures";

const query = forecastQuery.parse(fixture.query);
const curve = readSchemas.curve.parse(fixture.reads.curve);
function deferred() {
  let resolve!: (v: typeof curve) => void;
  let reject!: (v: Error) => void;
  const promise = new Promise<typeof curve>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function Harness() {
  const context = useForecast();
  return (
    <>
      <button onClick={context.openSelector}>Open selector</button>
      <button
        onClick={() => {
          context.commit({ query, curve, key: "ORIGINAL_A" });
          context.selectDate("2026-01-02");
        }}
      >
        Seed valid A
      </button>
      <output data-testid="context">
        {JSON.stringify({ key: context.verified?.key, date: context.selectedDate })}
      </output>
      <AuthorizedSavedRunSelector />
    </>
  );
}
const button = () =>
  screen.getByRole<HTMLButtonElement>("button", { name: /核验并使用保存预测|正在核验…/ });
async function open() {
  fireEvent.click(screen.getByText("Open selector"));
  await screen.findByRole("button", { name: "核验并使用保存预测" });
  return screen.getByRole("dialog");
}
function mount() {
  return render(
    <StrictMode>
      <ForecastProvider>
        <Harness />
      </ForecastProvider>
    </StrictMode>,
  );
}
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    if (!this.open) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input).split("?")[0];
    if (path.endsWith("/scope")) return reply(business(scope));
    if (path.endsWith("/saved-runs")) return reply(business(listing));
    if (path.endsWith("/selection")) return reply(business(selection));
    if (path.endsWith("/csrf")) return reply(auth({ csrf_token: "SYNTHETIC", expires_in: 300 }));
    throw new Error("Unexpected unit request");
  });
});
afterEach(() => vi.restoreAllMocks());

it.each(["button", "escape", "native"] as const)(
  "StrictMode %s close resets busy, preserves A and protects B from late A finally",
  async (way) => {
    const old = deferred(),
      next = deferred();
    const read = vi
      .spyOn(api, "read")
      .mockImplementationOnce(() => old.promise)
      .mockImplementationOnce(() => next.promise);
    mount();
    fireEvent.click(screen.getByText("Seed valid A"));
    const previous = screen.getByTestId("context").textContent;
    const dialog = await open();
    fireEvent.click(button());
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    expect(button().disabled).toBe(true);
    if (way === "button") fireEvent.click(screen.getByText("关闭"));
    else if (way === "escape") fireEvent(dialog, new Event("cancel", { cancelable: true }));
    else act(() => (dialog as HTMLDialogElement).close());
    expect(read.mock.calls[0][2].aborted).toBe(true);
    expect(screen.getByTestId("context").textContent).toBe(previous);
    await open();
    expect(button().disabled).toBe(false);
    fireEvent.click(button());
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    await act(async () => {
      old.resolve(curve);
      await old.promise;
    });
    expect(button().disabled).toBe(true);
    expect(screen.getByTestId("context").textContent).toBe(previous);
    await act(async () => {
      next.resolve(curve);
      await next.promise;
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByTestId("context").textContent).toContain(query.entity_id);
  },
);
it.each(["resolve", "reject"] as const)(
  "filter change cancels old %s and prevents invalid commit",
  async (settlement) => {
    const old = deferred();
    const read = vi.spyOn(api, "read").mockImplementationOnce(() => old.promise);
    mount();
    fireEvent.click(screen.getByText("Seed valid A"));
    const previous = screen.getByTestId("context").textContent;
    await open();
    fireEvent.click(button());
    await waitFor(() => expect(read).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText("产季"), { target: { value: "2026-2027" } });
    expect(read.mock.calls[0][2].aborted).toBe(true);
    await act(async () => {
      if (settlement === "resolve") old.resolve(curve);
      else old.reject(new api.DashboardError(409, "OLD"));
      await old.promise.catch(() => {});
    });
    expect(screen.getByTestId("context").textContent).toBe(previous);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "查询授权记录" }).disabled).toBe(
      false,
    );
  },
);
it("native synchronous open removal rejects a result before the close event", async () => {
  const pending = deferred();
  const read = vi.spyOn(api, "read").mockImplementationOnce(() => pending.promise);
  mount();
  const dialog = await open();
  fireEvent.click(button());
  await waitFor(() => expect(read).toHaveBeenCalled());
  dialog.removeAttribute("open");
  await act(async () => {
    pending.resolve(curve);
    await pending.promise;
  });
  expect(screen.getByTestId("context").textContent).not.toContain(query.entity_id);
  fireEvent(dialog, new Event("close"));
  await open();
  expect(button().disabled).toBe(false);
});
it("unmount aborts active request; ignored abort completion cannot commit", async () => {
  const pending = deferred();
  const read = vi.spyOn(api, "read").mockImplementationOnce(() => pending.promise);
  const view = mount();
  await open();
  fireEvent.click(button());
  await waitFor(() => expect(read).toHaveBeenCalled());
  view.unmount();
  expect(read.mock.calls[0][2].aborted).toBe(true);
  await act(async () => {
    pending.resolve(curve);
    await pending.promise;
  });
  expect(screen.queryByTestId("context")).toBeNull();
});
it.each([0, 409])(
  "failure %s never commits and repeated reopen permits a new verification",
  async (status) => {
    const read = vi
      .spyOn(api, "read")
      .mockRejectedValueOnce(new api.DashboardError(status, "SYNTHETIC"))
      .mockResolvedValue(curve);
    mount();
    await open();
    fireEvent.click(button());
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("context").textContent).not.toContain(query.entity_id),
    );
    if (screen.queryByRole("dialog")) fireEvent.click(screen.getByText("关闭"));
    for (let i = 0; i < 3; i++) {
      await open();
      fireEvent.click(screen.getByText("关闭"));
    }
    await open();
    fireEvent.click(button());
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByTestId("context").textContent).toContain(query.entity_id);
  },
);
it("does not expose manual run/hash inputs or accept unknown identity fields", async () => {
  mount();
  await open();
  expect(document.querySelector('[name="run_id"]')).toBeNull();
  expect(document.querySelector('[name="expected_source_result_hash"]')).toBeNull();
  expect(forecastQuery.safeParse({ ...query, actor: "administrator" }).success).toBe(false);
});
