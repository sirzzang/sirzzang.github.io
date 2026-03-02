---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.0. 실습 구성도"
excerpt: "kubeadm 클러스터 구성 실습에서 각 단계별 조감도를 그려보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이 글은 kubeadm 클러스터 구성 실습의 **조감도**다.

- **4단계**: containerd 설치 → kubelet/kubeadm 설치 → `kubeadm init`(또는 `join`) → CNI 설치
- 각 단계에서 **어떤 파일이 어디에 생성되는지**, 그 시점의 **시스템 상태**는 어떤지를 정리
- 파일의 상세 내용은 각 글에서 다루고, 여기서는 **경로와 역할**에 집중

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %})에서 kubeadm의 개념과 설계 철학을 살펴봤다. 이번 글부터 실제로 클러스터를 구성하는데, 그 전에 전체 흐름에서 **어떤 파일이 어디에 생기는지** ~~길을 잃지 않기 위해~~ 먼저 정리해 둔다.

실습은 크게 네 단계를 거친다.

| 단계 | 작업 | 컨트롤 플레인 | 워커 노드 |
| --- | --- | --- | --- |
| 1 | [containerd 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#cri-설치-containerd) | CRI 런타임 준비 | (동일) |
| 2 | [kubeadm/kubelet/kubectl 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubeadm-kubelet-kubectl-설치) | kubelet systemd 서비스 등록 (crashloop) | (동일) |
| 3 | [kubeadm init]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}) / [kubeadm join]({% post_url 2026-01-18-Kubernetes-Kubeadm-02-2 %}) | 인증서(22개), kubeconfig(5개), Static Pod(4개), kubelet 설정 | ca.crt만, kubelet.conf만, Static Pod 없음 |
| 4 | [CNI(Flannel) 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}) | Pod 네트워크 활성화, 노드 `Ready` | (동일, DaemonSet으로 자동 배포) |

각 단계에서 생성되는 파일과 디렉토리를 **컨트롤 플레인**과 **워커 노드**로 나누어 정리한다. 각 파일의 상세 내용은 해당 글에서 다루므로, 여기서는 **경로와 역할**만 짚는다.

<br>

# 컨트롤 플레인 노드

## Stage 1: containerd 설치

> 상세: [1.3. CRI(containerd) 및 kubeadm 구성 요소 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#cri-설치-containerd)

| 경로 | 역할 |
| --- | --- |
| `/etc/containerd/config.toml` | containerd 설정 (SystemdCgroup 활성화) |
| `/run/containerd/containerd.sock` | CRI 유닉스 도메인 소켓. kubelet이 이 소켓을 통해 containerd와 통신 |

이 시점 상태:

| 구성 요소 | 실행 방식 | 상태 |
| --- | --- | --- |
| containerd | systemd 서비스 | 실행 중 |
| kubelet | - | 미설치 |
| etcd | - | 미설치 |
| kube-apiserver | - | 미설치 |
| kube-controller-manager | - | 미설치 |
| kube-scheduler | - | 미설치 |
| CoreDNS | - | 미설치 |
| kube-proxy | - | 미설치 |
| Flannel | - | 미설치 |

<br>

## Stage 2: kubeadm/kubelet/kubectl 설치

> 상세: [1.3. CRI(containerd) 및 kubeadm 구성 요소 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubeadm-kubelet-kubectl-설치)

| 경로 | 역할 |
| --- | --- |
| `/usr/lib/systemd/system/kubelet.service` | kubelet systemd 서비스 유닛 |
| `/usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf` | kubeadm용 drop-in (환경변수, 플래그 오버라이드) |
| `/etc/sysconfig/kubelet` | 사용자 정의 추가 인자 (`KUBELET_EXTRA_ARGS`) |
| `/opt/cni/bin/*` | 기본 CNI 바이너리 (`kubernetes-cni` 패키지) |

이 시점에서 kubelet은 **crashloop** 상태다. drop-in이 참조하는 아래 파일들이 아직 존재하지 않기 때문이다.

| 경로 | 설명 | 생성 시점 |
| --- | --- | --- |
| `/etc/kubernetes/bootstrap-kubelet.conf` | 부트스트랩 kubeconfig | `kubeadm init/join` |
| `/etc/kubernetes/kubelet.conf` | kubelet kubeconfig | `kubeadm init/join` |
| `/var/lib/kubelet/config.yaml` | kubelet 런타임 설정 | `kubeadm init/join` |
| `/var/lib/kubelet/kubeadm-flags.env` | kubeadm이 생성하는 kubelet 플래그 | `kubeadm init/join` |

> 각 파일의 역할 상세는 [kubelet 서비스 파일]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubelet-서비스-파일)을 참고한다.

이 시점 상태:

| 구성 요소 | 실행 방식 | 상태 |
| --- | --- | --- |
| containerd | systemd 서비스 | 실행 중 |
| kubelet | systemd 서비스 | crashloop (설정 파일 미존재) |
| etcd | - | 미설치 |
| kube-apiserver | - | 미설치 |
| kube-controller-manager | - | 미설치 |
| kube-scheduler | - | 미설치 |
| CoreDNS | - | 미설치 |
| kube-proxy | - | 미설치 |
| Flannel | - | 미설치 |

## Stage 3: kubeadm init

> 상세: [1.4. kubeadm init 실행]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %})

`kubeadm init`이 실행되면 Stage 2에서 비어 있던 디렉토리들이 채워진다.

**인증서** (`/etc/kubernetes/pki/`)

| 경로 | 역할 |
| --- | --- |
| `ca.crt`, `ca.key` | 클러스터 CA |
| `apiserver.crt`, `apiserver.key` | API Server 서버 인증서 |
| `apiserver-kubelet-client.crt`, `apiserver-kubelet-client.key` | API Server → kubelet 클라이언트 인증서 |
| `front-proxy-ca.crt`, `front-proxy-ca.key` | Front Proxy CA |
| `front-proxy-client.crt`, `front-proxy-client.key` | Front Proxy 클라이언트 인증서 |
| `sa.key`, `sa.pub` | Service Account 서명 키 쌍 |
| `etcd/ca.crt`, `etcd/ca.key` | etcd CA |
| `etcd/server.crt`, `etcd/server.key` | etcd 서버 인증서 |
| `etcd/peer.crt`, `etcd/peer.key` | etcd 피어 인증서 |
| `etcd/healthcheck-client.crt`, `etcd/healthcheck-client.key` | etcd 헬스체크 클라이언트 인증서 |
| `apiserver-etcd-client.crt`, `apiserver-etcd-client.key` | API Server → etcd 클라이언트 인증서 |

> 상세: [1.6. 인증서 확인]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %}#인증서-확인)

<br>

**Static Pod 매니페스트** (`/etc/kubernetes/manifests/`)

| 파일 | 컴포넌트 |
| --- | --- |
| `etcd.yaml` | etcd |
| `kube-apiserver.yaml` | API Server |
| `kube-controller-manager.yaml` | Controller Manager |
| `kube-scheduler.yaml` | Scheduler |

> 상세: [1.7. Static Pod 확인]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-7 %}#static-pod-확인)

<br>

**kubeconfig 파일** (`/etc/kubernetes/`)

| 파일 | 사용자 |
| --- | --- |
| `admin.conf` | 클러스터 관리자 |
| `super-admin.conf` | 슈퍼 관리자 (RBAC 우회) |
| `controller-manager.conf` | kube-controller-manager |
| `scheduler.conf` | kube-scheduler |
| `kubelet.conf` | kubelet (외부 인증서 파일 참조) |

> 상세: [1.6. kubeconfig 확인]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %}#kubeconfig-확인)

<br>

**kubelet 설정** (`/var/lib/kubelet/`)

| 경로 | 역할 |
| --- | --- |
| `config.yaml` | kubelet 런타임 설정 (`staticPodPath`, `cgroupDriver`, `clusterDNS` 등) |
| `kubeadm-flags.env` | kubeadm이 생성한 kubelet 플래그 (`--container-runtime-endpoint`, `--node-ip` 등) |
| `pki/kubelet-client-current.pem` | kubelet → API Server 클라이언트 인증서 (심볼릭 링크) |
| `pki/kubelet.crt`, `pki/kubelet.key` | kubelet 서버 인증서 |

> 상세: [1.6. kubelet 상태 및 설정 확인]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %}#kubelet-상태-및-설정-확인)

<br>s

**etcd 데이터**

| 경로 | 역할 |
| --- | --- |
| `/var/lib/etcd/` | etcd 데이터 디렉토리 |

이 시점 상태:

| 구성 요소 | 실행 방식 | 상태 |
| --- | --- | --- |
| containerd | systemd 서비스 | 실행 중 |
| kubelet | systemd 서비스 | 실행 중 |
| etcd | Static Pod | 실행 중 |
| kube-apiserver | Static Pod | 실행 중 |
| kube-controller-manager | Static Pod | 실행 중 |
| kube-scheduler | Static Pod | 실행 중 |
| CoreDNS | Deployment (2 replicas) | Running (Pod 네트워크 미활성) |
| kube-proxy | DaemonSet | Running |
| Flannel | - | 미설치 |

노드 상태: **NotReady** (CNI 미설치)

<br>

## Stage 4: CNI(Flannel) 설치

> 상세: [1.5. Flannel CNI 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %})

| 경로 | 역할 |
| --- | --- |
| `/etc/cni/net.d/*` | CNI 설정 파일 (Flannel이 생성) |

이 시점 상태:

| 구성 요소 | 실행 방식 | 상태 |
| --- | --- | --- |
| containerd | systemd 서비스 | 실행 중 |
| kubelet | systemd 서비스 | 실행 중 |
| etcd | Static Pod | 실행 중 |
| kube-apiserver | Static Pod | 실행 중 |
| kube-controller-manager | Static Pod | 실행 중 |
| kube-scheduler | Static Pod | 실행 중 |
| CoreDNS | Deployment (2 replicas) | Running |
| kube-proxy | DaemonSet | Running |
| Flannel | DaemonSet | Running |

노드 상태: **Ready**

<br>

# 워커 노드

## Stage 1~2: containerd, kubelet/kubeadm 설치

컨트롤 플레인과 **동일**하다. 같은 패키지를 설치하고 같은 파일이 생성된다.

<br>

## Stage 3: kubeadm join

> 상세: [2.2. 워커 노드 Join 실행]({% post_url 2026-01-18-Kubernetes-Kubeadm-02-2 %})

컨트롤 플레인의 `kubeadm init`과 달리, 워커 노드의 `kubeadm join`은 **최소한의 파일만** 생성한다.

**`/etc/kubernetes/`**

| 경로 | 역할 | 컨트롤 플레인과 차이 |
| --- | --- | --- |
| `kubelet.conf` | kubelet kubeconfig | 동일 |
| `pki/ca.crt` | 클러스터 CA 인증서 | 컨트롤 플레인: 22개 파일 → 워커: **ca.crt만** |
| `manifests/` | (비어 있음) | 컨트롤 플레인: Static Pod 4개 → 워커: **없음** |

`admin.conf`, `controller-manager.conf`, `scheduler.conf` 등은 워커 노드에 **생성되지 않는다**.

<br>

**`/var/lib/kubelet/`**

| 경로 | 역할 | 컨트롤 플레인과 차이 |
| --- | --- | --- |
| `config.yaml` | kubelet 런타임 설정 | 동일 |
| `kubeadm-flags.env` | kubelet 플래그 | 동일 (node-ip 값만 다름) |
| `pki/kubelet-client-current.pem` | kubelet 클라이언트 인증서 | 동일 |

<br>

## Stage 4: CNI

DaemonSet으로 자동 배포되므로 컨트롤 플레인과 **동일한 경로**에 CNI 설정이 생성된다.

<br>

# 전체 디렉토리 트리

컨트롤 플레인 노드의 최종 상태를 한 트리로 보면 다음과 같다. 어느 단계에서 생성되었는지를 함께 표기한다.

```bash
/etc/
├── containerd/
│   └── config.toml                          # [Stage 1] containerd 설정
├── cni/
│   └── net.d/                               # [Stage 4] CNI 설정 (Flannel)
├── kubernetes/
│   ├── admin.conf                           # [Stage 3] 관리자 kubeconfig
│   ├── controller-manager.conf              # [Stage 3] controller-manager kubeconfig
│   ├── kubelet.conf                         # [Stage 3] kubelet kubeconfig
│   ├── scheduler.conf                       # [Stage 3] scheduler kubeconfig
│   ├── super-admin.conf                     # [Stage 3] 슈퍼 관리자 kubeconfig
│   ├── manifests/
│   │   ├── etcd.yaml                        # [Stage 3] etcd Static Pod
│   │   ├── kube-apiserver.yaml              # [Stage 3] API Server Static Pod
│   │   ├── kube-controller-manager.yaml     # [Stage 3] Controller Manager Static Pod
│   │   └── kube-scheduler.yaml              # [Stage 3] Scheduler Static Pod
│   └── pki/
│       ├── ca.crt                           # [Stage 3] 클러스터 CA
│       ├── ca.key
│       ├── apiserver.crt                    # [Stage 3] API Server 인증서
│       ├── apiserver.key
│       ├── apiserver-kubelet-client.crt     # [Stage 3] API Server → kubelet 인증서
│       ├── apiserver-kubelet-client.key
│       ├── apiserver-etcd-client.crt        # [Stage 3] API Server → etcd 인증서
│       ├── apiserver-etcd-client.key
│       ├── front-proxy-ca.crt               # [Stage 3] Front Proxy CA
│       ├── front-proxy-ca.key
│       ├── front-proxy-client.crt           # [Stage 3] Front Proxy 클라이언트
│       ├── front-proxy-client.key
│       ├── sa.key                           # [Stage 3] Service Account 키
│       ├── sa.pub
│       └── etcd/
│           ├── ca.crt                       # [Stage 3] etcd CA
│           ├── ca.key
│           ├── server.crt                   # [Stage 3] etcd 서버
│           ├── server.key
│           ├── peer.crt                     # [Stage 3] etcd 피어
│           ├── peer.key
│           ├── healthcheck-client.crt       # [Stage 3] etcd 헬스체크
│           └── healthcheck-client.key
└── sysconfig/
    └── kubelet                              # [Stage 2] 사용자 추가 인자

/opt/cni/bin/                                # [Stage 2] 기본 CNI 바이너리

/run/containerd/
└── containerd.sock                          # [Stage 1] CRI 소켓

/usr/lib/systemd/system/
├── kubelet.service                          # [Stage 2] kubelet 서비스
└── kubelet.service.d/
    └── 10-kubeadm.conf                      # [Stage 2] kubeadm drop-in

/var/lib/
├── etcd/                                    # [Stage 3] etcd 데이터
└── kubelet/
    ├── config.yaml                          # [Stage 3] kubelet 런타임 설정
    ├── kubeadm-flags.env                    # [Stage 3] kubelet 플래그
    └── pki/
        ├── kubelet-client-current.pem       # [Stage 3] kubelet 클라이언트 인증서
        ├── kubelet.crt                      # [Stage 3] kubelet 서버 인증서
        └── kubelet.key
```

<br>

# 단계별 상태 요약

| 단계 | systemd 서비스 | Static Pod | Deployment / DaemonSet | 노드 상태 | 해당 글 |
| --- | --- | --- | --- | --- | --- |
| Stage 1 | containerd | - | - | - | [1.3]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#cri-설치-containerd) |
| Stage 2 | containerd, kubelet (crashloop) | - | - | - | [1.3]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubeadm-kubelet-kubectl-설치) |
| Stage 3 (init) | containerd, kubelet | etcd, apiserver, controller-manager, scheduler | CoreDNS (Deployment), kube-proxy (DaemonSet) | NotReady | [1.4]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}) |
| Stage 4 (CNI) | containerd, kubelet | etcd, apiserver, controller-manager, scheduler | CoreDNS, kube-proxy, Flannel (DaemonSet) | **Ready** | [1.5]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}) |

<br>

# 마무리

이 글에서 정리한 파일 맵은 이후 실습을 따라가면서 **"지금 어느 단계에 있고, 무엇이 생겨야 하는지"** 참조하는 용도로 활용하면 된다. 다음 글부터 실제로 각 단계를 진행한다.

<br>