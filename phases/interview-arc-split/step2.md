# Step 2: contract-docs

## 읽어야 할 파일

먼저 아래 파일들을 읽고 계약 문서 관례를 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개 + "인터뷰 턴 계약" 규칙(인터뷰 계약 파일 동시 점검 · "하나만 고치는
  PR은 반려") — 이 step에서 한 줄 갱신 대상이기도 하다
- `/docs/INTERVIEW-TURN-CONTRACT.md` — 이 step의 주 대상. "동시 점검 세트 (계약 4종)" 표(:124-133
  부근)·변경 이력 관례(2026-10-04 제안서 아크 고도화 항목·2026-10-13 area 어휘 확장·2026-10-31 본문
  맥락 허용 항목의 서식)·"구조만 잠근다" 원칙
- `/docs/ADR.md` — 결정·편차 기록 서식(이전 프롬프트 고도화·doc-loop 결정 항목 선례)
- `/backend/README.md` — "prompts/interview.md" 언급 위치(:206 부근) 확인용
- `/backend/app/modules/interview/application/prompts/interview.md` — base의 `<!--ARC-->` 마커·아크
  참조 문구 (기록할 사실의 근거)
- `/backend/app/modules/interview/application/agent.py` — `ARC_MARKER`·`ARC_LEGACY_SLUG`·`_arc_section()`
  조립 규약 (step 0에서 만들어진 것 — 그 코드를 읽고 문서에 그대로 기록한다)
- `/phases/interview-arc-split/index.json` — step 0·1의 summary (무엇이 완료됐는지의 기록 근거)

이전 step에서 만들어진 것: step 0 — base+조각 3종 분리·로더 치환·UI·UX설계서 아크 신규 설계·파라미터화
조립 테스트. step 1 — UI·UX설계서 e2e 잠금(fixture `tests/fixtures/plan.interview-uiux.md` + fakes 래퍼 +
`UIUX_TURNS` + `test_interview_uiux_arc_full_flow_to_plan_approval`).

## 작업

목표: 인터뷰 프롬프트 분리 구조를 **계약 문서에 기록**해 이후 PR이 조약을 지키게 한다. 이 step은 문서만
수정하고 코드·테스트는 무변경이다 (이미 step 0-1에서 녹색으로 잠겼다).

### 1. `docs/INTERVIEW-TURN-CONTRACT.md`

- **"동시 점검 세트 (계약 4종)" 표 갱신**: `interview.md` 행을
  `backend/app/modules/interview/application/prompts/interview.md (공통 base) + arc_{proposal,dev-design,uiux-design}.md (아크 조각)`로
  갱신 — "계약 서술의 원문" 역할은 base+조각 세트가 함께 수행함을 명시.
- **신규 결정 항목 추가** (변경 이력·결정 섹션 — 기존 항목 서식을 따른다, 날짜는 실행일 기준):
  - 분리 구조: base=interview.md(행동 규칙·질문 설계 규칙·plan 포맷 공통 규칙·ask_questions 완성 예시·톤),
    조각=arc_{slug}.md 3종(`## 이번 인터뷰 아크` 헤딩 기재, 서사·예시 질문·[문서] 체크리스트·plan 구성
    가이드 소관 — **콘텐츠 규칙 소관이 base→base+조각 세트로 확장**된 것이지 소관이 바뀐 게 아님).
  - 로더 조립 규약: `agent.py` `_system_prompt()`가 base의 `<!--ARC-->` 마커(계약 어휘)를 `arc_{doc_slug}.md`
    치환으로 조립 — slug→파일명이 SSOT이고, `doc_slug=None`(레거시)은 `ARC_LEGACY_SLUG="proposal"` 폴백,
    마커 부재 시 RuntimeError 조기 노출.
  - 점검 결과 기록: `tools.py`는 **점검 후 무수정** — update_checklist area 소프트 어휘·도구 스키마 계약
    무변경 (2026-10-04 제안서 아크 고도화 선례와 동일 기록).
  - 이후 규칙: 아크 콘텐츠(서사·예시 질문·체크리스트 항목·구성 가이드)를 바꾸는 PR은 base·조각·이 문서·
    테스트의 동시 점검 대상이다 — 아크 조각 3종이 계약 4종의 일부임을 명시.
- 신규 항목에 테스트 잠금 근거 기록: `test_system_prompt_carries_arc_sections`(
  3-slug 파라미터화·아크 격리 음성 단언)·`test_interview_uiux_arc_full_flow_to_plan_approval`·
  기존 e2e/레거시 단언 무수정 통과.

### 2. 루트 `CLAUDE.md`

"인터뷰 턴 계약(도구 전용 출력·ask_questions 스키마·검증 재시도)" 단락의 계약 파일 문구에 아크 조각 3종
포함 — 예: "`interview.md` + `arc_{proposal,dev-design,uiux-design}.md` 프롬프트" 로 서술 갱신. 계약 절차
설명 자체("동시 점검·수정 — 하나만 고치는 PR은 반려")는 무변경.

### 3. `backend/README.md`

`prompts/` 경로·interview.md 언급을 분리 구조(base + arc_{doc_slug}.md 조각, 로더가 doc_slug로 조립)로
갱신. 언급이 한 문장 수준이면 그 한 문장만 고친다.

### 4. `docs/ADR.md`

분리 결정을 ADR 서식(배경/결정/결과 선례)으로 1항 추가:
- 배경: 매 세션 아크 1개인데 프롬프트에 3종 아크가 함께 실려 무관 아크 토큰(~35%)이 매 턴 전송됨,
  "한 세션 한 아크" 규칙이 프롬프트 문구로만 방어됨, UI·UX설계서에는 아크가 없었음.
- 결정: 공통 base + 문서별 아크 조각 조립(slug 기반 파일명, `<!--ARC-->` 마커 치환, 레거시 proposal 폴백),
  UI·UX설계서 아크 신규 설계로 3종 완성.
- 결과: 기존 e2e/레거시 단언 무수정 통과(무손실 이동), 차후 4번째 문서 타입은 조각 파일 추가로 확장.

## Acceptance Criteria

```bash
python -m pytest -q    # 저장소 루트 (PYTHONUTF8=1) — 문서 step이지만 전체 회귀를 녹색으로 확인
git status             # workspaces/·sources/·data/·backend/planforge/config.json 등 ignored 경로 미혼입 확인
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 정합 체크리스트:
   - 계약 문서의 동시 점검 표가 실제 파일 구조(interview.md + arc_*.md 3종)와 일치하는가?
   - 기록된 로더 규약(마커·폴백·RuntimeError)이 `agent.py` 실코드와 일치하는가? (코드에서 복사해 쓸 것 —
     문서가 코드를 지어내면 계약 자체가 무효)
   - CLAUDE.md 설계 원칙 8개 위반 없는가?
3. 결과에 따라 `phases/interview-arc-split/index.json`의 step 2를 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "계약 문서 동기화 — INTERVIEW-TURN-CONTRACT.md(동시 점검 4종 표 갱신+아크 조각 분리 결정 기록·tools.py 무수정)+CLAUDE.md·backend/README.md·ADR.md, 전체 pytest 통과"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 코드(backend·packages·frontend)와 테스트를 수정하지 마라. 이유: 기능·잠금은 step 0-1에서 완료됐고 이
  step은 기록 step이다 — 문서 step에서 코드 건드리면 회귀 원인이 분리되지 않는다.
- 계약 문서에 실제 코드와 다른 규약을 쓰지 마라. 이유: `ARC_MARKER`·폴백 slug·RuntimeError 사양은 agent.py
  실코드에서 확인해 기록한다 — 문서-코드 불일치는 계약 위반이다.
- 기존 변경 이력·결정 항목의 서식을 바꾸지 마라. 이유: 이후 대조·회고의 기준인 문서 관례다.