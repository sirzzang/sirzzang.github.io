---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: The Hard Way - 4. Private Container Registry"
excerpt: "폐쇄망 환경에서 컨테이너 이미지 배포를 위한 사설 컨테이너 레지스트리를 구축해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Air-Gapped
  - Offline
  - Container-Registry
  - Podman
  - Docker-Registry
  - registries.conf
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 폐쇄망 환경에서 컨테이너 이미지를 배포하기 위한 **사설 컨테이너 레지스트리(Private Container Registry)**를 구축한다.

- **레지스트리 구축**: admin에서 Podman으로 Docker Registry 컨테이너를 기동
- **이미지 Push**: 샘플 이미지(alpine)를 사설 레지스트리에 업로드
- **이미지 Pull**: k8s-node에서 사설 레지스트리의 이미지를 다운로드
- **정리**: 이후 kubespray-offline 실습을 위해 컨테이너 및 설정 원복

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | Podman으로 Docker Registry 기동 | 사설 이미지 저장소 구축 |
| 2 | admin | alpine 이미지 태깅 + Push | 내부 레지스트리에 이미지 등록 |
| 3 | k8s-node | 사설 레지스트리에서 이미지 Pull | 이미지 배포 확인 |
| 4 | admin, k8s-node | 컨테이너 삭제 + 설정 원복 | 이후 실습을 위한 정리 |

<br>

# 사설 컨테이너 레지스트리의 필요성

[이전 글(8.1.3)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})에서 로컬 패키지 저장소를 구축했다. 이제 **컨테이너 이미지**를 배포할 수 있어야 한다.

Kubernetes 클러스터를 구성하면 다양한 시스템 컴포넌트가 컨테이너로 실행된다.

| 컴포넌트 | 이미지 출처 |
|----------|-----------|
| kube-apiserver, kube-controller-manager, kube-scheduler, kube-proxy | `registry.k8s.io` |
| etcd, coredns, pause | `registry.k8s.io` |
| CNI 플러그인 (Calico, Flannel 등) | `docker.io`, `quay.io` 등 |

온라인 환경에서는 kubelet이 `registry.k8s.io`, `docker.io` 등 공개 레지스트리에서 이미지를 직접 Pull하면 된다. 폐쇄망에서는 이 레지스트리들에 접근할 수 없으므로, **admin에 사설 레지스트리를 구축**하고 필요한 이미지를 미리 넣어두어야 한다.

```
[온라인]  k8s-node → registry.k8s.io / docker.io → 이미지 Pull
[폐쇄망]  k8s-node → admin (192.168.10.10:5000) → 사설 레지스트리에서 이미지 Pull
```

이번 글에서는 사설 레지스트리의 기본 구성과 동작 원리를 실습한다. 실제 Kubernetes 배포에 필요한 이미지를 대량으로 옮기는 작업은 이후 kubespray-offline 실습에서 자동화된다.

<br>

# 배경지식

## 컨테이너 레지스트리란

**컨테이너 레지스트리(Container Registry)**는 컨테이너 이미지를 저장하고 배포하는 서비스다. Python의 PyPI, Node.js의 npm registry처럼, 컨테이너 이미지의 중앙 저장소 역할을 한다.

```
개발자 → (build) → 이미지 → (push) → 레지스트리 → (pull) → 런타임(kubelet, podman, docker)
```

레지스트리와 이미지를 주고받는 프로토콜은 **OCI Distribution Specification**(구 Docker Registry HTTP API V2)으로 표준화되어 있다. 따라서 Docker, Podman, containerd, CRI-O 등 어떤 컨테이너 런타임이든 동일한 레지스트리와 통신할 수 있다.

### 주요 공개 레지스트리

| 레지스트리 | 주소 | 운영 |
|-----------|------|------|
| **Docker Hub** | `docker.io` | Docker Inc. |
| **Quay.io** | `quay.io` | Red Hat |
| **GitHub Container Registry** | `ghcr.io` | GitHub |
| **Kubernetes Registry** | `registry.k8s.io` | Kubernetes SIG Release |
| **Amazon ECR Public** | `public.ecr.aws` | AWS |
| **Google Artifact Registry** | `gcr.io` / `us-docker.pkg.dev` | Google |

> 폐쇄망에서 Kubernetes를 설치할 때, 어떤 이미지를 미리 다운받아야 하는지 확인하려면 [explore.ggcr.dev](https://explore.ggcr.dev/?repo=registry.k8s.io)에서 `registry.k8s.io`의 이미지 목록을 탐색할 수 있다.

### 컨테이너 이미지 이름 구조

이미지 이름은 여러 구성 요소로 이루어진다.

```
docker.io  /  library  /  nginx  :  1.25  @sha256:abc123...
─────────     ───────     ─────     ────   ──────────────
registry     namespace    image     tag       digest
```

| 구성 요소 | 의미 | 예시 |
|-----------|------|------|
| **Registry** | 이미지를 저장하는 서버의 도메인(또는 IP:포트) | `docker.io`, `192.168.10.10:5000` |
| **Namespace** | 이미지의 소유자/조직. Docker Hub 공식 이미지는 `library` | `library`, `grafana` |
| **Image** | 이미지 이름 | `nginx`, `alpine` |
| **Tag** | 이미지 버전. 생략하면 `latest`가 기본 | `1.25`, `latest` |
| **Digest** | 이미지의 SHA256 해시. 특정 빌드를 고유하게 식별 | `sha256:abc123...` |

레지스트리 도메인을 포함한 이름을 **정규화된 이름(Fully Qualified Name)**이라 한다. `docker.io/library/nginx:latest`는 정규화된 이름이고, `nginx`는 **비정규화된 이름(Unqualified Name)**이다.

```bash
# 정규화된 이름 (Qualified) → 레지스트리가 명확
podman pull docker.io/library/nginx:latest
podman pull 192.168.10.10:5000/alpine:1.0

# 비정규화된 이름 (Unqualified) → 어느 레지스트리에서 가져올지 결정 필요
podman pull nginx
podman pull alpine
```

> 참고: 비정규화된 이름의 해석 
>
> 비정규화된 이름의 헤석 방식은 컨테이너 런타임마다 다르다.
> - **Podman/Buildah/Skopeo**: `registries.conf`의 설정에 따라 이미지를 검색한다 (뒤에서 자세히 다룬다).
> - **Docker**: 항상 `docker.io`로 고정되어 있으며, `/etc/docker/daemon.json`에서 insecure 레지스트리만 설정 가능하다.
> - **containerd/CRI-O**: 각각 자체 설정 파일을 사용한다.

<br>

## Docker Registry

**Docker Registry**는 Docker Inc.가 관리하는 공식 컨테이너 이미지(`docker.io/library/registry`)로, 사설 레지스트리를 간단하게 구축할 수 있게 해준다.

| 항목 | 내용 |
|------|------|
| 이미지 이름 | `docker.io/library/registry` (short name: `registry`) |
| 기반 프로젝트 | **CNCF Distribution** (구 Docker Distribution) |
| 기본 포트 | 5000 |
| 인증 | 기본 비활성 (Basic Auth, Token Auth 설정 가능) |
| 저장소 | 로컬 파일시스템 (S3, Azure Blob, GCS 등도 지원) |

이 이미지의 기반인 **Distribution** 프로젝트는 OCI Distribution Specification의 참조 구현체(reference implementation)이며, CNCF에서 관리한다. Harbor, GitLab Container Registry 같은 엔터프라이즈 레지스트리도 내부적으로 Distribution을 사용한다.

```
Docker Registry (이미지)  →  Distribution (CNCF 프로젝트)  →  OCI Distribution Spec (표준)
       ↑ 실습에서 사용                ↑ 기반 엔진                    ↑ 프로토콜 표준
```

이번 실습에서는 인증 없이 HTTP로 동작하는 가장 기본적인 구성을 사용한다. 프로덕션에서는 TLS + 인증이 필수다.

## Podman

Rocky Linux 10에는 **Podman**이 기본 설치되어 있다. Podman은 Red Hat이 주도하는 **데몬리스(daemonless) 컨테이너 도구**로, Docker와 거의 동일한 CLI를 제공한다.

### Docker와의 차이

| 항목 | Docker | Podman |
|------|--------|--------|
| 아키텍처 | **데몬 기반** (`dockerd` 상주) | **데몬리스** (명령 실행 시에만 프로세스 생성) |
| 루트 권한 | 데몬이 root로 실행 (보안 이슈) | 루트리스(rootless) 모드 기본 지원 |
| OCI 런타임 | runc (기본) | crun (기본, C 구현으로 더 가벼움) |
| 레지스트리 설정 | `/etc/docker/daemon.json` | `/etc/containers/registries.conf` |
| Pod 지원 | 없음 (docker-compose 별도) | **Pod 네이티브 지원** (K8s Pod 개념 반영) |

Docker에서 `docker` 명령이 하는 일을 Podman에서는 `podman`으로 그대로 대체할 수 있다. 이미지 pull, push, build, run 등 대부분의 명령이 동일하다.

```bash
# Docker
docker pull nginx
docker run -d -p 80:80 nginx

# Podman (명령어 동일)
podman pull nginx
podman run -d -p 80:80 nginx
```

### Red Hat 컨테이너 도구 생태계

Podman은 단독 도구가 아니라, Red Hat이 "Docker 데몬 없는 컨테이너 도구"를 목표로 만든 생태계의 일부다.

| 도구 | 역할 |
|------|------|
| **Podman** | 컨테이너 **실행** (run, exec, ps, ...) 및 이미지 관리 |
| **Buildah** | 이미지 **빌드** (Dockerfile 없이 스크립트로 레이어 쌓기 가능) |
| **Skopeo** | 이미지 **전송/검사** (레지스트리 간 복사, 매니페스트 조회) |

이 세 도구는 공통 라이브러리를 공유한다.

| 라이브러리 | 역할 |
|-----------|------|
| **containers/image** | 이미지 pull/push/복사, 레지스트리 인증, 매니페스트 파싱 |
| **containers/storage** | 이미지/컨테이너 레이어의 로컬 저장소 관리 |
| **containers/common** | 공통 설정 파일 (`registries.conf`, `policy.json` 등) |

이 라이브러리들은 Go로 작성되어 각 도구의 바이너리에 컴파일되어 들어간다. `registries.conf`를 하나만 설정하면 podman, buildah, skopeo 모두에 적용되는 구조다.

### 배포판별 패키징

이 프로젝트들은 **Red Hat 엔지니어가 핵심 메인테이너**다. Red Hat이 "Docker 데몬 없는 컨테이너 도구"를 목표로 직접 시작한 프로젝트이기 때문에, RHEL/Fedora에 기본 탑재되어 있고 Rocky Linux도 RHEL 호환이므로 그대로 포함한다. "외부 프로젝트를 가져온 것"이 아니라 **배포판 제작자가 직접 만든 프로젝트를 자기 OS에 넣은 것**이다.

설정 파일의 내용도 배포판마다 다르다. `registries.conf`, `000-shortnames.conf` 등은 `containers-common` 패키지에 포함되어 있는데, 이 패키지를 **어떤 내용으로 채워서 배포하느냐는 각 배포판 메인테이너가 결정**한다.

| 배포판 | `000-shortnames.conf` 내용 |
|--------|---------------------------|
| **RHEL / Rocky / CentOS** | 수백 개 매핑이 미리 포함 (Red Hat이 직접 관리) |
| **Fedora** | 비슷하지만 버전에 따라 매핑 목록이 조금 다름 |
| **Ubuntu / Debian** | `containers-common` 패키지가 있지만 shortnames 매핑이 적거나 없을 수 있음 |

## registries.conf

`registries.conf`는 **containers/image 라이브러리의 레지스트리 설정 파일**이다. Podman, Buildah, Skopeo가 이미지를 pull/push할 때 이 파일을 참조한다. `containers-common` 패키지에 포함되어 있다.

```bash
rpm -qf /etc/containers/registries.conf
# → containers-common-x.x.x
```

> Docker는 이 설정 체계를 사용하지 않는다. Docker는 자체 설정(`/etc/docker/daemon.json`)만 사용한다.

| 도구 | `registries.conf` 사용 | `000-shortnames.conf` 사용 |
|------|:---:|:---:|
| **Podman** | O | O |
| **Buildah** | O | O |
| **Skopeo** | O | O |
| **Docker** | X (`daemon.json` 사용) | X (항상 `docker.io`로 고정) |

### Unqualified Search

비정규화된 이름(예: `podman pull nginx`)으로 이미지를 요청하면, Podman은 `unqualified-search-registries`에 등록된 레지스트리를 순서대로 탐색한다.

```ini
# /etc/containers/registries.conf
unqualified-search-registries = ["registry.access.redhat.com", "registry.redhat.io", "docker.io"]
```

```
podman pull nginx
  → 1순위: registry.access.redhat.com/nginx 시도
  → 2순위: registry.redhat.io/nginx 시도
  → 3순위: docker.io/library/nginx 시도
```

이 탐색 방식에는 **보안 이슈**가 있다. 공격자가 상위 순위 레지스트리에 같은 이름의 악성 이미지를 등록하면, 의도치 않게 악성 이미지를 pull할 수 있다. 예를 들어, 아래와 같이 설정되어 있다고 가정하자.

```ini
unqualified-search-registries = ["my-company-registry.com", "docker.io"]
```

사용자가 `podman pull myapp`을 실행하면, Podman은 먼저 `my-company-registry.com/myapp`을 찾는다. 그런데 공격자가 `my-company-registry.com`에 `myapp`이라는 이름의 악성 이미지를 미리 올려두었다면, 사용자는 `docker.io`의 정상 이미지 대신 **1순위에서 찾은 악성 이미지를 pull**하게 된다. 레지스트리 순서를 뒤집어도 공격 대상 레지스트리만 달라질 뿐, 근본적으로 같은 문제가 발생한다.

이를 방지하기 위해 **Short Name Alias**가 도입되었다.

### Short Name Alias

Short Name Alias는 비정규화된 이름을 **특정 레지스트리의 정규화된 이름으로 고정**하는 매핑이다. `/etc/containers/registries.conf.d/000-shortnames.conf`에 정의되어 있으며, `containers-common` 패키지에 수백 개의 사전 매핑이 포함되어 있다.

```ini
# /etc/containers/registries.conf.d/000-shortnames.conf
[aliases]
  "alpine" = "docker.io/library/alpine"
  "nginx" = "docker.io/library/nginx"
  "registry" = "docker.io/library/registry"
  "python" = "docker.io/library/python"
  # ... (수백 개)
```

```
podman pull alpine
  → 000-shortnames.conf 조회
  → "alpine" = "docker.io/library/alpine"
  → docker.io/library/alpine:latest에서 pull
```

Short Name Alias가 없으면 Podman은 `unqualified-search-registries`를 순서대로 시도하거나, `short-name-mode = "enforcing"` 설정에 따라 사용자에게 직접 선택을 요구한다.

```bash
# short-name-mode = "enforcing" + alias 없는 이미지
podman pull unknown-image
? Please select an image:
    registry.access.redhat.com/unknown-image
  ▸ docker.io/library/unknown-image       ← 매번 선택해야 함
```

이미지 이름 해석 전체 흐름을 정리하면 다음과 같다.

```
podman pull <이름>
  ├─ FQDN인가? (docker.io/library/nginx 등)
  │    └─ Yes → 해당 레지스트리에서 직접 pull
  │
  └─ No (비정규화 이름: nginx 등)
       ├─ 000-shortnames.conf에 매핑 있는가?
       │    └─ Yes → 매핑된 FQDN으로 pull
       │
       └─ No
            ├─ short-name-mode = "enforcing"
            │    └─ 사용자에게 선택 요구
            └─ short-name-mode = "permissive"
                 └─ unqualified-search-registries 순서대로 시도
```

### Insecure Registry 설정

기본적으로 컨테이너 런타임(Docker, Podman, containerd 등)은 레지스트리와 **HTTPS로만 통신**한다. HTTP 레지스트리에 접근하려면 명시적으로 **insecure** 설정을 해야 한다.

HTTPS를 기본으로 요구하는 이유:

| 이유 | 설명 |
|------|------|
| 이미지 무결성 | HTTP 전송 시 MITM 공격으로 이미지 레이어를 변조할 수 있음 |
| 인증 정보 보호 | `podman login` 시 Base64 인코딩된 자격 증명이 HTTP 헤더로 전송됨 |
| 보안 기본 정책 | "옵트아웃" 방식 설계 — HTTP를 쓰려면 명시적으로 허용해야 함 |

`registries.conf`에 `[[registry]]` 블록을 추가하여 특정 레지스트리를 insecure로 등록할 수 있다.

```ini
# /etc/containers/registries.conf에 추가
[[registry]]
location = "192.168.10.10:5000"
insecure = true
```

이 설정은 `containers/image` 라이브러리가 읽으므로, podman, buildah, skopeo 모두에 동일하게 적용된다.

> 폐쇄망에서 insecure 레지스트리를 사용하는 이유는 TLS 인증서 발급의 번거로움 때문이다. 외부 CA(Let's Encrypt 등)를 쓸 수 없고, 자체 CA를 만들어 모든 노드에 배포해야 한다. 실습에서는 편의상 HTTP를 허용하지만, **실무에서는 내부 CA를 만들어 HTTPS를 쓰는 것이 권장**된다. 폐쇄망이라도 내부 공격자나 설정 실수로 인한 위험은 존재한다.

<br>

# 실습

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | Podman 환경 확인 | 컨테이너 도구 상태 파악 |
| 2 | admin | Docker Registry 기동 | 사설 이미지 저장소 구축 |
| 3 | admin | 이미지 Push | 내부 레지스트리에 이미지 등록 |
| 4 | k8s-node | 이미지 Pull | 내부 레지스트리에서 이미지 다운로드 |
| 5 | admin, k8s-node | 정리 | 이후 실습을 위한 원복 |

## 1. [admin] Podman 환경 확인

사설 레지스트리를 구축하기 전에, admin에 설치된 Podman과 레지스트리 설정 현황을 파악한다.

### Podman 설치 확인

```bash
# Podman 바이너리 경로 확인
root@admin:~# which podman
/usr/bin/podman

# 버전 확인
root@admin:~# podman --version
podman version 5.4.0

# 설치된 저장소 확인 (AppStream에서 제공)
root@admin:~# dnf info podman | grep repo
From repo    : AppStream
```

Rocky Linux 10에는 Podman이 AppStream 저장소에서 기본 제공된다. 별도 설치 없이 바로 사용 가능하다.

### 런타임 정보 확인

```bash
root@admin:~# podman info
host:
  arch: arm64
  buildahVersion: 1.39.4
  cgroupManager: systemd
  cgroupVersion: v2
  conmon:
    package: conmon-2.1.12-4.el10.aarch64
    path: /usr/bin/conmon
    version: 'conmon version 2.1.12, commit: '
  ...
  distribution:
    distribution: rocky
    version: "10.0"
  ...
  networkBackend: netavark
  ociRuntime:
    name: crun
    package: crun-1.21-1.el10_0.aarch64
    path: /usr/bin/crun
    ...
registries:
  search:
  - registry.access.redhat.com
  - registry.redhat.io
  - docker.io
store:
  graphDriverName: overlay
  graphRoot: /var/lib/containers/storage
  ...
```

| 항목 | 값 | 의미 |
|------|-----|------|
| OCI 런타임 | `crun` | C 구현의 경량 컨테이너 런타임 |
| 네트워크 백엔드 | `netavark` | Podman 4.0+의 기본 네트워크 스택 |
| 스토리지 드라이버 | `overlay` | OverlayFS 기반 이미지 레이어 관리 |
| cgroup | v2 + systemd | 최신 cgroup 관리 방식 |
| 레지스트리 검색 순서 | Red Hat → Docker Hub | `registries.conf`의 `unqualified-search-registries` |

### 레지스트리 설정 파일 확인

```bash
root@admin:~# cat /etc/containers/registries.conf
# ... (주석 생략)
unqualified-search-registries = ["registry.access.redhat.com", "registry.redhat.io", "docker.io"]
short-name-mode = "enforcing"
```

`unqualified-search-registries`에 3개의 레지스트리가 등록되어 있고, `short-name-mode = "enforcing"`으로 설정되어 있다. Short Name Alias에 매핑이 없는 비정규화된 이름을 사용하면 사용자에게 선택을 요구한다.

```bash
# Short Name Alias 확인 (일부)
root@admin:~# grep -E "\"(alpine|nginx|registry)\"" /etc/containers/registries.conf.d/000-shortnames.conf
  "alpine" = "docker.io/library/alpine"
  "registry" = "docker.io/library/registry"
```

`alpine`, `registry` 등 주요 이미지는 이미 Short Name Alias로 매핑되어 있다. `podman pull alpine` 시 `docker.io/library/alpine`에서 자동으로 pull된다.

## 2. [admin] 사설 레지스트리 구축

Docker Registry 이미지를 받아 사설 레지스트리 컨테이너를 실행한다.

### 이미지 Pull

```bash
root@admin:~# podman pull docker.io/library/registry:latest
Trying to pull docker.io/library/registry:latest...
Getting image source signatures
Copying blob 92c7580d074a done   |
Copying blob 1cc3d49277b7 done   |
Copying blob a447a5de8f4e done   |
Copying blob 0a52a06d47e0 done   |
Copying blob 50b5971fe294 done   |
Copying config 2f5ec5015b done   |
Writing manifest to image destination
2f5ec5015badd603680de78accbba6eb3e9146f4d642a7ccef64205e55ac518f

root@admin:~# podman images
REPOSITORY                  TAG         IMAGE ID      CREATED      SIZE
docker.io/library/registry  latest      2f5ec5015bad  12 days ago  57.3 MB
```

### 컨테이너 실행

```bash
# 데이터 디렉토리 준비
root@admin:~# mkdir -p /data/registry
root@admin:~# chmod 755 /data/registry

# Registry 컨테이너 실행
root@admin:~# podman run -d \
  --name local-registry \
  -p 5000:5000 \
  -v /data/registry:/var/lib/registry \
  --restart=always \
  docker.io/library/registry:latest
2c3cf464e3c9572aeb5e7182325fd2fc291da61abe75d3db41e2079b75785bbf
```

| 옵션 | 의미 |
|------|------|
| `-d` | 백그라운드(detached) 실행 |
| `--name local-registry` | 컨테이너 이름 지정 |
| `-p 5000:5000` | 호스트 5000번 포트를 컨테이너 5000번 포트에 매핑 |
| `-v /data/registry:/var/lib/registry` | 호스트 디렉토리를 컨테이너 내 저장소 경로에 마운트 (영속 저장) |
| `--restart=always` | 호스트 재부팅 시 자동 재시작 |

### 동작 확인

```bash
# 컨테이너 상태 확인
root@admin:~# podman ps
CONTAINER ID  IMAGE                              COMMAND               CREATED        STATUS        PORTS                   NAMES
2c3cf464e3c9  docker.io/library/registry:latest  /etc/distribution...  6 seconds ago  Up 6 seconds  0.0.0.0:5000->5000/tcp  local-registry

# 포트 리스닝 확인
root@admin:~# ss -tnlp | grep 5000
LISTEN 0      4096         0.0.0.0:5000      0.0.0.0:*    users:(("conmon",pid=9951,fd=5))
```

`conmon`은 Podman이 각 컨테이너마다 생성하는 **모니터 프로세스**다. Docker의 `containerd-shim`과 비슷한 역할로, 컨테이너의 stdout/stderr을 관리하고 종료 상태를 추적한다.

```bash
# 프로세스 트리에서 Registry 확인
root@admin:~# pstree -a | grep -A1 conmon
  ├─conmon --api-version 1 -c 2c3cf464e3c9...
  │   └─registry serve /etc/distribution/config.yml
```

`conmon` 아래에 `registry serve` 프로세스가 실행 중이다. `config.yml`은 Distribution 프로젝트의 설정 파일이다.

```bash
# Registry API로 빈 카탈로그 확인
root@admin:~# curl -s http://localhost:5000/v2/_catalog | jq
{
  "repositories": []
}
```

`/v2/_catalog`는 OCI Distribution API 엔드포인트로, 레지스트리에 저장된 모든 이미지 목록을 반환한다. 아직 Push한 이미지가 없으므로 빈 배열이다.

## 3. [admin] 이미지 Push

샘플 이미지(alpine)를 사설 레지스트리에 Push한다.

### 이미지 가져오기 + 태깅

```bash
# Short Name Alias로 alpine 이미지 pull
root@admin:~# podman pull alpine
Resolved "alpine" as an alias (/etc/containers/registries.conf.d/000-shortnames.conf)
Trying to pull docker.io/library/alpine:latest...
Getting image source signatures
Copying blob d8ad8cd72600 done   |
Copying config 1ab49c19c5 done   |
Writing manifest to image destination
1ab49c19c53ebca95c787b482aeda86d1d681f58cdf19278c476bcaf37d96de1

# 사설 레지스트리 주소로 태깅
root@admin:~# podman tag alpine:latest 192.168.10.10:5000/alpine:1.0

root@admin:~# podman images
REPOSITORY                  TAG         IMAGE ID      CREATED      SIZE
docker.io/library/registry  latest      2f5ec5015bad  12 days ago  57.3 MB
192.168.10.10:5000/alpine   1.0         1ab49c19c53e  12 days ago  8.99 MB
docker.io/library/alpine    latest      1ab49c19c53e  12 days ago  8.99 MB
```

`podman pull alpine` 실행 시 `Resolved "alpine" as an alias` 로그가 출력된다. Short Name Alias가 동작하여 `docker.io/library/alpine`으로 자동 확장된 것이다.

`podman tag`는 같은 이미지(IMAGE ID 동일)에 **새로운 이름을 추가**하는 것이다. 이미지를 복사하는 것이 아니라, 하나의 이미지에 태그(이름)를 여러 개 붙이는 것이다. 사설 레지스트리에 Push하려면 레지스트리 주소가 포함된 이름이 필요하다.

### insecure 레지스트리 설정

```bash
# Push 시도 → HTTPS 오류
root@admin:~# podman push 192.168.10.10:5000/alpine:1.0
Getting image source signatures
Error: trying to reuse blob sha256:45f3ea5848e8... at destination: pinging container registry 192.168.10.10:5000: Get "https://192.168.10.10:5000/v2/": http: server gave HTTP response to HTTPS client
```

Podman이 기본적으로 HTTPS로 접근하려 하지만, 사설 레지스트리는 HTTP로 동작하므로 실패한다. insecure 레지스트리로 등록한다.

```bash
# 기존 설정 백업
root@admin:~# cp /etc/containers/registries.conf /etc/containers/registries.bak

# insecure 레지스트리 추가
root@admin:~# cat <<EOF >> /etc/containers/registries.conf
[[registry]]
location = "192.168.10.10:5000"
insecure = true
EOF

# 추가된 설정 확인 (주석 제외)
root@admin:~# grep "^[^#]" /etc/containers/registries.conf
unqualified-search-registries = ["registry.access.redhat.com", "registry.redhat.io", "docker.io"]
short-name-mode = "enforcing"
[[registry]]
location = "192.168.10.10:5000"
insecure = true
```

### 이미지 Push + 확인

```bash
# Push 성공
root@admin:~# podman push 192.168.10.10:5000/alpine:1.0
Getting image source signatures
Copying blob 45f3ea5848e8 done   |
Copying config 1ab49c19c5 done   |
Writing manifest to image destination

# 레지스트리 카탈로그 확인
root@admin:~# curl -s 192.168.10.10:5000/v2/_catalog | jq
{
  "repositories": [
    "alpine"
  ]
}

# 태그 목록 확인
root@admin:~# curl -s 192.168.10.10:5000/v2/alpine/tags/list | jq
{
  "name": "alpine",
  "tags": [
    "1.0"
  ]
}
```

`/v2/_catalog`에 `alpine`이 등록되었고, `/v2/alpine/tags/list`에 `1.0` 태그가 표시된다. 사설 레지스트리에 이미지가 정상적으로 Push되었다.

## 4. [k8s-node] 이미지 Pull

k8s-node1에서 사설 레지스트리의 이미지를 Pull한다. admin과 마찬가지로 insecure 레지스트리 설정이 필요하다.

```bash
# insecure 레지스트리 설정
root@week06-week06-k8s-node1:~# cp /etc/containers/registries.conf /etc/containers/registries.bak
root@week06-week06-k8s-node1:~# cat <<EOF >> /etc/containers/registries.conf
[[registry]]
location = "192.168.10.10:5000"
insecure = true
EOF

# 설정 확인
root@week06-week06-k8s-node1:~# grep "^[^#]" /etc/containers/registries.conf
unqualified-search-registries = ["registry.access.redhat.com", "registry.redhat.io", "docker.io"]
short-name-mode = "enforcing"
[[registry]]
location = "192.168.10.10:5000"
insecure = true

# 사설 레지스트리에서 이미지 Pull
root@week06-week06-k8s-node1:~# podman pull 192.168.10.10:5000/alpine:1.0
Trying to pull 192.168.10.10:5000/alpine:1.0...
Getting image source signatures
Copying blob 9268c2c682e1 done   |
Copying config 1ab49c19c5 done   |
Writing manifest to image destination
1ab49c19c53ebca95c787b482aeda86d1d681f58cdf19278c476bcaf37d96de1

root@week06-week06-k8s-node1:~# podman images
REPOSITORY                 TAG         IMAGE ID      CREATED      SIZE
192.168.10.10:5000/alpine  1.0         1ab49c19c53e  12 days ago  8.98 MB
```

k8s-node1에서 admin의 사설 레지스트리(`192.168.10.10:5000`)로부터 이미지를 정상적으로 Pull했다. 폐쇄망에서 외부 레지스트리 대신 내부 레지스트리를 사용하여 이미지를 배포할 수 있음을 확인했다.

## 5. 정리

이후 kubespray-offline 실습에서 다른 방식으로 레지스트리를 구성할 예정이므로, 현재 구성을 정리한다.

### admin

```bash
# Registry 컨테이너 삭제
root@admin:~# podman rm -f local-registry

# registries.conf 원복
root@admin:~# mv /etc/containers/registries.bak /etc/containers/registries.conf
```

`-f` 옵션은 실행 중인 컨테이너도 강제 종료 후 삭제한다. 정리하지 않으면 다음과 같은 문제가 생길 수 있다.

| 문제 | 설명 |
|------|------|
| 포트 충돌 | 5000번 포트가 이미 사용 중이라 새 컨테이너를 띄울 수 없음 |
| 이름 충돌 | 같은 이름(`local-registry`)의 컨테이너를 중복 생성할 수 없음 |
| 데이터 꼬임 | 이전 실습의 이미지가 남아 있어 깨끗한 상태에서 시작이 보장되지 않음 |

### k8s-node

```bash
# registries.conf 원복
root@week06-week06-k8s-node1:~# mv /etc/containers/registries.bak /etc/containers/registries.conf
```

<br>

# 정리

이번 글에서는 폐쇄망 환경에서 컨테이너 이미지를 배포하기 위한 사설 레지스트리를 구축했다.

| 순서 | 위치 | 작업 | 도구 |
|------|------|------|------|
| 1 | admin | Podman으로 Docker Registry 기동 | `podman run -p 5000:5000 registry` |
| 2 | admin | insecure 설정 + 이미지 Push | `registries.conf` + `podman push` |
| 3 | k8s-node | insecure 설정 + 이미지 Pull | `registries.conf` + `podman pull` |

현재까지의 폐쇄망 인프라 구성 상태:

| 구성요소 | 상태 |
|----------|------|
| Network Gateway | 완료 ([8.1.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})) |
| NTP Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| DNS Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| Local Package Repository | 완료 ([8.1.3]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})) |
| Private Container Registry | 완료 (본 글) |

이것으로 폐쇄망 기반 인프라의 모든 구성요소가 갖추어졌다. 이후 kubespray-offline을 사용한 실제 Kubernetes 클러스터 배포를 진행할 수 있다.

> 이번 실습에서는 수동으로 하나의 이미지를 push/pull하는 기본 동작만 확인했다. 실제 Kubernetes 배포에는 수십 개의 이미지(`kube-apiserver`, `etcd`, `coredns`, CNI 등)가 필요한데, 이 과정은 kubespray-offline이 자동화해 준다.

<br>

# 참고 자료

- [OCI Distribution Specification](https://github.com/opencontainers/distribution-spec)
- [CNCF Distribution (Docker Registry)](https://github.com/distribution/distribution)
- [Podman Documentation](https://docs.podman.io/)
- [containers/image - registries.conf](https://github.com/containers/image/blob/main/docs/containers-registries.conf.5.md)
- [Kubernetes Registry (explore.ggcr.dev)](https://explore.ggcr.dev/?repo=registry.k8s.io)

<br>
