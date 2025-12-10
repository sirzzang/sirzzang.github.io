---
title:  "[Container] NVIDIA Container Runtime"
excerpt: 컨테이너 런타임과 NVIDIA Container Runtime에 대하여
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - docker
  - container
  - nvidia
  - gpu
  - kubernetes
  - container-runtime
  - cuda
---

[Kubernetes 환경에서 GPU를 사용하는 방법](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Setting/)에 대해 공부하다, NVIDIA Container Runtime에 대해 더 알아 본 내용에 대해 작성한다.

<br>
# Container Runtime

 NVIDIA Container Runtime을 알기 위해 먼저 Container Runtime에 대해 알아야 한다. 말 그대로, **컨테이너를 실행하고 관리하는 환경 혹은 소프트웨어**라고 보면 된다. 

컨테이너 런타임은 크게 **고수준 런타임**과 **저수준 런타임**으로 나뉘며, 각각 다른 표준 규격을 따른다.

```
┌─────────────────────────────────────────┐
│   High-Level Runtime (CRI)              │
│   Docker, containerd, CRI-O             │ ← kubectl이 통신하는 레벨
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│   Low-Level Runtime (OCI)               │
│   runc, crun, kata-runtime              │ ← 실제 컨테이너 생성
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│   Linux Kernel (namespaces, cgroups)    │
└─────────────────────────────────────────┘
```
- 고수준 컨테이너 런타임: Docker, containerd, CRI-O → CRI 규격
  - kubelet과 컨테이너 런타임이 gRPC로 통신하기 위한 인터페이스 명세
  - 쿠버네티스 환경에서의 kubelet이 통신하는 런타임
  - 이미지 관리, 네트워크, 볼륨, API 등 고수준 레벨 작업 처리
- 저수준 컨테이너 런타임: runc, crun, kata-runtime → OCI 규격
  - 고수준 컨테이너 런타임이 저수준 컨테이너 런타임을 호출하기 위한 인터페이스 명세
  - 컨테이너 생성을 위해 필요한 JSON 설정 파일(`config.json`)이 핵심
  - 저수준 컨테이너 런타임이 설정 파일을 읽고 실제 컨테이너 프로세스 생성
  - 실제 컨테이너 프로세스 생성, 리눅스 네임스페이스, cgroups 설정 등 실제 저수준 작업 담당

> 참고: 각 컨테이너 런타임 간 통신
>
> - 고수준 kubelet ↔ CRI runtime (containerd/CRI-O) 간 통신: gRPC 사용
>   - kubelet이 CRI 명세에 따라 gRPC 호출
>   - 컨테이너 런타임은 CRI 구현해서 요청에 응답
> - 저수준 CRI runtime ↔ OCI runtime (runc/crun) 간 통신: 직접 프로세스 실행 + JSON 파일
>   - 고수준 컨테이너 런타임이 저수준 컨테이너 런타임을 fork, exec으로 실행하면서, OCI 스펙에 맞는 설정 파일 전달
>   - 저수준 컨테이너 런타임에서 해당 설정 파일을 읽고 실제 컨테이너 프로세스 생성

<br>

## 동작 원리
- Docker : dockerd → containerd → runc → container
  - 가장 친숙한 컨테이너 엔진인 Docker의 경우, 내부적으로 containerd와 runc를 이용함
- containerd: containerd → runc → container
- 그 외 다른 컨테이너 런타임(CRI-O, Podman, Kata 등)도 당연히 있으며, Docker, containerd와 같이 내부적으로 저수준 컨테이너 런타임을 호출하는 방식으로 동작함 

> 참고: Docker와 containerd의 관계
> 
> 컨테이너 런타임에 대해 알아보다가 대관절 궁금해진 것. 어차피 Docker가 containerd를 이용하면, 사람들은 왜 containerd를 안 쓰고 Docker를 사용할까? 결국 Docker는 containerd를 한 번 래핑해 놓은 것이 아닌가?
> 
> 이에 대해 찾아 보니, 역사적인 이유가 있다고 한다. 컨테이너 솔루션으로 Docker가 최전성기를 달리고 있을 때, containerd는 Docker의 일부였다고 한다. Kubernetes도 컨테이너 오케스트레이션 솔루션이었으니, Docker에 의존할 수 밖에 없었고. 그런데, Docker 내부 구조가 슬슬 분리되기 시작했다. dockerd와 containerd로, 그리고 OCI 표준화에 의해 runc로. 그러다 2020년대에 Kubernetes가 Docker 지원을 중단하게 되면서, 대대적인 변화가 나타났다고 한다.
> 
> 어쩌면 지금 사람들이 Docker를 계속 사용하는 건 관성적인 이유도 있을 것이고, 레거시 시스템이나 개발 환경이 Docker에 의존하기 때문도 있을 것이라 보인다. 다만, 컨테이너 런타임 계층 구조에 대해 알게 되니, 굳이 Docker에만 의존해서 개발할 필요는 없어 보이기도 한다.
> 
> 어쨌든, 재미있는 이야기다. 나중에 시간 나면 역사 공부하듯 재미 삼아 찾아봐도 좋을 듯하다.


<br> 

# NVIDIA Container Runtime

컨테이너 런타임에서 NVIDIA GPU를 사용할 수 있게 해 주는 소프트웨어다. 정확히는, OCI 규격의 컨테이너 런타임에서 NVIDIA GPU를 사용할 수 있게 한다. 
> [공식 문서](https://developer.nvidia.com/container-runtime)에 의하면, GPU aware container runtime, compatible with the Open Containers Initiative(OCI) specification used by Docker, CRI-O, and other popular container technologies로, OCI 런타임과 호환된다는 것이 명시되어 있다.

구조적으로는 **runc(저수준 컨테이너 런타임)에 GPU 기능을 추가**해 놓은 런타임이다. runc의 NVIDIA wrapper인 셈이다. 


## NVIDIA Container Toolkit

NVIDIA Container Toolkit은 컨테이너 환경에서 NVIDIA GPU를 사용하기 위한 **전체 도구 모음(패키지)**이다. NVIDIA Container Runtime은 이 Toolkit의 핵심 구성 요소 중 하나이며, Toolkit을 설치하면 `nvidia-container-runtime`을 포함한 여러 도구들이 함께 설치되어 GPU를 컨테이너에 노출시킬 수 있게 된다.

```
NVIDIA Container Toolkit (전체 패키지)
  ├─ nvidia-container-runtime      # 런타임 래퍼
  ├─ nvidia-container-runtime-hook # 실제 작업 수행
  ├─ nvidia-container-cli          # GPU 디바이스 관리
  ├─ libnvidia-container           # 핵심 라이브러리
  └─ nvidia-ctk                    # 설정 도구
```

- 구성 요소
  - `nvidia-container-runtime`: `/usr/bin/nvidia-container-runtime`
    - runc의 wrapper 역할
  - `nvidia-container-runtime-hook`: `/usr/bin/nvidia-container-runtime-hook`
    - OCI prestart hook으로 동작하며, 실제 GPU 설정 작업 수행
  - `nvidia-container-cli`: `/usr/bin/nvidia-container-cli`
    - GPU 디바이스 파일과 라이브러리를 컨테이너에 마운트
  - `libnvidia-container`: 핵심 라이브러리
    - GPU 드라이버와 디바이스를 컨테이너 내부로 마운트하는 핵심 로직 구현
    - 다른 모든 도구들이 이 라이브러리를 사용하여 실제 GPU 작업 수행
  - `nvidia-ctk`: `/usr/bin/nvidia-ctk`
    - 컨테이너 런타임 설정을 자동화하는 도구

<br>

### libnvidia-container의 역할

`libnvidia-container`는 NVIDIA Container Toolkit의 **가장 핵심이 되는 라이브러리**로, 실제로 GPU를 컨테이너에서 사용 가능하게 만드는 로직을 담당한다. 컨테이너는 기본적으로 호스트 시스템과 격리된 환경이기 때문에, 호스트의 GPU에 직접 접근할 수 없다. `libnvidia-container`는 이 격리 환경에 안전하게 GPU 리소스를 연결하는 역할을 한다.

구체적으로는 다음과 같은 작업을 수행한다:
- **GPU 디바이스 파일 마운트**: `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm`, `/dev/nvidia-modeset` 등 GPU 디바이스 파일을 컨테이너 네임스페이스에 마운트
- **NVIDIA 드라이버 연결**: 호스트에 설치된 NVIDIA 드라이버를 컨테이너 내부에서 사용할 수 있도록 연결
- **CUDA 라이브러리 마운트**: `libcuda.so`, `libnvidia-ml.so` 등 GPU 연산에 필요한 라이브러리들을 컨테이너에 마운트
- **환경 변수 설정**: GPU 관련 환경 변수(`NVIDIA_VISIBLE_DEVICES` 등)를 컨테이너 환경에 주입

이 라이브러리는 `nvidia-container-cli`와 `nvidia-container-runtime-hook`에 의해 호출되어 사용된다.

<br>

### 동작 흐름

NVIDIA Container Toolkit의 구성 요소들이 어떻게 동작하여 GPU를 컨테이너에 연결하는지 살펴보자.

1. **컨테이너 런타임 설정 (초기 설정)**
   - `nvidia-ctk`를 이용해 Docker나 containerd 설정 파일에 nvidia 런타임 등록

2. **컨테이너 실행 시 동작**
   1. `nvidia-container-runtime` 실행 (runc wrapper)
   2. `nvidia-container-runtime-hook` 호출 (OCI prestart hook)
      > 참고: OCI Runtime Hooks
      > 
      > OCI(Open Container Initiative) 표준은 컨테이너 생성 과정의 특정 시점에 추가 작업을 주입할 수 있는 **Hooks 메커니즘**을 제공한다. Hook 종류로는 `prestart`, `createRuntime`, `createContainer`, `startContainer`, `poststart`, `poststop` 등이 있으며, `nvidia-container-runtime-hook`은 **prestart hook**으로 동작한다.
      > 
      > Prestart hook은 컨테이너 네임스페이스가 생성된 후, 컨테이너 프로세스가 시작되기 **직전**에 실행된다. 이 시점에 GPU 디바이스, 라이브러리, 환경 변수를 컨테이너 스펙에 주입하고, 수정된 스펙으로 runc가 컨테이너를 생성하게 된다. 이것이 NVIDIA가 runc를 직접 수정하지 않고도 GPU 기능을 추가할 수 있는 핵심 메커니즘이다.
   3. `nvidia-container-cli` 실행
      - 이때 `libnvidia-container` 라이브러리 사용
      - GPU 디바이스 파일(`/dev/nvidia0`, `/dev/nvidiactl` 등) 컨테이너에 추가
      - CUDA 라이브러리 마운트
      - GPU 관련 환경 변수 설정
   4. 수정된 컨테이너 스펙으로 `runc` 호출하여 실제 컨테이너 생성

즉, **libnvidia-container**가 실제 GPU 연결 로직을 구현하고, **nvidia-container-cli**가 이 라이브러리를 사용하며, **nvidia-container-runtime-hook**이 이 모든 과정을 OCI 표준에 맞게 진행한다.

<br>

# 동작 구조

컨테이너 환경에서의 컨테이너 런타임 동작 원리만 알면, 쿠버네티스 환경으로 확장하는 것은 한층 수월하다.

## Container, w/o NVIDIA GPU
- Docker: dockerd → containerd → runc → 컨테이너
- containerd: containerd → runc → 컨테이너

## Container, w/ NVIDIA GPU
- Docker: dockerd → containerd → nvidia-container-runtime → runc → 컨테이너
  - Docker에 `nvidia-container-runtime`이 설정되어 있어야 함
    ```json
    // /etc/docker/daemon.json
    {
      "runtimes": {
        "nvidia": {
          "path": "/usr/bin/nvidia-container-runtime",
          "runtimeArgs": []
        }
      }
    }
    ```
- containerd 런타임일 경우: containerd → nvidia-container-runtime → runc → 컨테이너
  - containerd에 `nvidia-container-runtime`이 설정되어 있어야 함
    ```toml
    # /etc/containerd/config.toml
    version = 2
    
    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
      runtime_type = "io.containerd.runc.v2"
      
      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
        BinaryName = "/usr/bin/nvidia-container-runtime"
        SystemdCgroup = true
    ```

## Kubernetes, w/o NVIDIA GPU
- kubelet (CRI) → containerd → runc → 컨테이너
- kubelet (CRI) → CRI-O → runc → 컨테이너

> 참고: dockershim 제거
> Kubernetes 1.24 이전에는 `kubelet → dockerd → containerd → runc` 경로도 가능했으나, dockershim 제거 이후 containerd나 CRI-O를 직접 사용하는 것이 표준이 되었다.

## Kubernetes, w/ NVIDIA GPU
- kubelet → containerd → nvidia-container-runtime → runc → 컨테이너
- kubelet → CRI-O → nvidia-container-runtime → runc → 컨테이너

> 참고: dockershim 제거
> Kubernetes 1.24 이전에는 `kubelet → dockerd → containerd → nvidia-container-runtime → runc` 경로도 가능했다.

<br>

# 실제 사용 예시

Docker, Kubernetes 환경 각각에서 NVIDIA Container Runtime을 이용해 GPU를 사용할 수 있다.

## Docker에서 GPU 사용

NVIDIA Container Toolkit을 설치한 후, Docker에서 GPU를 사용하려면 `--gpus` 플래그를 사용한다.

```bash
# 모든 GPU 사용
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# 특정 GPU만 사용 (GPU 0, 1번)
docker run --rm --gpus '"device=0,1"' nvidia/cuda:11.0-base nvidia-smi

# GPU 개수 지정
docker run --rm --gpus 2 nvidia/cuda:11.0-base nvidia-smi
```

## Kubernetes에서 GPU 사용

Kubernetes에서는 `RuntimeClass`를 정의하여 특정 Pod에서 NVIDIA Container Runtime을 사용하도록 설정할 수 있다.

```yaml
# RuntimeClass 정의
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: nvidia
handler: nvidia # [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]와 매칭
---
# Pod에서 RuntimeClass 사용
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  runtimeClassName: nvidia  # nvidia 런타임 지정
  containers:
  - name: cuda-container
    image: nvidia/cuda:11.0-base
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1  # GPU 1개 요청
```

## 설치 및 설정 확인

NVIDIA Container Toolkit 설치 및 Docker 런타임 설정에 대한 자세한 내용은 [Kubernetes 환경에서 GPU 사용하기](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Setting/)를 참고하자. 여기서는 간단히 확인 방법만 살펴본다.

```bash
# 설치 확인
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

실행 결과로 GPU 정보가 출력되면 정상적으로 설정된 것이다.

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 525.60.13    Driver Version: 525.60.13    CUDA Version: 12.0   |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
...
```

<br>

# 결론

결과적으로, NVIDIA Container Runtime은 컨테이너 환경이나 쿠버네티스 환경에서 NVIDIA GPU를 사용하기 위한 컨테이너 런타임이라고 정의하면 된다. 고수준 컨테이너 런타임에서 호출되어, GPU 기능을 감싸 저수준 컨테이너 런타임을 호출하는 역할을 한다.

지금까지는 NVIDIA GPU에 국한되어 이야기했으나, 사실 다른 GPU 벤더사의 경우도 동일하다. 벤더사 별로 자신의 GPU 기능과 runc를 감싸 컨테이너 런타임을 제공하면 되는 것이다. 조금 더 구체적으로는,
- 아래와 같은 OCI 명세를 따르며
  - config 읽기
  - namespace/cgroup 설정
  - 프로세스 실행
  - ...
- GPU를 사용할 수 있는 기능을 제공하는 
  - config 수정
  - GPU 기능 추가
  - 실제 OCI 런타임 호출
- 런타임을 만들면 되는 것이다.

<br>

GPU 벤더별로 달라질 뿐, 전부 다 동일한 위치에 있다.

```
┌─────────────────────────────────────┐
│  High Level Container Runtime       │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  GPU Runtime Wrapper (vendor 제공)   │
│  - nvidia-container-runtime         │
│  - rocm-container-runtime           │
│  - intel-gpu-container-runtime      │
└─────────────────────────────────────┘
              ↓
        GPU 디바이스 추가
        라이브러리 마운트
        환경변수 설정
              ↓
┌─────────────────────────────────────┐
│  Low Level Container Runtime        │
└─────────────────────────────────────┘
              ↓
        컨테이너 생성
```

Kubernetes 환경에서도 마찬가지로, GPU 벤더사가 앞선 글에서 살펴봤던 것과 같은 Device Plugin을 만들어 제공하기만 하면, 그것을 사용할 수 있게 되는 것이다.