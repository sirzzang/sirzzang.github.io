---
title:  "[Go] 10일간의 리팩토링 여정: 스불재에서 Clean Architecture까지"
excerpt: "시간에 쫓겨 쌓아 올린 기술 부채를 청산하기 위한 10일간의 기록(feat. Cursor)"
categories:
  - Dev
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - Refactoring
  - Clean Architecture
  - Cursor
  - AI
toc: true
---

<br>

회사 Backend를 리팩토링한 경험을 정리한다. 혼자 백엔드를 담당하며 시간에 쫓겨 쌓아 온 기술 부채를 청산하고, AI 툴을 제대로 활용해 보는 실험을 함께 진행했다. 생산성 향상과 비용 폭발, 그리고 새로운 개발 방식을 배운 소중한 기록이다.

<br>

# 문제의 시작

## 스불재가 쌓이다

처음엔 작았다. Handler 파일 하나에 몇 개의 엔드포인트, Service 로직 몇 줄. 그런데 시간이 지나면서 이런 파일이 만들어졌다.

```go
// device.go
func (h *Handler) GetDeviceList(...) { /* 200줄 */ }
func (h *Handler) GetDeviceDetail(...) { /* 150줄 */ }
func (h *Handler) CreateDevice(...) { /* 180줄 */ }
func (h *Handler) UpdateDevice(...) { /* 120줄 */ }
func (h *Handler) DeleteDevice(...) { /* 90줄 */ }
func (h *Handler) DeployModel(...) { /* 300줄 */ }
// ... 더 많은 메서드들
// 총 1,938줄
```

<br>

야심차게 설계, 구현, 테스트까지 잘 짜겠다고 시작한 프로젝트였다. 그러나 혼자 백엔드를 담당하며 일정 관리를 제대로 하지 못했다. 개발이란 게 항상 일정한 속도로 진행되는 게 아니다 보니, 일감이 몰려올 때가 있다. 그러다 보면 그러지 말아야겠다고 다짐하면서도 같은 일이 반복된다. 기능 추가 요청이 들어오면? `일단 돌아가게만, 나중에 정리하지`. 테스트 코드는? `일단은 생략, 나중에 추가하지`. 구조 개선은? `일단은 생각만 해 놓고, 시간 나면 하자`.

비슷한 상황에 놓여 본 개발자라면 모두 알겠지만, **"나중에"는 오지 않는다**. ~~사실 비단 개발 뿐만이 아니라, 인생 대부분의 일이 그러하다. 해야 할 시기에, 잘해야 한다.~~ 그러다 보니, 스불재(*스스로 불러온 재앙*)가 눈덩이처럼 불어났다.

<br>

특히 현재 팀에 합류한 2024년 7월 이후로 약 1년 반의 시간 동안, 비즈니스 모델을 찾아가며 기능 추가와 형상 변경이 잦았다. 소위 말하는 *갈아 엎는* 수준의 변경도 종종 있었는데, 그렇게 만들어 놓은 코드를 전부 지우고 새로 시작해야 하는 상황이 되면, 기술 부채 점검은 커녕 비슷한 기능을 다시 동일한 방식으로 구현하고 있는 나 자신을 발견할 뿐이었다. 

<br>

## 유기농 개발자의 함정

웃프게도, 나는 회사에서 *유기농 개발자*라고 불렸다. AI를 쓰지 않고 모든 걸 손으로 짜는 개발자. 당시 나는 이런 생각을 하고 있었다.

- "AI가 짜준 코드를 받아 들이기만 해서는 배우는 게 없다"
- "내가 생각해서 구현해야 진짜 내 것이 된다"

<br>

일리 있는 고민이었지만, 결과적으로는 **생산성의 병목**이 되었다. 간단한 CRUD 기능 세트를 개발하는 데 하루가 걸렸다. 스키마 설계에 30분에서 1시간, Table SQL 작성에 30분, Domain Entity 정의와 Repository 메서드 나열에 1시간, 테스트 코드 작성에 2시간, 실제 구현에 2~3시간, 디버깅에 1시간. 총 7~8시간이 걸렸다. 상태 동기화, 3rd Party 의존성 등 복잡한 로직이 필요한 경우에는 기능 하나에 하루가 통째로 걸렸다.

<br>

일정이 급박해지면 테스트 코드를 스킵했고, 비슷한 기능은 기존 코드를 복붙한 후 도메인만 바꿨다. 당연히 버그가 양산되었다. 
복붙한 코드에서 도메인 이름 바꾸는 걸 빼먹고, 테스트 코드가 없어서 런타임에 발견하는 일이 반복되었다. 생각해서 구현해야 내 것이 된다고 했던 다짐과는 너무 모순적이게도, *생각 없이* 개발해 버린다. 

<br>

## 더 이상은 안 된다

언제까지 이대로 놔둘 수는 없었다. 반복되는 버그도 문제였지만, 무엇보다 자기 모순적으로 개발하는 과정에서 나 자신에 대한 회의감이 들었다. 
- "나는 항상 이런 식으로 개발할 건가?"
- "새로운 패턴이나 개선점을 찾아보려는 노력은?"
- "더 생산성을 올릴 방법은 없는가?

<br>

리팩토링을 결심했다.

<br>

# 리팩토링 전략

## 세 가지 목표

이번 리팩토링의 목표는 세 가지였다.
- **1. Clean Architecture 적용**: Handler → Service → Repository 계층을 명확히 분리한다. HTTP 요청 처리와 비즈니스 로직이 뒤섞인 Handler를 정리하고, 테스트 가능한 구조를 만든다.
- **2. 도메인별 분리**: 파일을 책임별로 쪼갠다. Device, Model, Event 등 도메인을 명확히 구분하고, 각 도메인 내에서도 역할별로 적절히 분리한다.
- **3. AI 툴 제대로 써보기**: 유기농 개발자를 벗어나 생산성 향상을 실험한다. 회사에서 지원받은 Cursor를 활용해서 기술 부채 청산과 새로운 개발 방식을 동시에 시도한다.

특히 세 번째가 중요했다. 혼자 백엔드를 담당하며 일정에 쫓기다 보니, "나중에 정리"가 습관이 되었다. 그러나, 시간이 없다는 것도 이제는 핑계다. 달라져야 한다. AI 툴을 제대로 활용해서 빠르게 리팩토링하고, 앞으로의 개발 방식도 바꿔보고 싶었다.

<br>

### 왜 이제야 Service 레이어인가

사실, Clean Architecture의 3계층 구조는 백엔드 개발의 기본이다. 하지만 Go 생태계는 조금 다르다. Gin이나 Echo 같은 주요 웹 프레임워크의 공식 예시를 보면, 대부분 handler에서 모든 걸 처리한다. Spring처럼 `@Controller` → `@Service` → `@Repository` 같은 명확한 계층 구조가 프레임워크 레벨에서 강제되지 않는다.

```go
// Go 프레임워크의 일반적인 예시
func getUser(c *gin.Context) {
    // handler에서 DB 조회부터 응답까지 전부
    user := db.Query(...)
    c.JSON(200, user)
}
```

<br>

처음 프로젝트를 시작할 때, 나는 Go 생태계의 일반적인 예시를 따랐다. Route → Handler → Repository로 간단하게 시작했다. 프로젝트가 작을 땐 이게 충분했다. Go 커뮤니티의 "simple first" 철학에도 부합했고, Uber Go Style Guide도 "필요할 때 추상화를 추가하라"고 말한다.

문제는 프로젝트가 커지면서 발생했다. Handler에 비즈니스 로직이 쌓이기 시작했고, 하나의 메서드가 200줄을 넘어갔다. 테스트를 작성하려면 HTTP 요청을 모킹해야 했고, 같은 로직을 다른 엔드포인트에서 재사용할 수 없었다. 이제는 Service 레이어가 필요한 시점이 된 것이다.
이번 리팩토링은 "처음부터 왜 3계층을 안 만들었냐"가 아니라, "프로젝트 규모에 맞춰 적절한 시점에 적절한 복잡도를 추가하는 과정"이라고 봐야 한다.

<br>

## 표준 패턴 확립

리팩토링이 끝나면 재사용 가능한 템플릿을 만들고 싶었다. 앞으로 비슷한 프로젝트를 시작할 때, 혹은 새 도메인을 추가할 때 바로 적용할 수 있는 표준 구조가 필요했다. 일관된 에러 처리, 계층 간 책임 분리, 테스트 가능한 설계가 포함된 템플릿 말이다.

<br>

# 10일간의 여정

## 아키텍처 재설계

기존 프로젝트는 이런 구조였다.

```
internal/app/server/
├── handler/
│   ├── device.go (1,938줄 - 모든 것이 여기에)
│   ├── event.go (998줄 - 모든 것이 여기에)
│   └── model.go (800줄 - 모든 것이 여기에)
│   ...
```

<br>

이걸 아래처럼 바꿨다.

```
internal/
├── app/server/
│   ├── handler/           # HTTP 요청/응답만
│   │   ├── base.go        # 공통 에러 처리
│   │   ├── device/
│   │   │   └── handler.go 
│   │   ├── model/
│   │   │   └── handler.go
│   │   └── ...
│   ├── service/           # 비즈니스 로직
│   │   ├── device/
│   │   │   ├── dependencies.go
│   │   │   ├── input.go
│   │   │   └── service.go
│   │   ├── model/
│   │   │   └── service.go
│   │   └── ...
│   └── routes/            # 라우트 분리
│       ├── device.go
│       ├── model.go
│       └── ...
├── infra/                 # 인프라 레이어
│   ├── db/postgres/
│   ├── cache/
│   └── external/
└── pkg/
    ├── entity/            # 도메인 엔티티
    └── domain/            # 도메인 에러
        ├── errors.go
        ├── device_errors.go
        └── ...
```

핵심은 계층을 명확히 분리하는 것이었다. 
- Handler는 HTTP 요청과 응답만 처리하고, 
- Service는 비즈니스 로직을 담당하고, 
- Repository는 데이터 접근만 한다.


<br>

## Cursor와 함께한 작업 방식

Cursor를 쓰기 시작하면서 작업 방식이 완전히 바뀌었다. 처음엔 조심스러웠다. 관점을 바꿔야겠다는 생각은 있었지만, AI가 짜준 코드를 그냥 받아들이면 내가 배우는 게 없을 것 같았다. 그래서 이렇게 접근했다.

<br>

### 1단계: 계획 수립

가장 먼저 Cursor에게 현재 코드의 문제점을 분석하고 리팩토링 계획을 세워달라고 요청했다.

```
Me: "device 로직을 리팩토링하고 싶어. 내가 생각할 땐 아래와 같은 문제가 있어.
    - device.go 파일 크기가 너무 비대함
    - Model 로직과 Event 로직도 섞여 있음
    - 핸들러에 비즈니스 로직이 직접 구현되어 있음
    어떻게 리팩토링하면 좋을까? 계획만 수립해 줄래?"

Cursor: "... 이렇게 분리하면 어떨까요?
    1. 파일 분리: handler/device/, service/device/
    2. 서비스 레이어 도입: Handler → Service → Repository
    3. 공통 유틸리티 추출: Poller를 제네릭으로
    ..."
```

Cursor가 제시한 계획을 검토하고, 디렉토리 구조 먼저 분리할지, 타입 정의부터 분리할지 같은 세부 사항을 함께 논의했다. 이 과정에서, 예컨대 `타입을 먼저 분리하면 나중에 다시 옮겨야 할 수 있으니, 디렉토리 구조를 먼저 잡는 게 좋다`와 같은 **실용적인 조언**을 받았다.

<br>

### 2단계: 패턴 학습

계획이 세워지면, 먼저 내가 직접 2-3개 메서드를 구현했다. Handler에서 Service로 로직을 옮기고, 도메인 에러를 정의하고, BaseHandler 패턴을 적용하는 등의 과정을 손으로 익혔다. 그러고 나서 Cursor에게 코드 리뷰를 요청했다.

```
Me: "이 Handler 코드를 리팩토링했는데, Clean Architecture 관점에서 봐줄래?"

Cursor: "좋은 시작입니다만, Service 레이어에 HTTP 관심사가 조금 남아있네요.
        c.Request.Context()를 Service에서 받지 말고 Handler에서 추출해서 전달하는 게 더 깔끔할 것 같습니다. ..."
```

이런 식으로 내가 먼저 시도하고, Cursor가 개선점을 제시했다. 덕분에 패턴을 제대로 이해할 수 있었다.

<br>

### 3단계: 반복 작업 위임

패턴이 확립되고 나니 비슷한 작업이 반복되었다. CRUD 기능들, 테스트 코드, 에러 처리 같은 것들. 이런 건 Cursor에게 맡겼다.

```
Me: "GetByID 메서드와 동일한 패턴으로 Update, Delete 메서드도 만들어줘.
     도메인 에러는 ModelNotFoundError, ModelUpdateFailedError 사용."

Cursor: [코드 생성]

Me: [코드 검토 후 필요한 부분만 수정]
```

생산성이 확실히 달라졌다. 기존에는 CRUD 하나 만드는 데 하루가 걸렸는데, 이제는 2-3시간이면 됐다.

<br>

### 4단계: 새로운 시도

Cursor 덕분에 혼자서는 시도하지 못했을 패턴도 도입할 수 있었다. 제너릭 프로그래밍이 대표적이다.

```
Me: "Device 배포 로직이 Model과 Event에서 중복되는데, 개선 방법을 제안해줘"

Cursor: ".. DeploymentHandler 내 폴링 로직을 제너릭으로 만들면..."

// 결과
type DeploymentHandler[T any] struct {
    repo Repository
    transform func(*entity.Model) T
}

func (h *DeploymentHandler[T]) Deploy(ctx context.Context, input DeployInput) error {
    // 공통 배포 로직
}
```

제너릭 프로그래밍은 이론적으로만 알던 내용이었는데, 실제 개발에 적용하는 게 어려웠다. Cursor가 실무에서 사용할 수 있는 패턴을 제안해준 덕분에 쉽게 적용할 수 있었다. Cursor와 대화하며 더 나은 설계를 찾을 수 있었던 대표적인 사례다.
<br>

## 핵심 패턴들

리팩토링 과정에서 확립한 패턴들이 있다.

<br>

### 1. Service Layer 패턴

```go
// Before: Handler에 모든 것이
func (h *Handler) CreateModel(c *gin.Context) {
    // 비즈니스 로직 200줄...
}

// After: 계층 분리
func (h *ModelHandler) CreateModel(c *gin.Context) {
    var req dto.CreateModelRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(400, gin.H{"error": err.Error()})
        return
    }
    
    model, err := h.modelService.Create(c.Request.Context(), service.CreateModelInput{
        Name: req.Name,
        Type: req.Type,
    })
    if err != nil {
        h.HandleDomainError(c, err)
        return
    }
    
    c.JSON(201, model)
}

// service/model/service.go
func (s *Service) Create(ctx context.Context, input CreateModelInput) (*entity.Model, error) {
    // 비즈니스 로직 - 이제 테스트 가능!
}
```

<br>

### 2. BaseHandler 패턴

공통 에러 처리를 BaseHandler에 구현하고, 각 도메인 Handler에 임베딩했다.

```go
type BaseHandler struct{}

func (b *BaseHandler) HandleDomainError(c *gin.Context, err error) {
    if domainErr, ok := err.(domain.DomainError); ok {
        c.AbortWithStatusJSON(domainErr.HTTPStatus(), gin.H{
            "message": domainErr.Error(),
        })
        return
    }
    c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
        "message": err.Error(),
    })
}

type ModelHandler struct {
    handler.BaseHandler
    modelService *model.Service
}
```

이제 Handler는 `HandleDomainError` 한 줄만 호출하면 된다.

<br>

### 3. 도메인 에러 패턴

도메인 에러 인터페이스를 정의하고, 각 에러 타입이 이를 구현하도록 했다.

```go
// pkg/domain/errors.go
type DomainError interface {
    error
    HTTPStatus() int
}

// pkg/domain/model_errors.go
type ModelNotFoundError struct {
    ModelID int
}

func (e ModelNotFoundError) Error() string {
    return fmt.Sprintf("model %d not found", e.ModelID)
}

func (e ModelNotFoundError) HTTPStatus() int {
    return http.StatusNotFound
}
```

Service에서 도메인 에러를 반환하면, BaseHandler가 자동으로 적절한 HTTP 상태 코드로 변환한다. 이제 Handler 구현을 전부 읽지 않아도, 도메인 단에서 어떤 에러에 어떤 상태 코드가 매핑되는지 명확해졌다.

<br>

## Device 도메인: 가장 큰 고비

1,938줄짜리 거대한 파일을 분리하는 작업이었다. HTTP 핸들링, 비즈니스 로직, DB 쿼리, 외부 API 호출, 배포 상태 폴링, 동기화 로직이 모두 뒤섞여 있었다. 처음엔 어디서부터 손을 대야 할지 막막했다.

Cursor와 함께 계획을 세웠다. 먼저 HTTP 처리와 비즈니스 로직을 분리하고, 그다음 비즈니스 로직을 책임별로 나누기로 했다. 결과는 이랬다.

```
handler/device/handler.go (568줄)        // HTTP만
service/device/service.go                // 비즈니스 로직
service/device/deployment.go             // 배포 로직
service/device/poller.go                 // 폴링 로직
```

여러 번 시행착오를 겪었다. 처음엔 Service가 2,000줄이 넘어서 다시 분리했고, 그다음엔 파일을 너무 잘게 쪼개서 오히려 복잡해졌다. 최종적으로는 책임별로 적절히 분리하는 지점을 찾았다.

<br>

## 생산성의 변화

Cursor 없이 혼자 작업했다면 얼마나 걸렸을까? 기존 내 작업 패턴에 빗대어 보면, Device 도메인만 1,938줄에 최고 난이도로 3일, Event 도메인이 2.5일, 그 외 CRUD 위주 도메인들과 인프라 이동, 문서화까지 합치면 16.5일 정도. 게다가 새로운 패턴을 학습해서 도입해야 했으니, 얼마 간의 시간이 더 추가되었을 것이다. 실제로는 10일 만에 끝났다. 생산성이 약 1.65배 향상된 셈이다.

작업 패턴을 보면 12월 4일과 5일에 폭발적인 작업량을 보였다. Model 도메인으로 패턴을 확립하고, Event와 Device로 확장하는 과정이었다. 9일에는 Tag 도메인들을 빠르게 처리했고, 10일과 11일에는 마무리 작업을 했다.

Cursor 통계를 보니 총 23,861줄의 코드를 AI가 생성했고, 이는 커밋된 코드의 69.1%였다. Agent 요청은 445건, Messages는 448건이었다. 처음 이 수치를 보고 당황했다. "내가 짠 코드가 30%밖에 안 된다고?" 하지만 곰곰이 생각해 보니, 이게 AI를 제대로 활용한 결과였다. 반복적인 패턴 코드는 AI에게 맡기고, 핵심 설계와 검증은 내가 했다. 결과적으로 더 빠르고 일관된 코드를 만들 수 있었다.

<br>

# AI 툴 활용의 명암

## 생산성 향상

Cursor가 실제로 도운 부분들을 정리하면 이렇다.

- **새로운 패턴 도입**: 제너릭 프로그래밍처럼 전에는 실무에서 사용해 본 적 없는 패턴을 시도할 수 있었다. Cursor와 대화하며 설계를 다듬고, 실제 코드로 구현하는 과정을 함께했다.
- **의존성 구조 진단**: "inference client를 어디에 둬야 할까?"라고 물으면, Cursor는 현재 구조의 문제점을 지적하고 Clean Architecture 관점에서 올바른 위치를 제안해 줬다. 내가 놓치기 쉬운 계층 간 의존성 문제를 잡아줬다.
- **테스트 코드 작성**: 기존에는 테스트 코드 작성에 시간이 너무 오래 걸려서 스킵하곤 했다. 이제는 내가 Service 로직을 구현하면, Cursor가 테스트 코드를 생성해 줬다. Mock 설정, Given-When-Then 패턴, edge case까지 커버했다. 덕분에 테스트 커버리지가 크게 향상되었다.

그 외에, 기존 코드가 수행하던 기능이 모두 마이그레이션되었는지, 문서화는 어떻게 해야 하는지 등에 대해서도 도움을 많이 받았다.

<br>

## 비용의 현실

12월 중순, Cursor 대시보드를 보고 정신이 번쩍 들었다. AI가 생성한 코드가 69.1%, Agent 요청 445건, Messages 448건. 회사에서 Cursor를 지원해 준 첫 달이었고, 나도 처음 써보는 거라 마구잡이로 사용했다.

간단한 질문도 Agent에게 물어봤고, 대부분의 Tab Completion도 수용했고, 마음에 들지 않는 경우 같은 요청도 여러 번 반복했고, 컨텍스트를 최소화하지 않았다. 그런데, 이 모든 툴 호출이 전부 다 비용이었다.

<br>

## 교훈: AI에게 맡길 것 vs 내가 할 것

AI와 함께 작업할 때, 작업의 성격 별로 수행 방식을 명확하게 구분할 필요가 있음을 깨달았다.

- **AI에게 맡길 것**: 반복적인 패턴 코드, 테스트 코드 생성, 보일러플레이트, 문서화 초안. 이런 건 Cursor가 더 빠르고 일관되게 처리한다.
- **내가 할 것**: 아키텍처 설계, 핵심 비즈니스 로직, 에러 처리 전략, 코드 리뷰 및 검증. 이건 여전히 내가 해야 한다. AI는 내 의도를 완벽히 이해할 수 없고, 비즈니스 컨텍스트를 모른다.

<br>

이제부터는 최적화 관점도 생각해 보려 한다. Agent는 정말 필요할 때만, Tab Completion은 신중하게, 컨텍스트는 최소화하고, 반복 작업에 집중한다. 생산성 향상은 분명하지만, 공짜가 아니다. 비용 대비 효과를 생각하며 써야 한다. 나아가 비용 최적화에 대한 방안도 공부해야 한다.

이전에는 "내 스스로가 짜야만, 진짜 개발이다"라고 생각했다. 지금은 달라졌다. "AI와 협업해서 짜도, 개발이다. 잘 쓰면 생산성이 향상된다"고 생각한다. 중요한 것은, "핵심은 무엇을 AI에게 맡기고, 무엇을 내가 할지 구분하는 것"이라고 믿는다.

<br>

# 결과와 회고

## 숫자로 보는 성과

10일간의 작업으로 가장 큰 Handler 파일이 1,938줄에서 694줄로 줄었다. 64%가 감소한 셈이다. Service 레이어를 신규 도입했고, 8개 도메인으로 명확하게 분리했다. 무엇보다 테스트가 어려웠던 구조에서 쉬운 구조로 바뀌었고, 제각각이던 에러 처리가 도메인 에러 패턴으로 일관되게 개선되었다.

총 130개 이상의 파일을 수정했고, 약 3,000줄을 추가하고 2,500줄을 삭제했다. 코드가 줄지는 않았지만, 구조 변경에 따른 자연스러운 결과다. 파일 수가 늘어났지만, 역할별로 재배치되고 구조화되었다고 보는 게 맞다.

<br>

## 얻은 것

### 표준 템플릿
가장 큰 성과는 재사용 가능한 템플릿을 만든 것이다. 일반적인 3-tier architecture를 기반으로 한 표준 구조를 확립했고, [github.com/sirzzang/go-backend-template](https://github.com/sirzzang/go-backend-template)에 정리했다. 앞으로 비슷한 프로젝트를 시작하거나 새 도메인을 추가할 때 바로 적용할 수 있다.
> 물론, 규모가 작은 프로젝트일 때 초기부터 이 템플릿을 사용할 필요는 없을 것이다. 이번의 경험을 통해 프로젝트의 규모를 가늠하고, 어떤 구조를 가져갈 것인지 알아서 잘 조절해야 함을 깨달았다.

### AI 활용법
AI 툴을 사용하는 법을 배웠다. 패턴 학습은 내가 직접 하고, 반복 작업은 AI에게 맡기고, 검증은 다시 내가 한다. 이 사이클을 익혔다.

### 테스트 문화
리팩토링 과정에서 테스트의 중요성을 절감했다. Service 레이어 단위 테스트, Handler 통합 테스트를 작성하면서, 앞으로는 새 기능 추가 시 테스트를 우선으로 하려고 한다.

### 개발자 경험(DX) 향상
누군가에게는 별 거 아닐 수도 있다. 하지만 나에게는 이번 리팩토링이 **개발자 경험을 크게 향상시킨 작업**이었다. 

기술 부채가 쌓이면 개발 효율이 떨어진다. 코드를 다루는 일이 번거로워지고, 새 기능 추가 시 고민이 많아진다. 이번 리팩토링으로 그런 번거로움을 줄였고, 개발 작업이 더 즐거워졌다. 스스로에게 더 나은 경험을 제공한 것만으로도 충분한 성과라고 생각한다.

<br>

## 앞으로

템플릿을 활용해서 새 프로젝트를 더 빠르게 시작하고, 지속적으로 개선할 것이다. Cursor는 비용 대비 효과를 고려해서 반복 작업에 집중하고, 핵심 로직은 여전히 직접 작성할 것이다. 테스트는 더 이상 "나중에"가 아니라 "지금" 작성한다.

리팩토링을 돌이켜 보면, 완벽한 선택은 아니었을 것이다. 더 나은 방법도 있었을 테고, 일부 도메인은 더 쪼갤 수도 있었고, 에러 처리를 더 세밀하게 할 수도 있었다. 하지만 당시 상황에서는 최선의 선택이었다. 10일 만에 130개 파일을 수정하고, 기존 기능은 모두 정상 동작하게 하고, 테스트 커버리지를 대폭 향상시키고, 향후 재사용 가능한 템플릿을 확립했다. 완벽하지 않아도 괜찮다. 중요한 건, 지속적으로 개선하려는 노력이다. 

<br>

앞으로도 더 나은 코드, 더 나은 구조를 향해 나아가겠다.

<br>

# 참고

## 관련 글

이번 리팩토링에서 적용한 패턴들에 대한 상세 설명:
- [Functional Options 패턴으로 생성자 리팩토링하기]({% post_url 2026-01-01-Dev-Go-Functional-Options-Pattern-in-Refactoring %})
- [go-github SDK 패턴을 적용한 리팩토링 - 1. 패턴 이해]({% post_url 2026-01-02-Dev-Go-Github-SDK-Pattern-in-Refactoring-1 %})
- [go-github SDK 패턴을 적용한 리팩토링 - 2. 실무 적용]({% post_url 2026-01-02-Dev-Go-Github-SDK-Pattern-in-Refactoring-2 %})

## 템플릿

- [sirzzang/go-backend-template](https://github.com/sirzzang/go-backend-template): 이번 리팩토링으로 확립한 Go Backend 프로젝트 템플릿