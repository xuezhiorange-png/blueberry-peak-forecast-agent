import { test, expect } from "@playwright/test";
import { createServer } from "node:net";
import { once } from "node:events";
import {
  startOwnedServer,
  OwnedServerStartError,
  type BoundServer,
  type OwnedServer,
} from "./support/owned-server";

const probe = "frontend.e2e.support.owned_server:probe_app";

async function assertReleased(bound: BoundServer) {
  expect(() => process.kill(bound.pid, 0)).toThrow();
  await expect(fetch(bound.url + "/__e2e_owned_server__")).rejects.toThrow();
}

test("OS-bound concurrent listeners are distinct and cleanup leaves unrelated resources alive", async () => {
  const unrelated = createServer((socket) => socket.end("SYNTHETIC_UNRELATED"));
  unrelated.listen(0, "127.0.0.1");
  await once(unrelated, "listening");
  const servers: OwnedServer[] = [];
  try {
    // Each socket remains bound from allocation through Uvicorn shutdown.
    for (let i = 0; i < 4; i++) servers.push(await startOwnedServer(probe));
    expect(new Set(servers.map((s) => s.port)).size).toBe(4);
    await servers[0].stop();
    await assertReleased(servers[0]);
    for (const server of servers.slice(1)) {
      const owner = await (await fetch(server.url + "/__e2e_owned_server__")).json();
      expect(owner).toEqual({
        SYNTHETIC: true,
        pid: server.pid,
        nonce: server.nonce,
        port: server.port,
      });
    }
    expect(unrelated.listening).toBe(true);
  } finally {
    await Promise.all(servers.map((s) => s.stop()));
    await new Promise<void>((resolve, reject) =>
      unrelated.close((e) => (e ? reject(e) : resolve())),
    );
  }
});

test("normal SIGTERM cleanup waits for close and is idempotent", async ({}, info) => {
  const server = await startOwnedServer(probe);
  const receipt = await server.stop();
  expect(receipt.closed).toBe(true);
  expect(receipt.forced).toBe(false);
  expect(receipt.sigtermSent).toBe(true);
  expect(await server.stop()).toEqual(receipt);
  await assertReleased(server);
  await info.attach("SYNTHETIC-owned-cleanup.json", {
    body: JSON.stringify({ ...server.bound, ...receipt }),
    contentType: "application/json",
  });
});

test("startup failure after binding reclaims the owned process and socket", async () => {
  let failure: unknown;
  try {
    await startOwnedServer(probe, { env: { SYNTHETIC_FIXTURE_FAIL_STARTUP: "1" } });
  } catch (error) {
    failure = error;
  }
  expect(failure).toBeInstanceOf(OwnedServerStartError);
  const error = failure as OwnedServerStartError;
  expect(error.message).toContain("SYNTHETIC_STARTUP_FAILURE");
  expect(error.cleanup.closed).toBe(true);
  expect(error.bound).toBeDefined();
  await assertReleased(error.bound!);
});

test("cancellation immediately after binding cannot strand a starting process", async () => {
  const controller = new AbortController();
  let bound: BoundServer | undefined;
  let failure: unknown;
  try {
    await startOwnedServer(probe, {
      signal: controller.signal,
      onBound: (value) => {
        bound = value;
        controller.abort();
      },
    });
  } catch (error) {
    failure = error;
  }
  expect(failure).toBeInstanceOf(OwnedServerStartError);
  expect(bound).toBeDefined();
  expect((failure as OwnedServerStartError).cleanup.closed).toBe(true);
  await assertReleased(bound!);
});

test("a failing test body still awaits the owned service cleanup", async () => {
  const server = await startOwnedServer(probe);
  await expect(
    (async () => {
      try {
        throw new Error("SYNTHETIC_BODY_FAILURE");
      } finally {
        await server.stop();
      }
    })(),
  ).rejects.toThrow("SYNTHETIC_BODY_FAILURE");
  await assertReleased(server);
});

test("eight consecutive owned service lifecycles leave no occupied listener", async () => {
  for (let i = 0; i < 8; i++) {
    const server = await startOwnedServer(probe);
    try {
      expect(server.port).toBeGreaterThan(0);
      expect((await fetch(server.url + "/__e2e_owned_server__")).status).toBe(200);
    } finally {
      await server.stop();
    }
    await assertReleased(server);
  }
});
