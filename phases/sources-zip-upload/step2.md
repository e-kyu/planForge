# Step 2: zip-extraction-core

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/ARCHITECTURE.md` — 모듈 경계 규칙 (application 계층에 순수 유스케이스 로직 위치)
- `/docs/ADR.md` — 계층 배치 결정 (presentation/application/infrastructure/domain)
- `/backend/app/shared/workspace.py` — 소스 검증 섹션(`SOURCE_EXTS`, `validate_source_file`,
  `sanitize_source_filename`, `SourceError`) — step 0에서 read_sources_context 재귀화 완료
- `/backend/app/modules/sources/presentation/api.py` — step 1에서 `_list_dir` 재귀·
  `{name:path}` 라우트 완료 (zip 결과가 최종적으로 어떤 계약에 맺혀야 하는지 파악)
- `/tests/test_sources_zip.py` (아직 없음 — 이 step에서 신규 생성)
- `/tests/test_sources_context.py` — 단위 테스트 패턴 참고 (tmp_path 기반)

이전 step 목록·읽기 계층이 하위 디렉터리를 지원한다. 이 step은 zip 바이트 → sources/ 기록의
순수 추출 코어를 만든다 (API 결합은 step 3).

## 작업

### 1. `backend/app/shared/workspace.py`에 상수·헬퍼 추가

```python
MAX_ZIP_MEMBERS = 200                       # zip 멤버 수 상한 (채택+기각 포함)
MAX_ZIP_UNCOMPRESSED_BYTES = 8 * 1024 * 1024  # zip 압축 전 합계 상한 (zip-bomb 방어)

def sanitize_source_relpath(member: str) -> str | None:
    """zip 멤버 상대경로 → 성분별 정규화된 POSIX 상대경로. 구조적 기각 시 None."""
```

정규화 규약 (설계 의도 — 반드시 준수):
- 멤버 경로를 `/`·`\`로 성분 분해.
- **기각(반환 None, 치환하지 않음)**: 절대경로(선도 `/` 또는 `\`), 드라이브 성분(`c:` 등),
  `..` 성분, `.` 성분, `__MACOSX*` 성분, `._*` 성분, `.`으로 시작하는 숨김 성분,
  최종 성분이 비는 경우(디렉터리만 남는 등).
- **치환**: 각 성분에 기존 `sanitize_source_filename`과 동일 규약 적용 — 금지문자
  (`<>:"/\|?*`)는 `_` 치환, 트레일링 공백/점 제거.
- 반환: 성분을 `/`로 조인한 POSIX 상대경로.
- 구조적 취약점(`..` 등)은 치환해 통과시키지 않고 기각한다 — 이유: zip 해제는 사용자가
  정확히 검증할 수 없는 일괄 경로이므로 안전 쪽(기각)이 설계 의도다.

### 2. 신규 `backend/app/modules/sources/application/zip_sources.py`

```python
"""zip 소스 추출 (소스 zip 지원) — presentation 미의존 순수 로직."""

def extract_zip(data: bytes, dest: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """zip 바이트 → (저장된 상대경로 목록, 스킵 목록 [(멤버 원명, 사유)])."""
```

구현 규칙 (핵심 — 설계 의도에서 벗어나면 안 되는 것):

- **`ZipFile.extract()` / `extractall()` 사용 절대 금지** — 이유: 멤버 이름이 그대로
  파일시스템 경로가 되어 Zip Slip이 성립한다. 반드시 `zf.open(info).read()`로 바이트만 꺼내
  `sanitize_source_relpath`로 정규화한 상대경로에 직접 `mkdir`(parents) + `write_bytes`한다.
- **zip 자체 결함 → `SourceError` 전체 거부** (이 시점 어떤 파일도 기록되지 않아야 한다):
  `zipfile.BadZipFile`, `len(data) > MAX_SOURCE_BYTES`(zip 자체 2MB), 멤버 수 >
  `MAX_ZIP_MEMBERS`, `infolist()`의 `file_size` 합 > `MAX_ZIP_UNCOMPRESSED_BYTES`.
- **2페이즈**: ① 전 멤버 사전 스캔(정규화·확장자·file_size·수집 대상 합 판정) ② 스캔에서
  수집 확정된 멤버만 순서대로 읽고 기록. 사전 스캔에서 스킵 확정된 멤버는 절대 읽지 않는다
  (비화이트리스트 바이너리 멤버를 읽는 비용을 원천 배제).
- **멤버별 스킵 사유 (사전 스캔)**: 디렉터리 엔트리(`is_dir()`), `sanitize_source_relpath` None
  ("지원하지 않는 경로"), 확장자 화이트리스트 외("지원하지 않는 확장자"), `file_size` >
  `MAX_SOURCE_BYTES`("파일이 너무 큽니다").
- **실측 재검사(읽기 직후)**: `zf.open(info).read(MAX_SOURCE_BYTES + 1)`로 상한 걸고 읽은 뒤
  `len(data) > MAX_SOURCE_BYTES` 재검사(메타데이터 위조 방지 이중화). 그 후
  `data.decode("utf-8-sig")` 실패 시 "UTF-8 텍스트 파일만" 스킵.
- **멤버명 인코딩 복원**: `info.flag_bits & 0x800`가 없으면 Python이 cp437로 디코딩한
  `original_filename`에 대해 `orig.encode("cp437").decode("cp949")` 복원 시도 (실패 시 원값
  유지). 한글 Windows 탐색기로 압축한 zip(EUC-KR 멤버명) 대응. 복원 결과도
  `sanitize_source_relpath`에 통과시킨다.
- **충돌 정책 — 덮어쓰기 금지 원칙 유지**: 대상 경로가 ①dest(워크스페이스 sources/)에
  이미 존재하거나 ②본 zip에서 앞서 수집된 경로와 중복이면 스킵 보고
  ("같은 이름의 소스가 이미 있습니다"). 기존 파일은 절대 덮지 않는다.
- **저장 규약**: 검증 통과한 원본 바이트를 그대로 기록한다 (BOM 포함 여부 변형 없음 —
  읽는 쪽 `utf-8-sig`가 처리).
- 사유 문자열은 사용자에게 그대로 보인다 — 한글 명사형 규약 유지.

### 3. 신규 `backend/app/modules/sources/application/__init__.py`

빈 마커(또는 기존 모듈 `__init__.py` 스타일의 최소 docstring)로 패키지화한다.

### 4. 신규 테스트 `tests/test_sources_zip.py`

tmp_path 기반 단위 테스트. zip은 테스트 코드에서 `zipfile`로 메모리 생성한다
(`io.BytesIO`) — `tests/fixtures/`에 zip fixture 파일을 만들지 않는다.
케이스:

- 구조 보존: `sub/회의.md` 멤버 → dest에 `sub/회의.md` 기록, 반환 목록에 상대경로
- 비지원 확장자(`img/logo.png`) → 스킵 보고, 파일 미기록
- 비UTF-8 텍스트(cp949로 인코딩한 `.txt` 바이트) → 스킵 보고
- 트래버설 멤버(`../evil.md`, 절대경로 성분) → 기각 보고, dest 밖에 아무것도 없음
- `__MACOSX/x/_.y.md`·`.DS_Store`류 숨김 성분 → 기각 보고
- cp949 멤버명 복원: `ZipInfo`에 `filename`을 cp437로 강제 인코딩해 넣고(flag_bits에
  0x800 없음) 복원 결과로 저장되는지 — 멤버명에 한글이 살아있는지 단언
- 멤버 2MB+ 초과 → 스킵 보고 (zip 자체는 2MB 이하)
- 기존 소스 충돌: dest에 미리 동명 파일 배치 → 스킵 보고, 기존 파일 내용 불변
- zip 내부 중복 경로 → 두 번째부터 스킵 보고
- 손상 zip(랜덤 바이트) → `SourceError`
- 멤버 수 초과 / 해제 총량 초과 → `SourceError`
- zip 자체 2MB+ → `SourceError`
- 전체 실패 시 dest에 아무 파일도 기록되지 않음을 단언 (디렉터리 생성도 없어도 무방하나
  *파일은 반드시 0개*)

## Acceptance Criteria

```bash
python -m pytest tests/test_sources_zip.py -q   # 저장소 루트에서
```

## 검증 절차

1. 위 AC 커맨드를 실행한다 (회귀 포함: `python -m pytest tests/test_sources_context.py tests/test_sources_api.py tests/test_sources_zip.py -q`).
2. 아키텍처 체크리스트를 확인한다:
   - `application/zip_sources.py`가 presentation·FastAPI를 import하지 않는가? (순수 로직)
   - 모듈 경계: shared workspace의 검증 유틸을 shared 경유로만 사용하는가?
   - CLAUDE.md 설계 원칙 계약 8개를 위반하지 않는가? (특히 덮어쓰기 금지 = 무손실 원칙)
3. 결과에 따라 `/phases/sources-zip-upload/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 즉시 중단

## 금지사항

- `ZipFile.extract()`·`extractall()` 사용 금지 — 이유: 멤버 이름이 곧 파일시스템 경로가 되는
  Zip Slip 경로 자체를 제거하는 것이 이 설계의 핵심 방어 계층이다.
- `..`·절대경로 성분을 치환(예: `_`로)해 통과시키지 마라 — 이유: 일괄 해제 결과는 사용자가
  검증할 수 없으므로 치환이 아니라 기각이 설계 의도다.
- 비화이트리스트 멤버의 바이너리를 읽지 마라 — 이유: 사전 스캔으로 거르지 않으면 압축
  비율 조작(초대형 `video.mp4` 멤버)으로 메모리·CPU가 공격당한다.
- 이 step에서 `presentation/api.py`·`schemas.py`를 수정하지 마라 — 이유: API 결합은 step 3이
  다룬다 (scope 최소화).
- 기존 테스트(`test_sources_context.py`·`test_sources_api.py`)를 깨뜨리지 마라.