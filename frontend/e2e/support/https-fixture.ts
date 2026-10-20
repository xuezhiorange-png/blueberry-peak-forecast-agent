import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtempSync, mkdirSync, appendFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { connect } from "node:net";
import { performance } from "node:perf_hooks";
import { expect, type PlaywrightWorkerArgs, type WorkerInfo } from "@playwright/test";

type Playwright = PlaywrightWorkerArgs["playwright"];

// Independent worker initialization (<=150s) + finalization (<=75s), not a
// change to any test body/global timeout. All stage deadlines remain finite.
export const HTTPS_WORKER_TIMEOUT = 240_000;
const SETUP_TOTAL = 150_000;
type App = "business_pg" | "acceptance_s6_pg" | "probe";
type Receipt = Record<string, unknown> & {
  phase: string;
  pid: number;
  nonce: string;
  port: number;
};
type Options = {
  app: App;
  playwright: Playwright;
  outputDir: string;
  env?: NodeJS.ProcessEnv;
  signal?: AbortSignal;
  onEvent?: (event: Receipt) => void;
  readyTimeout?: number;
};
export class HttpsLifecycleError extends AggregateError {
  constructor(
    readonly primary: unknown,
    readonly cleanup: unknown,
  ) {
    super(
      [primary, cleanup].filter(Boolean),
      `HTTPS primary=${String(primary ?? "none")} cleanup=${String(cleanup ?? "none")}`,
    );
  }
}

export async function bounded<T>(
  operation: Promise<T>,
  timeout: number,
  phase: string,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`HTTPS_STAGE_TIMEOUT:${phase}`)), timeout);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function closedPort(port: number) {
  return bounded(
    new Promise<void>((done, fail) => {
      const socket = connect({ host: "127.0.0.1", port });
      socket.once("connect", () => {
        socket.destroy();
        fail(new Error("HTTPS_OWNED_PORT_STILL_OPEN"));
      });
      socket.once("error", (error: NodeJS.ErrnoException) => {
        if (error.code === "ECONNREFUSED") done();
        else fail(error);
      });
      socket.setTimeout(2000, () => {
        socket.destroy();
        fail(new Error("HTTPS_PORT_STATE_UNKNOWN"));
      });
    }),
    3000,
    "port-closed",
  );
}

async function command(args: string[], cwd: string, timeout: number, phase: string) {
  const child = spawn(args[0], args.slice(1), { cwd, stdio: "pipe" });
  // These commands write key material to a private file, never stdout. Retain
  // bounded diagnostics on failure so compiler/certificate errors aren't lost.
  let output = "";
  const drain = (data: Buffer) => {
    output = (output + data.toString()).slice(-32768);
  };
  child.stdout.on("data", drain);
  child.stderr.on("data", drain);
  const closed = new Promise<number | null>((done, fail) => {
    child.once("error", fail);
    child.once("close", done);
  });
  try {
    const code = await bounded(closed, timeout, phase);
    if (code !== 0) throw new Error(`HTTPS_COMMAND_FAILED:${phase}:exit=${code}\n${output}`);
  } catch (primary) {
    child.kill("SIGTERM");
    try {
      await bounded(closed, 5000, `${phase}-terminate`);
    } catch {
      child.kill("SIGKILL");
      await bounded(closed, 5000, `${phase}-kill`);
    }
    throw primary;
  }
}

let build: Promise<void> | undefined;

export async function withOwnedHttps<T>(
  options: Options,
  body: (url: string) => Promise<T>,
): Promise<T> {
  const start = performance.now();
  const nonce = randomUUID();
  const directory = mkdtempSync(resolve(tmpdir(), "SYNTHETIC-owned-https-"));
  mkdirSync(options.outputDir, { recursive: true });
  const evidence = resolve(options.outputDir, `https-${nonce}`);
  const stage = async <V>(name: string, limit: number, run: () => Promise<V>, setup = true) => {
    const begin = performance.now();
    let status = "PASS";
    try {
      const budget = setup ? Math.min(limit, SETUP_TOTAL - (begin - start)) : limit;
      if (budget <= 0) throw new Error("HTTPS_SETUP_TOTAL_EXHAUSTED");
      return Number.isFinite(budget) ? await bounded(run(), budget, name) : await run();
    } catch (error) {
      status = "FAIL";
      throw error;
    } finally {
      const receipt = { phase: name, status, elapsed_ms: Math.round(performance.now() - begin) };
      appendFileSync(evidence + "-timing.jsonl", JSON.stringify(receipt) + "\n");
      console.log("SYNTHETIC_HTTPS_STAGE " + JSON.stringify(receipt));
    }
  };
  let child: ChildProcess | undefined;
  let closed: Promise<void> | undefined;
  let owner: Receipt | undefined;
  let ready = false;
  let lifespanAcquired = false;
  let exited = false;
  let logs = "";
  let cleanupReceipt: Receipt | undefined;
  let socketClosed = false;
  let primary: unknown;
  let cleanupError: unknown;
  let value: T | undefined;
  const api = await options.playwright.request.newContext({ ignoreHTTPSErrors: true });
  try {
    await stage("certificate", 15_000, () =>
      command(
        [
          "openssl",
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
        process.cwd(),
        14_000,
        "certificate",
      ),
    );
    if (options.app !== "probe") {
      await stage(
        "build",
        65_000,
        () => (build ??= command(["npm", "run", "build"], process.cwd(), 60_000, "build")),
      );
    }
    await stage("spawn-bind-ready", 75_000, async () => {
      let boundDone!: () => void;
      let boundFailed!: (error: unknown) => void;
      const binding = new Promise<void>((done, fail) => {
        boundDone = done;
        boundFailed = fail;
      });
      child = spawn(
        process.env.DASHBOARD_TEST_PYTHON ?? "python3",
        [
          "-m",
          "frontend.e2e.support.https_owned_server",
          "--app",
          options.app,
          "--nonce",
          nonce,
          "--key",
          directory + "/key.pem",
          "--cert",
          directory + "/cert.pem",
        ],
        {
          cwd: resolve(process.cwd(), ".."),
          env: { ...process.env, ...options.env, PYTHONPATH: ".", S4_SYNTHETIC_ONLY: "1" },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      closed = new Promise<void>((done) =>
        child!.once("close", () => {
          exited = true;
          done();
        }),
      );
      let pending = "";
      const waiting = new Promise<void>((done, fail) => {
        child!.once("error", (error) => {
          boundFailed(error);
          fail(error);
        });
        const drain = (data: Buffer) => {
          logs = (logs + data.toString()).slice(-65536);
        };
        child!.stderr!.on("data", drain);
        child!.stdout!.on("data", (data: Buffer) => {
          drain(data);
          pending += data.toString();
          let newline: number;
          while ((newline = pending.indexOf("\n")) >= 0) {
            const line = pending.slice(0, newline);
            pending = pending.slice(newline + 1);
            if (!line.startsWith("SYNTHETIC_HTTPS_LIFECYCLE ")) continue;
            try {
              const event = JSON.parse(line.slice("SYNTHETIC_HTTPS_LIFECYCLE ".length)) as Receipt;
              if (
                event.pid !== child!.pid ||
                event.nonce !== nonce ||
                !Number.isInteger(event.port) ||
                event.port < 1
              )
                throw new Error("HTTPS_CHILD_IDENTITY_MISMATCH");
              appendFileSync(
                evidence + "-lifecycle.jsonl",
                JSON.stringify({ ...event, elapsed_ms: Math.round(performance.now() - start) }) +
                  "\n",
              );
              if (event.phase === "BOUND") {
                owner = event;
                boundDone();
              }
              if (event.phase === "LIFESPAN_READY") lifespanAcquired = true;
              if (event.phase === "READY") done();
              if (event.phase === "CLEANUP_VERIFIED") cleanupReceipt = event;
              if (event.phase === "SOCKET_CLOSED") socketClosed = true;
              options.onEvent?.(event);
            } catch (error) {
              boundFailed(error);
              fail(error);
            }
          }
        });
        void closed!.then(() => {
          const error = new Error(`HTTPS_EXIT_BEFORE_READY:${logs}`);
          boundFailed(error);
          fail(error);
        });
      });
      const cancelled = new Promise<never>((_, reject) => {
        const abort = () => reject(new Error("HTTPS_START_CANCELLED"));
        options.signal?.addEventListener("abort", abort, { once: true });
        if (options.signal?.aborted) abort();
        void waiting
          .finally(() => options.signal?.removeEventListener("abort", abort))
          .catch(() => {});
      });
      // Both promises acquire rejection handlers immediately, including when
      // startup fails before the bound/ready stage can be awaited.
      void waiting.catch(() => {});
      await stage("spawn-and-bind", 10_000, () => Promise.race([binding, cancelled]));
      await stage("service-ready", options.readyTimeout ?? 60_000, () =>
        bounded(
          Promise.race([waiting, cancelled]),
          options.readyTimeout ?? 60_000,
          "service-ready",
        ),
      );
      if (!owner || exited) throw new Error("HTTPS_OWNER_MISSING_OR_EXITED");
      const url = `https://127.0.0.1:${owner.port}`;
      expect(
        await (await api.get(url + "/__e2e_https_owner__", { timeout: 3000 })).json(),
      ).toMatchObject(ownerFields(owner));
      if (options.app !== "probe")
        expect((await api.get(url + "/__s4_test__/ready", { timeout: 3000 })).status()).toBe(200);
      ready = true;
    });
    await stage(
      "test-execution-and-business-audit",
      Infinity,
      async () => {
        const url = `https://127.0.0.1:${owner!.port}`;
        value = await body(url);
        if (options.app !== "probe")
          expect(
            (await (await api.get(url + "/__s4_test__/ready")).json()).post_seed_business_dml_count,
          ).toBe(0);
      },
      false,
    );
  } catch (error) {
    primary = error;
  }
  try {
    await stage(
      "cleanup",
      80_000,
      async () => {
        if (child && closed) {
          if (!exited) child.kill("SIGTERM");
          try {
            await bounded(closed, 75_000, "graceful-process-close");
          } catch (error) {
            if (!exited) child.kill("SIGKILL");
            await bounded(closed, 3000, "forced-process-close");
            throw error; // Forced exit is cleanup failure, never success.
          }
          if (owner) await closedPort(owner.port);
          if (ready || lifespanAcquired) {
            expect(child.exitCode).toBe(0);
            expect(socketClosed).toBe(true);
            expect(cleanupReceipt).toBeDefined();
            if (options.app !== "probe") {
              expect(cleanupReceipt!.postgres).toBe("ABSENT_VERIFIED");
              if (options.app === "business_pg") {
                expect(logs).toContain("Application shutdown complete.");
              } else {
                // Nested MCP config deliberately uses warning-level Uvicorn
                // logs; S6's original marker is independent of logger verbosity.
                expect(cleanupReceipt!.tls_mcp).toBe("CLOSED_VERIFIED");
                expect(logs).toContain("S6_HARNESS_CLEANUP_COMPLETE");
              }
            }
          }
        }
      },
      false,
    );
  } catch (error) {
    cleanupError = error;
  } finally {
    await api.dispose();
    writeFileSync(
      evidence + "-receipt.json",
      JSON.stringify(
        {
          SYNTHETIC: true,
          app: options.app,
          pid: child?.pid,
          port: owner?.port,
          ready,
          exited,
          socketClosed,
          cleanup: cleanupReceipt,
          primary: primary ? String(primary) : null,
          cleanupError: cleanupError ? String(cleanupError) : null,
        },
        null,
        2,
      ) + "\n",
    );
    // Only test-owned child logs; no cookies, CSRF tokens, passwords or key bytes.
    writeFileSync(evidence + "-process.log", logs);
  }
  if (primary || cleanupError) throw new HttpsLifecycleError(primary, cleanupError);
  return value as T;
}

function ownerFields(owner: Receipt) {
  return { SYNTHETIC: true, pid: owner.pid, nonce: owner.nonce, port: owner.port };
}

export function httpsFixture(
  app: Exclude<App, "probe">,
): [
  (
    args: { playwright: Playwright },
    use: (url: string) => Promise<void>,
    worker: WorkerInfo,
  ) => Promise<void>,
  { scope: "worker"; timeout: number },
] {
  return [
    async (
      { playwright }: { playwright: Playwright },
      use: (url: string) => Promise<void>,
      worker: WorkerInfo,
    ) => {
      await withOwnedHttps({ app, playwright, outputDir: worker.project.outputDir }, use);
    },
    { scope: "worker" as const, timeout: HTTPS_WORKER_TIMEOUT },
  ];
}
