# /make-md — plan.md → 마크다운 문서 생성

$ARGUMENTS

FORMAT=md로 `make-doc.md`의 절차를 그대로 실행한다: `<P>/plan.md` → `<P>/work/report.json`(문서체 재구성) → `python scripts/build_doc.py <P>/work/report.json md`.

## 포맷별 주의

- 결과물은 편집기로 열어 문장체·구조를 확인하도록 안내한다.
- 수치·표 데이터의 plan.md 대조는 `/review-doc`에서 수행한다 — 이 커맨드에서 grep 대조를 대신하지 않는다.
- 외부 의존성 없음 (표준 라이브러리만으로 동작).