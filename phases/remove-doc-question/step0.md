# Step 0: doc-context — 세션 문서 정체성을 인터뷰 컨텍스트에 주입

## 배경 (자기완결 — 외부 대화 참조 금지)

feat-doc-loop 이후 각 인터뷰 세션은 생성 시 `doc_slug`로 문서가 고정된다
(프로젝트 카드 문서 버튼/칩 진입, `docloops.require_session_doc` 게이트).
그런데 `InterviewAgent`는 `doc_slug`를 LLM 컨텍스트로 주입하지 않아 인터뷰
에이전트가 세션의 문서 정체성을 모른다. 결과적으로 에이전트가 "이번 인터뷰로
확정할 산출 문서는 무엇인가요?"를 묻게 되는 근원이 된다 (프롬프트 쪽 지시 제거는
step 2에서 처리 — 이 step은 주입만 한다).

이 step에서는 에이전트가 어떤 문서 인터뷰인지 매턴 알 수 있게 주입 컨텍스트를
확장한다. 프롬프트(interview.md)·tools.py는 이 step에서 수정하지 않는다
(테스트는 fake LLM이라 잠시 구 프롬프트 지시와 주입이 공존해도 동작에 영향 없음).

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/INTERVIEW-TURN-CONTRACT.md`
- `/backend/app/modules/interview/application/agent.py` — 이 step의 주 대상
- `/backend/app/modules/docloops/facade.py` — `doc_label` 공개 함수 (모듈 경계: 반드시 facade 경유)
- `/backend/app/modules/docloops/application/service.py` — `DOC_KINDS` SSOT
- `/tests/test_interview_api.py` — 기존 테스트 스타일 (fake LLM·주입 assert)
- `/tests/test_docloops_api.py` — DocLoop 행 직접 세팅 패턴 참조

## 작업

### 1. `backend/app/modules/interview/application/agent.py` — `_turn_context()` 주입

`_turn_context()`(파일에서 "### 턴 컨텍스트" 주석 아래 메서드)의 `parts` 조립
선두에서, 세션에 `doc_slug`가 있으면 다음 블록을 추가한다:

```
### 이번 인터뷰 문서
- 이번 인터뷰는 **{label}** 단독 문서 세션이다. 산출 문서는 서버가 세션 생성 시
  고정한 값이다 — 문서 목록·선택을 묻거나 확정 항목으로 다루지 않는다. plan 메타는
  `- 산출 문서: {label}` 하나만 쓴다.
```

- `{label}`은 `docloops.doc_label(self.sess.doc_slug)`로 조회한다
  (facade에 이미 공개 — 다른 경로로 DOC_KINDS를 직접 순회하지 마라).
- 레거시 세션(`doc_slug is None`)은 이 블록을 넣지 않는다.
- 소스·팩트 조립 로직은 건드리지 않는다 (블록이 있어도 뒤의 "텅 비면 뼈대 질문"
  폴백 문구는 유지된다).

### 2. `agent.py` `_system_prompt()` 헤더 문구

`## 이번 턴 주입 컨텍스트 (소스·확립 팩트 — 임의 추측 금지)` →
`## 이번 턴 주입 컨텍스트 (이번 인터뷰 문서·소스·확립 팩트 — 임의 추측 금지)`

### 3. `tests/test_interview_api.py` — 주입 assert

- **positive**: 세션을 `POST /api/projects/{pid}/interview/sessions`,
  `json={"doc_slug": "proposal"}`로 생성(제안서 루프는 생성 직후 active라 게이트
  통과). kick 후 첫 LLM 호출의 system 프롬프트에
  `"이번 인터뷰 문서"`·`"제안서"`·`"문서 목록·선택을 묻거나 확정 항목으로"`가
  포함됐는지 assert한다. 기존 `test_system_prompt_carries_fewshot_and_reminder`
  테스트를 확장해도, 별도 테스트를 하나 만들어도 좋다 (기존 스타일 준용).
- **negative(레거시)**: 기존처럼 `json={}`(doc_slug NULL) 세션의 시스템 프롬프트에
  `"이번 인터뷰 문서" not in sys` — 레거시 세션엔 주입이 없다는 것을 잠근다.

테스트 셋업은 파일의 기존 fixture(`_setup`, `base_kit` 등)를 재사용하고,
fake LLM이 필요하면 기존 `FakeStreamLLM` 턴 스크립트 패턴을 따른다.

## Acceptance Criteria

```bash
python -m pytest tests/test_interview_api.py -q   # 저장소 루트에서
```

## 검증 절차

1. 위 AC 커맨드를 실행한다 (추가로 `python -m pytest tests/test_docloops_api.py -q`로
   docloops 회귀 없음을 확인).
2. 아키텍처 체크리스트:
   - 문서 라벨 조회는 `docloops` facade(`doc_label`) 경유만 — DOC_KINDS·모델 직접 import 금지.
   - `planforge/` 파서·빌더를 수정하지 않았는가?
   - `backend/app/agents/tools.py`를 수정하지 않았는가?
   - CLAUDE.md 설계 원칙(SSOT·LLM 역할 분리 등) 위반 없는가?
3. `phases/remove-doc-question/index.json`의 step 0 status를 업데이트한다
   (성공 → `"completed"` + `"summary"`는 "agent.py doc_slug 주입 블록 + pos/neg assert" 등
   다음 step에 유용한 한 줄).

## 금지사항

- `interview.md` 프롬프트를 수정하지 마라 — 이유: 프롬프트 재작성은 step 2의
  소관이고, 이 step에서 고치면 step 2 세션이 "이미 바뀐" 파일을 예상대로 읽지 못해
  동시 점검 계약을 깨는다.
- `backend/app/agents/tools.py`를 수정하지 마라 — 이유: 도구 스키마·검증에는 산출
  문서 개념이 없다 (무수정 근거는 step 2가 계약 문서에 기록한다).
- `planforge/`(파서·빌더)를 수정하지 마라 — 이유: ADR 결정 22상 결정론 파이프라인 무수정.
- 워크스페이스 파생물(`workspaces/**`)을 직접 쓰지 마라 — 이유: SSOT 가드훅이 차단한다.
- 기존 테스트를 깨뜨리지 마라.