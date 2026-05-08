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

GPU를 여러 워크로드가 나눠 쓸 수 있는 메커니즘을 하나씩 알아보자. NVIDIA 공식 블로그 [Improving GPU Utilization in Kubernetes](https://developer.nvidia.com/blog/improving-gpu-utilization-in-kubernetes)에서 정리한 5가지 메커니즘을 기준으로 한다.

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

> Time Slicing의 상세 개념, 쿠버네티스 환경에서의 설정과 적용은 [GPU Sharing: Time Slicing 시리즈]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %})에서 다루었다.

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

> **참고**: MPS를 사용하려면 MPS Control Daemon이 실제로 별도의 데몬 프로세스로 떠 있어야 한다. `nvidia-cuda-mps-control`이 Control Daemon이고, 클라이언트가 CUDA 호출을 하면 자동으로 `nvidia-cuda-mps-server` 프로세스가 생성된다. Control Daemon이 떠 있지 않으면 MPS가 동작하지 않고, 일반적인 Time Slicing 방식으로 fallback된다.
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

**NVIDIA vGPU**를 통해 가상 머신 환경에서 GPU를 공유하는 기법이다.

* 하이퍼바이저 수준에서 GPU를 분할하여 여러 VM에 할당
* IOMMU 보호를 통한 VM 간 격리 제공
* Live Migration 등 VM 관리 기능과 연동 가능
* 별도의 vGPU 라이선스가 필요

bare-metal이나 컨테이너 기반 쿠버네티스 환경에서는 사용 빈도가 낮으므로, 이 글에서는 간단히 언급만 하고 넘어간다.

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

| 메커니즘 | 핵심 | 격리 |
|----------|------|------|
| CUDA Streams | 단일 프로세스 내 병렬화 | 없음 |
| Time Slicing | 시간 축 공유. 한 시점에 하나만 실행 | 없음 |
| MPS | 공간 축 공유. 여러 프로세스 커널이 동시에 실행 | 제한적 |
| MIG | 하드웨어 물리 분할. 독립된 mini-GPU | **완전** |
| vGPU | 가상화. VM 단위 격리 | 있음 |

GPU 공유 메커니즘의 전체 그림을 잡았으니, 각 기법의 상세 내용은 개별 글에서 다루면 된다.

* [GPU Sharing: Time Slicing 시리즈]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %}): Time Slicing의 개념, 쿠버네티스 설정, 적용 사례

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
