import { createHash } from "node:crypto";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

export type FixturePhase =
  | "AUTHORITY_READINESS"
  | "AUTHORITY_STATE"
  | "AUTHORITY_AUDIT"
  | "WORKER_USE_BEGIN"
  | "WORKER_USE_END"
  | "PAGE_USE_BEGIN"
  | "PAGE_UNROUTE_BEGIN"
  | "PAGE_UNROUTE_END"
  | "API_DISPOSE_BEGIN"
  | "API_DISPOSE_END"
  | "FIXTURE_END";

export type OwnedEvent = {
  seq: number;
  event: string;
  at_utc: string;
  elapsed_ms: number;
  worker_pid: number;
  child_pid: number | null;
  nonce: string;
  port: number | null;
  [key: string]: unknown;
};

export function errorDetails(error: unknown) {
  const name = error instanceof Error ? error.name : "NonError";
  const message = error instanceof Error ? error.message : "";
  const transport = /socket hang up/i.test(message)
    ? "SOCKET_HANG_UP"
    : /ECONNRESET/.test(message)
      ? "ECONNRESET"
      : /ECONNREFUSED/.test(message)
        ? "ECONNREFUSED"
        : /abort/i.test(name + message)
          ? "ABORTED"
          : /timeout|deadline/i.test(name + message)
            ? "TIMEOUT"
            : "UNCLASSIFIED";
  // Never persist exception messages, request URLs, headers or response bodies.
  return {
    error_type: /^[A-Za-z][A-Za-z0-9_.]{0,63}$/.test(name) ? name : "RedactedError",
    transport_error: transport,
  };
}

export class OwnedServerJournal {
  readonly filePath: string;
  private readonly started = performance.now();
  private readonly stderrHash = createHash("sha256");
  private stderrTail = Buffer.alloc(0);
  private stderrBytes = 0;
  private sequence = 0;
  private readonly recent: OwnedEvent[] = [];
  private ioFailed = false;
  private dropped = 0;
  childPid: number | null = null;
  port: number | null = null;

  constructor(readonly nonce: string) {
    const directory = resolve(process.cwd(), "test-results", "owned-server-diagnostics");
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    this.filePath = resolve(directory, `${process.pid}-${nonce}.jsonl`);
    // A new nonce owns one journal; never replace another run's diagnostics.
    writeFileSync(this.filePath, "", { flag: "wx", mode: 0o600 });
  }

  stderr(data: Buffer) {
    this.stderrBytes += data.length;
    this.stderrHash.update(data);
    this.stderrTail = Buffer.concat([this.stderrTail, data]).subarray(-8192);
  }

  stderrSummary() {
    const safe = this.stderrTail
      .toString("utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(-32)
      .map((line) => {
        const lifecycle = line.match(
          /^(?:INFO:\s+)?(Started server process \[\d+\]|Finished server process \[\d+\]|Waiting for application startup\.|Application startup complete\.|Shutting down|Waiting for application shutdown\.|Application shutdown complete\.)\s*$/,
        );
        if (lifecycle) return lifecycle[1];
        const frame = line.match(
          /^\s*File "[^"]*\/(frontend\/e2e\/support\/[a-zA-Z0-9_.-]+\.py|backend\/(?:app|tests)\/[a-zA-Z0-9_/.-]+\.py)", line (\d+), in ([a-zA-Z0-9_<>]+)\s*$/,
        );
        if (frame) return `CODE_FRAME ${frame[1]}:${frame[2]} ${frame[3]}`;
        if (/^(?:ERROR:\s+)?SYNTHETIC_STARTUP_FAILURE\s*$/.test(line))
          return "SYNTHETIC_STARTUP_FAILURE";
        return `REDACTED_STDERR_LINE sha256=${createHash("sha256").update(line).digest("hex")}`;
      });
    return {
      bytes: this.stderrBytes,
      sha256: this.stderrHash.copy().digest("hex"),
      safe_tail: safe.join("\n").slice(-4096),
    };
  }

  record(event: string, data: Record<string, unknown> = {}) {
    // Bound high-volume ASGI records while always retaining lifecycle/failure records.
    if (this.sequence >= 4096 && event.startsWith("ASGI_")) {
      this.dropped += 1;
      return;
    }
    const entry: OwnedEvent = {
      ...data,
      seq: ++this.sequence,
      event,
      at_utc: new Date().toISOString(),
      elapsed_ms: Math.round((performance.now() - this.started) * 1000) / 1000,
      worker_pid: process.pid,
      child_pid: this.childPid,
      nonce: this.nonce,
      port: this.port,
    };
    this.recent.push(entry);
    if (this.recent.length > 256) this.recent.shift();
    try {
      appendFileSync(this.filePath, JSON.stringify(entry) + "\n", { mode: 0o600 });
    } catch {
      // Event handlers must not strand the child. stop()/assertRunning fail visibly.
      this.ioFailed = true;
    }
  }

  assertWritable() {
    if (this.ioFailed) throw new Error("OWNED_SERVER_DIAGNOSTIC_WRITE_FAILED");
  }

  snapshot() {
    return {
      worker_pid: process.pid,
      child_pid: this.childPid,
      nonce: this.nonce,
      port: this.port,
      stderr: this.stderrSummary(),
      dropped_asgi_events: this.dropped,
      events: [...this.recent],
    };
  }
}
