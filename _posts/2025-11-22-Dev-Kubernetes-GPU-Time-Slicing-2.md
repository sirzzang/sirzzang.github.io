---
title:  "[Kubernetes] Kubernetes 환경에서 GPU Time Slicing 사용하기 - 2. 설정"
excerpt: NVIDIA GPU Time Slicing의 동작 원리와 ConfigMap 설정 방법을 알아보자.
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


[지난 글](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Time-Slicing-1/)에서 GPU Time Slicing의 일반적인 개념에 대해 알아보았다. Context Switching, Preemptive Switching, 그리고 ~~간략한~~ 하드웨어 수준에서의 동작 원리까지 살펴보았는데, 이번 글에서는 이러한 개념이 쿠버네티스 환경에서 **어떻게 동작하는지**, 그리고 **Time Slicing ConfigMap을 어떻게 구성하는지** 알아본다.

GPU Time Slicing을 적용하는 방법은 GPU 벤더마다 다르다. 이 글에서는 가장 널리 사용되는 **NVIDIA GPU**를 기준으로 설명한다. NVIDIA는 쿠버네티스 환경에서 GPU를 사용할 수 있게 해주는 [NVIDIA Device Plugin](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Setting/)과 [GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html)를 제공하며, 이를 통해 Time Slicing 설정을 적용할 수 있다.

> 나중에 다른 GPU 벤더(AMD, Intel 등)를 사용하게 된다면, 해당 벤더의 공식 문서를 참고하자. Time Slicing의 핵심 개념은 동일하므로, 이 글에서 다루는 NVIDIA 사례를 참고하면 설정 방향을 잡는 데 도움이 될 것이다.

<br>

# 동작 원리

쿠버네티스 환경에서 GPU Time Slicing이 어떻게 동작하는지 알아보자. [NVIDIA Device Plugin 동작 원리](https://sirzzang.github.io/dev/Dev-Kubernetes-NVIDIA-GPU-Mechanism/)에서 Device Plugin이 Kubelet에게 GPU 개수를 보고하고, 스케줄링 시 GPU를 할당하는 메커니즘을 소개한 바 있다. Time Slicing은 이 메커니즘을 활용하되, 핵심은 **NVIDIA Device Plugin이 GPU 개수를 속여서 보고**한다는 것이다.

<br>

## 전체 흐름

Time Slicing 동작은 크게 두 단계로 나눌 수 있다.

**1단계: 보고 (ListAndWatch)**

Device Plugin이 시작되면, ConfigMap을 읽고 Kubelet에게 GPU 개수를 보고한다.

```text
┌─────────────────────────────────────────┐
│   Time-slicing ConfigMap                │
│   - replicas: 4                         │
└──────────────┬──────────────────────────┘
               │ (읽어서 적용)
┌──────────────▼──────────────────────────┐
│   NVIDIA Device Plugin                  │
│   - ConfigMap 파싱                      │
│   - replicas만큼 논리적 GPU 생성        │
└──────────────┬──────────────────────────┘
               │ (GPU 개수 보고: ListAndWatch)
┌──────────────▼──────────────────────────┐
│   Kubelet                               │
│   - "이 노드에 nvidia.com/gpu: 4 있음"  │
└─────────────────────────────────────────┘
```

<br>

**2단계: 할당 및 실행 (Allocate)**

파드가 스케줄링되면, Device Plugin이 GPU를 할당하고 Container Runtime이 컨테이너를 실행한다.

```text
┌─────────────────────────────────────────┐
│   Pod 생성 요청 (nvidia.com/gpu: 1)     │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│   Kubelet                               │
│   - Device Plugin에게 GPU 할당 요청     │
└──────────────┬──────────────────────────┘
               │ (Allocate 호출)
┌──────────────▼──────────────────────────┐
│   NVIDIA Device Plugin                  │
│   - 같은 물리 GPU 정보 반환             │
└──────────────┬──────────────────────────┘
               │ (GPU 디바이스 정보 전달)
┌──────────────▼──────────────────────────┐
│   Container Runtime                     │
│   - 같은 GPU를 여러 컨테이너에 마운트   │
└──────────────┬──────────────────────────┘
               │ (CUDA 초기화)
┌──────────────▼──────────────────────────┐
│   nvidia.ko (커널 드라이버)             │
│   - ConfigMap 전혀 모름!                │
│   - 여러 context 감지하면               │
│     자동으로 time-slicing 실행          │
└─────────────────────────────────────────┘
```

<br>

## 보고 단계

[NVIDIA Device Plugin이 GPU 개수를 보고](https://sirzzang.github.io/dev/Dev-Kubernetes-NVIDIA-GPU-Mechanism/#보고)할 때, Time Slicing 설정의 replica 수에 따라 **논리 슬롯 개수를 여러 개로 보고**한다.

```go
// ListAndWatch 의사코드
func ListAndWatch() {
    physicalGPUs := []GPU{
        {UUID: "GPU-abc123", Index: 0},  // 물리 GPU 1개
    }
    
    // replicas: 4 설정 → 4개로 복제
    virtualDevices := []Device{
        {Name: "nvidia0-0", UUID: "GPU-abc123"},  // 가상 슬롯 0
        {Name: "nvidia0-1", UUID: "GPU-abc123"},  // 가상 슬롯 1
        {Name: "nvidia0-2", UUID: "GPU-abc123"},  // 가상 슬롯 2
        {Name: "nvidia0-3", UUID: "GPU-abc123"},  // 가상 슬롯 3
    }
    
    // Kubernetes에 등록
    kubelet.RegisterDevices("nvidia.com/gpu", 4)  // "GPU 4개 있어요!"
}
```

결과적으로, 클러스터 내에서는 해당 노드에 replica 수만큼의 GPU가 있다고 인식하게 된다.

<br>

## 할당 단계

[NVIDIA Device Plugin이 GPU 할당 결과를 반환](https://sirzzang.github.io/dev/Dev-Kubernetes-NVIDIA-GPU-Mechanism/#스케줄링)할 때, **전부 같은 물리 GPU를 반환**한다.

```go
// Allocate 의사 코드
func Allocate(deviceID string) {
    // deviceID = "nvidia0-0", "nvidia0-1", "nvidia0-2"
    // 하지만 전부 같은 물리 GPU UUID 반환
    
    return &AllocateResponse{
        Devices: []Device{
            {ID: "/dev/nvidia0"},        // 같은 디바이스
            {ID: "/dev/nvidiactl"},
            {ID: "/dev/nvidia-uvm"},
        },
        Envs: map[string]string{
            "CUDA_VISIBLE_DEVICES": "GPU-abc123",  // 같은 UUID
        },
    }
}
```

<br>

## 마운트 단계

컨테이너 런타임은 Kubelet이 Device Plugin으로부터 받은 응답대로 마운트하여 컨테이너를 실행한다. 컨테이너 런타임은 Time Slicing에 대해 전혀 모른다.

```yaml
# Pod A 컨테이너
Mounts:
  /dev/nvidia0 → /dev/nvidia0
  /dev/nvidiactl → /dev/nvidiactl
Env:
  CUDA_VISIBLE_DEVICES=GPU-abc123

# Pod B 컨테이너  
Mounts:
  /dev/nvidia0 → /dev/nvidia0      # 똑같은 디바이스
  /dev/nvidiactl → /dev/nvidiactl
Env:
  CUDA_VISIBLE_DEVICES=GPU-abc123  # 똑같은 UUID

# Pod C 컨테이너
Mounts:
  /dev/nvidia0 → /dev/nvidia0      # 또 똑같은 디바이스
  /dev/nvidiactl → /dev/nvidiactl
Env:
  CUDA_VISIBLE_DEVICES=GPU-abc123  # 똑같은 UUID
```

<br>

## GPU Driver의 시간 분할

실제 GPU 사용 시점에 NVIDIA GPU Driver가 Context Switching을 수행하며 시간을 분할한다.

```text
Time ──────────────────────────────────────────────────────────────────────→

         ┌─────┐       ┌─────┐       ┌─────┐       ┌─────┐       ┌─────┐
Pod A    │█████│       │█████│       │█████│       │█████│       │█████│
         └─────┘       └─────┘       └─────┘       └─────┘       └─────┘

               ┌─────┐       ┌─────┐       ┌─────┐       ┌─────┐       ┌───
Pod B          │█████│       │█████│       │█████│       │█████│       │███
               └─────┘       └─────┘       └─────┘       └─────┘       └───

                     ┌─────┐       ┌─────┐       ┌─────┐       ┌─────┐
Pod C                │█████│       │█████│       │█████│       │█████│
                     └─────┘       └─────┘       └─────┘       └─────┘

GPU      ──A────B────C────A────B────C────A────B────C────A────B────C────→
         (하나의 물리 GPU를 시간 단위로 분할하여 번갈아 사용)
```

각 파드는 자신이 전용 GPU를 받았다고 생각하지만, 실제로는 동일한 GPU를 보고 있으며, NVIDIA GPU Driver의 [Compute Preemption](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Time-Slicing-1/#preemptive-context-switching)이 시간을 나눠 할당해 준다.

결과적으로, 여러 파드가 동시에 하나의 GPU ID를 보게 되고, NVIDIA GPU Driver의 Compute Preemption이 자동으로 시간을 분할해 준다. 마치 **OS에서 프로세스 스케줄링하듯, NVIDIA GPU Driver가 각 프로세스마다 시간을 분할해서 할당**해 주는 것이다.


<br>

# Time Slicing ConfigMap

GPU Time Slicing을 적용하기 위한 설정 파일이다. NVIDIA Device Plugin이 이 ConfigMap을 읽어서, Kubelet에게 GPU 리소스를 보고할 때 적용한다.

<br>

## 기본 구조

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        renameByDefault: false
        failRequestsGreaterThanOne: false
        resources:
          - name: nvidia.com/gpu
            replicas: 4
```

<br>

## 설정 항목

### `data.<key>`

Time Slicing 설정 이름이다. NVIDIA Device Plugin에 마운트될 때 키로 사용된다.
* 키 이름은 자유롭게 지정할 수 있다. 위 예시에서는 `any`를 사용했다.
* 노드별로 다른 설정을 적용하고 싶다면, 키를 여러 개 작성하면 된다.

<br>

### `version`

설정 파일 버전이다.

<br>

### `flags.migStrategy`

Time Slicing 설정이 적용되는 노드의 MIG 장치에 레이블을 지정하는 방식이다.
* `none`: MIG 사용 안 함 (기본값)
* `single`: 노드의 모든 MIG 인스턴스가 같은 GPU 프로파일
  * 예: 리소스 전부가 `nvidia.com/mig-1g.5gb` 형태로 등록됨
* `mixed`: 한 노드에 다양한 MIG 프로파일이 혼재할 수 있는 경우
  * 예: `1g.5gb` 2개 + `3g.20gb` 1개

<br>

### `sharing.timeSlicing.renameByDefault`

GPU 리소스 리네임 여부이다. 기본값은 `false`이다.

* `true`: `<resource-name>` 대신 `<resource-name>.shared` 이름으로 리소스를 등록함
  * 예: `nvidia.com/gpu` → `nvidia.com/gpu.shared`
  * 리소스 요청에 `<resource-name>.shared`를 지정하여 공유 액세스가 있는 GPU에 파드를 스케줄링하려는 경우 유용
* `false`: 리소스 이름은 그대로이나, 제품 이름 레이블 값에 `-SHARED` 접미사가 붙음
  * 예: `nvidia.com/gpu.product=Tesla-T4` → `nvidia.com/gpu.product=Tesla-T4-SHARED`
  * 리소스 요청 시 `-SHARED` 접미사가 포함된 노드 셀렉터를 지정하여 스케줄링할 수 있음

> 참고: renameByDefault 기본값
>
> 해당 설정 항목의 기본값이 `false`인 이유는 **하위 호환성** 때문이다. 
> 만약 `true`라면, 기존에 `nvidia.com/gpu: 1`로 리소스를 요청하던 파드의 경우, 스케줄링에 실패할 수 있다. `false`로 두면, 리소스 이름은 그대로 유지하면서 GPU product 레이블 값만 변경되기 때문에, 노드 리소스명이 변경되어 나타나는 문제를 예방할 수 있다.

<br>

### `sharing.timeSlicing.resources`

Time Slicing을 적용할 리소스 목록이다.

* `name`: 리소스명
  * `nvidia.com/gpu`: 일반 GPU
  * `nvidia.com/mig-1g.5gb`: MIG 인스턴스 등
* `replicas`: 논리적 슬롯 개수
  * 타임 슬라이싱이 적용된 GPU에 몇 개까지의 shared access를 허용할 것인지 지정
  * 반드시 **2 이상**이어야 함

<br>

### `sharing.timeSlicing.failRequestsGreaterThanOne`

1개를 초과하는 리소스 요청이 실패하는지 여부이다. 기본값은 `false`이다.

* `false`: 2개 이상 요청해도 허용하지만, 실제로는 1개 요청한 것과 같은 성능
* `true`: 2개 이상 요청하면 아예 파드 생성 실패 (UnexpectedAdmissionError)

<br>

예를 들어, 물리 GPU 1개를 4개 replica로 분할한 상황에서 파드 A가 GPU 1개, B가 GPU 1개, C가 GPU 2개를 요청한 경우를 보자.

`false`인 경우, 여러 개 요청은 가능하지만, 성능을 더 받지는 않는다.

```yaml
# Time-slicing config
sharing:
  timeSlicing:
    replicas: 4
    failRequestsGreaterThanOne: false
---
# Pod A
resources:
  limits:
    nvidia.com/gpu: 1  # 성공

# Pod B  
resources:
  limits:
    nvidia.com/gpu: 1  # 성공

# Pod C
resources:
  limits:
    nvidia.com/gpu: 2  # 성공 (하지만 의미 없음)
```

Pod C가 GPU 2개를 요청해도 배포는 성공하지만, 실제로는 Pod A, B와 동일하게 시간을 1/3씩 나눠 쓰게 된다.

<br>

`true`인 경우, 여러 개 요청 자체가 불가능하다.

```yaml
# Time-slicing config
sharing:
  timeSlicing:
    replicas: 4
    failRequestsGreaterThanOne: true
---
# Pod A
resources:
  limits:
    nvidia.com/gpu: 1  # 성공

# Pod B  
resources:
  limits:
    nvidia.com/gpu: 1  # 성공

# Pod C
resources:
  limits:
    nvidia.com/gpu: 2  # UnexpectedAdmissionError
```

Pod C는 UnexpectedAdmissionError를 받게 되어, GPU 요청을 1로 수정해서 재배포해야 한다.

<br>

> **참고: 이 설정 항목의 의의**
>
> NVIDIA 공식 문서에는 이 설정에 대해 다음과 같이 설명되어 있다.
>
> *"The purpose of this field is to enforce awareness that requesting more than one GPU replica does not result in receiving more proportional access to the GPU."*
>
> 처음 읽으면 무슨 말인지 헷갈릴 수 있는데, 풀어서 설명하면 다음과 같다.
>
> Time Slicing 원리상, GPU 슬롯을 2개 요청하더라도 더 많은 GPU 시간을 받는 것이 아니다. 슬롯을 2개 차지하기만 할 뿐, 실제로는 같은 GPU가 마운트되기 때문이다. GPU Driver 입장에서는 그냥 "파드 A, B, C가 GPU를 쓰네?" 정도로 인식할 뿐, 어느 파드에 더 많은 시간을 분배해야겠다는 개념이 없다.
>
> 따라서 이 설정은, replica를 여러 개 요청해도 그에 비례한 GPU 액세스를 얻지 못한다는 사실을 **사용자에게 인지시키기 위한** 것이다. `true`로 설정하면, 아예 배포 자체를 막아서 "GPU 2개 요청하면 2배 빠르겠지?"라는 잘못된 기대를 원천 차단하는 효과가 있다.

<br>

## 설정 예시

### 클러스터 전체에 동일 설정 적용

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config-all
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 4
```

<br>

### 노드별로 다른 설정 적용

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config-fine
data:
  a100-40gb: |-
    version: v1
    flags:
      migStrategy: mixed
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 8
        - name: nvidia.com/mig-1g.5gb
          replicas: 2
        - name: nvidia.com/mig-3g.20gb
          replicas: 3
  tesla-t4: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 4
```

<br>

### MIG와 Time Slicing 조합

MIG 인스턴스에도 Time Slicing을 적용할 수 있다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
data:
  any: |-
    version: v1
    flags:
      migStrategy: mixed
    sharing:
      timeSlicing:
        renameByDefault: false
        resources:
        - name: nvidia.com/mig-1g.5gb
          replicas: 4  # 1g.5gb 하나를 4개 pod가 공유
        - name: nvidia.com/mig-3g.20gb
          replicas: 2  # 3g.20gb 하나를 2개 pod가 공유
```

위 설정에서, `nvidia.com/mig-1g.5gb`가 2개, `nvidia.com/mig-3g.20gb`가 1개 있다면, 논리적으로는 다음과 같이 인식된다.
* `nvidia.com/mig-1g.5gb`: 2 × 4 = 8 (논리적으로 8개 파드 스케줄링 가능)
* `nvidia.com/mig-3g.20gb`: 1 × 2 = 2 (논리적으로 2개 파드 스케줄링 가능)
