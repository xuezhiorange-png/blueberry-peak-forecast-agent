import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { DashboardError, request, safeError } from "../api/client";
import { subscribeSecurity } from "../api/security";
import { useSession } from "../context/SessionContext";
import { Panel } from "./presentation";
import "../styles/rollingForecast.css";
import {
  rollingComparison,
  rollingEnvelope,
  rollingHistory,
  rollingRun,
  type RollingRun,
} from "../schemas/rolling";

const PATH = "/api/v1/rolling-forecast-runs";
type History = z.infer<typeof rollingHistory>;
type Comparison = z.infer<typeof rollingComparison>;

export function RollingForecastPanel() {
  const session = useSession();
  return <RollingForecastWorkspace key={session?.user.principal_id ?? "no-session"} />;
}

function Curve({ rows, model }: { rows: { date: string; kg: string }[]; model: string }) {
  // Coordinates only: business quantities and all peak metrics remain server values.
  const maximum = Math.max(1, ...rows.map((r) => Number(r.kg)));
  return (
    <figure>
      <svg
        viewBox="0 0 600 180"
        role="img"
        aria-label={`${model} 未来15日预测曲线；精确值见下表`}
        style={{ width: "100%", maxHeight: 220 }}
      >
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          points={rows
            .map((r, i) => `${12 + i * 40},${165 - (Number(r.kg) / maximum) * 150}`)
            .join(" ")}
        />
      </svg>
      <figcaption>
        {rows[0]?.date} 至 {rows.at(-1)?.date} · kg（非分位数）
      </figcaption>
    </figure>
  );
}

function RollingForecastWorkspace() {
  const [history, setHistory] = useState<History | null>(null);
  const [run, setRun] = useState<RollingRun | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [resourceIndex, setResourceIndex] = useState(0);
  const [snapshotIndex, setSnapshotIndex] = useState(0);
  const [modelIndex, setModelIndex] = useState(0);
  const [modeIndex, setModeIndex] = useState(0);
  const [origin, setOrigin] = useState("");
  const [cutoff, setCutoff] = useState("17:00");
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [baseFilter, setBaseFilter] = useState("");
  const [seasonFilter, setSeasonFilter] = useState("");
  const [originFilter, setOriginFilter] = useState("");
  const generation = useRef(0);
  const active = useRef<AbortController | null>(null);
  function cancel() {
    generation.current++;
    active.current?.abort();
    setBusy(false);
  }
  function resetResult() {
    cancel();
    setRun(null);
    setComparison(null);
    setMessage("");
  }
  useEffect(() => {
    const clear = () => {
      generation.current++;
      active.current?.abort();
      setHistory(null);
      setRun(null);
      setComparison(null);
      setLeft("");
      setRight("");
      setOrigin("");
      setMessage("权限上下文已清除，请重新查询。");
      setBusy(false);
    };
    const unsubscribe = subscribeSecurity(clear);
    return () => {
      unsubscribe();
      generation.current++;
      active.current?.abort();
    };
  }, []);
  async function act<T>(work: (signal: AbortSignal) => Promise<T>, accept: (value: T) => void) {
    cancel();
    const id = ++generation.current;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setMessage("");
    try {
      const value = await work(controller.signal);
      if (!controller.signal.aborted && id === generation.current) accept(value);
    } catch (error) {
      if (!controller.signal.aborted && id === generation.current) {
        if (error instanceof DashboardError && [403, 409].includes(error.status)) {
          cancel();
          setHistory(null);
          setRun(null);
          setComparison(null);
          setLeft("");
          setRight("");
        }
        setMessage(safeError(error));
      }
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }
  function refresh(offset = 0) {
    resetResult();
    setLeft("");
    setRight("");
    void act(
      (s) =>
        request(PATH, rollingEnvelope(rollingHistory), s, {
          offset,
          limit: 20,
          ...(baseFilter ? { base_id: baseFilter } : {}),
          ...(seasonFilter ? { target_season: seasonFilter } : {}),
          ...(originFilter ? { origin_date: originFilter } : {}),
        }),
      (v) => {
        if (
          v.data.items.some(
            (r) =>
              (baseFilter && r.base_id !== baseFilter) ||
              (seasonFilter && r.target_season !== seasonFilter) ||
              (originFilter && r.origin_date !== originFilter),
          )
        ) {
          setMessage("历史查询范围不匹配，已拒绝展示。");
          return;
        }
        setHistory(v.data);
        setResourceIndex(0);
        setSnapshotIndex(0);
        setModelIndex(0);
        setModeIndex(0);
      },
    );
  }
  function generate() {
    const resource = history?.resources[resourceIndex];
    if (!resource || !origin || !cutoff) return;
    resetResult();
    const body = {
      base_id: resource.base_id,
      target_season: resource.target_season,
      origin_date: origin,
      origin_cutoff_at: `${origin}T${cutoff}:00+08:00`,
      area_authority_reference: resource.area_authority_reference,
      observation_snapshot_reference: resource.observation_snapshot_references[snapshotIndex],
      frozen_model_artifact_reference: resource.frozen_model_artifact_references[modelIndex],
      execution_mode: resource.execution_modes[modeIndex],
    };
    void act(
      (s) => request(PATH, rollingEnvelope(rollingRun), s, undefined, body),
      (v) => {
        if (
          Object.entries(body).some(
            ([k, value]) => v.data.input.issue[k as keyof typeof v.data.input.issue] !== value,
          )
        ) {
          setMessage("响应输入不匹配，已拒绝展示。");
          return;
        }
        setRun(v.data);
        setMessage("研究预测已保存。请刷新历史列表以比较。");
      },
    );
  }
  function selectRun(id: number, hash: string) {
    resetResult();
    void act(
      (s) => request(`${PATH}/${id}`, rollingEnvelope(rollingRun), s),
      (v) => {
        if (v.data.run_id !== id || v.data.result_hash !== hash) {
          setMessage("记录身份已变化，已拒绝展示。");
          return;
        }
        setRun(v.data);
      },
    );
  }
  function compare() {
    resetResult();
    void act(
      (s) =>
        request(`${PATH}/compare`, rollingEnvelope(rollingComparison), s, {
          left_run_id: left,
          right_run_id: right,
        }),
      (v) => {
        if (String(v.data.left_run) !== left || String(v.data.right_run) !== right) {
          setMessage("比较身份不匹配。");
          return;
        }
        setComparison(v.data);
      },
    );
  }
  return (
    <Panel
      className="d-rolling-shadow"
      title="滚动预测 · 研究影子"
      note="独立于正式预测选择；不代表模型晋级或生产精度"
    >
      <p>
        只读取明确授权的观测快照。D 当天不进入采收进度，目标为 D+1…D+15。当前真实产季数据未授权。
      </p>
      <fieldset>
        <legend>研究历史筛选（精确身份，可留空）</legend>
        <label>
          筛选基地 ID{" "}
          <input
            maxLength={200}
            value={baseFilter}
            onChange={(e) => {
              resetResult();
              setBaseFilter(e.target.value);
            }}
          />
        </label>
        <label>
          筛选产季{" "}
          <input
            placeholder="2026-2027"
            maxLength={9}
            value={seasonFilter}
            onChange={(e) => {
              resetResult();
              setSeasonFilter(e.target.value);
            }}
          />
        </label>
        <label>
          筛选 Origin{" "}
          <input
            type="date"
            value={originFilter}
            onChange={(e) => {
              resetResult();
              setOriginFilter(e.target.value);
            }}
          />
        </label>
      </fieldset>
      <div className="d-actions">
        <button onClick={() => refresh()}>查询研究预测</button>
        <button disabled={!busy} onClick={cancel}>
          取消研究请求
        </button>
      </div>
      {busy && <p role="status">正在核验并读取研究数据…</p>}
      {message && <p role="status">{message}</p>}
      {history && (
        <>
          <fieldset>
            <legend>手动生成（仅服务器登记范围）</legend>
            <label>
              研究基地{" "}
              <select
                value={resourceIndex}
                onChange={(e) => {
                  resetResult();
                  setResourceIndex(Number(e.target.value));
                  setSnapshotIndex(0);
                  setModelIndex(0);
                  setModeIndex(0);
                }}
              >
                {history.resources.map((r, i) => (
                  <option value={i} key={r.base_id + r.target_season + r.area_authority_reference}>
                    {r.base_id} · {r.target_season}
                  </option>
                ))}
              </select>
            </label>
            <label>
              观测快照{" "}
              <select
                value={snapshotIndex}
                onChange={(e) => {
                  resetResult();
                  setSnapshotIndex(Number(e.target.value));
                }}
              >
                {history.resources[resourceIndex]?.observation_snapshot_references.map((ref, i) => (
                  <option value={i} key={ref}>
                    {ref}
                  </option>
                ))}
              </select>
            </label>
            <label>
              冻结模型{" "}
              <select
                value={modelIndex}
                onChange={(e) => {
                  resetResult();
                  setModelIndex(Number(e.target.value));
                }}
              >
                {history.resources[resourceIndex]?.frozen_model_artifact_references.map(
                  (ref, i) => (
                    <option value={i} key={ref}>
                      {ref}
                    </option>
                  ),
                )}
              </select>
            </label>
            <label>
              执行性质{" "}
              <select
                value={modeIndex}
                onChange={(e) => {
                  resetResult();
                  setModeIndex(Number(e.target.value));
                }}
              >
                {history.resources[resourceIndex]?.execution_modes.map((mode, i) => (
                  <option value={i} key={mode}>
                    {mode}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Origin 日期{" "}
              <input
                type="date"
                value={origin}
                onChange={(e) => {
                  resetResult();
                  setOrigin(e.target.value);
                }}
              />
            </label>
            <label>
              截止时间（上海）{" "}
              <input
                type="time"
                value={cutoff}
                onChange={(e) => {
                  resetResult();
                  setCutoff(e.target.value);
                }}
              />
            </label>
            <button disabled={busy || !origin || !history.resources.length} onClick={generate}>
              生成并保存研究预测
            </button>
          </fieldset>
          <div className="d-table-wrap">
            <table>
              <caption>授权研究历史 · 第 {history.offset / history.limit + 1} 页</caption>
              <thead>
                <tr>
                  <th>记录</th>
                  <th>基地 / 产季</th>
                  <th>Origin</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((r) => (
                  <tr key={r.run_id}>
                    <td>{r.run_id}</td>
                    <td>
                      {r.base_id} / {r.target_season}
                    </td>
                    <td>{r.origin_date}</td>
                    <td>{r.status}</td>
                    <td>
                      <button onClick={() => selectRun(r.run_id, r.result_hash)}>
                        读取研究记录 {r.run_id}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="d-actions">
            <button
              disabled={!history.offset || busy}
              onClick={() => refresh(Math.max(0, history.offset - 20))}
            >
              上一页
            </button>
            <button
              disabled={history.items.length < 20 || busy}
              onClick={() => refresh(history.offset + 20)}
            >
              下一页
            </button>
          </div>
          <label>
            比较起点{" "}
            <select
              value={left}
              onChange={(e) => {
                resetResult();
                setLeft(e.target.value);
              }}
            >
              <option value="">请选择</option>
              {history.items.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id} · {r.origin_date}
                </option>
              ))}
            </select>
          </label>
          <label>
            比较终点{" "}
            <select
              value={right}
              onChange={(e) => {
                resetResult();
                setRight(e.target.value);
              }}
            >
              <option value="">请选择</option>
              {history.items.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id} · {r.origin_date}
                </option>
              ))}
            </select>
          </label>
          <button disabled={!left || !right || left === right || busy} onClick={compare}>
            比较两个研究 Origin
          </button>
        </>
      )}
      {run && (
        <section aria-label="滚动预测结果">
          <h3>
            记录 {run.run_id} · {run.base_id} · {run.origin_date}
          </h3>
          <p>
            特征观测口径：
            {run.result.feature_observation_quantity_basis ??
              run.result.feature_snapshot.quantity_basis ??
              "未证明"}{" "}
            · {run.result.feature_snapshot.visibility} · issued_at：未正式发行 · Strict PIT=false
            {" · 观测完整性："}
            {run.result.feature_snapshot.complete ? "完整" : "不完整"}
          </p>
          <details style={{ overflowWrap: "anywhere" }}>
            <summary>来源身份</summary>
            <p>
              观测 {run.input.issue.observation_snapshot_reference} · 面积{" "}
              {run.input.issue.area_authority_reference} · 模型{" "}
              {run.input.issue.frozen_model_artifact_reference}
            </p>
            <p className="d-hash">
              Input {run.input_hash}
              <br />
              Result {run.result_hash}
              <br />
              Feature {run.result.feature_snapshot.feature_hash}
            </p>
          </details>
          {Object.entries(run.result.models).map(([name, model]) => (
            <section key={name}>
              <h4>
                {name} · {model.model_id} · {model.status}
              </h4>
              <p style={{ overflowWrap: "anywhere" }}>冻结参数 {model.model_artifact_hash}</p>
              <p>
                训练目标口径：{model.model_training_target_quantity_basis ?? "未证明"} ·{" "}
                预测目标口径：{model.forecast_target_quantity_basis ?? "未证明"} ·{" "}
                评价标签口径：未评分 · 模型来源：{model.model_provenance ?? "未证明"}
              </p>
              {model.model_provenance === "REAL_FROZEN_S6" && (
                <p>
                  CROSS_SOURCE_TARGET_BASIS_UNVERIFIED：入库重量训练目标不等于已验证的田间采收量预测。
                </p>
              )}
              {model.status === "NOT_COMPUTABLE" ? (
                <p role="status">不能计算：{model.blocker_reason?.join("；")}</p>
              ) : (
                <>
                  <p>
                    H7：{model.H7?.forecast_total_kg} kg · H15：{model.H15?.forecast_total_kg} kg
                  </p>
                  <p>
                    H15 单日峰：{model.H15?.single_day_peak_date} / {model.H15?.single_day_peak_kg}{" "}
                    kg；窗口内连续七日峰：{model.H15?.rolling_7day_peak_start} 至{" "}
                    {model.H15?.rolling_7day_peak_end} /{" "}
                    {model.H15?.rolling_7day_peak_cumulative_kg} kg
                  </p>
                  <Curve rows={model.daily_forecast_kg} model={name} />
                  <div className="d-table-wrap">
                    <table>
                      <caption>{name} 逐日预测（kg，服务器原值）</caption>
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>预测 kg</th>
                        </tr>
                      </thead>
                      <tbody>
                        {model.daily_forecast_kg.map((d) => (
                          <tr key={d.date}>
                            <td>{d.date}</td>
                            <td>{d.kg}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </section>
          ))}
        </section>
      )}
      {comparison && (
        <section aria-label="研究 Origin 对比">
          <h3>
            {comparison.left_origin} → {comparison.right_origin}
          </h3>
          <p>不同窗口总量差不是相同日期预测修正；两者分别列示。</p>
          {Object.entries(comparison.models).map(([name, value]) => (
            <section key={name}>
              <h4>
                {name} · {value.status}
              </h4>
              {value.status === "COMPARABLE" ? (
                <>
                  {Object.entries(value.windows).map(([w, v]) => (
                    <p key={w}>
                      {w} 不同窗口总量变化：{v.total_delta_kg} kg；单日峰移动{" "}
                      {v.single_peak_date_delta_days} 日，峰量变化 {v.single_peak_kg_delta}{" "}
                      kg；七日峰起点移动 {v.rolling7_start_delta_days} 日，累计变化{" "}
                      {v.rolling7_kg_delta} kg。
                    </p>
                  ))}
                  <div className="d-table-wrap">
                    <table>
                      <caption>{name} 共同目标日期上的逐日变化</caption>
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>后者 − 前者 kg</th>
                        </tr>
                      </thead>
                      <tbody>
                        {value.common_target_daily_delta_kg?.map((r) => (
                          <tr key={r.date}>
                            <td>{r.date}</td>
                            <td>{r.kg}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <p>不能比较：{value.reasons.join("；")}</p>
              )}
            </section>
          ))}
        </section>
      )}
    </Panel>
  );
}
