# 기본 추천 아키텍처·디자인 가이드라인 (Modular Monolith & React MVVM)

> **이 문서의 용도 — 기본 추천 베이스라인**
>
> 본 문서는 프로젝트에 별도의 아키텍처 계획이나 확정된 설계 결정이 없을 때 기본으로 제안하는 추천 베이스라인이다.
>
> - **우선순위:** 프로젝트 인터뷰에서 확정된 결정(팩트)이 본 문서의 기본값보다 우선한다. 충돌 시 확정 팩트를 따른다.
> - **채택 절차:** 본 문서의 기본값은 확정이 아니라 **제안**이다. 인터뷰에서 결정+이유+대안 형태로 제안하고, 사용자 확인(팩트 승인) 후에야 확정한다. 사용자가 이견을 내면 본 문서 항목을 참고해 대안과 함께 재제안한다.
> - 본 문서의 구체적 예시(모듈명, PG 연동 등)는 예시일 뿐이며, 프로젝트 도메인에 맞게 치환한다.

본 문서는 프로젝트 계획 수립(인터뷰·개발설계서 작성)과 구현 단계(AI 코딩 어시스턴트, 팀원)에서 참조할 아키텍처 규칙, 디렉토리 구조, 디자인 패턴의 기본 권장 컨벤션을 제안한다.

---

## 1. 시스템 아키텍처: 모듈러 모놀리식 (기본 추천)

백엔드는 **Modular Monolith** 아키텍처를 기본 추천한다.
**이유:** 소규모~중규모 서비스에서 마이크로서비스 대비 배포·운영 복잡도와 비용이 낮으면서, 모듈 경계를 명확히 해 추후 모듈 단위 분리도 가능한 중간 지점이기 때문이다.

### 1.1 기본 원칙
1. **모듈 독립성:** 각 도메인(모듈)은 독립적인 영역으로 동작하며, 도메인 내부 구현 상세를 외부에 노출하지 않는다.
2. **엄격한 경계:** 모듈 간 직접 참조는 명시적인 Public Interface(Service/Facade)로만 허용한다. 다른 모듈의 DB 테이블이나 내부 Internal Repository에 직접 접근하는 것은 금지한다.
3. **이벤트 기반 결합 (선택):** 모듈 간 강한 결합을 해제할 필요가 있을 때 도메인 이벤트를 활용한다.

### 1.2 모듈 디렉토리 구조 (예시)
아래 모듈명(user, payment, notification)은 예시다. 프로젝트 도메인에 맞게 치환한다.

```
src/
├── modules/
│   ├── user/                    # [사용자 도메인 모듈]
│   │   ├── domain/              # 비즈니스 엔티티 및 핵심 로직
│   │   ├── application/         # 유스케이스, 서비스, DTO
│   │   ├── infrastructure/      # DB 접근(ORM), 외부 API 연동
│   │   ├── presentation/        # Controller / API Endpoint
│   │   └── user_facade.py       # 타 모듈에 제공하는 Public Interface
│   ├── payment/                 # [결제 도메인 모듈]
│   └── notification/            # [알림 도메인 모듈]
├── shared/                      # 공통 유틸리티 및 기반 클래스
│   ├── config/
│   ├── database/
│   └── errors/
└── main.py                      # Application Entrypoint
```

---

## 2. 프론트엔드 아키텍처: React Feature-driven MVVM (기본 추천)

프론트엔드는 UI와 비즈니스·상태 로직을 분리하는 **Feature-driven MVVM**을 기본 추천한다.
**이유:** 컴포넌트는 표현에만 집중해 재사용성을 높이고, 상태·로직을 훅 단위로 격리해 테스트와 유지보수가 쉬워지기 때문이다.

### 2.1 역할 정의
* **Model (M):** API 호출, 데이터 변환(DTO), 도메인 데이터 구조 정의.
* **ViewModel (VM):** 커스텀 훅 기반으로 상태(State) 관리, 비즈니스 처리 로직, UI 이벤트 핸들러를 보유. View에 필요한 상태만 반환.
* **View (V):** UI 표현에만 집중하는 React 컴포넌트(JSX/TSX). 비즈니스 로직을 가지지 않고 ViewModel이 제공하는 상태와 함수를 사용.

### 2.2 Feature 디렉토리 구조 (예시)
기능명(auth, checkout)은 예시다. 프로젝트 도메인에 맞게 치환한다.

```
src/
├── features/
│   ├── auth/                    # [인증 기능 모듈]
│   │   ├── models/              # DTO, API 호출 함수, Types
│   │   ├── viewmodels/          # 커스텀 훅 (useAuthViewModel.ts)
│   │   └── views/               # UI 컴포넌트 (LoginPage.tsx, AuthForm.tsx)
│   └── checkout/                # [주문 기능 모듈]
├── shared/                      # 공통 UI 컴포넌트, 유틸, Global Store
│   ├── components/
│   └── utils/
└── App.tsx
```

### 2.3 React MVVM 패턴 예시 (축약)
새 프론트엔드 코드는 아래 역할 분리 패턴을 따른다.

```tsx
// 1. Model — features/auth/models/auth.api.ts : API 호출과 DTO만
export const loginApi = (req: LoginRequest): Promise<UserProfile> => api.post('/auth/login', req);

// 2. ViewModel — features/auth/viewmodels/useLoginViewModel.ts : 상태·로직을 훅으로 격리
export function useLoginViewModel() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const handleLogin = async (req: LoginRequest) => {
    setLoading(true);
    try { setUser(await loginApi(req)); } finally { setLoading(false); }
  };
  return { user, loading, handleLogin };
}

// 3. View — features/auth/views/LoginForm.tsx : 표현만 담당, 로직 없음
export function LoginForm() {
  const { user, loading, handleLogin } = useLoginViewModel();
  if (loading) return <div>Loading...</div>;
  if (user) return <div>Welcome {user.name}!</div>;
  return <LoginFormView onSubmit={handleLogin} />;
}
```

---

## 3. 디자인 패턴 기본 추천

신규 코드 작성 시 다음 패턴 적용을 기본으로 권장한다.

### 3.1 Facade 패턴 (외부 연동·모듈 간 통신)
* **적용 대상:** PG 연동(예시: 토스, 카카오페이), 외부 알림 서비스(SMS, Email), 모듈 간 통신.
* **원칙:** 복잡한 외부 SDK나 타 모듈 내부 구조와 직접 상호작용하지 않고 단일 `Facade` 클래스를 거치도록 구현한다.

```typescript
// 예시: 외부 결제 Facade
export class PaymentFacade {
  async processPayment(orderId: string, amount: number) {
    // 외부 SDK 호출 및 복잡한 세부 절차 은닉
  }
}
```

### 3.2 Strategy 패턴 (가변적 로직 교체)
* **적용 대상:** 런타임에 실행 로직을 교체해야 하는 비즈니스 로직(알림 채널, 결제 수단 등).
* **원칙:** 인터페이스를 정의하고, 구체적인 전략 클래스를 구현해 의존성 주입(DI) 형태로 사용한다.

---

## 4. 기본 제약·비목표

계획 수립·구현 단계에서 기본으로 권장하는 제약이다. (프로젝트 확정 결정이 이 항목보다 우선한다.)

1. **Pragmatic 유지:** MVP 단계에서는 사용되지 않는 불필요한 추상화 레이어(과도한 Interface, DTO 변환기)를 임의로 추가하지 않는다.
2. **모듈 경계 존중:** 타 모듈의 내부 DB 모델이나 Internal 파일 경로를 import하지 않고, 필요 시 `facade`나 `shared`를 경유한다.
3. **React MVVM 엄수:** React 컴포넌트 내부에 `useEffect`나 `fetch` 로직을 직접 넣지 않고, ViewModel(커스텀 훅)로 격리한다.