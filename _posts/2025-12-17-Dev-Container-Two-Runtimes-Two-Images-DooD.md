---
title:  "[Container] DooD 환경에서의 이미지 관리"
excerpt: DooD 환경에서 containerd와 Docker에 서로 다른 이미지가 저장되는 현상에 대해 알아 보자.
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
  - docker-in-docker
  - bitbucket
  - ci-cd

---

# TL;DR

DooD 방식으로 동작하는 Bitbucket Pipeline Runner를 K3s 클러스터에서 테스트했더니, **Runner 이미지는 containerd에, 파이프라인 실행 이미지는 Docker에 각각 저장**되었다. DooD 구조에서 발생하는 자연스러운 현상이다.

<br>

---

이전 글에서 다룬 [컨테이너 이미지 중복 저장 문제]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %})와 [중복처럼 보이지만 아닌 경우]({% post_url 2025-12-12-Dev-Container-Non-Duplicate-Container-Images %})에서는 같은 이미지가 두 런타임에 저장되거나, 그렇게 보이는 경우를 다뤘다. 이번에는 **서로 다른 이미지가 각 런타임에 분리 저장되는 경우**를 살펴본다.

<br>

# 현상

Bitbucket Pipeline Runner의 DooD 방식을 테스트해보기 위해 K3s 클러스터에 배포하고 파이프라인을 실행해 봤다. 이미지 목록을 확인해보니 흥미로운 점이 있었다.

```bash
# containerd 런타임 (K3s)
$ sudo crictl images | grep atlassian
docker-public.packages.atlassian.com/sox/atlassian/bitbucket-pipelines-runner   5.6.0     fe7379cb5987b   278MB
docker-public.packages.atlassian.com/sox/atlassian/bitbucket-pipelines-runner   latest    fe5ce3c34aa56   278MB

# Docker 런타임
$ docker images | grep atlassian
docker-public.packages.atlassian.com/sox/atlassian/bitbucket-pipelines-auth-proxy   prod-stable   e886720710d9   5 months ago   11.8MB
docker-public.packages.atlassian.com/sox/atlassian/bitbucket-pipelines-dvcs-tools   prod-stable   9ea04d92255b   8 months ago   40.3MB
k8s-docker.packages.atlassian.com/pause                                             3.8           4873874c08ef   3 years ago    711kB
atlassian/default-image                                                             latest        3a09dfec7e36   8 years ago    1.39GB
```

흥미로운 점은, **두 런타임에서 보이는 이미지가 완전히 다르다**는 것이다.

| 런타임 | 이미지 | 용도 |
|--------|--------|------|
| containerd (crictl) | `bitbucket-pipelines-runner` | Runner Pod 자체 |
| Docker (docker) | `auth-proxy`, `dvcs-tools`, `default-image` 등 | 파이프라인 실행 시 사용되는 컨테이너들 |

<br>

이전에 다뤘던 [중복 저장 문제]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %})에서는 **같은 이미지**가 두 런타임에 각각 저장되어 디스크가 낭비되었다. 하지만 이번에는 **서로 다른 이미지**가 각 런타임에 저장되어 있다. 왜 이런 구조가 되었을까?

<br>

# 분석

## 테스트 환경 구조

Bitbucket Pipelines는 파이프라인 step 실행 시 Docker 데몬을 사용하며, containerd를 직접 지원하지 않는다. 따라서 K8s(containerd) 환경에서 Runner를 사용하려면 DooD나 DinD 방식으로 Docker에 접근해야 한다.

이번 테스트에서는 호스트의 `/var/run/docker.sock`을 마운트하여 **DooD (Docker-outside-of-Docker)** 방식으로 설정했다. DooD는 컨테이너 안에서 호스트의 Docker 데몬에 접근하여 다른 컨테이너를 실행하는 방식이다.

K3s 클러스터에서의 동작 구조는 다음과 같다.

```
[K3s Cluster (containerd)]
    └─ [Runner Pod] ← crictl images에서 보임
          └─ /var/run/docker.sock 마운트
                   ↓
         [Host Docker Daemon]
              └─ Pipeline Step Containers ← docker images에서 보임
                    (auth-proxy, dvcs-tools, default-image 등)
```

Runner Pod는 호스트의 docker.sock을 마운트하여 Pod 내부에서 `docker` 명령을 실행할 수 있게 된다. 이렇게 실행된 컨테이너들은 **Pod 내부가 아닌 호스트의 Docker 데몬**에서 관리된다.

1. **K3s (containerd)**: Runner Pod 자체를 실행
   - Runner 이미지(`bitbucket-pipelines-runner`)를 pull
   - containerd의 이미지 저장소에 저장됨 (`/var/lib/rancher/k3s/agent/containerd/`)

2. **Host Docker Daemon**: Runner가 파이프라인 실행 시 사용
   - 파이프라인 step별로 필요한 컨테이너를 실행
   - 관련 이미지(`auth-proxy`, `dvcs-tools` 등)를 pull
   - Docker의 이미지 저장소에 저장됨 (`/var/lib/docker/overlay2/`)

<br>

## 참고: 각 이미지의 역할

Docker 런타임에서 보이는 이미지들의 역할은 다음과 같다.

| 이미지 | 역할 |
|--------|------|
| `bitbucket-pipelines-auth-proxy` | Bitbucket과의 인증 처리 |
| `bitbucket-pipelines-dvcs-tools` | Git 관련 도구 (clone, checkout 등) |
| `atlassian/default-image` | 파이프라인 step의 기본 이미지 |
| `k8s-docker.packages.atlassian.com/pause` | 컨테이너 네트워크 설정용 |

이 이미지들은 파이프라인 실행 시 Runner가 Docker를 통해 pull하고 실행한다.

<br>

# 이전 사례와의 비교

| 항목 | [중복 저장 문제]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %}) | 이번 사례 |
|------|----------------------|----------|
| 현상 | 같은 이미지가 두 런타임에 저장 | 다른 이미지가 각 런타임에 저장 |
| 원인 | 런타임 전환 과정에서 기존 이미지 잔존 | DooD 구조로 인한 의도적 분리 |
| 문제 여부 | 디스크 낭비 (정리 필요) | 정상 동작 (정리 불필요) |
| 해결 방법 | 미사용 런타임의 이미지 정리 | 해결 필요 없음 |

이번 사례는 **문제가 아니라 정상적인 동작**이다. DooD 구조상 두 런타임이 각각의 역할을 수행하므로, 이미지가 분리되는 것이 당연하다.

<br>

# 결론

DooD 환경에서는 **두 런타임이 각각 다른 이미지를 관리**할 수 있다. 이는 중복 저장 문제가 아니라 자연스러운 구조다.

- containerd: 오케스트레이션 레이어 (Pod 관리)
- Docker: 애플리케이션 레이어 (파이프라인 실행)

<br>


| 질문 | 답변 |
|------|------|
| 왜 두 런타임에서 다른 이미지가 보이는가? | DooD 구조로 인해, Runner Pod는 containerd에서, 파이프라인 컨테이너는 Docker에서 실행되기 때문 |
| 이것은 문제인가? | 아니다. Bitbucket Pipelines가 Docker를 요구하므로 의도된 구조 |



