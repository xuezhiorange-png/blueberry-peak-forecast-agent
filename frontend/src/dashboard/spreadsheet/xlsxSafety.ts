import { Unzip, UnzipInflate, zipSync } from "fflate";
import { LIMITS } from "./contracts";

// Validate ACTUAL inflated bytes, not merely a ZIP's attacker-controlled size.
// Repack bounded, checked XML as STORE entries before the reader sees it. The
// original file hash remains the identity; this is only an internal read buffer.
export function safeArchive(raw: Uint8Array): Uint8Array {
  const entries: Record<string, Uint8Array> = Object.create(null);
  const names = new Set<string>();
  let total = 0,
    count = 0,
    complete = 0,
    cells = 0,
    sheets = 0;
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const unzip = new Unzip((file) => {
    if (++count > LIMITS.entries) throw Error("ARCHIVE_ENTRY_LIMIT");
    const name = file.name;
    const lower = name.toLowerCase();
    if (
      names.has(lower) ||
      name.startsWith("/") ||
      name.includes("\\") ||
      name.split("/").includes("..")
    )
      throw Error("ARCHIVE_PATH_INVALID");
    names.add(lower);
    if (/vbaproject|macrosheets|activex|externallinks|embeddings|\.bin$/i.test(name))
      throw Error("ACTIVE_CONTENT_FORBIDDEN");
    if (![0, 8].includes(file.compression) || (file.originalSize ?? 0) > LIMITS.expandedBytes)
      throw Error("ARCHIVE_SIZE_LIMIT");
    const chunks: Uint8Array[] = [];
    let length = 0;
    file.ondata = (error, data, final) => {
      if (error) throw error;
      total += data.length;
      length += data.length;
      if (total > LIMITS.expandedBytes || total > Math.max(1, raw.length) * 100)
        throw Error("ARCHIVE_SIZE_LIMIT");
      chunks.push(data);
      if (!final) return;
      complete++;
      if (!/\.(xml|rels)$/i.test(name)) return;
      const bytes = new Uint8Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.length;
      }
      const text = decoder.decode(bytes);
      if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw Error("XML_ENTITY_FORBIDDEN");
      if (/TargetMode\s*=\s*["']External["']/i.test(text)) throw Error("EXTERNAL_LINK_FORBIDDEN");
      if (/<(?:\w+:)?f(?=[\s/>])/i.test(text)) throw Error("FORMULA_FORBIDDEN");
      let maxRow = 0,
        maxColumn = 0;
      for (const tag of text.matchAll(/<(?:\w+:)?(row|c|dimension|sheet)\b([^>]*)>/g)) {
        if (tag[1] === "sheet" && ++sheets > LIMITS.sheets) throw Error("SHEET_LIMIT");
        if (tag[1] === "c" && ++cells > LIMITS.cells) throw Error("CELL_LIMIT");
        const ref = /\b(?:r|ref)\s*=\s*["']([^"']*)["']/.exec(tag[2])?.[1];
        if (!ref || tag[1] === "sheet") continue;
        if (tag[1] === "row") {
          if (!/^\d+$/.test(ref) || Number(ref) > LIMITS.rows) throw Error("ROW_LIMIT");
          continue;
        }
        for (const coordinate of ref.split(":")) {
          const match = /^([A-Z]+)([1-9]\d*)$/.exec(coordinate);
          if (!match) throw Error("CELL_REFERENCE_INVALID");
          let column = 0;
          for (const letter of match[1]) column = column * 26 + letter.charCodeAt(0) - 64;
          const row = Number(match[2]);
          if (row > LIMITS.rows) throw Error("ROW_LIMIT");
          if (column > LIMITS.columns) throw Error("COLUMN_LIMIT");
          maxRow = Math.max(row, maxRow);
          maxColumn = Math.max(column, maxColumn);
        }
      }
      if (maxRow * maxColumn > LIMITS.cells) throw Error("CELL_LIMIT");
      entries[name] = bytes;
    };
    file.start();
  });
  unzip.register(UnzipInflate);
  for (let i = 0; i < raw.length; i += 1024)
    unzip.push(raw.subarray(i, i + 1024), i + 1024 >= raw.length);
  if (!count || complete !== count) throw Error("ARCHIVE_INVALID");
  return zipSync(entries, { level: 0 });
}
