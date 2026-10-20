import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";

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
  const child = spawn(
    process.env.DASHBOARD_TEST_PYTHON ?? "python3",
    ["-m", "frontend.e2e.support.owned_server", "--app", app, "--nonce", nonce],
    {
      cwd: resolve(process.cwd(), ".."),
      env: { ...process.env, ...options.env, PYTHONPATH: "." },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let bound: BoundServer | undefined;
  let logs = "";
  let didClose = false;
  const closed = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>((done) => {
    child.once("close", (code, signal) => {
      didClose = true;
      done({ code, signal });
    });
  });
  let stopPromise: Promise<Cleanup> | undefined;
  const stopChild = () =>
    (stopPromise ??= (async () => {
      // Captured ChildProcess identity only: never search/kill by port or name.
      const sigtermSent =
        !didClose && child.pid !== undefined && child.exitCode === null && child.signalCode === null
          ? child.kill("SIGTERM")
          : false;
      let forced = false;
      let result;
      try {
        result = await within(closed, 10000);
      } catch {
        forced = true;
        if (!didClose && child.exitCode === null && child.signalCode === null)
          child.kill("SIGKILL");
        result = await within(closed, 5000);
      }
      return {
        pid: child.pid ?? null,
        port: bound?.port ?? null,
        closed: true as const,
        forced,
        sigtermSent,
        exitCode: result.code,
        exitSignal: result.signal,
      };
    })());

  let abort: (() => void) | undefined;
  try {
    const ready = new Promise<void>((done, fail) => {
      let pending = "";
      const drain = (data: Buffer) => {
        logs = (logs + data.toString()).slice(-32768);
      };
      child.stderr.on("data", drain);
      child.stdout.on("data", (data: Buffer) => {
        drain(data);
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
              options.onBound?.(bound);
            } else if (value.phase === "READY" && bound?.port === value.port) done();
            else throw new Error("OWNED_SERVER_PHASE_MISMATCH");
          } catch (error) {
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
      assertRunning: () => {
        if (didClose || child.exitCode !== null || child.signalCode !== null)
          throw new Error(`OWNED_SERVER_EXITED: ${logs}`);
      },
      stop: async () => {
        const receipt = await stopChild();
        if (receipt.forced || (receipt.exitCode !== 0 && receipt.exitSignal !== "SIGTERM"))
          throw new Error(`OWNED_SERVER_UNCLEAN_EXIT: ${logs}`);
        return receipt;
      },
    };
  } catch (error) {
    const cleanup = await stopChild();
    throw new OwnedServerStartError(`${String(error)}\n${logs}`, bound, cleanup);
  } finally {
    if (abort) options.signal?.removeEventListener("abort", abort);
  }
}
