---
description: 요청서 §8 참조 파일을 읽고 현재 마일스톤 진행 계획 제시 (새 세션 진입점)
---

# /kickoff — 개발 세션 진입점

AGENT-DEV-REQUEST.md §9에 정의된 세션 시작 절차를 수행한다.

## 절차

1. **계약 확인**: `CLAUDE.md`와 `AGENT-DEV-REQUEST.md` §2.1(설계 원칙 8개)을 읽는다.
   이 8개는 계약이며, 위반 시 구현 자체가 오답이다.
2. **참조 파일 읽기**: `AGENT-DEV-REQUEST.md` §8의 참조 파일을 읽는다.
   단, §8의 경로는 legacy 원본 기준이므로 아래 매핑된 실제 경로를 사용한다
   (원문이 요약보다 권위 있다):
   - `CLAUDE.md`
   - `docs/legacy/commands/plan-doc.md`, `make-ppt.md`, `make-doc.md`, `review-doc.md`, `compact-log.md`
   - `docs/legacy/skills/SKILL.md`, `docs/legacy/skills/layouts.md`
   - `docs/legacy/scripts/build_ppt.py`, `build_doc.py`, `theme.py`
   - `docs/legacy/samples/*.sample.json`, `plan.sample.md`, `interview-log.sample.md`
3. **진행 상황 파악**: `git log --oneline`과 저장소 상태(backend/, frontend/ 등의
   존재 여부, 진행 중 마일스톤 산출물)로 현재 위치를 판단한다.
4. **계획 제시**: `AGENT-DEV-REQUEST.md` §6의 마일스톤 순서(M1 → M2 → M3 → M4,
   M1이 전체 리스크의 대부분이므로 다른 작업과 섞지 않음)에 따라
   현재 마일스톤의 구현 계획을 제시한다.

## 제약

- M1 완료 전에 M2/M3/M4 작업을 시작하지 않는다.
- 빌더 포팅 시 `docs/legacy/scripts/*.py`는 로직 변경 없이 가져오고,
  경로/워크스페이스 주입만 어댑터로 처리한다.
- LLM 호출은 `openai` SDK 기반 provider 추상화 계층으로만 한다.