# CLAUDE.md — report-agent 개발 규칙

이 저장소는 `docs/legacy/`의 Claude Code 기반 기획 문서 생성 에이전트를
Claude Code 없이 동작하는 웹 서비스로 이식하는 프로젝트다.
개발 요청서는 `AGENT-DEV-REQUEST.md`이며, 이 파일은 개발 세션 전체에서 유효한 계약을 담는다.

## 설계 원칙 계약 (AGENT-DEV-REQUEST.md §2.1 — 위반 시 구현 자체가 오답)

1. **SSOT**: 콘텐츠의 유일한 원본은 plan.md(DB `Plan` 레코드)다. 파생물
   (slides.json·report.json·산출물)은 절대 직접 수정하지 않고 항상 원본에서 재생성한다.
   `workspaces/*/work/slides.json`, `work/report.json`, `workspaces/*/output/*`에 대한
   직접 쓰기/편집은 PreToolUse 훅(`.claude/hooks/guard_ssot.py`)이 차단한다 — 훅을
   우회할 방법을 만들지 말고, 차단 메시지를 보면 설계를 되돌아볼 것.
2. **LLM/코드 역할 분리**: LLM은 콘텐츠 변환만 한다. 파일 조립·좌표 배치·채번은
   Python 빌더(결정론)가 담당한다. LLM이 pptx/docx 바이너리를 만드는 코드는 금지.
3. **수치 무결성**: 수치·표·차트 데이터·`(미확정)` 표기·근거/출처 문자열은 plan과
   한 글자도 다르게 복사되지 않는다. 재구성(개조식→서술형)은 문장에만 적용.
4. **팩트 선(先)적립**: 확정 팩트는 먼저 팩트 저장소(DB `Fact`)에 기록 후 plan 반영.
   추측 수치는 `(미확정)` 명시.
5. **무손실 채번**: 산출물명 `<문서 제목>_vNN.<ext>`, 확장자별 독립 시퀀스, 절대 덮어쓰기
   금지(동시성 포함 — 빌드는 DB 작업 큐로 직렬화).
6. **다중 문서 태그**: `[문서: 제안서+개발설계서]` 태그로 문서별 필터링, 문서별 목차 재채번.
7. **디자인 토큰 4종 세트**: 색·폰트·여백 토큰 변경 시 **문서(SKILL.md)·토큰(theme.py)·
   렌더러(빌더)·샘플(samples)** 을 반드시 동시 수정. 하나만 고치는 PR은 리뷰에서 반려.
8. **골격 검증**: 파생물 생성 전 표지·목차·마무리·내용 슬라이드 각 1개 이상 검증, 미달 시 중단.

## 이식 대상 원문 (요약보다 원문이 권위 있다 — 작업 전 반드시 읽을 것)

| 원문 | 용도 |
|---|---|
| `docs/legacy/CLAUDE.md` | 전체 규칙·plan.md 포맷·report.json 스키마·버전 규칙의 원전 |
| `docs/legacy/commands/plan-doc.md` | 인터뷰 에이전트 행동 명세 (→ 백엔드 interview 단계 시스템 프롬프트) |
| `docs/legacy/commands/make-ppt.md` · `make-doc.md` | 파생물 생성 명세 (→ derive 단계 프롬프트) |
| `docs/legacy/commands/review-doc.md` | 검수 체크리스트 (→ review 단계 프롬프트) |
| `docs/legacy/commands/compact-log.md` | 팩트 압축 절차 (FR-6.1) |
| `docs/legacy/skills/SKILL.md` · `layouts.md` | 슬라이드 7종·색·폰트·좌표 + slides.json 스키마 |
| `docs/legacy/scripts/build_ppt.py` · `build_doc.py` · `theme.py` | 빌더 원형 — **로직 변경 금지, I/O 어댑터만 추가** |
| `docs/legacy/samples/*` | 계약 테스트 fixture (tests/로 이식 대상, 이식 전까지 직접 실행) |

## 개발 규칙

- 마일스톤 순서를 따른다: **M1(코어 엔진, CLI) → M2(백엔드) → M3(프론트엔드) → M4(검수·운영)**.
  M1이 전체 리스크의 대부분이므로 다른 작업과 섞지 않는다.
- 빌더 포팅 시: `docs/legacy/scripts/*.py`를 `backend/`로 가져오되 로직 변경 금지,
  경로/워크스페이스 주입만 어댑터로 처리한다.
- 테스트: `samples/*.sample.json`은 빌더 회귀(계약 테스트)로 잠근다. 수치 무결성
  검사는 단위 테스트로 상시 실행(`/numcheck`).
- LLM 호출은 `openai` SDK 기반 provider 추상화 계층으로만 한다. anthropic SDK 사용 금지.
- Windows 개발 환경: `PYTHONUTF8=1` 필수(settings.json env에 설정됨). 파일명 금지 문자
  정규화는 legacy `_sanitize_title` 규칙을 유지한다.
- 커밋 전 `git status`로 `workspaces/` 등 ignored 경로가 섞이지 않았는지 확인.

## 명령어

- `/kickoff` — 요청서 §8 참조 파일을 읽고 현재 마일스톤 진행 계획 제시 (새 세션 진입점)
- `/contract` — 계약 테스트(빌더 회귀) 실행
- `/numcheck` — 수치 무결성 대조 검증 실행

(테스트/빌드/마이그레이션 명령은 각 마일스톤에서 확정되는 대로 이 아래에 추가한다.)