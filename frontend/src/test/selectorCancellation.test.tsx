import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthorizedSavedRunSelector } from "../dashboard/components/AuthorizedSavedRunSelector";
import { ForecastProvider, useForecast } from "../dashboard/context/ForecastContext";
import * as api from "../dashboard/api/client";
import { forecastQuery, readSchemas } from "../dashboard/schemas/contracts";
import fixture from "./fixtures/dashboard-synthetic.json";

// SYNTHETIC=true. Deliberately ignore AbortSignal when resolving old promises.
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
function openAndFill() {
  fireEvent.click(screen.getByText("Open selector"));
  const dialog = screen.getByRole("dialog");
  for (const [key, value] of Object.entries(query))
    fireEvent.change(dialog.querySelector(`[name="${key}"]`)!, {
      target: { value: String(value) },
    });
  return dialog;
}
function submit() {
  fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);
}
function retryButton() {
  return screen.getByRole("dialog").querySelector<HTMLButtonElement>('button[type="submit"]')!;
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
});
afterEach(() => vi.restoreAllMocks());

it("native dialog closure rejects a response even before its queued close event", async () => {
  const pending = deferred();
  vi.spyOn(api, "read").mockImplementationOnce(() => pending.promise);
  render(
    <StrictMode>
      <ForecastProvider>
        <Harness />
      </ForecastProvider>
    </StrictMode>,
  );
  fireEvent.click(screen.getByText("Seed valid A"));
  const previous = screen.getByTestId("context").textContent;
  const dialog = openAndFill();
  submit();
  // Browser dialog.close() clears open synchronously, then queues its close event.
  dialog.removeAttribute("open");
  await act(async () => {
    pending.resolve(curve);
    await pending.promise;
  });
  expect(screen.getByTestId("context").textContent).toBe(previous);
  fireEvent(dialog, new Event("close"));
  fireEvent.click(screen.getByText("Open selector"));
  expect(retryButton().disabled).toBe(false);
});

it("resubmission invalidates old generation and ignores its completion after the new result", async () => {
  const old = deferred(),
    next = deferred();
  const read = vi
    .spyOn(api, "read")
    .mockImplementationOnce(() => old.promise)
    .mockImplementationOnce(() => next.promise);
  render(
    <StrictMode>
      <ForecastProvider>
        <Harness />
      </ForecastProvider>
    </StrictMode>,
  );
  const dialog = openAndFill();
  submit();
  // Synthetic reentrant submission exercises the handler, even when the UI button is busy.
  fireEvent.submit(dialog.querySelector("form")!);
  expect(read.mock.calls[0][2].aborted).toBe(true);
  expect(read.mock.calls[1][2].aborted).toBe(false);
  await act(async () => {
    next.resolve(curve);
    await next.promise;
  });
  const committed = screen.getByTestId("context").textContent;
  await act(async () => {
    old.reject(new api.DashboardError(409, "OLD_REQUEST"));
    await old.promise.catch(() => {});
  });
  expect(screen.getByTestId("context").textContent).toBe(committed);
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("invalid run ID never queries or replaces a previously verified context", () => {
  const read = vi.spyOn(api, "read");
  render(
    <StrictMode>
      <ForecastProvider>
        <Harness />
      </ForecastProvider>
    </StrictMode>,
  );
  fireEvent.click(screen.getByText("Seed valid A"));
  const previous = screen.getByTestId("context").textContent;
  const dialog = openAndFill();
  fireEvent.change(dialog.querySelector('[name="run_id"]')!, { target: { value: "not-a-run" } });
  submit();
  expect(retryButton().disabled).toBe(false);
  expect(read).not.toHaveBeenCalled();
  expect(screen.getByTestId("context").textContent).toBe(previous);
});

it.each(["button", "escape", "native"] as const)(
  "StrictMode %s close resets busy and allows unchanged retry",
  async (way) => {
    const old = deferred(),
      next = deferred();
    const read = vi
      .spyOn(api, "read")
      .mockImplementationOnce(() => old.promise)
      .mockImplementationOnce(() => next.promise);
    render(
      <StrictMode>
        <ForecastProvider>
          <Harness />
        </ForecastProvider>
      </StrictMode>,
    );
    const dialog = openAndFill();
    submit();
    expect(retryButton().disabled).toBe(true);
    if (way === "button") fireEvent.click(screen.getByText("关闭"));
    else if (way === "escape") fireEvent(dialog, new Event("cancel", { cancelable: true }));
    else act(() => (dialog as HTMLDialogElement).close());
    expect(read.mock.calls[0][2].aborted).toBe(true);
    fireEvent.click(screen.getByText("Open selector"));
    expect(retryButton().disabled).toBe(false);
    expect(retryButton().textContent).toBe("核验并使用保存预测");
    submit();
    expect(retryButton().disabled).toBe(true);
    await act(async () => {
      old.resolve(curve);
      await old.promise;
    });
    expect(retryButton().disabled).toBe(true); // old finally must not finish request B
    expect(screen.getByTestId("context").textContent).not.toContain("SYNTHETIC");
    await act(async () => {
      next.resolve(curve);
      await next.promise;
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByTestId("context").textContent).toContain(query.entity_id);
  },
);

it.each(["resolve", "reject"] as const)(
  "form cancellation rejects late %s and protects previous valid context/date",
  async (settlement) => {
    const old = deferred(),
      next = deferred();
    const read = vi
      .spyOn(api, "read")
      .mockImplementationOnce(() => old.promise)
      .mockImplementationOnce(() => next.promise);
    render(
      <StrictMode>
        <ForecastProvider>
          <Harness />
        </ForecastProvider>
      </StrictMode>,
    );
    fireEvent.click(screen.getByText("Seed valid A"));
    const previous = screen.getByTestId("context").textContent;
    const dialog = openAndFill();
    submit();
    fireEvent.change(dialog.querySelector('[name="entity_id"]')!, {
      target: { value: "SYNTHETIC_B" },
    });
    expect(read.mock.calls[0][2].aborted).toBe(true);
    expect(retryButton().disabled).toBe(false);
    submit();
    await act(async () => {
      if (settlement === "resolve") old.resolve(curve);
      else old.reject(new api.DashboardError(409, "AUTHORITY_MISMATCH"));
      await old.promise.catch(() => {});
    });
    expect(retryButton().disabled).toBe(true);
    expect(screen.getByTestId("context").textContent).toBe(previous);
    fireEvent.click(screen.getByText("关闭"));
    await act(async () => {
      next.resolve(curve);
      await next.promise;
    });
    expect(screen.getByTestId("context").textContent).toBe(previous);
  },
);

it.each([0, 409])(
  "recovers from failure %s and repeated open/close without committing invalid input",
  async (status) => {
    const read = vi
      .spyOn(api, "read")
      .mockRejectedValueOnce(new api.DashboardError(status, "TEST_ONLY"))
      .mockResolvedValueOnce(curve);
    render(
      <StrictMode>
        <ForecastProvider>
          <Harness />
        </ForecastProvider>
      </StrictMode>,
    );
    openAndFill();
    submit();
    await waitFor(() => expect(retryButton().disabled).toBe(false));
    expect(screen.getByTestId("context").textContent).not.toContain(query.entity_id);
    for (let i = 0; i < 3; i++) {
      fireEvent.click(screen.getByText("关闭"));
      fireEvent.click(screen.getByText("Open selector"));
      expect(retryButton().disabled).toBe(false);
    }
    submit();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(read).toHaveBeenCalledTimes(2);
  },
);

it("unmount aborts active request; ignored-abort completion cannot commit", async () => {
  const pending = deferred();
  const read = vi.spyOn(api, "read").mockImplementationOnce(() => pending.promise);
  const view = render(
    <StrictMode>
      <ForecastProvider>
        <Harness />
      </ForecastProvider>
    </StrictMode>,
  );
  openAndFill();
  submit();
  view.unmount();
  expect(read.mock.calls[0][2].aborted).toBe(true);
  await act(async () => {
    pending.resolve(curve);
    await pending.promise;
  });
  expect(screen.queryByTestId("context")).toBeNull();
});
