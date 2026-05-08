---
title:  "[Kubernetes] GPU Sharing: Time Slicing - 1. 개념"
excerpt: GPU Time Slicing에 대해 알아보자.
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - GPU
  - GPU Sharing
  - Time Slicing
  - NVIDIA
---



<br>

# TL;DR

- 쿠버네티스는 GPU를 **독점 자원**으로 취급하여 1 Pod = 1 GPU로 할당한다. GPU를 나눠 쓰려면 MIG(하드웨어 분할), Time Slicing(시분할), MPS(공간 분할) 등의 [GPU 공유 메커니즘]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %})이 필요하다
- Time Slicing은 하나의 물리 GPU의 **연산 자원(SM 실행 시간)**을 시간 단위로 분할하여 여러 프로세스가 번갈아 사용하는 기법이다. **GPU 메모리는 시분할되지 않으며**, 모든 프로세스의 메모리 할당이 동시에 상주한다
- GPU Driver가 Timer 기반 Preemptive Context Switching을 수행하며, 이를 위해 GPU 하드웨어의 Compute Preemption 기능(Pascal 아키텍처 이후)이 필요하다
- Time Slicing은 Fault Isolation을 제공하지 않는다. MIG 대비 격리가 약하지만, MIG 미지원 GPU에서도 사용할 수 있다는 장점이 있다

<br>

# 개요

쿠버네티스 환경에서 GPU는 특수한 자원이다. GPU는 쿠버네티스가 스케줄할 수 있는 자원이 아니라서, 사용 설정만 하려고 해도 좀 번거로운 절차가 필요하다.

* [NVIDIA Device Plugin을 이용한 배포]({% post_url 2024-07-19-Dev-Kubernetes-GPU-Setting %})
* [GPU Operator를 이용한 배포](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html)

특수하다는 것에는, 이렇게 쿠버네티스가 GPU를 스케줄 대상 자원으로 인식할 수 없다는 맥락 외에, 더 나아가, 쿠버네티스가 GPU를 **독점 자원**으로 취급한다는 의미가 담겨 있다.

독점 자원이란, **쿠버네티스에서 파드를 할당할 때 하나의 파드에 하나의 GPU만 할당한다**는 의미이다. 스케줄러가 애초에 GPU를 요청하는 여러 개의 파드를 하나의 GPU만 있는 노드에 배치해 주지 않는다는 것이다. 결과적으로 쿠버네티스 환경에서는 애초에 하나의 프로세스만 GPU를 사용하게 된다. 

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
  - 각자 GPU 할당 받기 위해 대기 → 생산성 저하
  - 만약 GPU를 분할하여 사용할 수 있다면, 10명이 GPU 3-4개를 유동적으로 공유할 수 있음


## GPU 분할 기법

그래서 쿠버네티스 환경에서 GPU를 분할하기 위한 기법은 정녕 없을까. 그렇지 않다. 대표적인 방법은 다음과 같다.

* MIG(Multi-Instance GPU): 하드웨어적 분할. GPU를 물리적으로 독립된 인스턴스로 나눠 사용
* Time Slicing: 소프트웨어적 시분할. 하나의 GPU를 여러 프로세스가 시간을 나눠 사용
* MPS(Multi-Process Service): 소프트웨어적 공간 분할. 여러 프로세스의 커널을 GPU 위에서 동시에 병렬 실행

GPU 공유 메커니즘의 전체 그림(CUDA Streams, Time Slicing, MPS, MIG, vGPU)과 각 기법의 비교는 [GPU 공유 메커니즘: 개요]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %}) 글에서 다루었다. 이 시리즈에서는 그 중 **Time Slicing**에 집중하며, **NVIDIA GPU** 기준으로 설명한다.

<br>

# GPU Time Slicing

먼저, GPU의 Time Slicing이 무엇인지 명확하게 이해해 보자.

> **참고**: 이 글에서 등장하는 SM, Warp, GPU Kernel, GPU Context 등의 GPU 실행 모델 용어와, Cooperative/Preemptive Context Switching 개념에 대해서는 [GPU 공유 메커니즘: 개요]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %}) 글을 참고하자. 이 글에서 커널이라는 용어가 반복 등장하는데, 모두 GPU Kernel(GPU에서 실행되는 함수)을 가리킨다.

GPU 실행 모델을 이해하면, 뒤에 나오는 Time Slicing의 핵심이 자연스럽게 연결된다:
- **Time Slicing이 시분할하는 것**: SM의 실행 시간 (연산 자원)
- **Preemption이 중단하는 단위**: Warp 또는 Thread Block (아키텍처에 따라 다름). SM은 항상 어떤 프로세스의 Warp를 실행하고 있는데, 시간을 나눠 쓰려면 현재 실행 중인 것을 멈추고 다른 프로세스의 Warp를 실행해야 한다. 이 "멈추는 단위"가 Preemption 단위다
- **Context Switching이 저장/복원하는 것**: GPU Context. 프로세스가 GPU를 사용하기 위한 전체 상태의 스냅샷이며, 현재 실행 중인 Warp의 레지스터, Program Counter, 메모리 할당 상태 등을 포함한다

```text
Time Slicing (목적)  "SM 실행 시간을 나눠 쓰고 싶다"
       |
       | to achieve this
       v
Preemption (수단)  "현재 실행 중인 Warp/Thread Block을 중단"
       |
       | on preemption
       v
Context Switching (동작)  "GPU Context를 저장/복원"

GPU Context = {
  Program Counter   : 각 Warp가 어디까지 실행했는지
  Register          : 각 Thread의 계산 중간 결과
  Memory Allocation : cudaMalloc으로 할당한 GPU 메모리 영역
  CUDA Stream       : 커널 실행 큐
  ...
}
```

<br>

## Time Slicing

**하나의 물리적 자원을 시간 단위로 분할하여 여러 작업이 공유**하는 기법이다. 일반적인 개념이지만, GPU 관점에서는 하나의 GPU를 여러 프로세스가 시간을 나눠 사용하는 것을 의미한다.

- 일반적인 예시:
  - CPU Time Slicing: 하나의 CPU 코어를 여러 프로세스가 시간을 나눠 사용
  - Network Time Slicing: 하나의 네트워크 채널을 시간을 나눠 사용

조금 더 엄밀하게 정의하자면, **시간 기반의 강제적 context switching**이라고 할 수 있다.

<br>

## GPU Context Switching

GPU에서 여러 프로세스가 GPU를 나눠 쓰려면, 실행 중인 Context를 전환하는 Context Switching이 필요하다. GPU Context Switching에는 두 가지 방식이 있다.

* **Cooperative Context Switching**: 현재 커널이 자발적으로 완료된 후 전환. 강제 중단 불가
* **Preemptive Context Switching**: 외부에서 강제로 중단하고 전환. NVIDIA GPU에서는 Compute Preemption이라는 하드웨어 기능으로 구현

Time Slicing은 이 중 **Preemptive Context Switching**, 그 중에서도 Timer 기반 주기적 전환(Time-based Preemption)에 해당한다. 두 방식의 상세 비교는 [GPU 공유 메커니즘: 개요]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %}#gpu-context-switching) 글을 참고하자.

<br>


## 동작 원리

조금 더 계층적으로 나눠서, Time Slicing이 어떻게 동작하는지 알아 보자.

```text
어플리케이션 코드 (CPU)
  │  CUDA API (cudaLaunchKernel 등)
  ▼
GPU Driver (CPU) ─── Time Slicing 구현 주체
  │  커널 제출(submit) 및 스케줄링
  ▼
GPU 하드웨어 ──────── Compute Preemption 하드웨어 기능
  │                    상태 저장/복원, preemption 수행
  │
  └──→ GPU Kernel ─── 하드웨어 위에서 실행되는 함수 (소프트웨어)
                       드라이버와 상호작용 없이, GPU가 직접 실행
```

* **어플리케이션 코드**: CUDA Runtime/Driver API를 통해 GPU Driver에 GPU Kernel(커널)을 **제출(submit)**
  * GPU Kernel: GPU에서 실행되는 함수. 자신이 언제 선점될지 모르며, 스케줄링이나 중단에 대해 전혀 관여하지 않음
* **GPU Driver**: Time Slicing 구현 주체
  * 커널을 GPU에 **디스패치(dispatch)** 및 스케줄링 정책 결정
  * 언제 preemption할지 결정: timer 관리
  * GPU에게 명령 전송
  * GPU Context 상태 추적 및 관리 (위 비교 테이블 참고)
* **GPU 하드웨어**: preemption 관련 하드웨어 기능 있어야 함
  * Driver 명령 받아 실행
  * 실제로 warp 중단
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
* 하나의 GPU를 GPU Driver가 설정한 time slice 간격으로 분할하고
* 여러 GPU 컨텍스트를 주기적으로 전환하며 실행하는 리소스 공유 방식이다.

> **참고**: time slice의 길이는 `nvidia-smi compute-policy --set-timeslice` 명령으로 `DEFAULT`, `SHORT`, `MEDIUM`, `LONG` 중 선택할 수 있다. 정확한 ms 값은 NVIDIA에서 공개하지 않는다.

<br>

간단하게 아래 내용 정도로만 이해해 두어도 좋을 듯하다.
* **Context Switching이 발생한다고 해서, 모두 Time Slicing인 것은 아님**. Time Slicing은 Preemptive Context Switching 중에서도 Time-based Preemption에 해당
* GPU Time Slicing은 Compute Preemption 하드웨어 기능을 제공하는 GPU에서만 가능하며, NVIDIA의 경우 Pascal 아키텍처 이후 지원
* 아키텍처별 Preemption 단위의 상세 비교는 [GPU 공유 메커니즘: 개요]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %}#preemptive-context-switching) 글을 참고하자

<br>

## 한계

GPU Time Slicing을 적용했을 때 나타날 수 있는 문제점은 다음과 같다.
- Context Switching 오버헤드
- 메모리 OOM

### Context Switching 오버헤드

Time Slicing은 공짜가 아니다. 프로세스를 전환할 때마다 비용이 발생한다.
* 상태 저장/복원: 레지스터, 메모리 상태를 저장하고 다시 불러 와야 함
* 캐시 무효화: 다른 프로세스로 전환 시 L1/L2 캐시가 비워져서 성능 저하

그리고 Time slice가 짧을수록 전환이 잦아져 위에서 말한 오버헤드가 증가한다. 워크로드에 따라 유의미한 오버헤드가 발생할 수 있으니, **Context Switching 오버헤드 < 리소스 공유의 이득**인 경우에만 유용하다.

<br>

### 메모리 OOM

Time Slicing에서 핵심적으로 이해해야 할 점은, **시분할되는 것은 연산 자원(SM 실행 시간)이지, GPU 메모리가 아니라는 것**이다. 각 프로세스의 GPU 메모리 할당은 해당 프로세스가 실행 중이 아닐 때에도 GPU 메모리에 상주한다.

```text
GPU 메모리 (24GB 기준)
┌──────────────────────────────────────────────────┐
│  Process A: cudaMalloc(8GB)  ← 항상 상주         │
│  Process B: cudaMalloc(8GB)  ← 항상 상주         │
│  Process C: cudaMalloc(8GB)  ← 항상 상주         │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  남은 메모리: 0GB → Process D는 cudaMalloc 실패  │
└──────────────────────────────────────────────────┘
          ↕ 연산(SM)만 시분할
    A 실행 → B 실행 → C 실행 → A 실행 → ...
```

즉, 3개의 프로세스가 시분할로 GPU를 나눠 쓰더라도 각각 8GB씩 총 24GB가 **동시에** GPU 메모리를 점유한다. CPU의 경우 프로세스가 swap out되면 메모리도 디스크로 내려갈 수 있지만, GPU에는 그런 메커니즘이 없다.

| 구분 | CPU (OS) | GPU (Driver) |
|------|----------|--------------|
| 메모리 시분할 | 가능 (Virtual Memory + Swap) | **불가** — 모든 프로세스의 할당이 동시에 상주 |
| OOM 발생 시 | OOM Killer가 프로세스 종료 | 즉시 실패 반환 (예: `cudaMalloc()` 에러) |
| 보호 수준 | 시스템 차원의 보호 메커니즘 | 애플리케이션이 직접 처리 |

> 결론적으로, Time Slicing은 **연산은 나눠 쓰되, 메모리는 나눠 쓰지 않는다**. GPU에는 OS 수준의 Virtual Memory 보호가 없으므로, 각 프로세스의 GPU 메모리 사용량 합계가 물리 메모리를 초과하지 않도록 직접 관리해야 한다.



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

<br>

# 정리

이 글에서는 GPU Time Slicing의 개념적 기반을 살펴보았다.

| 항목 | 내용 |
|------|------|
| **Time Slicing이란** | 하나의 물리 GPU의 SM 실행 시간을 여러 프로세스가 번갈아 사용하는 기법 |
| **핵심 메커니즘** | GPU Driver의 Timer 기반 Preemptive Context Switching |
| **하드웨어 요구사항** | Compute Preemption 지원 GPU (NVIDIA Pascal 아키텍처 이후) |
| **시분할 대상** | 연산 자원(SM)만 시분할. GPU 메모리는 시분할되지 않음 |
| **한계** | Context Switching 오버헤드, 메모리 OOM 위험, Fault Isolation 미제공 |
| **vs. MIG** | MIG는 하드웨어 분할로 완전한 격리 제공. Time Slicing은 격리를 희생하고 더 넓은 GPU 호환성과 유연성 확보 |

[다음 글]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-2 %})에서는 이 개념이 쿠버네티스 환경에서 어떻게 동작하는지, 그리고 Time Slicing ConfigMap을 어떻게 구성하는지 알아본다.

<br>
