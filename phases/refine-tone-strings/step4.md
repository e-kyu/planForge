# Step 4: docs-sync

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 인터뷰 턴 계약 규칙(계약 4종 동시 점검), 문서 갱신 관례
- `/docs/INTERVIEW-TURN-CONTRACT.md` — step 0에서 갱신된 대조표·변경 이력 최종 확인
- `/phases/refine-tone-strings/step0.md`~`/phases/refine-tone-strings/step3.md` — 이전 step(완료) 요약
- `/docs/ARCHITECTURE.md`·`/docs/ADR.md` — 용어 사용 예("세대"·"채번" 등) 확인용

## 작업

목표: task 전체의 정합성을 문서·전체 회귀로 마감한다. **코드를 새로 고치지 않고 검증·문서 동기화만 한다.**

1. **계약 대조 최종 확인**: `docs/INTERVIEW-TURN-CONTRACT.md`의 "동시 점검 세트 (계약 4종)" 표가
   실제 코드와 일치하는지 확인한다:
   - `backend/app/agents/tools.py`에 `MAX_QUESTION_LEN=300`·빈 본문 거부·300자 초과 거부가 있고
     `_PROSE_OPTION_LINE` 선택지 나열 거부가 유지되는가
   - `interview.md` 프롬프트에 "배경 1~2문장 + 질문 1문장(300자)" 규칙·하세요체 톤 지시가 있고
     "본문은 질문 한 문장" 문구가 제거되었는가
   - 변경 이력에 2026-10-31 항목이 있고 4종을 한 커밋에 갱신함을 명시하는가
   - 빠진 부분이 있으면 이 step에서 보완한다 (작은 보완은 허용).
2. **문서 용어 점검**: `docs/` 하위에서 이번 변경으로 **모순**이 생긴 서술만 수정한다 (예: 계약
   문서·UI 가이드가 "본문은 한 문장"을 아직 서술하고 있는 경우). 단 docs는 개발자 문서이므로
   "세대"·"채번" 등 개발 용어를 전면 순화하지 않는다 — 사용자 노출 문자만이 순화 대상이었다
   (사용자 결정사항). 단, 이번 계약 변경으로 **틀려진** 내용(구조 제약 서술)만 고친다.
3. **전체 회귀**: 최종 확인 커맨드 실행.
4. **README 화면 문구**: 루트 `README.md`에 UI 스크린샷 설명 등에 이번에 바꾼 문자("세대",
   "채번" 등)가 사용자 노출 예시로 인용되어 **틀려진** 부분이 있는지 확인하고 최소한만 수정한다.

## Acceptance Criteria

```bash
python -m pytest -q
npm run build
```

(각각 저장소 루트에서 `PYTHONUTF8=1` 환경 / frontend/ 디렉토리에서)

## 검증 절차

1. 위 AC 커맨드를 둘 다 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 계약 4종이 서로 정합인가 (스키마 ↔ 프롬프트 ↔ 계약 문서 ↔ 테스트)?
   - CLAUDE.md 설계 원칙 8개를 전 step에서 위반한 부분이 없는가?
   - `git status`로 ignored 경로(`workspaces/`·`sources/`·`data/`·`backend/planforge/config.json`)
     가 커밋 대상에 섞이지 않았는지 확인한다.
3. 결과에 따라 `phases/refine-tone-strings/index.json`의 step 4을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "계약 4종 정합 확인·문서 동기화 마감·전체 회귀 통과(pytest+frontend build)"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- docs의 개발 용어("세대"·"채번"·"골격" 등)를 전면 바꾸지 마라. 이유: docs는 개발자 문서이고,
  순화 대상은 사용자 노출 문자로 한정되었다(사용자 결정). 계약 변경으로 틀려진 서술만 고친다.
- 새 기능·리팩터링을 하지 마라. 이유: 이 step은 검증·문서 동기화 마감 step이다.
- `docs/INTERVIEW-TURN-CONTRACT.md`의 계약 내용(선택지 나열 거부, 문항 수 상한, 도구 전용 출력 등)을
  완화하지 마라. 이유: 완화된 것은 본문 맥락(300자)뿐이며 나머지는 계속 유효하다.
- 기존 테스트를 깨뜨리지 마라.