# Step 0: backend-keepalive

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개 (최상위)
- `/docs/INTERVIEW-TURN-CONTRACT.md` — 인터뷰 턴 계약 (동시 점검 세트 절 포함)
- `/backend/app/modules/interview/presentation/api.py` — `_stream_turn` (109-152행 부근), 이번 수정 대상
- `/backend/app/shared/config.py` — `Settings.sse_keepalive_seconds` (dead config, wiring 대상)
- `/backend/app/modules/interview/domain/events.py` — `Event.sse()` 프레임 포맷 (변경 금지 확인용)
- `/backend/README.md` — `sse_keepalive_seconds` 문서 확인 대상
- `/tests/test_interview_api.py` — `_sse_events` 헬퍼와 fake LLM (`llm_app_factory`, `FakeStreamLLM`) 패턴
- `/tests/fakes.py`, `/tests/conftest.py`, `/tests/_helpers.py` — fake LLM·fixture 구조
- `/frontend/src/api/client.ts` — `parseFrame`이 data 라인 없는 프레임을 null로 무시함을 확인 (변경은 아래 절찰로 진행)

배경: 인터뷰 SSE 턴에서 LLM 첫 토큰(TTFB) 대기·도구 실행 구간에 서버가 아무 바이트도 보내지
않아, 프록시 유휴 타임아웃/LLM 정체 시 프론트가 half-open 연결에서 무한 대기한다.
`sse_keepalive_seconds=15` 설정이 존재하지만 이 값을 읽는 코드가 없어 dead config다.
이 step은 유휴 구간에 SSE 코멘트 프레임(`: ping`)을 흘려 다음 step(프론트 inactivity
타임아웃)의 활동 감지 기준을 만든다. 코멘트 프레임은 **이벤트가 아니다** —
`parseFrame`이 무시하고 `interview_messages`에 영속되지 않는다(D6 이벤트 계약 무변경).

## 작업

### 1. `backend/app/shared/config.py`

`sse_keepalive_seconds`를 float으로 파싱하도록 수정 (테스트에서 0.2초 주입과 소수
keepalive 지원):

```python
self.sse_keepalive_seconds: float = float(os.environ.get("SSE_KEEPALIVE_SECONDS", "15"))
```

### 2. `backend/app/modules/interview/presentation/api.py` `_stream_turn.generate()`

`while True: ev = q.get()` 루프를 타임아웃 방식으로 교체한다. 시그니처 수준:

- `generate()` 진입 시 `keepalive = max(0.0, float(settings_param.sse_keepalive_seconds))`
  — `settings_param`은 `_stream_turn`의 기존 `settings` 인자다.
- 루프 내 큐 대기를 다음으로 바꾼다:

```python
try:
    ev = q.get(timeout=keepalive) if keepalive > 0 else q.get()
except queue.Empty:
    yield ": ping\n\n"      # SSE 코멘트 프레임 — 전송 계층 유지 신호
    continue
```

- `queue.Empty`는 이미 import된 `queue` 모듈에서 사용한다 (`import queue` 존재 확인).
- 핵심 규칙(설계 의도 — 재량 금지):
  - ping은 **코멘트 프레임 문자열** 그대로 yield한다. `Event` 객체를 만들지 않는다 —
    이유: ping은 이벤트가 아니며, Event로 만들면 `interview_messages` 영속·리플레이
    커서 소비·프론트 이벤트 핸들링 계약(D6)이 오염된다.
  - `Event.sse()` 포맷·이벤트 타입 시그니처는 무변경으로 유지한다.
  - keepalive <= 0이면 기존 동작(무한 대기, ping 없음)과 동일해야 한다.

### 3. `tests/test_interview_api.py` — 회귀 테스트 2개 추가

- (a) **keepalive ping 수신**: `sse_keepalive_seconds`를 0.2 같은 소값으로 설정
  (`app.state.settings` 필드 직접 교체 — `Settings` 클래스 문서 "테스트에서는 필드를
  직접 교체한다" 관례)하고, LLM 스트림 토큰/이벤트 사이에 keepalive보다 긴 지연(예:
  0.5초)이 흐르는 fake stream을 주입해 SSE 원문(raw)에 `: ping` 프레임이 끼어드는지 검증.
  - 기존 `_sse_events` 헬퍼는 `data: ` 라인만 수집하므로 코멘트 프레임을 감지할 수
    없다 — 이 테스트 파일 안에 raw 라인 수집 헬퍼(예: `_sse_raw_lines(client, url)`)
    를 새로 만들어 사용한다. 테스트 파일 간 import 금지 규칙을 지킬 것 — 공용화는
    `tests/_helpers.py`로만.
  - fake stream 주입은 `tests/fakes.py`의 `FakeStreamLLM` 구조를 읽고 재량으로:
    스트리밍 생성자 사이에 `time.sleep`을 넣는 래퍼 fake 또는 FakeStreamLLM 지연
    옵션. 인터뷰 프로필 주입은 기존 `llm_app_factory({"interview": fake})` 패턴 사용.
- (b) **keepalive=0이면 ping 없음**: `sse_keepalive_seconds = 0` 설정 시 동일 지연
  fake로 스트림 원문에 코멘트 프레임이 없음을 검증 — 기존 동작 불변 잠금.
- 기존 테스트는 모두 그대로 통과해야 한다 — 기존 `_sse_events`는 코멘트 프레임을
  무시하므로 ping 추가가 기존 어설션을 깨지 않는다.

### 4. `docs/INTERVIEW-TURN-CONTRACT.md` — 전송 계층 keepalive 섹션 추가

기존 문서 스타일(날짜 표기 + 결정 기록)을 따라 스트림 전송 계층 섹션을 추가한다:

- `: ping` 코멘트 프레임 — 이벤트 아님 · `interview_messages` 미영속 · 프론트
  `parseFrame` 무시 · 구현 위치 `api.py _stream_turn` · 설정 `sse_keepalive_seconds`
  (기본 15초, SSE_KEEPALIVE_SECONDS 환경변수).
- 프론트 inactivity 타임아웃과의 결합 — 다음 step에서 프론트가 바이트 청크 기준
  유휴 판정(60초)으로 이 프레임을 활동 신호로 사용한다.
- 동시 점검 세트 기록: `tools.py`·`interview.md`는 이 변경으로 점검했다는 사실과
  무수정 이유(도구 스키마·프롬프트 계약 무변경)를 명시 — 기존 무수정 기록 사례
  (2026-10-13 area 어휘 확장 등)와 같은 형식.

### 5. `backend/README.md` — `sse_keepalive_seconds` 설명 확인

README에서 `sse_keepalive_seconds`를 언급하는 절이 실제 wiring 사실과 일치하는지
확인하고, 부정확하면 최소 범위로 보정한다.

## Acceptance Criteria

```bash
python -m pytest tests/test_interview_api.py -q   # 저장소 루트에서 — 기존 전체 + 신규 2개 통과
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - docs/ARCHITECTURE.md 모듈 경계 규칙(타 모듈 직접 import 금지)을 지키는가?
   - docs/ADR.md의 결정·편차를 벗어나지 않았는가? (이 변경은 편차 신규 아님 —
     dead config 활성화다. ADR 기록이 필요하다고 판단되면 docs/ADR.md에 한 줄 결정
     기록을 추가해도 된다)
   - CLAUDE.md 설계 원칙 계약 8개를 위반하지 않는가? (SSOT·수치 무결성 관련 없음 —
     파생물·plan 콘텐츠를 건드리지 않았는지 확인)
3. 결과에 따라 `phases/sse-keepalive/index.json`의 step 0을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `Event.sse()` 포맷·이벤트 타입(`domain/events.py`)을 변경하지 마라. 이유: ping은
  이벤트가 아니며 D6 SSE 이벤트 계약·리플레이 영속화 계약이 오염된다.
- ping을 `interview_messages`에 영속하지 마라. 이유: 전송 계층 신호를 이력에 쌓으면
  재접속 리플레이 오염·seq 커서 소비가 발생한다(progress_event의 emit-only 설계와 같다).
- LLM 호출 계약(`chat_fn`/`stream_fn` dict)과 `planforge/llm/provider.py`를 변경하지
  마라. 이유: 편차 10 계약 불변.
- `workspaces/`·`sources/`·`data/` 산출물을 직접 수정하지 마라. 이유: SSOT 가드훅
  (`guard_ssot.py`)이 차단하며 계약 1 원칙 위반이다.
- 기존 테스트의 어설션을 "ping 추가로 깨졌다"는 이유로 수정하지 마라. 이유: 기존
  `_sse_events`는 코멘트 프레임을 무시하므로 기존 테스트가 깨진다는 것은 ping 구현
  결함이다(코멘트가 아니라 이벤트로 나간 것) — 구현을 되돌아볼 것.