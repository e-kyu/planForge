# -*- coding: utf-8 -*-
"""legacy scripts/build_*.py·theme.py의 바이트 동일 이식본 (원문은 git 이력에만 존재).
로직 변경 금지 — I/O 어댑터만 이 파일 밖에서 처리.

- theme.py: 디자인 토큰 (tokens.css와 동일 값 유지 — 토큰 변경 시 3종 세트 동시 수정,
  docs/token-checklist.md 참조)
- build_ppt.py: slides.json → PPTX
- build_doc.py: report.json → md/html/docx (확장자별 독립 채번)
"""