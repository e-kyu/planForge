# Step 8: interview-agent-and-tools

## 읽어야 할 파일

- `/CLAUDE.md` — 원칙 2(LLM/코드 역할 분리)
- `/docs/INTERVIEW-TURN-CONTRACT.md` — 계약 4종 동시 점검 세트
- `/backend/app/modules/interview/application/agent.py` — `_write_plan`(341-393),
  `_turn_context`(147-153), `commit_facts`(413-417)
- `/backend/app/agents/tools.py` — `validate_tool_args`(195-285), 스키마 정의
- `/backend/app/modules/review/application/review_agent.py` — 팩트 라인(71-74)
- Step 5 산출물: `app/shared/factline.py`
- `/tests/test_interview_api.py`, `/tests/test_agents_tools.py`

## 배경

`validate_tool_args`는 91줄의 도구 분기 + 5단 중첩을 갖고, `_write_plan`은 검증·영속·
이벤트를 한 함수에 섞는다. 도구별 검증 함수와 검증/영속 분리로 가독성을 높인다.
**도구 스키마·프롬프트·SSE 이벤트·피드백 문자열은 불변**이다.

## 작업

### 1. `agent.py::_write_plan` 분리

- `_validate_plan_for_session(md) -> tuple[parsed | None, str | None]` 형태(또는 동등):
  - 핵심 메시지 승인 가드.
  - `parse_plan_text` + 기존 `ERROR: plan 포맷 검증 실패 ...` + cheatsheet.
  - doc 세션 문서 정체성 가드(정확한 ERROR 문구).
  - 문서별 골격 검증 루프(정확한 ERROR 문구).
- `_persist_plan(md, parsed)`:
  - `create_generation`, `write_plan_mirror`, phase 변경, `plan_draft` 이벤트,
    `state_event`, 반환 문자열.
- `_write_plan`은 두 함수를 순서대로 호출하는 얇은 함수로 만든다.
- **검증 순서와 메시지 순서를 바꾸지 않는다.**

### 2. `tools.py::validate_tool_args` 분리

도구별 private 검증 함수로 나눈다(이름 재량, 역할 고정):

- `_validate_ask_questions(args)`
- `_validate_save_facts(args)`
- `_validate_confirm_key_messages(args)`
- `_validate_update_checklist(args)`
- `_validate_write_plan(args)`
- 공통 `_require(cond, message)` 또는 early-return 헬퍼.

`ask_questions` 내부 검증 순서(suggestions → options → prose-option)와 모든
`ToolError` 문자열을 1바이트도 바꾸지 않는다. 인자 비-object 처리도 유지한다.

### 3. 팩트 라인

`format_fact_line(...)`을 `agent._turn_context`, `agent.commit_facts`,
`review_agent.build_context`에 적용한다. 각 호출의 출력(불릿 유무, 날짜 표현,
`(출처: ...)`)이 기존과 **바이트 동일**할 때만 적용하고, 다르면 그 호출은 남긴다.

### 4. 매직 넘버

- `MAX_ROUNDS`를 사용해 `"한도(8)"` 문구를 만들되 출력은 동일하게 유지한다.
- `MAX_DERIVATIVE_CONTEXT_CHARS = 40_000` 같은 상수는 review_agent에 도입해도 되지만
  값·동작은 동일해야 한다.

### 5. 테스트

기존 `test_interview_api.py`·`test_agents_tools.py`를 그대로 통과시킨다. 필요하면
`test_agents_tools.py`에 도구별 검증 함수가 기존 메시지를 내는지 최소 케이스를 추가한다.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_interview_api.py tests\test_agents_tools.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - 도구 스키마 dict·순서·설명이 동일한가?
   - SSE 이벤트 순서·프롬프트 바이트가 동일한가?
   - 모든 `ToolError` 문자열이 동일한가?
   - 문서 가드·골격 검증 순서가 동일한가?
3. `phases/refactor-standalone-cli/index.json`의 step 8을 갱신한다.

## 금지사항

- `INTERVIEW_TOOLS`/`WRITE_PLAN_TOOL`/`BLOCKING_TOOLS` 스키마를 생성 헬퍼로 바꾸지
  마라. 이유: dict 순서·설명 드리프트가 모델 동작을 바꾼다(유예 D12).
- `turn_graph.py`를 변경하지 마라. 이유: SSE·턴 제어 흐름의 고위험 영역이다.
- 프롬프트 파일(`interview.md`)을 변경하지 마라. 이유: 이번 작업은 코드 가독성이다.
- 검증 메시지·순서를 통일하지 마라. 이유: 테스트와 모델 재시도 동작이 고정한다.
