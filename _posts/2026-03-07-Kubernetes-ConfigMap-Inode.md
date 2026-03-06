---
title:  "[Kubernetes] ConfigMap 업데이트와 bind mount"
excerpt: "ConfigMap 일반 mount와 subPath mount의 업데이트 반영 차이를 inode 관점에서 분석해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - ConfigMap
  - subPath
  - bind mount
  - inode
  - kubelet
---

<br>

Docker 컨테이너에 bind mount한 파일이 호스트에서 바뀌어도 컨테이너에 반영되지 않는 문제가 있다. bind mount가 mount 시점의 inode를 참조하기 때문인데, 심볼릭 링크 대상이 바뀌거나 파일이 삭제-재생성되면 inode가 달라져 mount가 끊긴다. 이 문제를 [Docker 타임존 동기화 글]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %})에서 다룬 적이 있다.

ConfigMap 동작 원리를 공부하던 중, 이 문제가 갑자기 떠올랐다. [Kubernetes 공식 문서](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/#mounted-configmaps-are-updated-automatically)에 이런 내용이 있다.

> A container using a ConfigMap as a subPath volume mount will not receive ConfigMap updates.

subPath로 마운트한 ConfigMap은 업데이트가 반영되지 않는다는 것. 왜 그런지에 대해 살펴 보다, 불현듯 "이거 그때 그 Docker Container Timezone 문제랑 같은 거 아닌가?" 싶었다. 파고 들어가다 보니 정확히 같은 뿌리였다.

<br>

# TL;DR

- ConfigMap **일반 mount**: kubelet이 심볼릭 링크 atomic swap으로 업데이트. 파드 재시작 없이 반영된다(다만 전파 지연이 있다).
- ConfigMap **subPath mount**: 개별 파일을 직접 bind mount. 파드 재시작 없이는 반영되지 않는다.
- subPath가 업데이트되지 않는 이유: [Docker 타임존 동기화 문제]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %})와 **근본적으로 같은 원인**으로, bind mount가 mount 시점의 inode를 잡기 때문이다.

<br>

# ConfigMap 볼륨 마운트

ConfigMap을 파드에서 사용하는 방법 중 하나는 볼륨으로 마운트하는 것이다. ConfigMap의 각 키가 **파일 이름**이 되고, 값이 **파일 내용**이 되어 컨테이너 파일 시스템에 나타난다. `nginx.conf`나 `application.properties`처럼 설정 파일 자체를 컨테이너 내부에 배치해야 할 때 쓴다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp
spec:
  containers:
  - name: webapp
    image: nginx
    volumeMounts:
    - name: config-volume
      mountPath: /etc/config
  volumes:
  - name: config-volume
    configMap:
      name: app-config
```

이렇게 하면 `/etc/config/` 아래에 ConfigMap의 키가 파일로 생긴다.

```bash
/etc/config/APP_COLOR   # 내용: blue
/etc/config/APP_MODE    # 내용: prod
```

그런데 컨테이너 내부에서 이 디렉토리의 실제 구조를 들여다보면, 단순한 파일이 아니다.

<br>

# 일반 mount의 내부 구조: 심볼릭 링크 체인

컨테이너 안에서 마운트된 ConfigMap 디렉토리를 자세히 보면 이렇게 생겼다.

```bash
/etc/config/
├── ..data           → ..2024_03_06_09_00_00.123456/   # 심볼릭 링크
├── ..2024_03_06_09_00_00.123456/                       # 실제 데이터 디렉토리
│   ├── APP_COLOR    # 내용: blue
│   └── APP_MODE     # 내용: prod
├── APP_COLOR        → ..data/APP_COLOR                 # 심볼릭 링크
└── APP_MODE         → ..data/APP_MODE                  # 심볼릭 링크
```

앱이 `/etc/config/APP_COLOR`를 읽으면, 심볼릭 링크 체인을 따라간다.

```
APP_COLOR → ..data/APP_COLOR → ..2024_03_06.../APP_COLOR → "blue"
```

왜 이렇게 복잡한 구조를 쓰는 걸까?

<br>

## 원자적 업데이트를 위한 설계

ConfigMap이 바뀌면 마운트된 파일도 바뀌어야 한다. 그런데 파일을 하나씩 덮어쓰면, 읽는 시점에 따라 일부는 옛날 값이고 일부는 새 값인 불일치 상태가 생길 수 있다. 이를 방지하기 위해 kubelet은 심볼릭 링크를 이용해 **한 번에 전체를 교체**한다.

교체 과정은 다음과 같다.

**1단계** — kubelet이 새 타임스탬프 디렉토리를 만들고 새 데이터를 쓴다.

```bash
..2024_03_06_10_30_00.987654/
├── APP_COLOR    # 내용: green (변경됨)
└── APP_MODE     # 내용: staging (변경됨)
```

**2단계** — 새 디렉토리를 가리키는 임시 심볼릭 링크(`..data_tmp`)를 생성한 뒤, `rename()` 시스템 콜로 기존 `..data`를 원자적으로 교체한다.

```bash
# Before — 임시 심볼릭 링크 생성 후, rename() 직전 상태
..data     → ..2024_03_06_09_00_00.123456/   (기존)
..data_tmp → ..2024_03_06_10_30_00.987654/   (새로 생성)

# After — rename("..data_tmp", "..data")
..data     → ..2024_03_06_10_30_00.987654/
```

`rename()`은 심볼릭 링크의 타겟을 변경하는 것이 아니라, **심볼릭 링크 파일 자체를 교체**한다. 파일시스템 수준에서 한 번에 이루어지므로 중간 상태가 없고, `..data`가 순간적으로 새 디렉토리를 가리키게 되어 모든 파일이 **동시에** 새 버전을 가리킨다. [Docker 타임존 동기화 글]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#1단계-inotify-기반-타임존-변경-감시-스크립트)에서 `timedatectl`이 임시 파일을 만든 뒤 `rename()`으로 교체하는 atomic swap 패턴을 다뤘는데, kubelet도 정확히 같은 패턴을 사용한다.

**3단계** — 이전 디렉토리를 삭제한다.

```bash
rm -rf ..2024_03_06_09_00_00.123456/
```

이 방식이 동작하는 이유는, 컨테이너에 마운트된 것이 **디렉토리**이기 때문이다. 디렉토리의 inode를 잡고 있으므로, 디렉토리 안의 심볼릭 링크가 바뀌면 컨테이너가 디렉토리를 읽을 때 새 링크를 따라간다. [Docker 타임존 동기화 글]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#디렉토리-bind-mount)에서 다룬 "디렉토리 마운트로 inode 불일치를 우회한다"는 원리와 같다.


### 참고: 업데이트 전파 지연

"파드 재시작 없이 반영된다"고 했지만, 즉시 반영되는 것은 아니다. kubelet이 주기적으로 ConfigMap의 변경을 확인하고 로컬 캐시를 거쳐 업데이트하기 때문에 전파 지연이 발생한다. [Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically)에서는 ConfigMap이 업데이트된 시점부터 파드에 반영되기까지의 총 지연이 **kubelet 동기화 주기 + 캐시 전파 지연**의 합산만큼 걸릴 수 있다고 설명하고 있다. 캐시 전파 지연은 캐시 유형(watch, TTL, API 서버 직접 조회)에 따라 달라진다.

> As a result, the total delay from the moment when the ConfigMap is updated to the moment when new keys are projected to the Pod can be as long as the kubelet sync period + cache propagation delay, where the cache propagation delay depends on the chosen cache type (it equals to watch propagation delay, ttl of cache, or zero correspondingly).
>
> — [Kubernetes Documentation: Mounted ConfigMaps are updated automatically](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically)

<br>

# subPath mount

`subPath`는 ConfigMap의 특정 키 하나를 컨테이너의 특정 경로에 마운트할 때 쓴다. 기존 디렉토리의 다른 파일을 가리지 않고, 원하는 파일 하나만 끼워 넣을 수 있어서 편리하다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp
spec:
  containers:
  - name: webapp
    image: nginx
    volumeMounts:
    - name: config-volume
      mountPath: /etc/nginx/nginx.conf
      subPath: nginx.conf
  volumes:
  - name: config-volume
    configMap:
      name: nginx-config
```

이렇게 하면 `/etc/nginx/` 디렉토리의 다른 파일들은 그대로 유지되고, `nginx.conf`만 ConfigMap 값으로 대체된다.

편리하지만 대가가 있다. **ConfigMap을 업데이트해도 파드를 재시작하지 않으면 반영되지 않는다.**

<br>

## subPath가 업데이트되지 않는 이유

`subPath`는 내부적으로 **개별 파일을 직접 bind mount**한다. 디렉토리 수준이 아니라 파일 수준이다.

컨테이너 시작 시점에 kubelet이 볼륨 내의 특정 파일을 bind mount하는데, 이때 심볼릭 링크 체인을 따라간 **최종 실제 파일의 inode**를 직접 잡는다.

```
[컨테이너 시작 시점 — v1]
subPath mount → ..data/nginx.conf → ..2024_v1/nginx.conf (inode #1234)
컨테이너 내부: /etc/nginx/nginx.conf → inode #1234에 직접 바인드
```

ConfigMap이 업데이트되면, kubelet이 `..data` 링크를 새 디렉토리로 교체한다. 그런데 subPath로 마운트된 파일은 심볼릭 링크 체인을 거치지 않는다. 이미 resolve된 최종 파일의 inode에 직접 바인드되어 있다.

```
[업데이트 후 — v2]
..data → ..2024_v2/nginx.conf (inode #5678)  ← 새 파일
컨테이너의 subPath mount → inode #1234       ← 여전히 옛 inode
```

kubelet이 `..data` 링크를 아무리 교체해도, bind mount는 이미 resolve된 옛날 inode를 계속 바라본다. 반영이 안 되는 게 당연하다.

파드를 재시작하면 kubelet이 볼륨을 처음부터 다시 마운트한다. 이때 최신 ConfigMap 데이터로 새 디렉토리를 만들고, subPath도 새 파일의 inode를 잡으니까 최신 값이 반영된다.

> 참고: subPath 한계를 우회하는 방법
>
> 파드 재시작 없이 ConfigMap 변경을 반영해야 한다면, subPath 대신 다음과 같은 방법을 고려할 수 있다.
> - **디렉토리 전체 마운트 + 컨테이너 내부 심볼릭 링크**: ConfigMap을 별도 경로에 디렉토리로 마운트하고, 컨테이너 엔트리포인트에서 필요한 파일만 심볼릭 링크로 연결한다. [Docker 타임존 동기화 글의 4단계]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#4단계-컨테이너-내부-심볼릭-링크-재설정)와 같은 발상이다.
> - **사이드카 컨테이너**: ConfigMap 변경을 감시하는 사이드카를 두고, 변경 시 설정 파일을 갱신하거나 메인 프로세스에 시그널을 보내 reload한다.

<br>

# 디렉토리 mount vs. 파일 mount

[Docker 타임존 동기화 글]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#bind-mount)에서 파일 bind mount와 디렉토리 bind mount의 차이를 다뤘다. 핵심 차이는 **디렉토리 inode를 잡느냐, 파일 inode를 잡느냐**다.

## 일반 볼륨 mount

디렉토리 전체를 bind mount한다. 컨테이너가 보는 건 디렉토리의 inode다. 디렉토리 안의 내용물(심볼릭 링크 포함)은 접근할 때마다 다시 탐색된다. kubelet이 `..data` 심볼릭 링크를 교체하면, 컨테이너가 디렉토리를 읽을 때 새 링크를 따라간다.

```
mount: /etc/config/ (디렉토리 inode)
       └── ..data → 새 디렉토리로 교체 가능
```

## subPath mount

개별 파일을 bind mount한다. 컨테이너가 보는 건 파일의 inode 자체다. 심볼릭 링크를 resolve한 최종 파일의 inode에 직접 바인드되어 있으므로, 원본 쪽에서 심볼릭 링크가 바뀌어도 bind mount는 옛날 inode를 계속 바라본다.

```
mount: /etc/nginx/nginx.conf → inode #1234 (직접 바인드)
       원본에서 ..data 링크 교체 → inode #5678
       컨테이너는 여전히 inode #1234
```

<br>

# Docker 타임존 문제와 같은 뿌리

여기까지 살펴 보면 [Docker 타임존 동기화 문제]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %})와 겹쳐 보인다. 호스트의 `/etc/localtime`을 Docker 컨테이너에 bind mount하면, 호스트에서 심볼릭 링크 대상이 바뀌어도 컨테이너가 mount 시점의 inode를 계속 바라본다. ConfigMap subPath와 정확히 같은 구조다.

| 상황 | 근본 원인 |
|---|---|
| ConfigMap subPath | 시작 시 resolve된 inode에 바인드 → 링크 교체해도 반영 안 됨 |
| Docker 타임존 파일 | 시작 시 resolve된 inode에 바인드 → 링크 교체 또는 파일 재생성해도 반영 안 됨 |

둘 다 **"bind mount는 mount 시점의 inode를 잡는다"**는 같은 원리다. 심볼릭 링크가 나중에 다른 곳을 가리키든, 파일이 삭제-재생성되든, bind mount 쪽은 원래 inode를 계속 본다.

<br>

# 해결 전략의 비교

같은 원인이지만, 해결 방식은 문맥에 따라 다르다.

| 케이스 | mount 방식 | 업데이트 전략 | 결과 |
|---|---|---|---|
| ConfigMap 일반 mount | 디렉토리 bind mount | kubelet symlink atomic swap | 자동 반영 |
| ConfigMap subPath | 파일 bind mount | 없음 | 파드 재시작 필요 |
| [Docker 타임존]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}) | 디렉토리 bind mount | inotify 감지 + 파일 복사 | 자동 반영 |

ConfigMap 일반 mount와 Docker 타임존 해결책은 전략이 같다. **mount 단위를 파일에서 디렉토리로 올려서 inode 불일치 문제를 우회**하는 것이다. ConfigMap subPath에는 이 전략이 적용되어 있지 않으므로 파드 재시작만이 답인데, [Docker 타임존 동기화 글]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#컨테이너-재시작)에서 다뤘듯 재시작은 불필요한 다운타임과 운영 부담을 수반한다.


- kubelet subPath: 파일 inode 고정 → 내용 변경 방법 없음 → 재시작만이 답
- Docker 타임존 동기화 해결책: 디렉토리 inode 고정 → 안의 파일 교체는 보임 → 재시작 없이 반영
- kubelet 일반 mount:  디렉토리 inode 고정 → 안의 심볼릭 링크 교체는 보임 → 자동 반영


<br>

# 정리

하나의 원리가 세 가지 다른 양상으로 나타난다.

1. **ConfigMap 일반 mount** — 디렉토리 bind mount + symlink atomic swap. 디렉토리 inode를 잡고 있으므로, 안의 심볼릭 링크가 교체되면 자동 반영된다.
2. **ConfigMap subPath mount** — 파일 bind mount. 파일 inode를 직접 잡고 있으므로, 원본이 교체되어도 반영되지 않는다.
3. **[Docker 파일 bind mount]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %})** — 파일 bind mount. 2번과 정확히 같은 문제.

세 케이스 모두 **bind mount가 mount 시점의 inode를 참조한다**는 하나의 원리에서 비롯된다. 그리고 이 문제의 해결 전략도 하나다: **mount 단위를 파일에서 디렉토리로 올리면 inode 불일치를 우회할 수 있다.**

과거에 겪었던 Docker 타임존 동기화 문제가, Kubernetes ConfigMap의 subPath 제약과 정확히 같은 메커니즘이었다. 결국 파일시스템 수준의 동작 원리를 이해하면, 추상화된 도구의 제약과 설계가 왜 그런 모양인지 보이기 시작한다.

<br>
