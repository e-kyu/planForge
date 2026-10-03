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
- **suggestions(추천 후보) — 문항 단위 선택 필드**: `string[]`(최대 3개,
  각 120자 이내·strip 정규화·빈 값·개행(리터럴 `\n`·이스케이프 `\\n`) 금지 —
  검증은 `validate_tool_args`, 거부 피드백은 위반 번호·원문 인용을 함께 알린다).
  서버는 프론트 답변 카드에 "추천 칩"으로 노출한다 — 칩 클릭은 자유 입력 채움이며
  사용자가 수정한 뒤 [답변 제출]로 제출한다 (즉시 제출 아님). "소스·확립 팩트에서
  도출한 것만 담는다"는 콘텐츠 규칙과 "추측이면 (미확정) 포함" 유도는 결정론 검증
  불가(의미 판단)라 `interview.md`의 소관이다.

## 모름 답변과 추천 적립

- `/answers` 라인 조립은 결정론이다 — **제출하지 않은(미제출) 문항은 `→ (모름)`
  마킹 라인으로 채워** 사용자 원문과 함께 인덱스 오름차순으로 전달한다 (무응답
  인덱스가 메시지에서 소실돼 LLM이 추론해야 했던 지점 차단). 답변이 0건인 빈 배열은
  409다 — "전부 모름" 제출은 받지 않고 문항별 "모름" 입력·추천 칩으로 커버한다.
- "모름·몰라·모르겠다" 계열 free_text는 **그대로 전달한다** — 정규식 마킹은
  부분답변("모르지만 대안 검토가 필요하다") 오표기 위험이 있고 원칙 3(원문 보존)과
  충돌한다. 모름 인지와 추천 생성은 `interview.md` "모름 답변 처리" 절의 소관이다.
- 추천의 적립은 `save_facts` 경유로만 한다 — content에 `(미확정)`·근거를 명시하고
  source는 "인터뷰 추천", origin은 기존 `interview` 그대로다. **fact_gate 승인
  (사용자 수정 가능)이 유일한 채택 승인 지점**이고, 승인 후 interview-log 미러 →
  plan 근거로 이어진다. save_facts는 라운드를 소모하지 않는다 (ask_questions만
  `round_no +1`) — 모름 문항이 여러 개면 한 번의 호출에 모두 제시한다.
- save_facts는 blocking 도구 — **추천 제시와 다음 질문을 같은 턴에 함께 호출하지
  않는다**. 첫 blocking만 실행되고 뒤 호출은 소실되며(turn_graph `dispatch_blocking`),
  소실되는 쪽이 ask_questions라 안전측이다. 승인 다음 턴에서 이어서 진행한다.

## 검증과 재시도 의미

- 도구 인자는 항상 JSON object다 — list/str 등 비-object 인자도 ToolError 피드백으로
  되돌려진다 (세션 FAILED로 튕기지 않는다).
- `validate_tool_args`(`backend/app/agents/tools.py`) 실패 → `ERROR: …` tool 피드백 →
  같은 턴 내 재호출 (`turn_graph.py` `route_after_blocking`). 턴당 LLM 호출 한도
  MAX_TOOL_TURNS=8 — 초과 시 TurnError → FAILED (사용자가 재실행한다).
- 위반 피드백은 위반 문항 번호·위반 줄 원문 인용·치료안(options 이동 / 나열 제거+
  allow_free)을 한 번에 알린다 — 소형 모델도 재시도 1회에 고칠 수 있도록.
- `write_plan` 포맷 실패 피드백은 **불릿 허용 키·모범 표기 치트시트**(`agent.py`
  `PLAN_BULLET_CHEATSHEET`, 교정 예 포함)를 함께 되돌린다 — 파서 메시지는 결정론
  파이프라인 공용(derive·numcheck·CLI)이라 건드리지 않고, 치료안은 앱 계층(`_write_plan`)
  이 붙인다. 임의 키(`내용:`·`행:`) 위반이 동일 반복돼 재시도를 소진한 실세션 수업의
  대응이다. write_plan 검증 실패는 턴 한도와 별개로 `PLAN_FIX_ATTEMPTS=3`까지 재시도하며
  4번째 write_plan 호출에서 TurnError → 세션 FAILED. 골격 미달(SkeletonError)도
  "plan 골격 검증 실패"(문서명 포함) ERROR 피드백으로 같은 재시도 루프에 참여한다.
- 다중 문서 계약은 파서가 교차검증한다 — 슬라이드 `[문서: ...]` 태그는 메타 `산출 문서:
  (쉼표 나열)`에 정의된 문서만 가리킬 수 있고, 메타가 복수 문서면 각 문서가 태그 슬라이드를
  1개 이상 갖는다 (`planforge/plan/parser.py _validate_plan`; 구분자 쉼표·플러스 흡수).
  메타 라인 누락은 디폴트(["제안서"])와 태그의 불일치로 검출된다 — 위반 시 "plan 포맷
  검증 실패" ERROR 피드백으로 위 재시도 루프에 참여한다. 이 검증이 없으면 태그는 정확해도
  전 파이프라인이 문서 1개 전제로 무음 단일화된다 (제안서만 산출되는 실사고의 방지책).
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
   피드백 문구 + 테스트 잠금. 적용 사례: 목차 `- 내용:`·표 행 `- 행:` 임의 키 위반이
   동일 반복돼 세션 FAILED — 치료안 치트시트·SkeletonError 피드백·임의 키 금지 프롬프트
   문구를 이 갱신으로 반영했다.

## 실패 수업 참조 (모델 교체 디버깅)

| 수업 (위반) | 서버 반응 | 출처 |
|---|---|---|
| 도구 호출 없이 텍스트 전용 | 넛지 1회 → TurnError | `turn_graph.py route_after_llm` |
| 문항에 options도 allow_free도 없음 | "선택지가 없습니다" | `tools.py validate_tool_args` |
| options가 1개뿐 | "선택지는 2개 이상이어야" | `tools.py validate_tool_args` |
| 선택지를 본문에 `예:` 등으로 나열 | "질문 본문에 선택지 나열이 있습니다" | `tools.py validate_tool_args` |
| options 라벨 비어 있음 | "label이 비어 있습니다" | `tools.py validate_tool_args` |
| 추천 후보(suggestions)를 4개 이상 제시 | "추천 후보는 최대 3개다" | `tools.py validate_tool_args` |
| 추천 후보가 빈 문자열 | "추천 후보가 비어 있습니다" | `tools.py validate_tool_args` |
| 추천 후보에 개행(리터럴·이스케이프) 포함 | "추천 후보는 한 줄 문장이다" | `tools.py validate_tool_args` |
| 추천 후보가 120자 초과 | "추천 후보는 120자 이내 한 줄이다" | `tools.py validate_tool_args` |
| 인자가 비-object(list/str/int) | "도구 인자는 JSON object여야" | `tools.py validate_tool_args` |
| 인자 JSON 파싱 실패 | "도구 인자 JSON 파싱 실패" | `agent.py _dispatch` |
| plan 마크다운 포맷·핵심 메시지 3개 위반 | "plan 포맷 검증 실패" 등 — 치료안 치트시트 첨부 | `agent.py _write_plan` |
| 목차 슬라이드를 `- 내용: 01 … / 02 …` 임의 키로 작성 | "plan 포맷 검증 실패 — 해석할 수 없는 불릿" + 치트시트 (교정 예: `- 핵심문장: 01 …`) | `agent.py _write_plan` + `planforge/plan/parser.py` |
| 표 데이터 행을 `- 행: …`(키 붙인 최상위 불릿)으로 작성 | "plan 포맷 검증 실패 — 해석할 수 없는 불릿" + 치트시트 (교정 예: 들여쓰기 + 키 없는 `셀\|셀\|셀`) | `agent.py _write_plan` + `planforge/plan/parser.py` |
| plan 포맷은 통과했으나 표지·목차·마무리·내용 슬라이드 누락 (SkeletonError) | "plan 골격 검증 실패 — 문서명 포함" ERROR 피드백 → 재시도 참여 | `agent.py _write_plan` |
| 다중 문서 plan에서 `## 메타` `산출 문서:` 누락 (슬라이드 태그는 정상) | "plan 포맷 검증 실패 — 슬라이드 문서 태그 '개발설계서'가 메타 '산출 문서'(제안서)에 없습니다…" + 치트시트 | `agent.py _write_plan` + `planforge/plan/parser.py` |
| plan 검증 실패 3회 소진 후 4번째 write_plan 호출 | TurnError "plan 검증 재시도 한도 초과" → 세션 FAILED | `turn_graph.py dispatch_blocking` |

참고: 같은 수업의 병행 결함은 plans 모듈 후속 커밋으로 잠갔다 — `planrevise.py`의
`validate_plan_markdown`(단일 권위)이 SkeletonError를 "plan 골격 검증 실패 — 문서 '…'"
PlanError로 감싸 revise 루프의 `except PlanError` 재시도에 참여시켰고, revise API가
500 대신 422로 답하는 것과 job 오류 분류(SCHEMA→VALIDATION)도 한 번에 정상화됐다.
파서·filter 원문은 결정론 파이프라인 공용(derive·numcheck·CLI)이라 건드리지 않는다.