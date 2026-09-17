# /make-word — plan.md → Word 문서(docx) 생성

$ARGUMENTS

FORMAT=docx로 `make-doc.md`의 절차를 그대로 실행한다: `<P>/plan.md` → `<P>/work/report.json`(문서체 재구성) → `python scripts/build_doc.py <P>/work/report.json docx`.

## 포맷별 주의

- `python-docx` 필요: 빌드가 실패하면 `pip install python-docx` 후 재시도한다.
- 생성 후 Word로 열어 확인하도록 안내한다: 한글 폰트(맑은 고딕) 적용 여부, 표 헤더 색상, 데이터 표 + 해설 문단.
- docx에는 차트 이미지가 없다 — 데이터는 표로, 해석은 해설 문단으로 표현되는 것이 정상이다.