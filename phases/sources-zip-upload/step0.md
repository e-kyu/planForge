# Step 0: recursive-sources-context

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/ARCHITECTURE.md` — 모듈 경계 규칙·공용 소스 파일(fs 네이티브) 구조
- `/docs/ADR.md` — 결정 14 (개요 문서 fs 네이티브, sources는 파일이 곧 SSOT)
- `/backend/app/shared/workspace.py` — 109행부터 소스 파일 섹션: `SOURCE_EXTS`, `validate_source_file`, `read_sources_context`
- `/backend/app/modules/interview/application/agent.py` — `read_sources_context`의 유일한 소비자 (매 턴 주입)
- `/tests/test_sources_context.py` — 기존 계약 (기존 7개 테스트가 회귀 기준)
- `/tests/conftest.py` — 테스트 환경

기존 테스트를 먼저 실행해 현재 녹색 상태를 확인하고, 설계 의도(파일당·전체 예산, 절단 마커)를 이해한 뒤 작업하라.

## 작업

`backend/app/shared/workspace.py`의 `read_sources_context`만 재귀 탐색으로 수정한다.
이 phase는 "소스 업로드 zip 지원"의 첫 단계로, zip 해제 전에 하위 디렉터리 소스 주입을
먼저 확립한다. 이 step에서 zip 코드는 만들지 않는다.

시그니처는 변경 금지:

```python
def read_sources_context(sources_dirs: list[Path],
                         max_chars: int = MAX_SOURCE_FILE_CHARS,
                         total_chars: int = MAX_SOURCE_TOTAL_CHARS) -> str:
```

변경 요구:

1. 순회를 `sorted(d.iterdir())` → 하위 디렉터리 포함 재귀로 교체:
   ```python
   files = sorted((f for f in d.rglob("*") if f.is_file()),
                  key=lambda f: f.relative_to(d).as_posix())
   ```
   정렬 키는 POSIX 상대경로 문자열(코드포인트 비교) — Windows/Linux 출력이 같아야
   하는 결정론 필수. `sorted(d.iterdir())`의 기존 "디렉터리 순 → 이름순"은 그대로
   유지된다(`sources_dirs` 인자 순서 = 디렉터리 순서).
2. 주입 헤더를 `### 소스: {f.relative_to(d).as_posix()}`로 변경. 플랫 파일은
   상대경로 == 파일명이므로 기존 출력과 동일하다 (기존 테스트 무수정 통과의 근거).
3. 다음은 전부 불변 (변경하면 안 되는 기존 계약):
   - `SOURCE_EXTS` 화이트리스트 필터 (`f.suffix.lower() not in SOURCE_EXTS` → 스킵)
   - `f.read_text(encoding="utf-8-sig")` + `UnicodeDecodeError/OSError` 시 무음 스킵
   - 파일당 16,000자 / 전체 48,000자 greedy 예산 배분
   - 절단 마커 `...(절단: 주입 상한 {budget:,}자 초과)`
   - 미주입 마커 `(전체 상한 도달로 미주입: {', '.join(skipped)})`
   - `not d.is_dir()` 시 디렉터리 스킵

`tests/test_sources_context.py`에 신규 케이스를 추가한다 (tmp_path 기반, 기존 스타일):
- `sub/nested.md` 파일이 주입되고 헤더가 `### 소스: sub/nested.md`인지 단언
- 최상위 파일 + 하위 파일을 섞어 배치하고 명시적 순서 단언 (예: `a.md` < `sub/z.md`)
- 하위 디렉터리 안의 비UTF-8 파일·비화이트리스트 파일도 스킵됨을 단언

## Acceptance Criteria

```bash
python -m pytest tests/test_sources_context.py -q   # 저장소 루트에서
```

기존 7개 테스트가 무수정으로 통과하고 신규 케이스가 추가되어야 한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `read_sources_context`의 시그니처·기본값·문자열 마커를 변경하지 않았는가?
   - docs/ARCHITECTURE.md 모듈 경계 규칙 위반이 없는가? (이 step은 shared만 수정)
   - CLAUDE.md 설계 원칙 계약 8개를 위반하지 않는가?
3. 결과에 따라 `/phases/sources-zip-upload/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 즉시 중단

## 금지사항

- `read_sources_context`의 시그니처·기본 상수값·절단/미주입 마커 문자열 변경 금지 — 이유: interview 에이전트가 매 턴 의존하는 공용 계약이며 변경 시 주입 컨텍스트 품질 계약이 깨진다.
- 하위 경로를 `os.sep`(Windows에서 `\`)로 출력 금지 — 이유: LLM 프롬프트 안정성과 크로스플랫폼 결정론을 위해 `as_posix()` 고정이 설계 의도다.
- 이 step에서 `validate_source_file`·`sanitize_source_filename` 등 다른 함수 수정 금지 — 이유: step 0은 read_sources_context 재귀화만 다룬다 (scope 최소화).
- 기존 테스트를 깨뜨리지 마라 — 특히 `sources/default_architecture_guidelines.md` 온전 주입 회귀 테스트.
- `workspaces/` 아래 직접 쓰기 금지 — 이유: SSOT 가드훅이 차단하는 파생물 경로다. fixture는 tmp_path를 사용한다.