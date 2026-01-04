---
title:  "[Go] go-github SDK 패턴을 적용한 리팩토링 - 2. 적용"
excerpt: go-github SDK 패턴을 Internal API Client에 실제로 적용해 보자.
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


회사에서 Internal API Client를 리팩토링하면서 go-github SDK의 구조적 패턴을 적용해 보았다. 해당 패턴이 무엇인지, 그리고 go-github에서 어떻게 구현되어 있는지 알아 보고, 어떻게 적용했는지 정리한다. [go-github SDK 패턴 이해하기](/dev/go-github-sdk-pattern-in-refactoring-1/)에 이어, 실제 프로젝트에 패턴을 적용한 경험을 다룬다.


<br>

# 실제 적용

내 상황에 어떻게 정리했는지 살펴 보자.

<br>

## 현재 상황 분석

공유 리소스가 있고, 도메인이 나뉘고, 메서드가 많아질 예정이라 이 패턴을 적용하기에 적합하다고 판단했다.


| 조건 | 현재 상황 | 패턴 적용 이유 |
| --- | --- | --- |
| **두 개의 다른 서버** | Argo Server + Workflow Server (FastAPI) | 서비스 분리 필요 |
| **공유 리소스** | httpClient, minioConfig, trainerConfig | 한 곳에서 관리 |
| **도메인이 다름** | Argo = 워크플로우 제어, Pipeline = 트리거 | 메서드 그룹화 |
| **기존 코드의 문제** | 한 Client에 10개+ 메서드가 뒤섞임 | 정리 필요 |

<br>

## 구현

### Client 정의

```go
type Client struct {
    // 설정
    config        Config
    trainerConfig TrainerConfig
    splitConfig   SplitConfig

    // HTTP 클라이언트
    httpClient Doer

    // 서비스들
    Argo     ArgoService
    Pipeline PipelineService
}

func New(cfg Config, opts ...ClientOption) (*Client, error) {
    if err := cfg.Validate(); err != nil {
        return nil, err
    }

    c := &Client{
        config:     cfg,
        httpClient: &http.Client{},
        splitConfig: SplitConfig{
            TrainRatio: 0.8,
            ValRatio:   0.2,
        },
    }

    for _, opt := range opts {
        opt(c)
    }

    // 서비스 초기화
    c.Argo = newArgoService(c)
    c.Pipeline = newPipelineService(c)

    return c, nil
}
```

<br>

### 내부 서비스: ArgoService

Argo Workflow 엔진 서버와 직접적으로 통신하는 서비스이다.

```go
type argoService struct {
    httpClient Doer
    serverURL  string
    namespace  string
}

func newArgoService(c *Client) *argoService {
    return &argoService{
        httpClient: c.httpClient,
        serverURL:  c.config.ArgoServerURL,
        namespace:  c.config.ArgoServerNamespace,
    }
}
```

<br>

### 내부 서비스: PipelineService

Argo Workflow CRD를 관리하고, Pipeline을 실제로 트리거링하는 Pipeline Server와 통신하는 서비스이다.

```go
type pipelineService struct {
    httpClient    Doer
    serverURL     string
    argoServerURL string
    minio         ObjectStorageConfig
    trainer       TrainerConfig
    split         SplitConfig
}

func newPipelineService(c *Client) *pipelineService {
    return &pipelineService{
        httpClient:    c.httpClient,
        serverURL:     c.config.WorkflowServerURL,
        argoServerURL: c.config.ArgoServerURL,
        minio:         c.config.Minio,
        trainer:       c.trainerConfig,
        split:         c.splitConfig,
    }
}
```

<br>

# go-github 방식과의 비교

## Client 참조 방식

현재 코드는 서비스가 2개뿐이고 로직이 단순해서, 서비스 초기화 시 Client에서 필요한 값만 복사하는 방식을 선택했다. 나중에 서비스가 늘어나면 go-github 방식으로 전환할 수도 있다.

<br>

### 현재 방식: 필요한 값만 복사


```go
func newArgoService(c *Client) *argoService {
    return &argoService{
        httpClient: c.httpClient,      // 필요한 값만 복사
        serverURL:  c.config.ArgoServerURL,
        namespace:  c.config.ArgoServerNamespace,
    }
}
```

<br>

### go-github 방식: Client 참조

서비스가 Client 전체를 참조하고, 필요할 때 Client의 필드에 접근한다. 설정이 런타임에 변경되어도 서비스에 반영된다.

```go
func newArgoService(c *Client) *argoService {
    return &argoService{
        client: c,  // Client 전체 참조
    }
}

func (s *argoService) GetStatus(...) {
    s.client.httpClient.Do(...)  // 필요할 때 접근
}
```

<br>

## 추가 개선: NewRequest/Do 패턴 적용

현재는 각 서비스에서 HTTP 요청을 직접 생성하고 실행하지만, 서비스가 늘어나면 go-github처럼 `NewRequest`/`Do` 패턴을 적용해 공통 로직을 Client에 집중시킬 수 있다.

```go
func (c *Client) NewRequest(method, path string, body interface{}) (*http.Request, error) {
    // URL 결정 로직: 경로에 따라 Base URL 선택
    var baseURL string
    if strings.HasPrefix(path, "/api/v1/workflows") {
        baseURL = c.config.ArgoServerURL
    } else {
        baseURL = c.config.WorkflowServerURL
    }

    u, err := url.Parse(baseURL + path)
    if err != nil {
        return nil, err
    }

    var buf io.ReadWriter
    if body != nil {
        buf = &bytes.Buffer{}
        if err := json.NewEncoder(buf).Encode(body); err != nil {
            return nil, err
        }
    }

    req, err := http.NewRequest(method, u.String(), buf)
    if err != nil {
        return nil, err
    }

    if body != nil {
        req.Header.Set("Content-Type", "application/json")
    }

    return req, nil
}

func (c *Client) Do(ctx context.Context, req *http.Request, v interface{}) error {
    req = req.WithContext(ctx)

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return err
    }
    defer resp.Body.Close()

    if resp.StatusCode >= 400 {
        return fmt.Errorf("API error: %d", resp.StatusCode)
    }

    if v != nil {
        return json.NewDecoder(resp.Body).Decode(v)
    }

    return nil
}
```

<br>

서비스에서는 Client의 공통 메서드를 호출하여 요청을 처리하면 될 것이다.

```go
func (s *argoService) GetWorkflow(ctx context.Context, name string) (*Workflow, error) {
    req, err := s.client.NewRequest("GET",
        fmt.Sprintf("/api/v1/workflows/%s/%s", s.client.config.ArgoServerNamespace, name),
        nil)
    if err != nil {
        return nil, err
    }

    wf := new(Workflow)
    err = s.client.Do(ctx, req, wf)
    return wf, err
}
```

<br>

# 정리

SDK-style Client 패턴의 특징을 정리하면 다음과 같다.

| 특징 | 설명 |
| --- | --- |
| **공유 리소스** | HTTP 클라이언트, 인증, base URL 등을 한 곳에서 관리 |
| **일관된 설정** | 모든 서비스가 동일한 설정 사용 |
| **네임스페이스** | `client.Users.Get()`, `client.Repos.List()` 처럼 깔끔한 API |
| **Lazy init 가능** | 필요할 때만 서비스 초기화 가능 |
| **공통 로직 재사용** | NewRequest/Do 패턴으로 중복 코드 제거 |

<br>

외부에 배포하는 SDK가 아니더라도, 내부 클라이언트에 이 패턴을 적용하면 코드 구조가 깔끔해지고 확장성도 좋아진다. 도메인별로 메서드가 분리되어 있어 유지보수도 쉬워진다.

<br>

