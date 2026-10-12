# Step 10: docs-adr

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 설계 원칙 계약 + 문서 갱신 규약
- `/docs/ADR.md` — 결정·편차 기록 형식 (새 항목 추가 위치·형식)
- `/backend/CLAUDE.md` — 모듈 목록 표기 (7종 표기 vs 실제 8개+docloops 불일치 정정)
- `/phases/doc-loop/index.json` — 전 step summary (기록할 결정·산출의 목록)
- `/docs/ARCHITECTURE.md` — 모듈 구조 기술 (docloops 모듈 언급 필요 여부 판단)
- `phases/doc-loop/step{0..9}-output.json` — 각 step의 핵심 결정 요약

## 작업

기능 구현 종료 선언 단계다. 새 코드는 쓰지 않고, 남은 것은 문서화·전체 회귀·
미반영 사실 정리다.

### 1. docs/ADR.md — 결정·편차 항목 추가

아래 결정들을 기존 형식에 맞춰 새 항목으로 기록한다 (내용은 각 step summary에서
근거를 확인해 압축):

1. **신규 리프 모듈 `docloops`** — facts 템플릿 복제. 의존성 방향
   projects/plans/interview → docloops, 도큰은 어떤 facade도 import하지 않음
   (모듈 경계 계약 유지).
2. **문서 정체성 = 영문 슬러그 3종** (`proposal`·`uiux-design`·`dev-design` —
   DOC_KINDS 매핑 SSOT). 계획 본문 한글 어휘(`- 산출 문서:`·`[문서: ...]` 태그)는
   유지 → `planforge/**` 파서·필터·빌더 무수정.
3. **레이아웃 권위 = DB 행 (doc_loops)** — 기존 프로젝트(행 없음)는 flat 구조로
   계속 동작. 이관(마이그레이션)은 별도 이터레이션 (미확정 유지).
4. **문서 루프 상태머신 = 단방향 래치** `locked → active → done` — 승인 훅
   `on_plan_approved`은 plans 승인 트랜잭션 내(커밋 전) 호출. done 문서 재작업
   허용, 재잠금은 (미확정).
5. **승인 전이 문서 스코프 좁힘** — "프로젝트당 승인본 1개"를 "문서당 승인본 1개"로
   좁힘. `doc_slug=None`(레거시)은 `is_(None)` 명시 분기로 기존 불변식 유지.
6. **version_no 프로젝트 전체 단조 유지** (`uq_project_planver` 무변경) — 문서별
   재채번은 (미확정)로 Phase 2 후보.
7. **facts는 프로젝트 공유, 미러만 문서별** — compact 루트 미러 유지 (문서별 compact
   미러는 Phase 2 (미확정)).
8. **`Build.file_path`의 "output/..." 상대 형식은 유지하되 ws 루트가 문서별로
   결정된다** — 파일 경로 계약 형식 보존, 경로 결정 권위만 `doc_ws_root`로 이동.

### 2. backend/CLAUDE.md — 모듈 목록 정정

- "모듈 7종" 식의 기존 표기를 실제 목록으로 정정한다 (docloops 추가 후
  9종이면 9종 — 실제 `backend/app/modules/` 디렉터리 기준으로 센다). 기존에도
  실제와 불일치가 있었던 경우 이 기회에 맞춘다.
- 기타 docloops 관련 언급이 필요한 계약(테스트 명·명령어)이 있으면 최소 추가.

### 3. docs/ARCHITECTURE.md — 모듈 구조에 docloops 반영

- 모듈 구조 목록에 docloops를 추가하고 의존성 방향을 한 줄로 명시.
- 워크스페이스 구조 기술 중 문서별 레이아웃(`workspaces/{slug}/{doc}/` 4 subdirs)
  부가 — 기존 flat 기술에 "문서 루프 프로젝트" 분기를 함께 표기.

### 4. 전체 회귀

```powershell
# 저장소 루트에서 — 백엔드 전체
python -m pytest -q
# frontend/ 에서
npm run build
```

전부 통과해야 한다. 실패 시 이 step에서 코드를 손대기 전에 원인을 summary에 기록
하고 실패한 원인 step의 범위로 한정해 최소 수정한다(어느 step의 회귀인지 특정).

## Acceptance Criteria

```powershell
python -m pytest -q   # 저장소 루트 — 전체
npm run build         # frontend/ — tsc --noEmit 포함
```

## 검증 절차

1. 위 AC 커맨드를 실행한다 (전체 회귀).
2. ADR 항목이 결정·이유·대안(필요시) 형식으로 기록됐는지 확인.
3. `/phases/doc-loop/index.json`의 해당 step을 업데이트한다 (completed + summary —
   최종. task 자체 완료 판정은 execute.py가 처리한다).

## 금지사항

- 이 step에서 기능 코드를 수정하는 것 금지 — 이유: 회귀 특정을 어렵게 한다. 회귀
  수정이 불가피하면 원인 step 범위로 명시해 한정한다.
- ADR에 (미확정) 항목을 확정으로 기록하는 것 금지 — 이유: 이탈(재잠금·문서별
  재채번·이관·Phase 2 plan 상호 참조)은 여전히 (미확정)이며 후속 인터뷰 대상이다.
- `docs/INTERVIEW-TURN-CONTRACT.md`를 이 step에서 수정하는 것 금지 — 이유: 계약
  4세트는 step 4에서 완료됐다. 누락 발견 시 blocked 이유로 기록하고 사용자 검토를
  요청한다.
- 커밋 대상 아닌 파일(workspaces/·data/ 등 ignored 경로)을 문서·summary에서
  산출물로 선언하지 마라.