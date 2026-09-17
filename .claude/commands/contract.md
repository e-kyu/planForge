---
description: 계약 테스트(빌더 회귀) 실행
---

# /contract — 계약 테스트 실행

`docs/legacy/samples/*.sample.json`을 fixture로 사용하는 빌더 회귀 테스트를 실행한다.

## 절차

1. 테스트가 존재하는지 확인한다:
   - M1 이후: `backend/tests/` 아래의 계약 테스트(빌더 회귀)를 찾는다.
     fixture는 `docs/legacy/samples/`의 샘플들이며, 이식 전까지는 legacy 원본을 직접 실행한다.
   - M1 이전(테스트 미생성): 이 명령은 "계약 테스트 미확보"를 보고하고 종료한다.
     fixture를 임시로 만들어야 하면 `workspaces/` 대신 `tests/fixtures/`를 사용할 것
     (SSOT 가드 훅이 workspaces/ 파생물 직접 쓰기를 차단한다).
2. 존재하면 실행하고 결과를 요약한다:
   - Windows 환경이므로 `PYTHONUTF8=1`이 설정되어 있어야 한다(.claude/settings.json env 참조).
   - 빌더 출력(pptx/docx) 비교가 필요하면 샘플 기대값과 생성물의 구조(슬라이드 수,
     레이아웃 유형, 채번, 토큰 적용)를 대조한다.
3. 실패 시: 빌더 로직을 수정하지 않는다(로직 변경 금지). 어댑터·fixture 문제인지,
   이식 과정의 버그인지부터 판별한다.

## 참고

- 샘플 파일: `docs/legacy/samples/slides.sample.json`, `report.sample.json`,
  `slides.design.sample.json`, `report.design.sample.json`
- 계약 테스트 명령이 확정되면 `CLAUDE.md` 명령어 섹션에도 추가한다.