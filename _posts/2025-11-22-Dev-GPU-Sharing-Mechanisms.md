---
title:  "[GPU] GPU 공유 메커니즘: 개요"
excerpt: GPU를 여러 워크로드가 나눠 쓰는 방법을 알아보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - GPU Sharing
  - CUDA
  - NVIDIA
  - MPS
  - MIG
  - Time Slicing
---



<br>

# TL;DR

- GPU는 원래 하나의 프로세스가 독점하는 구조다. 여러 워크로드가 GPU를 나눠 쓰려면 별도의 공유 메커니즘이 필요하다
- GPU 공유 메커니즘은 크게 5가지: **CUDA Streams**(단일 프로세스 내 병렬화), **Time Slicing**(시간 축 공유), **MPS**(공간 축 공유), **MIG**(하드웨어 파티셔닝), **vGPU**(가상화)
- Time Slicing은 한 시점에 하나의 Context만 실행(시분할), MPS는 여러 프로세스의 커널을 **동시에** 병렬 실행(공간 분할)
- MIG만이 완전한 하드웨어 수준의 메모리 격리와 Fault Isolation을 제공한다

<br>

# GPU 실행 모델

GPU 공유 메커니즘을 이해하려면, 먼저 GPU가 작업을 실행하는 방식을 알아야 한다.

> 이 글에서 다루는 실행 모델 용어(SM, Warp, CUDA Context 등)와 공유 메커니즘(Time Slicing, MPS, MIG 등)은 **NVIDIA GPU와 CUDA 플랫폼 기준**이다. GPU 공유라는 개념 자체는 벤더 공통이지만, 구체적인 구현과 이름은 벤더마다 다르다. 다른 벤더의 대응 개념은 이 글 마지막의 [다른 GPU 벤더의 대응 기술](#다른-gpu-벤더의-대응-기술) 섹션을 참고하자.

<br>

## CPU와의 비교

CPU는 소수의 강력한 코어가 순차적 작업을 빠르게 처리하는 구조인 반면, GPU는 수천 개의 작은 코어가 동일한 작업을 대량으로 병렬 처리하는 구조다.

> 위에서 언급했듯이, 아래 표의 용어들(CUDA Thread, GPU Kernel 등)은 NVIDIA CUDA 플랫폼에서 정의한 것이다. PyTorch·TensorFlow 같은 AI 프레임워크도 내부적으로 CUDA를 통해 GPU 연산을 수행한다.

| CPU | GPU | 설명 |
|-----|-----|------|
| Core | **SM** (Streaming Multiprocessor) | 실행 유닛. CPU 코어 하나에 대응하는 GPU의 연산 블록. GPU 하나에 수십~백여 개의 SM이 있음 |
| Thread | **CUDA Thread** | 최소 실행 단위 |
| *(해당 없음)* | **Warp** (32 threads) | GPU 스케줄링의 최소 단위. SM이 한 번에 실행하는 32개 스레드 묶음 |
| *(해당 없음)* | **Thread Block** | 같은 SM에 배치되는 스레드 그룹. Block 내 스레드끼리 메모리 공유 가능 |
| 함수 호출 | **GPU Kernel** | GPU에서 실행되는 함수. 수천 개의 스레드가 동시에 같은 커널을 실행 |
| 프로세스 context | **GPU Context** | 프로세스가 GPU를 사용하기 위한 모든 상태 (레지스터, 메모리 할당, Program Counter 등) |

> **참고**: GPU Kernel은 OS Kernel(운영체제 핵심)과 전혀 다른 개념이다. GPU 문맥에서 커널은 단순히 "GPU에 제출하는 함수 하나"를 의미한다.


```text
CPU                                 GPU
┌──────────────────┐                ┌──────────────────────────────────────────────┐
│ ┌──────┐┌──────┐ │                │  SM 0              SM 1             ... SM N │
│ │Core 0││Core 1│ │                │  ┌──────────────┐  ┌──────────────┐          │
│ └──────┘└──────┘ │                │  │ Thread Blk   │  │ Thread Blk   │          │
│ ┌──────┐┌──────┐ │                │  │ ┌────┐┌────┐ │  │ ┌────┐┌────┐ │          │
│ │Core 2││Core 3│ │                │  │ │Warp││Warp│ │  │ │Warp││Warp│ │          │
│ └──────┘└──────┘ │                │  │ │32t ││32t │ │  │ │32t ││32t │ │          │
│ ┌──────┐┌──────┐ │                │  │ └────┘└────┘ │  │ └────┘└────┘ │          │
│ │Core 4││ ...  │ │                │  ├──────────────┤  ├──────────────┤          │
│ └──────┘└──────┘ │                │  │ Thread Blk   │  │ Thread Blk   │          │
│                  │                │  │ ┌────┐┌────┐ │  │ ┌────┐┌────┐ │          │
│                  │                │  │ │Warp││Warp│ │  │ │Warp││Warp│ │          │
│                  │                │  │ └────┘└────┘ │  │ └────┘└────┘ │          │
│                  │                │  └──────────────┘  └──────────────┘          │
└──────────────────┘                └──────────────────────────────────────────────┘
```

CPU Core와 GPU SM은 둘 다 독립적인 실행 유닛이지만, CPU Core는 소수(4~64개)이고 GPU SM은 수십~백여 개로 훨씬 많다. 각 Core가 독립적으로 스레드를 실행하듯, 각 SM도 독립적으로 Thread Block을 실행한다. GPU 쪽은 SM 안에 더 깊은 계층 구조가 있다: GPU → SM → Thread Block → Warp(32 threads).

<br>

## CUDA 소프트웨어 모델

위 표의 SM, Warp, Thread Block은 GPU **하드웨어**의 물리적 구조다. 그런데 GPU 공유 메커니즘을 이해하려면, 하드웨어 구조만으로는 부족하다. "여러 프로세스가 GPU를 어떻게 나눠 쓰는가"는 결국 **소프트웨어가 하드웨어 자원을 어떻게 추상화하고 관리하는가**의 문제이기 때문이다. CUDA 플랫폼은 이를 위해 **CUDA Context**와 **CUDA Stream**이라는 소프트웨어 추상화를 제공한다. 이 둘이 하드웨어와 어떻게 다른지, 그리고 하드웨어 위에서 어떤 역할을 하는지 이해하는 것이 이후의 공유 메커니즘(Time Slicing, MPS, MIG 등)을 구분하는 핵심이다.

| 개념 | 계층 | 설명 |
|------|------|------|
| SM, Warp, Thread Block | **하드웨어** | GPU 칩에 물리적으로 존재하는 실행 유닛과 스케줄링 단위 |
| CUDA Context | **소프트웨어** (드라이버 수준) | 프로세스가 GPU를 사용하기 위한 상태 묶음. 드라이버가 관리 |
| CUDA Stream | **소프트웨어** (런타임 수준) | Context 안의 작업 큐. 런타임이 관리 |

<br>

### CUDA Context

CUDA Context는 CPU의 프로세스 주소 공간(process address space)에 대응하는 개념이다. 하나의 프로세스가 GPU를 사용하기 위해 필요한 **모든 소프트웨어 상태**를 묶어서 관리하는 단위다.

Context가 포함하는 상태:
* GPU 메모리 할당 테이블 (어떤 가상 주소가 어떤 물리 VRAM에 매핑되는지)
* 로드된 GPU 모듈(커널 코드)
* SM 레지스터 상태, Program Counter
* Stream, Event 등의 동기화 객체

GPU 하드웨어에 "Context 레지스터"라는 전용 회로가 있는 것이 아니다. CUDA 드라이버가 이 상태들을 소프트웨어 자료구조로 관리하고, GPU에 작업을 제출할 때 해당 상태를 하드웨어에 올린다. Context Switch가 발생하면 현재 SM의 레지스터, Program Counter 등을 메모리에 저장하고, 다음 Context의 상태를 복원하는 과정이 수반되므로 하드웨어와 밀접하게 연동된다. Context Switch 시 실제로 어떤 상태가 저장/복원되는지, 그리고 이것이 Time Slicing에서 어떤 의미를 갖는지는 [GPU Sharing: Time Slicing - 1. 개념]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %}#gpu-time-slicing) 글에서 상세히 다룬다.

> **비유**: OS 커널이 관리하는 `task_struct`(프로세스 디스크립터)가 CPU 하드웨어에 물리적으로 존재하지 않듯, CUDA Context도 드라이버가 관리하는 소프트웨어 구조체다. 다만 context switch 시 하드웨어 레지스터 저장/복원이 동반된다는 점은 CPU의 프로세스 context switch와 동일하다.

기본적으로 **프로세스 하나 = CUDA Context 하나**다. CUDA Runtime API를 사용하면 프로세스당 하나의 Context가 자동 생성된다. CUDA Driver API를 사용하면 하나의 프로세스에서 여러 Context를 명시적으로 생성할 수도 있지만, 일반적인 사용 패턴은 아니다.

<br>

### CUDA Stream

CUDA Stream은 하나의 Context 안에서 GPU에 작업을 제출하는 **큐(queue)**다.

```text
Process
└─ CUDA Context
   ├─ Stream 0 (default): [Kernel A] → [Kernel B] → [Kernel C] → ...
   ├─ Stream 1:           [Kernel D] → [Kernel E] → ...
   └─ Stream 2:           [Kernel F] → [memcpy H→D] → [Kernel G] → ...
```

* 같은 Stream 안의 작업은 **FIFO 순서 보장**: Kernel A가 끝나야 Kernel B가 실행된다
* 서로 다른 Stream 간에는 **순서 보장 없음**: Stream 0의 Kernel A와 Stream 1의 Kernel D는 동시에 실행될 수 있다
* GPU 하드웨어 스케줄러는 **Stream이라는 개념을 모른다**. 하드웨어가 보는 것은 "제출된 커널들"이다. CUDA 드라이버/런타임이 Stream 간의 의존성 그래프를 해석한 뒤, 실행 가능한 커널을 하드웨어에 제출하면 SM 스케줄러가 가용 SM에 배치한다

Stream을 통한 병렬 실행이 실제로 동시에 이루어지려면, 각 커널이 GPU의 모든 SM을 점유하지 않을 만큼 작아야 한다. 하나의 커널이 GPU 전체를 꽉 채우면 다른 Stream의 커널은 대기할 수밖에 없다.

<br>

### GPU 메모리 계층과 가상 주소 공간

GPU 메모리는 계층 구조를 가진다.

| 메모리 종류 | 위치 | 범위 | 용도 |
|------------|------|------|------|
| **글로벌 메모리** (= VRAM) | GPU 보드의 DRAM | Context 전체 | `cudaMalloc`으로 할당. 모든 스레드에서 접근 가능 |
| **공유 메모리** (Shared Memory) | SM 내부 SRAM | Thread Block 내 | Block 내 스레드 간 데이터 공유. 매우 빠름 |
| **레지스터** | SM 내부 | 스레드별 | 개별 스레드의 지역 변수 |

CUDA Context가 **글로벌 메모리의 할당/해제를 관리**한다. `cudaMalloc`, `cudaFree` 등의 호출은 현재 활성 Context의 메모리 할당 테이블을 변경한다.

#### GPU 가상 주소 공간 (GPU VA)

Pascal 아키텍처 이후 NVIDIA GPU는 **GPU MMU**(Memory Management Unit)를 내장하여, GPU 커널이 사용하는 가상 주소를 물리 VRAM 주소로 변환한다. CPU의 가상 메모리 시스템과 유사한 구조다.

| | CPU 가상 메모리 | GPU 가상 주소 (GPU VA) |
|---|---|---|
| 주소 변환 | CPU MMU + Page Table | **GPU MMU** + GPU Page Table |
| 관리 주체 | OS 커널 | **CUDA 드라이버** |
| Swap | 있음 (디스크로 페이지 아웃) | **없음** |
| Overcommit | 지원 (커널 설정) | **미지원** |
| 프로세스 간 격리 | Page Table 분리로 완전 격리 | MIG 없이는 제한적 |

GPU에도 가상 주소 → 물리 주소 매핑이 존재하지만, CPU의 가상 메모리와 결정적으로 다른 점은 **swap이 없고, overcommit도 없다**는 것이다. 물리 VRAM이 부족하면 `cudaMalloc`이 즉시 실패한다. OS의 보호를 받는 CPU 메모리와 달리, GPU 메모리는 CUDA 드라이버가 직접 관리하므로 안전장치가 제한적이다.

> **참고**: VRAM(Video RAM)은 GPU 보드에 물리적으로 장착된 DRAM 칩이다. "가상 메모리"가 아니라 GPU의 **물리 메모리**에 해당한다. GPU VA는 이 물리 VRAM 위에 주소 변환 계층을 올린 것이다. CPU에서 물리 RAM + 가상 주소 공간이 분리되듯, GPU에서도 물리 VRAM + GPU VA가 분리된다.

> **참고**: NVIDIA의 Unified Memory(`cudaMallocManaged`)는 CPU RAM↔GPU VRAM 간 자동 마이그레이션을 지원한다. CPU의 swap과 유사해 보이지만, 이는 CPU RAM을 fallback 저장소로 사용하는 것이며 GPU VRAM 자체에 swap이 생기는 것이 아니다. 성능 저하가 크기 때문에 VRAM 부족의 근본 해결책으로 사용되지 않는다.

<br>

## GPU Context Switching

CPU에서 OS 스케줄러가 프로세스를 번갈아 실행하듯, GPU에서도 여러 CUDA Context가 GPU를 나눠 쓰려면 Context Switching이 필요하다. GPU Context Switching에는 두 가지 방식이 있다.

<br>

### Cooperative Context Switching

```text
Time: 0s ────────────────────────────────────────────────→   60s
Process A: |══════════════════════|                         (30초)
Process B:                        |══════════════════════|  (30초)
           ↑                      ↑
        시작                Context Switch (A 완료 후)
```

* 현재 실행 중인 커널이 **자발적으로 완료**되어야 다음 Context로 전환
* 강제 중단 불가: 하나의 커널이 오래 걸리면 다른 프로세스는 그만큼 대기
* GPU의 전통적인 동작 방식

<br>

### Preemptive Context Switching

```text
Time: 0s ────────────────────────────────────────────→ 60s
Process A: |███|   |███|   |███|   |███|   |███|    ...
Process B:     |███|   |███|   |███|   |███|   |███|
           ↑   ↑   ↑   ↑
           시작   preemption  ...  →  Context Switch
```

* 외부에서 **강제로 중단**(preempt): 실행 중인 작업을 빼앗아 다른 작업에게 넘김
* GPU 하드웨어의 **Compute Preemption** 기능이 필요
* 종류
  * Event-based Preemption: 특정 이벤트(높은 우선순위 작업 도착 등) 발생 시 전환
  * Time-based Preemption: 시간 기반 주기적 전환 (timer interrupt 사용)
* NVIDIA GPU 아키텍처별 Preemption 단위
  * Pascal 이전 (Maxwell 등: GTX 900 시리즈): **Thread Block 단위** preemption만 가능. 현재 실행 중인 thread block이 완료될 때까지 기다린 후 전환하므로 지연이 큼. 사실상 cooperative에 가까운 동작
  * Pascal 이후 (GTX 10xx, RTX 시리즈, A100, H100): **Instruction 단위** preemption 지원. 실행 중인 명령어(instruction) 수준에서 중단 가능하여 지연이 작음

<br>

# GPU 공유 메커니즘

GPU를 여러 워크로드가 나눠 쓸 수 있는 메커니즘을 하나씩 알아보자. NVIDIA 공식 블로그 [Improving GPU Utilization in Kubernetes](https://developer.nvidia.com/blog/improving-gpu-utilization-in-kubernetes)에서 정리한 5가지 메커니즘을 기준으로 한다. 참고 자료 제목에 "in Kubernetes"가 붙어 있지만, 아래에서 다루는 5가지 메커니즘은 NVIDIA GPU 드라이버·하드웨어 수준의 기능으로 **쿠버네티스 환경에 종속되지 않는다**. bare-metal 리눅스에서도 동일하게 동작하며, 쿠버네티스에서는 Device Plugin이나 GPU Operator를 통해 이 메커니즘들을 Pod 단위로 설정·적용하는 것일 뿐이다.

아래에서는 소프트웨어 수준(프로그래밍 모델) → 드라이버 수준 → 하드웨어 수준 → 가상화 순으로, **격리 강도가 약한 것부터 강한 것** 순서로 설명한다.

<br>

## CUDA Streams

**단일 프로세스 내**에서 여러 작업을 병렬로 실행하는 프로그래밍 모델 수준의 기법이다.

```text
하나의 CUDA Context (단일 프로세스) 안에서:

Stream 1: [Kernel A] ──────→ [Kernel C] ──────→
Stream 2:    [Kernel B] ──────→ [Kernel D] ──→
                ↑
         서로 다른 Stream의 커널은 동시에 실행 가능
```

* 하나의 프로세스가 여러 CUDA Stream을 생성하여 커널을 병렬 실행
* 같은 Stream 내의 작업은 순차적이지만, 서로 다른 Stream 간의 작업은 동시에 실행 가능
* 애플리케이션 코드 레벨에서 직접 관리해야 하며, 프로세스 간 공유 기법은 아님

<br>

## Time Slicing

**하나의 물리 GPU를 시간 단위로 분할**하여 여러 프로세스가 번갈아 사용하는 기법이다. 한 시점에 GPU의 SM을 사용하는 것은 **하나의 Context뿐**이다.

```text
Time ──────────────────────────────────→

SM 전체: [Context A][Context B][Context A][Context B]...
         ←─ 1 slice ─→
         A가 쓸 때 B는 대기, B가 쓸 때 A는 대기
```

* GPU Driver가 Timer 기반 Preemptive Context Switching을 수행
* GPU 하드웨어의 Compute Preemption 기능(Pascal 아키텍처 이후)이 필요
* **GPU 메모리는 시분할되지 않는다**. 모든 프로세스의 메모리 할당이 동시에 상주하므로, 메모리 사용량 합계가 물리 메모리를 초과하지 않도록 직접 관리해야 한다
* Fault Isolation 미제공

> **참고: CPU 메모리 관리와의 차이**
>
> "메모리를 직접 관리해야 한다"는 점이 왜 강조할 만한가? CPU 프로그래밍에서도 OOM(Out of Memory)은 발생하지만, CPU 쪽에는 OS가 제공하는 여러 겹의 안전장치가 있기 때문이다.
>
> **CPU 메모리**: OS 커널이 가상 메모리(MMU + Page Table)로 프로세스 간 메모리를 보호한다. 물리 메모리가 부족하면 swap(디스크로 페이지 아웃) → OOM Killer 순서로 단계적 안전장치가 작동한다. CPU 프로그래밍에서 보는 OOM은 이 모든 보호 메커니즘을 거친 **후에** 발생하는 최후의 사건이다. 가상 메모리, 오버커밋, swap, OOM의 상세 동작은 [메모리, 페이지, 스왑]({% post_url 2026-01-23-CS-Memory-Page-Swap %}) 글을 참고하자.
>
> **GPU 메모리**: GPU 메모리는 **OS의 메모리 관리 범위 밖**에 있다. GPU 메모리의 할당과 해제는 OS 커널이 아니라 **CUDA 드라이버**가 담당하며, swap이 없다. 따라서 물리 VRAM 한계 = hard limit이고, `cudaMalloc` 실패 = 즉시 에러다. OS가 CPU 메모리에 제공하는 가상 주소 공간 격리, swap, overcommit 같은 안전장치가 GPU 메모리에는 존재하지 않는다.
>
> GPU에도 [GPU MMU를 통한 가상 주소 공간(GPU VA)](#gpu-메모리-계층과-가상-주소-공간)이 있지만, CPU의 가상 메모리 시스템과 달리 swap/overcommit이 없고, 다중 Context 간 페이지 테이블 격리가 MIG 없이는 제한적이다.
>
> 핵심은 GPU가 OS의 관리를 벗어나 드라이버 수준에서 모든 것을 처리하는 장치이기 때문에, CPU 측에서 OS가 해주는 단계적 보호를 기대할 수 없다는 점이다. Time Slicing에서 여러 Context의 메모리가 동시에 VRAM에 상주하므로, **사용량 합계가 물리 VRAM을 넘지 않도록 운영자가 직접 계산하고 제한해야 한다**. 구체적인 OOM 시나리오와 CPU/GPU 비교는 [GPU Sharing: Time Slicing - 1. 개념]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %}#메모리-oom) 글에서 더 자세히 다룬다.

> Time Slicing의 상세 개념, 쿠버네티스 환경에서의 설정과 적용은 GPU Sharing: Time Slicing 시리즈([1. 개념]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %}), [2. 설정]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-2 %}), [3. 적용]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-3 %}))에서 다룬다.

<br>

## MPS (Multi-Process Service)

**여러 프로세스의 CUDA 커널을 동시에 GPU 위에서 병렬 실행**하는 기법이다. Time Slicing이 시간 축으로 나눠 쓴다면, MPS는 **공간 축**으로 나눠 쓴다.

```text
[Time Slicing]
시간: ──────────────────────────────→
SM 전체: [A 독점][B 독점][A 독점][B 독점]
         한 시점에 하나만 실행

[MPS]
시간: ──────────────────────────────→
SM 0~3:  [A의 커널][A의 커널][A의 커널]...
SM 4~7:  [B의 커널][B의 커널][B의 커널]...
         같은 시점에 둘 다 실행
```

MPS의 핵심 구조는 다음과 같다.

```text
Process A ──┐
            ├──→ MPS Server ──→ 단일 공유 CUDA Context ──→ GPU
Process B ──┘
```

* MPS Server라는 데몬이 여러 클라이언트 프로세스의 CUDA Context를 **하나의 공유 CUDA Context**로 합침
* GPU 입장에서는 하나의 Context에서 여러 커널이 들어오는 것으로 인식하므로, SM 스케줄러가 서로 다른 프로세스의 커널을 **동시에 다른 SM에 배치** 가능
* Context Switching이 발생하지 않으므로 전환 오버헤드가 없음
* 리소스 제어 기능 (CUDA 11.4+)
  * `CUDA_MPS_ACTIVE_THREAD_PERCENTAGE`: SM 사용률 상한 설정 (예: 50%이면 전체 SM의 절반만 사용)
  * `CUDA_MPS_PINNED_DEVICE_MEM_LIMIT`: GPU 메모리 할당 상한 설정
* Fault Isolation 미제공. 오히려 Time Slicing보다 약함: 하나의 CUDA Context를 공유하므로, 한 프로세스의 크래시가 같은 MPS Server를 사용하는 **모든 프로세스**에 영향

> **참고: MPS 사용***
>
> MPS를 사용하려면 MPS Control Daemon이 실제로 별도의 데몬 프로세스로 떠 있어야 한다. `nvidia-cuda-mps-control`이 Control Daemon이고, 클라이언트가 CUDA 호출을 하면 자동으로 `nvidia-cuda-mps-server` 프로세스가 생성된다. Control Daemon이 떠 있지 않으면 MPS가 동작하지 않고, 일반적인 Time Slicing 방식으로 fallback된다.
>
> ```bash
> # MPS Control Daemon 시작
> nvidia-cuda-mps-control -d
>
> # MPS Server 상태 확인
> echo get_server_list | nvidia-cuda-mps-control
>
> # 프로세스로도 확인 가능
> ps aux | grep mps
> ```
>
> Kubernetes 환경에서는 [NVIDIA Device Plugin]({% post_url 2024-07-23-Dev-Kubernetes-NVIDIA-GPU-Mechanism %})이 MPS 모드로 설정되면 Pod 안에서 Control Daemon을 자동으로 띄워 주므로 수동 관리가 필요 없다.

<br>

## MIG (Multi-Instance GPU)

**GPU 하드웨어 자체를 물리적으로 분할**하여 독립된 인스턴스로 나누는 기법이다. Ampere 아키텍처(A100) 이후 지원된다.

```text
물리 GPU (A100 80GB)
├─ MIG Instance 0 (1g.10gb): SM 14개, 메모리 10GB → Process A 전용
├─ MIG Instance 1 (1g.10gb): SM 14개, 메모리 10GB → Process B 전용
└─ MIG Instance 2 (5g.40gb): SM 70개, 메모리 40GB → Process C 전용
    각 인스턴스가 독립된 SM, L2 캐시, 메모리 컨트롤러를 가짐
```

* 각 인스턴스는 **독립된 SM, L2 캐시, 메모리 컨트롤러**를 가진 mini-GPU처럼 동작
* **유일하게 하드웨어 수준의 메모리 격리와 Fault Isolation을 제공**
* 최대 7개 인스턴스로 분할 가능 (미리 정의된 프로파일 조합)
* 분할 구성 변경 시 GPU idle 상태 필요 (동적 변경 불가)
* MIG 인스턴스 위에 Time Slicing이나 MPS를 추가 적용할 수도 있음

<br>

## vGPU (Virtual GPU)

**NVIDIA vGPU**(정식 명칭: NVIDIA Virtual GPU Software, 구 GRID)를 통해 가상 머신 환경에서 GPU를 공유하는 기법이다.

* 하이퍼바이저(VMware vSphere, KVM/QEMU, Citrix 등) 수준에서 GPU를 분할하여 여러 VM에 할당
* IOMMU 보호를 통한 VM 간 격리 제공
* 각 VM에는 가상 GPU 디바이스가 노출되어, 게스트 OS에서 전용 GPU가 있는 것처럼 보임
* Live Migration 등 VM 관리 기능과 연동 가능
* **별도의 유료 vGPU 라이선스**가 필요 (하드웨어 기능이 아닌 소프트웨어 제품)

bare-metal이나 컨테이너 기반 쿠버네티스 환경에서는 사용 빈도가 낮으므로, 이 글에서는 간단히 언급만 하고 넘어간다.

<br>

### MIG와 vGPU의 차이

MIG와 vGPU는 둘 다 "GPU를 나눠 쓴다"는 점은 같지만, **분할이 일어나는 계층**이 근본적으로 다르다.

| | MIG | vGPU |
|---|---|---|
| **분할 계층** | GPU 하드웨어 내부 | 하이퍼바이저 |
| **격리 메커니즘** | SM/L2/메모리 컨트롤러 물리 분리 | IOMMU + 하이퍼바이저 시분할 |
| **라이선스** | 불필요 (GPU 하드웨어 기능) | **유료 라이선스 필요** |
| **사용 환경** | bare-metal, 컨테이너, VM 모두 | **VM 환경 필수** |
| **지원 GPU** | Ampere 이후 (A100, A30, H100, H200) | vGPU 지원 GPU (Tesla, Quadro/RTX 계열) |
| **최대 인스턴스** | 7개 (GPU 모델별 프로파일) | GPU 메모리에 따라 가변 |
| **동적 변경** | GPU idle 상태 필요 | VM 할당/해제로 유연 |
| **주요 용도** | 멀티테넌트 추론, 격리가 필요한 프로덕션 | VDI(Virtual Desktop), VM 기반 멀티테넌시 |

**조합 사용**: MIG 위에 vGPU를 결합할 수도 있다. 예를 들어 A100을 MIG로 7개 인스턴스로 나눈 뒤, 각 MIG 인스턴스를 vGPU를 통해 다른 VM에 할당하면 하드웨어 격리 + VM 격리를 동시에 얻는다.

<br>

# 비교

| 항목 | CUDA Streams | Time Slicing | MPS | MIG | vGPU |
|------|-------------|-------------|-----|-----|------|
| **파티션 유형** | 단일 프로세스 | 시간 분할 (temporal) | 공간 분할 (spatial) | 물리 분할 (physical) | 시간+물리 분할 (VM) |
| **동시 실행** | 가능 (같은 프로세스) | 불가 (한 시점에 하나) | **가능** (다른 프로세스) | **가능** (독립 인스턴스) | 가능 (MIG 지원 GPU) |
| **SM 성능 격리** | 없음 | 있음 (시간 기반) | 있음 (퍼센티지 지정) | **있음** (물리 분리) | 있음 |
| **메모리 보호** | 없음 | **없음** | 있음 (상한 설정) | **있음** (물리 분리) | 있음 |
| **Fault Isolation** | 없음 | 없음 | 없음 | **있음** | 있음 |
| **최대 파티션 수** | 제한 없음 | 제한 없음 | 48 | 7 | 가변 |
| **지원 GPU** | 전체 | Pascal 이후 | Volta 이후 | Ampere 이후 (A100, A30, H100, H200) | 별도 라이선스 |
| **적합 워크로드** | 단일 앱 내 병렬화 | 간헐적/burst 워크로드, 지연 허용 가능한 공유 | GPU를 조금씩 꾸준히 쓰는 MPI/HPC, 추론 서빙 | 강한 격리가 필요한 멀티테넌트, 프로덕션 추론 | VM 기반 멀티테넌시 |

> 위 비교표는 NVIDIA 공식 블로그 [Improving GPU Utilization in Kubernetes](https://developer.nvidia.com/blog/improving-gpu-utilization-in-kubernetes)의 Table 1을 기반으로 재구성한 것이다.

<br>

## 선택 기준

어떤 메커니즘을 선택할지는 **격리 요구 수준**과 **GPU 하드웨어**에 따라 달라진다.

```text
GPU 하드웨어가 MIG를 지원하는가?
├─ Yes → 격리가 필요한가?
│        ├─ Yes → MIG (+ 필요시 MIG 인스턴스 위에 Time Slicing/MPS)
│        └─ No  → MPS (동시 실행으로 활용률 극대화) 또는 Time Slicing
└─ No  → MPS (Volta 이후) 또는 Time Slicing (Pascal 이후)
```

* **격리가 중요한 프로덕션 워크로드**: MIG
* **GPU 활용률 극대화가 목표** (각 프로세스가 GPU를 조금씩만 사용): MPS
* **간단한 공유** (개발/테스트, 간헐적 추론 등): Time Slicing
* **VM 기반 멀티테넌시**: vGPU

<br>

# 정리

| 메커니즘 | 핵심 | 격리 | 격리 수준 | 동작 계층 |
|----------|------|------|-----------|-----------|
| CUDA Streams | 단일 프로세스 내 병렬화 | 없음 | — | 소프트웨어 (프로그래밍 모델) |
| Time Slicing | 시간 축 공유. 한 시점에 하나만 실행 | 없음 | 없음 | 드라이버 |
| MPS | 공간 축 공유. 여러 프로세스 커널이 동시에 실행 | 제한적 | SM/메모리 상한 | 드라이버 + 데몬 |
| MIG | 하드웨어 물리 분할. 독립된 mini-GPU | **완전** | SM/L2/메모리 물리 분리 | 하드웨어 |
| vGPU | 가상화. VM 단위 격리 | 있음 | IOMMU + VM 격리 | 하이퍼바이저 |

GPU 공유 메커니즘의 전체 그림을 잡았으니, 각 기법의 상세 내용은 이후 개별 글에서 다루면 된다.

* GPU Sharing: Time Slicing 시리즈: [1. 개념]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %}), [2. 설정]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-2 %}), [3. 적용]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-3 %})

<br>

# 다른 GPU 벤더의 대응 기술

이 글에서 다룬 메커니즘은 NVIDIA GPU 기준이지만, "시분할 공유", "하드웨어 파티셔닝", "가상화" 같은 개념 자체는 벤더 공통이다. 참고로, 다른 GPU 벤더에서 대응하는 기술은 다음과 같다.

| 개념 | NVIDIA | AMD | Intel |
|------|--------|-----|-------|
| 프로세스 내 병렬 스트림 | CUDA Streams | HIP Streams | SYCL / Level Zero Queues |
| 시분할 공유 | Time Slicing (Compute Preemption) | 드라이버 수준 context switching (명시적 API 없음) | 별도 명시적 메커니즘 없음 |
| 다중 프로세스 병렬 실행 | MPS (Multi-Process Service) | 대응 없음 | 대응 없음 |
| 하드웨어 파티셔닝 | MIG (Multi-Instance GPU) | 대응 없음 | SR-IOV 기반 GPU 파티셔닝 (Flex/Max 시리즈) |
| 가상화 | NVIDIA vGPU | AMD MxGPU (SR-IOV) | Intel GVT-g / SR-IOV |

현재 GPU 공유 메커니즘이 가장 체계적으로 정리되어 있는 것은 NVIDIA 생태계이며, 쿠버네티스 환경에서의 GPU 공유 관련 문서와 도구도 NVIDIA가 가장 풍부하다.

<br>

# 참고

* [Improving GPU Utilization in Kubernetes - NVIDIA Technical Blog](https://developer.nvidia.com/blog/improving-gpu-utilization-in-kubernetes)
* [NVIDIA Multi-Process Service (MPS) Documentation](https://docs.nvidia.com/deploy/mps/index.html) — MPS Control Daemon(`nvidia-cuda-mps-control`) 시작/종료, MPS Server 상태 확인(`echo get_server_list | nvidia-cuda-mps-control`) 등 운영 방법도 포함
* [NVIDIA GPU Operator - Time Slicing GPUs in Kubernetes](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html)
* [NVIDIA MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/)

<br>
