---
title:  "[Go] Closure Capture - 1. Closure"
excerpt: go의 클로저 캡처에 대해 알아 보기 위해 클로저에 대해 알아 보자.
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

<br>

클로저 캡처에 대해 알아 보자. 이를 위해, 먼저 클로저가 무엇인지 자세히 살펴 보자.

<br>

# 클로저

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
 

# 렉시컬 스코프 체인


클로저 개념을 이해하기 위해, **렉시컬 스코프 체인**(Lexical Scope Chain)이라는 개념을 이해해야 한다. 이는, **렉시컬 스코프를 기반으로 연결된 스코프의 체인**을 의미한다.
- 스코프: 변수의 유효 범위
- 렉시컬 스코프: 변수의 유효 범위를 **코드 작성 위치**(어디서 선언되었는지)로 결정하는 방식
- 렉시컬 스코프 체인: 렉시컬 스코프 방식으로 안쪽에서 바깥쪽으로 연결된 스코프를 따라 변수를 찾아 가기 위한 체인

<br>

왜 이런 단어를 사용하게 되었을까. 단어를 하나씩 찬찬히 뜯어 보자.
- 렉시컬(Lexical): 어휘의, 단어의. 프로그래밍에서는 코드에서 변수를 찾을 때, 코드의 **어디에 쓰여 있나**를 봄
  - 사전에서 단어를 찾을 때, 단어를 위치로 찾듯, 코드의 물리적 위치를 기반으로 판단한다는 의미에서 Lexical이라는 단어를 사용함
  - 반대의 개념은 다이나믹(Dynamic)으로, 코드가 실행되는 위치로 결정되는 언어에 해당
- 스코프(Scope): 범위. **변수가 보이는 범위**를 의미함
  - 블록 스코프: 블록 안에서만 보임
  - 함수 스코프: 함수 안에서만 보임
  - 패키지 스코프: 패키지 안에서 보임
- 체인(Chain): 사슬. 프로그래밍에서는 **연결된 것들을 따라가는 경로**를 의미함

<br>
결과적으로, 코드가 쓰여진 위치(Lexical)에 따라, 변수가 보이는 영역(Scope)들을 사슬(Chain)처럼 연결하여, 안쪽에서 바깥쪽으로 변수를 찾아 가는 것을 의미한다. 

```go
// 스코프 체인: inner 스코프 -> middle 스코프 -> outer 스코프 -> global 스코프

var a = "global"          // 스코프 1 (가장 바깥)
func outer() {
    var b = "outer"       // 스코프 2
    func middle() {
        var c = "middle"  // 스코프 3
        func inner() {
            var d = "inner"  // 스코프 4 (가장 안쪽)
        }
    }
}
```

<br>

# 클로저와 렉시컬 스코프 체인
클로저는 자신의 렉시컬 스코프 체인을 기억한다. 덕분에, 아래와 같은 특징을 가진다.



## 변수 탐색

클로저는 렉시컬 스코프 체인을 따라 변수를 찾는다. 즉, 렉시컬 스코프 체인을 따라 최상위 스코프를 만날 때까지 변수를 탐색한다.



```go
    [전역 스코프]
        ↑
        |
  [outer 함수 스코프]
        ↑
        |
  [middle 함수 스코프]
        ↑
        |
  [inner 함수 스코프]
        ↑
        |
      [클로저]
```

즉, 클로저가 변수를 사용하면, 아래와 같은 과정을 거쳐 변수를 탐색한다.
1. 자신의 로컬 스코프 확인
2. 없으면 한 단계 위(부모) 확인: 
3. 없으면 또 한 단계 위(조부모) 확인
4. ... 전역 스코프까지 확인

최상위(전역) 스코프를 만날 때까지 렉시컬 스코프 체인을 따라 변수를 탐색하는 것을 반복했음에도 불구하고 변수를 찾지 못할 때, 컴파일 에러가 발생한다.

### Shadowing

이러한 변수 탐색 특징으로 인해, 아래와 같이 **안쪽 스코프의 변수가 바깥쪽 스코프의 같은 이름 변수를 가리는** 현상도 발생한다. 이를 Shadowing이라고 한다. 가까운 스코프의 변수가 먼 스코프의 같은 이름 변수를 가려 버린다.

```go
var x = "global x"

func level1() {
    var x = "level1 x" // level1의 x가 원본이나, 여기까지 확인하지 않음
     
    level2 := func() {
        var x = "level2 x"  // level2에서 확인: 있음 -> shadowing
        
        level3 := func() {
            // 여기서 x를 찾으면?
            fmt.Println(x)  // 자신의 스코프에서 x를 찾을 수 없음
        }
        
        level3()
    }
    
    level2()
}
```


## 메모리 관점
종료된 함수에서도, 스코프 체인의 변수에 접근할 수 있다.
```go
func outer() {
    x := 1  // 보통은 outer가 끝나면 사라짐
    
    closure := func() {
        fmt.Println(x)  // x를 사용
    }
    
    return closure
}

c := outer()  // outer는 끝났지만
c()  // x에 접근 가능! (클로저가 스코프 체인을 유지)
```
- 클로저 개념이 없었다면, `outer` 함수가 종료되면서 스택에서 `x`가 제거되어 x에 접근이 불가해야 함
- 클로저 개념이 있어서, `outer` 함수가 종료된 후에도 클로저가 `x`를 참조하기 때문에 스코프 체인이 유지되며 `x`에 접근할 수 있게 됨

<br>


