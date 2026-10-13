# Step 1: frontend-idle-timeout

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/frontend/CLAUDE.md` — feature-MVVM 구조·규칙
- `/CLAUDE.md` — 설계 원칙 계약 8개 (최상위)
- `/frontend/src/api/client.ts` — 이번 수정 대상 (`apiSSE` 85-99행, `parseSSE` 102-125행, `parseFrame` 127-140행)
- `/frontend/src/features/interview/viewmodels/useInterview.ts` — SSE 소비 경로 (무변경 확인용)
- `/docs/INTERVIEW-TURN-CONTRACT.md` — step 0에서 추가된 스트림 전송 계층 keepalive 섹션
- `frontend/src`에서 `apiSSE`·`parseSSE`의 전체 호출부를 grep으로 확인하라 (`Grep "apiSSE\|parseSSE"`) — 시그니처 하위 호환을 유지해야 하므로 모든 호출부를 알아야 한다.

배경: step 0(백엔드)이 유휴 구간에 `: ping` 코멘트 프레임을 흘린다(기본 15초 간격).
하지만 프론트는 아무 타임아웃이 없어 백엔드 죽음/half-open/LLM 정체 시 `reader.read()`
에서 영구 대기하고, "소스 문서와 팩트를 정리하는 중…" 라벨이 영구 고착된다.
이 step은 프론트에서 바이트 청크 기준 유휴 판정으로 이러한 정체를 감지하고, 사용자를
재제출 가능 상태로 복귀시킨다. `useInterview.ts`의 시그니처는 변경하지 않는다 —
오류는 기존 catch 경로로 자연 복귀한다(busy/status 해제·입력 유지·재제출 가능).

## 작업

`frontend/src/api/client.ts`만 수정한다:

### 1. 유휴 상수

```typescript
const SSE_IDLE_TIMEOUT_MS = 60_000; // 서버 keepalive(15s)의 4배 — 4회 소실 판정
```

서버 keepalive가 꺼진 배포에서도 동작하는 본수(本 수) 방어로 이 값으로 한다.

### 2. `parseSSE` — 선택적 옵션 파라미터 (하위 호환)

```typescript
export async function parseSSE(
  stream: ReadableStream<Uint8Array>,
  onEvent: (ev: SseEvent) => void,
  opts?: { idleTimeoutMs?: number; signal?: AbortSignal },
): Promise<void>
```

- **바이트 청크 기준** 유휴 판정이다 — `reader.read()`가 청크를 돌려줄 때마다 타이머를
  리셋한다. 파싱된 이벤트 기준이 아니다 — 이유: `: ping` 코멘트 프레임은 `parseFrame`
  이 null로 무시하지만 바이트는 흐르므로, 코멘트도 유효 활동으로 간주해야 백엔드
  keepalive가 방어선으로 동작한다.
- 유휴 초과 처리: 자기 자신은 스트림을 abort할 수 없으므로 `opts.signal`이 abort되는
  방식으로 구현한다(`AbortController`는 `apiSSE`가 소유 — 아래). 타이머 만료 시
  타이머 소유 측에서 abort한다.
- `opts`가 없거나 `idleTimeoutMs`가 0/음수이면 타임아웃 없음 — 기존 동작과 동일
  (하위 호환 잠금).
- 타임아웃을 쓰든 안 쓰든 기존 이벤트 파싱 동작은 무변경이어야 한다.

### 3. `apiSSE` — 내부 AbortController + 유휴 감지 에러

```typescript
export async function apiSSE(
  path: string,
  body: unknown,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,          // 기존 시그니처 유지
  idleTimeoutMs: number = SSE_IDLE_TIMEOUT_MS,
): Promise<void>
```

- 내부 `AbortController`를 만들고 fetch에 주입한다. 외부 `signal`이 있으면 외부 signal
 의 abort 이벤트가 내부 controller를 abort하도록 연결한다(addEventListener 후 정리).
  외부 시그니처는 유지 — 기존 호출부(`useInterview.ts` 포함)를 수정할 필요가 없다.
- fetch 응답이 오면 `parseSSE(res.body, onEvent, { idleTimeoutMs, signal: controller.signal })`
  로 소비하고, 별도 타이머(청크 도착마다 리셋하는 것은 parseSSE의 책임이 아니라 apiSSE
  가 소유한 타이머가 parseSSE의 활동 콜백… 로 재량 구현 — 단, "청크마다 리셋"이 실제로
  동작하는 것이 AC다)에서 유휴 초과 시 `controller.abort()`를 호출한다.
- 유휴로 abort된 경우 `reader.read()`가 내는 AbortError를 잡아 의미 있는 오류로
  재던진다:

```typescript
throw new ApiError(504, "서버 응답이 지연되어 연결을 종료했습니다 — 다시 시도해 주세요");
```

  핵심 규칙(재량 금지):
  - **유휴로 abort된 경우만** ApiError(504)로 변환한다 — 외부 signal 수동 취소나
    fetch 단계의 AbortError는 그대로 전파한다(다른 의미의 취소다).
  - 오류 문자열 위 값을 그대로 쓰라 — 사용자 노출 메시지(`useInterview` catch →
    `errMsg` → setError)이므로 행동 지침이 담겨야 한다.
- 정상 종료·오류 종료 모두 타이머를 반드시 정리한다(`clearTimeout` — finally에서).

### 4. `useInterview.ts`는 수정하지 않는다

- 이유: 시그니처 무변경 설계. `ApiError(504)`는 `run()`의 catch로 들어가 `setError`
  → `finally`에서 busy/status 해제 → 답변 입력 유지(ok=false) → 재제출 가능. 이미
  원하는 복귀 동작이 구현되어 있다.
- 다만 `apiSSE`/`parseSSE`의 **다른 호출부가 있다면**(grep으로 확인) 모두 컴파일되는지
  확인한다 — 선택적 파라미터라 기존 호출부는 무수정이 정상이다.

## Acceptance Criteria

```bash
npm run build   # frontend/에서 — tsc --noEmit 포함
```

## 검증 절차

1. 위 AC 커맨드를 실행한다 (frontend/ 디렉토리에서).
2. 아키텍처 체크리스트를 확인한다:
   - View(`views/`)에서 fetch·서버 데이터 로직을 직접 다루지 않았는가? (가이드 §4.3 —
     이 step은 `api` 레이어만 만진다)
   - `src/api/types.gen.ts`를 손으로 편집하지 않았는가? (자동 생성물)
3. 결과에 따라 `phases/sse-keepalive/index.json`의 step 1을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `useInterview.ts`·View 컴포넌트를 수정하지 마라. 이유: 본 step의 복구 동작(오류
  표시·busy 해제·입력 유지)은 기존 catch 경로가 이미 제공한다 — 불필요한 시그니처
  변경은 기존 feature 계약을 흔든다.
- `apiSSE`의 기존 4개 파라미터 시그니처를 바꾸지 마라. 이유: 호출부 무변경이 설계
  의도고, step 0 계약 문서에 명시된 결합 방식이다.
- `types.gen.ts`를 편집하지 마라. 이유: 자동 생성물 — 손편집은 재생성 시 유실된다.
- 기존 테스트·다른 feature의 코드를 이번 사유로 수정하지 마라. 이유: 프론트에는
  lint·테스트 설정이 없어 `npm run build`(tsc)가 유일한 회귀 감지선이다 — 범위 외
  수정은 감지 없이 회귀를 심는다.