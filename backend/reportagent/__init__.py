# -*- coding: utf-8 -*-
"""report-agent 코어 엔진 (M1).

구성:
- builders/: legacy 빌더 원형 (build_ppt.py·build_doc.py·theme.py) — 로직 무변경 이식
- plan/: plan.md 결정론 파서·문서 태그 필터·골격 검증
- numcheck.py: plan ↔ 파생물 수치 무결성 대조 (원칙 3)
"""