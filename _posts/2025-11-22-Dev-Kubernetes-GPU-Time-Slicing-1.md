---
title:  "[Kubernetes] Kubernetes 환경에서 GPU Time Slicing 사용하기 - 1. 개념"
excerpt: GPU Time Slicing에 대해 알아보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - gpu
  - time slicing
---



<br>

# 개요

쿠버네티스 환경에서 GPU는 특수한 자원이다. GPU는 쿠버네티스가 스케줄할 수 있는 자원이 아니라서, 사용 설정만 하려고 해도 좀 번거로운 절차가 필요하다.

* [NVIDIA Device Plugin을 이용한 배포](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Setting/)
* GPU Operator를 이용한 배포

<br>

특수하다는 것에는, 이렇게 쿠버네티스가 GPU를 스케줄 대상 자원으로 인식할 수 없다는 맥락 외에, 더 나아가, 쿠버네티스가 GPU를 **독점 자원**으로 취급한다는 의미가 담겨 있다.

독점 자원이란, **쿠버네티스에서 파드를 할당할 때 하나의 파드에 하나의 GPU만 할당한다**는 의미이다. 스케줄러가 애초에 GPU를 요청하는 여러 개의 파드를 하나의 GPU만 있는 노드에 배치해 주지 않는다는 것이다. 결과적으로 쿠버네티스 환경에서는 애초에 하나의 프로세스만 GPU를 사용하게 된다. 
<br>

## GPU 분할의 필요성
그런데 **작업이 가볍거나 간헐적일 때** GPU를 여러 워크로드가 나눠 쓸 수 있다면 비용 대비 효율이 크게 올라간다. 아래와 같은 사례를 예로 들 수 있다.
- AI 추론 서빙
  - RTX 4090 GPU 1대가 있고, 2개의 추론 파드를 서빙해야 함
  - 각 모델은 GPU 메모리 7GB 정도만 사용 (RTX 4090은 24GB)
  - GPU 분할 없이는 RTX 4090 GPU 1대가 더 필요함
  - GPU 분할 시, 기존 1대의 GPU만을 이용해 서빙할 수 있음
- 개발/테스트 환경
  - 개발자 10명이 각자 모델 학습 실험 중
  - 대부분 시간은 코드 작성 및 데이터 전처리 (GPU 미사용)
  - 실제 학습은 하루에 2-3시간 정도
  - 현재: 각자 GPU 할당 받기 위해 대기 → 생산성 저하
  - 만약 GPU를 분할하여 사용할 수 있다면, 10명이 GPU 3-4개를 유동적으로 공유할 수 있음


<br>
## GPU 분할 기법

그래서 쿠버네티스 환경에서 GPU를 분할하기 위한 기법은 정녕 없을까. 그렇지 않다. 아래와 같이 두 가지 방법이 있다.

* MIG(Multi-Instance GPU): 하드웨어적 분할. 말 그대로 GPU를 하드웨어적으로 여러 개의 인스턴스로 나눠 사용함. 물리적 분할
* Time Slicing: 소프트웨어적 공유. 하나의 GPU를 여러 개의 파드가 시분할하여 나눠 사용함. 논리적인 분할

MIG의 경우, 하드웨어적 분할이라는 데서 짐작할 수 있겠지만, 애초에 하드웨어 레벨에서 지원되는 GPU에서만 사용할 수 있다. 물론, 엄밀하게는 Time Slicing도 모든 GPU 아키텍처에서 다 지원되는 것은 아니지만, MIG보다는 지원되는 GPU 범위가 넓다.

<br>
지금부터는, GPU를 분할하여 사용하는 두 가지 방법 중, Time Slicing에 대해 알아보자.

<br>

# GPU Time Slicing

먼저, GPU의 Time Slicing이 무엇인지 명확하게 이해해 보자.

## Time Slicing

**하나의 물리적 자원을 시간 단위로 분할하여 여러 작업이 공유**하는 기법이다. 일반적인 개념이지만, GPU 관점에서는 하나의 GPU를 여러 프로세스가 시간을 나눠 사용하는 것을 의미한다.

- 일반적인 예시:
  - CPU Time Slicing: 하나의 CPU 코어를 여러 프로세스가 시간을 나눠 사용
  - Network Time Slicing: 하나의 네트워크 채널을 시간을 나눠 사용

조금 더 엄밀하게 정의하자면, **시간 기반의 강제적 context switching**이라고 할 수 있다.

<br>

## Context Switching

**현재 진행 중인 작업 컨텍스트를 전환**하는 것을 의미한다. 일반적인 개념이지만, GPU 관점에서는 GPU가 실행 중인 작업의 컨텍스트를 바꾸는 행위이다.

<br>

GPU Context Switching 방식으로는 Cooperative Context Switching, Preemptive Context Switching이 있다.

<br>

### Cooperative Context Switching

```text
Time: 0s ────────────────────────────────────────────────→   60s
Process A: |══════════════════════|                         (30초)
Process B:                        |══════════════════════|  (30초)
           ↑                      ↑
        시작                Context Switch (A 완료 후)
```
* 작업이 스스로 양보 (자발적)
* 커널 완료 시 전환
* 강제 중단 불가
* 다른 프로세스는 기존 프로세스가 끝날 때까지 대기

<br>
### Preemptive Context Switching

```text
Time: 0s ────────────────────────────────────────────→ 60s
Process A: |███|   |███|   |███|   |███|   |███|    ...
Process B:     |███|   |███|   |███|   |███|   |███|
           ↑   ↑   ↑   ↑
           시작   preemption  ...  →  Context Switch
```
* 외부에서 강제 중단(preempt)
  > 선점이라는 말 어감에서 볼 수 있듯, 실행 중인 작업을 강제로 빼앗아 다른 작업에게 넘긴다는 의미이다.
* 외부에서 강제로 중단하기 위한 하드웨어 기능이 필요 → NVIDIA GPU에서는 Compute Preemption이라는 기능으로 구현됨
* 종류
  * Event-based Preemption: 특정 이벤트 발생 시 전환
    * 예: 높은 우선순위 작업 도착
  * Time-based Preemption: 시간 기반 주기적 전환
    * timer interrupt 사용
* 한 프로세스 커널 실행 중에도 여러 차례 context switching이 발생할 수 있음

<br>


## 동작 원리

조금 더 계층적으로 나눠서, Time Slicing이 어떻게 동작하는지 알아 보자.
* 어플리케이션 코드: GPU 커널 호출
  * GPU Kernel: GPU에서 실행되는 함수
* GPU Kernel: GPU Driver 호출
  * 단순히 작업을 정의할 뿐, 스케줄링이나 중단에 대해 전혀 모름
* GPU Driver: Time Slicing 구현 주체
  * 스케줄링 정책 결정
  * 언제 preemption할지 결정: timer 관리
  * GPU에게 명령 전송
  * context 상태 추적 및 관리
    * context: 프로세스가 GPU를 사용하기 위해 필요한 모든 상태 정보
      * Program Counter: 프로그램을 어디까지 실행헀는지
      * Register 값: 계산 중간 결과
      * 메모리 할당 상태
* GPU 하드웨어: preemption 관련 하드웨어 기능 있어야 함
  * Driver 명령 받아 실행
  * 실제로 warp 중단
    * warp: GPU가 동시에 실행하는 32개의 스레드 묶음. GPU가 한 번에 처리하는 작업 묶음 최소 단위
  * 실제로 상태 저장, 복원



<br>

### 하드웨어 수준에서의 동작 원리

그렇다면 하드웨어 수준에서 Time Slicing은 어떻게 동작하는가. 하드웨어 기능이 필요하다고 했는데, 그 하드웨어 기능은 아래와 같은 절차로 Time Slicing을 처리한다.

1. GPU scheduler가 timer interrupt 발생
2. 현재 실행 중인 warp의 상태 저장
   * Program counter
   * Register 값
   * Local memory 상태
3. 다른 context로 전환
4. 새로운 warp 실행
5. 다시 timer → 원래 warp로 복귀



<br>



## 결론

결론적으로 GPU Time Slicing은, **하나의 물리 GPU를 일정 시간 간격으로 나누어 여러 프로세스가 번갈아 가며 사용하는 기법**을 의미한다.

조금 더 기술적으로는:

* Timer 기반의 Preemptive Context Switching 기능을 활용하여
* 하나의 GPU를 시간 단위(예: 1ms)로 분할하고
* 여러 GPU 컨텍스트를 주기적으로 전환하며 실행하는 리소스 공유 방식이다.

<br>

이를 위해서는 아래와 같은 연관 개념들의 계층 구조를 명확히 이해해야 한다.

```text
Context Switching (가장 넓은 개념)
│
├─ Cooperative Context Switching: 작업이 끝나고 자발적으로 양보할 때 전환
│
└─ Preemptive Context Switching: 작업이 진행 중이더라도 강제로 중단하고 전환
      │
      ├─ Event-based Preemptive Switching: 특정 이벤트 발생 시 전환
      │
      └─ Time-based Preemptive Switching: 시간 기반 주기적 전환
         = Time Slicing
```

<br>

사실 그냥 아래 내용 정도로만 이해해 두어도 좋을 듯하다.
* **Context Switching이 발생한다고 해서, 모두 Time Slicing인 것은 아님**
* 진정한 의미에서 GPU Time Slicing 기능은 Preemptive Context Switching, 그 중에서도 Time-based Preemptive Switching을 위한 하드웨어 기능이 제공되는 GPU에서만 가능
  * NVIDIA GPU의 경우에는 이와 같은 하드웨어 기능을 Compute Preemption이라고 부르며, Pascal 아키텍처 이후의 GPU들이 해당 방식을 지원함
    * Pascal 이전: GTX 900 시리즈 등
    * Pascal 이후: GTX 10xx, RTX 시리즈, A100, H100
      > 물론 Pascal 이후 아키텍처에서도 context switching 메커니즘이 점점 발전한다고 한다.
      > - 더 빠른 context switching
      > - context switching 오버헤드 감소
      > - ...

<br>

## 한계

GPU Time Slicing을 적용했을 때 나타날 수 있는 문제점은 다음과 같다.
- Context Switching 오버헤드
- 메모리 OOM

### Context Switching 오버헤드

Time Slicing은 공짜가 아니다. 프로세스를 전환할 때마다 비용이 발생한다.
* 상태 저장/복원: 레지스터, 메모리 상태를 저장하고 다시 불러 와야 함
* 캐시 무효화: 다른 프로세스로 전환 시 L1/L2 캐시가 비워져서 성능 저하

그리고 Time slice가 짧을수록 전환이 잦아져 위에서 말한 오버헤드가 증가한다. 보통 10~20% 정도의 오버헤드가 발생한다고 하니, **Context Switching 오버헤드 < 리소스 공유의 이득**인 경우에만 유용하다.

<br>

### 메모리 OOM

Time Slicing은 GPU 메모리 오버플로우를 방지하지 않는다. CPU의 Time Slicing과 비교하면 다음과 같다.

| 구분 | CPU (OS) | GPU (Driver) |
|------|----------|--------------|
| Virtual Memory | Swap으로 버퍼링 가능 | 지원 안 함 |
| OOM 발생 시 | OOM Killer가 프로세스 종료 | 즉시 실패 반환 (예: `cudaMalloc()` 에러) |
| 보호 수준 | 시스템 차원의 보호 메커니즘 | 애플리케이션이 직접 처리 |

> 결론적으로, CPU와 GPU 모두 물리 메모리 부족 시 문제가 발생하지만, GPU는 OS 수준의 보호 없이 더 직접적으로 실패한다.



<br>

# vs. MIG

GPU를 분할하여 사용하는 방법에는 MIG와 Time Slicing이 있다고 했는데, 주요 차이점은 다음과 같다.

* Time Slicing: 소프트웨어 공유
  * GPU Driver 수준에서의 소프트웨어적 공유
  * GPU Driver 수준에서의 소프트웨어적 시분할
  * 하나의 GPU 하드웨어를 여러 프로세스가 시간을 나눠 사용
  * **Fault Isolation 제공되지 않음**
* MIG: 하드웨어 분할
  * GPU 하드웨어 자체를 하드웨어적으로 분할
  * GPU 하드웨어를 물리적으로 독립된 인스턴스로 분할
  * 각 인스턴스는 완전히 독립된 작은 GPU
  * **Fault Isolation 제공됨**

둘 사이의 가장 큰 차이점은 Fault Isolation이 제공되는가이다.

<br>

## Fault Isolation

Fault Isolation이란, 하드웨어, 시스템 설계에서 사용되는 개념으로, **한 작업의 오류가 다른 작업에 영향을 주지 않도록 격리하는 것**을 의미한다. 

<br>

프로그래밍, 소프트웨어 관점에서는, **한 프로세스나 작업이 크래시하거나 문제를 일으키더라도, 다른 프로세스나 작업이 영향을 받지 않고 계속 동작하는 것**을 의미한다.  

* fault = 오류, 장애, 비정상 동작 → 실행 중 발생하는 소프트웨어적 문제
  * Segmentation Fault: 잘못된 메모리 접근
  * Out-of-Memory: 메모리 부족으로 할당 실패
  * Infinite Loop: 무한 루프로 인한 리소스 독점
  * Divide by Zero: 0으로 나누기 오류
  * Kernel Crash: GPU 커널 실행 중 비정상 종료
* isolation = 격리, 분리

 프로그래밍 관점에서 찾아 볼 수 있는 것들은 아래와 같은 것들이 있다.

* OS 수준에서의 프로세스 격리
  * 각 프로세스는 독립적인 메모리 공간을 가지고 있어서,
  * 한 프로세스가 크래시하더라도 다른 프로세스에 영향이 없음
* 컨테이너 격리: namespace, cgroup
  * 한 컨테이너에서 OOM이 발생하더라도, 다른 컨테이너에는 영향이 없음

<br>

조금 더 하드웨어 레벨로 내려간 GPU 레벨에서의 Fault Isolation은, **물리적으로 독립적인 GPU 리소스를 제공하는 것**이라고도 볼 수 있겠다.

<br>

### MIG의 Fault Isolation

MIG는 하드웨어 수준에서 GPU를 물리적으로 분할하므로 완전한 격리를 제공한다. 따라서, 하드웨어 수준에서 Fault Isolation이 제공된다.

```text
물리 GPU (A100 80GB)
├─ MIG Instance 0 (20GB) → Process A 전용
│   독립된 메모리
│
├─ MIG Instance 1 (20GB) → Process B 전용
│   Process A와 완전 격리
│
└─ MIG Instance 2 (40GB) → Process C 전용
    다른 인스턴스 영향 없음
```

* Process A가 20GB를 모두 사용해도 → Process B의 20GB는 보호됨
* Process A의 커널이 크래시해도 → Process B는 영향 없음

<br>

## Time Slicing의 한계

Time Slicing은 같은 GPU 하드웨어와 메모리를 공유하므로, Fault Isolation을 제공하지 않는다.

```text
Process A (GPU 0 사용)  \
                         → 같은 /dev/nvidia0, 같은 메모리 공간
Process B (GPU 0 사용)  /
```

* 발생 가능한 문제
  * Process A가 GPU 메모리를 전부 할당 받으면, Process B에서 GPU OOM 발생
  * Process A의 CUDA 커널이 무한 루프에 빠지면 → Process B도 대기 또는 타임아웃
  * Process A가 잘못된 메모리 접근으로 GPU 크래시 → Process B도 영향받음

그렇기 때문에, Time Slicing을 사용할 때에는 항상 GPU 메모리로 인해 여러 프로세스가 영향을 받을 수 있음에 유의하고, OOM 에러가 발생하지 않도록 주의해야 한다.

<br>

## 여담

Fault Isolation이 보장되지 않음에도 불구하고, MIG를 지원하는 GPU를 사용할 수 없는 상황에서는 Time-Slicing 기능을 사용하는 것이 좋은 선택지가 된다. NVIDIA GPU Operator의 Time Slicing 관련 문서에서, [관련 부분](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html#comparison-time-slicing-and-multi-instance-gpu)을 발췌해 본다.

> The latest generations of NVIDIA GPUs provide an operation mode called Multi-Instance GPU(MIG). MIG allows you to partition a GPU into several smaller, predefined instances, each of which looks like a mini-GPU that provides memory and fault isolation at the hardware layer.

* 최신 세대 NVIDIA GPU는 Multi-Instance GPU(MIG) 모드를 제공한다.
* MIG를 사용하면 GPU를 미리 정의된 크기의 더 작은 인스턴스로 분할할 수 있으며,
* 각 인스턴스는 하드웨어 계층에서 메모리와 Fault Isolation을 제공하는
* 독립된 mini-GPU처럼 동작한다.

> Unlike Multi-Instance GPU(MIG), there is no memory or fault-isolation between replicas, but for some workloads this is better than not being able to share at all. Time-slicing trades the memory and fault-isolation that is provided by MIG for the ability to share a GPU by a larger number of users. Time slicing also provides a way to provide shared access to a GPU for older generation GPUs that do not support MIG.

* Time Slicing은 MIG와 달리 메모리 격리나 Fault Isolation을 제공하지 않지만,
* 일부 워크로드에서는 GPU를 전혀 공유하지 못하는 것보다 낫다.
* Time Slicing은 MIG가 제공하는 격리 기능을 희생하는 대신,
* 더 많은 사용자에게 GPU 접근을 제공할 수 있다.
* 또한 MIG를 지원하지 않는 구형 GPU에서도 공유 접근을 가능하게 한다.
