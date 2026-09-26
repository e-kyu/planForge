# frontend/ 개발 가이드

> **공통 계약은 저장소 루트의 `../CLAUDE.md`를 참조** — 설계 원칙(SSOT·디자인 토큰
> 4종 세트·수치 무결성)과 전체 파이프라인 맥락은 이 파일에서 반복하지 않는다.
> 충돌 시 루트 CLAUDE.md가 우선한다.

## 구조 (feature-MVVM — 가이드 §2)

- `src/features/` — 화면별 feature 7종: `projects` · `project` · `sources` ·
  `interview` · `plan` · `review` · `outputs`.
  각 feature는 `models/`(API 호출) · `viewmodels/`(상태·로직 훅) · `views/`(표현 전용
  컴포넌트)로 구성. 새 feature는 기존 것을 템플릿으로 복제.
- `src/shared/components/` — CodeMirror 에디터 · 마크다운 미리보기 · 공통 UI.
- `src/shared/lib/` — 라우터 · 에러 문자열 변환.
- `src/api/` — API 클라이언트.

## 규칙

- **View에서 fetch·서버 데이터 로직 금지** — 반드시 viewmodel 훅 경유 (가이드 §4.3).
- 상태 관리는 TanStack Query, 스타일은 자체 CSS.
- `src/api/types.gen.ts`는 **자동 생성물** — 손으로 편집하지 않는다. 갱신은 backend에서
  `python scripts/export_openapi.py` 실행 후 `npm run gen:types`.
- 디자인 토큰은 `tokens.css`(미러) — 토큰 변경 시 루트 원칙 7의 4종 세트 동시 점검
  (`docs/token-checklist.md` 절차).

## 실행·명령

- `npm run dev` — dev 서버(5173, /api 프록시 → backend 8000).
- `npm run build` — `tsc --noEmit` 포함 (타입 체크·빌드; lint 설정은 없음).
- `npm run gen:types` — OpenAPI 타입 재생성.

## e2e 스모크

- 양쪽 dev 서버 기동(backend 8000 + frontend 5173) 후 `node e2e-smoke.mjs`.
  실제 LLM을 호출하는 **수동 검증 스크립트(커밋 대상 아님)**, 스크린샷은 `.e2e-shots/`에 쌓임.
- `visual-smoke.mjs`는 임시 리스타일 확인용.