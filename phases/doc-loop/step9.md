# Step 9: doc-buttons-ui

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 프론트엔드 계약 + 원칙 7(토큰 4종 세트 — 이 step은 토큰 변경 없음
  이므로 절차 미발생)
- `/docs/UI_GUIDE.md` — 스타일 규약(기존 배지·스타일 패턴)
- `/frontend/src/features/projects/views/ProjectsPage.tsx` — `ProjectRow`(원본 기준
  197-235행). 카드 전체가 `<button class="project-row">`이고 삭제 버튼
  `.project-del`이 **형제 요소**로 배치된 실존 구조
- `/frontend/src/features/projects/viewmodels/`(프로젝트 목록 훅) — docloops 데이터
  흐름
- `/frontend/src/shared/styles/` — 기존 배지·segment 스타일 (`.plan-seg` 패턴)
- `phases/doc-loop/step7-output.json`, `step8-output.json` — 계약 타입·라우트·훅
  시그니처 요약

step 8에서 만든 `DocSlug` 상수·doc 라우트 형식·ProjectPage 칩을 이어받아 작업한다.

## 작업

프로젝트 카드에 문서 버튼 3종을 추가한다. 기능 배경: 카드 하단에 제안서·
UI·UX설계서·개발설계서 버튼이 있고, 상태(locked/active/done)에 따라 동작이
달라진다.

### 1. ProjectRow — 문서 버튼 행

- `ProjectRow`는 카드 전체가 하나의 `<button>`이므로 버튼 안에 버튼을 넣으면
  불법 중첩(HTML 위반 + 클릭 버블링) — 문서 버튼들은 `.project-del`과 같은
  **형제 요소 컨테이너**로 배치해야 한다 (`.project-docs` 행).
- `p.docloops`가 빈 배열이거나 없으면(레거시 프로젝트) 버튼 행을 렌더링하지 않는다
  — 기존 카드 외형 무손상.
- 버튼 3종 상태 렌더링 (이미지·아이콘·텍스트는 기존 카드 아이콘 세트 재활용):
  - `locked`: `disabled` + `title="{label} — 이전 문서의 plan 승인 후 활성화"`
    클릭 불가. 시각적으로 흐리게(기존 disabled 패턴).
  - `active`: 클릭 → `#/projects/{pid}/{slug}/interview` 이동 (문서 인터뷰 진입).
  - `done`: 상태 표시(완료 아이콘 또는 배지) + 클릭 →
    `#/projects/{pid}/{slug}/plan` (plan 탭). done도 재작업 가능함을 tooltip으로
    안내.
- 버튼 라벨: `DocLoopOut.label` 필드(제안서·UI·UX설계서·개발설계서) 그대로 —
  프론트에서 어휘를 하드코딩하지 않는다.
- 문서 버튼 클릭은 카드 자체(전체 영역) 클릭 핸들러를 발동시켜서는 안 된다 —
  형제 요소 배치이므로 자연히 분리되지만, 이벤트 버블링으로 카드 네비게이션이
  트리거되지 않는지 확인한다.
- `plan_version`(최신 세대)은 버튼에 표시해도 좋다(선택) — 표시 시 "v{plan_version}"
  축약.

### 2. 스타일 — `/frontend/src/shared/styles/`

- 디자인 토큰(색·폰트·여백) 변경 및 신규 토큰 추가 **없음** — 기존 토큰만 소비.
  이유: 원칙 7의 4종 세트 절차를 발동시키지 않기 위함이며, 이 기능은 토큰 수준의
  새 비주얼 언어를 요구하지 않는다.
- 기존 배지/segment 스타일 클래스 패턴을 따라 `.project-doc-btn` 계열 클래스를
  추가한다 (locked/active/done 3변형 — 다크·라이트 테마 모두에서 점검).
- 반응형: 카드 폭이 좁아져도 버튼 행이 wrap되거나 수평 스크롤 없이 수용돼야 한다
  (기존 카드 grid 규약 준수).

### 3. 이스케이프 해치 — 레거시 프로젝트를 문서 루프로 시작할 수 없음을 명시

- docloops=[] 프로젝트 카드에 안내는 하지 않는다(기존 UI 유지, 이관은 범위 밖).
- 다만 문서 루프 UI가 보이는 프로젝트에서 레거시 plan 탭(doc 미지정 라우트)으로
  직접 진입하면 step 8의 리다이렉트가 처리한다 — 이 step에서 추가 작업 없음.

### 4. 수동 스모크 확인

개발 서버 2개(backend 8000 + frontend 5173) 기동 후 브라우저 수동 확인:

1. 신규 프로젝트 생성 → 카드에 proposal(active)·uiux-design(locked)·
   dev-design(locked) 버튼.
2. proposal 버튼 클릭 → `#/projects/{pid}/proposal/interview` 진입.
3. 기존 프로젝트(레거시) → 버튼 행 부재, 기존 카드와 동일.

(실제 LLM을 부르는 e2e-smoke.mjs는 이 step의 AC 대상이 아니다 — 수동 확인은
시각 검증만으로 충분하고, 상태 전이의 계약 검증은 백엔드 테스트가 담당했다.)

## Acceptance Criteria

```powershell
npm run build    # frontend/에서 — tsc --noEmit 포함
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - 버튼 중첩(카드 button 안에 button)이 없는가? — HTML 유효성·이벤트 정합 둘 다.
   - 토큰 4종 세트 절차가 미발생인가? (theme.py·빌더 fixture·tokens.css 무수정 확인)
   - 라벨 어휘를 프론트 하드코딩하지 않았는가? (백엔드 label 필드 사용)
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — UI 완성·수동 스모크 결과).

## 금지사항

- 카드 `<button class="project-row">` 내부에 문서 버튼을 중첩하는 것 금지 — 이유:
  HTML 인터랙티브 요소 중첩 불법 + 카드 전체 클릭 핸들러 버블링 버그.
- 디자인 토큰 추가·변경 금지 — 이유: 원칙 7의 4종 세트 절차(theme.py·렌더러·fixture·
  tokens.css 동시 수정)를 유발하며 본 기능에 필요 없다.
- docloops 어휘(한글 라벨)를 프론트에 하드코딩하는 것 금지 — 이유: SSOT는 백엔드
  DOC_KINDS이며 응답 label 필드가 계약이다.
- `visual-smoke.mjs`·`e2e-smoke.mjs`를 AC로 편입하는 것 금지 — 이유: e2e는 실제
  LLM이 필요한 수동 스크립트이고 커밋 대상이 아니다(visual-smoke는 임시 리스타일
  확인용).
- 기존 테스트·기존 카드(레거시 프로젝트) 렌더링을 깨뜨리지 마라.