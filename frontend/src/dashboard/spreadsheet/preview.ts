import readExcelFile from "read-excel-file/universal";
import {
  FIELDS,
  LIMITS,
  type Cell,
  type LocalBook,
  type Mapping,
  type QualityPreview,
} from "./contracts";
import { safeArchive } from "./xlsxSafety";
export { LIMITS } from "./contracts";

export async function sha256(bytes: ArrayBuffer): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((v) => v.toString(16).padStart(2, "0"))
    .join("");
}
function cell(value: unknown, preserveTime = false): Cell {
  const text =
    value == null
      ? ""
      : value instanceof Date
        ? preserveTime && value.toISOString().slice(11, 23) !== "00:00:00.000"
          ? value.toISOString().slice(0, -1)
          : value.toISOString().slice(0, 10)
        : String(value);
  if (text.length > LIMITS.cellText) throw Error("CELL_TEXT_LIMIT");
  return {
    text,
    ...(preserveTime && value instanceof Date
      ? { temporal_source: "EXCEL_SERIAL_TIMEZONE_UNPROVEN" as const }
      : {}),
    kind: !text
      ? "blank"
      : value instanceof Date
        ? "date"
        : /^-?\d+(?:\.\d+)?$/.test(text)
          ? "number"
          : "text",
  };
}
function csv(text: string): Cell[][] {
  const delimiter = [",", ";", "\t"].sort(
    (a, b) => text.slice(0, 4096).split(b).length - text.slice(0, 4096).split(a).length,
  )[0];
  const rows: Cell[][] = [];
  let row: Cell[] = [],
    value = "",
    quoted = false,
    closed = false;
  const pushCell = () => {
    row.push(cell(value));
    value = "";
    closed = false;
    if (row.length > LIMITS.columns) throw Error("COLUMN_LIMIT");
  };
  const pushRow = () => {
    pushCell();
    rows.push(row);
    row = [];
    if (rows.length > LIMITS.rows) throw Error("ROW_LIMIT");
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        value += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
        closed = true;
      } else value += ch;
    } else if (ch === '"' && !value && !closed) quoted = true;
    else if (ch === delimiter) pushCell();
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      pushRow();
    } else {
      if (closed || ch === '"') throw Error("CSV_STRUCTURE_INVALID");
      value += ch;
    }
    if (value.length > LIMITS.cellText) throw Error("CELL_TEXT_LIMIT");
  }
  if (quoted) throw Error("CSV_STRUCTURE_INVALID");
  if (value || row.length || closed) pushRow();
  return rows;
}
export async function parsePreview(
  buffer: ArrayBuffer,
  format: "csv" | "xlsx",
  v0_20_preserve_time = false,
): Promise<LocalBook> {
  if (!buffer.byteLength || buffer.byteLength > LIMITS.fileBytes) throw Error("FILE_SIZE_LIMIT");
  const hash = await sha256(buffer);
  const sheets =
    format === "csv"
      ? [
          {
            name: "CSV",
            rows: csv(
              new TextDecoder("utf-8", { fatal: true }).decode(buffer).replace(/^\uFEFF/, ""),
            ),
          },
        ]
      : (
          await readExcelFile(safeArchive(new Uint8Array(buffer)).buffer as ArrayBuffer, {
            parseNumber: (n) => n,
          })
        ).map((s) => ({
          name: s.sheet,
          rows: Array.from(s.data, (r) => Array.from(r ?? [], (v) => cell(v, v0_20_preserve_time))),
        }));
  if (!sheets.length || sheets.length > LIMITS.sheets) throw Error("SHEET_LIMIT");
  let cells = 0;
  for (const sheet of sheets) {
    if (sheet.rows.length > LIMITS.rows) throw Error("ROW_LIMIT");
    for (const row of sheet.rows) {
      cells += row.length;
      if (row.length > LIMITS.columns) throw Error("COLUMN_LIMIT");
    }
  }
  if (cells > LIMITS.cells) throw Error("CELL_LIMIT");
  return { sha256: hash, sheets };
}
export function dateValue(text: string): string | null {
  const match = /^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$/.exec(text.trim());
  if (!match) return null;
  const result = `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
  const value = new Date(result + "T00:00:00Z");
  return Number.isFinite(value.getTime()) &&
    value.toISOString().slice(0, 10) === result &&
    +match[1] >= 1900 &&
    +match[1] <= 2200
    ? result
    : null;
}
export function kgValue(text: string): string | null {
  if (!/^\d{1,18}(?:\.\d{1,6})?$/.test(text.trim())) return null;
  const [whole, fraction = ""] = text.trim().split(".");
  return `${BigInt(whole)}.${fraction.padEnd(6, "0")}`;
}
export async function analyzePreview(
  book: LocalBook,
  sheetIndex: number,
  header: number,
  mapping: Mapping,
): Promise<QualityPreview> {
  const sheet = book.sheets[sheetIndex];
  if (!sheet || !Number.isInteger(header) || header < 0 || header >= sheet.rows.length)
    throw Error("HEADER_ROW_INVALID");
  const headers = sheet.rows[header];
  const rows = sheet.rows.slice(header + 1);
  const columns = Math.max(headers.length, ...rows.map((r) => r.length));
  if (
    Object.values(mapping).some((v) => v != null && (!Number.isInteger(v) || v < 0 || v >= columns))
  )
    throw Error("MAPPING_INVALID");
  const report: QualityPreview = {
    status: "USER_FILE_PREVIEW_UNVERIFIED",
    recordCount: rows.length,
    blankRows: 0,
    invalidDate: 0,
    blankDate: 0,
    blankWeight: 0,
    invalidWeight: 0,
    zeroWeight: 0,
    duplicateIds: 0,
    duplicateRows: 0,
    sourceTimeMissing: 0,
    sourceTimeInvalid: 0,
    missingMembers: { base: 0, farm: 0, plot: 0, variety: 0 },
    unmapped: FIELDS.filter(([k]) => mapping[k] == null).map(([k]) => k),
    dateStart: null,
    dateEnd: null,
    dateCount: 0,
    missingDates: [],
    missingDateCount: 0,
    grades: [],
    units: [],
    projectionHash: null,
    columns: Array.from({ length: columns }, (_, i) => ({
      index: i,
      name: headers[i]?.text || `第 ${i + 1} 列（空表头）`,
      empty: rows.filter((r) => !r[i]?.text.trim()).length,
      types: [...new Set(rows.map((r) => r[i]?.kind ?? "blank"))],
    })),
    preview: rows
      .slice(0, LIMITS.preview)
      .map((r) => Array.from({ length: columns }, (_, i) => r[i]?.text ?? "")),
  };
  const seenIds = new Set(),
    seenRows = new Set(),
    days = new Set<string>(),
    grades = new Set<string>(),
    units = new Set<string>();
  const projection: string[][] = [];
  for (const row of rows) {
    const value = (key: keyof Mapping) =>
      mapping[key] == null ? "" : (row[mapping[key]!]?.text.trim() ?? "");
    if (row.every((v) => !v.text.trim())) report.blankRows++;
    if (mapping.date != null) {
      if (!value("date")) report.blankDate++;
      else {
        const day = dateValue(value("date"));
        if (day) days.add(day);
        else report.invalidDate++;
      }
    }
    if (mapping.weight != null) {
      const kg = kgValue(value("weight"));
      if (!value("weight")) report.blankWeight++;
      else if (kg == null) report.invalidWeight++;
      else if (kg === "0.000000") report.zeroWeight++;
    }
    for (const key of ["base", "farm", "plot", "variety"] as const)
      if (mapping[key] != null && !value(key)) report.missingMembers[key]++;
    if (value("record_id")) {
      if (seenIds.has(value("record_id"))) report.duplicateIds++;
      seenIds.add(value("record_id"));
    }
    const identity = JSON.stringify(row.map((v) => v.text));
    if (seenRows.has(identity)) report.duplicateRows++;
    seenRows.add(identity);
    if (mapping.recorded_at != null) {
      if (!value("recorded_at")) report.sourceTimeMissing++;
      else if (!Number.isFinite(Date.parse(value("recorded_at")))) report.sourceTimeInvalid++;
    }
    if (value("grade")) grades.add(value("grade"));
    if (value("unit")) units.add(value("unit"));
    projection.push(
      FIELDS.map(([k]) =>
        k === "date"
          ? (dateValue(value(k)) ?? value(k))
          : k === "weight"
            ? (kgValue(value(k)) ?? value(k))
            : value(k),
      ),
    );
  }
  const ordered = [...days].sort();
  report.dateStart = ordered[0] ?? null;
  report.dateEnd = ordered.at(-1) ?? null;
  report.dateCount = ordered.length;
  for (let i = 1; i < ordered.length; i++) {
    const start = Date.parse(ordered[i - 1] + "T00:00:00Z"),
      n = (Date.parse(ordered[i] + "T00:00:00Z") - start) / 86400000 - 1;
    report.missingDateCount += n;
    for (let j = 1; j <= n && report.missingDates.length < 100; j++)
      report.missingDates.push(new Date(start + j * 86400000).toISOString().slice(0, 10));
  }
  report.grades = [...grades].sort().slice(0, 20);
  report.units = [...units].sort().slice(0, 20);
  if (!report.unmapped.length)
    report.projectionHash = await sha256(
      new TextEncoder().encode(JSON.stringify(projection)).buffer,
    );
  return report;
}
