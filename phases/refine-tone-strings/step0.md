# Step 0: interview-tone

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개, 특히 "인터뷰 턴 계약" 규칙 (계약 파일 4종 동시 점검·수정)
- `/docs/INTERVIEW-TURN-CONTRACT.md` — 인터뷰 턴 계약 대조표·"동시 점검 세트 (계약 4종)" 표·변경 이력 관례
- `/backend/app/agents/tools.py` — ask_questions 스키마 + `validate_tool_args`/`_validate_ask_questions` (권위·기준점)
- `/backend/app/modules/interview/application/prompts/interview.md` — 런타임 LLM 프롬프트 원문
- `/backend/app/modules/interview/application/agent.py` — `_system_prompt()`·`_remind_ask()`
- `/tests/test_agents_tools.py`·`/tests/test_interview_api.py` — 계약 잠금 테스트

이전 step은 없다. 이 step이 task의 첫 step이다.

## 작업

목표: 인터뷰에서 LLM이 생성하는 질문이 축약 명사구("청중은 누구인가?", "시스템 구조는 어떻게 잡나요?")
투로 나오지 않고, **정중한 존댓말(하세요체) + 배경 맥락 포함** 문형으로 나오도록 계약을 바꾼다.
기존 "질문 본문은 한 문장" 하드 제약을 **완화**한다: 본문은 "배경 1~2문장 + 질문 1문장, 총 300자 이내"를
허용한다. 단 **본문에 선택지를 나열하는 것은 계속 위반**으로 유지한다.

**계약 4종을 반드시 한 커밋에 동시 수정한다** — 하나만 고치면 계약 위반(반려 사유).

구현 순서대로:

### 1. `backend/app/agents/tools.py` (권위·기준점 — 먼저 수정)

- 상수 신규 1건: `MAX_QUESTION_LEN = 300` (주석: 질문 본문 상한 — 배경 1~2문장 + 질문 1문장 규모).
- **기존 상수·정규식 전부 무변경**: `MAX_QUESTIONS=4`, `MAX_SUGGESTIONS=3`, `SUGGESTION_MAX_LEN=120`,
  `PROSE_OPTION_THRESHOLD=2`, `_PROSE_OPTION_LINE`의 모든 arm — 선택지 나열 거부는 이번 완화 대상이 아니다.
- `_validate_ask_questions`의 per-question 루프 안, 기존 prose 판정 이전(모든 문항이 검증되도록 options
  분기 `continue` 이전)에 가드 2개 추가:
  - 빈 본문 거부: `text`가 비문자열이거나 `strip()` 결과가 빈 값 → `ToolError(f"문항 {i}: 질문 본문이 비어 있습니다 — 본문을 배경 1~2문장 + 질문 1문장으로 채워 주세요")`
  - 길이 초과 거부: `len(text) > MAX_QUESTION_LEN` → `ToolError(f"문항 {i}: 질문 본문은 {MAX_QUESTION_LEN}자 이내입니다 (현재 {len(text)}자) — 배경 1~2문장 + 질문 1문장으로 다듬어 주세요")`
  - 문장 수 세기 검증은 **하지 마라. 이유:** "3.5배", "(주 10시간)" 같은 수치에서 마침표 개수 거짓 양성이
    생기고, 문장 수·톤은 콘텐츠 규칙이라 계약 문서 원칙("이 문서는 구조만 잠근다")상 interview.md 소관.
  - 길이 검증은 원문 그대로(정규화·strip 없이 `len(text)`) 기준으로 한다 — 기존 "raw 이력 보존, 정규화는
    pending_questions만" 계약 유지.
- 스키마 보강: `ask_questions` 도구의 `description` 끝에 1문장 추가
  ("질문 본문(text)은 정중한 존댓말로 배경 1~2문장 + 질문 1문장(총 300자 이내)으로 쓰고, 선택지 나열은
  본문에 두지 않는다."), `text` property에 description 부여("질문 본문 — 배경 1~2문장 + 질문 1문장, 300자 이내").
  **도구 이름(`ask_questions`)·필드명(`round_summary`, `questions`, `text`, `options`, `label`,
  `description`, `allow_free`, `suggestions`)·`required`·`minItems`/`maxItems`는 절대 바꾸지 마라. 이유:**
  API·OpenAPI·테스트가 잠그고 있고, 도구 스키마는 소형 모델 교체 시에도 유지되어야 하는 계약이다.
- ToolError 메시지 꼬리를 하세요체로 통일 (하라체 제거). 반드시 기존 잠금 substring("2개 이상",
  "선택지가 없습니다", "문항 2", "최대 4문항", "options 배열", "선택지 나열", "label이 비어",
  "description은 문자열", "옵션은 object", "JSON object여야", "한 줄", "120자 이내", "최대 3개",
  "후보가 비어", "문자열이어야", "문자열 배열이어야")이 잘리지 않게 중간 이전 부분은 보존:
  - "추천 후보 문장들의 배열로" → "추천 후보 문장들의 배열로 보내 주세요"
  - "제거하거나 문장을 채워라" → "제거하거나 문장을 채워 주세요"
  - "{N}개만 남겨라" → "{N}개만 남겨 주세요"
  - "나머지는 다음 라운드로" → "나머지는 다음 라운드로 넘겨 주세요"
  - "allow_free=true를 명시하라" → "allow_free=true를 명시해 주세요"
  - "options를 빼고 allow_free=true로" → "options를 빼고 allow_free=true로 바꿔 주세요"
  - "options 배열로 옮겨라 … 남긴다 … 나눌 것" → "options 배열로 옮겨 주세요 … 남겨 주세요. 문항당 1개
    주제로 나눠 주세요"
  - "save_facts를 호출하지 말 것" → "save_facts를 호출하지 말아 주세요"

### 2. `backend/app/modules/interview/application/prompts/interview.md`

- "질문 설계 규칙" 섹션: "본문은 질문 한 문장"에 해당하는 서술을 다음 규칙으로 교체:
  - **본문 구성(맥락 허용)**: 질문 본문(`text`)은 **배경 1~2문장 + 질문 1문장**으로 쓴다 (총 300자 이내 —
    서버가 길이를 검증한다). 배경 문장은 질문의 취지를 이해하는 데 꼭 필요한 맥락만 담는다. 축약
    명령형("청중은?", "구조는?")처럼 퉁명스럽게 한 단어만 던지지 않는다.
  - **선택지 나열은 계속 금지**다 — `예:`·`1.`·`가)`·`①`·불릿 줄 등 옵션 유사 줄이 본문에 2줄 이상
    보이면 서버가 거부한다. 선택지는 options 배열로만 전달한다.
- "## ask_questions 인자 형식 (완성 예시)" 서두의 "본문은 질문 한 문장이고, …" 문구를 위 새 규칙과
  정합되게 교체 ("본문은 배경 1~2문장 + 질문 1문장(총 300자 이내)이고, 옵션 유사 나열 줄이 보이면
  서버가 거부한다"). **섹션 제목 "## ask_questions 인자 형식 (완성 예시)"은 절대 바꾸지 마라. 이유:**
  `test_system_prompt_carries_fewshot_and_reminder`가 잠근다.
- few-shot 완성 예시 JSON의 `text` 3건을 맥락 포함 하세요체로 교체 (`round_summary`, options
  라벨/설명, suggestions는 무변경). 교체안 (실제 `_prose_option_lines()` 판정에 통과하는지 반드시 확인):
  - "시스템 전체 구조를 어떤 방향으로 잡을지 함께 정해 보려 합니다.\n예상하시는 팀 규모와 배포 여건을 고려할 때, 어느 구조가 이 프로젝트에 가장 잘 맞는다고 보시나요?"
  - "API 계약은 프론트엔드·외부 시스템과의 약속이라, 일찍 고정할수록 되돌리는 비용이 줄어듭니다.\n어떤 방식으로 규약을 고정하고 싶으신가요?"
  - "모듈별 책임 경계는 이후 확장에 큰 영향을 주는 부분이라 여쭙습니다.\n디렉터리 레이아웃과 모듈별 책임을 어떻게 나누고 싶으신지 자유롭게 설명해 주시겠어요?"
  - 주의: 줄이 "예:"·"1."·"가)"·"①"로 시작하면 서버가 거부한다. "예상하시는…"은 `예\s*[):]`와
    불일치라 안전하다. 교체 후 실제 검증 함수를 통과시켜 확인하라.
- "## 톤" 섹션 첫 불릿으로 추가:
  - **질문은 정중하고 부드러운 존댓말(하세요체)로 묻는다.** "…정하고 싶으신가요?", "…알려 주시겠어요?"
    같은 문형을 쓰고, "청중은 누구인가?", "시스템 구조는 어떻게 잡나요?" 같은 축약 명사구·퉁명스러운
    단문을 쓰지 않는다. 문항이 성의 있게 읽히도록 배경 맥락 1~2문장을 얹되, 질문 1문장으로 마무리해
    늘어지지 않게 한다.
- 제안서 아크(49~66행 부근)·개발설계서 아크(72~90행 부근)의 예시 질문도 같은 톤으로 순화한다.
  **라운드 목표 키워드("현황·문제 정의" 등 그룹명)와 섹션 구조는 무변경. 이유:** 테스트가
  "제안서 아크", "현황·문제 정의" substring을 잠그고, 아크 구조는 문서 품질 계약이다. 예시:
  - 현황·문제 정의 → "지금 겪고 계신 문제의 핵심은 무엇이라고 보시나요? 문제의 크기를 뒷받침하는
    수치나 사례가 있다면 함께 알려 주시면 큰 도움이 됩니다."
  - 영향·기회 → "이 문제를 그대로 두면 어떤 손실로 이어질 것 같으신가요? 언제까지 해결해야 긴급하다고
    판단하시는지도 알려 주세요."
  - 나머지 아크 문항도 동일 문형("…알려 주시겠어요?", "…어떻게 정하고 싶으신가요?")으로 순화.

### 3. `backend/app/modules/interview/application/agent.py` — `_remind_ask()`

- 매턴 주입 리마인더의 "본문은 질문 한 문장" 관련 불릿을 새 규칙으로 교체:
  "객관형 문항은 options에 {label, description}을 2개 이상, 서술형 문항은 options 없이 allow_free=true —
  질문 본문은 배경 1~2문장 + 질문 1문장(총 300자 이내)을 정중한 존댓말(하세요체)로 쓰고, 선택지
  나열은 본문에 두지 않는다(options 배열로만)."
- 나머지 불릿("라운드 {n} 목표" f-string 포함)·헤더("## 이번 턴 ask_questions 리마인더")·
  `_system_prompt()` 조립 구조는 무변경. 이유: `test_system_prompt_carries_fewshot_and_reminder`가
  잠근다.

### 4. `docs/INTERVIEW-TURN-CONTRACT.md`

- "ask_questions 스키마와 의미" 섹션에 신규 불릿 추가:
  - **질문 본문 구성(맥락 허용 완화, 2026-10-31)**: `text`는 배경 1~2문장 + 질문 1문장까지 허용된다 —
    과거 "본문은 질문 한 문장" 하드 제약을 폐지했다. 문장 수·톤(정중한 존댓말)은 콘텐츠 규칙이라
    `interview.md` 소관이고, 서버가 결정론으로 잠그는 것은 길이 상한 `MAX_QUESTION_LEN`=300자와
    빈 본문 거부뿐이다.
- "실패 수업" 참조 표에 2행 추가: "질문 본문이 300자 초과" / "질문 본문이 빈 문자열" → 각각의
  ToolError 메시지 → `tools.py validate_tool_args`.
- 변경 이력에 2026-10-31 항목 추가 — 계약 4종(tools.py·interview.md·이 문서·테스트 2종)을 한
  커밋에 갱신함과 신규 잠금 assert 추가를 명시 (기존 이력 항목의 형식을 따른다).

### 5. 테스트

- `tests/test_agents_tools.py`:
  - import에 `MAX_QUESTION_LEN` 추가.
  - 신규 회귀 테스트 3건 (계약 문서 원칙 "계약 변경 시 새 위반 케이스 회귀 테스트 추가"):
    1. 맥락 문장 포함 본문(예: "모듈 경계는 확장성에 큰 영향을 줍니다.\n디렉터리 레이아웃을 어떻게
       나누고 싶으신가요?" + `allow_free=True`)이 `validate_tool_args`를 무수정 통과 — 완화 잠금 (핵심 회귀).
    2. `MAX_QUESTION_LEN + 1`자 본문 → `pytest.raises(ToolError, match=f"{MAX_QUESTION_LEN}자 이내")`,
       "현재" 글자 수 포함 확인.
    3. `{"text": "   ", "allow_free": True}` → `match="본문이 비어"`.
  - `test_prose_choices_threshold_and_false_positives`의 ok_texts에 부드러운 톤 예 2건 추가.
    기존 항목("청중은 누구인가?" 등)은 통과 케이스로 여전히 유효하므로 유지.
  - 기존 위반 잠금 테스트는 메시지 교체 후에도 잠금 substring이 보존되므로 무변경 — 실패하는 경우에만
    해당 assert를 갱신한다.
- `tests/test_interview_api.py`:
  - `test_system_prompt_carries_fewshot_and_reminder`에 신규 잠금 assert 추가:
    `assert "배경 1~2문장" in sys1`, `assert "300자" in sys1`, `assert "하세요체" in sys1`,
    `assert "본문은 질문 한 문장" not in sys1` (변수명은 실제 코드를 따름).
  - fake LLM 스크립트 질문을 맥락 포함 하세요체로 갱신: BASE_TURNS, DESIGN_TURNS, PROPOSAL_TURNS,
    SUGGEST_TURNS. SUGGEST_TURNS의 답변 조립이 `f"{i+1}. {text}\n→ …"` 형태라 1줄 문형으로 갱신하고
    묶인 assert(예: "1. 주요 고객은…\n→ 사내 경영진")를 새 text에 맞춘다. 반복 사용 질문은 모듈
    상수로 추출해 스크립트와 assert가 같은 값을 참조하게 한다.
  - **절대 무변경**: PROSE_TURNS 첫 호출(고의 선택지 나열 위반 재현), "q" 단문 플레이스홀더,
    RETRY_TURNS·RAWARGS_TURNS·UIUX_AREA_TURNS의 위반/구조 재현 데이터는 assert가 text를 잠그지
    않으므로 갱신하지 않아도 통과한다 (일관성을 위해 상수로 교체하는 것은 허용).
  - 구조 검증을 통과하는 fake 질문이 되도록: 본문에 "예:"·"1."·"가)" 줄 없음, 300자 이내.

## Acceptance Criteria

```bash
python -m pytest tests/test_agents_tools.py tests/test_interview_api.py -q
python -m pytest -q
```

(저장소 루트에서, `PYTHONUTF8=1` 환경. 첫 커맨드가 계약 잠금, 둘째가 전체 회귀.)

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 도구 스키마 이름·필드명·required가 무변경인가? (변경했다면 즉시 원복)
   - `_PROSE_OPTION_LINE` 선택지 나열 거부가 유지되고, 새 회귀 테스트가 그것을 잠그는가?
   - 계약 4종(tools.py·interview.md·docs/INTERVIEW-TURN-CONTRACT.md·테스트 2종)이 모두 이 step에서
     갱신되었는가?
   - CLAUDE.md 설계 원칙 8개(특히 SSOT — 파생물 직접 수정 없음)를 위반하지 않았는가?
3. 결과에 따라 `phases/refine-tone-strings/index.json`의 step 0을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "인터뷰 계약 완화(본문 맥락 허용 300자)·하세요체 톤 지시·ToolError 문체 통일 — 계약 4종+회귀테스트 3건 동시 갱신"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 도구 스키마의 이름·필드명·`required`·`minItems`/`maxItems`를 바꾸지 마라. 이유: API·OpenAPI·테스트가
  잠그는 계약이며 소형 모델 교체 시에도 유지되어야 한다.
- `_PROSE_OPTION_LINE` 정규식이나 `PROSE_OPTION_THRESHOLD`를 완화하지 마라. 이유: 선택지 나열 거부는
  이번 완화 대상이 아니고, 완화되면 options 없는 문항의 서버 검증이 뚫린다.
- 문장 수를 세는 검증을 추가하지 마라. 이유: 수치의 마침표에서 거짓 양성이 생기고, 문장 수·톤은 콘텐츠
  규칙이라 interview.md 소관이다 (계약 문서: "이 문서는 구조만 잠근다").
- `interview.md`의 섹션 제목 "## ask_questions 인자 형식 (완성 예시)"와 아크 그룹명("현황·문제 정의"
  등)을 바꾸지 마라. 이유: `test_system_prompt_carries_fewshot_and_reminder`가 잠근다.
- PROSE_TURNS 첫 호출(고의 위반 본문)을 "고쳐" 버리지 마라. 이유: 위반 재현용 테스트 픽스처다.
- 기존 테스트를 깨뜨리지 마라 — 잠금 substring이 보존되는 범위에서만 메시지를 다듬는다.