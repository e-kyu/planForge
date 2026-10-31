# Step 1: frontend-strings

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 프론트엔드 feature-MVVM 구조, "View에 fetch·서버 데이터 로직 금지" 규칙
- `/frontend/CLAUDE.md` — 프론트엔드 디렉토리 가이드
- `/phases/refine-tone-strings/step0.md` — 이전 step(완료): 인터뷰 계약 완화. 이 step은 그와 독립적인
  UI 문자 순화 작업이다.
- 아래 "작업"에 나열된 프론트엔드 파일들 전부 — 수정 전에 실제 원문을 읽고 맥락을 파악하라.

## 작업

목표: 사용자에게 보이는 프론트엔드 문자(UI 라벨·배너·툴팁·에러·상태 문구)에서 부자연스러운
한자어·직역투·일본식 표현·은어·내부 참조를 자연스러운 친절한 한국어("하세요/입니다"체)로 전면 순화한다.

### 용어 순화 기준표 (반드시 이 표를 따른다)

| 현재 | 대체 |
|---|---|
| 채번 / 재채번 | (재)버전 번호 부여 / 번호를 새로 매김 |
| 결정론 빌드 / 결정론 대조 / 결정론+LLM 검수 | 자동 빌드 / 자동 대조 / 자동 검사+LLM 검수 |
| 확립 팩트 / 확립 | 확정된 팩트 / 확정 |
| 팩트 적립 / 적립 | 팩트 기록·저장 / 기록·저장 |
| 미달 N건 | 문제 N건 / 기준 미충족 |
| (plan) 세대 | (plan) 버전 |
| 원인 불명 | 알 수 없는 오류 |
| 파생물 / 산출물 혼용 | "산출물"로 통일 |
| 대체됨 | 이전 버전 |
| 반려 | 거절 / 수정 요청 (맥락에 따라) |
| 문서유형선택 | 문서 유형을 선택하세요 |
| 계획정의 | 기획 정의 |
| (FR-x)·(원칙 N) 내부 참조 | 삭제 또는 자연어 부연 |
| 명사형 축약 종결 ("반영됨", "건너뜀", "~필요") | 완결문 ("~했습니다", "~하세요") |
| 플랜 | plan (다른 화면과 표기 통일) |

**유지할 계약어**: `(미확정)` 마커, "plan.md"·파일명 규격(`문서제목_vNN.확장자` — "버전 번호
규칙"으로 소개하되 규격 문자열 자체는 유지), 영역 용어는 필요시 괄호로 원어 병기 가능.

### 수정 파일 목록 (사용자 노출 문자 전수 — 실제 파일을 읽으며 누락분도 기준표에 맞춰 함께 수정)

- `frontend/src/features/project/views/ProjectPage.tsx` — "계획정의" 탭 라벨 → "기획 정의"
- `frontend/src/features/project/views/HeaderMetrics.tsx` — "확립(활성) 팩트 수"·"확립 팩트" 툴팁 →
  "확정된 팩트 수"·"확정된 팩트"
- `frontend/src/features/interview/views/FactSidePanel.tsx` — "확립" 탭 라벨 → "확정", "적립됩니다" →
  "기록됩니다", "팩트 확정(승인·적립)" 은어 괄호 → 자연어, "게이트 우회 기록은 허용되지 않습니다" →
  "게이트를 거치지 않은 기록은 받지 않습니다" 등으로 완화. STATUS_TEXT의 "확립" → "확정"
  ("아카이브"는 도메인 용어로 유지 가능하나 "보관됨" 검토)
- `frontend/src/features/interview/views/CompactCard.tsx` — "활성 {m}건" → "남은 팩트 {m}건",
  "활성에 남깁니다" → "살아 있는 팩트로 남깁니다" 등 "활성" 장소명사 사용 정리
- `frontend/src/features/interview/views/InterviewPanel.tsx` — "원인 불명" → "알 수 없는 오류"
- `frontend/src/features/interview/views/InterviewGates.tsx` — "승인 · 적립" → "승인 · 기록",
  "반려 (다시 제시)" → "거절 (다시 제시)" 등
- `frontend/src/features/interview/views/InterviewFeed.tsx` — "팩트 적립을 준비하는 중…" →
  "팩트 기록을 준비하는 중…" 등
- `frontend/src/features/plan/views/PlanPanel.tsx` — "플랜" → "plan", "(이전 세대 없음)"·"(이전 세대)"·
  "이전 세대 대비" → "(이전 버전 없음)"·"(이전 버전)"·"이전 버전과 비교",
  "승인 (파생 단계 진입)" → "승인 (산출물 생성 단계로 넘어갑니다)" 등
- `frontend/src/features/outputs/views/OutputsPanel.tsx` — "채번 규칙" → "버전 번호 규칙",
  "결정론적으로 생성합니다" → "Python 빌더가 자동으로 생성합니다", "(원칙 5)" 삭제 또는 자연어 부연,
  "문서유형선택" → "문서 유형을 선택하세요", "수치 무결성 미달 N건" → "수치 검증에서 문제 N건",
  "결정론 빌드" 제목 → "자동 빌드"
- `frontend/src/features/review/views/ReviewPanel.tsx` — "결정론 대조" → "자동 대조",
  "선택 항목 plan에 반영 (새 세대)" → "선택한 항목을 plan에 반영 (새 버전 만들기)",
  "plan에 고쳐" → "plan을 고쳐", "세대(초안)을" 겹조사 정리, "(FR-4.3 — SSOT 게이트)" 내부 참조 정리
- `frontend/src/shared/lib/jobs.ts` — "결정론 빌드 중" → "산출물 조립 중", 전체 문구 하세요체 통일
- `frontend/src/shared/lib/labels.ts` — "대체됨" → "이전 버전", "이전 세대" → "이전 버전"
  (두 라벨의 의도적 차이는 주석 확인 후 유지)
- `frontend/src/features/review/viewmodels/useReviews.ts` — "결정론+LLM 검수" → "자동 검사+LLM 검수",
  "작업 큐 진입" 경직 표현 완화
- `frontend/src/features/plan/viewmodels/usePlans.ts` — "파생물을 생성하세요" → "산출물을 생성하세요"
- 그 외 위 파일들을 읽다가 발견하는 사용자 노출 문자(안내문·placeholder·aria-label)도 기준표에
  맞춰 수정한다. 단 `src/api/types.gen.ts`(자동 생성물)은 건드리지 않는다.

문구를 바꿀 때는 정보 손실이 없게 한다 — 예: "채번 규칙: 문서제목_vNN.확장자 — 절대 덮어쓰지 않습니다
(원칙 5)"는 "버전 번호 규칙: 문서제목_vNN.확장자 — 같은 파일을 점대로 덮어쓰지 않습니다" 수준으로
내용을 유지하면서 자연스럽게. "(미확정)" 같은 규약 마커는 그대로 둔다.

## Acceptance Criteria

```bash
npm run build
```

(frontend/ 디렉토리에서 — tsc --noEmit 포함)

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - View에서 fetch·서버 데이터 로직을 추가하지 않았는가? (문자 교체만 해야 한다)
   - 백엔드 API 계약 문자(에러 응답 코드, 필드명)를 건드리지 않았는가?
   - CLAUDE.md 설계 원칙 위반 없음(SSOT — 파생물 직접 수정 없음)?
3. 결과에 따라 `phases/refine-tone-strings/index.json`의 step 1을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "프론트엔드 UI 문자 전면 순화(용어 기준표 적용·하세요체 통일) — views/shared-lib/viewmodels N개 파일, npm run build 통과"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `frontend/src/api/types.gen.ts`를 직접 수정하지 마라. 이유: `npm run gen:types`으로 생성되는
  자동 생성물이다.
- 서버가 보내는 에러/상태 문자열의 원본 매핑 로직(jobs.ts의 에러 분류 키 등)을 바꾸지 마라. 이유:
  백엔드 계약 문자열과 매칭되는 키를 깨뜨리면 에러 분류가 동작하지 않는다. 라벨 문자만 바꾼다.
- View 컴포넌트에 새 로직을 추가하지 마라. 이유: 이 step은 문자 순화가 목적이고, 로직은 viewmodel
  소관이다 (가이드 §4.3).
- 기존 테스트를 깨뜨리지 마라.