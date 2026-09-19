# 디자인 토큰 일관성 체크리스트 (FR-6.2)

디자인 토큰(색·폰트·여백·좌표)의 SSOT는 `backend/reportagent/builders/theme.py`다.
토큰 값을 바꿀 때는 아래 파일들의 결합을 반드시 함께 점검·수정한다. 하나만 고친 PR은
리뷰에서 반려한다 (AGENT-DEV-REQUEST.md 원칙 7, CLAUDE.md 설계 원칙 7과 동일).

## 토큰 4종 세트(+프론트 렌더)

| # | 파일 | 결합 방식 | 토큰 변경 시 |
|---|---|---|---|
| 1 | `backend/reportagent/builders/theme.py` | 토큰 상수 (권위) | **수정** (기준점) |
| 2 | `docs/legacy/skills/SKILL.md` (+`layouts.md`) | 리터럴 값을 문서화 | **수정** — 같은 값으로 |
| 3 | `backend/reportagent/builders/build_ppt.py` · `build_doc.py` | `import theme as T` — 이름 참조만, 리터럴 하드코딩 없음 | **점검** — 새 토큰이면 참조 추가, 리터럴 추가 금지 |
| 4 | `tests/fixtures/*.sample.json` · `docs/legacy/samples/*` | 현재 토큰 리터럴 비의존 (레이아웃·구조 잠금) | **점검** — 좌표 규격이 바뀌는 변경이면 fixture 갱신 |
| 5 | `frontend/src/styles/tokens.css` | 리터럴 값을 CSS 변수로 미러 | **수정** — 같은 값으로 |

## 변경 절차

1. theme.py에서 토큰 값을 수정한다 (기준점).
2. SKILL.md의 해당 값·설명을 같은 값으로 수정한다.
3. `frontend/src/styles/tokens.css`의 CSS 변수 값을 같은 값으로 수정한다.
4. 빌더에 theme 리터럴 하드코딩이 생기지 않았는지 확인한다 — 값은 반드시 `T.<토큰>` 참조.
5. 변경이 좌표/크기 규격(슬라이드 크기·마진)에 걸치면 계약 테스트 fixture도 갱신한다.

## 검증

- **결정론**: `pytest` — 계약 테스트(빌더 회귀)가 렌더러↔샘플 일치를 검증한다.
  `/contract`로 실행해도 같다.
- **수동 대조** (SKILL.md·tokens.css는 테스트가 잠그지 않는다): 리터럴을 갖는 3곳
  (SKILL.md·theme.py·tokens.css)이 같은 값을 갖는지 대조한다.

  ```
  grep -rniE "1F3B5C|2E6DB4|Malgun Gothic" docs/legacy/skills/SKILL.md \
      backend/reportagent/builders/theme.py frontend/src/styles/tokens.css
  ```

- **프론트 빌드**: `npm run build` (frontend/) — tokens.css 문법 오류를 잡는다.