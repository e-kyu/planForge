# Step 3: upload-api-zip-and-upload-result

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/ARCHITECTURE.md` — 모듈 경계 (presentation은 application의 공개 함수만 경유)
- `/docs/ADR.md` — 계층 배치·결정 14 (개요 문서는 건드리지 않음)
- `/backend/app/modules/sources/presentation/api.py` — step 1 완료 상태 (`_list_dir` 재귀,
  `{name:path}` 라우트, `_validated_source_path` 재설계)
- `/backend/app/modules/sources/presentation/schemas.py` — `SourceOut`·`OverviewOut` 계약
- `/backend/app/modules/sources/application/zip_sources.py` — step 2 완료 (`extract_zip` 계약)
- `/backend/app/shared/workspace.py` — `SourceError`·검증 유틸 · zip 상수(최종값 확인)
- `/tests/test_sources_api.py` · `/tests/test_sources_zip.py`

이전 step에서 하위경로 접근·zip 추출 코어가 완성되었다. 이 step은 둘을 API 계약으로 묶는다.

## 작업

### 1. `backend/app/modules/sources/presentation/schemas.py`

```python
class SkipOut(BaseModel):
    name: str    # 스킵된 멤버의 원명(정규화 전) — 사용자가 원본 zip과 대조 가능하게
    reason: str

class UploadResult(BaseModel):
    saved: list[SourceOut]
    skipped: list[SkipOut]
```

`SourceOut` 구조는 불변이다 (name의 값이 상대경로가 되는 것만 이미 정해짐).

### 2. `backend/app/modules/sources/presentation/api.py` — `upload_source` 변경

```python
@router.post("/sources", status_code=201, response_model=UploadResult)
def upload_source(project_id: int, file: UploadFile, db=..., settings=...):
```

분기 로직:

1. `data = file.file.read()` 후 `Path(file.filename or "").suffix.lower() == ".zip"` 분기.
2. **zip 경로**: `try: extract_zip(data, src)` — `SourceError`는 `http_409`로 변환
   (전체 거부; 이 시점은 2페이즈 설계상 어떤 파일도 기록되지 않았다).
   성공 시 rel 목록으로 `SourceOut(name=rel, size, dir="project", mtime)` 구성,
   스킵 목록은 `SkipOut`으로 변환해 응답에 담는다. **saved가 0건이고 skipped만 있어도
   201** — 스킵 보고가 응답 본문의 책임이다.
3. **단일 파일 경로**: 기존 `validate_source_file` → `SourceError`는 기존대로 **409**.
   이 경로의 시맨틱은 변경 금지 — 사용자가 명시적으로 고른 파일 하나의 거부는 스킵이
   아니라 거부가 계약이다 (zip 멤버 스킵과의 경계를 문서화: "사용자 명시 선택 vs 일괄
   해제 결과"). 성공 시 `UploadResult(saved=[SourceOut(...)], skipped=[])` 래핑.
4. docstring/comments에 다음을 문서화한다:
   - 응답 계약이 단일 `SourceOut` → `UploadResult`로 확장되었다는 것
   - zip 멤버 덮어쓰기 금지는 스킵 보고로 원칙을 유지한다는 것
   - `.zip` 자체는 소스로 저장되지 않는다는 것 (해제 결과만 소스가 된다)

`_SOURCE_MEDIA`에 `.zip` 항목을 추가하지 마라 — zip은 download 대상 경로를 통과하지
않는다(sources/에 저장되지 않음).

### 3. 테스트 갱신 `tests/test_sources_api.py`

- 기존 upload 성공·실패 테스트의 응답 단언을 래핑 구조로 갱신
  (`body["saved"]` 접근 — 성공 시 `saved` 1건, 이름/크기 단언은 기존과 동일). 거부(409)
  테스트는 단언 방식 불변.
- 신규 zip 통합 케이스 (메모리 `zipfile` 생성):
  - 201, `saved`에 하위 경로 포함(`sub/메모.md`), 실제로 `db_env` 워크스페이스
    `sources/sub/메모.md`에 저장됨 검증
  - skipped 응답에 원명·사유 포함
  - 손상 zip → 409, 워크스페이스에 아무 파일도 생기지 않음
  - 단일 파일 409 여전 (래핑과 무관하게 시맨틱 보존)
- `tests/test_sources_zip.py`(step 2)는 무수정 통과해야 한다.

## Acceptance Criteria

```bash
python -m pytest tests/test_sources_api.py tests/test_sources_zip.py -q   # 저장소 루트에서
```

## 검증 절차

1. 위 AC 커맨드를 실행한다 (회귀 포함: `python -m pytest tests/test_sources_context.py tests/test_sources_api.py tests/test_sources_zip.py -q`).
2. 아키텍처 체크리스트를 확인한다:
   - presentation이 application(`extract_zip`)만 경유하고 zip 로직을 api.py에 두지 않았는가?
   - interview 모듈·facade를 건드리지 않았는가? (수정 불요)
   - 덮어쓰기 금지 원칙 위반이 없는가? (zip 멤버 충돌 = 스킵, 절대 미기록)
3. 결과에 따라 `/phases/sources-zip-upload/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 즉시 중단

## 금지사항

- 단일 파일 업로드의 409 거부를 zip과 같은 "스킵 보고"로 바꾸지 마라 — 이유: 명시적 선택 파일의
  거부를 조용히 스킵하면 사용자가 실패를 인지하지 못한다 (기존 계약 회귀).
- `SourceOut`의 필드를 추가·삭제하지 마라 — 이유: step 4에서 OpenAPI 재생성 diff를
  `UploadResult`/`SkipOut` 추가로 최소화한다 (`npm run gen:types` 계약).
- `extract_zip`의 시그니처·반환 규약을 바꾸지 마라 — 이유: step 2에서 계약이 고정되었다;
  api.py는 소비만 한다. 정말 필요하면 zip_sources.py 내부 수정은 가능하나 그 경우 step 2
  테스트가 회귀하지 않도록 함께 확인하라.
- `GET/PUT /overview`·개요 문서 계약을 건드리지 마라 — 이유: 개요 문서는 플랫 고정 특수
  소스로 이 phase의 영향 범위 밖이다 (ADR 결정 14).
- 기존 테스트를 깨뜨리지 마라.