---
title:  "[Go] Virtual Organization 도입기 - 접근 제어 로직 일원화"
excerpt: "이원화된 로직을 하나의 추상화로 통합하기"
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

[이전 글](/dev/Dev-Go-Organization-Provider/)에서 Provider Pattern을 활용한 멀티 인증 시스템 설계를 다뤘다. 당시 "남은 고민" 섹션에서 Virtual Organization 개념을 언급했었는데, 결국 이를 도입하기로 결정했다.

이번 글에서는 Virtual Organization을 도입하게 된 배경과 구현 과정을 정리한다.

<br>

# 문제 재인식

## 접근 제어 로직의 이원화

이전 설계에서는 두 가지 사용자 타입을 다르게 처리했다.

- **Standalone User**: 시스템 자체 JWT 인증, `created_by` 컬럼으로 리소스 소유권 관리
- **Organization User**: 외부 플랫폼 토큰 인증, `organization_id` 컬럼으로 리소스 소유권 관리

이 방식은 접근 제어 로직이 이원화되는 문제가 있었다.

```sql
-- 복잡한 접근 제어 쿼리
SELECT * FROM model
WHERE (created_by = ? AND organization_id IS NULL)  -- standalone user의 리소스
   OR (organization_id = ? AND created_by IS NULL)  -- organization user의 리소스
   OR (is_global = TRUE)                            -- 전역 공유 리소스
```

<br>

이 설계에는 여러 문제가 있었다.

1. **쿼리 복잡도 증가**: 모든 리소스 조회 쿼리에서 `created_by`와 `organization_id`를 동시에 체크해야 했다. OR 조건이 늘어나면서 쿼리 최적화도 어려워졌다.
2. **NULL 처리의 복잡성**: `created_by`와 `organization_id` 중 하나만 값이 있어야 하는 배타적 관계를 DB 레벨에서 강제하기 어려웠다. 애플리케이션 레벨에서 검증 로직이 필요했다.
3. **코드 중복**: 접근 제어 로직이 여러 곳에 분산되어 있다. Handler, Service, Repository 각 레이어에서 "Standalone인가, Organization인가"를 분기해야 했다.
    ```go
    // Handler
    func (h *Handler) GetModels(c *gin.Context) {
        if isStandaloneUser(c) {
            // standalone 로직
        } else {
            // organization 로직
        }
    }

    // Repository
    func (r *Repository) GetModels(ctx context.Context, filter *ModelFilter) ([]*Model, error) {
        if filter.CreatedBy != nil {
            // standalone 쿼리
        } else if filter.OrganizationId != nil {
            // organization 쿼리
        }
    }
    ```

4. **확장성 부족**: Standalone User가 나중에 Organization에 합류하는 시나리오를 처리하기 어려웠다. `created_by`로 관리하던 리소스들을 어떻게 `organization_id`로 옮길 것인가?

<br>

## 인증 로직의 이원화

접근 제어뿐만 아니라 인증 로직도 이원화되어 있었다. 

기존 인증 흐름은 다음과 같다:

```
Standalone User  → JWT 검증 → User ID 추출 → 접근 제어
Organization User → External Token 검증 → Provider ID 추출 → Organization 조회 → 접근 제어
```

두 흐름이 별도로 존재하다 보니, 미들웨어 레벨에서 분기 처리가 필요했다.

```go
// 기존 인증 미들웨어
func AuthMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        authType := c.GetHeader("X-Provider-Type")
        
        if authType == "" {
            // Standalone User: JWT 인증
            token := extractBearerToken(c)
            claims, err := jwtHandler.VerifyToken(token)
            if err != nil {
                c.AbortWithStatus(http.StatusUnauthorized)
                return
            }
            c.Set("user_id", claims.Subject)
            c.Set("is_standalone", true)
        } else {
            // Organization User: Provider 인증
            provider := providerFactory.GetProvider(authType)
            orgInfo, err := provider.Authenticate(c)
            if err != nil {
                c.AbortWithStatus(http.StatusUnauthorized)
                return
            }
            c.Set("organization_id", orgInfo.OrganizationUUID)
            c.Set("is_standalone", false)
        }
        c.Next()
    }
}
```

<br>

이 구조에도 문제점이 있었다.

1. **미들웨어 복잡도**: 인증 타입에 따른 분기가 미들웨어에 하드코딩되어 있다.
2. **컨텍스트 불일치**: `user_id`와 `organization_id` 중 무엇이 설정되어 있는지 후속 핸들러에서 매번 확인해야 한다.
3. **확장성 제한**: 새로운 인증 방식 추가 시 미들웨어 분기 로직을 수정해야 한다.

Provider Pattern을 도입했음에도 Standalone User 인증이 별도로 존재했기 때문에 완전한 일원화가 이루어지지 않은 것이었다.

<br>

# 설계 결정: Virtual Organization

## 핵심 아이디어

> **모든 사용자는 Organization을 가진다.**

Standalone User에게도 개인 전용 "Virtual Organization"을 부여하면, 모든 리소스가 `organization_id` 하나로 관리될 수 있다. 아래와 같이 모든 사용자가 Organization을 갖도록 설계한다.
```
├─ Standalone User → Personal Virtual Organization (1인 조직)
│   ├─ provider_type: "internal"
│   └─ provider_id: user_id
└─ Organization User → Real Organization (실제 조직)
    ├─ provider_type: "external"
    └─ provider_id: external_org_id
```

<br>

## 기대 효과


**1. 통일된 접근 제어**

```sql
-- 단순한 쿼리
SELECT * FROM model
WHERE organization_id = ? OR is_global = TRUE
```

**2. NULL 제약 단순화**

`organization_id NOT NULL` 제약만 있으면 된다. 모든 리소스는 반드시 소유 조직이 있다.

**3. 코드 중복 제거**

```go
// 하나의 로직으로 모든 케이스 처리
func (r *Repository) GetModels(ctx context.Context, organizationId string) ([]*Model, error) {
    query := `SELECT * FROM model WHERE organization_id = $1 OR is_global = TRUE`
    // ...
}
```

**4. 확장성 확보**

User가 여러 Organization에 소속되는 시나리오도 자연스럽게 지원 가능하다.

**5. 인증 로직 일원화**

Standalone User도 Provider 기반 인증 흐름에 통합된다. 더 이상 미들웨어에서 "JWT인가, 외부 토큰인가"를 분기할 필요가 없다.

```go
// 통일된 인증 미들웨어
func AuthMiddleware(factory *ProviderFactory) gin.HandlerFunc {
    return func(c *gin.Context) {
        providerType := c.GetHeader("X-Provider-Type")
        provider := factory.GetProvider(providerType) // "internal" or "external"
        
        orgInfo, err := provider.Authenticate(c)
        if err != nil {
            c.AbortWithStatus(http.StatusUnauthorized)
            return
        }
        
        // 모든 인증이 동일한 결과 형태로 귀결
        c.Set("organization_id", orgInfo.OrganizationUUID)
        c.Next()
    }
}
```

모든 인증 타입이 `IOrganizationProvider.Authenticate()` → `OrganizationInfo` 흐름으로 통일되어, 후속 핸들러는 인증 방식에 관계없이 `organization_id`만 참조하면 된다.

<br>

# 구현

## 스키마 변경

### ENUM 타입 확장

기존 `auth_provider_enum`에 새로운 값을 추가했다.

```sql
ALTER TYPE auth_provider_enum ADD VALUE 'internal';
```

<br>

### Organization 테이블

이전 글에서 설계한 Organization 테이블을 그대로 활용한다.

```sql
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

Virtual Organization은 `provider_type = 'internal'`, `provider_id = '{user_id}'` 형태로 저장된다.

<br>

## Internal Provider 구현

Standalone User를 위한 새로운 Provider를 구현했다.

```go
// internal_provider.go

type IUserRepository interface {
    GetUserById(userId int) (*entity.User, error)
}

type IJWTHandler interface {
    VerifyToken(token string) (string, *TokenClaim, error)
}

// InternalOrganizationProvider는 시스템 자체 JWT 인증을 처리한다.
// Standalone User에게 Virtual Organization을 제공한다.
type InternalOrganizationProvider struct {
    userRepository IUserRepository
    jwtHandler     IJWTHandler
}

func NewInternalOrganizationProvider(
    userRepository IUserRepository,
    jwtHandler IJWTHandler,
) (*InternalOrganizationProvider, error) {
    if userRepository == nil {
        return nil, errors.New("user repository is required")
    }
    if jwtHandler == nil {
        return nil, errors.New("jwt handler is required")
    }

    return &InternalOrganizationProvider{
        userRepository: userRepository,
        jwtHandler:     jwtHandler,
    }, nil
}

func (p *InternalOrganizationProvider) GetProviderType() string {
    return "internal"
}

func (p *InternalOrganizationProvider) Authenticate(token string) (*OrganizationInfo, error) {
    // 1. JWT 토큰 검증
    _, claims, err := p.jwtHandler.VerifyToken(token)
    if err != nil {
        return nil, ErrProviderUnauthorized
    }

    // 2. 사용자 ID 추출
    userId, err := strconv.Atoi(claims.Subject)
    if err != nil || userId <= 0 {
        return nil, ErrProviderUnauthorized
    }

    // 3. 사용자 조회
    user, err := p.userRepository.GetUserById(userId)
    if err != nil {
        return nil, ErrProviderAuthFailed
    }
    if user == nil {
        return nil, ErrProviderUnauthorized
    }

    // 4. Virtual Organization 정보 반환
    // User는 이미 Virtual Organization UUID를 가지고 있음
    if user.OrganizationId == "" {
        return nil, ErrProviderAuthFailed
    }

    orgUUID := user.OrganizationId
    return &OrganizationInfo{
        ProviderType:     "internal",
        ProviderId:       strconv.Itoa(userId),
        OrganizationUUID: &orgUUID, // 이미 UUID가 있으므로 Upsert 불필요
    }, nil
}
```

핵심은 마지막 부분이다. External Provider와 달리, Internal Provider는 **Organization Upsert가 필요 없다**. User 생성 시점에 이미 Virtual Organization이 만들어져 있기 때문이다.

<br>

## 사용자 생성 시 Virtual Organization 자동 생성

User 생성 로직을 수정하여 Virtual Organization을 자동으로 생성하도록 했다.

```go
// repository/user.go

func (r *Repository) InsertUser(user *entity.User) (int, error) {
    ctx, cancel := r.getContext()
    defer cancel()

    // 트랜잭션 시작
    tx, err := r.db.BeginTx(ctx, nil)
    if err != nil {
        return 0, fmt.Errorf("failed to begin transaction: %w", err)
    }
    defer tx.Rollback()

    // 1. Virtual Organization 생성
    orgName := generateVirtualOrgName(user)
    orgQuery := `
        INSERT INTO organization 
            (provider_type, provider_id, name)
        VALUES 
            ($1::auth_provider_enum, $2, $3)
        RETURNING id;
    `

    var organizationId string
    // 임시 provider_id 사용 (user 생성 후 실제 ID로 업데이트)
    tempProviderId := fmt.Sprintf("temp_%d", time.Now().UnixNano())
    err = tx.QueryRowContext(ctx, orgQuery,
        "internal",
        tempProviderId,
        orgName,
    ).Scan(&organizationId)
    if err != nil {
        return 0, fmt.Errorf("failed to create virtual organization: %w", err)
    }

    // 2. User 생성 (organization_id 포함)
    userQuery := `
        INSERT INTO users 
            (username, password_hash, name, email, phone, organization_id)
        VALUES 
            ($1, $2, $3, $4, $5, $6)
        RETURNING id;
    `

    var userId int
    err = tx.QueryRowContext(ctx, userQuery,
        user.Username,
        user.PasswordHash,
        user.Name,
        user.Email,
        user.Phone,
        organizationId,
    ).Scan(&userId)
    if err != nil {
        return 0, fmt.Errorf("failed to create user: %w", err)
    }

    // 3. Organization provider_id를 실제 user_id로 업데이트
    updateOrgQuery := `
        UPDATE organization
        SET provider_id = $1
        WHERE id = $2;
    `
    _, err = tx.ExecContext(ctx, updateOrgQuery, 
        fmt.Sprintf("%d", userId), 
        organizationId,
    )
    if err != nil {
        return 0, fmt.Errorf("failed to update organization provider_id: %w", err)
    }

    // 트랜잭션 커밋
    if err := tx.Commit(); err != nil {
        return 0, fmt.Errorf("failed to commit transaction: %w", err)
    }

    return userId, nil
}

func generateVirtualOrgName(user *entity.User) string {
    if user.Name != nil && *user.Name != "" {
        return fmt.Sprintf("Personal Organization of %s", *user.Name)
    }
    if user.Email != nil && *user.Email != "" {
        return fmt.Sprintf("Personal Organization of %s", *user.Email)
    }
    return fmt.Sprintf("Personal Organization of %s", user.Username)
}
```

<br>

### 임시 provider_id의 사용

User ID는 `users` 테이블에 INSERT 후에야 알 수 있다. 하지만 Organization은 User보다 먼저 생성되어야 한다(User가 `organization_id`를 FK로 참조하므로).

해결책으로 **3단계 트랜잭션**을 사용했다.

1. 임시 `provider_id`로 Organization 생성
2. Organization UUID를 참조하여 User 생성
3. Organization의 `provider_id`를 실제 User ID로 업데이트

모두 하나의 트랜잭션 안에서 실행되므로 데이터 정합성이 보장된다.

<br>

## 인증 흐름 변경

Middleware의 인증 흐름을 수정했다.

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
            m.handleOrganizationAuth(c, token, "external")
        case "internal":
            m.handleOrganizationAuth(c, token, "internal")
        default:
            // 하위 호환성: 헤더 없으면 토큰 형식으로 자동 감지
            if isJWTToken(token) {
                m.handleOrganizationAuth(c, token, "internal")
            } else {
                m.handleOrganizationAuth(c, token, m.defaultOrganizationProviderType)
            }
        }
    }
}
```

핵심 변경점은 **Internal Provider도 `handleOrganizationAuth`를 사용**한다는 것이다. 이제 두 인증 방식 모두 동일한 코드 경로를 탄다.

<br>

## 기존 데이터 마이그레이션

기존 Standalone User들에게 Virtual Organization을 부여하는 마이그레이션을 작성했다.

```sql
-- 1. 기존 사용자별 Virtual Organization 생성
INSERT INTO organization (provider_type, provider_id, name)
SELECT 
    'internal'::auth_provider_enum,
    id::text,
    COALESCE(
        'Personal Organization of ' || name,
        'Personal Organization of ' || email,
        'Personal Organization of ' || username
    )
FROM users
WHERE organization_id IS NULL;

-- 2. 사용자에게 Virtual Organization 연결
UPDATE users u
SET organization_id = o.id
FROM organization o
WHERE o.provider_type = 'internal'
  AND o.provider_id = u.id::text
  AND u.organization_id IS NULL;

-- 3. 기존 리소스의 created_by를 organization_id로 변환
UPDATE model m
SET organization_id = u.organization_id
FROM users u
WHERE m.created_by = u.id
  AND m.organization_id IS NULL;

-- 4. created_by 컬럼 제거 (또는 deprecated 처리)
ALTER TABLE model DROP COLUMN created_by;
```

<br>

# Entity 설계

Organization 엔티티에 Virtual Organization 관련 메서드를 추가했다.

```go
// entity/organization.go

const (
    OrganizationProviderExternal = "external"
    OrganizationProviderInternal = "internal"
    // 시스템 조직 UUID (전역 리소스용)
    SystemOrganizationUUID = "00000000-0000-0000-0000-000000000000"
)

type Organization struct {
    Id           string
    ProviderType string
    ProviderId   string
    Name         *string
    CreatedAt    time.Time
    UpdatedAt    time.Time
}

// IsVirtualOrganization은 Virtual Organization(개인 workspace)인지 확인한다.
func (o *Organization) IsVirtualOrganization() bool {
    return o.ProviderType == OrganizationProviderInternal && 
           o.Id != SystemOrganizationUUID
}

// IsExternalProvider는 외부 Provider인지 확인한다.
func (o *Organization) IsExternalProvider() bool {
    return o.ProviderType != OrganizationProviderInternal
}

// IsSystemOrganization은 시스템 조직(전역 리소스용)인지 확인한다.
func (o *Organization) IsSystemOrganization() bool {
    return o.Id == SystemOrganizationUUID
}
```

<br>

# 결과

## 달라진 점

| 구분 | Before | After |
|------|--------|-------|
| 접근 제어 | `created_by` + `organization_id` 이원화 | `organization_id` 단일화 |
| 쿼리 복잡도 | OR 조건 다수 | 단순 조건 |
| NULL 처리 | 복잡한 배타적 관계 | NOT NULL 제약 |
| 코드 분기 | Standalone/Organization 분기 | 통일된 로직 |

<br>

## 쿼리 단순화 예시
```sql
-- Before
SELECT * FROM model
WHERE (created_by = ? AND organization_id IS NULL)
   OR (organization_id = ? AND created_by IS NULL)
   OR (is_global = TRUE);

-- After
SELECT * FROM model
WHERE organization_id = ? OR is_global = TRUE;
```

<br>

## 트레이드오프

역시나 지금 설계에도 트레이드오프가 있다.

- **오버헤드**: User당 Organization 레코드 1개가 추가된다. 다만, 지금 단계에서 User가 많이 생성될 것이라 보이지는 않기 때문에, 이는 무시할 수 있는 수준이라 본다.
- **개념적 복잡성**: "Virtual Organization"이라는 새로운 개념이 도입된다. 하지만 사용자에게는 "개인 공간"으로 추상화할 수 있다.
- **마이그레이션 비용**: 기존 데이터 구조를 변경해야 한다. ENUM 값 추가, 기존 User에게 Virtual Organization 부여, `created_by` 컬럼 데이터 마이그레이션 등이 필요하다.

<br>

## 향후 확장 가능성

Virtual Organization 도입으로 다음과 같은 시나리오를 지원할 수 있게 되었다.

**1. Multi-Organization Membership**

User가 여러 Organization에 소속될 수 있다.

```sql
CREATE TABLE user_organization (
    user_id int,
    organization_id uuid,
    role varchar,
    PRIMARY KEY (user_id, organization_id)
);
```

**2. Context Switching**

요청 시 현재 작업할 Organization을 선택할 수 있다.

예컨대, 아래와 같은 확장 헤더를 도입하여 지원할 수 있다.
```http
X-Organization-Context: internal:123     # 개인 공간
X-Organization-Context: external:company1  # 회사 공간
```

**3. Resource Sharing**

Organization 간 리소스를 공유할 수 있다.

```sql
CREATE TABLE model_share (
    model_id uuid,
    shared_with_organization_id uuid,
    permission varchar  -- 'read', 'write', 'admin'
);
```

지금 당장 이 기능들이 필요하지는 않다. 하지만 Virtual Organization을 도입함으로써 **미래 확장 가능성을 열어두었다**.

<br>

# 회고

이전 글에서 "남은 고민"으로 언급했던 Virtual Organization을 결국 도입하게 됐다. 당시에는 오버헤드와 개념적 복잡성 때문에 채택하지 않았는데, 실제로 코드를 작성하다 보니 접근 제어 로직 이원화의 문제가 생각보다 크게 다가왔다.

결과적으로 쿼리가 단순해지고, 코드 중복이 사라지고, 확장 가능성도 확보됐다. "1인 조직"이라는 개념이 처음에는 어색했지만, Linux의 User Private Group(UPG)과 비슷하다고 생각하면 자연스럽다.

> 모든 사용자에게 개인 전용 그룹을 부여하면, 권한 관리가 단순해진다.

<br>

