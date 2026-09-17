# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 기획 문서 프로젝트

고객사별 프로젝트 단위로 제안서·개발설계서 등 기획 문서 콘텐츠를 관리하고, 하나의 plan.md에서 PPT·문서(md/html/docx)로 산출물을 파생시키는 다중 포맷 저장소다.

## 명령어

- **PPT 생성**: `python scripts/build_ppt.py <프로젝트>/work/slides.json` (저장소 루트에서 실행 권장 — 스크립트가 같은 디렉토리의 `theme.py`를 import). 출력은 입력 slides.json 위치에서 유도된다 (`<프로젝트>/work/slides.json` → `<프로젝트>/output/`). 2번째 인자로 출력 디렉토리 override 가능.
- **문서 생성**: `python scripts/build_doc.py <프로젝트>/work/report.json <md|html|docx>` — 포맷·[output_dir] 인자는 순서 무관하게 인식한다. 출력 유도·채번 규칙은 build_ppt.py와 동일하되 **버전 채번은 확장자별 독립 시퀀스**.
- **의존성**: `pip install python-pptx` (PPT), `pip install python-docx` (docx만 — md/html은 표준 라이브러리만으로 동작)
- **스모크 테스트**: `python scripts/build_ppt.py samples/slides.sample.json samples/output`, `python scripts/build_doc.py samples/report.sample.json samples/output md` (html/docx도 동일) — 이때만 `output_name`을 지정해 실제 프로젝트 output과 분리. 개발설계서·구성(arch) 샘플도 동일: `samples/slides.design.sample.json` · `samples/report.design.sample.json`, 태그·표기 참조점은 `samples/plan.sample.md`

## 프로젝트 결정 규칙

- 산출물 작업의 대상 프로젝트는 `projects/<프로젝트명>/` 디렉토리 단위로 특정한다.
- 커맨드 인자로 프로젝트명을 받는다: `/plan-doc ai-agent-doc`
- 인자가 없으면 `projects/*/plan.md`를 나열해 사용자에게 선택받는다. 1개뿐이어도 자동 진행하지 않고 확인한다.
- 프로젝트가 확정되면 세션 내 모든 파일 경로는 `projects/<프로젝트명>/` 기준으로 쓴다. 루트에는 plan.md·docs·work·output이 존재하지 않는다.
- 새 프로젝트 시작: `projects/<새 이름>/`에 `docs/interview-log.md`(헤더만), `work/`, `output/`, `sources/`, `assets/` 디렉토리를 만들고 /plan-doc 진행. 프로젝트명은 ASCII 소문자-하이픈 슬러그 (예: `ai-agent-doc`).

## 워크플로 (반드시 이 순서)

1. **`/plan-doc`** — 인터뷰 및 자료 정리 → `<프로젝트>/docs/interview-log.md`에 팩트 적립 → `<프로젝트>/plan.md` 작성 (모든 포맷의 유일 원본)
2. **산출물 생성** — 필요한 포맷만:
   - `/make-ppt` — `<프로젝트>/plan.md` → `work/slides.json` → `build_ppt.py` → `output/*.pptx`
   - `/make-md` · `/make-html` · `/make-word` — `<프로젝트>/plan.md` → `work/report.json`(문서체 재구성) → `build_doc.py` → `output/*.{md,html,docx}`
3. **`/review-doc`** — plan.md 대조 검수 → 수정은 반드시 plan.md에 반영 후 파생물 전체 재생성
4. **`/compact-log`** — `<프로젝트>/docs/interview-log.md`가 비대해지면 압축 (활성 팩트 통합 + 이전 항목은 archive로 이동)

## 파일 지도 (역할 변경 금지)

### 루트 공유

| 파일 | 역할 |
|---|---|
| `scripts/build_ppt.py` | slides.json → PPTX 조립 (결정론적 부분, 코드 수정은 신중히) |
| `scripts/build_doc.py` | report.json → md/html/docx 조립 (결정론적 부분, 문서 스타일 내장 — 스킬은 PPT 전용) |
| `scripts/theme.py` | 색상/폰트/여백 토큰. `.claude/skills/ppt-design/SKILL.md`와 동일 값 유지 |
| `samples/slides.sample.json` | slides.json 스키마 예시 (스모크 테스트 입력) |
| `samples/report.sample.json` | report.json 스키마 예시 (스모크 테스트 입력) |
| `samples/interview-log.sample.md` | 인터뷰 로그 형식 예시 |
| `sources/` | **글로벌 자료** — 전 프로젝트 공통 원본 자료 (회사 데이터·공통 참고문서). 프로젝트별 `sources/`와 함께 plan-doc이 둘 다 읽는다 |
| `assets/` | 전 프로젝트 공통 로고·이미지 |
| `templates/` | 사내 PPT 공통 템플릿. `template.pptx`가 있으면 build_ppt.py가 빈 레이아웃에 배치 (프로젝트 `assets/template.pptx`가 우선). 규칙은 `ppt-design` 스킬의 템플릿 절 |

### 프로젝트별 (`projects/<프로젝트명>/`)

| 파일 | 역할 |
|---|---|
| `plan.md` | **콘텐츠의 유일한 원본(Single Source of Truth)**. 사람이 검수하는 기획서. 모든 포맷(pptx/md/html/docx)의 원본 |
| `work/slides.json` | plan.md의 PPT용 기계 파생물. build_ppt.py의 입력 |
| `work/report.json` | plan.md의 문서용 기계 파생물(문서체 재구성됨). build_doc.py의 입력 |
| `output/*.{pptx,md,html,docx}` | plan.md의 **파생물**. 직접 수정하지 않는다 — 항상 재생성 |
| `docs/interview-log.md` | 인터뷰/확정 팩트 적립소. 세션이 바뀌어도 유지되는 근거 자료 |
| `docs/interview-log-archive.md` | 압축 시 밀어낸 이전 팩트 이력. 참고용으로만 읽는다 |
| `sources/` | 고객사 고유 원본 자료. plan-doc은 루트 `sources/`도 함께 읽는다 |
| `assets/` | 프로젝트 고유 이미지 |

**git 비공개 정책**: 고객 콘텐츠를 담는 `projects/<프로젝트>/` 파일(plan.md·docs/·sources/·work/·output/)은 `.gitignore`로 커밋하지 않는다. plan.md 등 SSOT의 백업은 이 저장소 git이 아니라 별도 경로/파일 동기화로 관리한다.

## 핵심 규칙

- **수정은 항상 원본에서**: 내용을 바꿀 때는 plan.md → 파생물(slides.json·report.json) → 재생성 순서. output 파일을 직접 손대지 않는다.
- **문서는 문서체로 재구성한다**: make-doc 계열은 PPT 개조식을 문서에 맞는 서술형으로 풀어 쓴다. 단 수치·표·차트 데이터·`(미확정)`·근거/출처 문자열은 plan.md와 **한 글자도 다르지 않게 복사**하고, plan에 없는 내용을 창작하지 않는다. 재구성은 문장에만 적용한다.
- **팩트는 기록하고 쓴다**: 인터뷰나 대화에서 확정된 수치·약속은 해당 프로젝트의 `docs/interview-log.md`에 먼저 기록한 뒤 plan.md에 반영한다. 추측 수치는 `(미확정)` 표기.
- **디자인은 스킬에 위임 (PPT)**: 슬라이드 레이아웃·색상·폰트 결정 전에 `ppt-design` 스킬을 로드한다. slides.json의 JSON 스키마도 스킬 문서에 정의되어 있다. 문서(md/html/docx) 스타일은 `build_doc.py`에 내장되어 있다.
- **디자인·스크립트는 함께 고친다**: 색/폰트/여백을 바꿀 때 `.claude/skills/ppt-design/SKILL.md`와 `scripts/theme.py`를 **항상 동시에** 수정 (동일 값 유지). 새 슬라이드 유형·요소 추가는 SKILL.md 유형 정의 + `layouts.md` 좌표 + `build_ppt.py`에 렌더러 + `samples/slides.sample.json` 예시 갱신 **4종 세트** (layouts.md 누락 방지 — 과거 table.note 추가에서 실제로 누락됨).
- **공용 파일 변경 판정 (범용 vs 전용)**: scripts/·`.claude/skills/`·theme.py·samples/를 고치기 전에 먼저 판정한다 — "이 변경이 특정 프로젝트에서 유발됐는가, 범용 개선인가".
  - **범용**: 공용 파일을 고쳐 일반화하고 **즉시 별도 커밋**으로 정리한다 (새 유형·요소면 SKILL.md·layouts.md·theme.py·build_ppt.py·samples 4종 세트 동반). 프로젝트 세션 종료 시점에 공용 파일에 미커밋 변경이 남으면 안 된다.
  - **전용**: 공용 파일을 고치지 않는다. 고객사 개성(로고·마스터·색 톤 차이)은 `projects/<프로젝트>/assets/template.pptx` 또는 `templates/template.pptx` 배치로, 데이터·문구 차이는 plan.md와 slides.json이 흡수한다. 템플릿으로도 흡수할 수 없는 전용 요구(새 슬라이드 유형 등)가 나오면 임의로 공용 파일을 고치지 말고 사용자에게 일반화 여부를 확인한다.
- **버전 관리**: output 파일명은 `<프로젝트>/output/<문서 제목>_vNN.<확장자>` — build_ppt.py·build_doc.py가 `meta.title`에서 자동 생성하고, **같은 프로젝트 output 디렉토리 내 같은 확장자**의 최대 vNN을 찾아 +1 한다 (확장자별 독립 시퀀스 — pptx v08과 md v01은 정상). 이전 버전을 덮어쓰지 않으며, 다른 프로젝트와 버전 번호를 공유하지 않는다. `output_name`은 특수한 경우(스모크 테스트 등)에만 지정.
- **스크립트 공통 로직**: build_ppt.py와 build_doc.py의 `_sanitize_title`·채번 로직은 의도적 복제다 (build_ppt.py 회귀 방지). 스크립트가 3개 이상 늘어나는 시점에 `scripts/common.py`로 추출을 검토한다.

## plan.md 포맷

```markdown
# <문서 유형> 기획 (제목)
## 메타
- 산출 문서: 제안서, 개발설계서 (단일 문서면 생략 가능 — 기본 제안서)
- 목적: / 청중: / 예상 분량: N장
## 핵심 메시지 (3개)
1. ...
## 슬라이드 목록
### 1. [유형: 표지] 슬라이드 제목
- 핵심문장: ...
- 근거/출처: interview-log 항목 또는 (미확정)
```

슬라이드 유형은 `ppt-design` 스킬의 7종(표지/목차/2단/표/차트/구성/마무리)만 사용한다. 유형 표기는 PPT 개조식 관점의 뼈대이며, 문서 포맷은 이를 섹션 구조로 해석한다. H1은 자유 텍스트다(기존 `# 제안서 기획 (제목)`도 유효) — 문서 구성의 유일 권위는 메타의 `산출 문서`다.

**유형별 표기법** (make-ppt·make-doc이 이 구조를 해석한다):

- **2단**: `- 좌 (소제목):` / `- 우 (소제목):` 아래 하위 불릿 `라벨 | 설명` 한 줄씩
- **표**: `- 표: [헤더 | 헤더 | 헤더]` 아래 하위 행 `셀 | 셀 | 셀` 한 줄씩
- **차트**: `- 차트:` 아래 범주/계열 데이터 (plan에 없는 내용 창작 금지는 동일)
- **구성**: `- 구성:` 아래 하위 행 `계층명 | 박스 라벨, 박스 라벨, ...` 한 줄씩 — 한 줄 = 계층 1개, 우측은 쉼표 구분 구성요소 나열 (라벨 안에 쉼표 금지). 계층은 상→하(사용자→데이터) 권장

**문서 태그 규칙** (plan.md에 여러 문서가 공존할 때):

- 슬라이드 제목 행에 유형 브래킷 뒤 문서 태그를 붙인다: `### 3. [유형: 2단][문서: 제안서] 제목` — 복수 소속은 `+` 구분 (`[문서: 제안서+개발설계서]`)
- 태그 없음 = 전체 문서 포함. `[문서: 공통]`은 태그 없음과 동일. 단일 문서 프로젝트는 태그를 쓰지 않는다 (현행 포맷 그대로)
- 표지·목차·마무리는 문서별 별도 슬라이드로 쓴다 (각 문서 태그). 각 문서의 목차 불릿은 **그 문서에 포함되는 슬라이드만** 필터링 순서대로 나열하고 label은 01..NN 재채번한다 (plan.md 전체 슬라이드 번호와 달라질 수 있음)
- 근거/출처는 슬라이드에 붙어 따라가므로 별도 태그 불필요

## report.json 스키마

문서용 계약 파일. `meta{title, subtitle, doc_type, company, department, date, output_name(선택적 파일명 오버라이드)}` + `sections` 배열 — 슬라이드 7종을 문서 섹션으로 매핑:

| plan.md 슬라이드 | report.json 섹션 |
|---|---|
| 표지 (cover) | `header{title, subtitle, meta_line}` |
| 목차 + 핵심 메시지 3개 (toc) | `overview{title, items[{no, label, body}]}` |
| 2단 (two-col) | `section` + `prose` 블록 2개 (좌/우 heading이 각각 블록 heading, label\|body를 문장으로 재구성) |
| 표 (table) | `section` + `table` 블록 — headers/rows는 **원본 그대로 복사** (+필요시 해설 `prose` 블록 추가) |
| 구성 (arch) | `section` + `table` 블록 — headers `[계층, 구성요소]`, 계층명·박스 라벨은 **원본 그대로 복사** (박스 라벨은 쉼표 나열 유지, 새 BLOCK_KIND 없음) |
| 차트 (chart) | `section` + `data` 블록 — categories/series 원본 복사, `unit`, 해설 `prose`. html은 CSS 막대, md/docx는 데이터표 |
| 마무리 (closing) | `conclusion{title, paragraphs, requests, note}` |

`section{no, title, lead, blocks[], source}` — blocks는 **`kind` 필드로 판별하는 3종**: `prose{kind, heading, paragraphs}`, `table{kind, heading, headers, rows}`, `data{kind, heading, categories, series[{name, values}], unit, prose}`. 각 섹션의 `source`에는 plan.md의 근거/출처 문자열을 그대로 둔다. 문서 제목은 header 섹션의 `title`을 우선하고, `meta.title`은 파일명·폴백용이다. `meta.doc_type`은 자유 텍스트로 문서 표지 meta_line에 노출된다 — make-doc은 대상 문서명(제안서·개발설계서 등)을 기록한다. `meta.output_name`은 특수한 경우(스모크 테스트 등)에만 지정하며 확장자는 스크립트가 보정한다. 전체 예시는 `samples/report.sample.json`.