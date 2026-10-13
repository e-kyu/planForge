# Step 1: plan-doc-guard — write_plan 문서 정합 가드

## 배경 (자기완결 — 외부 대화 참조 금지)

feat-doc-loop 이후 인터뷰 세션은 `doc_slug`로 문서가 고정돼 있고(프로젝트 카드 문서
버튼 진입), 이전 step(doc-context)에서 `agent.py _turn_context()`가
`### 이번 인터뷰 문서` 블록으로 세션 문서 정체성(라벨)을 매턴 주입하기 시작했다.

그러나 주입만으로는 잠금이 부족하다 — doc 세션(예: proposal)에서 LLM이 plan 메타를
다른 문서(`- 산출 문서: 개발설계서`)로 쓰거나 쉼표 나열을 써도, 파서는 태그가 없으면
수용한다(누락 시기 파서 default는 `["제안서"]`). doc 세션의 plan 행 doc_slug와
markdown의 문서가 어긋나면 derive가 다른 문서 기준으로 슬라이드를 걸러낸다.

이 step은 `write_plan` 도구에 앱 계층 정합 가드를 추가한다. **파서(`planforge/`)
는 수정하지 않는다** — LLM 대면 ERROR 피드백은 인터뷰 앱 계층 소관이라, 기존
PLAN_BULLET_CHEATSHEET 치료안과 동일한 철학의 대응이다.

## 읽어야 할 파일

- `/CLAUDE.md`
- `/docs/INTERVIEW-TURN-CONTRACT.md`
- `/backend/app/modules/interview/application/agent.py` — 주 대상
  (이전 step doc-context에서 `_turn_context()`에 `### 이번 인터뷰 문서` 주입 블록이
  이미 추가돼 있다 — 읽고 일관성을 유지하라)
- `/backend/app/modules/docloops/facade.py` — `doc_label`
- `/tests/test_interview_api.py` — 기존 가드·에러 피드백 테스트 스타일
- `/tests/test_docloops_api.py` — DocLoop 행 세팅 패턴 참조

## 작업

### 1. `agent.py` `_write_plan()` — 정합 가드

배치: parse·핵심 메시지 검증 뒤, **골격 검증(validate_skeleton) 루프보다 앞**.
이유: 잘못된 문서 메타 기준으로 골격 오류(문서별 표지·목차 미달 등)를 내기 전에
문서 자체를 바로잡아 재시도 1회 수렴을 노린다.

인터페이스 수준 로직 (구현은 기존 코드 스타일에 맞게):

```python
if self.sess.doc_slug:
    expected = [docloops.doc_label(self.sess.doc_slug)]
    if plan.docs != expected:
        return ("ERROR: 이 세션의 산출 문서는 '{expected[0]}' 단독이다 — 메타에 "
                "`- 산출 문서: {expected[0]}`을 쓰고 슬라이드 [문서: ...] 태그는 쓰지 "
                "않은 뒤 write_plan을 다시 호출하라")
```

- 레거시 세션(`doc_slug is None`)에는 가드를 적용하지 않는다 — 기존 2문서
  plan(sample 레거시 플로우)의 write_plan 경로가 그대로 통과해야 한다.
- 메시지에 재시도 치료안(what to write)이 포함돼 LLM이 한 번에 고치는 형태로 쓴다 —
  파서 원문을 건드리지 않는다.

### 2. `tests/test_interview_api.py` — 가드 회귀 테스트

- proposal 세션(`json={"doc_slug": "proposal"}` — 생성 직후 active, 게이트 통과)을
  만들고, 개발설계서 메타 plan markdown(파일에 이미 있는 `DESIGN_PLAN_MARKDOWN` =
  `- 산출 문서: 개발설계서`)으로 kick 이후 write_plan을 도달시킨다.
- assert: 도구 결과에 `"ERROR: 이 세션의 산출 문서는 '제안서' 단독이다"`가 있다 —
  세션은 FAILED가 아니라 재시도 가능 상태로 유지된다(기존 plan_fixes 재시도 루프
  참여 잠금).
- 같은 턴에서 제안서 메타 markdown으로 재호출하면 OK(`plan_draft` 이벤트)인 것도
  잠근다 — 기존 PROPOSAL_TURNS·DESIGN_TURNS fake 스크립트 패턴을 따르되,
  잘못된 호출→올바른 재호출 쌍을 이 테스트 안에서 스크립트한다.
- 세션 생성·게이트 처리는 `tests/test_docloops_api.py`와 이 파일의 기존 fixture를
  재사용하라.

## Acceptance Criteria

```bash
python -m pytest tests/test_interview_api.py tests/test_agents_tools.py tests/test_docloops_api.py -q   # 저장소 루트에서
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - `docloops` facade 경유만 (`doc_label`) — 모델·DOC_KINDS 직접 import 금지.
   - `planforge/plan/parser.py`(top parse·핵심 메시지 검증)를 수정하지 않았는가? — 가드는 agent.py 앱 계층 피드백이다.
   - `backend/app/agents/tools.py` 무수정 — 이유: 도구 스키마 변경이 아니라 write_plan
     실행 결과(피드백)다.
3. `phases/remove-doc-question/index.json`의 step 1 status를 업데이트한다
   (성공 → `"completed"` + `"summary"`에 가드 배치·회귀 테스트 한 줄).

## 금지사항

- `interview.md`·`docs/INTERVIEW-TURN-CONTRACT.md`를 수정하지 마라 — 이유: 프롬프트
  재작성과 계약 기록은 step 2가 계약 4세트 동시 점검으로 마무리한다.
- `planforge/` 파서·빌더를 수정하지 마라 — 이유: ADR 결정 22상 무수정 영역.
- 가드를 골격 검증 뒤로 옮기지 마라 — 이유: 잘못된 문서 메타 기준 골격 오류를 내기
  전에 문서 정합을 먼저 잠가 재시도 1회 수렴이
  이 step의 설계 의도다 (골격 검증 순서는 기존 그대로).
- 워크스페이스 파생물을 직접 쓰지 마라 (SSOT 가드훅 차단 정상).
- 기존 테스트를 깨뜨리지 마라.