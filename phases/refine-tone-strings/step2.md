# Step 2: backend-messages

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 모듈 경계 규칙(타 모듈 직접 import 금지), 백엔드 모듈러 모놀리식 구조
- `/phases/refine-tone-strings/step0.md`·`/phases/refine-tone-strings/step1.md` — 이전 step(완료):
  인터뷰 계약 완화·프론트엔드 문자 순화. 이 step에서 참고할 기준표는 step1.md의 용어 순화 기준표다.
- 아래 "작업"에 나열된 백엔드 파일들 전부 — 수정 전에 실제 원문을 읽고, 그 문자를 표시하는
  프론트엔드 화면(관련 view/viewmodel)과 assert하는 테스트가 있는지 함께 확인하라.

## 작업

목표: 백엔드가 사용자에게 노출하는 문자(API 4xx 응답 메시지, SSE/세션 오류, job 오류, 검수 발견사항,
경고 문자열)을 자연스러운 친절한 한국어("하세요/입니다"체, 완결문)로 순화한다.

기준표는 `phases/refine-tone-strings/step1.md`의 **용어 순화 기준표**를 따른다 (채번→버전 번호,
세대→버전, 미달→문제 N건, 해소→해결, 확립→확정, 적립→기록, 파생물/산출물→"산출물" 통일, 하라체·
평서형("~했다", "~해야 한다")→"~하세요/~합니다", 명사형 축약 종결→완결문, "(FR-x)" 내부 참조 제거).

### 수정 파일 목록

- `backend/app/modules/review/presentation/api.py`
  - "검수할 파생물이 없습니다 — 먼저 산출물을 생성하세요" → "검수할 산출물이 없습니다 — 먼저
    산출물을 생성해 주세요" (한 문장 안 파생물/산출물 혼용 해소)
- `backend/app/modules/plans/application/planrevise.py`
  - "plan 반영 실패 — {N}회 재시도 후에도 해소되지 않았습니다: …" → "해결되지 않았습니다"
- `backend/app/modules/plans/presentation/api.py`
  - "finding_indices에 중복이 있습니다" → 내부 필드명 노출을 피해 "선택한 발견사항에 중복이
    있습니다" (사용자가 전달하는 값에 대한 안내이므로 필드명 없이 설명)
- `backend/app/modules/interview/application/turn_graph.py`
  - "턴 내 도구 루프 한도({max_turns}) 초과" → 내부 용어 나열을 사용자 관점으로 풀어 안내
    (예: "한 턴에서 진행할 수 있는 횟수({max_turns}회)를 초과했습니다") — TurnError가 InterviewPanel
    "세션 실패: …"로 사용자에게 그대로 표시됨
- `backend/app/modules/facts/application/compact.py`
  - "… — 건너뜀" → "… — 건너뛰었습니다" (완결문)
  - "archive하지 않았습니다" → "(미확정) 항목이라 보관 대상에서 제외했습니다" 식으로 자연어화
    ((미확정) 규약어는 유지)
- `backend/app/modules/sources/application/zip_sources.py`
  - "디렉터리 항목" → "폴더 항목이라 저장하지 않았습니다" 식의 완결 스킵 사유
- `backend/app/modules/derivatives/application/derive_build.py`
  - progress 로그 문자("잔여 수치 위반 — 검수 자동 큐진입" 등) 중 사용자 노출 가능 분야의 관료어
    정리 — 로그 전용이면 최소한만 손대고 노출 문자 위주로
- `backend/app/modules/review/application/run_review.py`
  - "이전 plan 세대의 산출물입니다 — plan을 고친 뒤 파생물을 재생성하세요 (재생성 대상)" →
    "(재생성 대상)" 명사 나열을 풀어 완결문으로, 파생물→산출물
  - "결정론 검수 결과만 반영됨" → "자동 검사 결과만 반영했습니다"
- 그 외 위 파일들을 읽다가 발견하는 사용자 노출 문자(에러 메시지·경고)도 기준표에 맞춰 수정한다.

**각 문자를 수정하기 전에 반드시 `tests/`에서 그 문자를 assert하는 테스트가 있는지 grep으로 확인하고,
있다면 같은 step에서 함께 갱신한다.** (예: 검수·플랜 API 응답 메시지를 잠그는 테스트)

## Acceptance Criteria

```bash
python -m pytest -q
```

(저장소 루트에서, `PYTHONUTF8=1` 환경 — 전체 회귀)

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 모듈 경계 규칙(타 모듈 직접 import)을 위반한 변경이 없는가? — 문자 수정만 하므로 import
     변화가 생기면 안 된다.
   - API 스키마(경로·필드·응답 코드)는 무변경인가? — 메시지 문자열만 바꾼다.
   - CLAUDE.md 설계 원칙 8개 위반 없음(SSOT — 파생물 직접 수정 없음)?
3. 결과에 따라 `phases/refine-tone-strings/index.json`의 step 2을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "백엔드 사용자 노출 메시지 순화(파생물/산출물 통일·해소→해결·완결문화·세요체) — 모듈 N개 파일, 전체 pytest 통과"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `backend/app/agents/tools.py`의 ToolError·검증 메시지를 다시 건드리지 마라. 이유: step 0에서 인터뷰
  계약 4종과 함께 이미 갱신·잠금했고, 재수정하면 계약 테스트가 깨진다.
- 로그 전용 문자열을 대거 고치지 마라. 이유: 이 step은 사용자 노출 문자가 목적이고, 로그는 운영자
  진단 자료다 — grep 대상이 되는 키워드([tool-loop] 등)를 유지해야 한다.
- API 응답 스키마·필드명·HTTP 상태 코드를 바꾸지 마라. 이유: 프론트엔드와 OpenAPI 계약이다.
- `frontend/src/api/types.gen.ts` 재생성이 필요한 변경을 만들지 마라. 이유: 메시지 문자열은 스키마에
  들어가지 않으며, docstring 변경이 없어야 한다.
- 기존 테스트를 깨뜨리지 마라 — assert 문자를 바꾼 경우 반드시 같은 커밋에서 테스트를 갱신한다.