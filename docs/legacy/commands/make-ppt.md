# /make-ppt — plan.md → PPTX 생성

$ARGUMENTS

`plan.md`를 읽어 PPTX를 생성한다. 콘텐츠 가공은 여기서 끝내고, 조립은 스크립트에 맡긴다.

## 절차

0. **프로젝트 결정**: `$ARGUMENTS`를 프로젝트명으로 해석해 `<P>` = `projects/<프로젝트명>/`로 확정한다. 인자가 없으면 `projects/*/plan.md`를 나열해 사용자에게 선택받는다(1개여도 확인). 규칙 상세는 `CLAUDE.md`의 "프로젝트 결정 규칙" 참조.
1. **전제 확인**: `<P>/plan.md`가 없으면 `/plan-doc`부터 하도록 안내하고 종료. plan.md에 `(미확정)` 수치가 있으면 사용자에게 그대로 갈지 확인.
2. **디자인 스킬 로드**: `ppt-design` 스킬을 로드해 슬라이드 유형·색상·폰트 규칙을 확인한다.
3. **문서 선택·필터**: plan.md 메타의 `- 산출 문서:`를 읽는다 (항목 없으면 `제안서` 1개로 간주 — 현행 동작).
   - 산출 문서가 2개 이상이면 대상 문서를 사용자에게 선택받는다 (1회 실행 = 1문서 — 문서별로 채번 접두어가 분리되어야 버전이 섞이지 않는다).
   - 슬라이드 필터: 태그 없음 또는 태그에 대상 문서가 포함된 슬라이드만 추린다 (`CLAUDE.md`의 문서 태그 규칙).
   - **골격 검증**: 필터 결과에 표지·목차·마무리가 각 1개 이상, 내용 슬라이드가 1개 이상 있어야 한다. 미달이면 생성을 중단하고 `/plan-doc`으로 plan.md 수정을 안내한다.
   - `meta.title`은 대상 문서 표지 슬라이드의 제목으로 쓴다 (표지가 없으면 `<plan 제목> - <문서명>`). 문서마다 접두어가 달라야 버전 채번이 문서 간 섞이지 않는다.
4. **slides.json 생성**: `<P>/work/slides.json`에 plan.md의 각 슬라이드를 스킬의 JSON 스키마로 변환해 쓴다.
   - 스키마: `{"meta": {"title"}, "slides": [{"type", "title", "bullets", "table", "chart", "arch", "note"}]}` — `meta.title`은 대상 문서의 제목. `output_name`은 특수한 경우(스모크 테스트 등)에만 선택적으로 지정
   - `type`은 7종 중 하나: `cover` / `toc` / `two-col` / `table` / `chart` / `arch` / `closing` — `arch`는 `arch.groups [{name, items}]` 구조
   - `bullets`는 각 항목 `{label, body}` 구조. 표·차트·구성 데이터는 plan.md의 수치·라벨과 한 글자도 다르지 않게 복사한다.
5. **빌드 실행**: `python scripts/build_ppt.py <P>/work/slides.json` (저장소 루트에서 실행 — 스크립트가 theme.py를 import)
   - 실패하면 스크립트 오류 메시지를 확인하고 slides.json 스키마 문제인지 스크립트 문제인지 판별. 스크립트 수정이 필요하면 수정 사유를 사용자에게 말하고 수정.
6. **완료 보고**: 생성된 파일 경로, 슬라이드 수, 버전 번호를 보고하고 PowerPoint에서 열어 확인하도록 안내.
7. **차후 확인**: 사용자가 레이아웃/디자인 변경을 요구하면 → 스킬·스크립트 수정 후 재생성. **내용 변경을 요구하면 → plan.md 수정 후 재생성** (slides.json만 고치지 않는다).

## 주의

- output 파일명은 스크립트가 `meta.title`에서 자동 생성: `<P>/output/<문서 제목>_vNN.pptx` (같은 프로젝트 output 디렉토리 내 같은 접두어의 최대 버전 +1, 덮어쓰지 않음). slides.json에 `output_name`을 쓰지 않는다.
- python-pptx가 없으면 `pip install python-pptx` 후 진행.
- 수치·텍스트를 slides.json에서 임의로 다듬지 않는다. 문장 다듬기가 필요하면 plan.md에서 먼저 한다.