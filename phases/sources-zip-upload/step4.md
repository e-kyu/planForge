# Step 4: contract-type-regen

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — "타입 갱신: backend/ `python scripts/export_openapi.py` → frontend/ `npm run gen:types`"
- `/frontend/src/api/types.gen.ts` — 자동생성물 (손편집 금지 — regen으로만 갱신)
- `/backend/app/main.py` — OpenAPI 스키마 출처
- `/frontend/package.json` — `gen:types` 스크립트 정의 확인

step 3까지 백엔드 계약(`UploadResult`/`SkipOut`, `{name:path}` 라우트)이 완성되었다. 이 step은
코드 로직 편집 없이 계약 아티팩트를 재생성해 프론트와 백엔드의 타입 불일치를 해소한다.

## 작업

1. backend/에서 `python scripts/export_openapi.py` 실행 (가상환경 `backend/.venv` 사용).
2. frontend/에서 `npm run gen:types` 실행.
3. 생성된 `frontend/src/api/types.gen.ts`에 다음이 반영되었는지 확인:
   - `UploadResult` 스키마 추가: `{ saved: SourceOut[], skipped: SkipOut[] }`
   - `SkipOut` 스키마 추가: `{ name, reason }`
   - POST `/api/projects/{pid}/sources` 응답이 `SourceOut` → `UploadResult`로 변경
   - DELETE `/api/projects/{pid}/sources/{name}`·download 라우트의 `{name:path}` 반영
   - `SourceOut` 자체는 삭제되지 않음 (목록 응답이 계속 사용)

코드(로직) 편집은 이 step에서 하지 않는다. types.gen.ts에 문제가 있으면 백엔드 스키마
정의(schemas.py)를 regen 후 다시 확인하라 — 생성물을 손으로 고치지 마라.

## Acceptance Criteria

```bash
# backend에서
python scripts/export_openapi.py          # exit 0
# frontend에서
npm run gen:types                          # exit 0
# 저장소 루트에서 (회귀 확인)
python -m pytest tests/test_sources_api.py -q
# frontend에서 (타입 체크 겸용 빌드)
npm run build
```

`git diff frontend/src/api/types.gen.ts`에 `UploadResult`가 포함되어야 한다.

## 검증 절차

1. 위 AC 커맨드를 순서대로 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `types.gen.ts`를 regen 이외의 방법으로 고치지 않았는가?
   - 스키마 diff가 `UploadResult`/`SkipOut` 추가·응답 스키마 변경·`{name:path}` 반영으로
     제한되는가? (의도치 않은 다른 API 시그니처 변조가 없는가)
3. 결과에 따라 `/phases/sources-zip-upload/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 즉시 중단

## 금지사항

- `frontend/src/api/types.gen.ts`를 손으로 편집하지 마라 — 이유: 자동생성물이며 수동 편집은
  다음 regen에서 유실된다.
- 이 step에서 프론트 feature 코드(`sourcesApi.ts` 등)를 수정하지 마라 — 이유: 소비 코드
  변경은 step 5의 scope다. 이 step은 계약 산출물 동기화만 다룬다.
- 기존 테스트를 깨뜨리지 마라.