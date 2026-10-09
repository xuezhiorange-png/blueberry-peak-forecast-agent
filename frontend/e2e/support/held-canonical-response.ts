import { once } from "node:events";
import { createServer } from "node:http";

// Test-only transport gate: hold REAL canonical GET JSON from synthetic SQLite.
// No fabricated business JSON and no delayed Playwright Route.fulfill.
export async function startHeldCanonicalGet(authorityUrl: string) {
  let signalStarted!: () => void;
  let signalFinished!: () => void;
  let release!: () => void;
  const started = new Promise<void>((resolve) => {
    signalStarted = resolve;
  });
  const finished = new Promise<void>((resolve) => {
    signalFinished = resolve;
  });
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const errors: unknown[] = [];
  const server = createServer((request, response) => {
    void (async () => {
      const path = request.url;
      if (request.method !== "GET" || !path?.startsWith("/api/v1/forecast-intelligence/curve?"))
        throw new Error("Only canonical GET curve requests may enter the held transport gate");
      const upstream = await fetch(authorityUrl + path);
      if (upstream.status !== 200)
        throw new Error(`Canonical upstream returned ${upstream.status}`);
      const body = await upstream.text();
      signalStarted();
      await held;
      response.writeHead(upstream.status, {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      });
      response.end(body);
      signalFinished();
    })().catch((error) => {
      errors.push(error);
      response.destroy();
      signalStarted();
      signalFinished();
    });
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Missing held transport gate port");
  return {
    url: `http://127.0.0.1:${address.port}`,
    started,
    finished,
    release,
    errors,
    close: async () => {
      release();
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      );
    },
  };
}
