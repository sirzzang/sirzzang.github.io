---
title:  "[Container] Docker와 containerd 이미지 관리 비교 - 2. 컨테이너 파일 시스템과 CLI"
excerpt: 컨테이너 파일 시스템, CLI에 대해 알아 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - container
  - docker
  - containerd
  - overlayfs
  - storage-driver
  - cri

---


동일한 이미지를 `docker`와 `crictl`로 확인했을 때 크기가 다르게 나타난 현상을 분석하면서, 컨테이너에 대한 배경 지식을 정리했다. 이 글에서는 [이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %})에 이어, **컨테이너 파일 시스템과 CLI**를 다루고, 다음 글에서 **실제 분석 과정**을 다룬다.


<br>

# 컨테이너 파일 시스템

[이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %})에서 이미지의 Layers는 `tar.gz` 형태로 압축되어 저장되어 있다고 했다.

 컨테이너 실행 시, 컨테이너 런타임은 **스토리지 드라이버**를 통해 이 레이어들을 압축 해제하고, OverlayFS 등의 Union File System을 활용하여 여러 레이어를 하나의 통합된 파일시스템으로 마운트한다. 이렇게 마운트된 파일시스템이 컨테이너의 루트(`/`) 파일시스템이 된다. 현재 대부분의 환경에서 OverlayFS 기반 스토리지 드라이버가 기본으로 사용된다.

컨테이너 시스템이 이미지 레이어 관리에 Union File System 기반 구조를 채택한 것은, 불변성, 공유, 효율성, 속도 등 컨테이너가 추구하는 철학과 Union File System의 특성이 **딱 맞아 떨어지기 때문**이다.

<br>

## Union File System

여러 디렉토리를 하나로 합쳐서 보여 주는 파일 시스템이다.

```
Layer 3 (top)   ──┐
Layer 2         ──┼──  Unified filesystem view
Layer 1 (base)  ──┘
```

이를 기반으로 한 컨테이너 파일 시스템 구조는 아래와 같다. 즉, Union File System을 이용해 이미지 레이어가 컨테이너 파일시스템으로 구성되는 방식은 다음과 같다.

```
[Container Filesystem]
Writable Layer (per container)  ←─ Writable, changes
    │
Image Layer 3        ──┐
Image Layer 2        ──┼───────── Read-only, shared
Image Layer 1 (base) ──┘
```
- **이미지 레이어**: 읽기 전용이며, 여러 컨테이너가 공유할 수 있음
- **쓰기 레이어**: 컨테이너별로 변경 사항을 기록하기 위한 레이어
- **컨테이너 파일 시스템**: 이미지 레이어 위에 쓰기 레이어를 얹은 통합 뷰

<br>

## 컨테이너 설계 철학

Union file system은 컨테이너가 추구하는 설계 철학을 기술적으로 구현하는 수단이 된다.

1. **불변성(Immutability)**: 서로 다른 컨테이너가 베이스 이미지 레이어를 공유하나, 읽기 전용이기 때문에 이미지의 불변성이 보장된다.
  ```
  Container A (writable layer)  ──┐
                                  ├── Shared image layers (read-only)
  Container B (writable layer)  ──┘
  ```
2. **디스크 효율성**: 같은 베이스 이미지를 쓰는 컨테이너가 100개 실행되더라도, 베이스 레이어는 한 번만 저장하면 된다.
3. **빠른 컨테이너 생성**: 컨테이너를 시작할 때 이미지 전체를 복사하지 않고, 얇은 쓰기 레이어만 추가하면 되므로 빠른 생성이 가능하다.
4. **레이어 캐싱**: 이미지 빌드 시에도 변경된 레이어만 새로 만들면 된다. 이전 레이어를 재사용할 수 있다.

<br>

## OverlayFS

리눅스 커널에 내장된 Union File System 구현체이다.

```
Upper (writable)    ──┐
                      ├──  Merged (unified single view)
Lower (read-only)   ──┘
```
<br>

OverlayFS는 아래와 같은 디렉토리 구조로 이루어진다.
- Lower: **읽기 전용** 베이스 레이어
- Upper: 변경 사항이 기록되는 **쓰기 가능** 레이어
- Work: 파일 변경 작업 시 중간 상태를 숨기기 위해 사용하는 임시 디렉토리
- Merged: Lower와 Upper를 합친 통합된 파일시스템 뷰 (컨테이너가 보는 뷰)

<br>

변경 사항이 발생하면 Lower는 건드리지 않고, Upper에만 기록된다. 이를 **Copy-on-Write (CoW)** 방식이라 한다.
- **파일 읽기**: Lower에서 직접 읽는다.
- **파일 수정**: Lower의 파일을 Upper로 복사한 후 수정한다.
- **파일 삭제**: Upper에 "whiteout" 파일을 생성하여 삭제를 표시한다.

> 참고: OverlayFS는 범용
>
> - 컨테이너 위주로 이야기하고 있어 관심이 쏠리기 쉽지만, OverlayFS는 컨테이너 전용이 아니다. 
> - OverlayFS는 범용 Union File System 구현체인데, 컨테이너 엔진이 이미지 관리를 위해 OverlayFS를 사용하는 것이다. 
> - 컨테이너 외에도 Live CD/USB(베이스는 읽기 전용, 변경사항만 메모리에), Embedded 시스템, 루트 파일시스템 보호 등에서도 사용된다.

<br>


## 스토리지 드라이버

각 컨테이너 시스템은 자체 스토리지 드라이버를 가지고 있다. 스토리지 드라이버란, **이미지 레이어를 디스크에 어떻게 저장하고 관리할지 정의하는 모듈**이다.

> 참고: 드라이버의 의미
> 
> 드라이버는 원래 무언가를 구동/제어하는 소프트웨어라는 넓은 의미를 가진다.
> - 장치 드라이버 (USB, GPU 등): 하드웨어 ↔ OS 간 통신
> - 스토리지 드라이버: 데이터 저장 방식 정의
> - 데이터베이스 드라이버: 애플리케이션 ↔ DB 간 통신 

<br>
```
Container Runtime
      ↓
Storage Driver
      ↓
Filesystem (ext4, xfs, etc.)
      ↓
Disk (hardware)
```
스토리지 드라이버의 역할은 다음과 같다:
1. **컨테이너 런타임이 pull한** 레이어를 디스크에 저장 (일반 파일시스템 사용)
2. **컨테이너 런타임의 요청에 따라** 컨테이너 실행 시 OverlayFS를 통해 레이어들을 마운트
3. **컨테이너 프로세스에게** 통합된 파일시스템 뷰 제공

<br>

### 마운트 

OverlayFS는 커널에 내장된 파일시스템이므로, 사용하려면 `mount` 시스템 콜을 통해 마운트해야 한다.

이 마운트 작업이 의미하는 것은 아래와 같다.
1. **호스트 관점**: 호스트 커널이 OverlayFS를 `마운트 포인트`에 마운트
  - OverlayFS(파일 시스템)가 호스트의 `마운트 포인트`에 마운트됨
  - 실제로 이 디렉토리는 lower(이미지 레이어들)와 upper(쓰기 레이어)가 합쳐진 통합 파일 시스템 뷰
2. **컨테이너 관점**: 컨테이너 프로세스가 시작될 때, 마운트 포인트 디렉토리가 컨테이너의 루트 파일 시스템(`/`)으로 설정됨
  - 컨테이너 내부에서 `/`를 보면, 실제로는 호스트의 마운트 포인트 디렉토리 내용을 보는 것임

<br>

컨테이너 실행 시, 컨테이너 런타임이 스토리지 드라이버를 이용해 내부적으로 다음과 같은 마운트 작업을 수행한다.
```bash
mount -t overlay overlay \
  -o lowerdir=/lower,upperdir=/upper,workdir=/work \
  /merged # 마운트 포인트
```

<br>

컨테이너 실행 시 아래와 같은 일이 일어난다.
1. 호스트 커널이 OverlayFS를 호스트의 `마운트 포인트`에 마운트
2. 컨테이너 프로세스 시작 시, 호스트의 `마운트 포인트`를 컨테이너 파일 시스템 루트(`/`)로 설정
결과는 다음과 같다.
```
호스트:    마운트포인트/bin/bash
                 ↓
컨테이너:           /bin/bash
```

<br>

### 구현체

컨테이너 런타임별로 자체 스토리지 드라이버 구현을 가지고 있다.

```
                     OverlayFS (kernel)
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   dockerd          containerd        Podman/CRI-O
   overlay2         snapshotter       overlay driver
```

> 참고: containerd는 "스토리지 드라이버" 대신 **"snapshotter"**라는 용어를 사용하지만, 역할은 동일하다.

<br>

| 런타임 | 스토리지 드라이버 명칭 | 저장 경로 | 레이어 식별 | 마운트 포인트 |
|--------|------------------------|----------|------------|--------------|
| dockerd | overlay2 | `/var/lib/docker/overlay2/` | layer-id (해시) | `merged/` |
| containerd | overlayfs snapshotter | `/var/lib/containerd/.../overlayfs/` | 숫자 ID | `fs/` |

즉, 컨테이너 시스템은 이미지 레이어를 관리하기 위해 모두 공통적으로 OverlayFS를 활용하지만:

- 각 시스템별로 OverlayFS 기반의 자체 스토리지 드라이버 구현체를 가지고 있으며,
- 각 구현체별로 레이어 디렉토리 구조, 메타데이터 관리 방식, 저장 경로 등이 다르다.
<br>
dockerd가 사용하는 overlay2를 예로 들면, overlay2는 dockerd에서 **OverlayFS라는 커널 기능을 컨테이너 레이어 관리 목적에 맞게 활용하기 위해 만든 스토리지 드라이버**라고 할 수 있다.

```
OverlayFS (범용 Union File System 구현체)
  ↓  사용 방식 정의
overlay2 (dockerd storage driver)
  - Per-layer directory structure (diff/, link/, work/, etc.)
  - Metadata management (lower, upper path tracking)
  - Layer caching strategy (build cache optimization)
```

<br>

## 실제 디렉토리 구조 확인

호스트에서 실제로 각 컨테이너 런타임의 스토리지 드라이버가 생성한 디렉토리 구조를 확인해 볼 수 있다.

### dockerd (overlay2)

dockerd는 overlay2를 통해 각 레이어를 관리한다. 각 레이어는 layer-id로 식별되며, `merged/` 디렉토리가 OverlayFS 마운트 포인트 역할을 한다.
- 호스트 마운트 경로: `/var/lib/docker/overlay2/{container-layer-id}/merged/`

<br>

**1. 이미지 레이어 확인**

이미지 레이어는 읽기 전용이므로 `diff/`, `link/`, `lower/`, `work/`만 존재한다.

```bash
$ ls -al /var/lib/docker/overlay2/{layer-id}/
├── diff/      # 이 레이어의 파일 변경 사항
├── link       # 이 레이어의 심볼릭 링크 ID
├── lower      # 이 레이어의 하위 레이어 목록
└── work/      # OverlayFS 작업 디렉토리

# lower 파일: 하위 레이어들이 `:` 로 구분되어 나열됨
# l/ 디렉토리는 긴 layer-id를 짧게 표현한 심볼릭 링크
$ cat /var/lib/docker/overlay2/{layer-id}/lower
l/MRT27FB56...:l/W4RDG2UV...:l/XX4MFEJP...:...  

# diff/ 내부: 이 레이어에서 변경된 파일들만 존재
$ ls -al /var/lib/docker/overlay2/{layer-id}/diff/usr/local/bin
lrwxrwxrwx 1 root root 23 docker-enforce-initdb.sh -> docker-ensure-initdb.sh
```

<br>

**2. 컨테이너 레이어 확인 (실행 중인 컨테이너)**

컨테이너 실행 시 쓰기 레이어가 생성되며, `merged/` 디렉토리가 추가된다.

```bash
$ ls -al /var/lib/docker/overlay2/{container-layer-id}/
├── diff/      # 컨테이너에서 변경된 파일 (upper 역할)
├── link       
├── lower      # 모든 이미지 레이어 참조 (lower 역할)
├── merged/    # 통합된 파일시스템 뷰 (마운트 포인트)
└── work/      
```

`merged/` 디렉토리는 OverlayFS 마운트 포인트이므로, 컨테이너가 실행 중이 아니면 비어있거나 접근이 불가능할 수 있다. 호스트에서는 `diff/` 디렉토리를 통해 각 레이어의 내용을 확인할 수 있다.

<br>
**3. OverlayFS 마운트 정보 확인**

`mount` 명령으로 lower, upper, merged가 어떻게 마운트되었는지 확인할 수 있다.

```bash
# 실제 실행 결과
$ mount | grep 9b6f469c
overlay on /var/lib/docker/overlay2/9b6f469c.../merged type overlay (
  rw,relatime,
  lowerdir=.../l/MRT27FB56...:...l/W4RDG2UV...:...(15개 레이어),
  upperdir=.../9b6f469c.../diff,
  workdir=.../9b6f469c.../work,
  nouserxattr
)

# 요약
overlay on .../merged type overlay (
  lowerdir=레이어N:...:레이어1,   ← 읽기 전용 이미지 레이어들 (lower)
  upperdir=.../diff,           ← 쓰기 가능 컨테이너 레이어 (upper)
  workdir=.../work
)
```

<br>

**4. merged/ 디렉토리 확인**

`merged/`는 lower와 upper를 통합한 뷰를 제공하며, 컨테이너 내부에서 보이는 파일시스템 루트(`/`)가 된다.

```bash
$ ls -al /var/lib/docker/overlay2/{container-layer-id}/merged/
bin -> usr/bin
boot/
dev/
etc/
home/
...
```

<br>

**5. OverlayFS의 lower/upper와 overlay2의 매핑:**
- **이미지 레이어의 `diff/`**: 해당 레이어의 파일 변경 사항을 저장. OverlayFS 마운트 시 **lower** 역할을 수행
- **컨테이너 쓰기 레이어의 `diff/`**: 컨테이너에서 발생한 변경 사항을 저장. OverlayFS 마운트 시 **upper** 역할을 수행
- **`merged/`**: OverlayFS 마운트 포인트로, lower와 upper를 통합한 뷰를 제공

<br>

### containerd (overlayfs snapshotter)

containerd는 snapshotter를 통해 각 레이어를 snapshot으로 관리한다. 각 snapshot은 숫자 ID로 식별되며, `fs/` 디렉토리가 OverlayFS 마운트 포인트 역할을 한다.

> 참고: containerd는 snapshotter 방식으로 레이어를 관리하므로, dockerd의 overlay2와는 디렉토리 구조가 다르다. `fs/` 디렉토리는 OverlayFS 마운트 포인트이며, 실제 파일시스템 내용을 포함한다. snapshot ID는 숫자로 관리된다.

```bash
$ ls -al /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/5
/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/{snapshot-id}/
├── fs/        # OverlayFS 마운트 포인트 (merged 역할, 실제 파일시스템 내용 포함)
│   ├── bin/
│   ├── dev/
│   ├── etc/
│   ├── lib/
│   └── ...
└── work/      # OverlayFS 작업 디렉토리
```

<br>

# 컨테이너 런타임 CLI

사용자 입장에서 각 컨테이너 런타임과 통신하기 위해 CLI 도구를 이용하게 된다. 대부분의 컨테이너 런타임은 Unix Socket을 통해 통신한다.

| CLI | 통신 대상 | 통신 방식 |
|-----|----------|----------|
| docker | dockerd | Docker API |
| ctr | containerd | containerd 네이티브 API |
| crictl | CRI 호환 런타임 | CRI 인터페이스 |

```
crictl  →  CRI 인터페이스     →  CRI 호환 런타임(containerd, CRI-O 등)
ctr     →  containerd API  →  containerd
docker  →  Docker API      →  dockerd     →  containerd
```

<br>

## docker

Docker 데몬(`dockerd`)과 통신하는 CLI이다. `dockerd`가 내부적으로 containerd를 사용하지만, 사용자는 Docker API를 통해 상호작용한다.

## ctr

containerd 네이티브 API로 직접 통신하는 저수준 CLI이다. containerd 패키지에 포함되어 있으며, Docker 설치 시 containerd가 함께 설치되면서 ctr도 같이 설치된다. containerd의 모든 네임스페이스에 접근할 수 있다.

> *참고*: moby 네임스페이스의 이미지 조회
>
> [1편에서 설명했듯이]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %}#containerd의-네임스페이스), dockerd는 containerd를 사용할 때 `moby` 네임스페이스를 사용하지만, 이미지는 containerd가 아닌 `/var/lib/docker`에서 자체 관리한다. 따라서 `ctr`로 moby 네임스페이스를 조회해도 Docker 이미지를 볼 수 없다.
>
> ```bash
> # moby 네임스페이스의 이미지 조회 (dockerd의 containerd 소켓 사용)
> $ sudo ctr -n moby images ls
> # ctr 기본 소켓: /run/containerd/containerd.sock (dockerd가 실행한 containerd)
> REF TYPE DIGEST SIZE PLATFORMS LABELS
> # (비어있음 - Docker는 이미지를 containerd가 아닌 /var/lib/docker에서 관리)
> ```

<br>

## crictl

CRI(Container Runtime Interface) 인터페이스를 통해 통신하는 디버깅 도구이다. containerd 전용이 아니라, CRI를 구현한 모든 런타임(containerd, CRI-O 등)과 통신할 수 있는 범용 도구이다.

쿠버네티스/CRI 생태계 도구로, k3s 설치 시 함께 설치된다.

> 참고: crictl에는 빌드 기능이 없다. pull, run, inspect 등 런타임 조작만 가능하다. containerd 환경에서 이미지를 빌드하려면 BuildKit, kaniko, nerdctl 등 별도 빌드 도구가 필요하다.

<br>

## k8s/k3s 환경에서의 권장 CLI

k8s/k3s 환경에서는 **crictl**을 사용하는 것이 적합하다.

- 쿠버네티스가 CRI를 통해 containerd와 통신하므로, crictl을 사용하면 **쿠버네티스가 보는 것과 동일한 뷰**를 볼 수 있다.
- ctr을 사용할 경우, containerd의 모든 네임스페이스를 볼 수 있어 쿠버네티스에서 사용하지 않는 이미지까지 보일 수 있다.

<br>
---

*다음 글에서는 이 배경 지식을 바탕으로, 동일한 이미지가 왜 중복 저장되고 다른 크기로 보이는지 실제 분석 과정을 다룬다.*

