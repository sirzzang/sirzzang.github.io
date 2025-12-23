---
title:  "[Container] Docker와 containerd 이미지 관리 비교 - 4. 같은 이미지이지만 중복 저장이 아닌 경우"
excerpt: docker와 crictl에서 같은 이미지가 보이는 현상이 실제 중복 저장인지 확인해 보자.
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

k3s agent 노드에서 `docker images`와 `crictl images`로 같은 이미지 ID를 가진 이미지가 보여서, [이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %})에서 다룬 것처럼 **중복 저장** 문제인지 의심했다. 하지만 실제로는 중복 저장이 아니었다.

```bash
$ sudo crictl images | grep 56371aef8cc2
example/my-app    1.0-prod    56371aef8cc26    1.81GB
$ docker images | grep 56371aef8cc2
example/my-app    1.0-prod    56371aef8cc2    1.81GB
```

분석 결과는 다음과 같다.

1. **중복 저장 아님**: `docker` CLI와 `crictl` CLI가 **같은 런타임(Docker runtime)**을 보고 있었음
2. **런타임 설정**: k3s가 `--docker` 플래그로 실행되어 Docker runtime을 사용하도록 설정됨
3. **crictl 설정**: crictl이 cri-dockerd를 통해 Docker runtime을 바라보도록 설정되어 있음
4. **실제 중복 저장**: 서로 다른 런타임(Docker runtime과 k3s 내장 containerd)이 각각 이미지를 pull할 때만 발생

<br>

---

이전 글에서 다룬 [컨테이너 이미지 중복 저장 문제]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %})와 비슷해 보였지만, 실제로는 다른 상황이었다. 이 글에서는 **같은 이미지가 중복 저장된 것처럼 보였지만 실제로는 그렇지 않았던 경우**를 다룬다.

<br>

# 문제

k3s agent 노드에서 이미지 목록을 확인하다가, 같은 이미지 ID를 가진 이미지가 `docker` CLI와 `crictl` CLI에서 모두 보였다.

```bash
$ sudo crictl images | grep 56371aef8cc2
example/my-app    1.0-prod    56371aef8cc26    1.81GB
$ docker images | grep 56371aef8cc2
example/my-app    1.0-prod    56371aef8cc2    1.81GB
```

이전 글에서 다룬 것처럼, 같은 이미지가 두 벌 저장되어 디스크가 낭비되는 문제를 겪었던 경험이 있어서, 이번에도 같은 문제인지 확인해야 했다.

하지만 이전 사례와 다른 점이 있었다.

1. **크기가 동일**: 이전 사례에서는 `docker`로 보면 20.3GB, `crictl`로 보면 10.4GB로 다르게 나타났지만, 이번에는 둘 다 1.81GB로 동일했다.
2. **이미지 삭제 테스트**: `docker rmi`로 이미지를 삭제하면 `crictl images`에서도 사라졌다.

이것은 실제로 중복 저장이 아니라, **같은 런타임을 다른 CLI로 보고 있는 상황**일 가능성을 시사했다.

<br>

# 분석

## 서버 환경 확인

먼저 k3s가 어떤 런타임을 사용하도록 설정되어 있는지 확인했다.

```bash
$ systemctl cat k3s-agent
# /etc/systemd/system/k3s-agent.service
[Service]
ExecStart=/usr/local/bin/k3s \
    agent \
        '--docker' \
        ...
```

k3s가 **`--docker` 플래그**로 실행되고 있었다. 이는 k3s가 내장 containerd 대신 Docker runtime을 사용하도록 설정되어 있다는 의미다.

<br>

## crictl 설정 확인

crictl이 어떤 런타임 엔드포인트를 바라보고 있는지 확인했다.

```bash
$ sudo crictl config --get runtime-endpoint
unix:///run/k3s/cri-dockerd/cri-dockerd.sock
```

<br>

crictl이 `cri-dockerd.sock`을 바라보고 있었다. 이것은 중요한 단서였다.

**cri-dockerd**는 Docker를 CRI 호환 런타임으로 만들어주는 어댑터로, k3s가 `--docker` 플래그로 실행될 때 사용된다. cri-dockerd에 대한 자세한 설명은 [이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %}#서버-환경-설명)에서 확인할 수 있다.

k3s가 `--docker` 플래그로 실행되면 crictl → cri-dockerd → Docker → containerd 경로로 연결되어, `crictl` CLI를 통해 Docker runtime의 이미지를 확인할 수 있게 된다.

<br>

## 실제 검증

### 1. 이미지 저장 위치 확인

```bash
# Docker 이미지 저장 위치
$ sudo du -sh /var/lib/docker/overlay2
115G    /var/lib/docker/overlay2

# k3s 내장 containerd 이미지 저장 위치 (존재하지 않음)
$ sudo ls -al /var/lib/rancher/k3s/agent/containerd/
ls: cannot access '/var/lib/rancher/k3s/agent/containerd/': No such file or directory

# k3s agent 디렉토리 확인
$ sudo ls -al /var/lib/rancher/k3s/agent/
drwxr-xr-x 3 root root 4096 cri-dockerd
drwx------ 5 root root 4096 etc
...
```

k3s 내장 containerd 디렉토리가 존재하지 않았다. 대신 `cri-dockerd` 디렉토리만 있었다. 이는 k3s가 내장 containerd를 사용하지 않고 Docker runtime을 사용하고 있음을 의미한다.

> **참고: k3s 내장 containerd를 사용하는 경우**
>
> k3s가 내장 containerd를 사용하도록 설정되어 있다면(`--docker` 플래그 없이 실행), `/var/lib/rancher/k3s/agent/containerd/` 디렉토리가 생성되고 이미지가 여기에 저장된다. 이 디렉토리 구조와 이미지 저장 방식에 대한 자세한 내용은 [이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %}#서버-환경-설명)에서 확인할 수 있다.
 
<br>

```bash
# cri-dockerd 디렉토리 구조 확인
$ sudo ls -al /var/lib/rancher/k3s/agent/cri-dockerd/
drwxr-xr-x 2 root root 4096 sandbox
```

cri-dockerd 디렉토리 구조를 확인해 보니 `sandbox` 디렉토리만 존재했다. 이 디렉토리는 쿠버네티스 Pod의 샌드박스(sandbox) 정보를 저장하는 곳으로, cri-dockerd가 각 Pod의 네트워크 네임스페이스와 관련된 메타데이터를 관리하기 위해 사용한다.

**cri-dockerd는 이미지를 직접 저장하지 않고**, Docker runtime이 관리하는 이미지를 참조한다. 따라서 실제 이미지는 Docker runtime이 관리하고, `/var/lib/docker/overlay2`에 저장된다.

<br>

### 2. 이미지 삭제 테스트

같은 이미지를 `docker rmi`로 삭제했을 때 `crictl images`에서도 사라지는지 확인했다.

```bash
$ docker images | grep 9ca93f9d4556
example/my-app    <none>    9ca93f9d4556    5 weeks ago    1.8GB
$ sudo crictl images | grep 9ca93f9d4556
example/my-app    <none>    9ca93f9d4556a    1.8GB

$ docker rmi 9ca93f9d4556
Untagged: example/my-app@sha256:5585ad9f290dad6358feb27bf5a4793411e96635cfafc65151afcc1271b39257
Deleted: sha256:9ca93f9d4556acf7a313c5a0188d5a7f56d88be2bad84dd50732486f6c43c379
...

$ sudo crictl images | grep 9ca93f9d4556
(결과 없음)
```

`docker rmi`로 삭제한 이미지가 `crictl images`에서도 사라졌다. 이것은 **두 CLI가 같은 이미지 저장소를 보고 있다**는 강력한 증거다.

<br>

### 3. containerd 소켓 확인

실행 중인 containerd 인스턴스를 확인했다.

```bash
$ ps aux | grep containerd | grep sock
root  770  /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
root  ...  /usr/bin/containerd-shim-runc-v2 -namespace moby -address /run/containerd/containerd.sock
```

Docker가 사용하는 containerd만 실행 중이었고, k3s 내장 containerd는 실행되지 않았다.

<br>

## 왜 같은 이미지가 보였는가?

`docker` CLI와 `crictl` CLI가 **같은 Docker runtime**을 보고 있었기 때문에, 같은 이미지가 보였던 것이다. 실제로는 중복 저장이 아니었다. 

정리하면 다음과 같다.

| 항목 | 내용 |
|------|------|
| k3s 런타임 설정 | `--docker` 플래그로 Docker runtime 사용 |
| crictl 엔드포인트 | `unix:///run/k3s/cri-dockerd/cri-dockerd.sock` |
| cri-dockerd 역할 | Docker를 CRI 호환 런타임으로 변환하는 어댑터 |
| 이미지 저장 위치 | `/var/lib/docker/overlay2` (하나만 존재) |

<br>

# 실제 중복 저장이 발생하는 경우

실제로 중복 저장이 발생하는 경우는 다음과 같다.

## 케이스 1: 런타임 전환 과정

[이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %})에서 다룬 것처럼, k3s의 런타임을 Docker runtime에서 containerd로 변경하는 과정에서:

- 기존: Docker runtime(dockerd)이 `/var/lib/docker/overlay2`에 이미지 저장
- 변경 후: k3s 내장 containerd가 `/var/lib/rancher/k3s/agent/containerd`에 이미지 저장
- 결과: 같은 이미지가 두 경로에 각각 저장됨

<br>

## 케이스 2: 두 런타임이 동시에 실행 중

```bash
# 두 개의 containerd 인스턴스가 실행 중
$ ps aux | grep containerd | grep sock
root  /usr/bin/dockerd --containerd=/run/containerd/containerd.sock
root  /var/lib/rancher/k3s/.../containerd-shim-runc-v2 -namespace k8s.io -address /run/k3s/containerd/containerd.sock
```

두 런타임이 동시에 실행 중일 때:
- Docker의 containerd: `/run/containerd/containerd.sock` (namespace: `moby`)
- k3s 내장 containerd: `/run/k3s/containerd/containerd.sock` (namespace: `k8s.io`)

아래와 같은 경우에 중복 저장이 발생할 수 있다:
- 로컬에서 `docker build`를 통해 이미지를 빌드한 후, k3s로 같은 이미지를 사용하는 파드 배포
- 로컬에서 테스트용으로 `docker pull`을 통해 이미지를 pull한 후, k3s로 같은 이미지를 사용하는 파드 배포

<br>

# 중복 저장 여부 확인 방법

같은 이미지가 여러 CLI에서 보일 때, 실제 중복 저장인지 확인하는 방법을 정리하면 다음과 같다.

## 1. 런타임 설정 확인

```bash
# k3s 런타임 설정 확인
$ systemctl cat k3s-agent | grep docker
ExecStart=/usr/local/bin/k3s agent '--docker'

# 또는
$ ps aux | grep k3s | grep docker
```

- `--docker` 플래그가 있으면: Docker runtime 사용 → 중복 저장 가능성 낮음
- `--docker` 플래그가 없으면: k3s 내장 containerd 사용 → 중복 저장 가능성 확인 필요

<br>

## 2. crictl 엔드포인트 확인

```bash
$ sudo crictl config --get runtime-endpoint
```

- `unix:///run/k3s/cri-dockerd/cri-dockerd.sock`: Docker runtime → 중복 저장 아님
- `unix:///run/k3s/containerd/containerd.sock`: k3s 내장 containerd → 중복 저장 가능성 확인 필요

<br>

## 3. 이미지 저장 위치 확인

```bash
# Docker 이미지 저장 위치
$ sudo du -sh /var/lib/docker/overlay2

# k3s 내장 containerd 이미지 저장 위치
$ sudo du -sh /var/lib/rancher/k3s/agent/containerd/
```

두 디렉토리가 모두 존재하고 용량이 크면, 중복 저장 가능성이 높다.

<br>

## 4. 이미지 삭제 테스트

```bash
# docker로 이미지 삭제
$ docker rmi <IMAGE_ID>

# crictl에서도 사라지는지 확인
$ sudo crictl images | grep <IMAGE_ID>
```

- `crictl`에서도 사라지면: 같은 런타임을 보고 있음 → 중복 저장 아님
- `crictl`에서 여전히 보이면: 다른 런타임을 보고 있음 → 중복 저장 가능성 높음

<br>

## 5. containerd 인스턴스 확인

```bash
$ ps aux | grep containerd | grep sock
```

- 하나의 containerd만 실행 중이면: 중복 저장 아님
- 두 개의 containerd가 실행 중이면: 중복 저장 가능성 확인 필요

<br>

# 결론

처음에 제시한 의문에 대한 답을 정리하면 다음과 같다.

| 의문 | 답변 |
|------|------|
| 같은 이미지가 중복 저장된 것인가? | 아니다. `docker` CLI와 `crictl` CLI가 같은 런타임을 보고 있었다. |
| 왜 같은 이미지가 보였는가? | k3s가 `--docker` 플래그로 실행되어 Docker runtime을 사용하고, crictl이 cri-dockerd를 통해 같은 Docker runtime을 바라보고 있었기 때문이다. |
| 실제 중복 저장은 언제 발생하는가? | 서로 다른 런타임(Docker runtime과 k3s 내장 containerd)이 각각 이미지를 pull할 때 발생한다. |

<br>

## 배운 점

### CLI와 런타임을 구분할 것

`docker` CLI와 `crictl` CLI가 같은 이미지를 보여준다고 해서 반드시 중복 저장인 것은 아니다. 각 CLI가 어떤 런타임을 바라보고 있는지 확인해야 한다.

- `docker` CLI: 항상 Docker runtime (`/var/run/docker.sock`)
- `crictl` CLI: 설정에 따라 다름 (cri-dockerd 또는 k3s 내장 containerd)

### k3s 런타임 설정을 이해할 것

k3s는 다양한 런타임을 사용할 수 있다:

- **내장 containerd** (기본값): `k3s agent` (플래그 없음)
- **Docker runtime**: `k3s agent --docker`
- **외부 CRI 런타임**: `k3s agent --container-runtime-endpoint <ENDPOINT>`

런타임 설정에 따라 crictl이 바라보는 엔드포인트가 달라진다.

### 실제 검증을 통해 확인할 것

의심만으로는 부족하다. 다음을 통해 실제로 확인해야 한다:

1. 런타임 설정 확인
2. crictl 엔드포인트 확인
3. 이미지 저장 위치 확인
4. 이미지 삭제 테스트

### cri-dockerd의 역할을 이해할 것

Docker 자체는 CRI 인터페이스를 따르지 않지만, **cri-dockerd**라는 어댑터를 통해 CRI 호환 런타임으로 동작할 수 있다. k3s가 `--docker` 플래그로 실행되면 k3s → cri-dockerd → Docker → containerd 경로로 연결되어, crictl을 통해 Docker runtime의 이미지를 확인할 수 있게 된다. cri-dockerd에 대한 자세한 설명은 [이전 글]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-3 %}#서버-환경-설명)에서 확인할 수 있다.

<br>

## k3s 런타임 선택 가이드

| 런타임 | 설정 방법 | 장점 | 단점 | 권장 상황 |
|--------|----------|------|------|----------|
| 내장 containerd | `k3s agent` (기본값) | k3s에 최적화, 가벼움, 빠름 | k3s에 종속적 | **대부분의 경우 권장** |
| Docker | `k3s agent --docker` | 익숙한 `docker` CLI 사용 가능 | cri-dockerd 레이어 추가, 오버헤드 | 로컬 개발, 레거시 워크플로우 |
| CRI-O | `k3s agent --container-runtime-endpoint` | Kubernetes 전용, OCI 표준 | 별도 설치/관리 필요 | OpenShift, Red Hat 환경 |

**권장 사항**: 특별한 이유가 없다면 k3s 내장 containerd를 사용하는 것이 좋다.

<br>

---

*처음에는 중복 저장 문제인 줄 알았지만, 실제로는 같은 런타임을 다른 CLI로 보고 있던 것이었다. 때로는 비슷해 보이는 현상도 자세히 살펴보면 다른 원인일 수 있다.*
