# 인터뷰 턴 계약 (FR-2)

인터뷰 프로필 LLM이 한 턴에 반환해야 할 구조와 서버의 강제 방식을 기술한다.
모델(특히 소형 모델)을 교체해도 이 계약이 유지되도록 하는 것이 목적이다 — 구조 준수를
프롬프트에만 맡지 않고 서버 검증 + 같은 턴 내 재시도로 기계적으로 잠근다. 이 문서를
고치지 않고 계약을 바꾸는 PR은 반려한다 (`docs/token-checklist.md`의 토큰 4종 세트와
동일 성격).

## 턴 출력 프로토콜 (도구 전용)

- 한 턴 = 인터뷰 StateGraph 1회 invoke (`backend/app/modules/interview/application/turn_graph.py`).
- **모든 진행은 도구 호출이다** — `ask_questions` · `save_facts` ·
  `confirm_key_messages` · `update_checklist` · `write_plan`. 스키마와 문항 계약은
  `backend/app/agents/tools.py`의 `INTERVIEW_TOOLS`가 기준점이다.
- 도구 없이 텍스트만 출력하면 넛지 1회 재호출, 두 번째 텍스트 전용이면
  TurnError → 세션 FAILED. provider의 `tool_choice="required"`는 프로토콜 단에서
  텍스트 전용 출력 자체를 금지한다 — 도구 호출이 흔들리는 소형 모델의 interview
  프로필에서 옵트인한다 (`planforge/llm/provider.py`).

## ask_questions 스키마와 의미

`{round_summary, questions[≤4]}` — 각 문항은 다음 조합만 허용된다:

| 문항 종류 | options | allow_free |
|---|---|---|
| 객관형 | **2개 이상** `{label, description?}` | 생략·false·true 모두 가능 |
| 서술형 | 없음 | **true 명시** (둘 다 없으면 거부) |

- options 라벨은 앞뒤 공백이 strip되고, 공백만 남으면 거부된다 (description은 문자열만).
- 객관형 선택지는 상호배타적·실제 사례 기반으로 하고, 근거는 옵션 `description`에
  넣는다 (콘텐츠 품질 규칙 — `interview.md` 프롬프트 소관).
- **선택지를 질문 본문(text)에 나열하는 것은 언제나 위반이다** — `예:`·`예)`·`보기:`·
  `답:`·`1.`·`2)`·`①..⑳`·`가)`·`(1)`·`(가)`·불릿 등 옵션 유사 줄이 2줄 이상이면
  options 유무와 무관하게 서버가 거부한다. 선택지는 options 배열로만 전달된다.
- 프론트는 `options.length > 0`일 때만 버튼을, `allow_free ?? true`(기본 true)일 때
  "직접 입력" 인풋을 렌더한다
  (`frontend/src/features/interview/views/InterviewPanel.tsx`) — 본문 마크다운을
  파싱하는 경로는 존재하지 않으므로, 본문 나열은 "본문엔 보이고 버튼은 없는" 결함이
  된다 (이 계약이 그 출발점이다).
- 계약 서술의 원문 두 곳: `interview.md`의 `## ask_questions 인자 형식 (완성 예시)`
  섹션(객관형+서술형 혼합 실물 JSON — 그대로 모방하도록 리드)과 `_system_prompt`가
  매턴 시스템 프롬프트 끝에 부착하는 `이번 턴 ask_questions 리마인더`(`round_summary`
  의 라운드 번호는 `sess.round_no + 1`로 서버가 계산해 주입 — 프롬프트 퓨샷 예시의
  번호를 복사하지 않도록 각주 포함). 스키마의 권위는 여전히 `tools.py`의
  `INTERVIEW_TOOLS`다.
- `round_summary`는 세션 행 `pending_round_summary`(nullable Text)로 영속돼
  `SessionOut`으로 노출되고, 이력 `questions` EVENT 행 payload에도 `summary`가
  포함된다 — 재접속 리플레이에 라운드 목표가 보존된다 (구세션 행은 summary 부재 →
  프론트 폴백 제목).

## 검증과 재시도 의미

- 도구 인자는 항상 JSON object다 — list/str 등 비-object 인자도 ToolError 피드백으로
  되돌려진다 (세션 FAILED로 튕기지 않는다).
- `validate_tool_args`(`backend/app/agents/tools.py`) 실패 → `ERROR: …` tool 피드백 →
  같은 턴 내 재호출 (`turn_graph.py` `route_after_blocking`). 턴당 LLM 호출 한도
  MAX_TOOL_TURNS=8 — 초과 시 TurnError → FAILED (사용자가 재실행한다).
- 위반 피드백은 위반 문항 번호·위반 줄 원문 인용·치료안(options 이동 / 나열 제거+
  allow_free)을 한 번에 알린다 — 소형 모델도 재시도 1회에 고칠 수 있도록.
- 이 문서는 **구조만** 잠근다. 하드 규칙(임의 추측 금지·모순 처리 등 콘텐츠 품질)은
  `interview.md` 프롬프트의 소관이다.
- 이력(interview_messages)에는 원본(raw) 도구 인자가 남는다 — 정규화(strip 등)는
  `pending_questions`·questions 이벤트(사용자 노출 payload)에만 적용된다.

## 동시 점검 세트 (계약 4종)

| # | 파일 | 결합 방식 | 계약 변경 시 |
|---|---|---|---|
| 1 | `backend/app/agents/tools.py` | `INTERVIEW_TOOLS` 스키마 + `validate_tool_args` (권위·기준점) | **수정** |
| 2 | `backend/app/modules/interview/application/prompts/interview.md` | 런타임 LLM 프롬프트 — 계약 서술의 원문 | **수정** — 같은 계약으로 |
| 3 | `docs/interview-turn-contract.md` | 이 대조표 | **수정** — 같은 계약으로 |
| 4 | `tests/test_agents_tools.py` · `tests/test_interview_api.py` | 스키마 잠금·재시도 잠금 (스크립트된 가짜 LLM) | **수정** — 새 위반 케이스 회귀 테스트 추가 |

하나만 고치는 PR은 리뷰에서 반려한다.

## 모델 교체 시 체크리스트

1. `backend/planforge/config.json`의 프로필을 교체한다 — 도구 호출이 흔들리는 모델이면
   interview 프로필에 `"tool_choice": "required"`. 일부 OpenAI 호환 릴레이는 required를
   무시(무해)하거나 거부(400)할 수 있다 — 거부되면 auto(기본값)로 되돌린다.
2. `pytest tests/test_agents_tools.py tests/test_provider_stream.py tests/test_interview_api.py`
   — 스키마·재시도 잠금 회귀.
3. 저장소 루트에서 `pytest` 전체.
4. 실세션 수동 관찰(개발 서버 또는 e2e-smoke): 질문 카드에 options 버튼·직접 입력
   노출, ERROR 피드백 뒤 같은 턴 내 재시도.
5. 아래 참조에 없는 반복 위반이 관찰되면 계약 4종을 한 커밋에 갱신한다 — 검증 추가 +
   피드백 문구 + 테스트 잠금.

## 실패 수업 참조 (모델 교체 디버깅)

| 수업 (위반) | 서버 반응 | 출처 |
|---|---|---|
| 도구 호출 없이 텍스트 전용 | 넛지 1회 → TurnError | `turn_graph.py route_after_llm` |
| 문항에 options도 allow_free도 없음 | "선택지가 없습니다" | `tools.py validate_tool_args` |
| options가 1개뿐 | "선택지는 2개 이상이어야" | `tools.py validate_tool_args` |
| 선택지를 본문에 `예:` 등으로 나열 | "질문 본문에 선택지 나열이 있습니다" | `tools.py validate_tool_args` |
| options 라벨 비어 있음 | "label이 비어 있습니다" | `tools.py validate_tool_args` |
| 인자가 비-object(list/str/int) | "도구 인자는 JSON object여야" | `tools.py validate_tool_args` |
| 인자 JSON 파싱 실패 | "도구 인자 JSON 파싱 실패" | `agent.py _dispatch` |
| plan 마크다운 포맷·핵심 메시지 3개 위반 | "plan 포맷 검증 실패" 등 | `agent.py _write_plan` |