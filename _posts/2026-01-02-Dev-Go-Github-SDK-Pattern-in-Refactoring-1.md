---
title:  "[Go] go-github SDK 패턴을 적용한 리팩토링 - 1. 패턴 이해"
excerpt: go-github SDK의 구조적 패턴을 분석하고 이해해 보자.
categories:
  - Dev
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - SDK
  - API Client
  - Design Pattern
  - Refactoring
toc: true
---

<br>

회사에서 Internal API Client를 리팩토링하면서 go-github SDK의 구조적 패턴을 적용해 보았다. 해당 패턴이 무엇인지, 그리고 go-github에서 어떻게 구현되어 있는지 알아 보고, 어떻게 적용했는지 정리한다.

<br>

# 배경

리팩토링 적용 대상은 Backend에서 Argo Workflow 제어를 위해 사용하는 Internal API Client였다. 기존 코드는 하나의 Client struct에 10개 이상의 메서드가 뒤섞여 있어, 도메인별 구분 없이 모든 기능이 한 곳에 몰려 있었다. 리팩토링이 필요했고, 표준적인 API Client 패턴을 따르고 싶어 찾아 보다, 표준 Go SDK 클라이언트의 구조적 패턴을 적용해 보기로 했다.

<br>

## SDK vs 현재 코드

내가 만든 건 엄밀히 말하면 SDK가 아니다. 정확한 표현은 **"SDK 스타일의 내부 인프라 클라이언트"**이다. SDK의 **구조적 패턴**을 차용했지만, SDK 자체는 아니다.


| 구분 | SDK | 현재 코드 |
| --- | --- | --- |
| **배포 대상** | 외부 개발자 (npm, go get) | 내부 프로젝트 전용 |
| **범용성** | 범용적, 모든 사용 사례 지원 | 특정 비즈니스 로직에 맞춤 |
| **문서화** | API 문서, 예제 코드 필수 | 팀 내부 공유 |
| **버전 관리** | SemVer, 하위 호환성 중요 | 내부 버전 관리 |

<br>

# SDK-style Client 패턴

## 핵심 개념

**하나의 루트 클라이언트가 공유 리소스를 관리하고, 도메인별 서비스들을 포함하여 일관된 API 접근을 제공하는 구조**이다.

```bash
# github client의 예
┌─────────────────────────────────────────┐
│                 Client                   │
│  ┌─────────────────────────────────┐    │
│  │ 공유 리소스                     │    │
│  │ - httpClient                    │    │
│  │ - config (URL, 인증, 설정)      │    │
│  └─────────────────────────────────┘    │
│                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │  Users   │  │  Repos   │  │ Issues │ │
│  │ Service  │  │ Service  │  │ Service│ │
│  └──────────┘  └──────────┘  └────────┘ │
└─────────────────────────────────────────┘
```

기본 구조는 다음과 같다.
1. **Client** = 공유 리소스 + 서비스 컨테이너
2. **Service** = 도메인별 API 메서드 그룹
3. Service 생성 시 Client의 리소스를 주입받음
4. 사용자는 `client.Service.Method()` 형태로 호출

<br>

## 패턴 유래

GoF 패턴처럼 학술적으로 정립된 것이 아니라, Go 커뮤니티에서 자연스럽게 형성된 관용적 구조다. 이 패턴을 명시적으로 정의한 공식 문서는 없으나, 많은 Go API Client가 이런 식으로 구현되어 있음을 확인할 수 있다.

- [google/go-github](https://github.com/google/go-github): 패턴의 원본
- [stripe/stripe-go](https://github.com/stripe/stripe-go): 유사한 구조
- [aws/aws-sdk-go](https://github.com/aws/aws-sdk-go): AWS SDK

<br>

Facade 패턴과 DI가 결합된 형태의 패턴이라고 볼 수 있다.

| 패턴 | 목적 | 차이점 |
| --- | --- | --- |
| **SDK-style Client** | API 클라이언트 구조화 | Service들이 Client 리소스 공유 |
| **Facade** | 복잡한 시스템 단순화 | 내부 구현 숨김에 집중 |
| **Dependency Injection** | 의존성 주입 | 외부에서 주입 받음 |

<br>

# go-github 구현 분석

SDK-style Client 패턴을 적용하기 위해 여러 Go API Client를 살펴봤다. 그 중에서도 [google/go-github](https://github.com/google/go-github/tree/master/github)을 분석 대상으로 선택한 이유는 다음과 같다.

- **패턴의 원본**: 이 패턴이 널리 알려진 계기가 된 대표적인 구현체
- **명확한 구조**: Client와 Service의 관계가 명확하게 드러남
- **활발한 유지보수**: Google에서 관리하며 지속적으로 업데이트됨
- **풍부한 예시**: 다양한 서비스(Users, Repositories, Issues 등)로 패턴 이해에 도움

이제 go-github의 구현을 분석해 보자.

<br>

## Client 정의

[github.go#L159](https://github.com/google/go-github/blob/master/github/github.go#L159)에서 Client가 정의되어 있다. 메인 API Client로 사용되는 구조체이다.

```go
type Client struct {
    client *http.Client
    BaseURL *url.URL

    // 핵심: 단일 service 인스턴스만 생성
    common service // Reuse a single struct instead of allocating one for each service on the heap.

    // 하위 서비스: 모든 서비스는 common을 재사용
    Users         *UsersService
    Repositories  *RepositoriesService
    Issues        *IssuesService
    // ... 
}
```

## service 구조체

[github.go#L238](https://github.com/google/go-github/blob/master/github/github.go#L238)에 service 구조체가 정의되어 있다.

```go
type service struct {
    client *Client
}
```

`common service`는 이 `service` 타입의 인스턴스다. 이 구조체는 단순히 `Client`에 대한 참조만 가지고 있으며, 모든 서비스(`ActionsService`, `ActivityService` 등)가 이 `service` 타입을 기반으로 정의된다.

이를 활용해 메모리 효율성을 크게 향상시킬 수 있는데, 그 원리는 Client 초기화 과정에서 드러난다.

<br>

## Client 초기화

### 일반적인 방식

각 서비스마다 별도의 struct를 힙에 할당한다고 해 보자.

```go
// 비효율적인 방식
func (c *Client) initialize() {
    c.Actions = &ActionsService{client: c}      // 할당 1
    c.Activity = &ActivityService{client: c}    // 할당 2
    c.Admin = &AdminService{client: c}          // 할당 3
    // ... 서비스 개수만큼 할당
}
```

- 구현은 직관적이나, 서비스마다 별도로 힙 영역에 메모리를 할당해야 한다.
- 특히, (서비스 개수) × (struct 크기)만큼 메모리를 할당해야 한다.

<br>

### 포인터 캐스팅 방식

반면, go-github 방식은 초기화 시 포인터 캐스팅을 활용해 `common` 구조체 하나만 할당하고 재사용한다. [github.go#L415](https://github.com/google/go-github/blob/master/github/github.go#L415)에 해당 부분이 구현되어 있다.

```go
// go-github: 효율적 방식
func (c *Client) initialize() {
    c.common.client = c  // Client 참조 설정

    // 포인터 캐스팅으로 같은 메모리 주소 재사용
    c.Actions = (*ActionsService)(&c.common)
    c.Activity = (*ActivityService)(&c.common)
    c.Admin = (*AdminService)(&c.common)
}
```

<br>

메모리 관점에서 보면, `common` 필드 하나만 할당하고 모든 서비스 포인터가 같은 주소를 가리킨다.

```
Client c (메모리 주소: 0x1000)
┌─────────────────────────────────────┐
│ common service (값 타입)            │
│ └─ client *Client → 0x1000 (순환)  │
│                                     │
│ Actions *ActionsService → &c.common│  // 0x1008 (같은 주소)
│ Activity *ActivityService → &c.common│  // 0x1008 (같은 주소)
│ Admin *AdminService → &c.common     │  // 0x1008 (같은 주소)
│ ...                                 │
└─────────────────────────────────────┘
```

> **참고**: `common`은 값 타입이므로 `Client` 구조체 내부에 직접 포함되어 있다. `Actions`, `Activity` 등은 모두 `&c.common`을 포인터 캐스팅한 것이므로 동일한 메모리 주소를 가리킨다.

<br>

## Service 정의

포인터 캐스팅이 어떻게 가능한 것일까? 이는 각 서비스들이 `service`의 **타입 정의(type definition)**로 선언되어 있기 때문이다.

실제 [users.go#L17](https://github.com/google/go-github/blob/master/github/users.go#L17)등에서 다음과 같은 구현 방식을 찾아볼 수 있다.

```go
// UsersService handles communication with the user related
// methods of the GitHub API.
type UsersService service
```

`ActionsService`, `ActivityService` 등은 모두 `service`와 동일한 메모리 레이아웃을 갖는다. Go에서는 동일한 메모리 레이아웃을 가진 타입 간에 포인터 캐스팅이 가능하다.

```go
// service = { client *Client }
// ActionsService = { client *Client }  // 구조가 완전히 같음

// 따라서 안전하게 캐스팅 가능
c.Actions = (*ActionsService)(&c.common)
```

<br> 
서비스의 메서드는 [users.go#L96-L115](https://github.com/google/go-github/blob/master/github/users.go#L96-L115)에서 살펴볼 수 있듯, `s.client`를 통해 Client의 공통 메서드(`NewRequest`, `Do`)에 접근한다.

```go
func (s *UsersService) Get(ctx context.Context, user string) (*User, *Response, error) {
    var u string
    if user != "" {
        u = fmt.Sprintf("users/%v", user)
    } else {
        u = "user"
    }

    // Client의 NewRequest 메서드 활용
    req, err := s.client.NewRequest("GET", u, nil)
    if err != nil {
        return nil, nil, err
    }

    uResp := new(User)
    // Client의 Do 메서드로 실행
    resp, err := s.client.Do(ctx, req, uResp)
    if err != nil {
        return nil, resp, err
    }

    return uResp, resp, nil
}
```

<br>

## NewRequest/Do 패턴

go-github에서는 공통 요청 생성/실행 로직을 Client에 구현한다. 모든 서비스가 이 메서드를 재사용하여 중복 코드를 제거한다.

<br>

### NewRequest

HTTP 요청을 생성하는 공통 메서드이다.[github.go#L544](https://github.com/google/go-github/blob/master/github/github.go#L544)에 구현되어 있으며, URL 파싱, Body 인코딩, 공통 헤더 설정을 담당한다.

```go
func (c *Client) NewRequest(method, urlStr string, body interface{}, opts ...RequestOption) (*http.Request, error) {
    // URL 파싱
    u, err := c.BaseURL.Parse(urlStr)
    ...
   
    // Body 인코딩
    var buf io.ReadWriter
    ...

    // Request 생성
    req, err := http.NewRequest(method, u.String(), buf)
    ...

    // 공통 헤더 설정
    ...
    req.Header.Set("Accept", mediaTypeV3)
    ...

    // functional options 기반 request 변경 
    for _, opt := range opts {
		opt(req)
	}

    return req, nil
}
```
> 심지어 여기에도 [Functional Options 패턴]({% post_url 2026-01-01-Dev-Go-Functional-Options-Pattern-in-Refactoring %})이 등장한다!

<br>

### Do

HTTP 요청을 실행하고 응답을 처리하는 공통 메서드이다. [github.go#1049](https://github.com/google/go-github/blob/master/github/github.go#L1049)에 정의되어 있다.

```go
func (c *Client) Do(ctx context.Context, req *http.Request, v any) (*Response, error) {
	resp, err := c.BareDo(ctx, req)
	if err != nil {
		return resp, err
	}
	defer resp.Body.Close()

	switch v := v.(type) {
	case nil:
	case io.Writer:
		_, err = io.Copy(v, resp.Body)
	default:
		decErr := json.NewDecoder(resp.Body).Decode(v)
		if decErr == io.EOF {
			decErr = nil // ignore EOF errors caused by empty response body
		}
		if decErr != nil {
			err = decErr
		}
	}
	return resp, err
}
```


<br>

## 사용 예시
해당 패턴 덕분에, 사용자 코드가 하위 서비스 네임스페이스 기준으로 접근할 수 있게 되며 깔끔해진다.

```go
// 사용자 코드
client, _ := github.NewClient(oauth2Client)

// 클라이언트 하위 서비스 네임스페이스로 접근
user, _ := client.Users.Get(ctx, "octocat")
repos, _ := client.Repositories.List(ctx, "octocat", nil)
issues, _ := client.Issues.ListByRepo(ctx, "owner", "repo", nil)
```

<br>

만약 이 패턴을 적용하지 않았더라면, 사용자 코드가 아래와 같이 지저분해졌을 수도 있다.
```go
// vs 네임스페이스 없이 (지저분함)
user, _ := client.GetUser(ctx, "octocat")
repos, _ := client.ListRepositories(ctx, "octocat", nil)
issues, _ := client.ListIssuesByRepo(ctx, "owner", "repo", nil)

```

<br>

