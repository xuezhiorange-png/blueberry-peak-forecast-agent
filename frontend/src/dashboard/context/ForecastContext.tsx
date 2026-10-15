import {
  createContext,
  useContext,
  useState,
  useRef,
  useEffect,
  type ReactNode,
  type RefObject,
} from "react";
import { subscribeSecurity } from "../api/security";
import type { ForecastReadQuery, ReadResponse, CurveData } from "../schemas/contracts";

export type VerifiedForecast = {
  query: ForecastReadQuery;
  curve: ReadResponse<CurveData>;
  key: string;
  entityName?: string;
  handoff?: { token: string; expiresAt: number };
};
const Context = createContext<{
  verified: VerifiedForecast | null;
  commit: (v: VerifiedForecast) => void;
  selectedDate: string | null;
  selectDate: (v: string | null) => void;
  openSelector: () => void;
  selectorOpen: boolean;
  closeSelector: () => void;
  leaveGuard: RefObject<(() => boolean) | null>;
  notice: string;
} | null>(null);
export function ForecastProvider({ children }: { children: ReactNode }) {
  const [verified, setVerified] = useState<VerifiedForecast | null>(null);
  const [selectedDate, selectDate] = useState<string | null>(null);
  const [selectorOpen, setOpen] = useState(false);
  const leaveGuard = useRef<(() => boolean) | null>(null);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (revision > 0)
      queueMicrotask(() =>
        document.querySelector<HTMLButtonElement>("[data-open-saved-run]")?.focus(),
      );
  }, [revision]);
  useEffect(
    () =>
      subscribeSecurity(() => {
        setVerified(null);
        selectDate(null);
        setOpen(false);
        leaveGuard.current = null;
        setRevision((v) => v + 1);
        setNotice("权限或来源已变化，旧结果已清除，请重新选择已保存预测。");
      }),
    [],
  );
  useEffect(() => {
    if (!verified?.handoff) return;
    const timer = window.setTimeout(
      () => {
        setVerified(null);
        selectDate(null);
        leaveGuard.current = null;
        setRevision((v) => v + 1);
        setNotice("选择交接已到期，请重新核验记录。旧结果已清除。");
      },
      Math.max(0, verified.handoff.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [verified]);
  return (
    <Context.Provider
      value={{
        verified,
        commit: (v) => {
          if (leaveGuard.current && !leaveGuard.current()) return;
          selectDate(null);
          setVerified(v);
          setNotice("");
          setOpen(false);
        },
        selectedDate,
        selectDate,
        selectorOpen,
        openSelector: () => setOpen(true),
        closeSelector: () => setOpen(false),
        leaveGuard,
        notice,
      }}
    >
      <div key={revision}>{children}</div>
    </Context.Provider>
  );
}
export function useForecast() {
  const value = useContext(Context);
  if (!value) throw new Error("Dashboard context missing");
  return value;
}
