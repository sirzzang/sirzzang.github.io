---
title:  "[Container] Docker와 containerd 이미지 관리 비교 - 3. 같은 이미지가 중복 저장된 이유"
excerpt: docker와 crictl에서 같은 이미지가 다른 크기로 보이는 현상을 분석해 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - container
  - docker
  - containerd
  - k3s
  - troubleshooting
  - disk-management

---

# TL;DR

k3s 클러스터에서 컨테이너 런타임을 Docker runtime에서 containerd로 변경한 뒤, 동일한 이미지가 **두 벌 저장**되어 디스크가 낭비되고 있었다. 같은 이미지인데 `docker`로 보면 20.3GB, `crictl`로 보면 10.4GB로 표시되었다.

```bash
$ docker images | grep co-detr
co-detr-coco-app                1.0    f05ffb0c16af   20.3GB
$ sudo crictl images | grep co-detr
docker.io/co-detr-coco-app      1.0    f05ffb0c16af   10.4GB
```

분석 결과는 다음과 같다.

1. **중복 저장**: 각 런타임이 독립적인 경로에 이미지를 저장하기 때문
   - `Docker runtime (dockerd)`: `/var/lib/docker/overlay2`
   - `containerd`: `/var/lib/containerd` 또는 `/var/lib/rancher/k3s/agent/containerd` (k3s)
2. **이름 차이**: Docker runtime(dockerd)은 `docker.io`를 생략하고, containerd는 fully qualified name으로 표시
3. **크기 차이**: 런타임별 계산 방식이 다름
   - `Docker runtime (dockerd)`: 압축 해제된 총 크기
   - `containerd`: 압축된 blob 크기 기반
4. **권장 사항**: k8s/k3s 환경에서는 `crictl`로 확인하는 것이 적합

<br>

---

이전 글에서 다룬 [컨테이너 이미지와 런타임]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %}), [컨테이너 파일 시스템과 CLI]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-2 %})에 대한 배경 지식을 바탕으로, 이 글에서는 **실제 분석 과정**을 다룬다.

<br>

# 문제

이미지 ID가 `f05ffb0c16af`로 같은 두 이미지를 각자 다른 CLI로 확인했는데, 이미지 크기가 다르다. 

```bash
$ sudo crictl images | grep co-detr
docker.io/co-detr-coco-app      1.0                       f05ffb0c16af                  10.4GB
$ docker images | grep co-detr
co-detr-coco-app                1.0                       f05ffb0c16af   8 months ago    20.3GB
```

**하나의 노드에 같은 이미지가 두 벌**있는 것은 목격하기 쉽지 않은 일이다. 
- 보통 로컬에서 이미지를 빌드하게 되면, 동일한 Dockerfile을 이용해 빌드하더라도 [이미지 ID]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %}#이미지-id)가 달라진다.
- 레지스트리에서 이미지를 pull하게 되더라도, 컨테이너 런타임이 같은 이미지가 있는지 확인한다. 같은 이미지가 있을 경우, 다운로드하지 않는다.

기존 레거시 k3s 클러스터에서 컨테이너 런타임으로 Docker runtime을 이용하고 있다가, k3s에 내장되어 있는 containerd를 이용하도록 변경하면서 발생한 일이다. k3s 클러스터가 **프라이빗 레지스트리를 이용하도록 미러링 설정**되어 있기 때문에, 두 이미지는 모두 프라이빗 레지스트리에서 pull해온 것이다. 
- `co-detr-coco-app:1.0`: 기존에 Docker runtime을 사용할 때 pull한 이미지
- `docker.io/co-detr-coco-app:1.0`: containerd 런타임을 사용하도록 변경하면서 pull한 이미지

<br>

노드에 장애가 생기지는 않았다. 다만, 습관처럼 루트 파티션 용량을 검사하다 70% 정도가 찬 것을 통해, 어디 크기가 큰 파일이 있는지 확인하다가 발견한 문제다. 결과적으로는 **같은 이미지가 중복 저장되어 디스크가 낭비**되고 있던 셈이다.

```bash
# docker 이미지 용량 확인
$ sudo du -sh /var/lib/docker/overlay2/
38G     /var/lib/docker/overlay2/
# k3s 내장 containerd 이미지 용량 확인
$ sudo du -sh /var/lib/rancher/k3s/agent/containerd/
73G     /var/lib/rancher/k3s/agent/containerd/
```

<br>

그런데 여기서 아래와 같은 의문이 발생한다.
- 어떻게 동일한 이미지가 중복 저장될 수 있었는가?
- 어떻게 동일한 이미지의 이름이 다르게 나타날 수 있는가?
- 어떻게 동일한 이미지의 크기가 다르게 나타날 수 있는가?


<br>

# 분석

## 서버 환경 설명

### 두 개의 containerd 인스턴스

dockerd와 k3s가 설치되어 있기 때문에, 이 서버에는 두 개의 `containerd` 인스턴스가 실행 중이다.

```bash
1. dockerd
   └── dockerd (/var/run/docker.sock)
       └── containerd (/run/containerd/containerd.sock) # dockerd가 실행
2. k3s
   └── k3s 내장 containerd (/run/k3s/containerd/containerd.sock) # k3s가 내장
```

실제로 실행 중인 containerd-shim 프로세스를 확인하면 두 개의 containerd 인스턴스가 동시에 실행 중임을 확인할 수 있다:

```bash
$ ps aux | grep containerd-shim | grep sock
# Docker의 containerd (namespace: moby)
root  /usr/bin/containerd-shim-runc-v2 -namespace moby -id ... -address /run/containerd/containerd.sock
root  /usr/bin/containerd-shim-runc-v2 -namespace moby -id ... -address /run/containerd/containerd.sock
...

# k3s 내장 containerd (namespace: k8s.io)
root  /var/lib/rancher/k3s/.../containerd-shim-runc-v2 -namespace k8s.io -id ... -address /run/k3s/containerd/containerd.sock
root  /var/lib/rancher/k3s/.../containerd-shim-runc-v2 -namespace k8s.io -id ... -address /run/k3s/containerd/containerd.sock
...
```

두 개의 containerd 인스턴스가 **각각 다른 네임스페이스와 소켓을 사용하여** 독립적으로 동작하고 있다.

- `-namespace moby -address /run/containerd/containerd.sock`: Docker의 containerd를 사용하는 컨테이너
- `-namespace k8s.io -address /run/k3s/containerd/containerd.sock`: k3s 내장 containerd를 사용하는 컨테이너

<br>

### k3s agent 디렉토리 구조

이 서버의 k3s agent 디렉토리를 확인하면, `containerd`와 `cri-dockerd` 디렉토리가 모두 존재한다:

```bash
$ sudo ls -al /var/lib/rancher/k3s/agent/
drwx------ 16 root root 4096 containerd
drwxr-xr-x  3 root root 4096 cri-dockerd
drwx------  5 root root 4096 etc
...
```

두 디렉토리가 모두 존재하는 이유는, k3s의 컨테이너 런타임을 전환할 때 **재설치가 아닌 재시작**만 했기 때문이다. 

k3s를 재설치하면 기존 디렉토리가 삭제되고 새로 생성되지만, 재시작만 하면 이전 런타임 설정에 따라 생성된 디렉토리가 그대로 남아있게 된다.

- `containerd/`: k3s가 내장 containerd를 사용했을 때 생성된 디렉토리 (이미지 저장)
- `cri-dockerd/`: k3s가 Docker runtime을 사용했을 때 생성된 디렉토리 (Pod 샌드박스 정보 저장)

> **참고: 재설치 대신 재시작을 선택한 이유**
>
> 재설치를 하면 기존 이미지와 설정이 모두 삭제되어 다시 pull해야 하고, 클러스터 설정도 재구성해야 한다. 런타임 전환만으로도 충분히 동작하므로, 데이터 보존과 다운타임 최소화를 위해 재시작만 수행했다.

<br>
현재는 k3s가 내장 containerd를 사용하고 있으므로, `containerd/` 디렉토리에 이미지가 저장되고 있다.


<br>

### cri-dockerd (CRI 어댑터)

**cri-dockerd**는 Docker를 CRI(Container Runtime Interface) 호환 런타임으로 만들어주는 어댑터다. kubelet의 CRI 요청을 Docker API 호출로 변환해준다.

<br>

k3s가 `--docker` 플래그로 실행되면 다음과 같은 구조로 연결된다:

```
k3s (kubelet)
    ↓
cri-dockerd (CRI 어댑터)
    ↓
Docker (dockerd)
    ↓
containerd (/run/containerd/containerd.sock)
```

이 경우 crictl은 cri-dockerd 소켓(`/run/k3s/cri-dockerd/cri-dockerd.sock`)을 통해 **Docker runtime이 관리하는 이미지**를 확인할 수 있다.

<br>

> **참고: dockershim과 cri-dockerd**
>
> 쿠버네티스 1.24 이전에는 **dockershim**이라는 컴포넌트가 쿠버네티스에 내장되어 있어, kubelet의 CRI 요청을 Docker API 호출로 변환해주는 역할을 했다. `dockershim`과 `cri-dockerd`는 모두 동일한 역할을 수행한다. 둘 다 kubelet의 CRI 요청을 Docker API 호출로 변환하여 Docker 엔진을 쿠버네티스 컨테이너 런타임으로 사용할 수 있게 해준다.  
>
> 하지만 쿠버네티스 1.24 버전부터 쿠버네티스에 내장되어 있던 dockershim이 제거되면서, Docker 엔진을 쿠버네티스 컨테이너 런타임으로 사용하려면 **cri-dockerd**를 별도로 설치해야 설치해야 하게 되었다.
>
> 쿠버네티스 공식 문서에서는 [dockershim 제거 이후 Docker 엔진 사용 방법](https://kubernetes.io/ko/docs/tasks/administer-cluster/migrating-from-dockershim/migrate-dockershim-dockerd/)을 안내하고 있다.


<br>

### CLI 도구와 소켓 연결

이 서버에는 Docker와 k3s가 모두 설치되어 있기 때문에, 각각의 설치 과정에서 다른 CLI 도구들이 함께 설치되었다.

- **Docker 설치 시**: `docker` CLI와 `containerd`(그리고 `ctr` CLI)가 함께 설치됨
- **k3s 설치 시**: `crictl`이 k3s 바이너리에 내장되어 설치됨

각 CLI가 어떤 소켓에 연결되는지 정리하면 다음과 같다.

| CLI | 기본 소켓 | 연결 대상 |
|-----|----------|----------|
| docker | /var/run/docker.sock | dockerd |
| ctr | /run/containerd/containerd.sock | dockerd가 사용하는 containerd |
| crictl | /run/k3s/containerd/containerd.sock | k3s 내장 containerd (기본값) |
| crictl | /run/k3s/cri-dockerd/cri-dockerd.sock | cri-dockerd (k3s가 `--docker` 플래그로 실행 시) |

> 참고: k3s는 crictl을 자체 바이너리에 내장하고, 기본값으로 k3s containerd 소켓을 사용하도록 설정되어 있다. k3s가 `--docker` 플래그로 실행되면 crictl은 cri-dockerd 소켓을 사용하도록 설정된다. ctr은 `--address` 옵션으로 소켓을 변경할 수 있다.

<br>


## 동일한 이미지가 중복 저장된 이유

**각각의 컨테이너 런타임이 독립적으로 이미지를 관리**하기 때문이다. [이전 글에서 살펴보았듯이]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-2 %}#구현체) Docker runtime과 containerd는 서로 다른 스토리지 드라이버 구현체를 사용하기 때문에 저장 구조도 다른데, 이미지 저장 경로가 다른 것이 직접적인 원인이다.

```
레지스트리 (원본)
├── manifest
├── config.json     ← sha256 = 이미지 ID (동일)
└── layers (tar.gz) ← 압축된 레이어들 (동일)
        │
        ├──→ docker pull ──→ /var/lib/docker/overlay2/
        │                     (overlay2 스토리지 드라이버로 관리)
        │
        └──→ k3s pull ──→ /var/lib/rancher/k3s/agent/containerd/
                          (overlayfs snapshotter로 관리)
```

> 각 런타임의 상세한 디렉토리 구조는 [이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-2 %}#실제-디렉토리-구조-확인)에서 확인할 수 있다.

<br>

같은 이미지를 Docker runtime과 containerd에서 각각 pull했을 때, 무엇이 같고 무엇이 다른지 정리하면 다음과 같다.

| 항목 | 동일 여부 |
|------|----------|
| 이미지 ID (config sha256) | 동일 |
| 레이어 내용 (파일들) | 동일 |
| 저장 경로 | 다름 |
| 디렉토리 구조/메타데이터 | 다름 |

이미지의 본질(ID, 레이어 내용)은 동일하지만, 각 런타임이 이를 저장하고 관리하는 방식이 다르다. 결과적으로, 같은 이미지를 Docker runtime으로도 pull하고 k3s(containerd)로도 pull하면, **디스크에는 동일한 레이어가 두 벌 존재**하게 된다.

<br>


## 동일한 이미지의 이름이 다르게 나타나는 이유

런타임별로 이미지 이름을 표시하는 방식이 다르다.

| 런타임 | 표시 방식 | 예시 |
|--------|----------|------|
| Docker runtime (dockerd) | 기본 레지스트리(docker.io) 생략 | `co-detr-coco-app:1.0` |
| containerd | fully qualified name으로 정규화 | `docker.io/co-detr-coco-app:1.0` |

<br>

containerd는 이미지를 **fully qualified name**(전체 경로)으로 저장한다.

```
[registry]/[namespace]/[repository]:[tag]
예: docker.io/library/nginx:latest
```

또한, containerd 미러링 설정을 사용하는 경우에도, 실제 다운로드는 미러 레지스트리에서 진행하지만 **이미지 이름은 원래 요청한 형식으로 유지**한다.

```
요청: co-detr-coco-app:1.0
     ↓(정규화)
docker.io/co-detr-coco-app:1.0
     ↓ (미러 설정 확인)
실제 다운로드: private.registry.com:5000/co-detr-coco-app:1.0
     ↓
저장되는 이름: docker.io/co-detr-coco-app:1.0  ← 원래 요청 유지
```

이는 containerd 미러링이 **투명하게 동작**하도록 설계되었기 때문이다. 클라이언트 입장에서 미러 존재 여부와 관계없이 동일한 이름으로 이미지를 참조할 수 있다.

<br>

## 동일한 이미지의 크기가 다르게 나타나는 이유

이미지 크기 차이는 **런타임 계산 방식 차이**와 **CLI 단위 표시 방식 차이**가 모두 영향을 준다.

<br>

### 실제 검증 결과

동일한 이미지를 각 CLI로 확인한 결과이다.

| 명령어 | 소켓 | 이미지 크기 |
|--------|------|------------|
| docker images | /var/run/docker.sock | 20.3GB |
| crictl images | /run/k3s/containerd/containerd.sock | 10.4GB |
| ctr images | /run/containerd/containerd.sock | (없음) |
| ctr -n k8s.io images | /run/k3s/containerd/containerd.sock | 9.7GiB |

```bash
# 1. docker로 확인
$ docker images | grep co-detr
co-detr-coco-app    1.0    f05ffb0c16af    20.3GB

# 2. crictl로 확인
$ sudo crictl images | grep co-detr
docker.io/co-detr-coco-app    1.0    f05ffb0c16aff    10.4GB

# 3. ctr로 확인 (Docker의 containerd, default 네임스페이스)
$ sudo ctr images ls
(비어있음 - Docker는 containerd가 아닌 /var/lib/docker에서 이미지 관리)

# 4. ctr로 확인 (k3s containerd, k8s.io 네임스페이스)
$ sudo ctr --address /run/k3s/containerd/containerd.sock -n k8s.io images ls | grep co-detr
docker.io/co-detr-coco-app:1.0    ...    9.7 GiB    linux/amd64    ...
```

<br>

### 실제 검증 결과 분석

<br>

**1 vs 2: 런타임 간 계산 방식 차이**

| 런타임 | 크기 계산 방식 |
|--------|---------------|
| Docker runtime (dockerd) | 모든 레이어의 **압축 해제된(uncompressed)** 총 크기 |
| containerd | Content Store에 저장된 레이어 blob의 **압축된(compressed)** 크기 기반 |

Docker runtime의 20.3GB와 containerd의 10.4GB 차이(약 2배)는 **압축 상태의 차이**가 주요 원인이다.

레지스트리에서 이미지를 pull할 때 레이어는 압축된 상태(`tar.gz`)로 전송되며, Docker runtime(dockerd)은 이를 압축 해제한 크기를, containerd는 압축된 blob 크기를 기준으로 계산한다.

이 구조 덕분에 containerd는:
- 디스크 저장 시에는 압축된 상태로 공간 효율적으로 저장하고,
- 컨테이너 실행 시에만 필요한 레이어를 압축 해제하여 제공할 수 있다.

> 참고: containerd의 이미지 크기와 Content Store
>
> [1편에서 다룬 것처럼]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %}), containerd는 이미지를 두 단계로 관리한다:
> - **Content Store**: 레이어 blob을 **압축 상태**로 저장 (`io.containerd.content.v1.content/blobs/sha256/`)
> - **Snapshotter**: 컨테이너 실행 시 압축을 **해제**하여 파일시스템으로 마운트 (`io.containerd.snapshotter.v1.overlayfs/snapshots/`)
>
> `crictl images`에서 보이는 크기는 **Content Store의 압축된 blob 크기**를 기반으로 한다. 반면, 컨테이너가 실제로 실행될 때는 Snapshotter가 이를 압축 해제하므로 실행 중인 컨테이너의 파일시스템 크기는 더 커진다.

<br>

**2 vs 4: 같은 런타임, CLI 단위 표시 차이**

crictl과 ctr은 같은 k3s containerd를 바라보지만, 표시 단위가 다르다. 표시 단위를 맞춰 보면, 같은 크기임을 확인할 수 있다.
- crictl: 10.4 GB (10^9 bytes 기준, SI 단위)
- ctr: 9.7 GiB (2^30 bytes 기준, 이진 단위)
- 환산: 9.7 GiB × 1.073741824 ≈ 10.4 GB

<br>

**3이 비어있는 이유**

ctr의 기본 네임스페이스는 `default`인데, Docker runtime(dockerd)은 이미지를 containerd에 저장하지 않고 `/var/lib/docker/`에서 자체 관리한다. 따라서 dockerd의 containerd에 연결해도 이미지가 보이지 않는다.

### 정리

- `docker` vs `crictl`: 런타임 간 크기 계산 방식 차이 (본질적 차이)
- `crictl` vs `ctr`: CLI 간 단위 표시 방식 차이 (같은 값, 다른 표현)


<br>

# 결론

처음에 제시한 의문에 대한 답을 정리하면 다음과 같다.

| 의문 | 답변 |
|------|------|
| 동일한 이미지가 중복 저장된 이유 | 각 런타임이 독립적인 스토리지 드라이버로 이미지를 관리하기 때문 |
| 동일한 이미지의 이름이 다르게 나타나는 이유 | Docker runtime(dockerd)은 docker.io를 생략하고, containerd는 fully qualified name으로 표시하기 때문 |
| 동일한 이미지의 크기가 다르게 나타나는 이유 | 런타임별 크기 계산 방식 차이 + CLI별 단위 표시 방식 차이 |

<br>

## 배운 점

### 숫자를 그대로 믿지 말 것
`docker images`에서 20GB로 보이던 이미지가 `crictl images`에서는 10GB로 보였다. 같은 이미지인데 숫자가 다르다고 당황할 필요 없다. 어떤 CLI로 어떤 런타임을 바라보느냐에 따라 계산 방식과 표시 단위가 다를 수 있다.

### 환경을 이해할 것

이번 문제를 해결하면서 컨테이너 런타임의 구조에 대해 이해하게 되었다. Docker runtime과 containerd가 어떻게 다른지, 이미지가 어디에 저장되는지, 각 CLI가 어떤 소켓으로 통신하는지를 알아야 문제 상황을 정확히 파악할 수 있다.

### 적절한 도구를 사용할 것

k8s/k3s 환경에서는 `crictl`, Docker runtime 환경에서는 `docker`를 사용하는 것이 맞다. 쿠버네티스가 보는 것과 동일한 뷰를 보려면, 쿠버네티스가 사용하는 CRI 인터페이스를 통해 확인해야 한다.

### 디스크 관리에 주의할 것

런타임이 여러 개 설치된 환경에서는 같은 이미지가 중복 저장될 수 있다. 여태까지 살펴본 것처럼, **같은 이미지가 두 벌 저장되어 디스크가 낭비**될 수 있다. 주기적으로 사용하지 않는 런타임의 이미지를 정리하고, 가능하다면 하나의 런타임으로 통일하는 것이 좋다.

```bash
# Docker 이미지 정리
docker image prune -a

# containerd 이미지 정리 (k3s)
sudo crictl rmi --prune
```

<br>

## k8s/k3s 환경에서의 권장 사항

k8s/k3s 환경에서는 **crictl**을 사용하는 것이 적합하다.

- 쿠버네티스가 CRI를 통해 containerd와 통신하므로, crictl을 사용하면 **쿠버네티스가 보는 것과 동일한 뷰**를 볼 수 있다.
- `docker` CLI(dockerd)로 이미지 크기를 확인할 경우 실제보다 크게 보일 수 있으니 당황하지 말자.

| 환경 | 권장 CLI | 이유 |
|------|---------|------|
| k3s/K8s | crictl | CRI 인터페이스, 쿠버네티스 관점 |
| Docker runtime 단독 | docker | dockerd가 관리하는 전체 정보 |
| containerd 직접 | ctr | 네이티브 API, 디버깅용 |

<br>
---

*장애가 발생한 것은 아니었지만, 디스크 용량을 확인하다 우연히 발견한 현상 덕분에 컨테이너 런타임의 동작 방식을 깊이 이해할 수 있었다. 때로는 사소한 의문이 가장 좋은 학습 기회가 된다*

