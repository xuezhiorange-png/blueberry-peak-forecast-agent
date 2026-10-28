import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { startOwnedServer, type OwnedServer } from "./support/owned-server";
import { withOwnedAuthority } from "./support/owned-authority";

const probe = "frontend.e2e.support.owned_server:probe_app";

async function released(server: OwnedServer) {
  expect(() => process.kill(server.pid, 0)).toThrow();
  await expect(fetch(server.url + "/__e2e_owned_server__")).rejects.toThrow();
}

async function journal(server: OwnedServer) {
  return (await readFile(server.diagnosticPath, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
}

test("owned diagnostics retain identity, request correlation and clean exit order", async ({
  request,
}) => {
  const server = await startOwnedServer(probe);
  try {
    const response = await server.traceRequest("AUTHORITY_AUDIT", (headers) =>
      request.get(server.url + "/__e2e_owned_server__", { headers }),
    );
    expect((await response.json()).pid).toBe(server.pid);
    server.mark("WORKER_USE_END");
  } finally {
    await server.stop();
  }
  await released(server);
  const events = await journal(server);
  expect(events.every((e) => e.worker_pid === process.pid && e.nonce === server.nonce)).toBe(true);
  expect(events.filter((e) => e.child_pid !== null).every((e) => e.child_pid === server.pid)).toBe(
    true,
  );
  expect(events.map((e) => e.seq)).toEqual(events.map((_, i) => i + 1));
  expect(events.every((e) => Number.isFinite(Date.parse(e.at_utc)))).toBe(true);
  const phases = events.map((e) => e.event);
  for (const phase of ["BOUND", "READY", "CLIENT_REQUEST_BEGIN", "CHILD_EXIT", "CHILD_CLOSE"])
    expect(phases).toContain(phase);
  expect(phases.indexOf("CLIENT_REQUEST_BEGIN")).toBeLessThan(phases.indexOf("CLIENT_REQUEST_END"));
  expect(phases.indexOf("CLIENT_REQUEST_END")).toBeLessThan(phases.indexOf("STOP_BEGIN"));
  expect(phases.indexOf("CHILD_EXIT")).toBeLessThan(phases.indexOf("CHILD_CLOSE"));
  expect(phases.indexOf("CHILD_CLOSE")).toBeLessThan(phases.indexOf("CLEANUP_COMPLETE"));
  const client = events.find((e) => e.event === "CLIENT_REQUEST_BEGIN");
  const asgi = events.filter((e) => e.request_id === client.request_id);
  expect(asgi.some((e) => e.event === "ASGI_REQUEST_BEGIN")).toBe(true);
  expect(asgi.some((e) => e.event === "ASGI_REQUEST_END")).toBe(true);
  expect(server.diagnostics().closed).toBe(true);
});

test("unexpected exit fails visibly and cannot stop another owned listener", async () => {
  const server = await startOwnedServer(probe);
  const other = await startOwnedServer(probe);
  try {
    process.kill(server.pid, "SIGKILL");
    await expect.poll(() => server.diagnostics().closed).toBe(true);
    expect(() => server.assertRunning()).toThrow("OWNED_SERVER_EXITED");
    await expect(server.stop()).rejects.toThrow("OWNED_SERVER_UNCLEAN_EXIT");
    await released(server);
    expect((await fetch(other.url + "/__e2e_owned_server__")).status).toBe(200);
    expect(server.diagnostics().exitSignal).toBe("SIGKILL");
  } finally {
    await other.stop();
    if (!server.diagnostics().closed) await server.stop();
  }
  await released(other);
});

test("an interrupted request is recorded and rethrown while its service stays alive", async () => {
  const server = await startOwnedServer(probe);
  const controller = new AbortController();
  try {
    const outcome = server
      .traceRequest("AUTHORITY_AUDIT", (headers) =>
        fetch(server.url + "/__owned_probe__/held", { headers, signal: controller.signal }),
      )
      .then(
        () => null,
        (error: unknown) => error,
      );
    await expect
      .poll(() =>
        server
          .diagnostics()
          .events.some((e) => e.event === "ASGI_REQUEST_BEGIN" && e.request_kind === "PROBE_HELD"),
      )
      .toBe(true);
    controller.abort();
    expect(await outcome).toBeInstanceOf(Error);
    server.assertRunning();
    expect((await fetch(server.url + "/__e2e_owned_server__")).status).toBe(200);
    await expect
      .poll(() => server.diagnostics().events.some((e) => e.event === "ASGI_DISCONNECT"))
      .toBe(true);
    expect(server.diagnostics().events.some((e) => e.event === "CLIENT_REQUEST_ERROR")).toBe(true);
  } finally {
    controller.abort();
    await server.stop();
  }
  await released(server);
});

test("shutdown with an in-flight request has a verifiable final cleanup", async () => {
  const server = await startOwnedServer(probe);
  const controller = new AbortController();
  try {
    const outcome = server
      .traceRequest("AUTHORITY_AUDIT", (headers) =>
        fetch(server.url + "/__owned_probe__/held", { headers, signal: controller.signal }),
      )
      .then(
        () => null,
        (error: unknown) => error,
      );
    await expect
      .poll(() =>
        server
          .diagnostics()
          .events.some((e) => e.event === "ASGI_REQUEST_BEGIN" && e.request_kind === "PROBE_HELD"),
      )
      .toBe(true);
    const stopping = server.stop();
    controller.abort();
    expect(await outcome).toBeInstanceOf(Error);
    expect((await stopping).forced).toBe(false);
  } finally {
    controller.abort();
    await server.stop();
  }
  await released(server);
  const events = await journal(server);
  expect(events.some((e) => e.event === "STOP_BEGIN")).toBe(true);
  expect(events.at(-1)!.event).toBe("CLEANUP_COMPLETE");
});

test("bounded stderr diagnostics never publish arbitrary child content", async () => {
  const secret = "SYNTHETIC_PRIVATE_CONTENT_DO_NOT_PUBLISH";
  const server = await startOwnedServer(probe, {
    env: {
      SYNTHETIC_FIXTURE_STDERR:
        (secret + " /private/source.xls Authorization: Bearer ").repeat(1000) +
        '\n  File "/private/synthetic-repo/frontend/e2e/support/owned_server.py", line 42, in probe_app',
    },
  });
  await server.stop();
  await released(server);
  const text = await readFile(server.diagnosticPath, "utf8");
  expect(text).not.toContain(secret);
  expect(text).not.toContain("/private/source.xls");
  expect(text).not.toContain("/private/synthetic-repo");
  const summary = server.diagnostics().stderr;
  expect(summary.bytes).toBeGreaterThan(10000);
  expect(summary.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(summary.safe_tail.length).toBeLessThanOrEqual(4096);
  expect(summary.safe_tail).toContain(
    "CODE_FRAME frontend/e2e/support/owned_server.py:42 probe_app",
  );
});

test("worker body failure is retained and cleanup is still completed", async ({ playwright }) => {
  let server: OwnedServer | undefined;
  await expect(
    withOwnedAuthority(
      playwright.request,
      "frontend.e2e.support.dashboard_api:app",
      async (authority) => {
        server = authority.owned;
        throw new Error("SYNTHETIC_BODY_FAILURE");
      },
    ),
  ).rejects.toThrow("SYNTHETIC_BODY_FAILURE");
  expect(server).toBeDefined();
  await released(server!);
  const events = await journal(server!);
  expect(events.some((e) => e.event === "FIXTURE_ERROR")).toBe(true);
  expect(events.some((e) => e.event === "CLEANUP_COMPLETE")).toBe(true);
});

test("audit and cleanup failures are both preserved without a successful fallback", async ({
  playwright,
}) => {
  let server: OwnedServer | undefined;
  let failure: unknown;
  try {
    await withOwnedAuthority(
      playwright.request,
      "frontend.e2e.support.dashboard_api:app",
      async (a) => {
        server = a.owned;
        process.kill(server.pid, "SIGKILL");
        await expect.poll(() => server!.diagnostics().closed).toBe(true);
      },
    );
  } catch (error) {
    failure = error;
  }
  expect(failure).toBeInstanceOf(AggregateError);
  const errors = (failure as AggregateError).errors;
  expect(errors.length).toBe(2);
  expect(String(errors[0])).toContain("apiRequestContext.get");
  expect(String(errors[1])).toContain("OWNED_SERVER_UNCLEAN_EXIT");
  await released(server!);
  const events = await journal(server!);
  expect(
    events.some((e) => e.event === "CLIENT_REQUEST_ERROR" && e.phase === "AUTHORITY_AUDIT"),
  ).toBe(true);
});
