---
description: CLAUDE.md 계약·아키텍처 결정 기준 변경사항 리뷰 체크리스트
---

이 프로젝트의 변경 사항을 리뷰하라.

먼저 다음 문서들을 읽어라:
- `/CLAUDE.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/INTERVIEW-TURN-CONTRACT.md` (인터뷰·LLM 계약을 건드린 경우)

그런 다음 변경된 파일들을 확인하고, 아래 체크리스트로 검증하라:

## 체크리스트

1. **아키텍처 준수**: docs/ARCHITECTURE.md의 디렉토리 구조·모듈 경계를 따르는가?
   (타 모듈의 테이블·내부 파일 직접 import 금지 — `facade.py` 공개 함수 또는
   `shared/` 경유만 허용)
2. **기술 스택 준수**: docs/ADR.md의 결정·편차를 벗어나지 않았는가? LLM은
   langchain-openai ChatOpenAI provider 계층만 사용했는가? (anthropic SDK 금지),
   빌더(`backend/planforge/builders/`) 로직을 변경하지 않았는가?
3. **테스트 존재**: 새로운 기능에 대한 테스트가 작성되어 있는가? (테스트는
   `tests/`·`backend/tests/` — fixture는 `tests/fixtures/`, `workspaces/` 금지)
4. **CRITICAL 규칙**: CLAUDE.md의 설계 원칙 계약 8개를 위반하지 않았는가?
   파생물(slides.json·report.json·output/*)을 직접 수정하지 않았는가? 디자인 토큰
   변경은 토큰 4종 세트(theme.py·빌더·fixture·tokens.css)를 동시 점검했는가?
5. **빌드 가능**: 백엔드 테스트 전체(`python -m pytest`)와 프론트
   (`frontend/`에서 `npm run build`)가 에러 없이 통과하는가?

## 출력 형식

| 항목 | 결과 | 비고 |
|------|------|------|
| 아키텍처 준수 | ✅/❌ | {상세} |
| 기술 스택 준수 | ✅/❌ | {상세} |
| 테스트 존재 | ✅/❌ | {상세} |
| CRITICAL 규칙 | ✅/❌ | {상세} |
| 빌드 가능 | ✅/❌ | {상세} |

위반 사항이 있으면 수정 방안을 구체적으로 제시하라.