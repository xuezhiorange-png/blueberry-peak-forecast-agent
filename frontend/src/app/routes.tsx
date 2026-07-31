import { Navigate, Route, Routes } from "react-router";
import { ForecastPage } from "../pages/ForecastPage";
import { NotFoundState } from "../pages/NotFoundState";
import { QualityPage } from "../pages/QualityPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/trial/forecast" element={<ForecastPage />} />
      <Route path="/trial/quality" element={<QualityPage />} />
      <Route path="/" element={<Navigate to="/trial/forecast" replace />} />
      <Route path="*" element={<NotFoundState />} />
    </Routes>
  );
}
