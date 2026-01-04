---
title:  "[Go] Functional Options 패턴으로 생성자 리팩토링하기"
excerpt: Rob Pike의 생각을 좇아, Functional Options 패턴을 적용해 유연하고 확장 가능한 생성자를 만들어 보자.
categories:
  - Dev
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - Design Pattern
  - Refactoring
  - Functional Options
toc: true
---

<br>

회사에서 Argo Workflow Client의 생성자를 리팩토링하면서 Functional Options 패턴을 적용해 보았다. 이 글에서는 해당 패턴이 무엇인지, 그리고 실제로 어떻게 적용했는지 정리한다.

<br>

# 패턴의 탄생

## Rob Pike의 문제의식

흥미롭게도 이 패턴을 제안한 사람은 Rob Pike다. 제안의 배경이 무척 흥미롭다. [Self-referential functions and the design of options](https://commandcenter.blogspot.com/2014/01/self-referential-functions-and-design.html)라는 글에서 그는 옵션 설정 문제로 오랫동안 고민했음을 밝히고 있다.

> The package is intricate and there will probably end up being dozens of options. There are many ways to do this kind of thing, but I wanted one that felt nice to use, didn't require too much API (or at least not too much for the user to absorb), and could grow as needed without bloat.

- 패키지가 복잡해서 결국 수십 개의 옵션이 필요하게 될 것 같았다.
- 이런 종류의 일을 처리하는 방법은 여러 가지가 있지만, 사용하기 좋고, API가 너무 많이 필요하지 않으면서(적어도 사용자가 흡수해야 할 양이 적으면서), 불필요한 비대화 없이 필요에 따라 확장될 수 있는 것을 원했다.

<br>

> I've tried most of the obvious ways: option structs, lots of methods, variant constructors, and more, and found them all unsatisfactory. After a bunch of trial versions over the past year or so, and a lot of conversations with other Gophers making suggestions, I've finally found one I like.

- 옵션 구조체, 많은 메서드, 여러 변형 생성자 등 분명해 보이는 방법들은 대부분 시도해 봤지만, 모두 만족스럽지 않았다.
- 지난 1년여간 여러 시행 버전을 거치고, 다른 Gopher들과 많은 대화를 나눈 끝에 마침내 마음에 드는 방법을 찾았다.

<br>

여기서 얼마나 많은 고민을 했을지 짐작해 볼 수 있다. Go의 아버지라고 불리는 분도 이렇게 고민하는구나 싶었다. 

<br>

## 왜 필요한가

Go에는 함수 오버로딩이 없다. 기본값이 있는 선택적 매개변수도 지원하지 않는다. 그렇다 보니 수많은 선택적 옵션을 처리하는 것이 쉽지 않다. Rob Pike도 같은 문제에 봉착했고, 이를 해결하기 위한 패턴을 고안했다.

<br>

## 기본 버전

Rob Pike가 제시한 첫 번째 버전은 단순하다. 

<br>

먼저 option 타입을 정의한다.

> First, we define an option type. It is a function that takes one argument, the Foo we are operating on.

```go
type option func(*Foo)
```

> The idea is that an option is implemented as a function we call to set the state of that option.

- option은 해당 옵션의 상태를 설정하기 위해 호출하는 함수로 구현된다.
- 다시 말해, **option 타입은 상태를 바꾸는 함수**다.

<br>

그 다음, option을 적용하는 메서드를 정의한다. option을 가변 인자로 받는다.

```go
// Option sets the options specified.
func (f *Foo) Option(opts ...option) {
    for _, opt := range opts {
        opt(f)
    }
}
```

- 가변 인자로 받으니까, 원하는 옵션을 몇 개든 적용할 수 있다.

<br>

마지막으로 실제 option 함수를 정의한다. verbosity라는 설정을 예로 들면:

```go
// Verbosity sets Foo's verbosity level to v.
func Verbosity(v int) option {
    return func(f *Foo) {
        f.verbosity = v
    }
}
```

- option 함수는 **클로저(closure)**를 반환한다.
- 클로저 안에서 필드를 설정한다.

<br>

여기서 **왜 클로저를 반환하는가?**에 대해 Rob Pike는 다음과 같이 설명한다.

> Why return a closure instead of just doing the setting? Because we don't want the user to have to write the closure and we want the Option method to be nice to use.

클로저를 반환하기 때문에, 사용하는 쪽에서 아래와 같이 깔끔하게 호출할 수 있다.

```go
foo.Option(pkg.Verbosity(3))
```

만약 클로저를 반환하지 않았다면, 사용자가 매번 아래처럼 작성해야 했을 것이다.

```go
foo.Option(func(f *Foo) { f.verbosity = 3 })
```

<br>

## 이전 값 반환 버전

Rob Pike는 여기서 멈추지 않고, 임시로 값을 변경했다가 복원해야 하는 상황을 위해 패턴을 발전시킨다.

> That's easy and probably good enough for most purposes, but for the package I'm writing, I want to be able to use the option mechanism to set temporary values, which means it would be nice if the Option method could return the previous state.

- 대부분의 경우에는 기본 버전으로 충분하지만, 임시 값을 설정하는 메커니즘으로 사용하고 싶었고, 그러려면 Option 메서드가 이전 상태를 반환할 수 있으면 좋겠다.

<br>

```go
type option func(*Foo) interface{}

// Verbosity sets Foo's verbosity level to v.
func Verbosity(v int) option {
    return func(f *Foo) interface{} {
        previous := f.verbosity
        f.verbosity = v
        return previous
    }
}

// Option sets the options specified.
// It returns the previous value of the last argument.
func (f *Foo) Option(opts ...option) (previous interface{}) {
    for _, opt := range opts {
        previous = opt(f)
    }
    return previous
}
```

- option 함수가 새로운 값을 설정한 뒤, 이전 값을 반환한다.
- Option 메서드는 마지막 option의 이전 값을 반환한다.

<br>

아래와 같이 사용하면 된다:

```go
prevVerbosity := foo.Option(pkg.Verbosity(3))
foo.DoSomeDebugging()
foo.Option(pkg.Verbosity(prevVerbosity.(int)))
```

- 그런데 복원할 때 type assertion(`prevVerbosity.(int)`)이 필요하다.
- 뭔가 좀 보기 싫다.

<br>

## Self-referential 버전

Rob Pike는 이 문제도 해결한다.

> The type assertion in the restoring call to Option is clumsy. We can do better if we push a little harder on our design.

- 복원할 때의 type assertion이 어색하다며, 설계를 조금 더 밀어붙이면 더 나아질 수 있다고 한다.

<br>

> First, redefine an option to be a function that sets a value and returns another option to restore the previous value.

```go
type option func(f *Foo) option
```

- option 타입이 자기 자신을 반환하도록 재정의한다.
- 값을 설정하고, **이전 값을 복원할 수 있는 또 다른 option을 반환**하는 함수다.

<br>

"Self-referential"은 **자기 자신을 참조한다**는 의미다. 여기서는 두 가지 측면에서 self-referential이다.

1. **타입 정의 자체가 self-referential**: `option` 타입이 자기 자신을 반환 타입으로 사용한다.
2. **구현에서 함수가 자기 자신을 사용**: 아래 코드에서 Verbosity 함수가 내부에서 다시 Verbosity를 호출하여 새로운 option을 생성한다.

<br>

최종 버전의 코드는 다음과 같다.

```go
// Option sets the options specified.
// It returns an option to restore the last arg's previous value.
func (f *Foo) Option(opts ...option) (previous option) {
    for _, opt := range opts {
        previous = opt(f)
    }
    return previous
}

// Verbosity sets Foo's verbosity level to v.
func Verbosity(v int) option {
    return func(f *Foo) option {
        previous := f.verbosity
        f.verbosity = v
        return Verbosity(previous)  // Verbosity를 다시 호출하여 undo용 option 생성
    }
}
```

> Instead of just returning the old value, it now calls the surrounding function (Verbosity) to create the undo closure, and returns that closure.

- 단순히 이전 값을 반환하는 대신, 감싸고 있는 함수(Verbosity)를 호출해서 undo 클로저를 만들고 그 클로저를 반환한다.

<br>

사용하는 쪽에서도 아주 깔끔해진다.

```go
prevVerbosity := foo.Option(pkg.Verbosity(3))
foo.DoSomeDebugging()
foo.Option(prevVerbosity)  // type assertion 불필요
```

거기다가 Go의 `defer`와 결합하면 더욱 우아해진다.

```go
func DoSomethingVerbosely(foo *Foo, verbosity int) {
    prev := foo.Option(pkg.Verbosity(verbosity))
    defer foo.Option(prev)
    // ... 높은 verbosity로 작업 수행
}
```

<br>

## Rob Pike의 제언

Rob Pike는 글을 마무리하며 이렇게 말한다.

> The implementation of all this may seem like overkill but it's actually just a few lines for each option, and has great generality. Most important, **it's really nice to use from the point of view of the package's client**. I'm finally happy with the design. **I'm also happy at the way this uses Go's closures to achieve its goals with grace.**

- 이 모든 구현이 과한 것처럼 보일 수 있지만, 실제로는 각 옵션당 몇 줄에 불과하고 일반성이 뛰어나다.
- 가장 중요한 것은, **패키지 사용자 관점에서 정말 사용하기 좋다**는 것이다.
- 마침내 설계에 만족한다. **Go의 클로저를 이용해 우아하게 목표를 달성하는 방식에도 만족**한다.

<br>

# 패턴의 특징

결과적으로 Functional Options 패턴은 **설정(configuration)을 함수(function)로 표현하고, 그 함수들을 가변 인자로 받아 객체의 상태를 변경하는 디자인 패턴**이다. 

조금 더 정확하게 정의하자면, 
- **설정을 일급 함수(first-class function)로 표현**하여,
- **선택적이고 확장 가능하며 타입 안전한 방식으로 객체를 구성하는 패턴**
이라고 할 수 있다.

<br>


## 1. 선택적(Optional)

필요한 옵션만 선택적으로 적용할 수 있다.

```go
foo.Option()                              // 옵션 없이
foo.Option(Verbosity(3))                  // 하나만
foo.Option(Verbosity(3), Timeout(30))     // 여러 개
```

## 2. 타입 안전(Type-safe)

컴파일 타임에 타입 체크가 된다.

```go
foo.Option(Verbosity(3))       
foo.Option(Verbosity("3"))     // 컴파일 에러
```

## 3. 확장 가능(Extensible)

새 옵션 추가 시 기존 코드를 수정하지 않아도 된다.

```go
// 새 옵션 추가
func NewOption(v Value) option {
    return func(f *Foo) {
        f.newField = v
    }
}
```


## 4. 자기 문서화(Self-documenting)

옵션 이름만 봐도 의미가 명확하다.

```go
foo.Option(
    Verbosity(3),
    Timeout(30 * time.Second),
    MaxRetries(5),
)
```

<br>

# 표준화

이 패턴은 Rob Pike가 2014년에 제안하고, Dave Cheney가 [Functional options for friendly APIs](https://dave.cheney.net/2014/10/17/functional-options-for-friendly-apis)라는 블로그 글에서 널리 알리면서 Go 커뮤니티에서 표준처럼 자리 잡게 되었다.

<br>

## Uber Style Guide

[Uber의 Go 스타일 가이드](https://github.com/uber-go/guide/blob/master/style.md#functional-options)에서도 Functional Options 패턴을 공식적으로 권장하고 있다.

> Functional options is a pattern in which you declare an opaque `Option` type that records information in some internal struct. You accept a variadic number of these options and act upon the full information recorded by the options on the internal struct.

- Functional options는 내부 구조체에 정보를 기록하는 불투명한(opaque) `Option` 타입을 선언하는 패턴이다.
- 이 옵션들을 가변 인자로 받아 내부 구조체에 기록된 전체 정보에 따라 동작한다.

<br>

> Use this pattern for optional arguments in constructors and other public APIs that you foresee needing to expand, especially if you already have three or more arguments on those functions.

- 생성자나 다른 공개 API에서 확장이 필요할 것으로 예상되는 선택적 인자에 이 패턴을 사용하라.
- 특히 함수에 이미 3개 이상의 인자가 있다면 사용을 고려하라.

<br>

Uber 가이드에서는 인터페이스 기반의 구현 방식을 권장한다.

```go
type options struct {
    cache  bool
    logger *zap.Logger
}

type Option interface {
    apply(*options)
}

type cacheOption bool

func (c cacheOption) apply(opts *options) {
    opts.cache = bool(c)
}

func WithCache(c bool) Option {
    return cacheOption(c)
}

type loggerOption struct {
    Log *zap.Logger
}

func (l loggerOption) apply(opts *options) {
    opts.logger = l.Log
}

func WithLogger(log *zap.Logger) Option {
    return loggerOption{Log: log}
}

// Open creates a connection.
func Open(addr string, opts ...Option) (*Connection, error) {
    options := options{
        cache:  defaultCache,
        logger: zap.NewNop(),
    }

    for _, o := range opts {
        o.apply(&options)
    }
    // ...
}
```

> Note that there's a method of implementing this pattern with closures but we believe that the pattern above provides more flexibility for authors and is easier to debug and test for users.

- 클로저로 이 패턴을 구현하는 방법도 있지만, 위의 패턴이 작성자에게 더 많은 유연성을 제공하고 사용자가 디버그하고 테스트하기 더 쉽다.
- 특히, 옵션들을 테스트와 mock에서 서로 비교할 수 있게 해주는데, 클로저로는 불가능하다.
- 또한 `fmt.Stringer` 같은 다른 인터페이스를 구현할 수 있어서 사용자가 읽을 수 있는 문자열 표현도 가능하다.

<br>

Rob Pike의 원문은 클로저 기반이고, Uber 가이드는 인터페이스 기반이다. 실무에서는 상황에 맞게 선택하면 된다. 단순한 경우에는 클로저 기반이 더 간결하고, 테스트 가능성이나 확장성이 중요한 경우에는 인터페이스 기반이 더 적합하다.

<br>

# 실무 적용

## 생성자 패턴으로의 전환

Rob Pike의 원문은 사실 **생성자가 아니라 이미 생성된 객체의 상태를 변경하는 패턴**을 보여준다. 기존 객체에 옵션을 적용하는 형태다. 
`foo.Option(pkg.Verbosity(3))`를 보면 알 수 있다.

<br>

하지만 실무에서는 대부분 **생성자 패턴**에 적용된다고 한다. 그 이유는 다음과 같다:

- 생성 시점에 설정이 필요한 경우가 많고
- 불변성을 유지하기 위해 생성 이후 변경을 막고 싶어서

<br>

생성자에 적용한 형태는 다음과 같다.

```go
type ServerOption func(*Server)

func NewServer(opts ...ServerOption) *Server {
    s := &Server{
        host: "localhost",
        port: 8080,
    }
    for _, opt := range opts {
        opt(s)
    }
    return s
}

func WithPort(port int) ServerOption {
    return func(s *Server) {
        s.port = port
    }
}
```

<br>

사용할 때는 아래와 같이 사용한다.
```go
// 사용
server := NewServer(
    WithPort(9090),
    WithTimeout(30 * time.Second),
)
```



이는 Rob Pike의 기본 버전 형태를 생성자에 적용한 것이다.

<br>

## 대안들과의 비교

생성자에 적용할 때 다른 대안들과 비교해 보면 Functional Options의 장점이 더 명확해진다.

<br>

**대안 1: 생성자에 수많은 인자를 넣는 방식**

```go
func NewServer(host string, port int, timeout time.Duration, retries int, ...) *Server
```

옵션이 늘어날 때마다 함수 시그니처가 복잡해지고, 필수/선택 구분이 어렵다.

<br>

**대안 2: 여러 변형 생성자를 만드는 방식**

```go
func NewServer(host string) *Server
func NewServerWithPort(host string, port int) *Server
func NewServerWithPortAndTimeout(host string, port int, timeout time.Duration) *Server
// 조합 폭발
```

옵션 조합의 수만큼 생성자가 필요하다.

<br>

**대안 3: Config 구조체 방식**

```go
type Config struct {
    Port    int
    Timeout time.Duration
    Retries int
}

NewServer(Config{
    Port:    8080,
    Timeout: 30 * time.Second,
    // Retries 생략 → 제로값(0)이 됨. 의도한 것인가?
})
```

선택적 필드 표현이 애매하다. 지정하지 않은 필드는 제로 값(Zero Value)이 되어 의도와 다르게 동작할 수 있다.

<br>

**대안 4: Builder 패턴**

```go
NewServerBuilder().
    Port(8080).
    Timeout(30 * time.Second).
    Build()
```

메서드 체이닝으로 장황해진다.

<br>

**Functional Options**

```go
NewServer(
    WithPort(8080),
    WithTimeout(30 * time.Second),
)
```

간결하고 명확하며, 필요한 옵션만 선택적으로 전달할 수 있다.

<br>

## 내 사례

회사에서 작성하는 Backend 코드에 학습 파이프라인 트리거를 위한 Argo Workflow Client가 있었다. 학습 제어 관련 변수(dataset split ratio, epoch, batch size 등), 데이터셋 augmentation 관련 변수들, checkpoint 및 로그 저장 관련 변수들 등 수많은 옵션이 필요했다.

파이프라인 트리거 시 이 값들을 주입해 줘야 하는데, 사용자가 명시하지 않으면 기본값을 사용해야 했다. 초기 개발 당시에는 Client에 속성으로 가지고 있다 주입해 주는 방식을 선택했는데, 시간이 지날수록 학습 제어가 세밀해지며, 생성자에 넣어야 할 파라미터가 점점 늘어났다. 자연히 생성자가 점점 길어지는 문제가 발생했다.

<br>

이를 해결하기 위해 Functional Options 패턴을 적용하면서, 추가로 **생성 시점에 검증까지 할 수 있도록** 변형했다. Option 함수가 error를 반환하도록 하면, 잘못된 옵션 조합을 생성 시점에 잡아낼 수 있다.

```go
type Option func(*Client) error

func WithDatasetSplitRatio(train, val float64) Option {
    return func(c *Client) error {
        if train + val != 1.0 {
            return errors.New("split ratios must sum to 1.0")
        }
        c.splitConfig = SplitConfig{TrainRatio: train, ValRatio: val}
        return nil
    }
}

func WithTrainerConfig(maxEpochs, maxBatchSize, dropoutInterval int) Option {
    return func(c *Client) error {
        if maxEpochs <= 0 {
            return errors.New("maxEpochs must be positive")
        }
        c.trainerConfig = TrainerConfig{
            MaxEpochs:           maxEpochs,
            MaxBatchSize:        maxBatchSize,
            DataDropoutInterval: dropoutInterval,
        }
        return nil
    }
}

func New(cfg Config, opts ...Option) (*Client, error) {
    c := &Client{
        // 기본값 설정
    }
    
    for _, opt := range opts {
        if err := opt(c); err != nil {
            return nil, err
        }
    }
    
    return c, nil
}
```

<br>

# 정리

Functional Options 패턴을 학습하고 적용하면서, **Go의 언어적 특성을 정말 잘 활용한 패턴**이라는 생각이 들었다.

1. **함수가 일급 객체(first-class citizen)라는 점**을 십분 활용한다. 함수를 타입으로 정의하고, 값으로 전달하고, 클로저로 상태를 캡처한다. 만약 함수가 일급 객체가 아니었다면, 이 패턴은 존재할 수 없었을 것이다.

2. **가변 인자(variadic parameters)를 지원한다는 점**도 중요하다. `opts ...Option`으로 원하는 만큼의 옵션을 유연하게 받을 수 있다. 이 덕분에 `NewServer()`, `NewServer(WithPort(8080))`, `NewServer(WithPort(8080), WithTimeout(30))`처럼 호출 형태가 자유로워진다.

3. **오버로딩이 없다는 제약**이 오히려 이런 창의적인 패턴을 낳았다는 점도 흥미롭다. 다른 언어였다면 그냥 오버로딩으로 해결했을 문제를, Go에서는 언어의 특성을 살려 더 우아하게 해결했다.

<br>

Rob Pike가 "I'm also happy at the way this uses Go's closures to achieve its goals with grace"라고 한 부분이 인상 깊다. 언어의 제약을 불평하기보다, 언어가 제공하는 것을 최대한 활용해서 우아한 해결책을 찾아낸 것. 이것이 바로 그 언어를 잘 쓴다는 것이 아닐까. 언어를 최대한 활용하며, 스스로의 설계에 만족하기까지 얼마나 많은 시간을 고민했을지 감히 상상조차 되지 않는다.

<br>

항상 느끼면서도 어렵지만, 언어는 기본에 충실할 때 가장 잘 쓸 수 있는 것이라는 생각이 든다. 대가는 괜히 대가가 아니다.

<br>

# 참고

- [Rob Pike - Self-referential functions and the design of options](https://commandcenter.blogspot.com/2014/01/self-referential-functions-and-design.html)
- [Dave Cheney - Functional options for friendly APIs](https://dave.cheney.net/2014/10/17/functional-options-for-friendly-apis)
- [Uber Go Style Guide - Functional Options](https://github.com/uber-go/guide/blob/master/style.md#functional-options)