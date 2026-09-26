# Claude Code 최적화 개발 워크플로우 가이드

본 문서는 Claude Code CLI 환경에서 토큰(Context Window) 사용량을 최소화하고, **[MVP → 리팩토링 → 고도화]** 및 **[기획 → 구현 → 검증]** 프로세스를 안정적으로 수행하기 위한 표준 운영 가이드입니다.

---

## 1. 컨텍스트(Token) 최적화 3대 원칙

1. **명시적 작업 범위 설정 및 Git 활용**
   * 각 Phase/Task 완료 후 반드시 Git Commit을 수행하여 상태를 저장합니다.
   * 새로운 작업 시작 시 "이전 작업은 완료됨. 다음 Task 진행:" 으로 명확히 선언합니다.
   * 각 Task별로 새로운 Claude Code 세션을 시작하여 맥락을 분리합니다.

2. **프로젝트 파일 구조 최적화**
   * `node_modules/`, `dist/`, `.git/`, `build/`, 대용량 로그/데이터셋 등은 `.gitignore`에 포함하여 불필요한 파일이 Claude에 노출되지 않도록 합니다.
   * 초기 대화에서 프로젝트 구조 설명을 최소화합니다.

3. **문서 기반 맥락 관리**
   * 프로젝트 루트에 `CLAUDE.md` 또는 `DEVELOPMENT.md` 파일을 작성하여 빌드, 테스트, 코드 스타일 규칙, 디렉토리 구조 등을 사전 정의합니다.
   * 작업 시작 시 명시적으로 **"README.md와 CLAUDE.md를 먼저 읽고 이 가이드에 맞춰 진행해줘"** 라고 지시합니다.

---

## 2. 전역 가드레일 (`CLAUDE.md` 작성 가이드)

프로젝트 루트에 `CLAUDE.md` 파일을 생성하고, 작업 시작 시 이 파일을 먼저 읽도록 명시적으로 지시하면 반복 프롬프트 작성에 들어가는 토큰을 크게 절약할 수 있습니다.

### CLAUDE.md 템플릿

```markdown
# 프로젝트 개발 및 행동 수칙

## 프로젝트 개요
- [프로젝트명]
- 기술 스택: [언어, 프레임워크, 주요 라이브러리]
- 진입점: [main.py, index.js 등]

## 디렉토리 구조
```
src/
  ├── core/      # 핵심 비즈니스 로직
  ├── modules/   # 기능별 모듈
  ├── utils/     # 유틸리티 함수
  └── tests/     # 테스트 코드
docs/
  ├── TASKS.md   # 전체 작업 로드맵
  └── tasks/     # Task별 상세 명세
```

## 개발 규칙

1. **작업 범위 제한:** 명시적으로 지시한 파일 및 Task 범위 외의 코드는 임의로 수정하지 않는다.
2. **Spec-First 접근:** 명세서(task_spec)가 작성되기 전에 코드 작성을 먼저 시작하지 않는다.
3. **검증 필수:** 모든 구현 후에는 반드시 테스트 명령어를 통해 정상 동작을 확인한다.
4. **오류 복구:** 테스트 실패 시 원인을 파악하지 않은 상태로 코드를 임의 재작성하지 않는다.

## 빌드 & 테스트 명령어

### 개발 및 실행
- 개발 환경 실행: `npm start` / `python main.py`
- 개발 서버 (핫 리로드): `npm run dev`

### 테스트 (단계별)
- 유닛 테스트: `npm test` / `pytest`
- 스모크 테스트: `npm run test:smoke` / `pytest -m smoke` (선택적)
- E2E 테스트: `npm run test:e2e` / `pytest -m e2e` (선택적)
- 전체 테스트: `npm run test:all`

### 빌드 & 배포 검증
- 빌드: `npm run build`
- 린트: `npm run lint`
- 타입 체크: `npm run type-check` (TypeScript인 경우)
- 배포 전 최종 검증: `npm run verify` 또는 `./scripts/verify.sh`

## 코드 스타일

- 들여쓰기: [공백 2칸 / 4칸 / 탭]
- 명명 규칙: camelCase / snake_case
- 주석: [규칙 정의]
```

---

## 3. 로드맵 단계별 처리 프로세스 (Phase)

```
Phase 0: 전체 로드맵 및 Task 분할 (docs/TASKS.md)
   │
   ├── Phase 1: MVP 구현 (핵심 기능 최소 작동)
   │
   ├── Phase 2: 리팩토링 (구조화, 예외 처리, 테스트 구축)
   │
   └── Phase 3: 고도화 (성능 최적화, 신규 확장 기능)
```

### Phase 0: 작업 분할 지시 프롬프트

> "우리는 [프로젝트 목표]를 개발하려고 해. 바로 코드를 작성하지 말고, 요구사항을 분석해서 `docs/TASKS.md` 파일로 실행 계획을 작성해 줘.
>
> 작업은 아래 3단계로 구성해 줘:
> 1. Phase 1 (MVP): 핵심 동작만 가능한 최소 구현
> 2. Phase 2 (Refactoring): 코드 구조화, 에러 처리, Clean Architecture 적용
> 3. Phase 3 (Advanced): 기능 고도화, 성능 최적화, 추가 기능
>
> 각 Task는 대화 3~5회 이내로 끝낼 수 있는 Atomic 단위를 가져야 해."

---

## 4. Task별 3단계 정밀 실행 사이클 (Standard Task Loop)

모든 개별 Task는 **'기획 ➔ 구현 ➔ 검증'** 3단계를 거쳐 진행합니다.

```
┌───────────────────────────────────────────────────────────┐
│ Task N 실행 루프                                           │
│  Step 1. 기획 (Plan)   → docs/tasks/task_N.md 작성          │
│  Step 2. 구현 (Code)   → 명세 범위 내 소스코드 수정        │
│  Step 3. 검증 (Verify) → 유닛 테스트 및 빌드 검증 실행      │
└───────────────────────────────────────────────────────────┘
```

### Step 1: 기획 (Planning & Spec)
* **목적:** 코드를 직접 수정하기 전에 설계와 검증 기준을 정립하여 환각 및 오류 방지.
* **프롬프트:**
  > "CLAUDE.md를 읽고 `docs/TASKS.md`의 **Task [X.X]** 작업을 기획해 줘.
  > 소스코드를 직접 수정하지 말고, `docs/tasks/task_[X_X].md` 파일에 다음 항목을 작성해 줘:
  > 1. 수정/생성할 대상 파일 목록
  > 2. 핵심 인터페이스 및 데이터 흐름 설계
  > 3. 예외 상황 처리 계획
  > 4. 검증 기준 (테스트 시나리오 및 실행할 CLI 명령어)"

### Step 2: 구현 (Implementation)
* **목적:** 작성된 명세서 범위를 벗어나지 않도록 작업 범위를 제한.
* **프롬프트:**
  > "`docs/tasks/task_[X_X].md` 명세서에 맞춰 구현을 진행해 줘.
  > - 명세에 정의된 파일 및 수정 범위 내에서만 작업할 것
  > - 명세에 없는 불필요한 구조 변경이나 추가 기능 개발 금지
  > - 작업 완료 후 변경된 파일 목록을 요약 보고할 것"

### Step 3: 검증 (Verification)
* **목적:** 단계별 테스트를 거쳐 품질을 확보하고, 배포 가능 상태까지 검증하여 완료 처리.
* **테스트 레벨:**
  1. **유닛 테스트 (Unit Tests)** - 개별 함수/메서드의 정상 동작
  2. **통합 테스트 (Integration Tests)** - 모듈 간 상호작용 검증
  3. **스모크 테스트 (Smoke Tests)** - 핵심 기능의 기본 동작만 빠르게 확인
  4. **E2E 테스트 (End-to-End Tests)** - 사용자 관점의 전체 워크플로우 검증

* **프롬프트:**
  > "`docs/tasks/task_[X_X].md`의 검증 절차를 수행해 줘.
  > 
  > **1단계: 유닛 + 통합 테스트**
  > - 해당 기능에 대한 유닛/통합 테스트 코드 작성
  > - `npm test` 또는 `pytest` 실행 및 모든 테스트 통과 확인
  > 
  > **2단계: 스모크 테스트**
  > - 핵심 기능만 빠르게 검증하는 스모크 테스트 코드 작성 (선택적이나 권장)
  > - 예: API 응답 상태 코드, 기본 동작 흐름, DB 연결 상태 등
  > - `npm run test:smoke` 또는 `pytest -m smoke` 실행
  > 
  > **3단계: E2E 테스트** (해당 Task가 E2E 범위인 경우)
  > - 사용자 관점의 전체 워크플로우 시뮬레이션 (CLI 명령 / API 호출 / UI 인터랙션)
  > - 예: 할일 생성 → 조회 → 수정 → 삭제의 전체 시나리오
  > - `npm run test:e2e` 또는 `pytest -m e2e` 실행
  > 
  > **4단계: 빌드 + 배포 가능성 검증**
  > - `npm run build` 또는 빌드 명령 실행하여 성공 확인
  > - 결과 바이너리/패키지가 정상 생성되었는지 확인
  > 
  > **실패 시:**
  > - 원인을 파악하지 않은 상태로 코드를 임의 재작성하지 말 것
  > - 실패 로그를 분석 후 3회 이상 수정 실패 시 롤백 권장
  > 
  > 모든 검증이 완료되면 최종 결과를 보고해 줘."

---

## 5. 실전 예외 처리 및 고급 운영 팁

### 1. 롤백 및 에러 복구 (Error Recovery)
구현이나 검증 단계에서 로직이 복잡하게 꼬여 오류 수정을 반복하게 되면 컨텍스트와 토큰 소모가 급증합니다.

**해결책:** 3회 이상 수정 실패 시, 대화로 고치려 하지 말고 즉시 롤백 후 새로 시작합니다.

```bash
# 1. 터미널에서 이전 커밋 상태로 롤백
git restore .
git clean -fd

# 2. 새로운 Claude Code 세션 시작
# (기존 세션의 대화 맥락을 초기화)
```

**재시작 프롬프트:**
> "CLAUDE.md를 먼저 읽고, `docs/tasks/task_[X_X].md` 명세서를 다시 확인한 후 처음부터 새로 구현해 줘. 이전 수정 시 오류가 발생했던 원인은 [오류 원인 요약]이었으니 이를 참고해서 재작성해 줘."

### 2. 파일 권한 및 안전장치 (Permission Control)
* 파일 수정 및 일반 작업 시에는 기본 권한 확인 모드를 유지합니다.
* 소스 제어(Git Commit)가 완료된 깨끗한 Working Directory 상태에서만 작업을 진행합니다.
* 무분별한 권한 생략 옵션의 사용은 지양합니다.

### 3. 외부 스키마 및 대용량 맥락 참조 최적화 (Schema / 큰 파일)
* 대용량 DB 스키마나 API 명세 전체를 Claude에게 읽게 하면 토큰 사용량이 폭증합니다.

**해결책:** 필요한 부분만 별도의 `docs/schema_summary.md` 파일로 추출하여 관리합니다.

```markdown
# docs/schema_summary.md 예시

## User 테이블
- id (PK)
- name (string)
- email (string, unique)
- created_at (timestamp)

## Post 테이블
- id (PK)
- user_id (FK)
- title (string)
- content (text)
```

작업 시 "docs/schema_summary.md를 참고해서 진행해줘" 라고 명시하면 불필요한 정보 노출을 줄일 수 있습니다.

---

## 6. Task 완료 후 정리 절차

1. **모든 테스트 통과 확인** (단계별)
   ```bash
   # 1. 유닛 테스트
   npm test
   # 또는
   pytest

   # 2. 스모크 테스트 (선택적이나 권장)
   npm run test:smoke
   # 또는
   pytest -m smoke

   # 3. E2E 테스트 (해당하는 경우)
   npm run test:e2e
   # 또는
   pytest -m e2e
   ```

2. **빌드 검증**
   ```bash
   npm run build
   # 또는 Python의 경우
   python -m py_compile src/**/*.py
   ```

3. **변경사항 Git Commit 수행**
   ```bash
   git add .
   git commit -m "feat: complete Task [X.X] - planned, implemented & verified (all tests passed)"
   ```

4. **다음 Task 준비**
   * 새로운 Claude Code 세션 시작
   * 프롬프트 시작: "CLAUDE.md와 docs/TASKS.md를 읽고, 다음 Task [X.X]를 진행해 줘"

---

## 7. 테스트 전략 가이드 (Test Strategy)

### 테스트 피라미드 구조

```
           E2E Tests (전체 워크플로우)
              ↑
       Integration Tests (모듈 간 상호작용)
              ↑
       Unit Tests (개별 함수/메서드)
              ↑
       Smoke Tests (핵심 기능만 빠르게)
        (기초 안전장치)
```

### 각 테스트 레벨별 특징

| 레벨 | 목적 | 범위 | 실행 시간 | Phase별 필수 여부 |
|------|------|------|---------|-----------------|
| **Smoke** | 배포 가능한 기본 상태 확인 | 핵심 기능만 | 매우 빠름 (< 1분) | Phase 1부터 권장 |
| **Unit** | 개별 함수 정상 동작 | 단일 모듈 | 빠름 (1~5분) | Phase 2 필수 |
| **Integration** | 모듈 간 상호작용 검증 | 여러 모듈 | 중간 (5~15분) | Phase 2 필수 |
| **E2E** | 사용자 관점 전체 시나리오 | 전체 시스템 | 느림 (10~30분) | Phase 3 필수 |

### Task별 테스트 전략

**Phase 1 (MVP):** Smoke Test 선택적 + 기본 유닛 테스트
```bash
# Phase 1 검증 명령어
npm test                    # 유닛 테스트
npm run test:smoke          # 스모크 테스트 (선택적)
npm run build               # 빌드 검증
```

**Phase 2 (Refactoring):** 전체 테스트 커버리지
```bash
# Phase 2 검증 명령어
npm test                    # 유닛 + 통합 테스트
npm run test:smoke          # 스모크 테스트
npm run test:coverage       # 커버리지 리포트
npm run lint                # 린트 검증
```

**Phase 3 (Advanced):** E2E 테스트 추가
```bash
# Phase 3 검증 명령어
npm test                    # 모든 유닛/통합 테스트
npm run test:e2e            # E2E 테스트
npm run test:coverage       # 커버리지 검증 (80% 이상 목표)
npm run type-check          # 타입 체크
npm run build               # 최종 빌드 검증
```

### 테스트 파일 구조 예시

```
tests/
├── unit/
│   ├── models/
│   │   └── test_task.py
│   ├── utils/
│   │   └── test_helpers.py
│   └── conftest.py
├── integration/
│   ├── test_api_endpoints.py
│   └── test_database.py
├── smoke/
│   ├── test_basic_health.py
│   └── test_critical_paths.py
├── e2e/
│   ├── test_create_task_workflow.py
│   ├── test_update_task_workflow.py
│   └── test_delete_task_workflow.py
└── fixtures/
    ├── sample_data.json
    └── mock_database.py
```

### pytest 마크 활용 예시

```python
# tests/smoke/test_basic_health.py
import pytest

@pytest.mark.smoke
def test_api_health_check():
    """API 서버 기동 확인"""
    response = client.get("/health")
    assert response.status_code == 200

@pytest.mark.smoke
def test_task_list_empty():
    """빈 Task 목록 조회"""
    response = client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []
```

```bash
# 스모크 테스트만 실행
pytest -m smoke

# E2E 테스트만 실행
pytest -m e2e

# 모든 테스트 실행
pytest
```

---

## 8. 체크리스트: Task 시작 전 확인사항

- [ ] `CLAUDE.md` 파일이 프로젝트 루트에 존재하는가?
- [ ] `docs/TASKS.md`에 전체 로드맵이 작성되었는가?
- [ ] `.gitignore`에 대용량 파일/디렉토리가 모두 등록되었는가?
- [ ] 이전 Task에 대한 Git Commit이 완료되었는가?
- [ ] 새로운 Claude Code 세션을 시작했는가?
- [ ] 첫 프롬프트에서 "CLAUDE.md를 읽고" 명시했는가?

---

## 9. 실전 예제

### 예제: 할일 관리 앱 개발

**초기 프롬프트:**
```
우리는 Python + FastAPI 기반 할일 관리 REST API를 개발하려고 해.

CLAUDE.md와 docs/TASKS.md를 먼저 읽고, 
다음과 같이 3 Phase로 작업을 분할해 줘:

Phase 1: 기본 CRUD 구현 (Task 모델, 기본 엔드포인트)
Phase 2: 데이터 검증, 예외 처리, 테스트 구축
Phase 3: 사용자 인증, 필터링, 성능 최적화

각 Phase 내 Task는 대화 3~5회 이내로 끝낼 수 있어야 해.
docs/TASKS.md 형식으로 작성해 줘.
```

**Phase 1, Task 1 시작:**
```
CLAUDE.md와 docs/TASKS.md를 읽고, Phase 1 - Task 1.1을 기획해 줘.
`docs/tasks/task_1_1.md` 파일에 다음을 작성해:

1. 수정할 파일 목록 (src/models.py, src/main.py 등)
2. Task 완료 후의 API 응답 예시
3. 테스트할 시나리오 (POST /tasks, GET /tasks 등)
4. 검증 실행 명령어 (pytest 커맨드)
```

**Phase 1, Task 1 구현:**
```
`docs/tasks/task_1_1.md` 명세에 맞춰 구현을 진행해 줘.
명세에 정의된 파일 범위 내에서만 작업하고,
추가 기능이나 구조 변경은 하지 말아 줘.
```

**Phase 1, Task 1 검증:**
```
`docs/tasks/task_1_1.md`의 검증을 진행해 줘.

**Step 1: 유닛 테스트**
1. 필요한 테스트 코드 작성 (test_models.py, test_main.py)
2. pytest 실행: pytest tests/unit/
3. 모든 테스트가 통과할 때까지 수정

**Step 2: 스모크 테스트 (선택적이나 권장)**
1. 기본 기능 스모크 테스트 작성 (tests/smoke/)
   - API 서버 기동 확인
   - GET /tasks 응답 상태 200 확인
   - POST /tasks 요청 성공 확인
2. pytest -m smoke 실행

**Step 3: E2E 테스트** (필요시)
1. 전체 워크플로우 E2E 테스트 작성
   - POST /tasks (할일 생성)
   - GET /tasks (목록 조회)
   - PATCH /tasks/{id} (할일 수정)
   - DELETE /tasks/{id} (할일 삭제)
2. pytest -m e2e 실행

**Step 4: 빌드 검증**
1. 빌드 성공 확인: python -m py_compile src/**/*.py
2. 최종 리포트 작성
```

**Task 완료 후:**
```bash
# 최종 테스트 실행
pytest
pytest -m smoke
pytest -m e2e

# 빌드 검증
python -m py_compile src/**/*.py

# 커밋
git add .
git commit -m "feat: complete Task 1.1 - basic Task CRUD (all tests passed)"

# 새로운 Claude Code 세션 시작
```

---

## 10. 요약

| 항목 | 핵심 내용 |
|------|---------|
| **컨텍스트 최적화** | Git + 문서 기반 관리, `.gitignore` 활용 |
| **작업 구조** | Phase 0-3 분할 + Task별 Spec-First 3단계 |
| **실행 방식** | 기획 → 구현 → 검증 (3회 실패 시 롤백) |
| **검증 전략** | Smoke → Unit → Integration → E2E (테스트 피라미드) |
| **문서 중심** | CLAUDE.md (공통규칙), TASKS.md (로드맵), task_X_X.md (상세명세) |
| **Git 활용** | Task 완료 시마다 Commit으로 상태 분리 |

### 검증 단계 빠른 참조

```bash
# Phase 1 (MVP)
npm run test:smoke && npm test && npm run build

# Phase 2 (Refactoring)
npm test && npm run test:smoke && npm run test:coverage && npm run lint

# Phase 3 (Advanced)
npm test && npm run test:e2e && npm run test:coverage && npm run type-check && npm run build
```

이 워크플로우를 따르면 **토큰 사용량 절감, 안정적인 진행, 오류 빠른 복구, 배포 가능한 품질 보증**이 가능합니다.
