# -*- coding: utf-8 -*-
"""legacy 빌더 원형 (docs/legacy/scripts/) — 로직 변경 금지, I/O 어댑터만 이 파일 밖에서 처리.

- theme.py: 디자인 토큰 (SKILL.md와 동일 값 유지 — 토큰 변경 시 4종 세트 동시 수정)
- build_ppt.py: slides.json → PPTX
- build_doc.py: report.json → md/html/docx (확장자별 독립 채번)
"""