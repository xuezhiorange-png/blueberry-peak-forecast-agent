import { z } from "zod";
import { forecastIdentity, hash, levels } from "./contracts";

export const userSchema = z.strictObject({
  principal_id: z.string().min(1),
  role: z.enum(["ADMIN", "BUSINESS_USER"]),
  must_change_password: z.boolean(),
  auth_revision: z.number().int().positive(),
  grant_revision: z.number().int().positive(),
});
export type User = z.infer<typeof userSchema>;
export const entitySchema = z.strictObject({
  hierarchy_level: z.enum(levels),
  entity_id: z.string(),
  entity_name: z.string(),
});
export const scopeSchema = z.strictObject({
  entities: z.array(entitySchema),
  data_types: z.array(z.string()),
  capabilities: z.array(z.string()),
  organization_ids: z.array(z.string()),
  grant_revision: z.number().int().positive(),
  catalog_snapshot: hash,
});
export const savedRunSchema = z.strictObject({
  forecast_identity: forecastIdentity,
  expected_source_result_hash: hash,
  entity_name: z.string(),
  forecast_family: z.string(),
  origin_date: z.iso.date(),
  completeness_status: z.enum([
    "COMPLETE",
    "EMPTY",
    "PARTIAL_DATE_WINDOW",
    "INCOMPLETE_CHILD_COVERAGE",
  ]),
  canonical_verification_required: z.literal(true),
  source_status: z.string(),
  saved_at: z.iso.datetime({ offset: true }),
  rerun_of_run_id: z.number().int().nullable(),
});
export const listSchema = z.strictObject({
  items: z.array(savedRunSchema).max(100),
  next_cursor: z.string().min(1).max(2048).nullable(),
  grant_revision: z.number().int().positive(),
  catalog_snapshot: hash,
});
export const selectionSchema = z.strictObject({
  forecast_identity: forecastIdentity,
  expected_source_result_hash: hash,
  projection_hash: hash,
  handoff_token: z.string().min(1).max(8192),
  expires_in: z.number().int().positive().max(300),
  authorization_required_on_consumption: z.literal(true),
});
export type SavedRun = z.infer<typeof savedRunSchema>;
export type RunList = z.infer<typeof listSchema>;
export const authEnvelope = <T>(data: z.ZodType<T>) =>
  z.object({
    schema_version: z.literal("V0_18_LOCAL_AUTH_R1"),
    status: z.literal("READY"),
    data,
  });
export const businessEnvelope = <T>(data: z.ZodType<T>) =>
  z.strictObject({
    schema_version: z.literal("V0_18_BUSINESS_ACCESS_R1"),
    status: z.literal("READY"),
    data,
  });
