import { createContext, useContext, useState, useRef, type ReactNode, type RefObject } from "react";
import type { ForecastReadQuery, ReadResponse, CurveData } from "../schemas/contracts";

export type VerifiedForecast = {
  query: ForecastReadQuery;
  curve: ReadResponse<CurveData>;
  key: string;
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
} | null>(null);
export function ForecastProvider({ children }: { children: ReactNode }) {
  const [verified, setVerified] = useState<VerifiedForecast | null>(null);
  const [selectedDate, selectDate] = useState<string | null>(null);
  const [selectorOpen, setOpen] = useState(false);
  const leaveGuard = useRef<(() => boolean) | null>(null);
  return (
    <Context.Provider
      value={{
        verified,
        commit: (v) => {
          if (leaveGuard.current && !leaveGuard.current()) return;
          selectDate(null);
          setVerified(v);
          setOpen(false);
        },
        selectedDate,
        selectDate,
        selectorOpen,
        openSelector: () => setOpen(true),
        closeSelector: () => setOpen(false),
        leaveGuard,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useForecast() {
  const value = useContext(Context);
  if (!value) throw new Error("Dashboard context missing");
  return value;
}
