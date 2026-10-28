import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { OwnedServerJournal, errorDetails, type FixturePhase } from "./owned-server-diagnostics";

export type BoundServer = Readonly<{ pid: number; port: number; nonce: string; url: string }>;
type Cleanup = Readonly<{
  pid: number | null;
  port: number | null;
  closed: true;
  forced: boolean;
  sigtermSent: boolean;
  exitCode: number | null;
  exitSignal: NodeJS.Signals | null;
}>;
export type OwnedServer = BoundServer & {
  bound: BoundServer;
  diagnosticPath: string;
  diagnostics(): ReturnType<OwnedServerJournal["snapshot"]> & {
    closed: boolean;
    exitCode: number | null;
    exitSignal: NodeJS.Signals | null;
  };
  mark(phase: FixturePhase): void;
  recordFailure(stage: "WORKER" | "API_DISPOSE" | "SERVER_STOP", error: unknown): void;
  traceRequest<T>(
    phase: FixturePhase,
    action: (headers: Record<string, string>) => Promise<T>,
  ): Promise<T>;
  assertRunning(): void;
  stop(): Promise<Cleanup>;
};
export class OwnedServerStartError extends Error {
  constructor(
    message: string,
    readonly bound: BoundServer | undefined,
    readonly cleanup: Cleanup,
  ) {
    super(message);
  }
}

async function within<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("OWNED_SERVER_DEADLINE")), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

export async function startOwnedServer(
  app: string,
  options: {
    env?: NodeJS.ProcessEnv;
    signal?: AbortSignal;
    onBound?: (bound: BoundServer) => void;
  } = {},
): Promise<OwnedServer> {
  const nonce = randomUUID();
  const journal = new OwnedServerJournal(nonce);
  const child = spawn(
    process.env.DASHBOARD_TEST_PYTHON ?? "python3",
    ["-m", "frontend.e2e.support.owned_server", "--app", app, "--nonce", nonce],
    {
      cwd: resolve(process.cwd(), ".."),
      env: { ...process.env, ...options.env, PYTHONPATH: "." },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  journal.childPid = child.pid ?? null;
  journal.record("SPAWN");
  let bound: BoundServer | undefined;
  let didClose = false;
  let exitCode: number | null = null;
  let exitSignal: NodeJS.Signals | null = null;
  let protocolFailure: unknown;
  child.once("exit", (code, signal) => {
    exitCode = code;
    exitSignal = signal;
    journal.record("CHILD_EXIT", { exit_code: code, exit_signal: signal });
  });
  const closed = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>((done) => {
    child.once("close", (code, signal) => {
      didClose = true;
      journal.record("CHILD_CLOSE", {
        exit_code: code,
        exit_signal: signal,
        stderr: journal.stderrSummary(),
      });
      done({ code, signal });
    });
  });
  let stopPromise: Promise<Cleanup> | undefined;
  const stopChild = () =>
    (stopPromise ??= (async () => {
      journal.record("STOP_BEGIN", { already_closed: didClose });
      // Captured ChildProcess identity only: never search/kill by port or name.
      const sigtermSent =
        !didClose && child.pid !== undefined && child.exitCode === null && child.signalCode === null
          ? child.kill("SIGTERM")
          : false;
      journal.record("SIGNAL_SENT", { signal: "SIGTERM", sent: sigtermSent });
      let forced = false;
      let result;
      try {
        result = await within(closed, 10000);
      } catch {
        forced = true;
        journal.record("FORCED_CLEANUP", { signal: "SIGKILL" });
        if (!didClose && child.exitCode === null && child.signalCode === null)
          child.kill("SIGKILL");
        result = await within(closed, 5000);
      }
      const receipt = {
        pid: child.pid ?? null,
        port: bound?.port ?? null,
        closed: true as const,
        forced,
        sigtermSent,
        exitCode: result.code,
        exitSignal: result.signal,
      };
      journal.record("CLEANUP_COMPLETE", { ...receipt, stderr: journal.stderrSummary() });
      return receipt;
    })());

  let abort: (() => void) | undefined;
  try {
    const ready = new Promise<void>((done, fail) => {
      let pending = "";
      child.stderr.on("data", (data: Buffer) => journal.stderr(data));
      child.stdout.on("data", (data: Buffer) => {
        pending += data.toString();
        let newline: number;
        while ((newline = pending.indexOf("\n")) !== -1) {
          const line = pending.slice(0, newline);
          pending = pending.slice(newline + 1);
          if (!line.startsWith("SYNTHETIC_OWNED_SERVER ")) continue;
          try {
            const value = JSON.parse(line.slice("SYNTHETIC_OWNED_SERVER ".length));
            if (
              value.SYNTHETIC !== true ||
              value.pid !== child.pid ||
              value.nonce !== nonce ||
              !Number.isInteger(value.port) ||
              value.port <= 0 ||
              value.port > 65535
            )
              throw new Error("OWNED_SERVER_IDENTITY_MISMATCH");
            const observed = {
              pid: value.pid,
              port: value.port,
              nonce,
              url: `http://127.0.0.1:${value.port}`,
            };
            if (value.phase === "BOUND" && !bound) {
              bound = observed;
              journal.port = value.port;
              journal.record("BOUND");
              options.onBound?.(bound);
            } else if (value.phase === "READY" && bound?.port === value.port) {
              journal.record("READY");
              journal.assertWritable();
              done();
            } else if (
              bound?.port === value.port &&
              [
                "ASGI_REQUEST_BEGIN",
                "ASGI_REQUEST_END",
                "ASGI_DISCONNECT",
                "ASGI_ERROR",
                "LIFESPAN_STARTUP_BEGIN",
                "LIFESPAN_STARTUP_COMPLETE",
                "LIFESPAN_STARTUP_FAILED",
                "LIFESPAN_SHUTDOWN_BEGIN",
                "LIFESPAN_SHUTDOWN_COMPLETE",
                "LIFESPAN_SHUTDOWN_FAILED",
                "SIGNAL_RECEIVED",
                "SERVER_SHUTDOWN_BEGIN",
                "SERVER_SHUTDOWN_END",
                "PROCESS_MAIN_RETURN",
              ].includes(value.phase)
            ) {
              // Whitelist metadata; never persist arbitrary child JSON fields.
              journal.record(value.phase, {
                request_id:
                  typeof value.request_id === "string" && /^[a-f0-9-]{36}$/.test(value.request_id)
                    ? value.request_id
                    : null,
                request_kind: ["AUTHORITY", "OWNERSHIP", "PROBE_HELD", "BUSINESS_HTTP"].includes(
                  value.request_kind,
                )
                  ? value.request_kind
                  : null,
                method: ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].includes(
                  value.method,
                )
                  ? value.method
                  : null,
                status:
                  Number.isInteger(value.status) && value.status >= 100 && value.status <= 599
                    ? value.status
                    : null,
                error_type:
                  typeof value.error_type === "string" &&
                  /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(value.error_type)
                    ? value.error_type
                    : null,
                emitted_at_utc:
                  typeof value.emitted_at_utc === "string" &&
                  /^\d{4}-\d{2}-\d{2}T[0-9:.+Z-]+$/.test(value.emitted_at_utc)
                    ? value.emitted_at_utc
                    : null,
                signal: ["SIGTERM", "SIGINT"].includes(value.signal) ? value.signal : null,
              });
            } else throw new Error("OWNED_SERVER_PHASE_MISMATCH");
          } catch (error) {
            protocolFailure = error;
            journal.record("PROTOCOL_ERROR", errorDetails(error));
            fail(error);
          }
        }
      });
      child.once("error", fail);
      void closed.then(() => fail(new Error("OWNED_SERVER_EXITED_BEFORE_READY")));
      abort = () => fail(new Error("OWNED_SERVER_START_CANCELLED"));
      options.signal?.addEventListener("abort", abort, { once: true });
      if (options.signal?.aborted) abort();
    });
    await within(ready, 30000);
    if (!bound) throw new Error("OWNED_SERVER_MISSING_BOUND_ADDRESS");
    const response = await fetch(bound.url + "/__e2e_owned_server__", {
      headers: { Connection: "close" },
      signal: options.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(10000)])
        : AbortSignal.timeout(10000),
    });
    const owner = await response.json();
    if (
      response.status !== 200 ||
      owner.SYNTHETIC !== true ||
      owner.pid !== child.pid ||
      owner.nonce !== nonce ||
      owner.port !== bound.port ||
      didClose
    )
      throw new Error("OWNED_SERVER_LIVE_IDENTITY_MISMATCH");
    return {
      ...bound,
      bound,
      diagnosticPath: journal.filePath,
      diagnostics: () => ({ ...journal.snapshot(), closed: didClose, exitCode, exitSignal }),
      mark: (phase) => journal.record("FIXTURE_PHASE", { phase }),
      recordFailure: (stage, error) =>
        journal.record("FIXTURE_ERROR", { stage, ...errorDetails(error) }),
      traceRequest: async (phase, action) => {
        const requestId = randomUUID();
        journal.record("CLIENT_REQUEST_BEGIN", { phase, request_id: requestId });
        try {
          const value = await action({ "x-e2e-owned-request": requestId });
          journal.record("CLIENT_REQUEST_END", { phase, request_id: requestId });
          return value;
        } catch (error) {
          journal.record("CLIENT_REQUEST_ERROR", {
            phase,
            request_id: requestId,
            ...errorDetails(error),
          });
          throw error;
        }
      },
      assertRunning: () => {
        journal.assertWritable();
        if (protocolFailure) throw protocolFailure;
        if (didClose || child.exitCode !== null || child.signalCode !== null)
          throw new Error(`OWNED_SERVER_EXITED: ${journal.stderrSummary().safe_tail}`);
      },
      stop: async () => {
        const receipt = await stopChild();
        journal.assertWritable();
        if (protocolFailure) throw protocolFailure;
        if (receipt.forced || (receipt.exitCode !== 0 && receipt.exitSignal !== "SIGTERM"))
          throw new Error(`OWNED_SERVER_UNCLEAN_EXIT: ${journal.stderrSummary().safe_tail}`);
        return receipt;
      },
    };
  } catch (error) {
    journal.record("START_ERROR", errorDetails(error));
    const cleanup = await stopChild();
    const code =
      error instanceof Error ? error.message.match(/\bOWNED_SERVER_[A-Z_]+\b/)?.[0] : undefined;
    throw new OwnedServerStartError(
      `${code ?? "OWNED_SERVER_START_FAILED"}\n${journal.stderrSummary().safe_tail}`,
      bound,
      cleanup,
    );
  } finally {
    if (abort) options.signal?.removeEventListener("abort", abort);
  }
}
