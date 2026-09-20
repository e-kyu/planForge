---
description: 계약 테스트(빌더 회귀) 실행
---

# /contract — 계약 테스트 실행

`tests/fixtures/*.sample.json`을 fixture로 사용하는 빌더 회귀 테스트를 실행한다.

## 절차

1. 계약 테스트(`tests/test_contract_builders.py`)를 저장소 루트에서 `pytest`로 실행한다.
   - Windows 환경이므로 `PYTHONUTF8=1`이 설정되어 있어야 한다(.claude/settings.json env 참조).
   - 빌더 출력(pptx/docx) 비교가 필요하면 fixture 기대값과 생성물의 구조(슬라이드 수,
     레이아웃 유형, 채번, 토큰 적용)를 대조한다.
2. fixture를 임시로 만들어야 하면 `workspaces/` 대신 `tests/fixtures/`를 사용할 것
   (SSOT 가드 훅이 workspaces/ 파생물 직접 쓰기를 차단한다).
3. 실패 시: 빌더 로직을 수정하지 않는다(로직 변경 금지). 어댑터·fixture 문제인지
   먼저 판별한다.

## 참고

- 샘플 파일: `tests/fixtures/slides.sample.json`, `report.sample.json`,
  `slides.design.sample.json`, `report.design.sample.json`
- fixture 원본(legacy samples)은 git 이력에만 존재한다.