---
title:  "[Go] Provider Pattern으로 멀티 인증 시스템 설계하기"
excerpt: "단순 컬럼 추가 vs 확장 가능한 설계, 그 사이에서 고민했던 기록"
categories:
  - Dev
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - Architecture
  - Provider Pattern
  - Authentication
toc: true
---

<br>

# 들어 가며

개발 중인 시스템에 새로운 인증 체계를 추가해야 했다. 기존에는 외부 플랫폼의 인증만 사용했는데, 이제 독립 인증 모드도 지원해야 했다. 

문제는 리소스 접근 제어였다. 기존에는 모든 리소스에 `organization_id`가 있어서 "이 리소스는 어느 조직 소유인가?"로 접근을 제어했다. 그런데 독립 인증 모드에서는? 시스템에 존재하는 독립적인 사용자가 만든 리소스는 어떤 조직에도 속하지 않는다. 

처음에는 단순하게, 리소스마다 `user_id`와 `organization_id`를 따로 관리하면 되지 않을까 생각했다. 하지만 곰곰이 생각해보니, 이 방식은 데이터 모델을 복잡하게 만들고 미래 확장성도 막는 구조였다. 결국 User와 Organization의 관계를 어떻게 설계할지 고민하게 됐고, 여러 인증 시스템을 유연하게 지원하기 위해 Provider Pattern을 도입하게 됐다. 

<br>

# 문제의 시작

## 기존 구조: 외부 플랫폼 인증 + 리소스 관리

기존 시스템은 연동된 외부 플랫폼의 인증에 전적으로 의존했다. 외부 플랫폼에서 토큰을 발급받고, 그 토큰으로 API를 호출하면, 미들웨어가 외부 API를 통해 토큰을 검증하고 조직 정보를 가져왔다.

```go
func (m *Middleware) RequireAuth() gin.HandlerFunc {
    return func(c *gin.Context) {
        token := extractToken(c)
        
        // 외부 API로 토큰 검증 및 조직 정보 조회
        resp, err := m.externalClient.GetOrganization(token)
        if err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"message": "unauthorized"})
            return
        }
        
        c.Set("organization_id", resp.Organization.Id)
        c.Next()
    }
}
```

<br>

리소스 관리도 이 `organization_id`에 의존했다. 모델, 프로젝트, 이벤트 등 모든 리소스 테이블에 `organization_id` 컬럼이 있었고, 조회 시에는 해당 조직의 리소스만 반환했다.

```go
// 모델 조회 - 해당 조직의 리소스만 반환
func (r *Repository) GetModels(organizationId int) ([]*Model, error) {
    query := `SELECT * FROM model WHERE organization_id = $1`
    // ...
}
```

<br>

단순하고 잘 동작했다. 외부 플랫폼의 조직 ID가 곧 시스템의 리소스 소유자였으니까.

<br>

## 새로운 요구사항: 멀티 인증

그런데 새로운 요구사항이 생겼다. 시스템 자체적으로도 사용자 인증을 지원해야 했다. 외부 플랫폼 연동 없이 시스템만 단독으로 사용하는 케이스가 생긴 것이다. 두 가지 인증 체계가 동시에 돌아가야 했다.

- **Standalone User**: 시스템 자체 JWT 인증
- **Organization User**: 외부 플랫폼 토큰 인증

<br>

## 첫 번째 고민: User와 Organization을 연결해야 하는가

여기서 한 가지 의문이 들 수 있다.

> "굳이 User에 Organization 정보를 넣어야 하나? 기존처럼 리소스(model, project)에만 `organization_id`를 두고, Standalone User가 사용할 때는 `user_id`로 접근 제어하면 되는 거 아닌가?"

처음에 내가 고려한 방식이다.

```go
// 리소스마다 user_id와 organization_id를 모두 관리
type Model struct {
    ID             uuid.UUID
    UserID         *uuid.UUID  // standalone user용
    OrganizationID *int        // organization user용
    // ...
}

// 접근 제어 로직이 분기됨
func (r *Repository) GetModels(ctx *gin.Context) ([]*Model, error) {
    if userID := ctx.GetString("user_id"); userID != "" {
        // standalone: user_id로 필터링
        query = `SELECT * FROM model WHERE user_id = $1`
    } else if orgID := ctx.GetInt("organization_id"); orgID > 0 {
        // organization: organization_id로 필터링
        query = `SELECT * FROM model WHERE organization_id = $1`
    }
    // ...
}
```

<br>

하지만 이 설계에는 몇 가지 문제가 있었다.

**1. 데이터 모델의 복잡성**

모든 리소스 테이블에 `user_id`와 `organization_id` 두 개의 nullable FK가 생긴다. 둘 중 하나는 항상 NULL이어야 하는데, 이런 배타적 관계(XOR)를 DB 레벨에서 강제하기가 까다롭다. "이 리소스는 누가 소유하는가?"라는 단순한 질문에 명확한 답을 주기 어려운 구조다.

**2. 비즈니스 로직의 분기**

접근 제어, 조회, 권한 검사 등 모든 로직에서 "Standalone인가, Organization인가"를 if-else로 분기해야 한다. 코드 전반에 이 분기가 퍼지면 유지보수가 어려워진다.

**3. 미래 확장성 차단**

더 큰 문제는 이 설계가 **User와 Organization의 관계 자체를 원천 차단**한다는 것이다.

당장은 User도 독립, Organization도 독립이니 상관없다. 그런데 만약 미래에 아래와 같은 시나리오가 발생한다면 어떻게 될까? 
- 시스템 내부에 조직 개념 도입
- Standalone User들도 팀을 만들어서 협업
- User X가 Organization A에 속하게 됨

리소스마다 `user_id`와 `organization_id`를 따로 관리하는 설계로는 다음 질문에 답할 수 없다.

```sql
-- user_id = X인 리소스들을 organization_id = A로 어떻게 마이그레이션?
UPDATE model 
SET organization_id = A 
WHERE user_id = X;

-- user_id는 어떻게 하지? 둘 다 채워진 레코드의 의미는?
-- user_id를 NULL로? 그럼 누가 만들었는지 추적 불가
-- 그대로 두기? 그럼 organization_id vs user_id 우선순위는?
```

결과적으로 이 설계는 미래 확장 가능성을 구조적으로 원천 차단하는 설계라는 생각에 이르렀다. 나중에 Standalone User들이 팀을 이루거나, 시스템 내부에 조직 개념이 생긴다면, `user_id`로 관리하던 리소스들을 `organization_id`로 옮겨야 하는데, 이 설계에서는 그 전환이 매우 까다롭다.

<br>

결국 **User 엔티티 자체에 Organization 소속 정보를 두는 것**이 더 자연스럽다는 결론에 도달했다. 리소스 소유권은 여전히 Organization 기준으로 관리하되, User가 어떤 Organization에 속하는지를 User 레벨에서 관리하는 것이다.

<br>

## 두 번째 고민: organization_id 컬럼 추가

User에 Organization 정보를 두기로 했다면, 가장 단순한 해결책은 `user` 테이블에 `organization_id` 컬럼을 추가하는 것이다.

```sql
ALTER TABLE user ADD COLUMN organization_id INTEGER;
```

<br>

로직도 간단하다. `organization_id`가 `NULL`이면 Standalone 사용자, 값이 있으면 Organization 사용자로 구분하면 된다.

```go
if user.OrganizationId == nil {
    // Standalone 사용자
} else {
    // Organization 사용자
}
```

구현은 빠르게 끝날 것 같았다. 하지만 뭔가 찜찜했다.

<br>

## 세 번째 고민: 확장 가능성

문제는 **확장성**이었다. 지금은 외부 플랫폼 하나만 있지만, 앞으로는 어떻게 될까?

- 시스템 자체에서도 Organization 개념을 도입하게 된다면?
- 다른 인증 시스템(NewCloud, Azure AD 등)이 붙게 된다면?

<br>

`organization_id` 하나로는 이런 질문에 답할 수 없었다. 값이 `123`일 때 이게 어느 시스템의 조직인지 알 수 없다. 플랫폼 A의 조직 `123`인지, 플랫폼 B의 조직 `123`인지, 아니면 자체 조직 `123`인지 구분할 방법이 없다.

```go
// organization_id = 123
// 이게 어느 시스템의 조직 123인가?
```

<br>

물론 지금 당장은 외부 플랫폼 하나뿐이다. 다른 조직 시스템을 고려할 일도, 시스템 내부에 조직 개념을 도입할 일도 당장은 없어 보인다. 하지만 나중에 그런 필요성이 생겼을 때, 지금의 단순한 설계가 발목을 잡을 게 뻔했다.

> 물론 YAGNI(You Aren't Gonna Need It) 원칙도 있다. 하지만 이건 단순히 "나중에 필요할지도 모르는 기능"을 미리 구현하는 게 아니라, **현재 설계가 미래 확장을 원천적으로 막는 구조인지** 점검하는 문제였다.

<br>

# 설계 방향

## 핵심 질문: 외부 조직을 어떻게 식별할 것인가

사실 `organization_id` 컬럼 하나만 추가하면 당장의 문제는 해결된다. 당장은 외부 플랫폼 하나뿐이니 문제없다. 하지만 나중에 다른 시스템이 붙는다면? 그때 가서 스키마를 뜯어고치는 건 마이그레이션 지옥이다. 지금 조금 더 고민해서 확장 가능한 구조를 가져 가고 싶었다.

핵심은, **외부 조직을 어떻게 식별할 것인가**였다.

시스템은 외부 조직들을 직접 관리하지 않는다. 대신 **외부 조직을 가리키는 참조(프록시)**만 저장한다. 

지금 외부 플랫폼 안에는 여러 조직이 있고, 나중에 NewCloud 같은 다른 시스템과 연동한다면 거기에도 자체 조직이 있을 것이다. 문제는 플랫폼 A의 조직 123과 플랫폼 B의 조직 123이 같은 숫자라도, 시스템 입장에서는 완전히 다른 엔티티여야 한다는 점이다. `organization_id` 하나로는 이 구분이 불가능하다.

<br>

## 세 가지 목표

확장 가능한 설계를 위해 세 가지 목표를 세웠다.

1. **Provider 기반 인증**: 각 외부 조직 시스템이 독립적인 인증 로직을 구현하되, 동일한 인터페이스로 관리
2. **스키마 정규화**: `organization_id` 하나가 아니라, `(provider_type, provider_id)` 조합으로 조직을 식별
3. **하위 호환성 유지**: 기존 외부 플랫폼 연동이 깨지지 않도록 점진적 마이그레이션

<br>

## 왜 Provider Pattern인가

인증 시스템 확장을 위해 여러 방법을 고려했다.

### if-else 분기

```go
if authType == "cloud_a" {
    // Cloud A 인증 로직
} else if authType == "cloud_b" {
    // Cloud B 인증 로직
} else if authType == "NewCloud" {
    // NewCloud 인증 로직
}
```

새로운 인증 시스템이 추가될 때마다 기존 코드를 수정해야 한다. Open/Closed 원칙 위반이다.

<br>

### Factory Pattern만 사용

```go
func CreateAuthenticator(authType string) Authenticator {
    switch authType {
    case "cloud_a":
        return NewCloudAAuth()
    // ...
    }
}
```

생성 로직은 캡슐화되지만, 동작 자체는 여전히 분기가 필요할 수 있다.

<br>

### Strategy Pattern (Provider Pattern)

```go
type IOrganizationProvider interface {
    GetProviderType() string
    Authenticate(token string) (*OrganizationInfo, error)
}
```

각 Provider가 동일한 인터페이스를 구현하고, Middleware는 인터페이스에만 의존한다. 런타임에 요청 헤더(`X-Provider-Type`)에 따라 적절한 인증 전략(Provider)을 선택하여 실행한다. 새로운 Provider 추가 시 기존 코드 수정 없이 확장 가능하다.

<br>

결국 Strategy Pattern의 변형인 **Provider Pattern**을 선택했다. Go 생태계에서도 database/sql의 Driver 등록, cloud SDK의 Provider 패턴 등 익숙한 방식이다.

<br>

## 스키마 설계

### Organization 테이블

조직을 별도 테이블로 분리하고, `(provider_type, provider_id)` 조합을 고유키로 설정했다.

```sql
CREATE TYPE auth_provider_enum AS ENUM ('external');

CREATE TABLE organization (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_type auth_provider_enum NOT NULL,
    provider_id varchar NOT NULL,
    name varchar,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT organization_provider_unique UNIQUE (provider_type, provider_id)
);
```

<br>

고유 제약 조건이 핵심이다.

```sql
CONSTRAINT organization_provider_unique UNIQUE (provider_type, provider_id)
```

위의 조건 덕분에 `(external, 123)`과 `(new_cloud, 123)`은 서로 다른 조직이다. 나중에 자체 조직이 생겨도 `(internal, 123)`으로 구분할 수 있다.

<br>

### PostgreSQL ENUM 사용 이유

`provider_type`은 VARCHAR 대신 PostgreSQL ENUM으로 정의했다. 아래와 같은 이유에서였다.

- **데이터 무결성**: DB 레벨에서 잘못된 값 차단
- **명시적 제약**: 허용된 Provider Type만 저장 가능
- **배포 프로세스 명시화**: 새 Provider 추가 시 DB 마이그레이션을 먼저 실행하도록 강제

<br>

물론 트레이드오프도 있다.

- 새 Provider 추가 시 DB 마이그레이션 필요
- 코드 배포 전에 DB 스키마 변경 필수
- PostgreSQL 12 미만에서는 ENUM 값 추가를 되돌릴 수 없음

확장성 제약이 있지만, 데이터 무결성을 우선했다. 어차피 새 인증 시스템 추가는 흔한 일이 아니고, 명시적인 마이그레이션 프로세스가 오히려 안전하다고 판단했다.

<br>

### 기존 테이블 변경

기존 리소스 테이블의 정수형 `organization_id` 컬럼은 유지하되, UUID 기반의 `new_organization_id` 컬럼을 추가했다.

| 컬럼 | 타입 | 용도 |
|------|------|------|
| `organization_id` | INTEGER | 하위 호환성 (deprecated) |
| `new_organization_id` | UUID | 새 스키마, Organization 테이블 FK |

하위 호환성을 위해 기존 컬럼은 남겨두고, 새 컬럼으로 점진적으로 전환하는 전략이다.

<br>

# 구현

## Provider 인터페이스

모든 Organization Provider가 구현해야 하는 인터페이스를 정의했다.

```go
// organization_provider.go

type OrganizationInfo struct {
    ProviderType string  // e.g., "external"
    ProviderId   string  // provider-specific ID
    Name         *string
}

type IOrganizationProvider interface {
    GetProviderType() string
    Authenticate(token string) (*OrganizationInfo, error)
}
```

<br>

공통 에러 타입도 정의했다.

```go
var (
    ErrProviderUnauthorized = errors.New("provider: unauthorized")
    ErrProviderAuthFailed   = errors.New("provider: authentication failed")
    ErrProviderNotFound     = errors.New("provider: not found")
)
```

Provider 구현체는 이 에러들을 반환하고, Middleware가 적절한 HTTP 상태 코드로 변환한다.

<br>

## External Provider 구현

기존 외부 플랫폼 연동을 Provider로 감쌌다.

```go
// external_provider.go

type IExternalClient interface {
    GetOrganization(token string) (*GetOrganizationResponse, error)
}

type ExternalOrganizationProvider struct {
    client IExternalClient
}

func NewExternalOrganizationProvider(client IExternalClient) *ExternalOrganizationProvider {
    return &ExternalOrganizationProvider{client: client}
}

func (p *ExternalOrganizationProvider) GetProviderType() string {
    return "external"
}

func (p *ExternalOrganizationProvider) Authenticate(token string) (*OrganizationInfo, error) {
    resp, err := p.client.GetOrganization(token)
    switch {
    case err == ErrUnauthorized:
        return nil, ErrProviderUnauthorized
    case err != nil:
        return nil, ErrProviderAuthFailed
    }

    if resp == nil || resp.Organization.Id <= 0 {
        return nil, ErrProviderAuthFailed
    }

    name := resp.Organization.Name
    return &OrganizationInfo{
        ProviderType: "external",
        ProviderId:   strconv.Itoa(resp.Organization.Id),
        Name:         &name,
    }, nil
}
```

핵심은 `ProviderId`를 문자열로 변환하는 부분이다. 외부 플랫폼의 `Organization.Id`는 정수지만, 다른 시스템에서는 UUID나 다른 형식일 수 있다. 문자열로 통일해서 유연성을 확보했다.

<br>

## Middleware 리팩토링

### Provider Registry

Middleware에 Provider를 등록하는 구조로 변경했다.

```go
// Provider Registry 구조
// - organizationProviders: 등록된 Provider들을 타입별로 관리
// - defaultOrganizationProviderType: X-Provider-Type 헤더가 없을 때 사용할 Provider
type Middleware struct {
    jwtHandler                      IJWTHandler
    SystemAuthenticator             ISystemAuthenticator
    organizationRepository          IOrganizationRepository
    organizationProviders           map[string]IOrganizationProvider
    defaultOrganizationProviderType string
}
```

<br>

Functional Options 패턴으로 유연한 초기화를 지원한다.

```go
func WithOrganizationProvider(provider IOrganizationProvider) MiddlewareOption {
    return func(m *Middleware) {
        if m.organizationProviders == nil {
            m.organizationProviders = make(map[string]IOrganizationProvider)
        }
        m.organizationProviders[provider.GetProviderType()] = provider
        
        // 첫 번째 Provider를 기본값으로 설정
        if m.defaultOrganizationProviderType == "" {
            m.defaultOrganizationProviderType = provider.GetProviderType()
        }
    }
}

func WithDefaultOrganizationProvider(providerType string) MiddlewareOption {
    return func(m *Middleware) {
        m.defaultOrganizationProviderType = providerType
    }
}
```

<br>

Server 초기화 시 이렇게 사용한다.

```go
authMiddleware, err := auth.New(
    SystemAuthenticator,
    jwtHandler,
    auth.WithOrganizationProvider(externalProvider),
    auth.WithDefaultOrganizationProvider("external"), // 외부 플랫폼을 기본 provider로 설정
    auth.WithOrganizationRepository(repository),
)
```

<br>

### 인증 흐름

`X-Provider-Type` 헤더로 인증 방식을 구분한다.

```
[Client Request]
      |
      v
[X-Provider-Type Header]
      |
      +-- "external" --> ExternalProvider.Authenticate()
      |                      |
      +-- "System" -------> JWT Validation
      |                      |
      +-- (empty) --------> Auto-detect
                             |
                    [Organization Auto-Registration]
                             |
                    [Context Setting & Next()]
```

```go
func (m *Middleware) RequireAuth() gin.HandlerFunc {
    return func(c *gin.Context) {
        providerType := c.GetHeader("X-Provider-Type")
        token, err := m.parseAndValidateAuthorizationHeader(c)
        if err != nil {
            c.AbortWithStatusJSON(401, gin.H{"message": "invalid authorization header"})
            return
        }

        switch providerType {
        case "external":
            providerType := m.mapAuthTypeToProviderType("external")
            m.handleOrganizationAuth(c, token, providerType)
        case "System":
            m.handleSystemAuth(c, token)
        default:
            // 하위 호환성: 헤더 없으면 토큰 형식으로 자동 감지
            if isJWTToken(token) {
                m.handleSystemAuth(c, token)
            } else {
                m.handleOrganizationAuth(c, token, m.defaultOrganizationProviderType)
            }
        }
    }
}
```

<br>

### Organization 자동 등록

Provider 인증 성공 시 Organization를 로컬 DB에 자동 등록한다.

```go
func (m *Middleware) handleOrganizationAuth(c *gin.Context, token string, providerType string) {
    provider, exists := m.organizationProviders[providerType]
    if !exists {
        c.AbortWithStatusJSON(400, gin.H{
            "message": fmt.Sprintf("provider not configured: %s", providerType),
        })
        return
    }

    // Provider를 통해 외부 시스템에서 조직 정보 조회
    orgInfo, err := provider.Authenticate(token)
    // ... 에러 처리 ...

    // Organization 자동 등록 (Best-Effort)
    // 등록 실패해도 인증은 성공 처리 - 외부 인증은 이미 성공했으므로
    var organizationUUID string
    if m.organizationRepository != nil {
        uuid, err := m.ensureOrganizationRegistered(organizationInfo)
        if err != nil {
            c.Set("organization_registration_error", err.Error())
        } else {
            organizationUUID = uuid
        }
    }

    // Context에 조직 정보 설정
    c.Set("organization_token", token)
    c.Set("new_organization_id", organizationUUID)
    
    // 하위 호환성: 기존 코드가 organization_id(정수)를 사용하는 경우 대비
    if legacyId, err := strconv.Atoi(orgInfo.ProviderId); err == nil && legacyId > 0 {
        c.Set("organization_id", legacyId)
    }
    c.Next()
}
```

Organization 등록 실패 시, **Best-Effort 전략**을 선택한 이유가 있다. 외부 Provider 인증은 성공했는데, 로컬 DB 문제로 인증을 거부하는 건 부적절하다. 가용성을 우선하고, 등록 실패는 로그로 추적하는 것이 낫다고 판단했다.

<br>

### 성능 최적화 고려 사항

다만, 매 인증 요청마다 Upsert가 실행된다는 것은 반드시 고려해야 할 사항이다. `ON CONFLICT` 절로 중복을 방지하기는 하지만, 어찌 됐든 DB 쿼리가 발생한다. 아래와 같은 방안을 고려해 볼 수 있다:

1. **인덱싱 전략**
   - `(provider_type, provider_id)` UNIQUE 제약이 곧 인덱스
   - 조회 성능 최적화를 위한 추가 인덱스 검토

2. **캐싱 도입**: 캐싱 등록 여부 확인 후 DB Upsert

3. **비동기 등록**
    - 인증은 즉시 성공 처리
    - Organization 등록은 백그라운드 Job으로

현재는 트래픽이 크지 않아 단순하게 유지했지만, 향후 필요시 위 방안들을 검토할 예정이다.


<br>

## Repository 구현

Upsert 패턴으로 조직을 등록/업데이트한다.

```go
func (r *Repository) UpsertOrganization(organization *entity.Organization) (string, error) {
    ctx, cancel := r.getContext()
    defer cancel()

    q := `
        INSERT INTO organization 
            (provider_type, provider_id, name)
        VALUES 
            ($1::auth_provider_enum, $2, $3)
        ON CONFLICT (provider_type, provider_id)
        DO UPDATE SET
            name = COALESCE(EXCLUDED.name, organization.name),
            updated_at = CURRENT_TIMESTAMP
        RETURNING id;
    `

    var id string
    if err := r.db.QueryRowContext(ctx, q,
        organization.ProviderType,
        organization.ProviderId,
        organization.Name,
    ).Scan(&id); err != nil {
        return "", err
    }

    return id, nil
}
```

`ON CONFLICT` 절이 핵심이다. `(provider_type, provider_id)` 조합이 이미 존재하면 이름만 업데이트하고, 없으면 새로 생성한다. 매번 인증할 때마다 조직 정보가 동기화된다.

<br>

# 마이그레이션

## 기존 데이터 이관

기존 스키마에서 새 스키마로 이관하는 전략을 수립했다.

| 단계 | 작업 | 설명 |
|------|------|------|
| 1 | Organization 테이블 생성 | `(provider_type, provider_id)` 복합 유니크 키 |
| 2 | 기존 ID 수집 | 리소스 테이블에서 DISTINCT한 기존 조직 ID 추출 |
| 3 | Organization 레코드 생성 | 기존 ID를 `provider_id`로, 기본 provider를 `provider_type`으로 설정 |
| 4 | FK 업데이트 | 리소스 테이블의 `new_organization_id`를 새 Organization 레코드로 연결 |
| 5 | 검증 | 이관 전후 레코드 수 일치 확인 |

핵심은 **기존 정수형 ID를 문자열로 변환**하여 `provider_id`에 저장하는 것이다. 이렇게 하면 기존 데이터와의 매핑을 유지하면서도 새로운 스키마로 전환할 수 있다.

<br>

## 하위 호환성

기존 정수형 컬럼은 삭제하지 않고 deprecated로 표시했다. 모든 시스템이 `new_organization_id`를 사용하도록 전환된 후에 삭제할 예정이다.

<br>

# 확장 예시

새로운 Organization Provider를 추가하는 과정을 정리했다. 예를 들어 `NewCloud`를 추가한다면:

## 1. DB ENUM 추가

```sql
ALTER TYPE auth_provider_enum ADD VALUE 'new_cloud';
```

## 2. Provider 구현

```go
type NewCloudOrganizationProvider struct {
    client INewCloudClient
}

func (p *NewCloudOrganizationProvider) GetProviderType() string {
    return "new_cloud"
}

func (p *NewCloudOrganizationProvider) Authenticate(token string) (*OrganizationInfo, error) {
    // NewCloud 토큰 검증 로직
    resp, err := p.client.IntrospectToken(token)
    // ...
    return &OrganizationInfo{
        ProviderType: "new_cloud",
        ProviderId:   resp.OrganizationId,
        Name:         &resp.OrganizationName,
    }, nil
}
```

## 3. Entity 상수 추가

```go
const (
    OrganizationProviderExternal = "external"
    OrganizationProviderNewCloud = "new_cloud"
)
```

## 4. Server에 Provider 등록

```go
authMiddleware, err := auth.New(
    SystemAuthenticator,
    jwtHandler,
    auth.WithOrganizationProvider(externalProvider),
    auth.WithOrganizationProvider(newCloudProvider), // 추가
    auth.WithDefaultOrganizationProvider("external"),
)
```

기존 코드 수정 없이 새 Provider를 추가할 수 있다. Open/Closed 원칙을 지킨 설계다.

<br>

# 결과와 회고

## 달라진 점

| 구분 | Before | After |
|------|--------|-------|
| 조직 식별 | `organization_id` (INTEGER) | `(provider_type, provider_id)` |
| 인증 확장 | 코드 수정 필요 | Provider 추가만으로 확장 |
| 다중 시스템 지원 | 불가 | 가능 |
| 데이터 무결성 | 애플리케이션 레벨 | DB ENUM 제약 |

<br>

## 트레이드오프

모든 설계에는 트레이드오프가 있다.

- **ENUM vs VARCHAR**: ENUM을 선택해서 데이터 무결성은 얻었지만, 새 Provider 추가 시 DB 마이그레이션이 필수다. 빠른 확장보다 안정성을 우선한 결정이다.
- **Best-Effort vs Strict**: Organization 등록 실패 시에도 인증을 성공 처리한다. 가용성을 우선한 결정이지만, 등록 실패가 누적되면 데이터 정합성 문제가 생길 수 있다. 모니터링으로 보완해야 한다.
- **하위 호환성 유지**: `organization_id` 컬럼을 당장 삭제하지 않았다. 점진적 전환을 위한 결정이지만, 당분간 두 가지 컬럼을 관리해야 하는 부담이 있다.

<br>

## 얻은 것

지금 당장 다른 인증 시스템을 추가할 계획은 없다. 그래서 굳이 이렇게까지 복잡하게 할 이유가 없어 보일 수도 있다. 

하지만 나중에 그런 필요가 생겼을 때, 이 설계 덕분에 훨씬 수월하게 대응할 수 있을 것이다. "미래의 우리 시스템"을 위한 투자라고 생각한다.

- **확장 가능한 구조**: 새 인증 시스템 추가 시 기존 코드 수정 불필요
- **명확한 식별**: `(provider_type, provider_id)` 조합으로 조직을 유일하게 식별
- **테스트 용이성**: Provider 인터페이스 기반으로 Mock 주입 가능
- **문서화**: Provider 추가 가이드, 아키텍처 문서 정리

<br>

## 남은 고민: 조직이 없는 사용자

이번 설계에서 한 가지 더 고민해볼 부분이 있다. 모든 연동 시스템이 조직 개념을 갖고 있는 것은 아니다. 예를 들어 NewCloud와 연동하는데, 해당 시스템에서 조직 없이 개인 사용자로만 존재하는 경우가 있을 수 있다.

현재 설계는 Provider가 반드시 `OrganizationInfo`를 반환하는 구조다. 조직이 없는 사용자를 지원하려면 몇 가지 방안이 있다.

<br>

### 방안 1: 사용자를 가상 조직으로 처리

사용자 자체를 하나의 조직으로 처리할 수도 있다. 예컨대 `provider_id`에 prefix를 붙여 개인/조직을 구분한다. 기존 설계 변경 없이 Provider 구현 레벨에서 처리할 수 있다.

```go
// 조직이 없는 경우, 사용자 자체를 조직 단위로 취급
if userInfo.OrganizationId == "" {
    return &OrganizationInfo{
        ProviderType: "new_cloud",
        ProviderId:   fmt.Sprintf("user:%s", userInfo.Id),
        Name:         &userInfo.Name,
    }, nil
}
```

이 방식은 리눅스의 User Private Group(UPG) 정책과도 유사하다. 리눅스에서는 새로운 사용자를 생성할 때, 시스템은 해당 사용자의 이름과 동일한 이름을 가진 전용 그룹을 자동으로 생성하고, 그 사용자를 해당 그룹의 유일한 멤버로 포함시킨다. 우리 시스템에서도 개인 사용자를 1인 조직으로 추상화하는 것을 고려해 볼 수 있다.

<br>

**나아가 이 패턴을 확장하면:**

Standalone User도 처음부터 가상 조직으로 취급할 수도 있다.
- 리소스는 항상 `new_organization_id`만 참조
- User가 팀에 합류하면 조직 이관만 하면 됨


이렇게 "Virtual Organization" 개념을 도입하면 User-Organization 관계를 더 유연하게 관리하면서도 접근 제어 로직을 일원화할 수 있다. 하지만 현재 시스템에서는:
- Standalone user와 Organization user가 섞일 가능성이 낮음
- 개념적 복잡도 증가
- user마다 organization 레코드 생성 오버헤드

이런 이유로 당장은 채택하지 않았다. 다만, 향후 시스템 내부에 실제로 조직 기능이 추가되거나 Standalone user들의 협업이 필요해지면 검토할 예정이다.

<br>

### 방안 2: 플래그 추가

기존 구조를 유지하면서 개인/조직을 명시적으로 구분할 수 있다.

```go
type OrganizationInfo struct {
    ProviderType string
    ProviderId   string
    Name         *string
    IsPersonal   bool  // true면 개인 사용자 (가상 조직)
}
```


<br>

방안 1이나 2 모두 기존 설계를 크게 변경하지 않으면서 문제를 해결할 수 있다. Provider 인터페이스 자체를 변경하는 방법도 있지만, 그러면 기존 구현체들을 전부 수정해야 하니 현실적으로는 위 방안들이 더 나아 보인다. 이 부분은 실제로 그런 요구사항이 생겼을 때 다시 고민해볼 예정이다.

<br>
