import { test, expect } from "@playwright/test";
import { createServer, type Socket, type AddressInfo } from "node:net";
import { once } from "node:events";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import {
  withOwnedHttps,
  HttpsLifecycleError,
  bounded,
  httpsFixture,
  finalizeHttpsLifecycle,
} from "./support/https-fixture";

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

for (const failure of ["primary", "cleanup", "dispose-only"] as const) {
  test(`${failure} plus real context disposal failure retains every cause`, async ({
    playwright,
  }, info) => {
    // Delegate all HTTPS requests and disposal to the real Playwright context;
    // inject only a finalizer failure, never a business/authorization response.
    const original = new Error("DISPOSE_RED");
    let disposed = false;
    const instrumented = {
      request: {
        newContext: async (...args: Parameters<typeof playwright.request.newContext>) => {
          const api = await playwright.request.newContext(...args);
          const dispose = api.dispose.bind(api);
          api.dispose = async () => {
            await dispose();
            disposed = true;
            throw original;
          };
          return api;
        },
      },
    } as typeof playwright;
    let error: unknown;
    try {
      await withOwnedHttps(
        {
          app: "probe",
          playwright: instrumented,
          outputDir: info.outputDir,
          env: failure === "cleanup" ? { SYNTHETIC_HTTPS_FAIL_STOP: "1" } : {},
        },
        async () => {
          if (failure === "primary") throw new Error("PRIMARY_BODY_RED");
        },
      );
    } catch (caught) {
      error = caught;
    }
    expect(disposed).toBe(true);
    expect(error).toBeInstanceOf(HttpsLifecycleError);
    const combined = error as HttpsLifecycleError;
    expect(String(combined.cleanup)).toContain("DISPOSE_RED");
    if (failure === "primary") expect(String(combined.primary)).toContain("PRIMARY_BODY_RED");
    if (failure === "cleanup") {
      expect(String(combined.cleanup)).toContain("HTTPS");
      expect((combined.cleanup as AggregateError).errors.length).toBeGreaterThanOrEqual(2);
    }
    if (failure === "dispose-only") expect(combined.primary).toBeUndefined();
    if (failure !== "cleanup") expect((combined.cleanup as Error).cause).toBe(original);
    const receipts = readdirSync(info.outputDir).filter((path) => path.endsWith("-receipt.json"));
    expect(receipts).toHaveLength(1);
    const receipt = JSON.parse(readFileSync(resolve(info.outputDir, receipts[0]), "utf8"));
    expect(receipt.privateDirectoryRemoved).toBe(true);
    expect(existsSync(receipt.privateDirectory)).toBe(false);
  });
}

test("primary error survives real evidence I/O failures and private key removal", async ({
  playwright,
}, info) => {
  let error: unknown;
  try {
    await withOwnedHttps(
      {
        app: "probe",
        playwright,
        outputDir: info.outputDir,
        onEvent: (event) => {
          if (event.phase === "READY") {
            // Genuine EISDIR from both evidence writes, not a mocked fs success.
            mkdirSync(resolve(info.outputDir, `https-${event.nonce}-receipt.json`));
            mkdirSync(resolve(info.outputDir, `https-${event.nonce}-process.log`));
          }
        },
      },
      async () => {
        throw new Error("PRIMARY_EVIDENCE_RED");
      },
    );
  } catch (caught) {
    error = caught;
  }
  expect(error).toBeInstanceOf(HttpsLifecycleError);
  expect(String((error as HttpsLifecycleError).primary)).toContain("PRIMARY_EVIDENCE_RED");
  const cleanup = (error as HttpsLifecycleError).cleanup as AggregateError;
  expect(cleanup.errors).toHaveLength(2);
  expect(String(cleanup)).toContain("HTTPS_FINALIZATION:process-log");
  expect(String(cleanup)).toContain("HTTPS_FINALIZATION:receipt");
  expect(String(cleanup)).toContain("EISDIR");
});

test("every finalizer is attempted and retains its original failure object", async () => {
  const primary = new Error("PRIMARY_RED");
  const failures = [
    new Error("CLEANUP_RED"),
    new Error("DISPOSE_RED"),
    new Error("PRIVATE_DIR_RED"),
    new Error("EVIDENCE_RED"),
  ];
  const attempted: string[] = [];
  let error: unknown;
  try {
    await finalizeHttpsLifecycle(
      primary,
      [{ phase: "cleanup", error: failures[0] }],
      ["dispose", "private-directory", "evidence"].map((phase, index) => ({
        phase,
        run: () => {
          attempted.push(phase);
          throw failures[index + 1];
        },
      })),
    );
  } catch (caught) {
    error = caught;
  }
  expect(attempted).toEqual(["dispose", "private-directory", "evidence"]);
  expect(error).toBeInstanceOf(HttpsLifecycleError);
  expect((error as HttpsLifecycleError).primary).toBe(primary);
  expect(
    ((error as HttpsLifecycleError).cleanup as AggregateError).errors.map((e: Error) => e.cause),
  ).toEqual(failures);
});

test("owned certificate directory is removed without touching an unrelated private directory", async ({
  playwright,
}, info) => {
  const unrelated = mkdtempSync(resolve(tmpdir(), "SYNTHETIC-unrelated-private-"));
  const key = resolve(unrelated, "key.pem");
  writeFileSync(key, "SYNTHETIC_UNRELATED_NOT_A_REAL_KEY");
  try {
    await withOwnedHttps({ app: "probe", playwright, outputDir: info.outputDir }, async () => {});
    const receipts = readdirSync(info.outputDir).filter((path) => path.endsWith("-receipt.json"));
    expect(receipts).toHaveLength(1);
    const receipt = JSON.parse(readFileSync(resolve(info.outputDir, receipts[0]), "utf8"));
    expect(receipt.privateDirectoryRemoved).toBe(true);
    expect(receipt.privateDirectory).toContain("SYNTHETIC-owned-https-");
    expect(existsSync(receipt.privateDirectory)).toBe(false);
    expect(readFileSync(key, "utf8")).toBe("SYNTHETIC_UNRELATED_NOT_A_REAL_KEY");
  } finally {
    rmSync(unrelated, { recursive: true });
  }
});

test("S4 external HTTPS branch uses but never owns or disposes the managed service", async ({
  playwright,
}, info) => {
  let pid = 0;
  await withOwnedHttps(
    {
      app: "probe",
      playwright,
      outputDir: info.outputDir,
      onEvent: (event) => {
        pid = event.pid;
      },
    },
    async (url) => {
      const forbidden = {
        request: {
          newContext: async () => {
            throw new Error("EXTERNAL_MUST_NOT_CREATE_CONTEXT");
          },
        },
      } as unknown as typeof playwright;
      const externalOutput = resolve(info.outputDir, "MUST_NOT_BE_CREATED");
      const previousExternal = process.env.S4_HTTPS_URL;
      process.env.S4_HTTPS_URL = url;
      const fixture = httpsFixture("business_pg", () => process.env.S4_HTTPS_URL);
      try {
        await fixture[0](
          { playwright: forbidden },
          async (received) => {
            expect(received).toBe(url);
            const api = await playwright.request.newContext({ ignoreHTTPSErrors: true });
            try {
              expect((await api.get(received + "/__e2e_https_owner__")).status()).toBe(200);
            } finally {
              await api.dispose();
            }
          },
          { project: { ...info.project, outputDir: externalOutput } },
        );
        expect(existsSync(externalOutput)).toBe(false);
        expect(() => process.kill(pid, 0)).not.toThrow();
        await expect(
          fixture[0](
            { playwright: forbidden },
            async () => {
              throw new Error("EXTERNAL_BODY_RED");
            },
            { project: info.project },
          ),
        ).rejects.toThrow("EXTERNAL_BODY_RED");
        expect(() => process.kill(pid, 0)).not.toThrow();
      } finally {
        if (previousExternal === undefined) delete process.env.S4_HTTPS_URL;
        else process.env.S4_HTTPS_URL = previousExternal;
      }
    },
  );
  expect(() => process.kill(pid, 0)).toThrow();
});
