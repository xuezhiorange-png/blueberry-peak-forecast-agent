export const LIMITS = {
  fileBytes: 2 * 1024 * 1024,
  expandedBytes: 8 * 1024 * 1024,
  entries: 128,
  sheets: 8,
  rows: 10000,
  columns: 80,
  cells: 200000,
  cellText: 4096,
  preview: 50,
  timeoutMs: 8000,
} as const;
export const FIELDS = [
  ["date", "业务日期"],
  ["base", "基地"],
  ["farm", "农场"],
  ["plot", "地块 / 分场"],
  ["variety", "品种"],
  ["weight", "记录重量"],
  ["unit", "重量单位"],
  ["grade", "品级（可选）"],
  ["record_id", "记录 ID（可选）"],
  ["recorded_at", "来源记录时间（可选）"],
  ["received_at", "系统接收时间（可选）"],
  ["revision_id", "修订 ID（可选）"],
] as const;
export type Field = (typeof FIELDS)[number][0];
export type Mapping = Partial<Record<Field, number | null>>;
export type Cell = {
  text: string;
  kind: "text" | "number" | "date" | "blank";
  temporal_source?: "EXCEL_SERIAL_TIMEZONE_UNPROVEN";
};
export type LocalBook = { sha256: string; sheets: { name: string; rows: Cell[][] }[] };
export type BookSummary = {
  sha256: string;
  sheets: { name: string; rowCount: number; columnCount: number }[];
};
export type QualityPreview = {
  status: "USER_FILE_PREVIEW_UNVERIFIED";
  recordCount: number;
  blankRows: number;
  invalidDate: number;
  blankDate: number;
  blankWeight: number;
  invalidWeight: number;
  zeroWeight: number;
  duplicateIds: number;
  duplicateRows: number;
  sourceTimeMissing: number;
  sourceTimeInvalid: number;
  missingMembers: Record<string, number>;
  unmapped: Field[];
  dateStart: string | null;
  dateEnd: string | null;
  dateCount: number;
  missingDates: string[];
  missingDateCount: number;
  grades: string[];
  units: string[];
  projectionHash: string | null;
  columns: { index: number; name: string; empty: number; types: string[] }[];
  preview: string[][];
};
export type WorkerRequest =
  | {
      type: "parse";
      id: number;
      buffer: ArrayBuffer;
      format: "csv" | "xlsx";
      v0_20_preserve_time?: boolean;
    }
  | { type: "analyze"; id: number; sheet: number; header: number; mapping: Mapping }
  | import("../agronomic/v0_20_contracts").V020WorkerRequest;
export type WorkerReply =
  | { id: number; type: "parsed"; book: BookSummary }
  | { id: number; type: "analyzed"; report: QualityPreview }
  | { id: number; type: "error"; code: string }
  | import("../agronomic/v0_20_contracts").V020WorkerReply;
