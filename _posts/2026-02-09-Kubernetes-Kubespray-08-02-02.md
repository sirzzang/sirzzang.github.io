---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: kubespray-offline - 2. Downloads / Mirror"
excerpt: "Kubespray의 다운로드 메커니즘과 변수 체계, 그리고 공개 미러 설정 방법을 이해해보자."
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
  - kubespray-offline
  - Ansible
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 Kubespray 공식 문서 [`downloads.md`](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/advanced/downloads.md)와 [`mirror.md`](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/mirror.md)를 분석한다.

[이전 글(8.2.1)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 "어떤 아티팩트가 필요하고, 어떤 서빙 인프라를 구성하고, 어떤 변수를 설정하라"는 **전체 가이드**를 살펴봤다면, 이번 글에서는 Kubespray가 **실제로 다운로드를 어떻게 수행하는지** — 즉, 다운로드의 내부 동작 원리를 살펴 본다.

- **변수 그룹**: 다운로드 전략 / Pull 정책 / 캐싱 전략의 3개 그룹으로 분류
- **다운로드 전략**: `download_run_once`, `download_localhost` 조합에 따른 동작 차이와 오프라인 환경 권장 설정
- **Pull 정책**: 이미 있는 이미지를 다시 받을지 결정하는 변수
- **캐싱 전략**: 다운로드 캐시의 동작 원리와 디스크 영향
- **아티팩트 변수 네이밍 컨벤션**: 바이너리/컨테이너 이미지의 변수 정의 패턴
- **Public Download Mirror**: 공개 미러의 목적, 설정 방법, 오프라인 환경에서의 활용

> **참고**: `downloads.md`도 `offline-environment.md`처럼 줄글로 풀어져 있어서 처음 읽으면 이해하기가 쉽지 않다. 이 글에서는 변수를 그룹별로 분류하고, 조합별 동작을 다이어그램으로 정리한다.

<br>

# 변수 그룹 한눈에

`downloads.md`에는 다운로드와 관련된 변수가 여러 개 나오는데, 크게 **3개 그룹**으로 분류하면 전체 그림이 잡힌다. 각 그룹은 **독립적으로 동작**한다. 다운로드 전략이 뭐든 Pull 정책은 동일하게 적용되고, 캐싱 전략도 별도로 동작한다.

| 그룹 | 답하는 질문 | 변수 |
|------|-----------|------|
| **다운로드 전략** | **누가, 어디서** 다운로드하나? | `download_run_once`, `download_localhost` |
| **Pull 정책** | **언제** (다시) 다운로드하나? | `k8s_image_pull_policy`, `download_always_pull` |
| **캐싱 전략** | 다운로드한 걸 **어떻게 재사용**하나? | `download_cache_dir`, `download_force_cache`, `download_keep_remote_cache` |

<br>

# 다운로드 전략

다운로드 전략을 결정하는 변수는 두 가지다.

| 변수 | 의미 | 기본값 |
|------|------|--------|
| `download_run_once` | 다운로드를 **한 번만** 할지, **각 노드가 개별로** 할지 | `false` |
| `download_localhost` | 다운로드를 **Ansible master(admin)**에서 할지, **delegate 노드**에서 할지 | `false` |

## download_run_once

`download_run_once`의 "once"는 **클러스터 전체에서 딱 한 번만 수행한다**는 뜻이다.

- `false` (기본값): 각 노드가 개별적으로 자기한테 필요한 바이너리/이미지를 다운로드
- `true`: **download delegate** 한 곳에서만 다운로드하고, 나머지 노드에는 push

## download_localhost와 download delegate

`download_run_once: true`일 때, Kubespray는 다운로드 task를 특정 노드에 delegate한다. 이 **download delegate** — 다운로드 역할을 위임받은 노드 — 가 모든 파일/이미지를 받은 뒤 나머지 노드에 배포하는 구조다. Ansible의 `delegate_to` 개념에서 온 용어다.

`download_localhost`는 이 delegate를 누구로 할지 결정한다.

- `false`: 첫 번째 `kube_control_plane` 노드가 delegate
- `true`: Ansible master(admin)가 delegate

여기서 "localhost"란 Ansible에서 `ansible-playbook` 명령을 실행하는 머신 자체를 가리킨다. `ansible-playbook cluster.yml`을 admin 서버에서 실행하니까, localhost = admin 서버가 되는 것이다.

| Ansible 관점 | 의미 |
|-------------|------|
| inventory에 있는 노드들 | 원격 대상 (SSH로 접속해서 task 실행) |
| localhost | Ansible을 실행하고 있는 바로 그 머신 (admin) |

따라서 `download_localhost: true`의 의미는 **"다운로드를 원격 노드에 위임하지 말고, 지금 Ansible을 돌리고 있는 이 머신(admin)에서 직접 하라"**는 뜻이다.

## 조합별 동작

두 변수의 조합에 따라 3가지 동작 모드가 나온다.

| 조합 | `download_run_once` | `download_localhost` | 동작 | 특징 |
|------|-------------------|---------------------|------|------|
| 각 노드가 개별로 pull | `false` (기본값) | (무관) | 각 노드가 직접 바이너리/이미지를 다운로드 | 가장 단순. 노드마다 외부 접근 필요 |
| delegate(control plane)이 pull → 각 노드에 push | `true` | `false` | 첫 번째 control plane이 전부 다운로드 → 각 노드에 배포 | delegate 노드에 모든 이미지가 쌓여서 스토리지 부담 |
| delegate(admin)이 pull → 각 노드에 push | `true` | `true` | Ansible master(admin)가 전부 다운로드 → 각 노드에 배포 | 클러스터 노드가 외부 접근 불가능할 때 유용. admin에 컨테이너 런타임 필요 |

각각의 흐름을 확인해 보자.

```
[1] download_run_once: false (기본)
    인터넷/내부서버 → 노드1이 직접 다운
    인터넷/내부서버 → 노드2가 직접 다운
    인터넷/내부서버 → 노드3이 직접 다운

[2] download_run_once: true + download_localhost: false
    인터넷/내부서버 → control plane(delegate)이 전부 다운
                        → 노드1에 push
                        → 노드2에 push
                        → 노드3에 push

[3] download_run_once: true + download_localhost: true
    인터넷/내부서버 → admin(Ansible master)이 전부 다운
                        → 노드1에 push
                        → 노드2에 push
                        → 노드3에 push
```

## 바이너리 파일의 배포 경로

주의할 점이 하나 있다. `download_localhost: false`여도 **바이너리 파일은 어차피 admin을 경유**한다.

> Note: even if `download_localhost` is false, files will still be copied to the Ansible server (local host) from the delegated download node, and then distributed from the Ansible server to all cluster nodes.

컨테이너 이미지와 바이너리 파일의 배포 경로가 다르다.

|  | `download_localhost: false` | `download_localhost: true` |
|---|---|---|
| **컨테이너 이미지** | delegate(control plane)에서 pull → delegate에서 직접 각 노드로 전송 | admin에서 pull → admin에서 각 노드로 전송 |
| **바이너리 파일** | delegate에서 다운로드 → **admin으로 복사** → admin에서 각 노드로 배포 | admin에서 다운로드 → admin에서 각 노드로 배포 |

바이너리 파일은 Ansible의 `fetch` → `copy` 패턴 때문에 어차피 admin을 경유한다. delegate에서 `fetch`해서 admin 로컬에 저장한 뒤, 거기서 각 노드에 `copy`하는 구조다.

## delegate 노드의 스토리지 부담

`download_run_once: true` + `download_localhost: false`일 때, delegate 노드(첫 번째 control plane)에 **해당 노드에 필요하지 않은 이미지까지 포함해서 전부** 다운로드된다. 모든 이미지가 컨테이너 런타임 스토리지에 로드되므로, `download_run_once: false`일 때보다 해당 노드의 스토리지 사용량이 커진다.

`download_localhost: true`로 하면 이 부담이 admin 노드로 옮겨간다. 클러스터 노드의 스토리지를 아낄 수 있다.

그러면 왜 `download_localhost: false`가 존재하는가? **admin에 컨테이너 런타임을 설치할 수 없거나 설치하고 싶지 않은 경우**다.

- admin이 순수 관리용 머신이라 docker/containerd를 깔기 싫은 경우
- admin이 다른 용도로도 쓰여서 컨테이너 런타임 설치가 부담인 경우
- 보안 정책상 admin에 컨테이너 런타임을 두지 않는 경우

이런 경우, control plane은 어차피 컨테이너 런타임이 있으니까 거기서 이미지 pull을 맡기고, 바이너리만 admin 경유로 배포하는 것이 합리적이다.

## 오프라인 환경에서의 권장 설정

오프라인 환경에서는 **`download_run_once: true`가 더 적합**하다. 모든 노드가 개별로 내부 서버에 접근하는 것보다, 한 곳에서 받아서 뿌리는 게 트래픽/관리 측면에서 효율적이기 때문이다.

여기서 `download_localhost: true`까지 설정하면, admin 서버가 다운로드 + 배포를 다 하니까 **노드는 외부 접근이 전혀 필요 없다.** 공식 문서도 이를 명시한다.

> Set `download_localhost: True` to make localhost the download delegate. This can be useful if cluster nodes cannot access external addresses.

다만 이 경우, admin에 컨테이너 런타임이 설치되고 실행 중이어야 하고, 현재 사용자가 컨테이너 런타임을 사용할 수 있어야 한다(docker의 경우 docker group, 일반적으로는 passwordless sudo).

결론적으로, **admin에 컨테이너 런타임이 있다면 `download_localhost: true`가 가장 깔끔하다.** 한 홉이 줄어든다.

<br>

# Pull 정책

이미 로컬에 있는 이미지를 다시 받을지 말지를 결정하는 변수다. 다운로드 전략과 독립적으로 동작한다.

| 변수 | 대상 | 동작 | 기본값 |
|------|------|------|--------|
| `k8s_image_pull_policy` | K8s 앱 (Pod) | `IfNotPresent`이면 로컬에 있으면 안 받음 | `IfNotPresent` |
| `download_always_pull` | 시스템 컨테이너 (kubelet, etcd 등) | `false`이면 repo+tag/digest가 다를 때만 pull | `false` |

- **`k8s_image_pull_policy`**: Kubernetes Pod에 적용되는 표준 imagePullPolicy다. `IfNotPresent`가 기본이므로, 로컬에 이미지가 이미 있으면 다시 받지 않는다.
- **`download_always_pull`**: Kubespray가 프로비저닝 과정에서 시스템 컨테이너 이미지를 다룰 때 적용된다. `false`이면 이미지의 repo+tag 또는 digest가 변경된 경우에만 다시 pull한다.

오프라인 환경에서는 둘 다 기본값 그대로 두면 된다. 불필요한 재다운로드를 피하고, 내부 레지스트리/서버의 부하를 줄일 수 있다.

<br>

# 캐싱 전략

## 기본 동작

`download_run_once: true`일 때, 캐싱은 자동으로 활성화된다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `download_cache_dir` | `/tmp/kubespray_cache` | admin 노드의 로컬 캐시 경로 |
| `download_force_cache` | `false` | `download_run_once: false`일 때도 기존 캐시를 강제로 사용 |
| `download_keep_remote_cache` | `false` | 원격 노드에 전송한 캐시 이미지를 삭제하지 않고 유지 |

동작 흐름은 이렇다.

1. **첫 번째 실행**: delegate가 다운로드 → admin의 로컬 캐시(`download_cache_dir`)에 저장
2. **이후 실행**: 캐시에서 바로 노드에 배포 → 다시 다운로드하지 않음 → 대역폭 절약 + 프로비저닝 시간 단축

## download_force_cache

`download_run_once: false`면 **기본적으로 캐시를 사용하지 않는다.** 각 노드가 직접 다운로드하니까 캐싱할 필요가 없기 때문이다.

하지만 이미 캐시가 다 준비되어 있고 그걸 쓰고 싶다면, `download_force_cache: true`로 강제할 수 있다. 이 경우 `download_run_once: false`여도 admin의 로컬 캐시에서 각 노드로 파일/이미지를 배포한다.

어떤 경우에 유용한가:

- 이전에 `download_run_once: true`로 한 번 돌려서 캐시가 쌓였다
- 이번에는 `download_run_once: false`로 바꿔서 돌리고 싶은데, 다시 다운로드하지 않고 **기존 캐시를 그대로 쓰고 싶다**
- → `download_force_cache: true` 설정

공식 문서도 이런 경우를 명시한다.

> If you have a full cache with container images and files and you don't need to download anything, but want to use a cache.

## 디스크 영향

캐시 사용 시 디스크 사용량을 정리하면:

|  | 기본 (캐시 삭제) | `download_keep_remote_cache: true` |
|---|---|---|
| **admin 노드** | ~800MB (로컬 캐시) | ~800MB |
| **원격 노드** | ~150MB (가장 큰 이미지 1개 크기) | ~550MB (모든 이미지 캐시 유지) |

admin 노드의 `download_cache_dir`에는 모든 파일 + 이미지가 캐시 파일 형태(바이너리 + 컨테이너 이미지 tar 등)로 저장되어 ~800MB가 필요하다.

원격 노드에서 ~150MB가 필요한 이유는, admin에서 원격 노드로 이미지를 전송할 때 **한 번에 하나씩 보내고 로드한 뒤 캐시 파일을 삭제**하기 때문이다. 동시에 디스크에 존재하는 캐시 파일의 최대 크기 = 가장 큰 이미지 1개의 크기인 것이다. `download_keep_remote_cache: true`로 하면 삭제를 안 하니까, 모든 이미지 캐시가 남아서 ~150MB → ~550MB로 늘어난다.

오프라인 환경에서 반복 프로비저닝할 때 `download_keep_remote_cache: true`는 시간을 줄여주지만, 노드 스토리지 사용량이 늘어나는 트레이드오프가 있다.

<br>

# 아티팩트 변수 네이밍 컨벤션

지금까지 다운로드의 **전략/정책/캐싱**을 살펴봤다면, 이번 섹션은 **"뭘 다운로드하나"의 구체적 정의 방식**이다. Kubespray는 모든 다운로드 대상을 `foo_*` 패턴의 변수로 정의하는데, 바이너리와 컨테이너 이미지가 다른 변수 세트를 사용한다.

## 바이너리 파일

바이너리 파일은 3개 변수로 정의된다.

| 변수 | 역할 | 예시 |
|------|------|------|
| `foo_version` | 버전 | `v1.31.0` |
| `foo_download_url` | 다운로드 URL | `https://dl.k8s.io/v1.31.0/kubeadm` |
| `foo_checksum` | 파일 무결성 검증용 체크섬 | SHA256 해시값 |

## 컨테이너 이미지

컨테이너 이미지는 2~3개 변수로 정의된다.

| 변수 | 역할 | 예시 |
|------|------|------|
| `foo_image_repo` | 이미지 레포 경로 | `andyshinn/dnsmasq` |
| `foo_image_tag` | 태그 | `2.72` |
| `foo_digest_checksum` (optional) | SHA256 다이제스트 | `7c883354f6ea...` |

이미지를 tag로만 지정할 수도 있고, **tag + SHA256 digest를 함께** 지정할 수도 있다.

- tag만: `andyshinn/dnsmasq:2.72` → 간편하지만, 같은 tag에 다른 이미지가 push될 수 있음
- tag + digest: `andyshinn/dnsmasq@sha256:7c883...` → **정확히 이 이미지**라는 것을 보장 (불변)

digest를 쓰면 tag와 digest가 서로 일치해야 한다.

```yaml
dnsmasq_digest_checksum: 7c883354f6ea9876d176fe1d30132515478b2859d6fc0cbf9223ffdc09168193
dnsmasq_image_repo: andyshinn/dnsmasq
dnsmasq_image_tag: '2.72'
```

## offline-environment.md와의 연결

공식 문서의 마지막 문장이 이 변수 체계와 오프라인 설정을 연결해준다.

> The full list of available vars may be found in the download's ansible role defaults. Those also allow to specify custom urls and local repositories for binaries and container images as well.

[이전 글(8.2.1)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 `files_repo`, `registry_host` 등을 바꾼 것이, 사실 이 `foo_download_url`, `foo_image_repo` 변수들의 **기본값을 오버라이드**하는 것이었다. 즉:

- `roles/download/defaults/main/`에 이 `foo_*` 변수들의 기본값이 정의되어 있고
- 오프라인에서는 이걸 내부 서버를 가리키도록 오버라이드하는 구조

{% raw %}
```
roles/download/defaults/main/
  └── foo_download_url: "https://dl.k8s.io/..."  ← 기본값 (온라인)
                            │
                            │ group_vars/all/offline.yml에서 오버라이드
                            ▼
      foo_download_url: "{{ files_repo }}/..."    ← 오프라인 값 (내부 서버)
```
{% endraw %}

<br>

# Public Download Mirror

여기서부터는 [`mirror.md`](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/mirror.md)의 내용이다.

## 공개 미러의 목적

Kubespray 기본 다운로드 URL들(`dl.k8s.io`, `github.com`, `registry.k8s.io` 등)은 대부분 미국/유럽에 호스팅되어 있다. 물리적으로 먼 지역이나 네트워크 제약이 있는 지역에서는 다운로드가 매우 느릴 수 있다.

Public Download Mirror는 **지리적으로 가까운 미러 서버**를 제공해서 다운로드 속도를 개선하는 것이 목적이다. 완전 오프라인(폐쇄망)이 아니라, 기본 URL로는 실용적으로 사용하기 힘든 **느린 네트워크 환경**에서 유용하다.

## 미러 설정

이미지/파일 다운로드를 공개 미러 사이트로 설정하려면 inventory에 다음과 같이 정의한다.

```yaml
# <your_inventory>/group_vars/k8s_cluster.yml
gcr_image_repo: "gcr.m.daocloud.io"
kube_image_repo: "k8s.m.daocloud.io"
docker_image_repo: "docker.m.daocloud.io"
quay_image_repo: "quay.m.daocloud.io"
github_image_repo: "ghcr.m.daocloud.io"

files_repo: "https://files.m.daocloud.io"
```

[이전 글(8.2.1)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 오프라인 환경 변수를 내부 서버로 오버라이드한 것과 **동일한 변수 체계**를 사용한다. 차이점은 값이 내부 서버 URL이 아니라 공개 미러 URL이라는 것뿐이다.

> **주의**: 미러 사이트의 provider를 신뢰할 때에만 설정할 것. Kubespray 측에서는 미러 사이트의 신뢰성이나 안전성을 담보하지 않는다.

현재 커뮤니티에서 운영하는 미러 사이트로는 DaoCloud(중국)이 있다.

- [이미지 미러](https://github.com/DaoCloud/public-image-mirror)
- [파일 미러](https://github.com/DaoCloud/public-binary-files-mirror)

## 오프라인 환경에서의 활용

공개 미러와 내부 미러는 **서로 다른 단계**에서 각각 사용된다.

- **공개 미러**: 아티팩트를 인터넷에서 다운로드하는 **1단계**에서, 원본 서버(`dl.k8s.io` 등) 대신 지리적으로 가까운 공개 미러에서 받아서 속도를 올리는 것이다. DMZ/Bastion 서버에서 다운로드할 때 소스 URL을 미러로 바꾼다.
- **내부 미러**: 폐쇄망 안에서 노드들이 사용하는 **2단계** 서빙 인프라다.

둘을 조합하면:

```
[인터넷 쪽 - 1단계: 아티팩트 준비]
공개 미러(DaoCloud 등) → Bastion/DMZ에서 빠르게 다운로드
                                  ↓ (물리 매체 or 승인된 경로)
[폐쇄망 쪽 - 2단계: 서빙 인프라]
내부 미러(Nginx, Registry 등) → 클러스터 노드들에 서빙
```

원본 서버까지의 거리가 먼 폐쇄망 환경이라면, 공개 미러를 활용해 아티팩트 준비 단계의 시간을 크게 줄일 수 있다.

<br>

# 참고 자료

- [Kubespray - Downloads](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/advanced/downloads.md)
- [Kubespray - Public Download Mirror](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/mirror.md)
- [DaoCloud Public Image Mirror](https://github.com/DaoCloud/public-image-mirror)
- [DaoCloud Public Binary Files Mirror](https://github.com/DaoCloud/public-binary-files-mirror)

<br>
