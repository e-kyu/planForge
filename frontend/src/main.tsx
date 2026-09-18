import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/app.css";
import "./styles/pages.css";
import "./styles/chat.css";
import "./styles/plan.css";
import "./styles/outputs.css";
import "./styles/review.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);