import { expect, type APIRequest } from "@playwright/test";
import { startOwnedServer, type OwnedServer } from "./owned-server";

export type OwnedAuthority = {
  url: string;
  identities: Record<string, string | number>[];
  owned: OwnedServer;
};

// Shared worker fixture only. No retries for state/audit reads, no changed business assertions.
export async function withOwnedAuthority(
  request: APIRequest,
  app: string,
  use: (authority: OwnedAuthority) => Promise<void>,
  auditTimeout?: number,
) {
  const owned = await startOwnedServer(app);
  const url = owned.url;
  let api: Awaited<ReturnType<APIRequest["newContext"]>> | undefined;
  const errors: unknown[] = [];
  try {
    api = await request.newContext();
    const context = api;
    await expect
      .poll(
        async () => {
          owned.assertRunning();
          try {
            return (
              await owned.traceRequest("AUTHORITY_READINESS", (headers) =>
                context.get(url + "/__dashboard_test__/authority", { headers }),
              )
            ).status();
          } catch {
            return 0;
          }
        },
        { timeout: 30000 },
      )
      .toBe(200);
    const state = await (
      await owned.traceRequest("AUTHORITY_STATE", (headers) =>
        context.get(url + "/__dashboard_test__/authority", { headers }),
      )
    ).json();
    expect(state.SYNTHETIC).toBe(true);
    owned.mark("WORKER_USE_BEGIN");
    await use({ url, identities: state.identities, owned });
    owned.mark("WORKER_USE_END");
    expect(
      (
        await (
          await owned.traceRequest("AUTHORITY_AUDIT", (headers) =>
            context.get(url + "/__dashboard_test__/authority", {
              headers,
              ...(auditTimeout === undefined ? {} : { timeout: auditTimeout }),
            }),
          )
        ).json()
      ).read_dml_count,
    ).toBe(0);
  } catch (error) {
    owned.recordFailure("WORKER", error);
    errors.push(error);
  } finally {
    if (api) {
      owned.mark("API_DISPOSE_BEGIN");
      try {
        await api.dispose();
      } catch (error) {
        owned.recordFailure("API_DISPOSE", error);
        errors.push(error);
      } finally {
        owned.mark("API_DISPOSE_END");
      }
    }
    try {
      await owned.stop();
    } catch (error) {
      owned.recordFailure("SERVER_STOP", error);
      errors.push(error);
    }
    owned.mark("FIXTURE_END");
  }
  if (errors.length > 1) throw new AggregateError(errors, "OWNED_AUTHORITY_MULTIPLE_FAILURES");
  if (errors.length === 1) throw errors[0];
}
