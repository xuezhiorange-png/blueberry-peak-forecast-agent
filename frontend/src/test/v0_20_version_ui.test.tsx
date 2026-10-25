import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { V020AgronomicPreparation } from "../dashboard/agronomic/V020AgronomicPreparation";
import { parsePreview } from "../dashboard/spreadsheet/preview";
import { prepareV020 } from "../dashboard/agronomic/v0_20_prepare";
import synthetic from "../dashboard/agronomic/v0_20_synthetic.json";
import type { WorkerReply, WorkerRequest } from "../dashboard/spreadsheet/contracts";
import type { V020SheetPlan } from "../dashboard/agronomic/v0_20_contracts";

// Transport-only doubles exercise delivery races. Core parsing/normalization and browser
// acceptance are tested separately against real XLSX bytes and real Workers.
class Transport {
  static instances: Transport[] = [];
  onmessage: ((event: { data: WorkerReply }) => void) | null = null;
  messages: WorkerRequest[] = [];
  constructor() {
    Transport.instances.push(this);
  }
  postMessage(m: WorkerRequest) {
    this.messages.push(m);
  }
  terminate() {}
  reply(m: WorkerReply) {
    act(() => this.onmessage?.({ data: m }));
  }
}
afterEach(() => {
  vi.unstubAllGlobals();
  Transport.instances = [];
});
async function open() {
  vi.stubGlobal("Worker", Transport);
  const asset = synthetic.wide.assets.xlsx;
  const book = await parsePreview(
    Uint8Array.from(atob(asset.base64), (c) => c.charCodeAt(0)).buffer,
    "xlsx",
    true,
  );
  const prepared = await prepareV020(book, asset.plans as V020SheetPlan[]);
  render(<V020AgronomicPreparation />);
  fireEvent.click(screen.getByRole("button", { name: "加载农事合成示例" }));
  const w = Transport.instances.at(-1)!;
  w.reply({
    type: "parsed",
    id: w.messages[0].id,
    book: {
      sha256: book.sha256,
      sheets: book.sheets.map((s) => ({
        name: s.name,
        rowCount: s.rows.length,
        columnCount: Math.max(...s.rows.map((r) => r.length)),
      })),
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "应用农事合成映射建议" }));
  return { w, prepared };
}
it("V0_20 ignores a completed Worker result after mapping change or clear", async () => {
  const { w, prepared } = await open();
  fireEvent.click(screen.getByRole("button", { name: "规范化并检查农事数据" }));
  const id = w.messages.at(-1)!.id;
  fireEvent.change(screen.getByLabelText("品种来源编码"), { target: { value: "" } });
  w.reply({ type: "v0_20_prepared", id, prepared });
  expect(screen.queryByRole("button", { name: "下载 agronomic-preparation.json" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "清空农事文件与所有版本" }));
  w.reply({ type: "v0_20_prepared", id, prepared });
  expect(screen.queryByLabelText("选择准备版本")).toBeNull();
});
it("V0_20 preserves five versions without silently accepting or exporting a sixth", async () => {
  const { w, prepared } = await open();
  for (let i = 1; i <= 6; i++) {
    fireEvent.click(screen.getByRole("button", { name: "规范化并检查农事数据" }));
    w.reply({
      type: "v0_20_prepared",
      id: w.messages.at(-1)!.id,
      prepared: { ...prepared, package_id: "V0_20-transport-case-" + i },
    });
  }
  expect(screen.getByLabelText("选择准备版本").querySelectorAll("option")).toHaveLength(6);
  expect(screen.queryByRole("button", { name: "下载 agronomic-preparation.json" })).toBeNull();
  expect(screen.getByText(/已保留五个版本/)).not.toBeNull();
  fireEvent.change(screen.getByLabelText("选择准备版本"), {
    target: { value: "V0_20-transport-case-1" },
  });
  expect(screen.getByRole("button", { name: "下载 agronomic-preparation.json" })).not.toBeNull();
});
