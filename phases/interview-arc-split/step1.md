# Step 1: uiux-arc-e2e

## 읽어야 할 파일

먼저 아래 파일들을 읽고 시나리오·패턴을 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개 (특히 SSOT·수치 무결성: `(미확정)` 원문 보존)
- `/backend/app/modules/interview/application/prompts/arc_uiux-design.md` — **step 0에서 생성된**
  UI·UX설계서 아크 조각 (체크리스트 6항·plan 구성 가이드가 이 step의 e2e 스크립트·fixture 기준)
- `/tests/test_interview_api.py` — 제안서 아크 e2e(:485-560)와 그 턴 스크립트 PROPOSAL_TURNS(:423-473
  부근), DOC_GUARD_KICK(:780-783 부근) — 이 step의 템플릿
- `/tests/fakes.py` — `FakeStreamLLM` 턴 스크립트 계약(:117-134), plan fixture 래퍼(:108-115)
- `/tests/fixtures/plan.interview-proposal.md` 및 `plan.interview-design.md` — fixture plan 형식 선례
- `/backend/app/modules/interview/application/agent.py` — `_validate_plan_for_session`(:366-373, docs
  단일성 검증)·미러 경로 규칙
- `/packages/planforge-cli/src/planforge/plan/loader.py`(:52-62) — `validate_each_doc`·`filter_slides`-
  골격 검증 (수정 금지)

이전 step(step 0 "arc-split-loader")에서 만들어진 것: `interview.md` 공통 base + 조각 3종 + 로더 치환.
step 0의 UI·UX설계서 체크리스트 항목 6개를 그대로 이 step의 스크립트·fixture에 반영한다.

## 작업

목표: UI·UX설계서 아크의 **e2e 잠금**을 만든다 — doc_slug=`uiux-design` 세션이 아크 조각 아코로
인터뷰를 진행해 `UI·UX설계서` 단독 plan을 만들고, 골격·문서 교차검증·`(미확정)` 원문 보존을 결정론으로
검증한다. 제안서 e2e(`test_interview_proposal_arc_full_flow_to_plan_approval`)와 동일 패턴의 대칭 테스트다.

### 1. fixture `tests/fixtures/plan.interview-uiux.md` (신규)

`plan.interview-proposal.md`의 형식 선례를 따르되, 아래 슬라이드 구성으로 만든다 (파서·골격 규약 통과가
필수 — 표기 규칙은 `arc_uiux-design.md`의 plan 구성 가이드와 `interview.md` plan.md 포맷 규칙 참조):

- `## 메타`: 첫 항목 `- 산출 문서: UI·UX설계서` (단독 — `plan.docs == ["UI·UX설계서"]`여야
  `_validate_plan_for_session`을 통과한다), 목적·청중·예상 분량
- `## 핵심 메시지 (3개)`: 아크 축(사용자·화면 구조 / 사용자 흐름 / UI 디자인 방향·요청)과 1:1 대응
- 슬라이드 목록 (내용 슬라이드는 아크 구성 가이드의 매핑을 그대로 시연한다):
  1. `[유형: 표지]` — 프로젝트명·핵심문장·근거/출처
  2. `[유형: 목차]` — `- 핵심문장: 01 사용자와 화면 구조 / 02 사용자 흐름 / 03 UI 디자인 방향 및 요청 사항`
  3. `[유형: 표]` 대상 사용자·페르소나 — 헤더 `[사용자 유형 | 특징 | 니즈]`, 행 2개
  4. `[유형: 표]` 화면 목록 — 헤더 `[화면 | 목적 | 주요 요소]`, 행 2개
  5. `[유형: 구성]` 정보 구조 — 계층 2개 (계층당 박스 2~3개, 라벨 안에 쉼표 금지)
  6. `[유형: 2단]` 사용자 흐름 — `- 좌 (정상 흐름):` / `- 우 (예외·분기):` 각 행 1-2개
  7. `[유형: 표]` UI 디자인 방향 결정표 — 헤더 `[항목 | 방향 | 이유 | 상태]`, **행 1개의 상태 칸에
     `(미확정)`** (아래 검증 대상)
  8. `[유형: 마무리]` — 핵심문장에 `(미확정)` 확인 계획 포함
- 근거/출처 문자열은 `interview-log [YYYY-MM-DD] 항목 (샘플)` 선례 형식

fixture는 반드시 `tests/fixtures/`에 만든다 — `workspaces/` 아래 쓰면 SSOT 가드 훅이 차단한다.

### 2. `tests/fakes.py` — 래퍼 추가

`plan_interview_proposal_markdown`(:113-115)과 동일 패턴:

```python
def plan_interview_uiux_markdown() -> str:
    """인터뷰 e2e UI·UX설계서 아크 시나리오의 최종 plan (UI·UX설계서 단독 문서)."""
    return _fixture_md("plan.interview-uiux.md")
```

### 3. `tests/test_interview_api.py` — `UIUX_TURNS` + `uiux_kit` + e2e 테스트

- **turn 스크립트 `UIUX_TURNS`**: PROPOSAL_TURNS를 템플릿으로 복제해 UI·UX설계서 시나리오로 교체:
  - 킥 턴 — `update_checklist` 1회 (아키텍처 체크리스트 6항 전부, area=`"UI·UX설계서"`, arc 파일의
    항목 문장을 그대로 사용) + `ask_questions` 1회 (`round_summary: "라운드 1 목표: 사용자·화면 구조
    확정"`, arc 예시 질문 2문항 — 하세요체·배경 문장 규칙·options 2개 이상/allow_free 규칙 통과 필수,
    옵션 유사 나열 줄 없음·300자 이내)
  - 이후 팩트 적립(`save_facts`) → `write_plan` 1회 (markdown = `plan_interview_uiux_markdown()`)
    구성의 턴을 PROPOSAL_TURNS의 완료 흐름 그대로 따른다. 질문 본문·팩트 content에
    "미확정" 답변 → `(미확정)` 팩트 케이스 1개 포함(결정표 (미확정) 행과 짝).
- **fixture `uiux_kit`**: 제안서 e2e의 kit fixture(예: `proposal_kit`)를 복제 — `create_app(
  start_worker=False, llm_overrides=...)` + doc_slug=`uiux-design` 세션 생성 + kick.
- **테스트 `test_interview_uiux_arc_full_flow_to_plan_approval`**: 제안서 e2e와 대칭인 단언:
  1. 첫 fake 호출의 system 프롬프트에 아크 조각 문자열 — `assert "UI·UX설계서 구성 가이드" in ...`,
     `assert "화면 목록·정보 구조" in ...`
  2. 첫 system 프롬프트 음성 — `assert "제안서 구성 가이드" not in ...`,
     `assert "개발설계서 구성 가이드" not in ...` (doc별 조립이 아크를 격리하는 잠금)
  3. 체크리스트 저장 단언 — `s["checklist"]`의 모든 항목 `area == "UI·UX설계서"`
  4. plan 승인 후: draft의 `docs == ["UI·UX설계서"]` (문서 교차검증 통과 잠금)
  5. 미러 경로: plan 마크다운이 워크스페이스에 쓰였음 확인 (제안서 e2e의 미러 검증 패턴 통일)
  6. 결정론 파이프라인 직접 검증: `parse_plan_text` → 슬라이드에 `table`·`arch`·`two-col` 유형이 있고
     `(미확정)` 문자열이 원문 그대로 파생 데이터에 남아 있으며, `validate_skeleton(filter_slides(
     plan.slides, "UI·UX설계서"))` 통과. (제안서 e2e가 이 단계 조립을 어떻게 하고 있는지 그 코드를
     그대로 따른다.)

## Acceptance Criteria

```bash
python -m pytest tests/test_interview_api.py -q        # 저장소 루트 (PYTHONUTF8=1) — 신규 uiux e2e 포함 전부 녹색
python -m pytest -q                                     # 전체 회귀
python -m planforge parse tests/fixtures/plan.interview-uiux.md   # backend/에서 — fixture가 파서를 통과하는지 수동 확인
```

(두 번째 커맨드는 파서 통과 대리 검증용 — pytest 단언으로도 커버되지만 실패 시 분리 원인 파악에 쓴다.)

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - fixture·턴 스크립트가 `arc_uiux-design.md`의 체크리스트 6항·구성 가이드 매핑(표지/표/구성/2단/표/마무리)과
     일치하는가?
   - `(미확정)`이 파생 데이터에 원문으로 보존됨을 단언하는가? (수치 무결성 원칙 3)
   - `tools.py`·`packages/planforge-cli/`·frontend 무수정인가?
3. 결과에 따라 `phases/interview-arc-split/index.json`의 step 1을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "UI·UX설계서 아크 e2e 잠금 — fixture plan.interview-uiux.md(표/구성/2단 골격+미확정 1행)+UIUX_TURNS+uiux_kit+full-flow e2e(아크 격리 음성 단언 포함), 전체 pytest 통과"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `backend/app/agents/tools.py`·`packages/planforge-cli/`·frontend를 수정하지 마라. 이유: 계약 소관이 아닌
  계층이며, 검증이 필요한 부분은 전부 기존 결정론 파이프라인이 이미 잠그고 있다.
- fixture를 `workspaces/` 아래에 만들지 마라. 이유: SSOT 가드 훅(`.claude/hooks/guard_ssot.py`)이 차단한다
  — 테스트 fixture는 `tests/fixtures/` 규약이다.
- fake plan fixture에 슬라이드 유형 7종 외의 유형을 두지 마라. 이유: 파서·골격 검증이 거부하고, 아크 설계
  계약("와이어프레임 유형 없음")을 위반한다.
- step 0에서 만든 아크 조각(arc_*.md)·interview.md base·agent.py를 수정하지 마라. 이유: 조각 콘텐츠는 step 0의
  테스트로 잠겨 있고, 이 step은 테스트·fixture만 추가하며 녹색을 유지해야 한다. (아크 문장·체크리스트 항목
  문구가 스크립트·fixture와 미세하게 맞지 않으면 **쪽에서 조각을 읽어 스크립트가 문장을 따르게 한다** —
  조각을 스크립트에 맞추지 않는다. 단 어떤 수정도 조각에서 잠긴 substring을 제거하면 안 된다.)
- 기존 테스트를 깨뜨리지 마라 — 이 step은 기존 테스트 무수정을 원칙으로 하며 신규 추가만 한다.