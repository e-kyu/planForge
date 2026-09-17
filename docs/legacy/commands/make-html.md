# /make-html — plan.md → 단일 파일 HTML 문서 생성

$ARGUMENTS

FORMAT=html로 `make-doc.md`의 절차를 그대로 실행한다: `<P>/plan.md` → `<P>/work/report.json`(문서체 재구성) → `python scripts/build_doc.py <P>/work/report.json html`.

## 포맷별 주의

- **생성 직후 브라우저로 열어 확인하라고 안내한다**: `start <생성된 파일 경로>` (Windows).
- 단일 파일(외부 리소스·JS 0건, CSS 인라인)이다. 렌더링에 외부 리소스를 요구하면 스크립트 버그로 분류해 보고한다.
- 차트는 CSS 가로 막대로 렌더된다 (데이터는 plan.md 차트와 한 글자도 같아야 한다).
- 스타일은 `scripts/build_doc.py`에 내장 — 문서 내용에 맞춰 CSS를 커맨드에서 손대지 않는다. 스타일 변경 요구는 스크립트·theme.py 수정 사안으로 분류한다.