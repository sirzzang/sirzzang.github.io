---
title:  "[Container] 컨테이너 장치 주입: OCI Runtime Hook과 CDI"
excerpt: "컨테이너에 장치 파일을 주입하기 위한 두 가지 방식을 알아보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Container
  - OCI
  - CDI
  - Runtime
  - Hook
  - Device
  - 컨테이너
  - 런타임
  - 장치
---

<br>

GPU 같은 하드웨어 장치를 컨테이너에서 사용하려면, 호스트의 장치 파일을 컨테이너에 주입해야 한다. [Kubernetes 환경에서 NVIDIA GPU를 설정](/dev/Dev-Kubernetes-GPU-Setting/)하거나, [NVIDIA Container Runtime의 동작 원리](/dev/Dev-Nvidia-Container-Runtime/)를 파악하다 보면 `nvidia-container-runtime-hook`, `CDI` 같은 개념을 마주하게 된다.

이 글에서는 컨테이너 환경에서의 장치 주입을 위한 두 가지 방식인 **OCI Runtime Hook**과 **CDI(Container Device Interface)**를 살펴본다.

> 장치 파일, 커널 모듈, 유저 라이브러리의 관계는 [리눅스 디바이스 드라이버 구조](/cs/CS-Linux-Device-Driver/) 참고.

<br>

# TL;DR

- **OCI Runtime Hook**: 컨테이너 생명주기 특정 시점에 외부 프로그램을 실행하는 명령형(imperative) 방식
- **CDI**: 주입할 장치를 YAML/JSON으로 선언하는 선언형(declarative) 방식
- **Hook 문제점**: 런타임별 설정 방식 상이, 벤더별 파편화, 디버깅 어려움
- **CDI 장점**: 런타임/벤더 중립, 투명한 설정, Kubernetes Device Plugin 통합
- **현황**: Hook은 레거시로 여전히 사용되나, CDI가 새로운 표준으로 자리잡는 중

<br>

# OCI Runtime Hook


## 배경

Docker가 컨테이너 시장을 독점하던 시기, 다양한 런타임 간 호환성을 위해 **OCI(Open Container Initiative)**가 설립되었다.

- **2015**: Docker가 사실상 컨테이너의 표준
- **2015.06.**: OCI 설립 (Linux Foundation 주도)
- **2017.07.**: OCI Runtime Spec 1.0.0 발표 - Hooks 포함
- **현재**: OCI Runtime Spec은 사실상 모든 컨테이너 런타임이 따르는 표준

OCI Runtime Hook은 **컨테이너 생명주기 중 특정 시점에 실행되는 외부 프로그램**이다. 이를 통해 런타임이 직접 지원하지 않는 기능(장치 주입, 네트워크 설정 등)을 확장할 수 있다.

> 컨테이너 생명주기와 Hook 종류에 대한 상세 내용은 [참고: 컨테이너 생명주기](#참고-컨테이너-생명주기) 참조.

<br>

## 장치 주입 방식

장치 주입에는 **createContainer** hook이 사용된다. 컨테이너 네임스페이스가 생성된 직후, 사용자 프로세스가 시작되기 전에 실행되어 장치 파일과 라이브러리를 주입한다.

<br>

### Hook 정의

Hook은 OCI 런타임이 읽는 `config.json`에 정의한다. `config.json`은 containerd나 CRI-O 같은 상위 런타임이 컨테이너 이미지와 실행 옵션을 기반으로 생성하며, runc 같은 OCI 런타임이 이를 읽어 컨테이너를 생성한다.

```json
{
  "hooks": {
    "createContainer": [
      {
        "path": "/usr/bin/nvidia-container-runtime-hook",
        "args": ["nvidia-container-runtime-hook", "prestart"],
        "env": [
          "NVIDIA_VISIBLE_DEVICES=0,1",
          "NVIDIA_DRIVER_CAPABILITIES=compute,utility"
        ],
        "timeout": 30
      }
    ]
  }
}
```

| 필드 | 설명 |
|-----|------|
| `path` | 실행할 프로그램 경로 |
| `args` | 프로그램에 전달할 인자 |
| `env` | 환경변수 |
| `timeout` | 타임아웃 (초) |

<br>

### 실행 흐름

OCI 런타임이 `config.json`을 읽고, 생명주기의 각 시점에 정의된 Hook을 fork/exec으로 실행한다.
1. **상위 런타임**(containerd, CRI-O)이 컨테이너 이미지 + 실행 옵션을 기반으로 `config.json` 생성
2. **OCI 런타임**(runc)이 `config.json`을 읽고 Hook 실행


```
Container Runtime (containerd, cri-o)
  ↓
OCI Runtime (runc)
  ↓ (reads config.json)
  ├─ Create container namespace
  ├─ [createContainer hook 실행] ← 장치 주입 시점
  ├─ Start user process
  └─ ...
```

> 참고: **containerd-shim과 Hook 실행**
>
> containerd 환경에서 Hook은 실제로 **containerd-shim**이 실행한다. shim은 컨테이너가 실행되는 동안 containerd가 재시작되더라도 라이프사이클을 독립적으로 관리한다. Hook도 shim이 실행하므로 containerd 재시작과 무관하게 동작한다.

<br>

### 예시: NVIDIA GPU 주입

`nvidia-container-runtime-hook`이 createContainer 시점에 실행되어 GPU 장치를 주입한다.

```
runc
  ↓
┌─────────────────────────────────────┐
  Container namespace created
  - mount namespace
  - pid namespace
  - rootfs prepared
└─────────────────────────────────────┘
  ↓ fork/exec
nvidia-container-runtime-hook prestart
  ↓
  ├─ mknod /dev/nvidia0          # 장치 파일 생성
  ├─ mknod /dev/nvidiactl
  ├─ mount libcuda.so.1          # 유저 라이브러리 마운트
  ├─ mount libcudnn.so.8
  └─ setup cgroup devices        # cgroup 설정
  ↓ exit(0)
runc (continues to start user process)
```

Hook은 stdin으로 컨테이너 상태 정보를 JSON 형태로 전달받아, 어떤 컨테이너에 장치를 주입할지 판단한다.

```json
{
  "ociVersion": "1.0.2",
  "id": "container-abc123",
  "pid": 12345,
  "root": "/run/runc/container-abc123/rootfs",
  "bundle": "/var/lib/containers/container-abc123",
  "annotations": {
    "io.kubernetes.cri.container-type": "container",
    "io.kubernetes.pod.name": "gpu-pod",
    "io.kubernetes.pod.namespace": "default"
  }
}
```

> 참고: `annotations` 필드는 Kubernetes 환경에서 중요하다. Hook이 어떤 Pod/Container인지 식별해 환경변수나 라벨 기반으로 장치 주입 여부를 결정할 수 있다.

<br>

### 사용 사례

OCI Runtime Hook을 활용하는 대표적인 장치 주입 사례는 다음과 같다.

| 분류 | Hook | 용도 |
|-----|------|------|
| GPU | nvidia-container-runtime-hook | NVIDIA GPU |
| GPU | amdgpu-container-hook | AMD GPU |
| RDMA | rdma-container-hook | InfiniBand 네트워크 장치 |
| FPGA | intel-fpga-hook | Intel FPGA |
| FPGA | xilinx-container-hook | Xilinx FPGA |

<br>

## 문제점

OCI Runtime Hook 방식에는 다음과 같은 문제점이 있다.

<br>

### 런타임별 설정 상이

Hook을 주입하는 방식이 런타임마다 다르다.

| 런타임 | 설정 방식 | 예시 |
|-------|----------|-----|
| Docker | `daemon.json`에 runtime 등록 | `--runtime=nvidia` 옵션 |
| containerd | `config.toml`에 runtime 래퍼 등록 | `[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]` |
| CRI-O | hooks 디렉토리에 JSON 파일 배치 | `/usr/share/containers/oci/hooks.d/*.json` |

표준화되지 않아 런타임별로 설정 파일과 방식이 모두 다르다.

<br>

### 런타임 래퍼 필요

Hook을 주입하려면 런타임을 감싸는 래퍼(wrapper)가 필요하다. 래퍼가 `config.json`을 동적으로 수정해 Hook을 주입한다.

```
Container Runtime
  ↓
Device-specific Runtime Wrapper ← config.json에 Hook 정의 주입
  ↓
runc
  ↓ (executes hook)
Device Hook Binary
  ↓
Device mounted
```

<br>

### 벤더별 파편화

각 하드웨어 벤더가 자체 Hook 시스템을 개발했다. 벤더마다 Hook 바이너리, 설정 파일 경로, 환경변수 규칙이 모두 다르다.

```bash
# NVIDIA
/usr/bin/nvidia-container-runtime-hook
/usr/share/containers/oci/hooks.d/oci-nvidia-hook.json

# AMD
/usr/bin/amdgpu-container-runtime-hook
/etc/amdgpu-container-runtime/hook.json

# Intel (FPGA)
/usr/bin/intel-fpga-hook
/etc/intel-fpga/container-hook.json
```

> 참고: **컨테이너 오케스트레이션과의 관계**
>
> Kubernetes 같은 컨테이너 오케스트레이션 시스템이 대중화되면서 이 문제가 더 부각되었다. Kubernetes Device Plugin 프레임워크는 다양한 하드웨어를 일관되게 스케줄링해야 하는데, 벤더별로 파편화된 Hook 방식으로는 통합 관리가 어려웠다. 이것이 CDI 등장의 직접적인 배경이 되었다.

<br>

### 명령형 방식의 한계

Hook은 **무엇을 실행할지**를 지정하는 명령형 방식이다. Hook이 **무엇을 하는지**는 실행해봐야 알 수 있다.

- Hook이 OCI spec을 런타임에 동적으로 변조
- 실행 결과가 블랙박스
- 실패 시 원인 파악이 힘듦

**보안 우려**도 있다. Hook은 **root 권한**으로 컨테이너 네임스페이스를 수정한다.

- 임의의 장치 파일 생성, 파일 마운트, cgroup 제한 우회 가능
- Hook 바이너리가 타사 벤더에서 제공되므로 공급망 공격 위험
- 바이너리 검증 어려움, 업데이트 시 신뢰 문제

CDI는 선언적 정의로 무엇이 주입되는지 명확히 확인할 수 있고, 런타임이 spec 유효성을 검증한다.

<br>

## 참고: 컨테이너 생명주기

OCI Runtime Spec은 컨테이너의 상태와 생명주기를 표준으로 정의한다.

<br>

### 컨테이너 상태

| 상태 | 설명 |
|-----|------|
| `creating` | 컨테이너 환경 생성 중 |
| `created` | 환경 생성 완료, 사용자 프로세스 미실행 |
| `running` | 사용자 프로세스 실행 중 |
| `stopped` | 사용자 프로세스 종료됨 |

```
[create 명령]
     ↓
 creating ─────→ created ─────→ running ─────→ stopped
              [start 명령]   [프로세스 실행]   [kill/종료]
                                                  ↓
                                            [delete 명령]
                                                  ↓
                                              (삭제됨)
```

> 참고: Docker의 `docker run`은 `create`와 `start`를 한 번에 수행하지만, OCI Runtime 수준에서는 두 단계가 분리되어 있다.

<br>

### Hook 종류와 실행 시점

OCI Runtime Spec에서 정의하는 Hook은 다음과 같다.

<details>
<summary>생명주기와 Hook 실행 시점 다이어그램</summary>

<img src="{{site.url}}/assets/images/oci-container-lifecycle.png" alt="oci-container-lifecycle">

</details>


| Hook | 실행 시점 | 주요 용도 |
|------|----------|----------|
| `createRuntime` | 런타임 네임스페이스 생성 시 | 런타임 환경 초기화 |
| `createContainer` | 컨테이너 네임스페이스 생성 직후 | **장치 주입**, 마운트 |
| `startContainer` | 사용자 프로세스 시작 직전 | 최종 검증, 트레이싱 |
| `poststart` | 사용자 프로세스 시작 직후 | 알림, 모니터링 (비동기) |
| `poststop` | 컨테이너 종료 후 | 리소스 정리, 로그 수집 |

> 참고: 초기 OCI Spec의 `prestart` hook은 deprecated 처리되었다. `createContainer`로 대체 가능하다.

> 참고: 컨테이너 생명주기에 대한 상세 내용은 [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec/blob/main/runtime.md) 참고.

<br>

# CDI


## 배경

CDI(Container Device Interface)는 OCI Runtime Hook의 문제점을 해결하기 위해 등장했다.

- **2019**: CNCF TAG Runtime에서 논의 시작
- **2021**: CNCF에서 CDI 스펙 발표
- **2022**: CDI v0.3.0 안정화
- **2023**: containerd 1.7+, CRI-O 1.25+ 공식 지원
- **현재**: Kubernetes Device Plugin의 표준으로 자리잡음

CDI는 CNI(Container Network Interface)의 설계 패턴을 따른다. CNI가 네트워크 설정을 선언적으로 정의하듯, CDI는 장치 설정을 선언적으로 정의한다.

> 참고: **Linux 철학과의 유사성**
>
> CDI의 설계는 Linux의 ["Everything is a file"](/cs/CS-Linux-Device-Driver/#everything-is-a-file) 철학과 유사하다. 다양한 하드웨어를 일관된 추상화 계층으로 접근한다는 점에서 동일한 설계 철학이다.
> - **Linux**: "Everything is a file" → **CDI**: "Everything is a CDI device"
> - **Linux**: `/dev/nvidia0`로 GPU 접근 → **CDI**: `nvidia.com/gpu=0`으로 GPU 선언
> - **Linux**: 파일 경로라는 통일된 인터페이스 → **CDI**: `vendor.com/class=name`이라는 통일된 인터페이스

<br>

## 장치 주입 방식

CDI는 **주입할 장치를 선언적으로 정의**한다. Hook처럼 "어떤 프로그램을 실행할지"가 아니라 "무엇을 주입할지"를 YAML/JSON으로 명시한다.

<br>

### CDI Spec 경로

CDI 런타임은 다음 경로를 순서대로 검색한다.

1. `/etc/cdi/` - 시스템 전역 설정 (권장)
2. `/var/run/cdi/` - 동적으로 생성된 spec (런타임 생성)
3. 추가 경로는 런타임 설정으로 지정 가능

파일명 형식은 `vendor-class.yaml` 또는 `vendor-class.json`이다. 예: `nvidia-gpu.yaml`, `amd-gpu.yaml`

<br>

### CDI Spec 정의

CDI spec은 YAML 또는 JSON 형식으로 작성한다.


```yaml
cdiVersion: "0.5.0"
kind: nvidia.com/gpu              # 장치 타입 (vendor.com/class)

devices:
  - name: "0"                     # 장치 이름
    containerEdits:
      deviceNodes:                # 장치 파일
        - path: /dev/nvidia0
          type: c
          major: 195
          minor: 0

      mounts:                     # 마운트할 파일/디렉토리
        - hostPath: /usr/lib/x86_64-linux-gnu/libcuda.so.1
          containerPath: /usr/lib/x86_64-linux-gnu/libcuda.so.1
          options: ["ro", "nosuid", "nodev", "bind"]

      env:                        # 환경변수
        - "CUDA_VISIBLE_DEVICES=0"
```

| 필드 | 설명 |
|-----|------|
| `deviceNodes` | 컨테이너에 생성할 장치 파일 |
| `mounts` | 마운트할 파일/디렉토리 (라이브러리 등) |
| `env` | 설정할 환경변수 |
| `hooks` | 추가로 실행할 Hook (선택적) |

<br>

### 장치 참조

CDI는 `vendor.com/class=name` 형식으로 장치를 참조한다.

```
# 형식
vendor.com/class=device-name

# 예시
nvidia.com/gpu=0           # NVIDIA GPU 0번
nvidia.com/gpu=1           # NVIDIA GPU 1번
amd.com/gpu=GPU-abc123     # AMD GPU (UUID)
intel.com/fpga=acl0        # Intel FPGA
```

| 장치 | CDI Kind | 참조 예시 |
|-----|----------|----------|
| NVIDIA GPU | `nvidia.com/gpu` | `nvidia.com/gpu=0` |
| AMD GPU | `amd.com/gpu` | `amd.com/gpu=0` |
| Intel FPGA | `intel.com/fpga` | `intel.com/fpga=acl0` |
| Mellanox RDMA | `mellanox.com/rdma` | `mellanox.com/rdma=mlx5_0` |

Kubernetes Pod에서는 Device Plugin이 이 형식을 사용해 장치를 할당한다.

```yaml
spec:
  containers:
  - name: gpu-container
    resources:
      limits:
        nvidia.com/gpu: 1   # CDI 런타임이 nvidia.com/gpu=0 주입
```

<br>

### 실행 흐름

CDI-aware 런타임이 CDI spec을 직접 해석한다. 런타임 래퍼가 필요 없다.

```
Container Runtime (CDI-aware)
  ↓ (reads /etc/cdi/*.yaml)
CDI Spec ← 명시적/선언적: 내용 확인 가능
  ↓ (parses & applies)
runc (directly)
  ↓
Device mounted
```

<br>

### CDI Spec 생성

CDI spec은 벤더가 제공하는 도구로 생성한다.

```bash
# NVIDIA: nvidia-ctk으로 CDI spec 생성
nvidia-ctk cdi generate \
  --output=/etc/cdi/nvidia.yaml \
  --device-name-strategy=index

# 생성된 spec 확인
nvidia-ctk cdi list
```

생성된 spec을 확인하면 어떤 장치가 주입되는지 명확히 알 수 있다.

<br>

### 사용 예시

```bash
# Docker에서 CDI 장치 사용
docker run --runtime=nvidia \
  --device=nvidia.com/gpu=0 \
  nvidia/cuda:12.0-base \
  nvidia-smi
```

```yaml
# Kubernetes Pod에서 CDI 장치 사용
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  containers:
  - name: cuda-container
    image: nvidia/cuda:12.0-base
    resources:
      limits:
        nvidia.com/gpu: 1   # Device Plugin이 CDI 장치 할당
```

<br>

### 사용 사례

| 분류 | CDI Kind |
|-----|----------|
| GPU | `nvidia.com/gpu`, `amd.com/gpu`, `intel.com/gpu` |
| FPGA | `xilinx.com/fpga`, `intel.com/fpga` |
| 네트워크 | `mellanox.com/rdma`, `sriov.com/nic` |
| 스토리지 | `nvme.com/device` |

<br>

## OCI Runtime Hook과 비교

| 측면 | OCI Runtime Hook | CDI |
|-----|-----------------|-----|
| 패러다임 | 명령형(imperative) | 선언형(declarative) |
| 정의 방식 | 실행할 프로그램 지정 | 주입할 리소스 선언 |
| 런타임 지원 | 런타임별로 다름 | 모든 CDI 지원 런타임 |
| 런타임 래퍼 | 필요 | 불필요 |
| 벤더 확장 | 각자 구현 (파편화) | 표준 포맷 (통일) |
| 디버깅 | 동적 변경으로 어려움 | 정적 파일로 쉬움 |
| 표준화 | 없음 (사실상 표준) | CNCF 공식 표준 |
| Kubernetes 통합 | 간접적 | Device Plugin과 직접 통합 |

<br>

### 공존

OCI Runtime Hook과 CDI는 공존할 수 있다. CDI spec 자체에 `hooks` 필드가 있어서, 선언적 정의로 부족한 경우 Hook을 추가로 실행할 수 있다.

```yaml
containerEdits:
  deviceNodes:
    - path: /dev/nvidia0
  hooks:                         # 선택적 Hook
    - hookName: createContainer
      path: /usr/bin/gpu-setup
      args: ["gpu-setup", "init"]
```

복잡한 장치의 경우 CDI로 기본 장치/라이브러리를 선언하고, Hook으로 추가 초기화를 수행하기도 한다.

<br>

## 장점


### 런타임 중립성

동일한 CDI spec을 containerd, CRI-O, podman 등 모든 CDI-aware 런타임이 사용한다. 런타임이 CDI만 구현하면 모든 장치를 지원할 수 있다.


### 벤더 중립성

모든 하드웨어 벤더가 동일한 방식으로 장치를 정의한다. Kubernetes가 벤더 무관하게 장치를 스케줄링할 수 있다.

```bash
# NVIDIA
nvidia.com/gpu=0

# AMD
amd.com/gpu=0

# Intel FPGA
intel.com/fpga=0
```


### 투명성

CDI spec 파일을 보면 정확히 무엇이 주입되는지 알 수 있다. Hook 방식과 달리 런타임에 뭐가 주입되는지 명확하다.


### GitOps 적용 가능

spec 파일 자체의 버전 관리가 가능하다. 선언적 방식이므로 GitOps 워크플로우에 적합하다.

<br>

# 결론

CDI 방식의 도입은 컨테이너 생태계 성숙에 따른 자연스러운 진화라고 볼 수 있다. Hook 방식의 한계를 극복하고, 클라우드 네이티브 환경에 맞는 선언적이고 표준화된 접근으로 발전했다.

- **2015-2017**: Docker 중심, OCI Runtime Spec과 Hook 방식 도입
- **2019-2021**: Kubernetes 대중화, CDI 스펙 개발
- **2022-현재**: CDI가 새로운 표준으로 자리잡음


<br>

## 현황

다만, 두 방식은 현재 공존하고 있다.

- **OCI Runtime Hook**: 여전히 널리 사용됨
  - 레거시 시스템과의 호환성 유지
  - 점진적으로 CDI 방식으로 마이그레이션 중
- **CDI**: 새로운 표준으로 자리잡음
  - Kubernetes 생태계에서 권장
  - GPU Operator, Device Plugin 등 CDI 지원 추가

<br>

# 정리

| 측면 | OCI Runtime Hook | CDI |
|-----|-----------------|-----|
| 패러다임 | 명령형 | 선언형 |
| 표준화 | 사실상 표준 | CNCF 공식 표준 |
| 런타임 래퍼 | 필요 | 불필요 |
| 디버깅 | 어려움 | 쉬움 |
| Kubernetes 통합 | 간접적 | Device Plugin과 직접 통합 |

<br>

# 참고 자료

- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec)
- [OCI Runtime Spec - Runtime and Lifecycle](https://github.com/opencontainers/runtime-spec/blob/main/runtime.md)
- [Container Device Interface (CDI)](https://github.com/cncf-tags/container-device-interface)
- [CDI Spec](https://github.com/cncf-tags/container-device-interface/blob/main/SPEC.md)

