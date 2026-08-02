import { useEffect, useRef, useState } from "react";
import { TrialClientError } from "../api/trialClient";
import { ForecastForm } from "../features/forecast/ForecastForm";
import { ForecastResult } from "../features/forecast/ForecastResult";
import { forecastApi } from "../features/forecast/forecastApi";
import type {
  ForecastDailyCurve,
  ForecastInputAuthority,
  ForecastInputAuthorityItem,
  ForecastSummary,
  TrialForecastRequest,
} from "../features/forecast/forecastSchemas";

function safeErrorMessage(error: unknown): string {
  if (error instanceof TrialClientError) return error.message;
  return "服务暂不可用，请稍后重试。";
}

async function saveDownload(blob: Blob, filename: string): Promise<void> {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function ForecastPage() {
  const [authority, setAuthority] = useState<ForecastInputAuthority | null>(null);
  const [selectedItem, setSelectedItem] = useState<ForecastInputAuthorityItem | null>(null);
  const [summary, setSummary] = useState<ForecastSummary | null>(null);
  const [daily, setDaily] = useState<ForecastDailyCurve | null>(null);
  const [authorityError, setAuthorityError] = useState<string | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const authorityAbort = useRef<AbortController | null>(null);
  const mutationAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    authorityAbort.current = controller;
    void forecastApi
      .authority(undefined, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setAuthority(value);
        setSelectedItem(value.items[0] ?? null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setAuthorityError(safeErrorMessage(error));
      });
    return () => {
      controller.abort();
      if (authorityAbort.current === controller) authorityAbort.current = null;
    };
  }, []);

  useEffect(() => () => mutationAbort.current?.abort(), []);

  async function createForecast(request: TrialForecastRequest): Promise<void> {
    mutationAbort.current?.abort();
    const controller = new AbortController();
    mutationAbort.current = controller;
    setSubmitting(true);
    setResultError(null);
    try {
      const created = await forecastApi.create(request, undefined, controller.signal);
      const persisted = await forecastApi.read(created.run_id, undefined, controller.signal);
      if (
        persisted.run_id !== created.run_id ||
        persisted.canonical_public_hash !== created.canonical_public_hash
      ) {
        throw new TrialClientError("EVIDENCE_CONFLICT", 409);
      }
      const curve = await forecastApi.daily(persisted.run_id, undefined, controller.signal);
      if (curve.run_id !== persisted.run_id) throw new TrialClientError("EVIDENCE_CONFLICT", 409);
      setSummary(persisted);
      setDaily(curve);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setResultError(safeErrorMessage(error));
      }
    } finally {
      if (mutationAbort.current === controller) {
        mutationAbort.current = null;
        setSubmitting(false);
      }
    }
  }

  async function exportForecast(): Promise<void> {
    if (!summary || exporting) return;
    setExporting(true);
    setResultError(null);
    try {
      const document = await forecastApi.export(summary.run_id);
      await saveDownload(document.blob, document.filename);
    } catch (error) {
      setResultError(safeErrorMessage(error));
    } finally {
      setExporting(false);
    }
  }

  return (
    <main className="page" data-testid="forecast-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TRIAL / FORECAST</p>
          <h1>
            先看清输入，
            <br />
            再相信预测。
          </h1>
          <p className="lead">
            加工厂、产季与地块范围来自服务端 authority；创建后只展示 persisted Forecast evidence。
          </p>
        </div>
        <div className="heading-meta">
          <strong>V0.2 / S5</strong>Forecast production integration
          <br />
          不在浏览器重算业务指标
        </div>
      </div>
      <div className="stack">
        <ForecastForm
          authority={authority}
          selectedItem={selectedItem}
          onSelectItem={setSelectedItem}
          onSubmit={createForecast}
          submitting={submitting}
          errorMessage={authorityError}
        />
        <ForecastResult
          summary={summary}
          daily={daily}
          onExport={exportForecast}
          exporting={exporting}
          errorMessage={resultError}
        />
      </div>
    </main>
  );
}
