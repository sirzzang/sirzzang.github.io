---
title:  "[Go] Closure Capture"
excerpt: go의 클로저 캡처에 대해 알아 보자
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - closure
  - closure capture
toc: true
---



# 개념

 클로저 캡처란, **클로저가 자신이 정의된 환경의 변수를 참조하거나 복사하여 사용하는 것**을 의미한다.

<br>

## 클로저

클로저(Closure)란, **외부 환경을 캡처한 함수** 혹은 **외부 환경을 참조하는 함수**이다.

- 클로저 = 함수 + 캡처된 환경
- 함수(함수 자체)와, 캡처된 환경(변수들)이 필요함

<br>

아래 함수에서 `makeCounter`가 반환하는 익명 함수가 클로저이다. 

```go
func makeCounter() func() int {
    count := 0  // 외부 환경
    
    // 이 익명 함수가 클로저
    return func() int {
        count++  // 클로저 자신의 로컬 변수가 아닌데도, 접근할 수 있음
        return count
    }
}
```

- 클로저 vs. 일반 함수

  ```go
  // 일반 함수 - 클로저가 아님
  func add(a, b int) int {
      return a + b
  }
  
  
  func makeAdder(x int) func(int) int {
    	// 클로저 - 외부 변수 x를 capture
      return func(y int) int {
          return x + y  // x를 capture
      }
  }
  ```

- 클로저 vs. 익명 함수: 익명 함수라고 다 클로저인 것은 아님

  ```go
  // 이건 그냥 익명 함수 (클로저 아님)
  func() {
      fmt.Println("Hello")
  }()
  
  // 이건 클로저 (외부 변수 name을 capture)
  name := "이레이저"
  func() {
      fmt.Println(name)  // capture 발생
  }()
  ```

  

<br>

Go 공식 문서에서 [function literals](https://go.dev/ref/spec#Function_literals)에 대한 부분에, 아래와 같은 클로저에 대한 표현을 찾을 수 있다.

> Function literals are *closures*: they may refer to variables defined in a surrounding function. Those variables are then shared between the surrounding function and the function literal, and they survive as long as they are accessible.

엄밀한 정의라고 보기는 어렵지만, 함수 리터럴이 외부 변수를 참조(capture)할 때 클로저가 될 수 있음을 설명하고 있다. 결과적으로는 외부 변수를 캡처하는 함수 리터럴을 클로저라고 할 수 있는 것이다.

<br>



## 클로저 캡처

클로저에 대한 이해를 바탕으로 클로저 캡처(Closure Capture)를 직역해 보자면, `클로저가 붙잡다/포획하다` 정도로 해석할 수 있을 것이다. 즉, **함수가 자신의 외부 스코프에 있는 변수를 기억하고 접근할 수 있게 하는 메커니즘**을 의미한다.

- 함수가 자신이 선언된 환경(lexical scope)을 함께 가지고 다니며 사용할 수 있게 됨
- 자신의 로컬 변수에만 접근할 수 있는 일반 함수와 달리, 클로저는 자신이 태어난 시점에 주변 환경에 있던 변수까지도 들고 다니며 사용할 수 있음

<br>



# Go의 클로저 캡처

Go에서의 클로저 변수 캡처 방식은 변수 값을 복사하는 것이 아니라, 변수 자체를 공유하는 것이다. 즉, Go에서의 클로저 캡처 방식은 **참조** 기반이라는 것이다.

무슨 말이냐면, 아래 코드에서 클로저는 `x`의 값 1을 복사하는 것이 아니라, `x` 변수 자체를 참조한다는 것이다. 클로저가 캡처하는 것은 값 1이 아니라, 변수 `x`에 대한 참조(주소)이다.

```go
func main() {
    x := 1
    
    inc := func() {
        x++ // x를 참조로 capture
    }
} 
```

<br>


이러한 클로저 변수 캡처 방식의 특성 상, 잘 모르고 쓰면, 버그가 발생하기 매우 쉽다.

<br>



## (1.22 이전) 루프 버그

가장 흔하게 go에서 루프 안에서 goroutine이나 함수를 생성할 때 발생하는 버그이다.

```go
for i := 0; i < 5; i++ {
    go func() {
        fmt.Println(i)  // 루프 변수 i를 참조로 캡처 (i의 주소를 캡처)
    }()
}
```

* 그러면 개념적으로는 어떤 고루틴이 먼저 끝날지 모르기 때문에, 0, 1, 2, 3, 4가 실행 순서만 달리 하여 출력되어야 할 것 같지만

  ```go
  // 예상 출력(순서 랜덤)
  0
  4
  3
  1
  2
  ```

* 아래와 같이 5만 나오게 된다

  ```go
  // 실제 출력
  5
  5
  5
  5
  5
  ```



<br>

클로저 캡처가 변수 자체를 참조한다는 것을 생각하면 이해할 수 있다.

![closure-capture-loop]({{site.url}}/assets/images/closure-capture-loop.png){: .align-center}
<sup><center>모든 goroutine이 같은 루프 변수 i를 참조</center></sup>

* goroutine으로 실행되는 클로저 안의 `i`는 루프 변수 `i` 자체를 참조한다.

  ```go
  for i := 0; i < 5; i++ { // 루프 변수 i는 한 번만 생성됨
      go func() {
          fmt.Println(i) // goroutine 안에서 i는 루프 변수 i 자체를 참조
      }()
  }
  ```

* 실제 goroutine은 루프가 끝난 후에 실행된다. 실행 시점, 즉, 클로저가 변수의 값을 읽을 시점에는 루프 변수 `i`의 값이 5가 되어 있기 때문에, 모든 goroutine이 5를 읽게 된다.

  ```go
  // 시간 순서:
  // t=0: i=0, goroutine 1 생성 (아직 실행 안 됨)
  // t=1: i=1, goroutine 2 생성 (아직 실행 안 됨)
  // t=2: i=2, goroutine 3 생성 (아직 실행 안 됨)
  // t=3: i=3, goroutine 4 생성 (아직 실행 안 됨)
  // t=4: i=4, goroutine 5 생성 (아직 실행 안 됨)
  // t=5: i=5, 루프 종료
  // t=6: goroutine들이 실행 시작 → 모두 i=5를 읽음!
  ```



<br>

이런 예시를 통해 보면, `나는 이런 문제 안 겪을 것 같은데` 싶지만, 생각보다 자주 마주하게 된다. 특히 go는 언어 차원에서 동시성 프로그래밍을 쉽게 사용할 수 있도록 지원하기 때문에, 루프를 순회하면서 고루틴을 이용해 여러 작업을 병렬로 처리해야 겠다고 생각하는 순간, 이런 버그가 굉장히 많이 발생한다.

```go
var eg errgroup.Group

for _, frame := range video {
    eg.Go(func() error {
        // frame processing logic
        
        fmt.Println("Processing frame:", frame.Id) // 마지막 프레임에 대해서만 반복 처리됨
        return nil
    })
}

eg.Wait()
```



<br>

### 1.22 버전 이후 개선

Go 1.22+ 버전에서부터 이와 같은 문제가 해결되었다고 한다.

- [go 1.22 for loop](https://go.dev/doc/go1.22#language) 설명에서 아래와 같은 문단을 찾을 수 있다.

  > Previously, the variables declared by a “for” loop were created once and updated by each iteration. In Go 1.22, each iteration of the loop creates new variables, to avoid accidental sharing bugs. The [transition support tooling](https://go.dev/wiki/LoopvarExperiment#my-test-fails-with-the-change-how-can-i-debug-it) described in the proposal continues to work in the same way it did in Go 1.21.

  * 기존에 루프 변수는 단 한 번만 생성되고, 매 반복마다 그 값만 변경되었으나,
  * 1.22 이후에 루프 변수는 각 반복마다 새로운 변수 인스턴스를 생성한다. 
  * 즉, 각 반복마다 서로 다른 변수가 생성되므로 클로저가 캡처해도 독립적으로 동작한다.

- 그러나, [이 글](https://go.dev/wiki/LoopvarExperiment)에서 보듯, 루프 변수의 주소를 가져가거나, 클로저가 캡처하는 경우에만 다르게 컴파일된다고 하며, 일반적인 루프에서는 최적화를 위해 기존과 동일하게 동작한다고 한다.

  ```go
  // 이런 일반적인 루프는 영향 없음 (최적화됨)
  for i := 0; i < len(arr); i++ {
      arr[i] = i * 2
  }
  
  // 이런 경우만 새로운 방식 적용 (주소를 가져감)
  for i := 0; i < 10; i++ {
      ptrs = append(ptrs, &i)  // 주소 사용
  }
  
  // 이런 경우도 적용 (클로저에서 capture)
  for i := 0; i < 10; i++ {
      go func() {
          fmt.Println(i)  // 클로저가 capture
      }()
  }
  ```

- 즉, 1.22 이후 버전에서는 아래와 같은 코드가 안전하다.

  ```go
  // Go 1.22+
  for i := 0; i < 5; i++ {
      go func() {
          fmt.Println(i)  // 의도한 대로 동작
      }()
  }
  ```

<br>





## 원본 값 변경 버그

클로저를 실행했을 때, 원본 값이 변경될 수도 있다. 아래와 같은 예시에서 함수를 실행하면, 클로저 캡처에 의해 원본이 바뀌어 버린다.

```go
func main() {
    x := 1
    
    inc := func() {
        x++
    }
    
    inc()
    fmt.Println(x) // 2 - 원본이 변경됨
}
```

실무에서 클로저를 다른 사람에게 넘겼거나, 나중에 실행될 거라 예상하지 못하고 구현해 두었다가, 의도치 않게 변경되는 경우가 있을 수 있다.

아래와 같은 예를 들 수 있다. 매일 초기화되는 일일 에러 카운터를 만들고 싶었는데, 현실에서는 에러 카운터가 계속 누적되며 에러 개수가 폭발하게 된다.

```go
// 에러 카운터
errorCount := 0

// 문제 1. 어딘가에서 에러 카운터가 증가되고
// 에러 핸들러 등록 (프레임워크/라이브러리에서 호출됨)
app.SetErrorHandler(func(err error) {
    errorCount++
    if errorCount > 100 {
        alertOps("Too many errors!")
    }
})

// 매일 자정에 리포트 생성하는 클로저
generateDailyReport := func() {
    report := fmt.Sprintf("Errors today: %d", errorCount)
    sendEmail(report)
    
    // 문제 2. 리포트 생성 후 errorCount를 초기화하지 않는다면,
    // errorCount = 0 // 이 줄을 까먹음!
}

// 결과:
// Day 1: "Errors today: 50"
// Day 2: "Errors today: 120" (실제로는 70개인데 누적됨)
```



<br>

# 올바른 사용

Go의 클로저 캡처를 버그 없이 안전하게 사용하려면 어떻게 해야 할까. 아래와 같은 두 가지 방법이 있으나, **shadowing 방식**으로 새로운 변수를 생성하여 캡처할 것이 권장된다.

- shadowing: 모든 타입에 대해 안전
- 함수 파라미터 전달
  - 단순 값 타입(int, string 등)에만 안전
  - 포인터나 참조 의미를 가진 타입(슬라이스, 맵, 포인터)은 주의 필요

<br>

## shadowing

루프 안에서 클로저 캡처를 사용할 일이 있다면, 아래와 같이 새로운 변수를 생성해서 값을 복사해 놓는 것이 좋다.

```go
for i := 0; i < 5; i++ {
    i := i  // 새로운 변수 i 생성 (shadowing)
    
    go func() {
        fmt.Println(i)  // 각 goroutine이 자신만의 i 복사본 참조
    }()
}
```

- 동작 원리

  - 루프 변수 `i`와 루프 내부에서 새로 선언한 변수 `i`는 서로 다른 변수
  - 내부 `i`는 외부 `i`의 현재 값을 복사함 
  - 클로저는 내부에서 새로 선언한 변수 `i`를 캡처
  - 각 반복마다 새로운 변수가 생성되므로 독립적

- 클로저가 내부에서 새로 선언한 변수 `i`를 참조하게 됨
- 각 루프마다 아래와 같은 원리로 동작함

  ```go
  반복 0:
    외부 i @ 0x1000 = 0
    내부 i @ 0x2000 = 0 (복사)
    goroutine → 내부 i (0x2000) 참조
  
  반복 1:
    외부 i @ 0x1000 = 1
    내부 i @ 0x2004 = 1 (복사)
    goroutine → 내부 i (0x2004) 참조
  
  반복 2:
    외부 i @ 0x1000 = 2
    내부 i @ 0x2008 = 2 (복사)
    goroutine → 내부 i (0x2008) 참조
  ```



<br>

실무에서는 다음과 같이 사용하면 된다.

```go
for _, stream := range streams {
    stream := stream  // shadowing
    go func() {
        processRTSP(stream.URL)
    }()
}
```

```go
for i, device := range devices {
    i, device := i, device // 여러 변수에 대한 shadowing도 가능
    go func() {
        log.Printf("Deploying to device %d: %s", i, device.ID)
        deploy(device)
    }()
}
```







<br>



## 함수 파라미터 전달

```go
for i := 0; i < 5; i++ {
    go func(i int) {  // 파라미터로 받음 → i는 새로운 지역 변수
        fmt.Println(i)
    }(i)  // 현재 i 값을 복사해서 전달
}
```

- 동작 원리
  - Go의 함수 호출은 **call by value** 방식
  - 함수에 인자를 전달할 때 항상 값을 복사해서 전달
  - 함수의 파라미터 `i`는 완전히 새로운 변수
- 주의 사항
  - **단순 값 타입**(int, float, string 등)에 대해서만 안전함
  - 포인터, 슬라이스, 맵, 채널 등 참조 의미를 가진 타입은 파라미터로 전달해도 같은 대상을 가리키므로 문제가 발생할 수 있음





<br>

## Go 1.22+ 업데이트 

위에서 살펴봤듯, Go 1.22부터는 루프 변수가 자동으로 각 반복마다 새로 생성되므로, `go.mod`의 go 버전이 1.22 이상이면 shadowing을 명시적으로 작성하지 않아도 된다. 그러니, Go 버전을 업데이트하는 것도 좋은 선택지가 될 수 있다.

```go
// Go 1.22+에서는 안전
for i := 0; i < 5; i++ {
    go func() {
        fmt.Println(i)  // 각 반복의 i 값 출력
    }()
}
```



단, `go.mod`의 go 버전과 실제 컴파일러 버전이 모두 1.22 이상이어야 한다.



<br>

# 사용 패턴

잘못 사용한다면 많은 버그를 일으키지만, 잘 사용한다면 굉장히 강력하고 유용한 기능이다. 애초에 필요하니까 만들어진 메커니즘이다. 아래와 같은 패턴을 잘만 응용한다면, 매우 도움이 된다.

<br>

아래와 같은 경우에 사용하면 좋다.

* **설정, 컨텍스트를 *구워넣은* 함수**가 필요할 때
* **상태를 캡슐화**해서 외부 접근을 제한하고 싶을 때
* **콜백, 핸들러에 추가 정보**를 전달하고 싶을 때
* **팩토리 패턴**으로 비슷하지만 설정이 다른 함수들을 만들 때
* **부분 적용**으로 함수의 일부 인자를 미리 고정하고 싶을 때

<br>

몇 가지 예시는 다음과 같다.

* 상태 캡슐화: go는 클래스가 없기 때문에, 클로저를 잘 사용하면 private 변수를 만들 수 있음

  ```go
  func makeCounter() func() int {
      count := 0 // 외부에서 직접 접근 불가능
      
      return func() int {
          count++
          return count
      }
  }
  
  counter1 := makeCounter()
  counter2 := makeCounter()
  
  fmt.Println(counter1()) // 1
  fmt.Println(counter1()) // 2
  fmt.Println(counter2()) // 1 (독립적인 상태)
  ```

* 비슷하지만, 설정이 다른 함수들을 만들고 싶을 때

  ```go
  // 다양한 데이터베이스 연결 팩토리
  type Database interface {
      Query(string) ([]map[string]interface{}, error)
  }
  
  func makeDatabaseFactory(dbType string, connString string) func() (Database, error) {
      // dbType과 connString을 capture
      
      return func() (Database, error) {
          switch dbType {
          case "postgres":
              return connectPostgres(connString)
          case "mysql":
              return connectMySQL(connString)
          case "mongodb":
              return connectMongoDB(connString)
          default:
              return nil, fmt.Errorf("unknown db type: %s", dbType)
          }
      }
  }
  
  // 각 환경별 팩토리 생성 시 사용
  devDBFactory := makeDatabaseFactory("postgres", "localhost:5432/dev")
  prodDBFactory := makeDatabaseFactory("postgres", "prod-server:5432/prod")
  
  // 나중에 필요할 때 연결
  devDB, _ := devDBFactory()
  prodDB, _ := prodDBFactory()
  ```

* 재귀 함수 구현 시 외부 상태를 공유할 때 ~~dfs 알고리즘 구현할 때(…)~~

  ```go
  visited := make([]bool, len(graph))
  
  var dfs func(node int) int
  dfs = func(node int) int {
    visited[node] = true // visited 참조
    count := 1
    for _, next := range graph[node] {
      if !visited[next] {
        count += dfs(next)
      }
    }
    return count
  }
  ```

  

<br>



# 결론

go의 클로저는 유용한 기능이지만, 클로저 변수 캡처 방식으로 인해 원치 않는 버그를 일으키기도 한다. 따라서, 클로저를 쓸 때는, 반드시 기억하자.

```go
// 새 변수에 복사
for _, x := range items {
    x := x
    go func() { use(x) }()
}

// 파라미터로 전달
for _, x := range items {
    go func(x Type) { use(x) }(x)
}

// 버그를 일으키는 방법
for _, x := range items {
    go func() { use(x) }()  // 버그!
}
```

go 1.22 이상을 쓰면 되는 거 아닌가 생각할 수 있지만, 다음과 같은 이유로 명시적 shadowing을 습관화하는 것이 좋다:
- 팀원들이 다양한 버전을 사용할 수 있음
- 코드 리뷰 시 의도가 명확함
- 포인터나 복잡한 타입에서는 여전히 주의 필요
- 다른 프로젝트(1.22 미만)에서도 안전한 코드 작성 가능
