# UI 디자인 가이드

## 디자인 원칙

1. **화면과 산출물이 같은 팔레트를 쓴다** — PPT·문서 출력물과 웹 UI가 같은 색 톤으로
   맞춰진다(§3.1). 색·폰트·여백의 권위(authority)는 `backend/planforge/builders/theme.py`
   이고, 화면은 `frontend/src/shared/styles/tokens.css`에 미러한다.
2. **토큰 우선, 원시값 금지** — 화면 CSS는 tokens.css의 CSS 변수를 참조한다. 화면 전용
   토큰(app 크롬·그림자·간격)은 tokens.css의 별도 섹션으로 분리하고, 미러 섹션(토큰 7종 +
   상태 색)은 theme.py 값과 동일하게 유지한다.
3. **토큰 변경은 4종 세트 동시 점검** — theme.py(권위)·빌더·계약 fixture·tokens.css
   (화면)를 동시에 점검·수정한다. 절차는 `docs/token-checklist.md`. 하나만 고치는
   변경은 반려된다.

## AI 슬롭 안티패턴 — 하지 마라

| 금지 사항 | 이유 |
|-----------|------|
| backdrop-filter: blur() | glass morphism은 AI 템플릿의 가장 흔한 징후 |
| gradient-text (배경 그라데이션 텍스트) | AI가 만든 SaaS 랜딩의 1번 특징 |
| "Powered by AI" 배지 | 기능이 아니라 장식. 사용자에게 가치 없음 |
| box-shadow 글로우 애니메이션 | 네온 글로우 = AI 슬롭 |
| 보라/인디고 브랜드 색상 | "AI = 보라색" 클리셰 |
| 모든 카드에 동일한 rounded-2xl | 균일한 둥근 모서리는 템플릿 느낌 |
| 배경 gradient orb (blur-3xl 원형) | 모든 AI 랜딩 페이지에 있는 장식 |

## 색상 (`theme.py` → `tokens.css` 미러)

### 문서 팔레트 (미러 — theme.py와 동일 값)

| 용도 | 토큰 | 값 |
|------|------|-----|
| 주강조(헤더·표지) | `--navy` | `#1f3b5c` |
| 포인트 버튼·링크 | `--blue` | `#2e6db4` |
| 연한 강조 | `--light-blue` | `#8fb8e0` |
| 페이지 배경 | `--bg` | `#ffffff` |
| 소프트 배경 | `--bg-soft` | `#f2f5f9` |
| 주 텍스트 | `--text` | `#222222` |
| 보조 텍스트 | `--text-sub` | `#666666` |
| 경계선 | `--line` | `#d8dee6` |
| 액센트(대비 강조) | `--accent` | `#e8a33d` |

### 상태 색 (검수 심각도 — FR-4.2)

| 용도 | 토큰 | 값 |
|------|------|-----|
| 부정/🔴 | `--danger` | `#c0392b` |
| 경고/🟡 | `--warn` | `#b7791f` |
| 긍정/⚪ | `--ok` | `#2f855a` |

### 화면 전용 토큰 (app 크롬 — theme.py 미러 아님)

`--surface`(#ffffff) · `--surface-sub`(#f8fafc) · `--line-soft`(#e7ecf2) —
카드·보조 경계용. 강조/상태 색은 미러 값을 재사용한다(별도 신규 색 정의 금지).

## 컴포넌트 토큰 규약

- **카드**: `--surface` 배경 + `--radius-lg`(14px) + `--shadow-sm` + `--line-soft` 경계.
  호버·모달 같은 부양 계층만 `--shadow-md`까지.
- **버튼**: Primary는 `--blue` 배경 + 흰 텍스트, 보조는 `--navy` 톤 텍스트/아웃라인.
  링크·텍스트 액션은 `--blue`. (radius는 `--radius` 8px 계열)
- **입력 필드**: `--surface` 배경 + `--line-soft`/`--line` 경계 + `--radius` 기본,
  포커스 링은 `--ring`(0 0 0 3px rgba(46,109,180,.25)).
- **그림자**: `--shadow-xs/sm/md` 3단만 사용 — 네온 글로우·글로우 애니메이션 금지.

## 레이아웃

- 전체 폭: `--container`(1280px) 기준, 좌측 정렬 기본.
- 여백 스케일: `--space-1`~`--space-6`(4/8/12/16/24/32px) — 문서 여백 `--margin`(24px,
  MARGIN 0.6in ≈ 24px)과 계열 일치.
- 헤더 높이 `--header-h`(64px) 고정 — 하단 콘텐츠 영역이 이 값에 맞춘다.

## 타이포그래피

| 용도 | 스타일 |
|------|--------|
| 폰트 | `--font`: "Malgun Gothic"(맑은 고딕) + system-ui 폴백 |
| 사이즈 스케일 | `--fs-title` 28px · `--fs-heading` 18px · `--fs-body` 14px · `--fs-caption` 11px |
| 컨트롤 텍스트(버튼·탭) | `--fs-ui` 13px (caption과 body 사이) |
| 코드·JSON | `--font-mono`: ui-monospace / Cascadia Mono / Consolas |
| 크기 기준 | theme.py pt 토큰(SIZE_SLIDE_TITLE 28 등)의 화면 px 배율 재해석 |

## 애니메이션

- 표준 전환 속도는 `--speed`(140ms) 1곳만 정의되어 있다. 톤 미먼 저해하는
  장식 애니메이션(glow, 무한 스피너 장식 등)은 금지.

## 아이콘

- 인라인 SVG를 기본으로 한다. 아이콘 컨테이너(둥근 배경 박스)로 감싸는 장식은
  자제한다 — 도구(dashboard) 톤을 유지한다.