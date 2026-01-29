---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 0. kubeadm이란"
excerpt: "kubeadm의 개념과 설계 철학, 주요 명령어를 살펴보고, Kubernetes The Hard Way와 비교해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **kubeadm의 개념과 설계 철학 이해**다.

- **kubeadm**: 쿠버네티스 클러스터 부트스트래핑을 위한 공식 도구
- **설계 철학**: 부트스트래핑만 담당, 머신 프로비저닝이나 애드온 설치는 하지 않음
- **핵심 명령어**: `kubeadm init` (컨트롤 플레인 구성), `kubeadm join` (노드 조인)
- **활용**: minikube, kind, kubespray 등 다양한 도구들이 내부적으로 kubeadm을 사용

<br>

# 들어가며

[Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})는 내 손으로 직접 쿠버네티스 클러스터를 구성하는 방법을 안내했다. 인증서 생성, etcd 설치, 컨트롤 플레인 구성, 워커 노드 조인까지 모든 과정을 수동으로 진행했다. 클러스터의 각 구성 요소를 이해하는 데는 좋지만, 실제 운영 환경에서 매번 이렇게 할 수는 없다.

이번 글부터는 **kubeadm**을 사용해 클러스터를 구성해 본다. kubeadm은 쿠버네티스 클러스터를 구성하기 위해 필요한 작업들을 자동화해주는 도구이다. Kubernetes The Hard Way에서 수동으로 수행한 작업들을 자동으로 수행한다고 생각하면 된다.

<br>

# kubeadm이란

## 공식 문서 살펴보기

[kubeadm 공식 문서](https://kubernetes.io/docs/reference/setup-tools/kubeadm/)를 보면, kubeadm을 다음과 같이 소개한다.

> Kubeadm is a tool built to provide `kubeadm init` and `kubeadm join` as best-practice "fast paths" for creating Kubernetes clusters.

쿠버네티스 클러스터 생성을 위한 **best-practice fast path**를 제공하는 도구라고 한다. `kubeadm init`과 `kubeadm join`이라는 두 명령어로 클러스터를 빠르게 구성할 수 있다는 의미다.

kubeadm은 Kubernetes SIG(Special Interest Group) 중 [Cluster Lifecycle](https://github.com/kubernetes/community/tree/master/sig-cluster-lifecycle) 그룹에서 관리하는 공식 프로젝트다. 즉, **쿠버네티스에서 공식적으로 제공하는 클러스터 부트스트래핑 도구**다.

## 설계 철학

kubeadm의 설계 철학은 명확하다. 공식 문서에서 이렇게 설명한다.

> kubeadm performs the actions necessary to get a minimum viable cluster up and running.

**최소한의 실행 가능한 클러스터(minimum viable cluster)**를 구성하는 데 필요한 작업만 수행한다. 설계 상, **부트스트래핑만** 담당한다.

### kubeadm이 하지 않는 것

kubeadm이 **하지 않는** 것들이 있다.

- **머신 프로비저닝**: VM이나 물리 서버를 생성하지 않음
- **컨테이너 런타임 설치**: containerd, CRI-O 등 CRI 호환 런타임을 설치하지 않음
- **kubelet 설치**: kubelet 바이너리 설치 및 systemd 서비스 등록을 하지 않음
- **CNI 플러그인 설치**: Pod 네트워크를 위한 CNI 플러그인(Calico, Flannel 등)을 설치하지 않음
- **애드온 설치**: Kubernetes Dashboard, 모니터링 솔루션, 클라우드 특화 애드온 등을 설치하지 않음

즉, kubeadm을 실행하기 전에 **containerd(또는 다른 CRI 런타임)와 kubelet이 이미 설치되어 있어야** 한다.

> Instead, we expect higher-level and more tailored tooling to be built on top of kubeadm.

공식 문서의 설명을 보면 kubeadm 위에 더 높은 수준의, 더 맞춤화된 도구들이 만들어지길 기대한다고 한다. kubeadm은 **기초(foundation)** 역할만 하고, 그 위에 다양한 도구들이 쌓이는 구조다.

실제로 minikube, kind, kubespray, Cluster API 등 다양한 쿠버네티스 배포 도구들이 내부적으로 kubeadm을 사용한다.

### kubeadm이 하는 것

kubeadm이 **하는** 것들은 다음과 같다.

- **인증서 생성**: CA 및 각 컴포넌트용 TLS 인증서 자동 생성
- **kubeconfig 파일 생성**: admin, kubelet, controller-manager, scheduler용 kubeconfig 자동 생성
- **etcd 구성**: Static Pod로 etcd 자동 배포
- **컨트롤 플레인 구성**: kube-apiserver, kube-controller-manager, kube-scheduler를 Static Pod로 배포
- **kubelet 설정**: kubelet 설정 파일 생성 및 시작
- **CoreDNS, kube-proxy 설치**: 기본 애드온으로 자동 설치

Kubernetes The Hard Way에서 OpenSSL로 인증서를 생성하고, systemd 서비스 파일을 작성하고, etcd와 컨트롤 플레인 컴포넌트를 직접 설치했던 과정들을 kubeadm이 자동화해준다.

<br>

# 주요 명령어

kubeadm이 제공하는 주요 명령어들을 살펴보자. 명령어들은 크게 세 가지 계층으로 분류할 수 있다.

![kubeadm-00-structure]({{site.url}}/assets/images/kubeadm-00-structure.png){: .align-center width="450"}

## 명령어 관계도

명령어들의 관계를 정리하면 다음과 같다.

```
[ Cluster Lifecycle ]
       │
       ├── init     ────┐
       │                │
       ├── join     ────┼──── [ Security ]
       │                │          ├── certs
       ├── upgrade  ────┘          ├── kubeconfig
       │                           └── token
       └── reset

[ Utility ]
       ├── config
       ├── version
       └── alpha
```

- `kubeadm init`으로 컨트롤 플레인을 구성하면, 내부적으로 인증서(`certs`)와 kubeconfig를 생성하고, 워커 노드 조인을 위한 토큰(`token`)을 발급한다.
- `kubeadm join`으로 워커 노드를 클러스터에 조인시킨다. 이때 토큰을 사용한다.
- 클러스터 버전을 올릴 때는 `kubeadm upgrade`를 사용한다.
- 노드를 클러스터에서 제거하거나 초기화할 때는 `kubeadm reset`을 사용한다.

<br>

## 생명주기 명령어

클러스터의 생성부터 삭제까지 전체 생명주기를 관리하는 핵심 명령어들이다.

```
init (시작) ──→ join (확장) ──→ upgrade (갱신)
                                    │
                                    ↓
                              reset (초기화)
```

| 명령어 | 설명 |
| --- | --- |
| `kubeadm init` | 컨트롤 플레인 노드 부트스트래핑 |
| `kubeadm join` | 워커 노드 또는 추가 컨트롤 플레인 노드를 클러스터에 조인 |
| `kubeadm upgrade` | 쿠버네티스 클러스터를 새 버전으로 업그레이드 |
| `kubeadm reset` | `kubeadm init` 또는 `kubeadm join`으로 만들어진 변경 사항을 되돌림 |


<br>

## 보안 기반 명령어

생명주기 명령어들이 내부적으로 사용하는 인증/인가 관련 명령어들이다. 직접 사용할 일은 적지만, 인증서 갱신이나 토큰 관리 시 필요하다.

| 명령어 | 설명 |
| --- | --- |
| `kubeadm certs` | 쿠버네티스 인증서 관리 (갱신, 확인 등) |
| `kubeadm kubeconfig` | kubeconfig 파일 관리 |
| `kubeadm token` | `kubeadm join` 시 사용할 토큰 관리 |

<br>

## 유틸리티 명령어

| 명령어 | 설명 |
| --- | --- |
| `kubeadm config` | 클러스터 설정 관리 (기본 설정 출력, 필요한 이미지 목록 확인 등) |
| `kubeadm version` | kubeadm 버전 확인 |
| `kubeadm alpha` | 다음 버전에 포함될 실험적 기능들 |


<br>

# Kubernetes The Hard Way vs. kubeadm

kubeadm은 Kubernetes The Hard Way에서 수동으로 수행하는 단계들을 자동화한다. 각 단계가 수동으로 클러스터를 구성하는 단계에 어떻게 매칭되는지 보여준다.

| kubeadm 단계 | Kubernetes The Hard Way |
| --- | --- |
| **(사전 준비)** | [0. Overview]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %}) |
| **(머신 프로비저닝)** | [1. Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}) |
| **(바이너리 준비)** | [2. Set Up The Jumpbox]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %}) |
| **(컴퓨트 리소스)** | [3. Provisioning Compute Resources]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %}) |
| **kubeadm init** | |
| └ preflight | (자동화된 사전 체크) |
| └ certs | [4.1. TLS/mTLS/PKI 개념]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %})<br>[4.2. ca.conf 구조 분석]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-2 %})<br>[4.3. CA 및 TLS 인증서 생성]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) |
| └ kubeconfig | [5.1. kubeconfig 개념]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-1 %})<br>[5.2. kubeconfig 파일 생성]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}) |
| └ etcd | [7. Bootstrapping etcd]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-07 %}) |
| └ control-plane | [8.1. Control Plane 설정 분석]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-1 %})<br>[8.2. Control Plane 배포]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}) |
| └ kubelet-start | (The Hard Way에서는 Control Plane에 kubelet 미설치) |
| └ wait-control-plane | (자동 대기) |
| └ upload-config | (ConfigMap 자동 업로드) |
| └ upload-certs | (인증서 자동 업로드) |
| └ mark-control-plane | (자동 마킹) |
| └ bootstrap-token | (토큰 자동 생성) |
| └ kubelet-finalize | (kubelet 최종 설정) |
| └ addon (coredns, kube-proxy) | (애드온 자동 설치) |
| **kubeadm join** | |
| └ Worker Node 구성 | [9.1. CNI 및 Worker Node 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %})<br>[9.2. Worker Node 프로비저닝]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) |
| **(추가 설정)** | |
| └ kubectl 원격 접근 | [10. Configuring kubectl]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-10 %}) |
| └ Pod Network Routes | [11. Pod Network Routes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-11 %}) |
| **(검증)** | [12. Smoke Test]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}) |

<br>

## 주요 차이점

| 구분 | Kubernetes The Hard Way | kubeadm |
| --- | --- | --- |
| **인증서 생성** | OpenSSL로 수동 생성 | 자동 생성 (`kubeadm certs`) |
| **etcd** | systemd 서비스로 직접 구성 | Static Pod로 자동 구성 |
| **Control Plane** | systemd 서비스로 직접 구성 | Static Pod로 자동 구성 |
| **kubeconfig** | kubectl로 수동 생성 | 자동 생성 (`kubeadm kubeconfig`) |
| **CNI** | bridge 플러그인 수동 설정 | 별도 설치 필요 (Calico, Flannel 등) |
| **etcd 통신** | HTTP (평문) | HTTPS (TLS 암호화) |
| **토큰 기반 join** | 수동 인증서 배포 | bootstrap token 사용 |
| **Control Plane kubelet** | 미설치 (컴포넌트를 systemd로 직접 실행) | 필수 (Static Pod 관리) |

> **참고**: Kubernetes The Hard Way에서는 학습 목적으로 etcd를 HTTP로 구성했지만, kubeadm은 보안을 위해 HTTPS를 기본으로 사용한다.

### Control Plane에 kubelet이 필요한 이유

Kubernetes The Hard Way에서는 Control Plane 컴포넌트들을 systemd 서비스로 직접 실행했기 때문에 kubelet이 필요하지 않았다. 하지만 kubeadm은 Control Plane 컴포넌트들을 **Static Pod**로 배포하므로, 이를 관리할 kubelet이 반드시 필요하다.

Control Plane에 kubelet이 필요한 이유를 정리하면:

1. **Static Pod 관리**: kubelet은 `/etc/kubernetes/manifests` 디렉토리를 모니터링하며, 여기에 있는 매니페스트(kube-apiserver, kube-controller-manager, kube-scheduler, etcd)를 자동으로 Pod로 실행하고 관리한다.

2. **노드 상태 보고**: Control Plane 노드도 클러스터의 일부이므로, 해당 노드의 상태(CPU, 메모리, 디스크 등)를 API Server에 보고해야 한다. 이 역할을 kubelet이 수행한다.

3. **워크로드 스케줄링**: Control Plane 노드의 taint를 제거하면 일반 워크로드 Pod도 스케줄링될 수 있다. 이때 해당 Pod들을 실행하는 것도 kubelet이다.

<br>

# 마무리

kubeadm은 Kubernetes The Hard Way에서 수동으로 했던 작업들을 자동화해주는 도구다. 하지만 모든 것을 해주는 것은 아니다. 머신 프로비저닝, CNI 플러그인 설치 등은 여전히 직접 해야 한다.

이런 설계 철학 덕분에 kubeadm은 다양한 환경에서 유연하게 사용할 수 있다. 온프레미스든, 클라우드든, VM이든, 베어메탈이든 상관없이 kubeadm으로 클러스터를 구성할 수 있다. 그리고 kubespray, Cluster API 같은 도구들이 kubeadm 위에서 더 높은 수준의 자동화를 제공한다.

1주차에 손으로 직접 클러스터를 구성해봤기 때문에, kubeadm이 어떤 작업들을 자동화해주는지 더 잘 이해할 수 있다. 다음 글에서는 실제로 kubeadm을 사용해 클러스터를 구성해 본다.
