// 시각 스모크 — 리스타일 화면 스크린샷 (e2e 본 실행 전 빠른 확인용, 임시 스크립트)
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { resolve } from "path";

const BASE = "http://localhost:5173";
const SHOTS = resolve(import.meta.dirname, "../.e2e-shots/restyle");
mkdirSync(SHOTS, { recursive: true });

const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.screenshot({ path: resolve(SHOTS, "home.png"), fullPage: true });

await page.goto(`${BASE}/#/projects/6/interview`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
// 세션 생성 (kick 없음 — LLM 호출 없음) → 2열 레이아웃 + 팩트 사이드 패널 확인
const createBtn = page.locator("button:has-text('인터뷰 세션 만들기')");
if (await createBtn.count() > 0) {
  await createBtn.click();
  await page.waitForTimeout(1500);
}
await page.screenshot({ path: resolve(SHOTS, "interview.png"), fullPage: true });

for (const tab of ["sources", "plan", "outputs", "review"]) {
  await page.goto(`${BASE}/#/projects/6/${tab}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: resolve(SHOTS, `${tab}.png`), fullPage: true });
}

console.log("콘솔/페이지 에러:", errors.length === 0 ? "없음" : errors);
await browser.close();