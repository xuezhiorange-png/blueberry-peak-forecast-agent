import { expect, it } from "vitest";
import synthetic from "../dashboard/agronomic/v0_20_synthetic.json";
import { parsePreview } from "../dashboard/spreadsheet/preview";
import { prepareV020, dateV020 } from "../dashboard/agronomic/v0_20_prepare";
import type { V020SheetPlan } from "../dashboard/agronomic/v0_20_contracts";
import { unzipSync } from "fflate";
import { sha256 } from "../dashboard/spreadsheet/preview";

async function custom(kind: V020SheetPlan["kind"], rows: Record<string, string>[]) {
  const common = {
    base: "B",
    farm: "F",
    subfarm: "S",
    plot: "P",
    variety: "V",
    season: "2023-2024",
    production_system: "DECIDUOUS_FORCING",
    status: "OBSERVED",
    source_reference: "source",
    source_version: "r1",
    recorded_at: "2023-09-03",
    known_at: "2023-09-04",
    method: "method",
    sample_scope: "scope",
    quality_status: "DECLARED",
  };
  const data = rows.map((r) => ({ ...common, ...r }));
  const fields = [...new Set(data.flatMap((r) => Object.keys(r)))];
  const csv = [
    fields,
    ...data.map((r) => fields.map((f) => (r as Record<string, string>)[f] ?? "")),
  ]
    .map((r) => r.map((v) => '"' + v.replaceAll('"', '""') + '"').join(","))
    .join("\n");
  const book = await parsePreview(new TextEncoder().encode(csv).buffer, "csv", true);
  const plan: V020SheetPlan = {
    sheet: 0,
    header: 0,
    kind,
    layout: "LONG",
    slots: [],
    columns: Object.fromEntries(fields.map((f, i) => [f, i])),
  };
  return prepareV020(book, [plan]);
}

function bytes(base64: string) {
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0)).buffer;
}
it.each(["wide", "long"] as const)(
  "V0_20 prepares real parsed %s XLSX with three kinds and two seasons",
  async (scenario) => {
    const a = synthetic[scenario].assets.xlsx;
    const book = await parsePreview(bytes(a.base64), "xlsx", true);
    const p = await prepareV020(book, a.plans as V020SheetPlan[]);
    expect(p.data.summary.kind_counts.AREA).toBe(18);
    expect(p.data.summary.kind_counts.EVENT).toBe(36);
    expect(p.data.summary.kind_counts.PHENOLOGY).toBe(36);
    expect(Object.keys(p.data.summary.season_counts)).toEqual(["2023-2024", "2024-2025"]);
    expect(p.data.summary.base_count).toBe(2);
    expect(p.data.summary.variety_count).toBe(2);
    expect(p.data.data_class, JSON.stringify(book.sheets.at(-1))).toBe("SYNTHETIC_TEST_FIXTURE");
    expect(
      p.data.records
        .filter((r) => r.phenology?.production_plan_field)
        .every((r) => r.phenology!.canonical_stage === null),
    ).toBe(true);
    expect(p.data.restrictions.model_use_authorized).toBe(false);
    expect(p.data.summary.research_admitted_count).toBe(0);
    expect(p.data.records.every((r) => r.states.includes("PIT_NOT_PROVEN"))).toBe(true);
    expect(p.files.map((f) => f.name)).toEqual([
      "agronomic-preparation.json",
      "agronomic-area.csv",
      "agronomic-events.csv",
      "agronomic-phenology.csv",
      "agronomic-quality-report.html",
    ]);
    expect(await prepareV020(book, a.plans as V020SheetPlan[])).toEqual(p);
  },
);
it("V0_20 keeps ambiguous forcing, conflicts, unknown plot and month precision", async () => {
  const a = synthetic.negative.assets.xlsx;
  const p = await prepareV020(
    await parsePreview(bytes(a.base64), "xlsx", true),
    a.plans as V020SheetPlan[],
  );
  const codes = p.data.summary.issue_counts;
  for (const c of [
    "FORCING_METHOD_UNRESOLVED",
    "DUPLICATE_REVISION",
    "AREA_INTERVAL_CONFLICT",
    "AREA_BASIS_CONFLICT",
    "PLANNED_OBSERVED_CONFLICT",
    "DATE_PRECISION_INSUFFICIENT",
    "IDENTITY_UNMAPPED",
  ])
    expect(codes[c], c).toBeGreaterThan(0);
  const forcing = p.data.records.find((r) => r.event?.raw_type === "促早")!;
  expect(forcing.event?.canonical_type).toBeNull();
  expect(p.data.records.filter((r) => r.logical_id === "SYN-DUP")).toHaveLength(2);
  expect(
    p.data.records.find((r) => r.phenology && r.business_date.precision === "MONTH")?.business_date
      .raw,
  ).toBe("2023-11");
});
it("V0_20 CSV normalizes without permitting arbitrary user-file authority", async () => {
  const a = synthetic.long.assets.csv;
  const book = await parsePreview(bytes(a.base64), "csv", true);
  const p = await prepareV020(book, a.plans as V020SheetPlan[]);
  const changed = { ...book, sha256: "a".repeat(64) };
  const q = await prepareV020(changed, a.plans as V020SheetPlan[]);
  expect(q.data.data_class).toBe("USER_FILE_PREVIEW_UNVERIFIED");
  expect(q.data.records.every((r) => r.scope.resolved === null)).toBe(true);
  expect(q.preparation_sha256).not.toBe(p.preparation_sha256);
  expect(
    p.data.records.some((r) => r.area?.basis === "PLANTED" && r.area.value === "100.000000"),
  ).toBe(true);
  expect(
    p.data.records.some((r) => r.area?.basis === "PRODUCTIVE" && r.area.value === "80.000000"),
  ).toBe(true);
});
it("V0_20 never fabricates date-only timestamps or percent bloom", () => {
  for (const s of ["2024-09-01", "2024-09", "2024", ""]) expect(dateV020(s).instant).toBeNull();
  expect(dateV020("2024-09-01T10:00:00").precision).toBe("LOCAL_DATETIME");
  expect(dateV020("2024-09-01T10:00:00+08:00").instant).toBe("2024-09-01T02:00:00.000Z");
  expect(dateV020("2024-02-30").precision).toBe("UNKNOWN");
});

it("V0_20 rejects cyclic and disconnected revisions while retaining all originals", async () => {
  const p = await custom("EVENT", [
    {
      logical_id: "cycle",
      revision_id: "r1",
      supersedes_revision: "r2",
      event_type: "PRUNING",
      date: "2023-09-01",
    },
    {
      logical_id: "cycle",
      revision_id: "r2",
      supersedes_revision: "r1",
      event_type: "PRUNING",
      date: "2023-09-02",
    },
    { logical_id: "fork", revision_id: "r1", event_type: "PRUNING", date: "2023-09-01" },
    { logical_id: "fork", revision_id: "r2", event_type: "PRUNING", date: "2023-09-02" },
  ]);
  expect(p.data.records).toHaveLength(4);
  expect(
    p.data.records.slice(0, 2).every((r) => r.issues.some((i) => i.code === "REVISION_CYCLE")),
  ).toBe(true);
  expect(
    p.data.records
      .slice(2)
      .every((r) => r.issues.some((i) => i.code === "REVISION_WINNER_UNRESOLVED")),
  ).toBe(true);
});
it("V0_20 checks phase order only within a source, sample, method, season and observation class", async () => {
  const rows = [
    { stage: "BLOOM_10", date: "2023-11-20" },
    { stage: "BLOOM_50", date: "2023-11-01" },
  ];
  expect((await custom("PHENOLOGY", rows)).data.summary.issue_counts.PHENOLOGY_ORDER_CONFLICT).toBe(
    2,
  );
  for (const change of [
    { source_reference: "other" },
    { source_version: "r2" },
    { sample_scope: "other" },
    { status: "PLANNED" },
    { season: "2024-2025" },
    { production_system: "EVERGREEN" },
  ]) {
    const q = await custom("PHENOLOGY", [rows[0], { ...rows[1], ...change }]);
    expect(q.data.summary.issue_counts.PHENOLOGY_ORDER_CONFLICT).toBeUndefined();
  }
});
it("V0_20 preserves null area, explicit zero, original rows and all time evidence", async () => {
  const p = await custom("AREA", [
    {
      area_basis: "PLANTED",
      area_value: "",
      area_unit: "mu",
      logical_id: "one",
      revision_id: "r1",
      effective_from: "2023-07-01",
      effective_to: "2024-06-30",
    },
    {
      area_basis: "EFFECTIVE",
      area_value: "0",
      area_unit: "mu",
      logical_id: "two",
      revision_id: "r1",
      effective_from: "2023-07-01",
      effective_to: "2024-06-30",
      recorded_at: "2023-09-02T03:00:00+08:00",
      known_at: "2023-09-01T03:00:00+08:00",
    },
  ]);
  expect(p.data.records[0].area!.value).toBeNull();
  expect(p.data.records[1].area!.value).toBe("0.000000");
  expect(p.data.summary.issue_counts.KNOWN_BEFORE_RECORDED).toBe(1);
  expect(p.data.source_rows).toHaveLength(2);
  expect(p.data.records.every((r) => r.scope.plot_authority_id === null)).toBe(true);
});
it("V0_20 exported ZIP, checksums and escaped reports bind the actual preparation", async () => {
  const p = await custom("EVENT", [
    {
      base: "=1+1",
      variety: "<img src=x onerror=alert(1)>",
      event_type: "促早",
      date: "2023-09",
      logical_id: "test",
      revision_id: "r1",
    },
  ]);
  expect(p.html).not.toContain("<img src=x");
  expect(p.html).toContain("&lt;img");
  const csv = p.files.find((f) => f.name === "agronomic-events.csv")!.content;
  expect(csv).toContain("'=1+1");
  const zipped = unzipSync(p.zip_bytes);
  expect(Object.keys(zipped)).toHaveLength(5);
  for (const f of p.files) {
    expect(await sha256(new TextEncoder().encode(f.content).buffer)).toBe(f.sha256);
    expect(Array.from(zipped[p.package_id + "/" + f.name])).toEqual(
      Array.from(new TextEncoder().encode(f.content)),
    );
  }
});
it("V0_20 refuses synthetic relabeling after cells or source identity change", async () => {
  const a = synthetic.wide.assets.xlsx;
  const b = await parsePreview(bytes(a.base64), "xlsx", true);
  b.sheets[1].rows[3][0].text = "changed";
  const p = await prepareV020(b, a.plans as V020SheetPlan[]);
  expect(p.data.data_class).toBe("USER_FILE_PREVIEW_UNVERIFIED");
  expect(p.data.records.every((r) => r.scope.resolved === null)).toBe(true);
});
it("V0_20 rejects unsafe mapping before expansion without silently dropping rows", async () => {
  const a = synthetic.wide.assets.xlsx;
  const b = await parsePreview(bytes(a.base64), "xlsx", true);
  const plans = a.plans as V020SheetPlan[];
  await expect(prepareV020(b, [plans[0], plans[0]])).rejects.toThrow("V0_20_DUPLICATE_SHEET_PLAN");
  await expect(prepareV020(b, [{ ...plans[0], columns: { base: 999 } }])).rejects.toThrow(
    "V0_20_COLUMN_INVALID",
  );
});
it("V0_20 treats prototype-like user text as unknown data, never as registry entries", async () => {
  const p = await custom("PHENOLOGY", [
    { stage: "__proto__", status: "constructor", date: "2023-10-01", season: "__proto__" },
  ]);
  expect(p.data.records[0].phenology!.production_plan_field).toBeNull();
  expect(p.data.records[0].phenology!.canonical_stage).toBeNull();
  expect(p.data.records[0].observed_or_planned).toBe("UNKNOWN");
  expect(p.data.summary.season_counts["__proto__"]).toBe(1);
});
it("V0_20 applies the existing registry's production-system eligibility without inventing effects", async () => {
  const p = await custom("EVENT", [
    { event_type: "HEATING_START", date: "2023-10-01", production_system: "DECIDUOUS_NATURAL" },
  ]);
  expect(p.data.summary.issue_counts.EVENT_SYSTEM_CONFLICT).toBe(1);
  const q = await custom("EVENT", [
    { event_type: "HEATING_START", date: "2023-10-01", production_system: "DECIDUOUS_FORCING" },
  ]);
  expect(q.data.summary.issue_counts.EVENT_SYSTEM_CONFLICT).toBeUndefined();
});
it.each(["", "UNKNOWN", "未知", "不详"])(
  "V0_20 forcing method %s does not establish a heating mapping",
  async (method) => {
    const a = synthetic.wide.assets.xlsx;
    const b = await parsePreview(bytes(a.base64), "xlsx", true);
    const plan = (a.plans as V020SheetPlan[]).find((p) => p.kind === "EVENT")!;
    const slot = plan.slots.find((s) => s.declared_type === "HEATING_START")!;
    b.sheets[plan.sheet].rows[plan.header][slot.column].text = "促早日期";
    b.sheets[plan.sheet].rows[plan.header + 1][plan.columns.method!].text = method;
    const p = await prepareV020(b, [plan]);
    const r = p.data.records.find(
      (r) => r.source_row === plan.header + 2 && r.slot?.id === slot.id,
    )!;
    expect(r.event!.canonical_type).toBeNull();
    expect(r.event!.method).toBe(method || null);
    expect(r.issues.some((i) => i.code === "FORCING_METHOD_UNRESOLVED")).toBe(true);
  },
);
