import { expect, it } from "vitest";
import { strToU8, zipSync } from "fflate";
import { parsePreview, analyzePreview, LIMITS } from "../dashboard/spreadsheet/preview";
import { safeArchive } from "../dashboard/spreadsheet/xlsxSafety";

it("previews UTF-8 CSV locally and preserves blank versus zero", async () => {
  const book = await parsePreview(
    new TextEncoder().encode("日子,名字,重量\n2026-11-01,A,0\n2026-11-02,A,\nwrong,,oops\n").buffer,
    "csv",
  );
  const report = await analyzePreview(book, 0, 0, { date: 0, base: 1, weight: 2 });
  expect(report.status).toBe("USER_FILE_PREVIEW_UNVERIFIED");
  expect(report.recordCount).toBe(3);
  expect(report.zeroWeight).toBe(1);
  expect(report.blankWeight).toBe(1);
  expect(report.invalidWeight).toBe(1);
  expect(report.invalidDate).toBe(1);
  expect(report.missingMembers.base).toBe(1);
});

it("handles quoted commas, multiple line text, non-first header and partial mapping", async () => {
  const book = await parsePreview(
    new TextEncoder().encode(
      '说明\nWhen,Who,Mass\n2026-11-01,"A,B",12.500000\n2026-11-03,"line\nname",0\n',
    ).buffer,
    "csv",
  );
  const report = await analyzePreview(book, 0, 1, { date: 0, weight: 2 });
  expect(report.recordCount).toBe(2);
  expect(report.preview[0][1]).toBe("A,B");
  expect(report.missingDates).toEqual(["2026-11-02"]);
  expect(report.unmapped).toContain("farm");
  expect(report.columns[2].empty).toBe(0);
});

it("detects duplicates and rejects invalid Decimal quantities without formula evaluation", async () => {
  const book = await parsePreview(
    new TextEncoder().encode(
      "date,base,weight,id\n2026-11-01,A,1,x\n2026-11-01,A,1,x\n2026-02-30,A,-2,y\n2026-11-03,A,=2+2,z\n",
    ).buffer,
    "csv",
  );
  const report = await analyzePreview(book, 0, 0, { date: 0, base: 1, weight: 2, record_id: 3 });
  expect(report.duplicateIds).toBe(1);
  expect(report.duplicateRows).toBe(1);
  expect(report.invalidWeight).toBe(2);
  expect(report.invalidDate).toBe(1);
});

it("enforces size, row and column limits before rendering", async () => {
  await expect(parsePreview(new ArrayBuffer(LIMITS.fileBytes + 1), "csv")).rejects.toThrow(
    "FILE_SIZE_LIMIT",
  );
  await expect(
    parsePreview(strToU8("a,".repeat(LIMITS.columns + 1)).buffer as ArrayBuffer, "csv"),
  ).rejects.toThrow("COLUMN_LIMIT");
  await expect(
    parsePreview(strToU8("a\n".repeat(LIMITS.rows + 2)).buffer as ArrayBuffer, "csv"),
  ).rejects.toThrow("ROW_LIMIT");
});

it.each([
  ["macro", { "xl/vbaProject.bin": "bad" }],
  [
    "external",
    {
      "xl/_rels/workbook.xml.rels":
        '<Relationships><Relationship TargetMode="External" Target="https://secret.invalid"/></Relationships>',
    },
  ],
  [
    "doctype",
    { "xl/workbook.xml": '<!DOCTYPE x [<!ENTITY a SYSTEM "https://secret.invalid">]><x/>' },
  ],
  [
    "formula",
    {
      "xl/worksheets/sheet1.xml":
        '<worksheet><row r="1"><c r="A1"><f>WEBSERVICE("https://secret.invalid")</f></c></row></worksheet>',
    },
  ],
  [
    "sparse",
    {
      "xl/worksheets/sheet1.xml":
        '<worksheet><row r="1048576"><c r="XFD1048576"><v>1</v></c></row></worksheet>',
    },
  ],
])("blocks unsafe XLSX %s before spreadsheet interpretation", async (_kind, files) => {
  const zipped = zipSync(
    Object.fromEntries(Object.entries(files).map(([k, v]) => [k, strToU8(v!)])),
  );
  await expect(parsePreview(zipped.buffer as ArrayBuffer, "xlsx")).rejects.toThrow();
});

it("bounds actual inflation and rejects duplicate paths, empty formula and entities", () => {
  const inflated = zipSync({ "xl/sharedStrings.xml": strToU8("A".repeat(2 * 1024 * 1024)) });
  expect(() => safeArchive(inflated)).toThrow("ARCHIVE_SIZE_LIMIT");
  for (const xml of ['<c r="A1"><f/><v>1</v></c>', '<!ENTITY e "value"><x/>']) {
    expect(() => safeArchive(zipSync({ "xl/worksheets/sheet1.xml": strToU8(xml) }))).toThrow();
  }
  expect(() =>
    safeArchive(zipSync({ "xl/a.xml": strToU8("<x/>"), "xl/A.xml": strToU8("<x/>") })),
  ).toThrow("ARCHIVE_PATH_INVALID");
});
