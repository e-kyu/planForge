import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./shared/styles/tokens.css";
import "./shared/styles/base.css";
import "./shared/styles/app.css";
import "./shared/styles/pages.css";
import "./shared/styles/chat.css";
import "./shared/styles/plan.css";
import "./shared/styles/outputs.css";
import "./shared/styles/review.css";
import App from "./App";

/* 서버 상태 전역 기본 — 원본 동작 유지: 재시도 없음, 포커스 리페치 없음. */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);