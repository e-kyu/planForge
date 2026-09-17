---
name: ppt-design
description: 제안서·개발설계서 등 기획 문서 PPT 디자인 시스템. 슬라이드 유형/색상/폰트/레이아웃 규칙과 slides.json 스키마. /make-ppt로 PPT를 생성하거나 슬라이드 레이아웃·디자인을 결정할 때 로드.
---

# PPT 디자인 시스템

16:9 (13.333in × 7.5in) 기준. 모든 값은 `scripts/theme.py`와 동일하게 유지한다 — 이 문서를 바꾸면 theme.py도 함께 바꾼다.

## 색상 토큰

| 토큰 | HEX | 용도 |
|---|---|---|
| `NAVY` | 1F3B5C | 표지/마무리 배경, 제목 강조 |
| `BLUE` | 2E6DB4 | 포인트, 차트 주 계열, 강조 바 |
| `LIGHT_BLUE` | 8FB8E0 | 차트 보조 계열 |
| `BG` | FFFFFF | 슬라이드 배경 |
| `BG_SOFT` | F2F5F9 | 카드·2단 배경 박스 |
| `TEXT` | 222222 | 본문 |
| `TEXT_SUB` | 666666 | 보조 설명, 출처 표기 |
| `LINE` | D8DEE6 | 구분선, 표 테두리 |
| `ACCENT` | E8A33D | 주의/하이라이트 (소량만) |

## 폰트

- 전체: 맑은 고딕(Malgun Gothic)
- 토큰 크기 (theme.py와 동일): 표지 제목 40pt(`SIZE_COVER_TITLE`) / 슬라이드 제목 28pt(`SIZE_SLIDE_TITLE`) / 표지 부제 18pt(`SIZE_HEADING`) / 표지 사명·마무리 note 14pt(`SIZE_BODY`) / 캡션·출처·슬라이드 번호 10pt(`SIZE_CAPTION`)
- 토큰 외 리터럴: 본문 불릿 13pt(two-col) / toc 번호 24pt·본문 20pt / 표 헤더 13pt·셀 12pt / closing 제목 32pt·불릿 16pt. 좌표 상세는 `layouts.md`.
- 본문은 개조식 (명사형 종결). 슬라이드당 본문 5줄 이하.

## 슬라이드 유형 7종

1. **표지 (`cover`)**: NAVY 배경 전체, 좌측 상단 사명, 중앙 좌측정렬 제목+부제, 좌하단 날짜·부서.
2. **목차 (`toc`)**: 흰 배경, 핵심 메시지 3개를 번호+한 줄씩 나열.
3. **2단 (`two-col`)**: 상단 제목, 하단 좌/우 두 개의 BG_SOFT 박스. 대비·비교 용도 (문제/해결, 현황/제안, 요구/설계 등).
4. **표 (`table`)**: 헤더 행 NAVY 배경 흰 글자, 교대 행 BG_SOFT, 테두리 LINE. `note`가 있으면 표 하단 캡션.
5. **차트 (`chart`)**: 주 계열 BLUE, 비교 계열 LIGHT_BLUE, 데이터 라벨 표시, 출처는 우하단 캡션.
6. **구성 (`arch`)**: 시스템 구성도. 가로 계층 밴드(좌측 계층명 BG_SOFT 박스) + 계층별 구성요소 박스(흰 배경·LINE 테두리)를 균등 분할 배치. 계층은 상→하(사용자→데이터 순 권장), 박스 라벨 중앙정렬. `note`가 있으면 하단 캡션.
7. **마무리 (`closing`)**: NAVY 배경, 요약 1~3줄 + 다음 단계·확인 사항 (제안서는 요청 사항, 개발설계서는 확인·합의 사항).

공통: 제목 위치 (0.6in, 0.4in)에서 시작, 좌우 여백 0.6in. 슬라이드 번호는 본문형 유형(toc/two-col/table/chart/arch)에만 우하단 표기 — 표지·마무리에는 없음.

## slides.json 스키마

```json
{
  "meta": {
    "title": "문서 제목 (표지 제목)",
    "subtitle": "부제",
    "company": "사명",
    "date": "2026. 9. 2.",
    "department": "작성 부서",
    "template": "선택적: 템플릿 경로 오버라이드. \"none\"이면 템플릿 미사용"
  },
  "slides": [
    {
      "type": "two-col",
      "title": "슬라이드 제목",
      "left": {"heading": "좌측 소제목", "bullets": [{"label": "라벨", "body": "설명"}]},
      "right": {"heading": "우측 소제목", "bullets": [{"label": "라벨", "body": "설명"}]}
    },
    {
      "type": "table",
      "title": "슬라이드 제목",
      "table": {"headers": ["항목", "현재", "제안 후"], "rows": [["비용", "100", "80"]], "note": "선택적: 표 하단 캡션 (출처·정합성 등)"}
    },
    {
      "type": "chart",
      "title": "슬라이드 제목",
      "chart": {"categories": ["2024", "2025", "2026"], "series": [{"name": "매출", "values": [10, 12, 15]}], "source": "출처: ..."}
    },
    {
      "type": "arch",
      "title": "시스템 구성도",
      "arch": {"groups": [
        { "name": "사용자 계층", "items": ["웹 콘솔", "모바일 앱"] },
        { "name": "서비스 계층", "items": ["API Gateway", "인증 서비스", "업무 서비스"] }
      ], "note": "선택적: 하단 캡션 (table.note와 동일 역할)"}
    },
    { "type": "cover", "title": "...", "subtitle": "..." },
    { "type": "toc", "title": "목차", "bullets": [{"label": "01", "body": "..."}] },
    { "type": "closing", "title": "...", "bullets": [{"label": "", "body": "..."}], "note": "요청 사항 한 줄" }
  ]
}
```

`build_ppt.py`가 이 스키마의 각 유형을 렌더링한다. 유형별 필수 키(모든 유형에 `title`, toc/two-col/table/chart/closing은 각 유형 고유 키 포함) 누락 시 스크립트가 오류를 내므로 생성 시 검증.

출력 파일명은 `meta.title`에서 자동 생성한다: `<제목 정규화>_vNN.pptx` (Windows 금지 문자·glob 메타문자 `[ ]` 제거·공백→`_`, 버전은 같은 접두어의 최대 vNN +1, 없으면 v01). 출력 디렉토리는 입력 slides.json 위치에서 유도된다 (`<프로젝트>/work/slides.json` → `<프로젝트>/output/`), 선택적 2번째 인자로 override 가능. `meta.output_name`은 스모크 테스트 등 특수한 경우에만 쓰는 선택적 오버라이드이며, 확장자 유무와 무관하게 `.pptx`가 자동 보정된다 (build_doc.py와 동일 규칙).

## 템플릿 (고객 브랜딩 통로)

색·폰트·좌표는 토큰 시스템이 담당하고, **고객사별 개성(로고·마스터 배경·머리글)은 템플릿 파일로 흡수한다** — 공용 스크립트·스킬·theme.py를 프로젝트 전용으로 고치지 않는다.

- **탐색 순서**: `meta.template`(명시적 경로) → `<프로젝트>/assets/template.pptx`(프로젝트 전용) → `templates/template.pptx`(사내 공통) → 없으면 빈 프레젠테이션.
- `meta.template: "none"`이면 템플릿이 존재해도 사용하지 않는다 (스모크 테스트·기본 디자인 비교용).
- 템플릿은 **16:9 (13.333×7.5in) 필수** — 아니면 스크립트가 경고 후 무시한다. 템플릿 내 placeholder가 없는 빈 레이아웃에 슬라이드를 얹는다.
- 제한: cover·closing은 NAVY 배경을 전체로 깔기 때문에 템플릿 마스터 장식이 가려진다 — 템플릿 브랜딩은 본문형 유형(toc/two-col/table/chart)에 나타난다.
- 프로젝트 전용 템플릿이 필요하면 `projects/<프로젝트>/assets/template.pptx`에 두고, 공용 템플릿은 `templates/template.pptx`에 둔다. 파일 수정이 아니라 파일 배치로 개성을 푼다.