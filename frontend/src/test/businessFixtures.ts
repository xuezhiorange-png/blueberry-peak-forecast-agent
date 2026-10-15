// SYNTHETIC=true. Unit-only S1/S2 transport DTOs; not security acceptance.
import fixture from "./fixtures/dashboard-synthetic.json";
export const user = {
  principal_id: "SYNTHETIC_USER",
  role: "BUSINESS_USER",
  must_change_password: false,
  auth_revision: 1,
  grant_revision: 1,
};
export const auth = (data: unknown) => ({
  schema_version: "V0_18_LOCAL_AUTH_R1",
  status: "READY",
  data,
});
export const business = (data: unknown) => ({
  schema_version: "V0_18_BUSINESS_ACCESS_R1",
  status: "READY",
  data,
});
const { expected_source_result_hash, ...forecast_identity } = fixture.query;
export const item = {
  forecast_identity,
  expected_source_result_hash,
  entity_name: fixture.query.entity_id,
  forecast_family: fixture.query.forecast_family,
  origin_date: fixture.query.origin_date,
  completeness_status: "COMPLETE",
  canonical_verification_required: true,
  source_status: "completed",
  saved_at: "2026-01-01T00:00:00Z",
  rerun_of_run_id: null,
};
export const scope = {
  entities: [
    {
      entity_id: fixture.query.entity_id,
      entity_name: fixture.query.entity_id,
      hierarchy_level: "BASE",
    },
  ],
  data_types: ["FORECAST"],
  capabilities: ["may_read_forecast"],
  organization_ids: ["SYNTHETIC"],
  grant_revision: 1,
  catalog_snapshot: "a".repeat(64),
};
export const listing = {
  items: [item],
  next_cursor: null,
  grant_revision: 1,
  catalog_snapshot: scope.catalog_snapshot,
};
export const selection = {
  forecast_identity,
  expected_source_result_hash,
  projection_hash: fixture.reads.curve.projection_hash,
  handoff_token: "SYNTHETIC_HANDOFF",
  expires_in: 300,
  authorization_required_on_consumption: true,
};
export const reply = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
