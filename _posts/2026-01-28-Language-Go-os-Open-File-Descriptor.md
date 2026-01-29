---
title:  "[Go] os.Open의 파일 디스크립터 생성 동작"
excerpt: "dup()을 알아보다 발견한 Go os.Open의 흥미로운 동작"
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - syscall
  - file descriptor
  - netpoller
toc: true
---

<br>

파일 디스크립터 복제 시스템 콜인 `dup()`을 알아보다가 흥미로운 사실을 발견했다. Go에서 `os.Open`을 하면 파일 디스크립터가 1개가 아니라 3개가 생성된다. 왜 그런지 알아보자.

<br>

# TL;DR

- **발견**: `dup()` 호출 시 FD가 건너뛰어지는 현상은 `dup()`의 문제가 아니라 `os.Open`이 내부적으로 추가 FD를 생성하기 때문
- **`dup()`**: 파일 디스크립터 시스템 콜, "다음 번호 +1"이 아니라 "사용 가능한 가장 작은 FD 번호" 할당
- **`syscall.Open`**: 순수 시스템 콜, FD 1개만 생성
- **`os.Open`**: Go 런타임 래퍼, FD 3개 생성 (파일 1개 + netpoller 관련 2개)

<br>

# 배경 지식

## 파일 디스크립터

파일 디스크립터(File Descriptor, FD)는 운영체제가 열린 파일을 식별하기 위해 사용하는 정수 값이다.

| FD | 용도 |
|----|------|
| 0 | stdin (표준 입력) |
| 1 | stdout (표준 출력) |
| 2 | stderr (표준 에러) |
| 3~ | 사용자가 여는 파일들 |

> **참고**: 0, 1, 2는 "예약"이 아니라 **관례**다. 프로세스가 시작될 때 쉘이 이 FD들을 표준 입출력에 연결해 주는 것이며, 프로그램에서 `close(0)`으로 닫고 다른 파일을 열면 그 파일이 FD 0을 받을 수 있다. 이를 이용해 입출력 리다이렉션을 구현하기도 한다.

프로세스가 파일을 열면 커널은 사용 가능한 가장 작은 FD 번호를 할당한다. 프로세스당 열 수 있는 FD 수에는 제한이 있으며, `ulimit -n` 명령으로 확인할 수 있다.

## dup() 시스템 콜

`dup()`은 파일 디스크립터를 복제하는 시스템 콜이다. 같은 프로세스 내에서 하나의 파일을 여러 FD로 참조할 수 있게 해준다.

```go
fd1 := 3  // 원본 파일
fd2 := syscall.Dup(fd1)  // fd2 = 4 (또는 다음 사용 가능한 번호)
```

핵심 특징은 다음과 같다:
- 같은 파일 테이블 엔트리를 가리킴 (파일 offset 공유)
- **사용 가능한 가장 작은 FD 번호**를 할당

> 참고: `fork()`는 프로세스를 복제하고, `dup()`은 FD를 복제한다. 둘 다 파일 offset을 공유하지만, `fork()`는 메모리 공간이 분리되고 `dup()`은 같은 프로세스 내에서 동작한다.

## Blocking vs Non-blocking I/O

I/O 처리 방식에는 두 가지가 있다.

### Blocking I/O
```go
syscall.Read(fd, buf)  // 데이터가 올 때까지 OS 스레드가 멈춤
```
- 읽기/쓰기가 완료될 때까지 호출한 스레드가 대기
- 10,000개 파일을 동시에 읽으려면 10,000개 스레드 필요

### Non-blocking I/O
```go
f.Read(buf)  // 데이터 없으면 즉시 반환, goroutine만 양보
```
- 데이터가 준비되지 않았으면 즉시 반환
- 하나의 스레드로 여러 I/O를 처리 가능

> 이 글에서는 개념만 간단히 소개한다. blocking/non-blocking, epoll/kqueue 등은 중요한 개념이라 시간을 들여 찬찬히 알아볼 예정이다.

## Go의 Netpoller

Go 런타임은 **netpoller**라는 I/O 멀티플렉싱 시스템을 내장하고 있다. I/O 멀티플렉싱이란 **하나의 스레드가 여러 I/O 채널을 동시에 감시**하는 기법이다. 여러 파일/소켓 중 어느 것이 준비되었는지 운영체제에게 물어보고, 준비된 것만 처리한다. 

```
              ┌─────────────┐
              │  Netpoller  │ ← 하나의 시스템 스레드가 모니터링
              │  (epoll_fd) │
              └──────┬──────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
┌────▼────┐    ┌────▼────┐    ┌────▼────┐
│ file1   │    │ file2   │    │ file3   │
│ (fd 5)  │    │ (fd 8)  │    │ (fd 11) │
└─────────┘    └─────────┘    └─────────┘
     ▲               ▲               ▲
goroutine1     goroutine2     goroutine3
 (대기중)        (대기중)        (대기중)
```

- Linux에서는 `epoll`, BSD/macOS에서는 `kqueue` 사용 (운영체제가 제공하는 I/O 멀티플렉싱 API)
- 하나의 OS 스레드로 수천 개의 FD를 모니터링
- goroutine이 I/O 대기 시 OS 스레드는 다른 goroutine 실행

이 netpoller가 `os.Open`이 추가 FD를 생성하는 핵심 원인이다.

<br>

# 실험

## 실험 1: os.Open + dup

`dup()`의 기본 동작을 확인해 보았다.

```go
func demonstrateDup() {
    f, _ := os.Open("test.txt")
    fd1 := int(f.Fd()) // fd1 = 3

    fd2, _ := syscall.Dup(fd1) // fd2 = ?

    fmt.Printf("fd1=%d, fd2=%d\n", fd1, fd2)
}
```
```bash
# 결과
fd1=3, fd2=6
```

fd1이 3인 것은 예측 가능하다. 0, 1, 2는 stdin, stdout, stderr로 사용 중이니 다음 사용 가능한 번호인 3이 할당된 것이다. 그런데 `dup()`은 "사용 가능한 가장 작은 FD 번호"를 할당한다고 했으니, fd2는 4가 나와야 할 것 같은데 6이 나왔다. 4, 5는 어디로 갔을까?

<details>
<summary>전체 코드</summary>

```go
func demonstrateDup() {
    f, _ := os.Open("test.txt")
    fd1 := int(f.Fd()) // fd1 = 3

    fd2, _ := syscall.Dup(fd1) // fd2 = 6

    fmt.Printf("Same process (PID %d)\n", os.Getpid())
    fmt.Printf("fd1=%d, fd2=%d\n", fd1, fd2)

    buf1 := make([]byte, 5)
    syscall.Read(fd1, buf1)
    fmt.Printf("fd1 read: %s\n", buf1)

    buf2 := make([]byte, 5)
    syscall.Read(fd2, buf2)
    fmt.Printf("fd2 read: %s\n", buf2)
}

func main() {
    demonstrateDup()
}
```

</details>

## 실험 2: FD 상태 직접 확인

`syscall.Fstat`을 이용해 FD 상태를 직접 확인해 보자.

```go
func checkFDs(label string) {
    fmt.Printf("=== %s ===\n", label)
    var stat syscall.Stat_t
    for i := 0; i < 10; i++ {
        err := syscall.Fstat(i, &stat)
        if err == nil {
            fmt.Printf("  fd %d: OPEN\n", i)
        }
    }
}

func demonstrateDup() {
    checkFDs("초기 상태")

    f, _ := os.Open("test.txt")
    fd1 := int(f.Fd())
    checkFDs("os.Open 후")

    fd2, _ := syscall.Dup(fd1)
    checkFDs("dup 후")
}
```

```bash
# 결과
=== 초기 상태 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN

=== os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN

=== dup 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN
  fd 6: OPEN
```

`os.Open()`으로 파일 1개를 열었는데, **FD가 3개(3, 4, 5)가 추가**되었다. 이는 이 프로세스에서 **첫 번째 `os.Open()` 호출**이었기 때문에 netpoller 초기화가 함께 발생한 것이다. (실험 5에서 자세히 확인) 반면 `dup()` 이후에는 **fd 6 하나만 추가**된 것을 볼 수 있다.

<details>
<summary>전체 코드</summary>

```go
func checkFDs(label string) {
    fmt.Printf("=== %s ===\n", label)
    var stat syscall.Stat_t
    for i := 0; i < 10; i++ {
        err := syscall.Fstat(i, &stat)
        if err == nil {
            fmt.Printf("  fd %d: OPEN\n", i)
        }
    }
}

func demonstrateDup() {
    fmt.Println("=== Initial FD state ===")
    checkFDs("initial")

    f, _ := os.Open("test.txt")
    fd1 := int(f.Fd())
    fmt.Printf("\n=== After os.Open(), fd1=%d ===\n", fd1)
    checkFDs("after open")

    fd2, _ := syscall.Dup(fd1)
    fmt.Printf("\n=== After Dup(), fd2=%d ===\n", fd2)
    checkFDs("after dup")

    fmt.Printf("\nSame process (PID %d)\n", os.Getpid())
    fmt.Printf("fd1=%d, fd2=%d\n", fd1, fd2)

    buf1 := make([]byte, 5)
    syscall.Read(fd1, buf1)
    fmt.Printf("fd1 read: %s\n", buf1)

    buf2 := make([]byte, 5)
    syscall.Read(fd2, buf2)
    fmt.Printf("fd2 read: %s\n", buf2)
}

func main() {
    demonstrateDup()
}
```

</details>

## 실험 3: syscall.Open과 비교

순수 시스템 콜인 `syscall.Open`과 비교해 보자.

```go
func demonstrateSyscallOpen() {
    checkFDs("초기 상태")

    fd1, _ := syscall.Open("test.txt", syscall.O_RDONLY, 0)
    checkFDs("syscall.Open 후")

    fd2, _ := syscall.Dup(fd1)
    checkFDs("dup 후")
}
```

```bash
# 결과
=== 초기 상태 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN

=== syscall.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN

=== dup 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
```

`syscall.Open`은 **FD 1개만 추가**되고, `dup()` 결과도 예상대로 4가 나온다.

<details>
<summary>전체 코드</summary>

```go
func checkFDs(label string) {
    fmt.Printf("=== %s ===\n", label)
    var stat syscall.Stat_t
    for i := 0; i < 10; i++ {
        err := syscall.Fstat(i, &stat)
        if err == nil {
            fmt.Printf("  fd %d: OPEN\n", i)
        }
    }
}

func demonstrateSyscallOpen() {
    fmt.Println("\n### Test: Using syscall.Open directly ###")
    fmt.Println("=== Initial FD state ===")
    checkFDs("initial")

    fd1, _ := syscall.Open("test.txt", syscall.O_RDONLY, 0)
    fmt.Printf("\n=== After syscall.Open(), fd=%d ===\n", fd1)
    checkFDs("after syscall.open")

    fd2, _ := syscall.Dup(fd1)
    fmt.Printf("\n=== After Dup(), fd2=%d ===\n", fd2)
    checkFDs("after dup")

    buf1 := make([]byte, 5)
    syscall.Read(fd1, buf1)
    fmt.Printf("fd1 read: %s\n", buf1)

    buf2 := make([]byte, 5)
    syscall.Read(fd2, buf2)
    fmt.Printf("fd2 read: %s\n", buf2)

    syscall.Close(fd1)
    syscall.Close(fd2)
}

func main() {
    demonstrateSyscallOpen()
}
```

</details>

## 실험 4: Close 후 FD 상태

`os.Close()` 후 FD가 어떻게 되는지 확인해 보자.

```go
func main() {
    checkFDs("프로그램 시작")

    // syscall.Open
    fd, _ := syscall.Open("test.txt", syscall.O_RDONLY, 0)
    checkFDs("syscall.Open 직후")
    syscall.Close(fd)
    checkFDs("syscall.Close 후")

    // os.Open
    f, _ := os.Open("test.txt")
    checkFDs("os.Open 직후")
    f.Close()
    checkFDs("os.Close 후")
}
```
```bash
# 결과
=== 프로그램 시작 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN

=== syscall.Open 직후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN

=== syscall.Close 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN

=== os.Open 직후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN
  fd 6: OPEN
  fd 7: OPEN

=== os.Close 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 6: OPEN
  fd 7: OPEN
```

아래와 같은 점을 발견할 수 있다:
- `os.Open()`은 FD 3개 추가 (5, 6, 7)
- `os.Close()`는 파일 FD(5)만 닫고, 내부 FD(6, 7)는 Go 런타임이 계속 보유

> **참고**: 프로그램 시작 시 fd 3, 4가 이미 열려있는 이유는 이 실험이 **독립된 프로세스가 아니라 같은 테스트 코드 내에서 이전 실험들과 함께 실행**되었기 때문이다. 새로운 프로세스를 `go run main.go`로 실행하면 fd 0, 1, 2만 열려있어야 정상이다. Netpoller는 **lazy initialization**을 사용하므로, 프로세스 시작만으로는 초기화되지 않고 처음 `os.Open()` 등이 호출될 때 초기화된다.

<details>
<summary>전체 코드</summary>

```go
package main

import (
    "fmt"
    "os"
    "strings"
    "syscall"
)

func checkAndPrintFDs(label string) {
    fmt.Printf("\n=== %s ===\n", label)
    var stat syscall.Stat_t
    for i := 0; i < 10; i++ {
        err := syscall.Fstat(i, &stat)
        if err == nil {
            fmt.Printf("  fd %d: OPEN\n", i)
        }
    }
}

func main() {
    checkAndPrintFDs("프로그램 시작")

    // 1단계: 직접 syscall.Open 호출
    fmt.Println("\n[Step 1] syscall.Open 호출 전")
    checkAndPrintFDs("syscall.Open 전")

    fd, err := syscall.Open("test.txt", syscall.O_RDONLY, 0)
    if err != nil {
        fmt.Printf("Error: %v\n", err)
        return
    }
    fmt.Printf("\nsyscall.Open 반환: fd=%d\n", fd)
    checkAndPrintFDs("syscall.Open 직후")

    syscall.Close(fd)
    checkAndPrintFDs("syscall.Close 후")

    // 2단계: os.Open 호출 - 단계별 추적
    fmt.Println("\n" + strings.Repeat("=", 50))
    fmt.Println("[Step 2] os.Open 호출")
    fmt.Println(strings.Repeat("=", 50))

    checkAndPrintFDs("os.Open 호출 전")

    f, err := os.Open("test.txt")
    if err != nil {
        fmt.Printf("Error: %v\n", err)
        return
    }

    fmt.Printf("\nos.Open 반환: fd=%d\n", f.Fd())
    checkAndPrintFDs("os.Open 직후")

    // File 객체의 내부 상태 확인
    fmt.Printf("\nFile 객체 정보:\n")
    fmt.Printf("  Name: %s\n", f.Name())
    fmt.Printf("  Fd: %d\n", f.Fd())

    f.Close()
    checkAndPrintFDs("os.Close 후")
}
```

</details>

## 실험 5: Netpoller FD 생성 시점

앞선 실험들에서 `os.Open()`이 FD를 3개 사용한다고 했는데, 이것이 **매번** 그런 것인지 확인해 보자. Netpoller 관련 FD(epoll fd, pipe 등)는 프로세스 전체에서 **매번 생성**되는지, 아니면 **한 번만 생성**되고 재사용되는지 확인하는 실험이다.

```go
func main() {
    checkFDs("프로그램 시작")

    // 첫 번째 os.Open
    f1, _ := os.CreateTemp("", "test1-*.txt")
    defer os.Remove(f1.Name())
    defer f1.Close()
    fmt.Printf("첫 번째 os.Open, fd=%d\n", f1.Fd())
    checkFDs("첫 번째 os.Open 후")

    // 두 번째 os.Open
    f2, _ := os.CreateTemp("", "test2-*.txt")
    defer os.Remove(f2.Name())
    defer f2.Close()
    fmt.Printf("두 번째 os.Open, fd=%d\n", f2.Fd())
    checkFDs("두 번째 os.Open 후")

    // 세 번째 os.Open
    f3, _ := os.CreateTemp("", "test3-*.txt")
    defer os.Remove(f3.Name())
    defer f3.Close()
    fmt.Printf("세 번째 os.Open, fd=%d\n", f3.Fd())
    checkFDs("세 번째 os.Open 후")
}
```

```bash
# 결과
=== 프로그램 시작 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN

첫 번째 os.Open, fd=3
=== 첫 번째 os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN

두 번째 os.Open, fd=6
=== 두 번째 os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN
  fd 6: OPEN

세 번째 os.Open, fd=7
=== 세 번째 os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN
  fd 4: OPEN
  fd 5: OPEN
  fd 6: OPEN
  fd 7: OPEN

=== 분석 ===
첫 번째 파일 FD: 3
두 번째 파일 FD: 6
세 번째 파일 FD: 7

FD 증가폭:
  첫 번째 → 두 번째: +3
  두 번째 → 세 번째: +1
```

`os.Open` 호출 순서에 따른 FD 증가폭을 기준으로, 아래 사항을 발견할 수 있다:

| 순서 | FD 증가폭 | 설명 |
|------|-----------|------|
| 첫 번째 `os.Open` | +3 (fd 3, 4, 5) | 파일 FD 1개 + **netpoller 초기화로 2개** |
| 두 번째 `os.Open` | +1 (fd 6) | 파일 FD 1개만 |
| 세 번째 `os.Open` | +1 (fd 7) | 파일 FD 1개만 |

**결론**적으로, Netpoller 관련 FD는 **프로세스 생명주기 동안 한 번만 생성**된다. 첫 번째 `os.Open()` 호출 시 netpoller가 초기화되면서 추가 FD(epoll fd, pipe 등)가 생성되고, 이후 호출에서는 이를 **재사용**한다.

### 추가 실험: 파일 닫은 후 다시 열기

위 실험에서 파일들을 `defer`로 닫은 후, 동일한 함수를 다시 호출해 두 번째 실험을 진행해 보았다.
- `defer`를 이용해 닫았기 때문에, fd 7, 6, 3 순서로 닫힘

```bash
=== 두 번째 실험 시작 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 4: OPEN   ← netpoller FD (유지됨)
  fd 5: OPEN   ← netpoller FD (유지됨)

첫 번째 os.Open, fd=3
=== 첫 번째 os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN   ← 다시 3번부터 할당!
  fd 4: OPEN
  fd 5: OPEN

두 번째 os.Open, fd=6
세 번째 os.Open, fd=7

FD 증가폭:
  첫 번째 → 두 번째: +3
  두 번째 → 세 번째: +1
```

**관찰 결과**를 살펴 보면 아래와 같다.

1. **defer 실행 순서**: 첫 번째 실험의 파일들이 `defer`로 인해 **7 → 6 → 3 순서**로 닫힘 (LIFO)
2. **netpoller FD 유지**: fd 4, 5는 파일을 닫아도 **계속 열려있음** (프로세스 전체에서 재사용)
3. **FD 재할당**: 두 번째 실험에서 fd 3이 비어있으므로 **다시 3번부터 할당**받음
4. **FD 증가폭 동일**: 두 번째 실험에서도 +3, +1 패턴이지만, 이는 netpoller 초기화가 아니라 **fd 4, 5가 이미 사용 중**이기 때문

<details>
<summary>전체 코드</summary>

```go
package main

import (
    "fmt"
    "os"
    "syscall"
)

func checkFDs(label string) {
    fmt.Printf("=== %s ===\n", label)
    var stat syscall.Stat_t
    for i := 0; i < 15; i++ {
        err := syscall.Fstat(i, &stat)
        if err == nil {
            fmt.Printf("  fd %d: OPEN\n", i)
        }
    }
    fmt.Println()
}

func checkDupMultipleOpen() {
    // 첫 번째 os.Open
    f1, err := os.CreateTemp("", "test1-*.txt")
    if err != nil {
        panic(err)
    }
    defer os.Remove(f1.Name())
    defer f1.Close()

    fd1 := int(f1.Fd())
    fmt.Printf("첫 번째 os.Open (CreateTemp), fd=%d\n", fd1)
    checkFDs("첫 번째 os.Open 후")

    // 두 번째 os.Open
    f2, err := os.CreateTemp("", "test2-*.txt")
    if err != nil {
        panic(err)
    }
    defer os.Remove(f2.Name())
    defer f2.Close()

    fd2 := int(f2.Fd())
    fmt.Printf("두 번째 os.Open (CreateTemp), fd=%d\n", fd2)
    checkFDs("두 번째 os.Open 후")

    // 세 번째 os.Open
    f3, err := os.CreateTemp("", "test3-*.txt")
    if err != nil {
        panic(err)
    }
    defer os.Remove(f3.Name())
    defer f3.Close()

    fd3 := int(f3.Fd())
    fmt.Printf("세 번째 os.Open (CreateTemp), fd=%d\n", fd3)
    checkFDs("세 번째 os.Open 후")

    // 분석
    fmt.Println("=== 분석 ===")
    fmt.Printf("첫 번째 파일 FD: %d\n", fd1)
    fmt.Printf("두 번째 파일 FD: %d\n", fd2)
    fmt.Printf("세 번째 파일 FD: %d\n", fd3)
    fmt.Printf("\nFD 증가폭:\n")
    fmt.Printf("  첫 번째 → 두 번째: +%d\n", fd2-fd1)
    fmt.Printf("  두 번째 → 세 번째: +%d\n", fd3-fd2)
}

func main() {
    // 프로그램 시작 시 FD 상태
    checkFDs("프로그램 시작")
    checkDupMultipleOpen()

    // 위의 호출에서 열었던 파일 닫힌 후 (defer로 7, 6, 3 순서로 닫힘)
    checkFDs("두 번째 실험 시작")
    checkDupMultipleOpen() // 두 번째 호출
}
```

</details>

### 추가 실험 2: 즉시 Close로 FD 재사용

파일을 열자마자 바로 닫으면 FD가 어떻게 재사용되는지 확인해 보았다.

```go
func checkDupMultipleOpenImmediate() {
    // 첫 번째 os.Open
    f1, _ := os.CreateTemp("", "test1-*.txt")
    fd1 := int(f1.Fd())
    fmt.Printf("첫 번째 os.Open, fd=%d\n", fd1)
    f1.Close() // ← 즉시 닫기
    os.Remove(f1.Name())

    // 두 번째 os.Open
    f2, _ := os.CreateTemp("", "test2-*.txt")
    fd2 := int(f2.Fd())
    fmt.Printf("두 번째 os.Open, fd=%d\n", fd2)
    f2.Close() // ← 즉시 닫기
    os.Remove(f2.Name())

    // 세 번째 os.Open
    f3, _ := os.CreateTemp("", "test3-*.txt")
    fd3 := int(f3.Fd())
    fmt.Printf("세 번째 os.Open, fd=%d\n", fd3)
    f3.Close()
    os.Remove(f3.Name())
}
```

```bash
# 결과
=== 프로그램 시작 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN

첫 번째 os.Open, fd=3
=== 첫 번째 os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN   ← 파일 FD
  fd 4: OPEN   ← netpoller (epoll fd)
  fd 5: OPEN   ← netpoller (pipe)

=== 첫 번째 Close 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 4: OPEN   ← netpoller 유지
  fd 5: OPEN   ← netpoller 유지
               (fd 3은 닫힘)

두 번째 os.Open, fd=3   ← fd 3 재사용!
=== 두 번째 os.Open 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 3: OPEN   ← 다시 fd 3 할당
  fd 4: OPEN
  fd 5: OPEN

=== 두 번째 Close 후 ===
  fd 0: OPEN
  fd 1: OPEN
  fd 2: OPEN
  fd 4: OPEN
  fd 5: OPEN
               (fd 3은 다시 닫힘)

세 번째 os.Open, fd=3   ← fd 3 또 재사용!

FD 증가폭:
  첫 번째 → 두 번째: +0
  두 번째 → 세 번째: +0
```

동일한 fd가 재사용됨을 확인할 수 있다.

```
FD 상태 변화 (시간순):

프로그램 시작:  [0, 1, 2]
                    ↓
첫 번째 Open:   [0, 1, 2, 3, 4, 5]  ← 파일(3) + netpoller(4, 5)
                    ↓
첫 번째 Close:  [0, 1, 2,    4, 5]  ← 3만 닫힘
                    ↓
두 번째 Open:   [0, 1, 2, 3, 4, 5]  ← 3 재할당 (가장 작은 빈 번호)
                    ↓
두 번째 Close:  [0, 1, 2,    4, 5]  ← 3만 닫힘
                    ↓
세 번째 Open:   [0, 1, 2, 3, 4, 5]  ← 3 또 재할당
```

- **fd 3**: 파일 열기/닫기에 따라 할당/해제 반복
- **fd 4, 5**: netpoller FD로 **프로세스 종료까지 유지**
- **FD 증가폭 +0**: 즉시 닫으면 같은 FD 번호를 계속 재사용

<details>
<summary>전체 코드</summary>

```go
package main

import (
    "fmt"
    "os"
    "syscall"
)

func checkFDs(label string) {
    fmt.Printf("=== %s ===\n", label)
    var stat syscall.Stat_t
    for i := 0; i < 15; i++ {
        err := syscall.Fstat(i, &stat)
        if err == nil {
            fmt.Printf("  fd %d: OPEN\n", i)
        }
    }
    fmt.Println()
}

func checkDupMultipleOpenImmediate() {
    fmt.Println(">>> 즉시 Close 버전 <<<")

    // 첫 번째 os.Open
    f1, _ := os.CreateTemp("", "test1-*.txt")
    fd1 := int(f1.Fd())
    fmt.Printf("첫 번째 os.Open, fd=%d\n", fd1)
    checkFDs("첫 번째 os.Open 후")
    f1.Close()
    os.Remove(f1.Name())
    checkFDs("첫 번째 Close 후")

    // 두 번째 os.Open
    f2, _ := os.CreateTemp("", "test2-*.txt")
    fd2 := int(f2.Fd())
    fmt.Printf("두 번째 os.Open, fd=%d\n", fd2)
    checkFDs("두 번째 os.Open 후")
    f2.Close()
    os.Remove(f2.Name())
    checkFDs("두 번째 Close 후")

    // 세 번째 os.Open
    f3, _ := os.CreateTemp("", "test3-*.txt")
    fd3 := int(f3.Fd())
    fmt.Printf("세 번째 os.Open, fd=%d\n", fd3)
    checkFDs("세 번째 os.Open 후")
    f3.Close()
    os.Remove(f3.Name())

    fmt.Printf("\nFD 증가폭:\n")
    fmt.Printf("  첫 번째 → 두 번째: +%d\n", fd2-fd1)
    fmt.Printf("  두 번째 → 세 번째: +%d\n", fd3-fd2)
}

func main() {
    checkFDs("프로그램 시작")
    checkDupMultipleOpenImmediate()
}
```

</details>

<br>

# 분석

## os.Open 호출 체인

`os.Open`의 내부 동작을 추적해 보았다.

```
os.Open(name)
    ↓
os.OpenFile(name, O_RDONLY, 0)
    ↓
openFileNolog(name, flag, perm)
    ↓
open(name, flag|O_CLOEXEC, perm)  ← 실제 시스템 콜, fd 생성
    ↓
newFile(fd, name, kindOpenFile, nonBlocking)  ← 여기서 추가 FD 생성
```

### os.Open

```go
func Open(name string) (*File, error) {
    return OpenFile(name, O_RDONLY, 0)
}
```

단순히 `OpenFile`을 호출한다.

### os.OpenFile

```go
func OpenFile(name string, flag int, perm FileMode) (*File, error) {
    testlog.Open(name)  // 테스트용 로깅 (FD 생성 안 함)
    f, err := openFileNolog(name, flag, perm)
    if err != nil {
        return nil, err
    }
    f.appendMode = flag&O_APPEND != 0
    return f, nil
}
```

`testlog.Open`은 테스트 로깅용이고, 실제 작업은 `openFileNolog`에서 이루어진다.

### openFileNolog 함수

이 함수에서 핵심적인 두 가지 작업이 이루어진다:

1. **`open()` 호출**: 실제 시스템 콜로 파일을 열고 FD를 반환받는다 (반환값 `r`이 실제 파일의 FD)
2. **`newFile()` 호출**: File 객체를 생성하면서 추가 FD가 생성된다

```go
func openFileNolog(name string, flag int, perm FileMode) (*File, error) {
    var (
        r int       // ← 여기가 파일 디스크립터
        s poll.SysFile
        e error
    )
    
    // 실제 시스템 콜 호출
    ignoringEINTR(func() error {
        r, s, e = open(name, flag|syscall.O_CLOEXEC, syscallMode(perm))
        return e
    })
    // ↑ 여기까지는 FD 1개만 (파일)
    
    // File 객체 생성 - 여기서 추가 FD 생성
    f := newFile(r, name, kindOpenFile, unix.HasNonblockFlag(flag))
    // ↑ 여기서 FD 추가 생성 (netpoller 관련)
    
    return f, nil
}
```

### newFile 함수

```go
func newFile(fd int, name string, kind newFileKind, nonBlocking bool) *File {
    // 1. File 구조체 생성
    f := &File{&file{
        pfd: poll.FD{       // poll.FD: Go의 FD 래퍼
            Sysfd: fd,       // 실제 시스템 FD
            IsStream: true,
        },
    }}
    
    // 2. Netpoller 등록 여부 결정
    pollable := kind == kindOpenFile || kind == kindPipe || ...
    
    // 3. Non-blocking 모드 설정
    if pollable {
        syscall.SetNonblock(fd, true)
    }
    
    // 4. Netpoller에 등록 - 여기서 추가 FD 생성
    f.pfd.Init("file", pollable)
    //        ↑ epoll_create, pipe 등으로 추가 FD 생성
    
    return f
}
```

<br>

`poll.FD`는 Go의 내부 FD 관리 구조체로, 실제 시스템 FD와 비동기 I/O 메타데이터를 포함한다.

```
os.File (사용자에게 공개) → os.file (내부) → poll.FD (FD 래퍼)
```


#### **os.File** (사용자에게 공개되는 타입)

```go
// The methods of File are safe for concurrent use.
type File struct {
    *file // os specific
}
```

`os.File`은 내부 `file` 구조체를 포인터로 감싸고 있다.

#### **os.file** (내부 구조체)

```go
type file struct {
    pfd         poll.FD                 // ← 핵심: poll.FD를 포함
    name        string
    dirinfo     atomic.Pointer[dirInfo]
    nonblock    bool                    // non-blocking 모드 여부
    stdoutOrErr bool                    // stdout 또는 stderr인지
    appendMode  bool                    // append 모드로 열렸는지
}
```

`file` 구조체가 `poll.FD`를 필드로 가지고 있다.

#### **poll.FD** (FD 래퍼)

```go
// FD is a file descriptor. The net and os packages use this type as a
// field of a larger type representing a network connection or OS file.
type FD struct {
    fdmu fdMutex      // Read/Write 메서드 직렬화를 위한 뮤텍스
    
    Sysfd int         // ← 실제 시스템 파일 디스크립터
    
    SysFile           // 플랫폼 의존적 상태
    
    pd pollDesc       // ← I/O poller (netpoller와 통신)
    
    csema uint32      // 파일 닫힘 시 시그널되는 세마포어
    isBlocking uint32 // blocking 모드 설정 여부
    IsStream bool     // 스트림 디스크립터 여부
    ZeroReadIsEOF bool // 0바이트 읽기가 EOF인지
    isFile bool       // 파일인지 (네트워크 소켓이 아닌지)
}
```

핵심 필드:
- `Sysfd`: 실제 시스템 FD (커널이 할당한 정수)
- `pd`: `pollDesc` 타입으로, netpoller와 통신하는 인터페이스

주요 역할:
- `Sysfd`: 실제 시스템 FD 보관
- 비동기 I/O 상태 관리
- netpoller와의 통신을 위한 메타데이터
- 읽기/쓰기 대기, 타임아웃, 취소 등 관리

### Init

`Init()` 호출 시 netpoller와 연결된다:

```go
func (fd *FD) Init(net string, pollable bool) error {
    fd.SysFile.init()
    
    if net == "file" {
        fd.isFile = true
    }
    if !pollable {
        fd.isBlocking = 1
        return nil
    }
    
    // 여기서 netpoller에 등록 → 추가 FD 생성
    err := fd.pd.init(fd)
    if err != nil {
        fd.isBlocking = 1
    }
    return err
}
```

바로 이 `fd.pd.init(fd)` 호출이 추가 FD가 생성되는 핵심 지점이다. 내부적으로 `epoll_create`와 `pipe` 시스템 콜을 호출하여 netpoller 인프라를 구축하고, 이 과정에서 2개의 추가 FD가 생성된다. 결국 `os.Open` 한 번에 총 3개의 FD(파일 1개 + netpoller 관련 2개)가 열리는 것이다.

## syscall.Open 호출 체인

```go
func Open(path string, mode int, perm uint32) (fd int, err error) {
    return openat(_AT_FDCWD, path, mode|O_LARGEFILE, perm)
}

func openat(dirfd int, path string, flags int, mode uint32) (fd int, err error) {
    // Go 문자열 → C 문자열 변환
    _p0, err := BytePtrFromString(path)
    
    // 실제 시스템 콜 호출
    r0, _, e1 := Syscall6(SYS_OPENAT, ...)
    
    fd = int(r0)  // 반환값 = 파일 디스크립터
    return
}
```

`syscall.Open`은 순수한 시스템 콜 래퍼로, Go 런타임의 개입이 없다:
- netpoller 등록 없음
- non-blocking 설정 없음
- `poll.FD` 생성 없음
- 커널이 반환한 FD 그대로 사용

## 비교 요약

| 항목 | syscall.Open | os.Open |
|-----|--------------|---------|
| **FD 개수** | 1개 (파일만) | 3개 (파일 + netpoller) |
| **I/O 모드** | blocking (OS 스레드 멈춤) | non-blocking (goroutine만 양보) |
| **동시성** | 10,000파일 = 10,000스레드 | 10,000파일 = 적은 수의 스레드 |
| **성능** | 단순 작업에 적합 | 많은 동시 I/O에 효율적 |
| **사용 케이스** | 저수준 제어, 단순 파일 읽기 | 일반적인 Go 프로그래밍 |

<br>

# 결론: os.Open의 추가 FD를 사용하는 이유

Go가 `os.Open`에서 추가 FD를 사용하는 이유는 **동시성(concurrency)**을 효율적으로 지원하기 위해서다.

## 핵심 차이

Go에서 파일을 열면, 래핑된 구조체로 다루기 때문에 순수 시스템 FD 외에 추가적인 것들이 포함된다.

```go
syscall.Open → fd 5 (순수 시스템 FD)
    vs
os.Open → File{pfd: poll.FD{Sysfd: 5, ...}} (Go의 관리 구조체)
```

`os.Open`이 하는 일:
- Go 런타임이 완전히 래핑
- netpoller에 등록
- non-blocking 모드 설정
- `poll.FD`로 감싸기
- 비동기 I/O 준비 완료

## 설계 목적

### 1. Goroutine 확장성

```go
// syscall.Open 사용 시
for i := 0; i < 10000; i++ {
    fd, _ := syscall.Open(files[i], syscall.O_RDONLY, 0)
    syscall.Read(fd, buf)  // OS 스레드가 블록됨
    // → 동시 처리하려면 10,000개 스레드 필요
}

// os.Open 사용 시
for i := 0; i < 10000; i++ {
    go func(path string) {
        f, _ := os.Open(path)
        f.Read(buf)  // goroutine만 양보, OS 스레드는 계속 일함
    }(files[i])
}
// → 몇 개의 OS 스레드로 모든 goroutine 처리 가능
```

수천 개의 파일을 동시에 열어도 적은 OS 스레드로 처리할 수 있다.


### 2. 효율적인 리소스 사용

I/O 대기 중에도 다른 goroutine이 실행 가능하다. 한 goroutine이 파일 읽기를 기다리는 동안, 같은 OS 스레드에서 다른 goroutine이 실행될 수 있다.

<br>

## 3. Go의 철학

"동시성(concurrency)을 쉽고 효율적으로" 지원하는 것이 Go의 핵심 설계 철학이다. `os.Open`의 추가 FD는 이 철학을 구현하기 위한 비용이다.

## 장단점

**장점** (서버, 네트워크 I/O에서):
- 높은 동시성 (10,000+ 동시 연결 가능)
- 적은 메모리 사용 (스레드 vs goroutine)
- Go 스케줄러와 완벽 통합

**단점**:
- 단순 파일 읽기는 오히려 오버헤드가 될 수 있음 (netpoller 설정 비용)
- 디스크 I/O는 여전히 blocking일 수 있음 (epoll은 네트워크 I/O에 최적화됨)

> **참고**: netpoller는 네트워크 I/O에 최적화되어 있다. 디스크 I/O의 경우 Linux에서 epoll이 제대로 작동하지 않아, 결국 `Read()`에서 blocking이 발생할 수 있다. 다만 goroutine 양보는 하므로 `syscall.Open`보다는 낫다.

<br>

# 주의사항

## FD 제한

이론적으로 FD 제한이 빡빡한 환경에서는 `os.Open`의 추가 FD가 문제가 될 수 있다. 하지만 현실에서 이 문제를 마주치는 경우는 드물다. 대부분의 환경에서 FD 제한은 충분히 높고, 파일을 수천 개씩 동시에 여는 경우도 흔치 않기 때문이다.

다만, 다음과 같은 특수한 환경에서는 알아두면 유용하다:
- FD 제한이 낮게 설정된 Docker 컨테이너
- 임베디드 시스템
- 수천 개의 파일을 동시에 열어야 하는 특수한 경우

```bash
# 프로세스당 FD 제한 확인
ulimit -n
# 출력: 1024 (기본값, 대부분의 시스템에서 더 높게 설정됨)
```

Go에서 특별히 다르게 처리할 건 없다. Close를 잘 해주고, 동시에 너무 많이 열지 않으면 된다. netpoller FD는 프로세스 전체에서 재사용되므로 파일당 1개씩만 증가한다.

## Close의 중요성

```go
func leak() {
    f, _ := os.Open("test.txt")
    // f.Close() 없음
}
```

Go는 `runtime.SetFinalizer`를 통해 GC 시 파일을 자동으로 닫아준다. 하지만 GC 타이밍이 불확실하므로, 루프에서 Close를 빠뜨리면 일시적으로 FD가 쌓일 수 있다.

```go
// 주의가 필요한 패턴
for i := 0; i < 1000; i++ {
    f, _ := os.Open(fmt.Sprintf("file%d.txt", i))
    f.Read(buf)
    // Close 안 함 → GC 전까지 FD가 열린 상태
}

// 권장 패턴
for i := 0; i < 1000; i++ {
    f, _ := os.Open(fmt.Sprintf("file%d.txt", i))
    // ... 작업 ...
    f.Close()
}
```

> **참고**: netpoller 관련 FD(epoll, pipe)는 Go 런타임이 프로세스 전체에서 재사용한다. 따라서 파일을 닫지 않아도 3개씩 누수되는 것은 아니고, 파일 FD 1개만 누수된다.

<br>

# 권장사항

## os.Open 사용

사실 대부분의 경우에 `os.Open`을 사용하면 된다. 단순한 파일 읽기/쓰기에도 `os.Open`을 쓰는 것이 일반적이다. `syscall.Open`은 정말 특수한 경우(저수준 제어가 필요하거나, ioctl/fcntl 등을 직접 다뤄야 할 때)에만 고려하면 된다.

이 글에서 살펴본 추가 FD 생성은 알아두면 좋은 지식이지만, 실제로 `syscall.Open`으로 바꿔야 할 정도로 문제가 되는 경우는 거의 없다.

## Best Practice

```go
// 1. 반드시 defer로 Close (FD 제한 환경에서 특히 중요)
func readFile() error {
    f, err := os.Open("file.txt")
    if err != nil {
        return err
    }
    defer f.Close()
    // ...
}

// 2. 극히 드문 경우: 저수준 제어가 필요할 때만 syscall
// (일반적인 경우에는 os.Open으로 충분)
func lowLevelControl() {
    fd, _ := syscall.Open("file.txt", syscall.O_RDONLY, 0)
    defer syscall.Close(fd)
    // ioctl, fcntl 등 직접 제어
}

// 3. 많은 파일 동시 처리: semaphore로 제한
sem := make(chan struct{}, 100)  // 최대 100개만 동시 열기
for _, file := range files {
    sem <- struct{}{}
    go func(f string) {
        defer func() { <-sem }()
        fd, _ := os.Open(f)
        defer fd.Close()
        // ...
    }(file)
}
```

<br>

# 실무 응용: 소켓과 FD

이 글에서는 파일 중심으로 설명했지만, 네트워크 소켓도 FD다. Go에서 `net.Dial`로 TCP/UDP 연결을 열면 파일과 마찬가지로 FD가 할당되고, netpoller에 등록된다.

## 대량 연결 시 FD 예측

예를 들어 RTSP 스트림 2000개를 연결한다면, 전송 모드에 따라 필요한 FD가 다르다:

| 모드 | 채널당 FD | 2000채널 기준 |
|------|----------|--------------|
| TCP Interleaved | 1개 | ~2,000개 |
| UDP (비디오만) | 3개 (RTSP + RTP + RTCP) | ~6,000개 |
| UDP (비디오+오디오) | 5개 | ~10,000개 |

## FD 제한 확인

```bash
# 프로세스당 FD 제한 (soft/hard)
ulimit -n
ulimit -Hn

# 시스템 전체 FD 제한
cat /proc/sys/fs/file-max

# 현재 프로세스의 열린 FD 수
ls /proc/<PID>/fd | wc -l
```

기본 `ulimit -n`이 1024인 경우가 많은데, 대량 연결 시에는 부족하다. 서비스 운영 시에는 `/etc/security/limits.conf`나 systemd unit 파일에서 `LimitNOFILE`을 늘려야 한다.

## Go에서 주의할 점

```go
// 연결 실패 시에도 Close 패턴 유지
conn, err := net.Dial("tcp", addr)
if err != nil {
    return err
}
defer conn.Close()

// 동시 연결 수 제한 (semaphore 패턴)
sem := make(chan struct{}, 500)
for _, target := range targets {
    sem <- struct{}{}
    go func(t string) {
        defer func() { <-sem }()
        conn, _ := net.Dial("tcp", t)
        defer conn.Close()
        // ...
    }(target)
}
```

소켓도 FD다. 대량의 네트워크 연결을 다루는 경우(RTSP 스트림, 동시 접속 등)에는 FD 제한을 반드시 확인해야 한다. 

<br>

# 정리

| 항목 | 설명 |
|-----|------|
| **발견** | `os.Open`은 파일 1개당 FD 3개 사용 |
| **원인** | Go 런타임의 netpoller가 비동기 I/O를 위해 추가 FD 사용 |
| **syscall.Open** | 순수 시스템 콜, FD 1개, blocking I/O |
| **os.Open** | Go 래퍼, FD 3개, non-blocking I/O, 높은 동시성 |
| **dup() 동작** | "사용 가능한 가장 작은 FD 번호" 할당 |
| **주의** | FD 제한 이슈는 이론적으론 가능하지만 현실에서는 드묾 |

<br>

# 참고 자료

- [Go 소스 코드 - os/file_unix.go](https://github.com/golang/go/blob/master/src/os/file_unix.go)
- [Go 소스 코드 - internal/poll/fd_unix.go](https://github.com/golang/go/blob/master/src/internal/poll/fd_unix.go)
- [The Go Blog - Go's Declaration Syntax](https://go.dev/blog/declaration-syntax)
- [Linux man page - dup(2)](https://man7.org/linux/man-pages/man2/dup.2.html)
- [Linux man page - epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html)

<br>