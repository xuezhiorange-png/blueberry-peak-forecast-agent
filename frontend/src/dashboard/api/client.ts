import { z } from "zod";
import {
  comparisonRequest,
  costSelection,
  decisionSchemas,
  forecastQuery,
  readSchemas,
  simulationRequest,
  type ForecastReadQuery,
  type SimulationRequest,
  type ComparisonRequest,
  type SimulationResult,
} from "../schemas/contracts";

export const COSTS = {
  SYNTHETIC_BALANCED_R1: "35f8316fbf2688b108e173d0d8438ce6323aa0f9db208f7a143f72e07aa5679f",
  SYNTHETIC_UNDER_4X_R1: "8d6f2567a18bd298f1a261a059a88b2772d77bcc6f03e313dc3853c9cd2f0f3f",
  SYNTHETIC_OVER_4X_R1: "6cec3474d85b6421467d43ff71fb6a52a4b4904289cded15c4fdcea74e49fe36",
} as const;
export type CostId = keyof typeof COSTS;
export class DashboardError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(code);
  }
}
export const errorCopy: Record<number, string> = {
  0: "网络连接失败，请重试。",
  401: "请通过可信上游完成认证。",
  403: "当前身份没有读取权限。",
  404: "指定保存记录或合同不存在，请核对完整身份。",
  409: "来源身份不一致，已停止展示受影响结果，请重新核验。",
  413: "请求超过技术上限，请减少情景或输入长度。",
  422: "输入不合法，请检查身份、日期与产能字段。",
  503: "服务暂时不可用，请稍后重试。",
};
export function safeError(error: unknown) {
  return error instanceof DashboardError
    ? (errorCopy[error.status] ?? "响应合同不兼容，已停止展示，请重新核验。")
    : "暂时无法读取，请重试。";
}
export function identityMatches(a: Record<string, unknown> | null, b: Record<string, unknown>) {
  return (
    a !== null &&
    Object.keys(a).length === Object.keys(b).length &&
    Object.entries(b).every(([k, v]) => a[k] === v)
  );
}
export function assertIdentity(
  value: { forecast_identity: Record<string, unknown> | null; source_result_hash: string | null },
  query: ForecastReadQuery,
) {
  const { expected_source_result_hash, ...identity } = query;
  if (
    !identityMatches(value.forecast_identity, identity) ||
    value.source_result_hash !== expected_source_result_hash
  )
    throw new DashboardError(409, "AUTHORITY_MISMATCH");
}
const paths = new Set([
  ...Object.keys(readSchemas).map((k) => `/api/v1/forecast-intelligence/${k}`),
  ...Object.keys(decisionSchemas).map((k) => `/api/v1/decision-support/${k}`),
]);
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
  params?: Record<string, string | number>,
  body?: unknown,
): Promise<T> {
  if (!paths.has(path)) throw new DashboardError(422, "PATH_NOT_ALLOWED");
  const encoded = body === undefined ? undefined : JSON.stringify(body);
  if (encoded !== undefined && new TextEncoder().encode(encoded).length > 131072)
    throw new DashboardError(413, "REQUEST_BODY_TOO_LARGE");
  const query = params
    ? "?" + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
    : "";
  let response: Response;
  try {
    response = await fetch(path + query, {
      method: encoded === undefined ? "GET" : "POST",
      headers: {
        Accept: "application/json",
        ...(encoded === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: encoded,
      signal,
      credentials: "same-origin",
      redirect: "error",
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new DashboardError(0, "NETWORK_UNAVAILABLE");
  }
  if (!response.ok) throw new DashboardError(response.status, "REQUEST_REJECTED");
  if (!/^application\/json(?:;|$)/i.test(response.headers.get("content-type") ?? ""))
    throw new DashboardError(502, "RESPONSE_INVALID");
  const text = await response.text();
  if (text.length > 4194304) throw new DashboardError(502, "RESPONSE_TOO_LARGE");
  try {
    return schema.parse(JSON.parse(text));
  } catch {
    throw new DashboardError(502, "RESPONSE_INVALID");
  }
}
const capabilities = {
  overview: "GET_FORECAST_OVERVIEW",
  curve: "GET_FORECAST_CURVE",
  hierarchy: "GET_HIERARCHICAL_FORECAST",
  uncertainty: "GET_FORECAST_UNCERTAINTY",
  attribution: "GET_FORECAST_ATTRIBUTION",
} as const;
export async function read<K extends keyof typeof capabilities>(
  kind: K,
  input: ForecastReadQuery,
  signal: AbortSignal,
): Promise<z.infer<(typeof readSchemas)[K]>> {
  const query = forecastQuery.parse(input);
  const result = await request(
    `/api/v1/forecast-intelligence/${kind}`,
    readSchemas[kind] as unknown as z.ZodType<z.infer<(typeof readSchemas)[K]>>,
    signal,
    query,
  );
  assertIdentity(result, query);
  if (
    result.source_kind !== query.source_kind ||
    result.source_run_id !== query.run_id ||
    result.policy_version !==
      (kind === "uncertainty"
        ? "V0_16_ROLLING_DATE_BOUND_CONFORMAL_R1"
        : kind === "attribution"
          ? "V0_16_M1_STANDARDIZED_LINEAR_ATTRIBUTION_R1"
          : query.source_kind === "HIERARCHICAL"
            ? "HIERARCHICAL_BOTTOM_UP_EXACT_SUM_R1"
            : query.policy_version) ||
    (result.hierarchy_identity &&
      (result.hierarchy_identity.entity_id !== query.entity_id ||
        result.hierarchy_identity.hierarchy_level !== query.hierarchy_level)) ||
    (result.authority_identity &&
      (result.authority_identity.source_policy_version !== query.policy_version ||
        result.authority_identity.source_baseline_id !== query.baseline_id))
  )
    throw new DashboardError(409, "SOURCE_AUTHORITY_MISMATCH");
  if (result.capability !== capabilities[kind])
    throw new DashboardError(409, "CAPABILITY_MISMATCH");
  if ("daily_rows" in (result.data ?? {})) {
    const rows = (
      result.data as { daily_rows: z.infer<typeof import("../schemas/contracts").dailyRow>[] }
    ).daily_rows;
    const data = result.data as { available_day_count: number };
    if (
      rows.length !== data.available_day_count ||
      new Set(rows.map((row) => row.target_date)).size !== rows.length ||
      rows.some(
        (row, index) =>
          index > 0 &&
          (row.target_date <= rows[index - 1].target_date ||
            row.lead_day <= rows[index - 1].lead_day),
      )
    )
      throw new DashboardError(409, "CURVE_ORDER_MISMATCH");
    for (const row of rows)
      if (
        row.source_result_hash !== query.expected_source_result_hash ||
        row.forecast_run_id !== query.run_id ||
        row.entity_id !== query.entity_id ||
        row.origin_date !== query.origin_date ||
        row.hierarchy_level !== query.hierarchy_level
      )
        throw new DashboardError(409, "ROW_AUTHORITY_MISMATCH");
  }
  return result;
}
export async function quality(signal: AbortSignal, current = false) {
  const result = await request(
    "/api/v1/forecast-intelligence/quality",
    readSchemas.quality,
    signal,
    {
      mode: current ? "CURRENT_PRODUCTION_ACCURACY" : "HISTORICAL_VALIDATION",
      model_id: "V0_15_S5_M1_RIDGE",
    },
  );
  if (
    result.capability !== "GET_FORECAST_QUALITY" ||
    result.evidence_mode !== (current ? "NO_CURRENT_ACTUAL" : "RETROSPECTIVE_OBSERVATION")
  )
    throw new DashboardError(409, "QUALITY_AUTHORITY_MISMATCH");
  return result;
}
export async function cost(id: CostId, signal: AbortSignal) {
  const selected = costSelection.parse({
    cost_contract_id: id,
    expected_cost_contract_hash: COSTS[id],
  });
  const result = await request(
    "/api/v1/decision-support/business-loss",
    decisionSchemas["business-loss"],
    signal,
    selected,
  );
  if (
    result.cost_contract_id !== id ||
    result.cost_contract_hash !== COSTS[id] ||
    result.data?.cost_contract.contract_hash !== COSTS[id] ||
    result.data.cost_contract.contract_id !== id
  )
    throw new DashboardError(409, "COST_AUTHORITY_MISMATCH");
  return result;
}
export async function simulate(input: SimulationRequest, signal: AbortSignal) {
  const body = simulationRequest.parse(input);
  const result = await request(
    "/api/v1/decision-support/simulate-capacity",
    decisionSchemas["simulate-capacity"],
    signal,
    undefined,
    body,
  );
  verifyDecision(result, body);
  if (result.data) verifyScenario(result.data, body, result.adapter_saved_forecast_hash);
  if (
    result.capability !== "SIMULATE_CAPACITY" ||
    (result.data &&
      (result.data.scenario_id !== body.scenario_id ||
        result.data.result_hash !== result.engine_result_hash))
  )
    throw new DashboardError(409, "RESULT_AUTHORITY_MISMATCH");
  return result;
}
export async function compare(input: ComparisonRequest, signal: AbortSignal) {
  const body = comparisonRequest.parse(input);
  const result = await request(
    "/api/v1/decision-support/compare-capacity-scenarios",
    decisionSchemas["compare-capacity-scenarios"],
    signal,
    undefined,
    body,
  );
  verifyDecision(result, body);
  if (result.data) {
    const { scenario_results, comparison } = result.data;
    if (
      scenario_results.length !== body.scenarios.length ||
      comparison.rankings.length !== body.scenarios.length ||
      new Set(scenario_results.map((r) => r.scenario_id)).size !== body.scenarios.length ||
      new Set(comparison.rankings.map((r) => r.scenario_id)).size !== body.scenarios.length
    )
      throw new DashboardError(409, "COMPARISON_MEMBERS_MISMATCH");
    for (const scenario of body.scenarios) {
      const output = scenario_results.find((r) => r.scenario_id === scenario.scenario_id);
      if (!output) throw new DashboardError(409, "SCENARIO_MISSING");
      verifyScenario(output, { ...body, ...scenario }, result.adapter_saved_forecast_hash);
    }
    for (const [index, rank] of comparison.rankings.entries()) {
      const output = scenario_results.find((r) => r.scenario_id === rank.scenario_id);
      if (
        !output ||
        rank.result_hash !== output.result_hash ||
        rank.scenario_hash !== output.scenario_hash ||
        rank.scenario_rank !== index + 1
      )
        throw new DashboardError(409, "RANK_AUTHORITY_MISMATCH");
    }
  }
  if (
    result.capability !== "COMPARE_CAPACITY_SCENARIOS" ||
    (result.data && result.data.comparison.comparison_hash !== result.engine_result_hash)
  )
    throw new DashboardError(409, "RESULT_AUTHORITY_MISMATCH");
  return result;
}
function verifyScenario(
  result: SimulationResult,
  body: SimulationRequest,
  savedHash: string | null,
) {
  const dates = body.capacity_rows.map((r) => r.date).sort();
  if (
    result.saved_forecast_hash !== savedHash ||
    result.forecast_source_hash !== body.expected_source_result_hash ||
    result.hierarchy_level !== body.forecast_selection.hierarchy_level ||
    result.hierarchy_entity_id !== body.forecast_selection.entity_id ||
    result.cost_contract_hash !== body.expected_cost_contract_hash ||
    result.planning_level !== body.planning_level ||
    result.scenario_id !== body.scenario_id ||
    result.day_count !== dates.length ||
    JSON.stringify(result.dates) !== JSON.stringify(dates) ||
    JSON.stringify(result.daily_rows.map((r) => r.date)) !== JSON.stringify(dates)
  )
    throw new DashboardError(409, "SCENARIO_AUTHORITY_MISMATCH");
}
function verifyDecision(
  result: {
    forecast_identity: Record<string, unknown> | null;
    source_result_hash: string | null;
    planning_level: string | null;
    cost_contract_id: string;
    cost_contract_hash: string;
  },
  body: SimulationRequest | ComparisonRequest,
) {
  assertIdentity(result, {
    ...body.forecast_selection,
    expected_source_result_hash: body.expected_source_result_hash,
  });
  if (
    result.planning_level !== body.planning_level ||
    result.cost_contract_id !== body.cost_contract_id ||
    result.cost_contract_hash !== body.expected_cost_contract_hash
  )
    throw new DashboardError(409, "DECISION_AUTHORITY_MISMATCH");
}
