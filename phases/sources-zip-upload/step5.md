# Step 5: frontend-zip-accept-and-report

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 프론트엔드 feature-MVVM 구조·View 데이터 로직 금지 (가이드 §4.3)
- `/docs/ARCHITECTURE.md` — D-9 Feature-driven MVVM (models/viewmodels/views 분리)
- `/docs/ADR.md` — TanStack Query 패턴 (useQuery/useMutation+무효화)
- `/frontend/src/api/types.gen.ts` — step 4에서 재생성된 `UploadResult`/`SkipOut` 타입
- `/frontend/src/api/client.ts` — `apiUpload` 공용 헬퍼·`SourceFile` alias
- `/frontend/src/features/sources/models/sourcesApi.ts` — step 5의 대상 1
- `/frontend/src/features/sources/viewmodels/useSources.ts` — step 5의 대상 2
  (`MAX_MB` 선거부, 뮤테이션·무효화)
- `/frontend/src/features/sources/views/SourcesPanel.tsx` — step 5의 대상 3
  (accept·안내문·목록·배너)
- `/frontend/src/shared/components/ui.tsx` — `Banner`·`Button`·`Empty`·`fmtBytes` 조합

백엔드(zip 해제·재귀 목록·UploadResult 계약)와 타입(regen)이 완료되었다. 이 step은 프론트
sources feature를 새 계약에 맞춘다.

## 작업

models → viewmodels → views 순서로 수정한다.

### 1. `frontend/src/features/sources/models/sourcesApi.ts`

```typescript
export const uploadSource = (pid: number, file: File) =>
  apiUpload<UploadResult>(`/api/projects/${pid}/sources`, file);
```

- 리턴 타입을 `SourceFile` → `UploadResult`(types.gen.ts)로 변경.
- `SourceFile` alias 사용처를 확인하고, 남는 참조가 있으면 유지 (구조 불변).

### 2. `frontend/src/features/sources/viewmodels/useSources.ts`

- `uploadM.mutationFn` 확장: 각 파일에 대해 기존 클라 선거부(`MAX_MB * 1024 * 1024` —
  zip 포함 동일 2MB) 유지, `uploadSource` 응답을 누적해 리턴.
- 신규 상태 `uploadReport`:

```typescript
export type UploadReport = {
  savedCount: number;
  skipped: { name: string; reason: string }[];
} | null;
```

  - 훅 리턴에 `uploadReport` 추가, 다음 업로드 시작 시 클리어.
  - 단일 파일 POST 응답도 동일 `UploadResult` 타입이므로 파일 분기 불요.
  - 기존 `refresh()` 무효화 패턴(`["sources", pid]`·`["sources", "global"]`) 불변.

### 3. `frontend/src/features/sources/views/SourcesPanel.tsx`

- `accept=".md,.txt,.json,.csv,.zip"` (multiple 유지)
- 안내문 갱신: zip 해제 지원·"zip 내부도 동일 규칙(확장자·2MB·UTF-8)"·"덮어쓰기는 하지 않음" 명시.
- `uploadReport` 렌더:
  - `skipped.length > 0`면 `Banner`(에러가 아닌 정보 계열)로 스킵 목록 `이름 — 사유` 나열.
  - `savedCount > 0`면 저장 개수 표시 (쿼리 무효화로 목록은 이미 갱신됨).
- 하위경로 소스(name에 `/` 포함): UI 표시는 상대경로 그대로 — zip 구조가 사용자에게 보이는
  것이 요구다. `extOf` 확장자 배지는 `name`이 `/`를 포함해도 마지막 성분 확장자로 정확히
  동작하는지 확인하고 필요시 조정.
- `downloadHref`·삭제 모달은 현재 `encodeURIComponent(name)` 그대로 하위경로에서 동작함을
  확인 (백엔드 `{name:path}` 라우트와 짝). 무수정이 정상.

프론트 단위 테스트 인프라는 없다 — AC는 tsc 포함 빌드 1회. 백엔드 통합 회귀는 이전 step의
테스트가 담당한다.

## Acceptance Criteria

```bash
# frontend에서
npm run gen:types    # step 4 완료 후 재실행로 최신 유지 (변경 없어야 정상)
npm run build        # tsc --noEmit 포함
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - View에 fetch·서버 데이터 로직을 추가하지 않았는가? (가이드 §4.3 — viewmodel 훅 경유)
   - models/viewmodels/views 경계를 유지했는가? (uploadReport 로직은 viewmodels에)
   - TanStack Query 무효화 패턴을 유지했는가?
3. 결과에 따라 `/phases/sources-zip-upload/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 즉시 중단

## 금지사항

- View 컴포넌트에 fetch·API 직접 호출을 넣지 마라 — 이유: 프로젝트 계약상 View는 표현 전용이며
  서버 데이터는 반드시 viewmodel 훅을 경유한다 (가이드 §4.3).
- `types.gen.ts`를 손으로 편집하지 마라. 이유: 자동생성물이다; 표시 로직 조정이 필요하면
  feature 코드에서 alias/파생 타입으로 처리하라.
- 클라 선거부(2MB)를 제거하거나 zip에 완화하지 마라 — 이유: 백엔드 zip 자체 한도가 2MB로
  고정되어 있어 클라 완화는 UX만 나쁘고 거부 409를 유발한다.
- 서버에 이미 존재하는 소스에 대한 UI 덮어쓰기 유도를 만들지 마라 — 이유: 덮어쓰기 금지(409)는
  "소스도 기록의 일부"라는 계약이다.
- 기존 기능(개요 편집기·삭제 모달)을 깨뜨리지 마라.