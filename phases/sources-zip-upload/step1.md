# Step 1: source-path-guard-and-recursive-listing

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/ARCHITECTURE.md` — 모듈 경계 규칙 (sources는 facade+presentation만, DB 테이블 없음)
- `/docs/ADR.md` — 결정 14 (개요 문서 계약 — `GET/PUT /overview`와 소스 경로의 대칭)
- `/backend/app/modules/sources/presentation/api.py` — 이 step의 대상 파일 전체
- `/backend/app/shared/workspace.py` — step 0에서 `read_sources_context`가 재귀화되었으므로 현재 상태 확인
- `/tests/test_sources_api.py` — 기존 API 계약 (409/UTF-8/2MB/traversal 케이스)

이전 step에서 `read_sources_context`가 재귀화되었다. 이 step은 sources presentation 계층의
목록·경로 접근을 하위 디렉터리 구조에 맞게 확립한다. zip 코드는 이 step에서 만들지 않는다.

## 작업

`backend/app/modules/sources/presentation/api.py`만 수정한다.

1. `_list_dir(d, dir_label)` 재귀화:

```python
def _list_dir(d: Path, dir_label: str) -> list[SourceOut]:
    files = sorted((f for f in d.rglob("*") if f.is_file()),
                   key=lambda f: f.relative_to(d).as_posix())
    # 각 파일: SourceOut(name=f.relative_to(d).as_posix(), size, dir, mtime)
```

   - `name`이 POSIX 상대경로가 된다 (`SourceOut` 스키마 구조 자체는 불변).
   - 플랫 소스는 상대경로 == 파일명이라 기존 출력과 동일 → 기존 테스트 무수정 통과.

2. `_validated_source_path(src, name)` 재설계 — 하위 상대경로 허용, 트래버설·절대경로 차단:

```python
def _validated_source_path(src: Path, name: str) -> Path:
    """DELETE·download 공용 — sources/ 내 상대 하위경로만 허용한다."""
    parts = [p for p in (name or "").replace("\\", "/").split("/") if p]
    if not parts or any(p == ".." for p in parts) or \
       (len(parts) == 1 and len(parts[0]) > 1 and parts[0][1] == ":" and parts[0][0].isalpha()):
        raise http_404(...)   # 빈 경로·트래버설·절대경로(드라이브 포함) 차단 — 404 통일
    target = (src / Path(*parts)).resolve()
    if not (target.is_file() and target.is_relative_to(src.resolve())):
        raise http_404(...)
    return target
```

   - 기존의 "이름에 `/`, `\`, `..` 포함 시 404" 규칙을 "하위 상대경로 허용 + `..`·절대경로 차단 +
     `resolve()` containment 검사"로 교체한다. 누설 방지를 위해 거부 응답은 404로 통일한다.
   - `\`는 성분 분해 전 `/`로 치환해 처리한다 (URL에서 `%5C`가 서버 도달 전 구분자로 해석될 수
     없으므로 구분자 문자 자체가 경로 침투다).
   - containment(`is_relative_to(src.resolve())`)는 resolve 경로 조작(예: 동일 디렉터리 심링크)
     최종 방어선이다.

3. 라우트 변환 — 하위 경로가 name에 슬래시를 포함하므로 단일 세그먼트 매처를 path로 바꾼다:
   - `@router.delete("/sources/{name:path}")`
   - `@router.get("/sources/{name:path}/download")`
   - `@global_router.get("/{name:path}/download")`
   - `POST /sources`, `GET /sources`와 라우트 충돌이 없어야 한다(FastAPI가 exact 매칭 우선).
   - 글로벌 라우트는 prefix가 `/api/sources` 전체이므로 `""`(목록) exact 라우트와의 우선순위를
     실제로 확인한다.

4. 빈 디렉터리 정리는 하지 않는다 — 삭제(`delete_source`)는 파일 `unlink()`만 하고, 비게 된
   하위 디렉터리는 잔존시킨다 (목록에 파일만 나오므로 사용자 영향 없음).

`tests/test_sources_api.py` 갱신:
- 기존 traversal 테스트(`..%2Fplan.md`, `..%5Cplan.md`, `%2E%2E` 변형)는 무수정으로 404 회귀해야 한다.
- 신규 케이스 (`db_env` fixture에서 워크스페이스 `sources/` 아래 `회의/sub노트.md` 직접 기록):
  - 목록 GET에서 `name == "회의/sub노트.md"` 확인
  - 하위경로 delete roundtrip (`DELETE /api/projects/{pid}/sources/{quoted}` 후 목록에서 소멸)
  - 하위경로 download roundtrip (내용 일치)
  - download가 여전히 sources/ 밖으로 못 나가는지 (예: `/sources/sub/..%2Fx.md` 형태 변형)
- URL을 만들 때 하위경로는 `urllib.parse.quote("회의/sub노트.md")` 사용 — TestClient의
  `%2F` 사전 디코딩 동작에 따라 단언 방식을 고정하고, 필요 시 서버가 실제로 받는 경로를
  확인해 라우트가 정상 매칭되는지 먼저 검증한다.

## Acceptance Criteria

```bash
python -m pytest tests/test_sources_api.py -q   # 저장소 루트에서
```

기존 테스트(업로드/목록/삭제 roundtrip, 확장자·UTF-8·2MB 거부, 동명 409, traversal 404,
글로벌 읽기전용, 개요 문서)가 무수정 통과하고 하위경로 신규 케이스가 추가되어야 한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다 (step 0 테스트도 함께: `python -m pytest tests/test_sources_context.py tests/test_sources_api.py -q`).
2. 아키텍처 체크리스트를 확인한다:
   - sources 모듈 밖 파일을 수정하지 않았는가? (이 step은 presentation/api.py와 테스트만)
   - DELETE·download가 여전히 sources/ 밖 접근을 차단하는가?
   - 덮어쓰기 금지(409) 규칙을 건드리지 않았는가?
3. 결과에 따라 `/phases/sources-zip-upload/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 즉시 중단

## 금지사항

- `SourceOut` 스키마(필드 구조) 변경 금지 — 이유: step 3에서 `UploadResult` 래핑으로 계약을
  확장하며, 구조 불변이 유지되어야 그 diff가 최소화된다.
- `_validated_source_path`의 거부 응답을 404가 아닌 다른 상태 코드로 바꾸지 마라 — 이유:
  존재 여부 누설 방지를 위해 기존 404 통일 규약이 유지된다.
- 라우트를 `{name:path}`로 바꿀 때 글로벌 목록 라우트(`@global_router.get("")`)를 건드리지
  마라 — 이유: 글로벌 소스는 읽기 전용 계약(운영자 배치)이며, 라우트 우선순위 역전 시
  목록이 다운로드로 흡수된다.
- 이 step에서 zip 추출 코드·`UploadResult` 스키마를 미리 만들지 마라 — 이유: step 2·3이
  각각 다룬다 (scope 최소화).
- 기존 테스트를 깨뜨리지 마라.