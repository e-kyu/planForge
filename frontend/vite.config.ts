import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 서버는 /api를 FastAPI(backend uvicorn, 기본 8000)로 프록시한다 —
// SSE도 프록시를 통과하므로 버퍼링 방지 설정이 필요하다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // SSE 응답 버퍼링 방지 (ws 미사용 — §3.1 SSE+REST 확정)
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["x-accel-buffering"] = "no";
          });
        },
      },
    },
  },
});