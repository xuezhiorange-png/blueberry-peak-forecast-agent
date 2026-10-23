import { afterEach, expect, it, vi } from "vitest";
import { z } from "zod";
import { request } from "../dashboard/api/client";
import { subscribeSecurity } from "../dashboard/api/security";

afterEach(() => vi.restoreAllMocks());

it.each([403, 409])(
  "shadow %s cannot revoke the independent formal Forecast context",
  async (status) => {
    const invalidation = vi.fn();
    const unsubscribe = subscribeSecurity(invalidation);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "FORBIDDEN" } }), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(
      request("/api/v1/rolling-forecast-runs", z.unknown(), new AbortController().signal),
    ).rejects.toThrow();
    expect(invalidation).not.toHaveBeenCalled();
    unsubscribe();
  },
);
