import { test, expect } from "@playwright/test";
import { createServer, type Socket, type AddressInfo } from "node:net";
import { once } from "node:events";
import { withOwnedHttps, HttpsLifecycleError, bounded } from "./support/https-fixture";

test("TLS identity, real readiness and repeated graceful cleanup preserve an unrelated listener", async ({
  playwright,
}, info) => {
  const unrelated = createServer((socket) => socket.end("SYNTHETIC_UNRELATED"));
  unrelated.listen(0, "127.0.0.1");
  await once(unrelated, "listening");
  try {
    for (let i = 0; i < 2; i++) {
      let pid = 0;
      await withOwnedHttps(
        {
          app: "probe",
          playwright,
          outputDir: info.outputDir,
          onEvent: (event) => {
            pid = event.pid;
            if (event.phase === "LIFESPAN_STOP") {
              // Only this ChildProcess's verified receipt, never a name/port kill.
              process.kill(pid, "SIGTERM");
              process.kill(pid, "SIGTERM");
            }
          },
        },
        async (url) => {
          const api = await playwright.request.newContext({ ignoreHTTPSErrors: true });
          try {
            expect((await api.get(url + "/__e2e_https_owner__")).status()).toBe(200);
          } finally {
            await api.dispose();
          }
        },
      );
      expect(() => process.kill(pid, 0)).toThrow();
      expect(unrelated.listening).toBe(true);
    }
  } finally {
    await new Promise<void>((done) => unrelated.close(() => done()));
  }
});

test("deterministic slow startup cannot enter the body before readiness", async ({
  playwright,
}, info) => {
  let connection: Socket | undefined;
  let release!: () => void;
  const arrived = new Promise<void>((done) => {
    release = done;
  });
  const gate = createServer((socket) => {
    connection = socket;
    release();
  });
  gate.listen(0, "127.0.0.1");
  await once(gate, "listening");
  const port = (gate.address() as AddressInfo).port;
  let entered = false;
  const running = withOwnedHttps(
    {
      app: "probe",
      playwright,
      outputDir: info.outputDir,
      env: { SYNTHETIC_HTTPS_START_GATE_PORT: String(port) },
    },
    async () => {
      entered = true;
    },
  );
  try {
    await bounded(arrived, 15_000, "probe-arrived");
    expect(entered).toBe(false);
  } finally {
    connection?.end("1");
    await new Promise<void>((done) => gate.close(() => done()));
  }
  await running;
  expect(entered).toBe(true);
});

test("failed initialization preserves the primary error and closes its bound process", async ({
  playwright,
}, info) => {
  let pid = 0;
  let body = false;
  let startupFailed = false;
  let error: unknown;
  try {
    await withOwnedHttps(
      {
        app: "probe",
        playwright,
        outputDir: info.outputDir,
        env: { SYNTHETIC_HTTPS_FAIL_START: "1" },
        onEvent: (event) => {
          pid = event.pid;
          if (event.phase === "LIFESPAN_FAILED" && event.event === "lifespan.startup.failed")
            startupFailed = true;
        },
      },
      async () => {
        body = true;
      },
    );
  } catch (failure) {
    error = failure;
  }
  expect(error).toBeInstanceOf(HttpsLifecycleError);
  expect(String((error as HttpsLifecycleError).primary)).toContain("HTTPS_EXIT_BEFORE_READY");
  expect((error as HttpsLifecycleError).cleanup).toBeUndefined();
  expect(body).toBe(false);
  expect(startupFailed).toBe(true);
  expect(String((error as HttpsLifecycleError).primary)).toContain("PROBE_START_RED");
  expect(() => process.kill(pid, 0)).toThrow();
});

test("body and shutdown errors are both retained, never mistaken for GREEN", async ({
  playwright,
}, info) => {
  let error: unknown;
  try {
    await withOwnedHttps(
      {
        app: "probe",
        playwright,
        outputDir: info.outputDir,
        env: { SYNTHETIC_HTTPS_FAIL_STOP: "1" },
      },
      async () => {
        throw new Error("PRIMARY_BODY_RED");
      },
    );
  } catch (failure) {
    error = failure;
  }
  expect(error).toBeInstanceOf(HttpsLifecycleError);
  expect(String((error as HttpsLifecycleError).primary)).toContain("PRIMARY_BODY_RED");
  expect((error as HttpsLifecycleError).cleanup).toBeDefined();
  expect((error as HttpsLifecycleError).errors).toHaveLength(2);
});

test("cleanup failure after a successful body is a real failure", async ({ playwright }, info) => {
  await expect(
    withOwnedHttps(
      {
        app: "probe",
        playwright,
        outputDir: info.outputDir,
        env: { SYNTHETIC_HTTPS_FAIL_STOP: "1" },
      },
      async () => {},
    ),
  ).rejects.toThrow("HTTPS primary=none cleanup=");
});

test("startup cancellation waits for its own cleanup and preserves cancellation", async ({
  playwright,
}, info) => {
  const controller = new AbortController();
  let pid = 0;
  await expect(
    withOwnedHttps(
      {
        app: "probe",
        playwright,
        outputDir: info.outputDir,
        signal: controller.signal,
        onEvent: (event) => {
          pid = event.pid;
          if (event.phase === "LIFESPAN_START") controller.abort();
        },
      },
      async () => {
        throw new Error("BODY_MUST_NOT_RUN");
      },
    ),
  ).rejects.toThrow("HTTPS_START_CANCELLED");
  expect(() => process.kill(pid, 0)).toThrow();
});

test("a stage deadline still fails rather than accepting a late result", async () => {
  let release!: () => void;
  const waiting = new Promise<void>((done) => {
    release = done;
  });
  try {
    await expect(bounded(waiting, 10, "negative-control")).rejects.toThrow(
      "HTTPS_STAGE_TIMEOUT:negative-control",
    );
  } finally {
    release();
  }
});
