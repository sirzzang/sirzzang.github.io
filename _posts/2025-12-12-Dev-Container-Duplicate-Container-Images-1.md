---
title:  "[Container] Docker와 containerd 이미지 관리 비교 - 1. 배경지식"
excerpt: 컨테이너 런타임(dockerd, containerd)의 구조, 스토리지 드라이버 구현 비교, 런타임 CLI에 대해 알아보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - container
  - docker
  - containerd
  - container-runtime
  - overlayfs
  - storage-driver
  - cri

---

<br>

# TL;DR

k3s 클러스터에서 동일한 이미지를 `docker`와 `crictl`로 확인했을 때, 이미지 이름과 크기가 다르게 나타났다.

```bash
$ docker images | grep co-detr
co-detr-coco-app                1.0    f05ffb0c16af   20.3GB
$ sudo crictl images | grep co-detr
docker.io/co-detr-coco-app      1.0    f05ffb0c16af   10.4GB
```

이 현상을 분석하려면, 각 CLI가 어떤 런타임과 통신하고 이미지가 어떻게 저장되는지 알아야 한다. 이 글에서는 분석에 필요한 배경 지식을 정리한다.

1. **컨테이너 런타임**: dockerd와 containerd는 독립적으로 이미지를 관리하며, 저장 경로가 다르다
2. **스토리지 드라이버**: Docker의 overlay2와 containerd의 overlayfs snapshotter는 디렉토리 구조가 다르다
3. **CLI 도구**: docker, ctr, crictl은 각각 다른 런타임 및 인터페이스와 통신한다

> 컨테이너 이미지의 기본 개념(정의, 레이어 구조, 이미지 ID, 레지스트리)은 [컨테이너 이미지]({% post_url 2026-02-28-CS-Container-Image %})를, 컨테이너 파일 시스템(OverlayFS, Copy-on-Write, 스토리지 드라이버)은 [컨테이너 파일 시스템]({% post_url 2026-03-01-CS-Container-Filesystem %})을 참고한다.

<br>

# 컨테이너 런타임

컨테이너 런타임이란, **컨테이너를 생성·실행·관리하는 시스템**을 말한다. 이미지를 기반으로 격리된 프로세스를 생성하고, 그 생명주기를 관리하는 역할을 한다. 넓은 의미에서는 컨테이너 관리뿐만 아니라, 이미지 pull/push, 네트워킹, 스토리지 관리까지 포함한다. 대표적으로 Docker runtime (dockerd)과 containerd가 있다.

## dockerd

`dockerd`는 Docker 데몬으로, **containerd를 사용**한다. **컨테이너 실행은 containerd에 위임**하고, 빌드, 네트워킹, 볼륨 관리 등의 기능을 얹은 형태이다.

```
┌───────────────────────────────────────┐
│              dockerd                  │
│  ┌────────┬─────────┬──────────────┐  │
│  │ Build  │ Network │ Volume Mgmt  │  │  <- Docker 추가 기능
│  └────────┴─────────┴──────────────┘  │
│              ↓ (사용)                  │
│  ┌──────────────────────────────────┐ │
│  │      containerd (별도 프로세스)     │ │  <- 컨테이너 런타임
│  └──────────────────────────────────┘ │
└───────────────────────────────────────┘
```

> 참고: 왜 이런 구조가 되었는가?
>
> 역사적인 이유다. 
> - **초기 Docker**: 모든 기능(이미지 관리, 컨테이너 실행, 빌드, 네트워킹 등)이 `dockerd` 하나의 프로세스에 통합되어 있었다.
> - **containerd 분리**: 이후 컨테이너 런타임 부분만 분리되어 `containerd`가 별도 프로세스로 탄생했다.
> - **현재 구조**: Docker는 하위 호환성을 위해 이미지 관리는 기존 방식(`/var/lib/docker`)을 유지하고, `containerd`에는 **컨테이너 실행 부분만 위임**하는 구조가 되었다. 따라서 `containerd`는 별도 프로세스이지만, `dockerd`가 `containerd`의 API를 호출하여 사용하는 관계이다.

<br>

## containerd

`containerd`는 **순수 컨테이너 런타임**이다. 이미지 pull, 컨테이너 생성·실행 등 핵심 기능만 담당하며, 빌드 기능은 없다.

```
Image storage: /var/lib/containerd
    ↓
containerd (default namespace)
    ↓
Container execution
```

### containerd의 네임스페이스

containerd는 내부적으로 **네임스페이스**를 사용하여 이미지와 컨테이너를 격리 관리한다. 누가 containerd를 사용하느냐에 따라 다른 네임스페이스에 저장된다.

| 사용 주체 | 네임스페이스 |
|----------|-------------|
| Docker (dockerd) | `moby` |
| Kubernetes | `k8s.io` |
| 미지정 시 기본값 | `default` |

> 참고: Kubernetes와 containerd
>
> Kubernetes 환경에서는 네트워크, 볼륨 관리 등을 Kubernetes가 담당하므로, 순수 런타임인 containerd만으로 충분하다. 이것이 Kubernetes가 Docker 의존성을 제거하고 containerd를 직접 사용하게 된 배경이다.

### containerd의 저장 구조

containerd는 이미지를 두 단계로 관리한다:
1. **Content Store**: 이미지 blob(레이어 tar.gz 등)을 압축 상태로 저장
  - 경로: `io.containerd.content.v1.content/blobs/sha256/`
2. **Snapshotter**: 컨테이너 실행 시 레이어를 압축 해제하여 파일시스템으로 제공
  - 경로: `io.containerd.snapshotter.v1.overlayfs/snapshots/`

<br>

## Docker runtime vs containerd 비교

| 항목 | Docker runtime (dockerd) | containerd |
|------|---------|------------|
| 역할 | 풀스택 컨테이너 플랫폼 | 순수 컨테이너 런타임 |
| 빌드 기능 | O | X |
| 이미지 저장 경로 | `/var/lib/docker` | `/var/lib/containerd` |
| Kubernetes 연동 | cri-dockerd(과거 dockershim, 현재 제거됨) | CRI로 직접 연동 |

> 참고: dockerd의 네임스페이스
> - dockerd는 자체적으로 네임스페이스 개념이 없지만, 내부적으로 containerd를 사용할 때 `moby` 네임스페이스를 사용함
> - 다만 dockerd는 이미지를 containerd가 아닌 `/var/lib/docker`에서 자체 관리하므로, containerd의 `moby` 네임스페이스에서 Docker 이미지를 **직접 볼 수는 없음**


<br>

# 실제 디렉토리 구조 확인

호스트에서 실제로 각 컨테이너 런타임의 스토리지 드라이버가 생성한 디렉토리 구조를 확인해 볼 수 있다. Docker의 overlay2와 containerd의 overlayfs snapshotter 모두 커널의 OverlayFS를 사용하므로, CoW 등 파일 시스템 동작은 동일하다. 차이는 레이어를 디스크에 어떤 구조로 저장하고 관리하느냐에 있다.

## Docker runtime (dockerd) - overlay2

Docker runtime(dockerd)은 overlay2를 통해 각 레이어를 관리한다. 각 레이어는 layer-id로 식별되며, `merged/` 디렉토리가 OverlayFS 마운트 포인트 역할을 한다.
- 호스트 마운트 경로: `/var/lib/docker/overlay2/{container-layer-id}/merged/`


### 1. 이미지 레이어 확인

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

### 2. 컨테이너 레이어 확인 (실행 중인 컨테이너)

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

### 3. OverlayFS 마운트 정보 확인

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

### 4. merged/ 디렉토리 확인

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

### 5. OverlayFS의 lower/upper와 overlay2의 매핑
- **이미지 레이어의 `diff/`**: 해당 레이어의 파일 변경 사항을 저장. OverlayFS 마운트 시 **lower** 역할을 수행
- **컨테이너 쓰기 레이어의 `diff/`**: 컨테이너에서 발생한 변경 사항을 저장. OverlayFS 마운트 시 **upper** 역할을 수행
- **`merged/`**: OverlayFS 마운트 포인트로, lower와 upper를 통합한 뷰를 제공

<br>

## containerd (overlayfs snapshotter)

containerd는 overlayfs snapshotter를 통해 각 레이어를 snapshot으로 관리한다. Docker의 overlay2와 달리, 이미지 데이터를 **Content Store**와 **Snapshotter** 두 단계로 관리한다.

### 1. Content Store (이미지 blob 저장)

이미지 pull 시 레이어 `tar.gz`, manifest, config 등의 blob이 Content Store에 압축 상태로 저장된다.

```bash
$ ls /var/lib/containerd/io.containerd.content.v1.content/blobs/sha256/
a1b2c3d4e5f6...   # 이미지 manifest
b2c3d4e5f6a1...   # 이미지 config
c3d4e5f6a1b2...   # 레이어 tar.gz (압축 상태)
d4e5f6a1b2c3...   # 레이어 tar.gz
...

# blob은 sha256 해시로 식별되며, 압축된 원본 그대로 저장
$ file /var/lib/containerd/io.containerd.content.v1.content/blobs/sha256/c3d4e5f6a1b2...
c3d4e5f6a1b2...: gzip compressed data
```

Docker의 overlay2는 Content Store 없이 레이어를 바로 `diff/` 디렉토리에 풀어서 저장하는 반면, containerd는 원본 blob을 별도로 보관한다.

### 2. Snapshot (레이어 압축 해제)

Snapshotter가 Content Store의 레이어를 압축 해제하여 snapshot 디렉토리로 만든다. 각 snapshot은 숫자 ID로 식별된다.

```bash
$ ls /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/
1/   2/   3/   4/   5/   ...
```

snapshot에는 두 종류가 있다.

- **Committed snapshot** (이미지 레이어): 읽기 전용. `fs/`에 해당 레이어의 파일이 직접 들어 있다. Docker의 `diff/`에 해당.
- **Active snapshot** (컨테이너 쓰기 레이어): 컨테이너 실행 시 생성. `fs/`가 OverlayFS 마운트 포인트(merged)로 사용된다.

```bash
# Committed snapshot (이미지 레이어) - fs/에 해당 레이어 파일이 직접 존재
$ ls /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/1/
├── fs/        # 이 레이어의 파일들 (Docker의 diff/에 해당)
│   ├── bin/
│   ├── etc/
│   ├── lib/
│   └── ...
└── work/

# Active snapshot (컨테이너 쓰기 레이어) - fs/가 OverlayFS merged 뷰
$ ls /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/5/
├── fs/        # OverlayFS 마운트 포인트 (merged 뷰, 컨테이너 실행 중에만 마운트됨)
│   ├── bin/
│   ├── dev/
│   ├── etc/
│   └── ...
└── work/
```

> `fs/`의 역할이 snapshot 종류에 따라 다르다는 점이 Docker와의 핵심 차이다. Docker는 `diff/`(레이어 내용)와 `merged/`(통합 뷰)가 명확히 분리되어 있지만, containerd는 `fs/` 하나가 committed에서는 레이어 내용, active에서는 merged 뷰 역할을 한다.


### 3. Snapshot 간 parent 관계

Docker의 `lower` 파일처럼, containerd도 snapshot 간 부모-자식 관계를 관리한다. 다만 파일 시스템이 아닌 containerd의 메타데이터 DB(boltdb)에서 관리한다.

```bash
# ctr로 snapshot 목록과 parent 관계 확인
$ ctr -n k8s.io snapshots ls
KEY                                      PARENT                                   KIND
sha256:a1b2c3...                                                                  Committed
sha256:b2c3d4...                         sha256:a1b2c3...                         Committed
sha256:c3d4e5...                         sha256:b2c3d4...                         Committed
container-abc123                         sha256:c3d4e5...                         Active

# KIND: Committed = 이미지 레이어 (읽기 전용), Active = 컨테이너 쓰기 레이어
# PARENT: 이 snapshot이 기반으로 하는 하위 레이어
```

### 4. OverlayFS 마운트 정보 확인

Docker와 마찬가지로 `mount` 명령으로 확인할 수 있다.

```bash
$ mount | grep 'containerd.*overlay'
overlay on /run/containerd/io.containerd.runtime.v2.task/.../rootfs type overlay (
  rw,relatime,
  lowerdir=.../snapshots/3/fs:.../snapshots/2/fs:.../snapshots/1/fs,
  upperdir=.../snapshots/5/fs,
  workdir=.../snapshots/5/work
)
```

Docker와 비교하면:
- **lowerdir**: `snapshots/{id}/fs` (committed snapshot들의 `fs/`)
- **upperdir**: active snapshot의 `fs/`
- **마운트 포인트**: `/run/containerd/.../rootfs` (Docker는 `overlay2/{id}/merged`)


### 5. Docker overlay2와의 비교 요약

| 항목 | Docker overlay2 | containerd overlayfs snapshotter |
|------|----------------|----------------------------------|
| 원본 blob 보관 | 없음 (바로 압축 해제) | Content Store에 별도 보관 |
| 레이어 식별 | layer-id (해시) | 숫자 ID |
| 레이어 내용 디렉토리 | `diff/` | `fs/` (committed snapshot) |
| 통합 뷰 디렉토리 | `merged/` | `fs/` (active snapshot) |
| 레이어 관계 관리 | `lower` 파일 (텍스트) | 메타데이터 DB (boltdb) |
| 마운트 포인트 | `/var/lib/docker/overlay2/{id}/merged` | `/run/containerd/.../rootfs` |

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
> [위에서 설명했듯이](#containerd의-네임스페이스), dockerd는 containerd를 사용할 때 `moby` 네임스페이스를 사용하지만, 이미지는 containerd가 아닌 `/var/lib/docker`에서 자체 관리한다. 따라서 `ctr`로 moby 네임스페이스를 조회해도 Docker 이미지를 볼 수 없다.
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

CRI(Container Runtime Interface) 인터페이스를 통해 통신하는 CLI이다. containerd 전용이 아니라, CRI를 구현한 모든 런타임(containerd, CRI-O 등)과 통신할 수 있는 범용 도구이다.

쿠버네티스/CRI 생태계 도구로, k3s 설치 시 함께 설치된다.

> 참고: crictl에는 빌드 기능이 없다. pull, run, inspect 등 런타임 조작만 가능하다. containerd 환경에서 이미지를 빌드하려면 BuildKit, kaniko, nerdctl 등 별도 빌드 도구가 필요하다.

<br>

## k8s/k3s 환경에서의 권장 CLI

k8s/k3s 환경에서는 **crictl**을 사용하는 것이 적합하다.

- 쿠버네티스가 CRI를 통해 containerd와 통신하므로, crictl을 사용하면 **쿠버네티스가 보는 것과 동일한 뷰**를 볼 수 있다.
- ctr을 사용할 경우, containerd의 모든 네임스페이스를 볼 수 있어 쿠버네티스에서 사용하지 않는 이미지까지 보일 수 있다.

<br>

# 정리

이 글에서 다룬 배경 지식을 요약하면 다음과 같다.

| 항목 | 핵심 내용 |
|------|-----------|
| 컨테이너 런타임 | dockerd는 containerd를 내부적으로 사용하지만, 이미지는 독립적으로 관리. 저장 경로가 다르다 |
| 스토리지 드라이버 | Docker overlay2는 레이어를 바로 압축 해제하여 `diff/`에 저장. containerd는 Content Store에 압축 보관 후 Snapshotter가 `fs/`로 해제 |
| CLI 도구 | docker(dockerd), ctr(containerd 네이티브), crictl(CRI 인터페이스). k8s 환경에서는 crictl 사용 권장 |

처음에 확인한 현상을 다시 살펴보면:
- **이름 차이**(`co-detr-coco-app` vs `docker.io/co-detr-coco-app`): 런타임마다 이미지 이름 표시 방식이 다르기 때문
- **크기 차이**(20.3GB vs 10.4GB): 런타임마다 크기 계산 기준(압축 해제 vs 압축 상태)이 다르기 때문
- **중복 저장**: 각 런타임이 독립적인 경로에 이미지를 저장하기 때문

[다음 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-2 %})에서는 이 배경 지식을 바탕으로, 동일한 이미지가 왜 중복 저장되고 다른 크기로 보이는지 실제 분석 과정을 다룬다.

<br>