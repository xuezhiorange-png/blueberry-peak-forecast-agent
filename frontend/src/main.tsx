import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { ProductEntry } from "./dashboard/app/ProductEntry";
import "./app/app.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ProductEntry />
    </BrowserRouter>
  </StrictMode>,
);
