# Step 2: regression

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이전 step의 산출물을 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개 (최상위)
- `/docs/INTERVIEW-TURN-CONTRACT.md` — step 0에서 추가된 스트림 전송 계층 keepalive 섹션
- `/backend/app/modules/interview/presentation/api.py` — step 0 산출물 (`_stream_turn` ping 루프)
- `/backend/app/shared/config.py` — step 0 산출물 (`sse_keepalive_seconds` float)
- `/tests/test_interview_api.py` — step 0에서 추가된 회귀 테스트 2개
- `/frontend/src/api/client.ts` — step 1 산출물 (유휴 타임아웃)
- `git diff main...HEAD` (또는 이전 step 커밋)로 누적 변경 전체를 훑어라.

배경: step 0(백엔드 keepalive wiring + 계약 문서 + 회귀 테스트)와 step 1(프론트
inactivity 타임아웃)을 각각의 AC로 검증했다. 이 step은 task 전체의 회귀 선을
확정한다 — 전체 pytest suite + 프론트 타입 체크·빌드가 모두 녹색인지 확인하고,
계약 동시 점검이 누락되지 않았는지 대조한다.

## 작업

1. **전체 회귀 실행** (아래 AC 두 커맨드). 실패 시 원인이 이 task의 변경인지
   확인해 수정한다 — 이 task 범위 밖의 사전 존재 실패면 `blocked`로 기록한다.
2. **계약 동시 점검 대조**:
   - `docs/INTERVIEW-TURN-CONTRACT.md`에 keepalive(전송 계층) 섹션이 존재하고,
     코멘트 프레임이 이벤트가 아님(`interview_messages` 미영속 · `parseFrame` 무시)
     가 서술돼 있는가?
   - `tests/test_interview_api.py`에 keepalive ping 수신·keepalive=0 무전송 테스트가
     모두 있는가?
   - `backend/README.md`의 `sse_keepalive_seconds` 설명이 실제 동작(float 파싱 ·
     `api.py _stream_turn`에서 실사용)과 일치하는가?
3. **범위 대조**: `git status`·diff에서 이 task 목적(keepalive + inactivity 타임아웃)
   에 필요 없는 변경이 섞였는지 눈으로 확인한다. `workspaces/`·`sources/`·`data/`·
   `backend/planforge/config.json`이 변경 목록에 있으면 안 된다(ignored 대상이
   스테이징된 경우 커밋하지 마라).
4. **수동 검증 항목 기록**: 실서버 수동 관찰(답변 제출 → DevTools Network에서 15초
   간격 `: ping` 수신, LLM 대기 후 "context"→"llm" 라벨 교체, 백엔드 kill 시 60초 내
   오류 표시·재제출 가능 복귀)은 실행자가 아닌 사용자 검증 항목이다 — 이 step에서
   실행하지 말고, step summary에 "수동 검증 미실시"를 명시하라.

## Acceptance Criteria

```bash
python -m pytest -q           # 저장소 루트에서 — 전체 suite 녹색
npm run build                 # frontend/에서 — tsc --noEmit 포함
```

## 검증 절차

1. 위 AC 커맨드 두 개를 모두 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - docs/ARCHITECTURE.md 모듈 경계 규칙을 지키는가?
   - docs/ADR.md의 결정·편차를 벗어나지 않았는가? (step 0에서 ADR 기록을 추가했다면
     일관성 확인)
   - CLAUDE.md 설계 원칙 계약 8개를 위반하지 않는가?
3. 결과에 따라 `phases/sse-keepalive/index.json`의 step 2를 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` — summary에
     전체 suite 통과 여부와 수동 검증 미실시 사실을 포함하라
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 이 step에서 기능 코드(`api.py`·`client.ts` 등)를 수정하지 마라. 이유: 회귀 확정
  step이 코드를 바꾸면 step 0/1의 AC가 다시 유효하지 않게 된다 — 코드 수정이
  필요하면 해당 step의 `status`를 `"pending"`으로 되돌리고 error 해소 후 재실행하는
  것이 하네스 규칙이다.
- 실제 LLM을 호출하는 `node e2e-smoke.mjs`를 실행하지 마라. 이유: 커밋 대상 아닌
  수동 검증 스크립트이며 API 키·사용자 관여가 필요하다 — 사용자 검증 항목이다.
- ignored 경로(`workspaces/`·`sources/`·`data/`·`backend/planforge/config.json`)를
  스테이징/커밋하지 마라. 이유: SSOT·키 보호 계약 위반이다 (CLAUDE.md 개발 규칙).