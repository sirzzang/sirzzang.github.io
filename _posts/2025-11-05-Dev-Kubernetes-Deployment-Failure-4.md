---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 4. Deadlock"
excerpt: 보다 보니, 이거 그냥 Deadlock이 아니던가
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - deployment
  - scheduler
---



~~도대체 거의 1년 가까이 된 내용을 왜 이제서야 작성하게 되었는지 반성하며~~ 회사에서 Deployment를 재배포하다가 쿠버네티스의 스케쥴링과 Deployment 업데이트 전략에 대해 공부하게 된 내용을 작성한다.



<br>

# 여담

공부하고 분석하다 보니 드는 생각인데, 이 상황은 마치 내가 goroutine을 사용하다 겪는 Deadlock 상황 같기도 하다. 정말 자주 겪어서 그런가, 바로 생각이 나 버렸다.

> *참고*: 여담의 여담
>
> 사실 go 언어에서 goroutine 쓰면서 Deadlock 상황을 자주 마주하는 건, 내 문제기도 하다. 다른 언어들(Python의 threading, Java의 Thread 등)로도 동시성 프로그래밍을 하다 보면 Deadlock을 겪을 수 있지만, 내 경우에는 go 언어를 주력으로 사용하면서 goroutine을 유독 자주 쓰게 되었다. 다른 언어에 비해 동시성 프로그래밍에 대한 접근성이 좋다고 느껴지기 때문이다.
>
> - `go` 키워드만 붙이면 되니까, 뭔가 이것 저것 임포트해서 불편하게 쓰지 않아도 되고,
> - go 런타임에서 관리되고, OS 스레드를 spawning하는 것처럼 비용이 크지도 않다고 하며,
> - 이런 이유에서인지 go의 장점 중 하나로 동시성 프로그래밍에 좋다는 게 언급되곤 하니,
> - 잘 모르면서도 goroutine을 잘 써야 go를 잘 쓰는 것 같다는 느낌을 받아, 
>
> 불필요한 상황에서도 goroutine을 써서 개발해 보려고 했던 적이 많다. 다행인지 불행인지, go 런타임이 Deadlock을 감지해서 fatal 에러를 던져줘 버리는 덕분(?)에, 남발해서 쓸 때마다 교훈을 얻었다. 그 덕에 지금은 그 어려움을 뼈저리게 느껴, 남발하지 않으려고 노력하기도 하지만, 이렇게 전혀 다른 분야(?)에서 인사이트를 얻게 되기도 하더라.

<br>

내 Deployment에 설정된 배포 전략을,

```yaml
replicas: 1
maxSurge: 1          # 새 파드 먼저 생성
maxUnavailable: 0    # 기존 파드는 새 파드 Ready 후 삭제
```

goroutine을 이용해 비유해 보자면, 딱 이런 상황이 아닐까?

```go
package main

import (
	"fmt"
	"time"
)

func main() {
	gpu := make(chan int, 1)  // 버퍼 크기 1 (GPU 1개)
	gpu <- 1                  // 기존 파드가 GPU 사용 중
	
	done := make(chan bool)
	
	// 새 파드 (goroutine)
	go func() {
		fmt.Println("새 파드: GPU 기다리는 중...")
		for {
			select {
			case gpuID := <-gpu:
				fmt.Printf("새 파드: GPU %d 획득, Ready!\n", gpuID)
				done <- true
				return
			default:
				fmt.Println("새 파드: GPU 없음, 계속 대기...")
				time.Sleep(100 * time.Millisecond)
			}
		}
	}()
	
	// Deployment Controller (main goroutine)
	fmt.Println("Controller: 새 파드가 Ready 될 때까지 기존 파드 유지")
	<-done // 새 파드 Ready 기다림
	
	// 여기 도달 못함 (새 파드는 영원히 Ready 안됨)
	fmt.Println("Controller: 기존 파드 종료, GPU 반환")
	gpu <- 1 // GPU 반환
}
```

<br>

그럼 아래와 같은 출력이 무한히 반복되다가

```bash
Controller: 새 파드가 Ready 될 때까지 기존 파드 유지
새 파드: GPU 기다리는 중...
새 파드: GPU 없음, 계속 대기...
새 파드: GPU 없음, 계속 대기...
새 파드: GPU 없음, 계속 대기...
(영원히 반복)
```

마지막엔 결국 이런 에러를 받게 될 것이다.

```bash
fatal error: all goroutines are asleep - deadlock!
```

<br>

생각해 보면, Deadlock 상황과 참 닮았다. Deadlock이 발생하는 조건을 다 충족해 버린다.

1. manual exclusion: 상호 배제
   - GPU는 한 번에 하나의 파드에서만 사용할 수 있음

2. hold and wait: 보유 및 대기
   - 기존 파드: GPU 보유
   - 새 파드: GPU 대기

3. no preemption: 비선점
   - 두 파드가 우선순위도 같아서, 선점할 수도 없음

4. circular wait: 순환 대기
   ```bash
   기존 파드 → (새 파드 Ready 대기) → 새 파드
   새 파드 → (GPU 대기) → 기존 파드
   ↑                                  ↓
   ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
   ```

   - 기존 파드: 새 파드가 Ready 상태가 되어야 종료될 수 있음
   - 새 파드: 기존 파드가 종료되어야 GPU를 받아 생성될 수 있음



<br>

해결 방법 역시 비슷한 면이 있다.

- goroutine 채널 버퍼 늘리기 = GPU 늘리기
  ```go
  gpu := make(chan int, 2) // gpu 2개로 늘리기
  ```

- 순서 바꾸기
  ```go
  gpu <- 1
  go func() {
  	<-gpu // 먼저 뻬기 = 기존 파드 먼저 내리기
  	gpu <- 2 // 다시 넣기 = 새 파드 배치하기	
  }
  ```

  

  

<br>

참으로 얄궂은 상황이 아닐 수 없다. 그러나 다행히도(?) 스케쥴링이 실패했다는 에러 메시지를 받는 경우가 전부 다 goroutine Deadlock이 발생해 에러 메시지를 받는 경우와 동일한 상황인 것은 아니다. 사고 실험을 해 보면, 아래와 같은 경우에도 스케쥴링이 불가하다는 에러 메시지를 받는 게 가능하다.

- 새로 파드를 생성하는 데 배치할 노드가 없는 상황: 예컨대, 내 상황에서 GPU가 없는 노드를 `nodeSelector`로 걸어 놓고 새로 생성하는 상황
- 스케일 업하는데 배치할 노드가 없는 상황: 예컨대, 내 상황에서 `replicas`를 2로 늘리는 상황

<br>
그리고 go runtime과 Kubernetes scheduler가 이런 상황을 처리하는 방식도 다르다.
- go runtime: Deadlock을 감지하고 fatal error 발생
- Kubernetes scheduler: 무한히 재시도하며 Pending 상태 유지


<br>

# 교훈

이러나 저러나, Kubernetes든 goroutine이든 잘 모르고 쓰면 문제가 된다. 그리고, 어쩔 수 없지만, 이렇게 문제를 겪어야 배울 수 있다.

> 이건 뭐 순환 참조도 아니고...



