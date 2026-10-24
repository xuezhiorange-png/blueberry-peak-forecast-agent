import { parsePreview, analyzePreview } from "./preview";
import type { LocalBook, WorkerReply, WorkerRequest } from "./contracts";

// Parsing has no network capability. Only the main application may request
// registered synthetic assets or authorized saved forecasts.
globalThis.fetch = () => Promise.reject(Error("PARSER_NETWORK_FORBIDDEN"));
let book: LocalBook | null = null;
self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  try {
    let reply: WorkerReply;
    if (request.type === "parse") {
      book = await parsePreview(request.buffer, request.format);
      reply = {
        id: request.id,
        type: "parsed",
        book: {
          sha256: book.sha256,
          sheets: book.sheets.map((s) => ({
            name: s.name,
            rowCount: s.rows.length,
            columnCount: Math.max(0, ...s.rows.map((r) => r.length)),
          })),
        },
      };
    } else {
      if (!book) throw Error("FILE_NOT_SELECTED");
      reply = {
        id: request.id,
        type: "analyzed",
        report: await analyzePreview(book, request.sheet, request.header, request.mapping),
      };
    }
    self.postMessage(reply);
  } catch (error) {
    const code =
      error instanceof Error && /^[A-Z][A-Z0-9_]+$/.test(error.message)
        ? error.message
        : "SPREADSHEET_PARSE_FAILED";
    self.postMessage({ id: request.id, type: "error", code } satisfies WorkerReply);
  }
};
