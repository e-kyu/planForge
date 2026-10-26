# Step 9: facts-compact-and-sources

## 읽어야 할 파일

- `/CLAUDE.md` — 원칙 1(SSOT), 원칙 4(팩트 선적립)
- `/backend/app/modules/facts/application/compact.py`
- `/backend/app/modules/facts/presentation/api.py`
- `/backend/app/modules/sources/application/zip_sources.py`
- `/backend/app/modules/sources/presentation/api.py` — `_validated_source_path` (변경 금지)
- `/backend/app/shared/workspace.py` — zip 상한·경로 정규화
- Step 5 산출물: `app/shared/factline.py`
- `/tests/test_facts_api.py`, `test_compact.py`, `test_sources_zip.py`, `test_sources_api.py`

## 배경

facts compact 미러 재작성과 zip 소스 스캔/쓰기가 긴 함수에 섞여 있다. 단일 책임
함수로 나눈다. **압축 의미·zip 보안·미러 경로·문구는 불변**이다.

## 작업

### 1. `compact.py`

- `fact_line(f, marker="")`가 `app.shared.factline.format_fact_line(...)`에 위임하도록
  바꾼다. 공개 이름과 출력은 그대로.
- `(미확정)` 매칭은 **exact**(`UNCONFIRMED_EXACT`)를 유지한다 — prefix로 넓히지 않는다.
- `clean_groups`/`select_archives`의 정렬·경고·archive 제외 규칙을 바꾸지 않는다.

### 2. `facts/presentation/api.py`

`compact_preview`를 다음 역할로 분해한다:

- 활성 팩트 로드
- LLM 호출 (`run_llm_compact`)
- preview 응답 조립

`compact_apply`를 다음 역할로 분해한다:

- 선택 변경 검증/archive 대상 산출
- 미러 재작성(루트 + 문서별)
- 응답 조립

미러 규칙 유지:

- 팩트 소속 세션의 `doc_slug`별 루트(`doc_ws_root(..., doc_layout=True)`)를 따른다.
- 루트 미러(`ws`)는 레거시(None) 소속 팩트만 남긴다.
- `docloops.resolve_workspace_root`로 바꾸지 않는다 — 레거시 프로젝트의 문서 세션도
  문서 하위를 써야 하는 기존 계약이 있다.

### 3. `zip_sources.py`

`extract_zip`을 다음 역할로 분해한다:

- `_scan_member(...)` — 멤버 검사·채택/기각 판정
- `_admit_member(...)` — 크기/경로/중복 검사
- `_write_member(...)` — 실제 쓰기

보존:

- 2단계 스캔/쓰기 순서
- 모든 skip/기각 사유 문자열과 `saved`/`skipped` 리스트 순서
- 상한(`MAX_ZIP_MEMBERS`, `MAX_ZIP_BYTES`, `MAX_ZIP_UNCOMPRESSED_BYTES`)
- 덮어쓰기 금지·트래버설 방어·CP949 이름 처리

### 4. 유예

- `_validated_source_path`의 보안 동작 통합(D22)은 하지 않는다.
- zip 상한 값·비율을 바꾸지 않는다.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_facts_api.py tests\test_compact.py tests\test_sources_zip.py tests\test_sources_api.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - `(미확정)` 매칭 의미가 바뀌지 않았는가?
   - archive/keep 의미·경고 문구·미러 경로가 동일한가?
   - zip 기각 사유·리스트 순서·상한이 동일한가?
3. `phases/refactor-standalone-cli/index.json`의 step 9를 갱신한다.

## 금지사항

- `(미확정)`을 prefix 매칭으로 넓히지 마라. 이유: compact의 archive 제외 동작이 바뀐다.
- zip 경로/보안 검증을 통합하지 마라. 이유: 보안 동작 변경은 별도 검토가 필요하다.
- 미러 경로 규칙을 `resolve_workspace_root`로 일괄 치환하지 마라. 이유: facts의
  `doc_layout=True` 예외가 레거시 문서 세션을 보존한다.
