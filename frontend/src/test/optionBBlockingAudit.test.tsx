// SYNTHETIC=true. Defect probes, NOT full HTTP/PostgreSQL acceptance.
// These intentionally fail at the audited main; do not weaken or skip them.
import { StrictMode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthorizedSavedRunSelector } from "../dashboard/components/AuthorizedSavedRunSelector";
import { ForecastProvider, useForecast } from "../dashboard/context/ForecastContext";
import { simulate } from "../dashboard/api/client";
import { forecastQuery, readSchemas } from "../dashboard/schemas/contracts";
import { auth, business, scope, listing, reply } from "./businessFixtures";
import fixture from "./fixtures/dashboard-synthetic.json";

function Harness() {
  const forecast = useForecast();
  return (
    <>
      <button
        onClick={() =>
          forecast.commit({
            query: forecastQuery.parse(fixture.query),
            curve: readSchemas.curve.parse(fixture.reads.curve),
            key: "SYNTHETIC_OLD_CONTEXT",
            handoff: { token: "SYNTHETIC_OLD_HANDOFF", expiresAt: Date.now() + 300000 },
          })
        }
      >
        Seed
      </button>
      <button onClick={forecast.openSelector}>Open</button>
      <output data-testid="verified-key">{forecast.verified?.key ?? "CLEARED"}</output>
      <output data-testid="identity-handoff-date">
        {JSON.stringify({
          identity: forecast.verified?.query,
          handoff: forecast.verified?.handoff,
          date: forecast.selectedDate,
        })}
      </output>
      <p>{forecast.notice}</p>
      <AuthorizedSavedRunSelector />
    </>
  );
}

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => vi.restoreAllMocks());

it.each(["grant_revision", "catalog_snapshot"] as const)(
  "directory conflict %s must clear prior verified forecast",
  async (field) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const changed = { ...listing, [field]: field === "grant_revision" ? 2 : "b".repeat(64) };
      return reply(business(String(url).includes("/scope") ? scope : changed));
    });
    render(
      <StrictMode>
        <ForecastProvider>
          <Harness />
        </ForecastProvider>
      </StrictMode>,
    );
    fireEvent.click(screen.getByText("Seed"));
    expect(screen.getByTestId("verified-key").textContent).toBe("SYNTHETIC_OLD_CONTEXT");
    fireEvent.click(screen.getByText("Open"));
    // Successful invalidation unmounts the old error panel and exposes the
    // existing provider re-selection notice. The original failing clear
    // assertion below is retained; original probe bytes are archived in red/.
    await screen.findByText(/旧结果已清除/);
    expect(screen.getByTestId("verified-key").textContent).toBe("CLEARED");
    expect(screen.getByTestId("identity-handoff-date").textContent).not.toContain(
      "SYNTHETIC_OLD_HANDOFF",
    );
    expect(screen.getByTestId("identity-handoff-date").textContent).not.toContain(
      fixture.query.entity_id,
    );
  },
);

it("simulation must reject a result from a different submitted capacity/version", async () => {
  const input = structuredClone(fixture.simulation_request);
  input.capacity_rows[0].daily_handling_capacity_kg = "999999";
  input.scenario_version = "SYNTHETIC_CHANGED_VERSION";
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
    reply(
      String(url).endsWith("/csrf")
        ? auth({ csrf_token: "SYNTHETIC", expires_in: 300 })
        : fixture.simulation,
    ),
  );
  await expect(simulate(input as never, new AbortController().signal)).rejects.toThrow();
});

it.each([422, 503] as const)(
  "ordinary scope failure %s preserves the previously verified context",
  async (status) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(reply({ data: null }, status));
    render(
      <StrictMode>
        <ForecastProvider>
          <Harness />
        </ForecastProvider>
      </StrictMode>,
    );
    fireEvent.click(screen.getByText("Seed"));
    fireEvent.click(screen.getByText("Open"));
    await screen.findByText(status === 422 ? /输入不合法/ : /服务暂时不可用/);
    expect(screen.getByTestId("verified-key").textContent).toBe("SYNTHETIC_OLD_CONTEXT");
    expect(screen.getByTestId("identity-handoff-date").textContent).toContain(
      "SYNTHETIC_OLD_HANDOFF",
    );
  },
);
