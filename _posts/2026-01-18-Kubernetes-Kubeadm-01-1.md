---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.1. kubeadm init"
excerpt: "kubeadm init 명령어의 동작 원리와 각 단계를 살펴보자."
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

이번 글의 목표는 **kubeadm init 명령어의 동작 원리 이해**다.

- **kubeadm init**: 컨트롤 플레인 노드를 부트스트래핑하는 핵심 명령어
- **14개의 단계**: preflight → certs → kubeconfig → etcd → control-plane → ... → addon
- **핵심 산출물**: 인증서, kubeconfig 파일, Static Pod 매니페스트, bootstrap token
- **특징**: etcd는 mTLS 필수, Control Plane 컴포넌트는 Static Pod로 배포

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %})에서 kubeadm의 개념과 설계 철학을 살펴보았다. kubeadm은 `kubeadm init`과 `kubeadm join`이라는 두 명령어로 클러스터를 빠르게 구성할 수 있다고 했다.

이번 글에서는 그 중 **`kubeadm init`** 명령어를 상세히 살펴본다. kubeadm init은 컨트롤 플레인 노드를 부트스트래핑하는 핵심 명령어다. 내부적으로 어떤 단계들이 실행되는지, 각 단계에서 무엇이 생성되는지 이해하면 클러스터 운영 시 트러블슈팅에 큰 도움이 된다.

- [kubeadm init](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/)

<br>

# kubeadm init

![kubeadm-init-process]({{site.url}}/assets/images/kubeadm-init-process.png){: .align-center}
<center><sup>kubeadm init을 이용한 control plane init 과정</sup></center>

## 개요

`kubeadm init`은 Kubernetes 컨트롤 플레인을 초기화하는 명령어다.

```bash
kubeadm init [flags]
```

이 명령어 하나로 다음 작업들이 자동으로 수행된다:
- 클러스터 CA 및 각 컴포넌트용 TLS 인증서 생성
- kubeconfig 파일 생성
- etcd 및 컨트롤 플레인 컴포넌트를 Static Pod로 배포
- 워커 노드 join을 위한 bootstrap token 생성

> **참고: Phase 표기법**
>
> `kubeadm init --help`나 공식 문서에서 `/ca`, `/apiserver` 같은 표기를 볼 수 있다. 이는 파일 경로가 아니라 **하위 단계(sub-phase)**를 나타내는 표기법이다.
>
> ```
> certs                    ← 상위 단계 (parent phase)
>   /ca                    ← 하위 단계 (sub-phase)
>   /apiserver             ← 하위 단계
> ```
>
> 실제 명령어에서는 슬래시 없이 `<상위단계> <하위단계>` 형태로 사용한다:
> ```bash
> kubeadm init phase certs ca          # /ca가 아님
> kubeadm init phase certs apiserver   # /apiserver가 아님
> kubeadm init phase addon coredns     # /coredns가 아님
> ```

<br>

## 주요 옵션

| 옵션 | 설명 |
| --- | --- |
| `--apiserver-advertise-address` | API Server가 광고할 IP 주소 |
| `--apiserver-cert-extra-sans` | API Server 인증서에 추가할 SAN(Subject Alternative Name) |
| `--cert-dir` | 인증서 저장 경로 (기본값: `/etc/kubernetes/pki`) |
| `--control-plane-endpoint` | 컨트롤 플레인의 엔드포인트 (HA 구성 시 로드밸런서 주소) |
| `--pod-network-cidr` | Pod 네트워크 CIDR (CNI에 따라 필요) |
| `--service-cidr` | Service 네트워크 CIDR (기본값: 10.96.0.0/12) |
| `--token` | 워커 노드 join 시 사용할 토큰 (미지정 시 자동 생성) |
| `--ignore-preflight-errors` | 무시할 preflight 에러 목록 |

### --apiserver-cert-extra-sans: API Server 인증서 SAN 추가

API Server 인증서는 클라이언트가 접속할 때 사용하는 모든 이름/IP에 대해 유효해야 한다. 이를 위해 **SAN(Subject Alternative Name)** 확장 필드를 사용한다.

> SAN은 하나의 인증서로 여러 호스트명이나 IP를 인증할 수 있게 해주는 X.509 확장 필드다. 자세한 내용은 [X.509 인증서의 SAN]({% post_url 2026-01-04-CS-Security-X509-Certificate %}#확장-필드extensions) 또는 [Kubernetes The Hard Way의 SAN 설명]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %}#sansubject-alternative-name)을 참고하자.

kubeadm은 기본적으로 다음 SAN을 포함한다:
- 노드의 호스트명과 IP 주소
- `kubernetes`, `kubernetes.default`, `kubernetes.default.svc` 등 내부 DNS 이름
- Service CIDR의 첫 번째 IP (기본값: `10.96.0.1`)

로드밸런서나 커스텀 도메인을 통해 API Server에 접근한다면, `--apiserver-cert-extra-sans` 옵션으로 추가 SAN을 지정해야 한다.

```bash
kubeadm init --apiserver-cert-extra-sans=kubernetes.example.com,10.0.0.100
```

### --control-plane-endpoint: HA 구성의 핵심

단일 컨트롤 플레인 클러스터라면 이 옵션이 필수는 아니다. 하지만 **나중에 HA(고가용성) 구성으로 확장할 계획**이 있다면 반드시 처음부터 지정해야 한다.

```bash
# HA 구성을 위한 로드밸런서 엔드포인트 지정
kubeadm init --control-plane-endpoint "k8s-api.example.com:6443"
```

이 옵션을 지정하면:
- 모든 kubeconfig 파일에 이 엔드포인트가 기록됨
- 워커 노드들이 이 주소로 API Server에 접근
- 추가 컨트롤 플레인 노드가 조인할 수 있음

> **주의**: 이 옵션 없이 클러스터를 생성한 후에는 HA로 전환하기 어렵다. 처음부터 다시 구성해야 할 수 있다.

> **참고: HA 구성 시 로드밸런서의 필요성**
>
> "처음부터 지정해야 한다면, 로드밸런서도 처음부터 준비해야 하는 건가?"라고 궁금할 수 있다.
>
> `--control-plane-endpoint`는 처음부터 지정해야 한다. 이 값이 인증서 SAN, kubeconfig, kubelet 설정 등에 포함되어 나중에 변경하기 어렵기 때문이다. 다만, **실제 로드밸런서 인프라가 즉시 준비되어 있을 필요는 없다**.
>
> 핵심은 **시점별 요구사항**이 다르다는 것이다. `kubeadm init` 시점에는 해당 주소의 유효성을 검증하지 않지만, **`kubeadm join` 시점에는 해당 주소로 반드시 연결이 되어야 한다**. 따라서 일반적인 패턴은 다음과 같다:
>
> 1. `init` 시 DNS 기반 endpoint 지정 (예: `k8s-api.example.com`)
> 2. 해당 DNS를 첫 번째 컨트롤 플레인 IP로 설정
> 3. 워커 노드 join (DNS가 첫 번째 CP를 가리키므로 연결 가능)
> 4. 나중에 LB 구성 후 DNS를 LB IP로 변경
> 5. 추가 컨트롤 플레인 join (LB를 통해 연결)
>
> 아래는 HA 구성 시 API Server 앞단을 구성하는 방식들이다:
>
> | 구분 | 방식 | 설명 |
> | --- | --- | --- |
> | **별도 LB 인프라 불필요** | DNS 방식 | DNS를 처음엔 단일 노드 IP로, 나중에 LB IP로 변경 |
> | | Virtual IP (kube-vip) | Static Pod로 VIP 제공 |
> | | HAProxy + Keepalived | 컨트롤 플레인 노드에 직접 설치하여 VIP 제공 |
> | **LB 인프라 필요** | 클라우드 LB | AWS ELB, GCP LB 등 미리 생성 후 endpoint로 지정 |
> 
> 즉, **endpoint 값 자체는 처음부터 정해야 하고 join 시점에는 연결 가능해야 한다**. DNS 방식을 사용하면 endpoint 값은 그대로 두고 DNS 레코드가 가리키는 IP만 변경하여 나중에 LB로 전환할 수 있다. 반면 IP를 직접 지정하면 나중에 변경이 어려우므로, **HA 전환 가능성이 있다면 DNS 기반 endpoint를 사용할 것이 일반적으로 권장된다**.

### --pod-network-cidr: Pod 네트워크 대역

Pod들이 사용할 IP 대역을 지정한다. CNI 플러그인에 따라 필수이거나 특정 값이 요구될 수 있다.

| CNI | 요구 사항 |
| --- | --- |
| Calico | 기본 `192.168.0.0/16`, 다른 값 사용 시 매니페스트 수정 필요 |
| Flannel | `10.244.0.0/16` 고정 (변경 시 매니페스트 수정 필요) |
| Cilium | 자동 감지, 명시적 지정 권장 |

```bash
# Calico 기본값 사용
kubeadm init --pod-network-cidr=192.168.0.0/16

# Flannel 사용 시
kubeadm init --pod-network-cidr=10.244.0.0/16
```

> **참고: 네트워크 대역 충돌 주의**
>
> `--pod-network-cidr`은 노드의 실제 네트워크 대역과 겹치지 않아야 한다. Pod 네트워크 CIDR이 노드의 라우팅 테이블에 등록되기 때문에, 외부 네트워크와 대역이 겹치면 해당 대역으로 가야 할 패킷이 Pod 네트워크 쪽으로 잘못 라우팅되어 통신이 끊어진다.
>
> 이는 Docker Bridge 네트워크에서 발생하는 IP 충돌 문제와 동일한 원리다. 자세한 사례는 [Docker Bridge Network IP 충돌]({% post_url 2023-11-09-Dev-docker-network-bridge-ip-collision-1 %})을 참고하자.

<br>

# kubeadm init 단계

컨트롤 플레인에서 `kubeadm init`을 실행하면 아래 단계들이 순차적으로 진행된다. 일부 단계는 설정에 따라 건너뛸 수 있다.

1. preflight
2. certs
3. kubeconfig
4. etcd *(stacked etcd인 경우)*
5. control-plane
6. kubelet-start
7. wait-control-plane
8. upload-config
9. upload-certs *(`--upload-certs` 사용 시)*
10. mark-control-plane
11. bootstrap-token
12. kubelet-finalize
13. addon
14. show-join-command

<br>

각 단계는 `kubeadm init phase <phase-name>` 명령으로 개별 실행할 수 있다.

- `--help`: 단계 목록과 하위 단계를 확인할 수 있다.
- `--skip-phases`: 특정 단계를 건너뛰고 실행할 수 있다. 커스텀 설정이 필요한 경우 유용하다.

```bash
# 전체 단계 목록 확인
kubeadm init phase --help

# 특정 단계의 하위 단계 확인
kubeadm init phase control-plane --help

# 특정 단계만 실행 (예: 인증서 생성)
kubeadm init phase certs all

# 특정 단계를 건너뛰고 실행
kubeadm init --skip-phases=control-plane,etcd --config=config.yaml
```

> 참고: 매니페스트 커스터마이징에서의 활용 예
>
> Control Plane과 etcd의 Static Pod 매니페스트를 수정하고 싶다면:
> 1. 먼저 매니페스트 생성 단계만 실행
>    ```bash
>    kubeadm init phase control-plane all --config=config.yaml
>    kubeadm init phase etcd local --config=config.yaml
>    ```
> 2. `/etc/kubernetes/manifests/`의 매니페스트 파일 수정
> 3. 해당 단계를 건너뛰고 나머지 실행
>    ```bash
>    kubeadm init --skip-phases=control-plane,etcd --config=config.yaml
>    ```

<br>

## 1. preflight

시스템 요구사항을 검증한다.

| 검증 항목 | 설명 |
| --- | --- |
| 포트 사용 | 6443, 10250, 10259, 10257, 2379-2380 등 필요 포트 확인 |
| 컨테이너 런타임 | containerd, CRI-O 등 설치 여부 |
| 시스템 요구사항 | 메모리, CPU, swap 비활성화 여부 |
| 커널 모듈 | br_netfilter, overlay 등 필요 모듈 로드 여부 |

대표적인 에러 예시:
- `[Error]` CRI 엔드포인트 연결 실패 → 컨테이너 런타임 확인 필요
- `[Error]` 루트 권한 아님 → `sudo`로 실행 필요
- `[Error]` kubelet 버전이 최소 요구 버전(현재 minor - 1) 미만

일부 체크는 경고만 출력하고 계속 진행하지만, 에러로 처리되면 kubeadm이 종료된다. 에러를 무시하려면 `--ignore-preflight-errors` 옵션을 사용한다.

```bash
# 예: swap 관련 에러 무시
kubeadm init --ignore-preflight-errors=Swap
```

<br>

## 2. certs

클러스터에 필요한 모든 인증서를 생성한다. 기본 저장 경로는 `/etc/kubernetes/pki`다.

| 하위 단계 | 생성 파일 | 설명 |
| --- | --- | --- |
| ca | `ca.crt`, `ca.key` | 클러스터 컴포넌트 인증서에 서명하는 self-signed Kubernetes CA |
| apiserver | `apiserver.crt`, `apiserver.key` | API Server가 서비스할 때 사용하는 서버 인증서 |
| apiserver-kubelet-client | `apiserver-kubelet-client.crt`, `apiserver-kubelet-client.key` | API Server가 Kubelet에 요청할 때 사용하는 클라이언트 인증서 |
| front-proxy-ca | `front-proxy-ca.crt`, `front-proxy-ca.key` | API 확장(Aggregation Layer)용 인증서를 서명하는 전용 CA |
| front-proxy-client | `front-proxy-client.crt`, `front-proxy-client.key` | API Server가 확장 API 서버에 프록시 요청할 때 사용하는 클라이언트 인증서 |
| etcd-ca | `etcd/ca.crt`, `etcd/ca.key` | etcd 관련 인증서에 서명하는 전용 CA |
| etcd-server | `etcd/server.crt`, `etcd/server.key` | etcd가 서비스할 때 사용하는 서버 인증서 |
| etcd-peer | `etcd/peer.crt`, `etcd/peer.key` | etcd 노드 간 상호 통신 시 사용하는 인증서 |
| etcd-healthcheck-client | `etcd/healthcheck-client.crt`, `etcd/healthcheck-client.key` | etcd 헬스체크 시 사용하는 클라이언트 인증서 |
| apiserver-etcd-client | `apiserver-etcd-client.crt`, `apiserver-etcd-client.key` | API Server가 etcd에 요청할 때 사용하는 클라이언트 인증서 |
| sa | `sa.key`, `sa.pub` | Service Account 토큰 서명 및 검증에 사용되는 키 페어 |

```bash
# 특정 인증서만 생성하는 예시
kubeadm init phase certs ca                    # CA만 생성
kubeadm init phase certs apiserver             # API Server 인증서만 생성
kubeadm init phase certs etcd-ca               # etcd CA만 생성
kubeadm init phase certs all                   # 모든 인증서 생성
```


> **참고: Aggregation Layer와 Front Proxy**
>
> **Aggregation Layer**는 Kubernetes API를 확장할 수 있게 해주는 기능이다. 사용자 정의 API 서버(확장 API 서버)를 kube-apiserver에 "통합(aggregate)"하여, 클라이언트가 동일한 kube-apiserver 엔드포인트로 확장 API에도 접근할 수 있게 한다.
>
> 대표적인 확장 API 서버로는 다음이 있다:
> - **metrics-server**: `metrics.k8s.io` API 제공 (`kubectl top` 명령어)
> - **custom-metrics-server**: 사용자 정의 메트릭 API
> - **service-catalog**: 외부 서비스 브로커 연동
>
> **Front Proxy**는 이 Aggregation Layer에서 kube-apiserver가 확장 API 서버로 요청을 전달(프록시)할 때 사용하는 메커니즘이다.
>
> ```
> kubectl top nodes  # metrics API 요청
>     → kube-apiserver가 요청 받음
>     → "이건 metrics.k8s.io API니까 metrics-server로 proxy해야겠다"
>     → front-proxy-client.crt로 자신을 인증하며 metrics-server에 요청
>     → metrics-server 응답을 클라이언트에게 전달
> ```
>
> 확장 API 서버는 요청이 정당한 kube-apiserver로부터 온 것인지 검증해야 한다. 이를 위해 kube-apiserver는 `front-proxy-client` 인증서로 자신을 증명하고, 확장 API 서버는 `front-proxy-ca`로 이를 검증한다.


### 기존 CA 사용

위 테이블의 CA 인증서들(`/ca`, `/front-proxy-ca`, `/etcd-ca`)은 kubeadm이 자동으로 생성한다. 하지만 조직에서 이미 사용 중인 CA가 있다면 그것을 사용할 수도 있다.

기존 CA를 사용하려면 `--cert-dir` 경로(기본값: `/etc/kubernetes/pki`)에 `ca.crt`, `ca.key`를 미리 넣어두면 된다. kubeadm은 해당 CA가 존재하면 새로 생성하지 않고, 이 CA를 사용하여 나머지 인증서를 서명한다.

> **참고: Identity Provisioning**
>
> 공식 문서에서 CA 인증서 생성을 설명할 때 다음과 같이 "provision identities"라는 표현이 자주 등장한다.
>
> ```
> /ca             Generate the self-signed Kubernetes CA to provision identities for other Kubernetes components
> /front-proxy-ca Generate the self-signed CA to provision identities for front proxy
> /etcd-ca        Generate the self-signed CA to provision identities for etcd
> ```
>
> identity를 provisioning한다는 게 무슨 의미일까? PKI 관점에서 해석해 보면:
> - **Identity(신원)**: 각 컴포넌트가 "나는 kube-apiserver다", "나는 kubelet이다"라고 증명할 수 있는 능력. 즉, **인증서**가 곧 신원 증명 수단이다.
> - **Provision(제공)**: 생성해서 제공하는 행위
>
> 따라서 "provision identities"는 **각 컴포넌트의 인증서를 발급해주는 행위**를 의미한다. 각 CA의 역할을 해석하면:
> - **Kubernetes CA (`/ca`)**: kube-apiserver, kubelet, controller-manager 등 핵심 컴포넌트들의 인증서를 서명
> - **Front Proxy CA (`/front-proxy-ca`)**: API 확장(Aggregation Layer)용 front-proxy-client 인증서를 서명. API Server가 확장 API 서버(metrics-server 등)에 프록시할 때 사용
> - **etcd CA (`/etcd-ca`)**: etcd 서버, 피어 간 통신, 헬스체크 클라이언트 등 etcd 관련 인증서를 서명
>
> 각 CA가 서명한 인증서를 가진 컴포넌트들은 해당 CA를 신뢰하는 다른 컴포넌트들과 안전하게 통신할 수 있다. 




<br>

## 3. kubeconfig

`/etc/kubernetes/`에 각 컴포넌트용 kubeconfig 파일을 생성한다.

| kubeconfig | 설명 |
| --- | --- |
| `/admin.conf` | 클러스터 관리자 및 kubeadm 자체가 사용 |
| `/super-admin.conf` | RBAC를 우회할 수 있는 슈퍼 관리자용 |
| `/kubelet.conf` | 클러스터 부트스트래핑 시 kubelet이 사용 |
| `/controller-manager.conf` | kube-controller-manager가 사용 |
| `/scheduler.conf` | kube-scheduler가 사용 |

생성된 kubeconfig 파일은 각 컴포넌트가 API Server와 통신할 때 사용된다.

```bash
# admin.conf를 사용하여 kubectl 설정
mkdir -p $HOME/.kube
cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
chown $(id -u):$(id -g) $HOME/.kube/config
```

<br>

## 4. etcd

`/etc/kubernetes/manifests/`에 로컬 etcd 인스턴스를 위한 Static Pod 매니페스트를 생성한다.

> **참고: Static Pod**
>
> Static Pod는 API Server를 거치지 않고 kubelet이 직접 관리하는 Pod다. 매니페스트 파일을 특정 디렉토리에 두면 kubelet이 자동으로 Pod를 생성하고 관리한다. 
> 따라서 컨트롤 플레인 컴포넌트를 Static Pod로 배포하면 API Server가 없는 상태에서도 컨트롤 플레인을 부트스트래핑할 수 있다.


이 단계의 하위 단계는 `local` 하나뿐이다:

```bash
kubeadm init phase etcd local
```

여기서 **`local`은 컨트롤 플레인 노드에서 직접 실행되는 etcd**를 의미한다. kubeadm의 기본 구성이며, etcd가 Static Pod로 컨트롤 플레인과 같은 노드에서 실행된다.

```yaml
# /etc/kubernetes/manifests/etcd.yaml (예시)
apiVersion: v1
kind: Pod
metadata:
  name: etcd
  namespace: kube-system
spec:
  containers:
  - name: etcd
    image: registry.k8s.io/etcd:3.5.x
    command:
    - etcd
    - --advertise-client-urls=https://192.168.1.100:2379
    - --cert-file=/etc/kubernetes/pki/etcd/server.crt
    - --key-file=/etc/kubernetes/pki/etcd/server.key
    # ... 기타 옵션
```

### etcd 인증서가 필요한 이유

kubeadm으로 설치하면 etcd는 **모든 연결에 mTLS(mutual TLS)를 요구**한다. 헬스체크조차 인증서 없이는 불가능하다.

```bash
# etcd 헬스체크 예시
etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  endpoint health
```

Kubernetes The Hard Way에서는 학습 목적으로 etcd를 HTTP로 구성했지만, kubeadm은 보안을 위해 HTTPS를 기본으로 사용한다.

### 외부 etcd 사용 시

별도 서버에서 운영되는 **외부(external) etcd**를 사용하는 경우, 이 단계(`etcd local`)는 건너뛴다.

외부 etcd 사용 시 인증서의 경우:
- etcd server/peer/healthcheck 인증서는 **외부 etcd 클러스터에서 자체 관리**한다.
- kube-apiserver가 외부 etcd에 접속하려면 `etcd-ca`(검증용)와 `apiserver-etcd-client`(인증용) 인증서가 필요하다. 이 인증서들은 **사용자가 외부 etcd 클러스터로부터 받아서 직접 준비**해야 한다.

외부 etcd를 사용하려면 `kubeadm init --config` 옵션으로 설정 파일을 전달한다. 설정 파일에서 준비한 인증서의 경로를 지정한다:

```yaml
# kubeadm-config.yaml
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
etcd:
  external:
    endpoints:
      - https://etcd1.example.com:2379
      - https://etcd2.example.com:2379
    caFile: /etc/kubernetes/pki/etcd/ca.crt              # 외부 etcd CA 인증서 경로
    certFile: /etc/kubernetes/pki/apiserver-etcd-client.crt  # 클라이언트 인증서 경로
    keyFile: /etc/kubernetes/pki/apiserver-etcd-client.key   # 클라이언트 키 경로
```

<br>

## 5. control-plane

`/etc/kubernetes/manifests/`에 컨트롤 플레인 컴포넌트의 Static Pod 매니페스트를 생성한다.

| 컴포넌트 | 매니페스트 파일 |
| --- | --- |
| kube-apiserver | `/etc/kubernetes/manifests/kube-apiserver.yaml` |
| kube-controller-manager | `/etc/kubernetes/manifests/kube-controller-manager.yaml` |
| kube-scheduler | `/etc/kubernetes/manifests/kube-scheduler.yaml` |

<br>

모든 컨트롤 플레인 Static Pod는 다음과 같은 공통 설정을 갖는다:

| 설정 | 값 | 설명 |
| --- | --- | --- |
| namespace | `kube-system` | 시스템 컴포넌트용 네임스페이스 |
| labels | `tier:control-plane`, `component:{name}` | 컨트롤 플레인 식별용 |
| priorityClassName | `system-node-critical` | 노드 필수 컴포넌트로서 최고 우선순위 |
| hostNetwork | `true` | 컨트롤 플레인 부트스트랩 시 네트워크 접근 허용 |

kubelet은 `/etc/kubernetes/manifests/` 디렉토리를 감시하고 있다가, 이 매니페스트 파일들이 생성되면 해당 Pod를 자동으로 생성한다.


<br>

## 6. kubelet-start

kubelet 설정을 작성하고 kubelet을 시작한다.

- `/var/lib/kubelet/config.yaml`: kubelet 설정 파일 생성
- `/var/lib/kubelet/kubeadm-flags.env`: kubeadm이 전달하는 kubelet 플래그
- systemctl로 kubelet 서비스 시작

```bash
# kubelet 설정 파일 확인
cat /var/lib/kubelet/config.yaml
```

<br>

## 7. wait-control-plane

컨트롤 플레인 Pod가 정상적으로 실행될 때까지 대기한다.

- kubelet이 Static Pod를 생성하고 컨테이너가 Running 상태가 될 때까지 기다림
- API Server의 `/healthz` 또는 `/livez` 엔드포인트가 정상 응답할 때까지 대기
- 타임아웃 시 에러 발생

<br>

## 8. upload-config

kubeadm 및 kubelet 설정을 ConfigMap으로 클러스터에 업로드한다.

| ConfigMap | Namespace | 설명 |
| --- | --- | --- |
| `kubeadm-config` | kube-system | kubeadm 클러스터 설정 |
| `kubelet-config` | kube-system | kubelet 설정 |

이후 노드가 join할 때 이 ConfigMap을 참조하여 동일한 설정을 적용한다.

```bash
# kubeadm 설정 확인
kubectl get configmap kubeadm-config -n kube-system -o yaml
```

<br>

## 9. upload-certs

인증서를 `kubeadm-certs` Secret에 업로드한다.

- HA 구성 시 다른 컨트롤 플레인 노드가 인증서를 가져갈 수 있도록 함
- 기본적으로 2시간 후 자동 삭제됨
- `--upload-certs` 플래그를 사용해야 활성화됨

```bash
# HA 구성 시 인증서 업로드
kubeadm init --control-plane-endpoint "LOAD_BALANCER_DNS:LOAD_BALANCER_PORT" --upload-certs
```

<br>

## 10. mark-control-plane

노드에 컨트롤 플레인 역할을 표시하는 label과 taint를 추가한다.

```bash
# 추가되는 label
node-role.kubernetes.io/control-plane=

# 추가되는 taint
node-role.kubernetes.io/control-plane:NoSchedule
```

이 taint로 인해 일반 워크로드 Pod가 컨트롤 플레인 노드에 스케줄되지 않는다.

<br>

## 11. bootstrap-token

워커 노드가 클러스터에 join할 때 사용할 부트스트랩 토큰을 생성한다.

- `--token` 옵션으로 사용자가 직접 토큰을 제공할 수도 있음
- 토큰은 기본적으로 24시간 후 만료됨

```bash
# 토큰 목록 확인
kubeadm token list

# 새 토큰 생성 (join 명령어 포함)
kubeadm token create --print-join-command
```

### Bootstrap Token과 TLS Bootstrap

새 노드가 클러스터에 join할 때 사용하는 메커니즘을 위한 설정이다. 아직 인증서가 없는 노드가 어떻게 API Server에 접근하여 인증서를 발급받을 수 있을까? 이 "닭과 달걀" 문제를 해결하기 위한 설정들이다.

- `kube-public` 네임스페이스에 `cluster-info` ConfigMap 생성
  - 클러스터 join에 필요한 최소한의 정보(API Server 주소, CA 인증서 등) 포함
  - 인증되지 않은 사용자(`system:unauthenticated`)도 접근 가능하도록 RBAC 설정 → 인증서 없이도 부트스트랩 데이터 획득 가능
- Bootstrap Token이 CSR(Certificate Signing Request) 서명 API에 접근할 수 있도록 허용
- 새로운 CSR 요청에 대한 자동 승인 설정

> 이 메커니즘의 상세 동작은 `kubeadm join`을 다루는 글에서 살펴본다.

<br>

## 12. kubelet-finalize

TLS 부트스트랩 이후 kubelet 관련 설정을 최종 업데이트한다.

- kubelet kubeconfig 업데이트
- 클라이언트 인증서 자동 갱신(rotation) 활성화

<br>

## 13. addon

필수 애드온을 설치한다.

| 애드온 | 배포 방식 | 설명 |
| --- | --- | --- |
| **kube-proxy** | DaemonSet | 모든 노드에서 서비스 네트워킹 담당 (iptables 또는 IPVS 기반) |
| **CoreDNS** | Deployment | 클러스터 내부 DNS (Kubernetes 1.11+에서 기본) |

- **kube-proxy**: `kube-system` 네임스페이스에 ServiceAccount 생성 후 DaemonSet으로 배포
- **CoreDNS**: 서비스 이름이 `kube-dns`로 설정됨 (레거시 `kube-dns` 애드온과의 호환성)

> **참고**: CoreDNS는 Deployment로 배포되지만, CNI가 설치될 때까지 Pod가 스케줄되지 않는다. CNI 플러그인 설치 후에 CoreDNS Pod가 Running 상태가 된다.

<br>

## 14. show-join-command

다른 노드가 클러스터에 join할 때 사용할 명령어를 출력한다.

```bash
# 출력 예시
kubeadm join 192.168.1.100:6443 --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxx...
```

<br>

# kubeadm init 결과물

`kubeadm init`이 완료되면 다음과 같은 결과물이 생성된다.

## 디렉토리 구조

```
/etc/kubernetes/
├── admin.conf                    # 관리자용 kubeconfig
├── controller-manager.conf       # controller-manager용 kubeconfig
├── kubelet.conf                  # kubelet용 kubeconfig
├── scheduler.conf                # scheduler용 kubeconfig
├── super-admin.conf              # 슈퍼 관리자용 kubeconfig
├── manifests/
│   ├── etcd.yaml                 # etcd Static Pod
│   ├── kube-apiserver.yaml       # API Server Static Pod
│   ├── kube-controller-manager.yaml
│   └── kube-scheduler.yaml
└── pki/
    ├── ca.crt                    # Kubernetes CA 인증서
    ├── ca.key                    # Kubernetes CA 키
    ├── apiserver.crt             # API Server 인증서
    ├── apiserver.key
    ├── apiserver-kubelet-client.crt
    ├── apiserver-kubelet-client.key
    ├── front-proxy-ca.crt
    ├── front-proxy-ca.key
    ├── front-proxy-client.crt
    ├── front-proxy-client.key
    ├── sa.key                    # Service Account 키
    ├── sa.pub
    └── etcd/
        ├── ca.crt                # etcd CA
        ├── ca.key
        ├── server.crt
        ├── server.key
        ├── peer.crt
        ├── peer.key
        ├── healthcheck-client.crt
        └── healthcheck-client.key
```

<br>

# 더 알아보기

이 글에서는 `kubeadm init`의 기본적인 옵션과 14개 단계를 살펴보았다. 공식 문서에서는 이 외에도 다양한 고급 사용법을 다루고 있다:

| 주제 | 설명 |
| --- | --- |
| [Configuration File](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#config-file) | YAML 설정 파일로 클러스터 구성을 선언적으로 관리 |
| [Feature Gates](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#feature-gates) | 실험적 기능이나 베타 기능 활성화/비활성화 (`--feature-gates` 플래그) |
| [kube-proxy Parameters](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#kube-proxy) | kube-proxy 설정 (IPVS 모드 등) |
| [Control Plane Flags](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#control-plane-flags) | 컨트롤 플레인 컴포넌트에 커스텀 플래그 전달 |
| [Running without Internet](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#without-internet-connection) | 오프라인 환경에서 이미지 사전 다운로드 후 설치 |
| [Custom Images](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#custom-images) | 커스텀 이미지 레지스트리 사용 |
| [Uploading Certificates](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/#uploading-control-plane-certificates-to-the-cluster) | HA 구성 시 `--upload-certs`로 인증서를 Secret에 임시 저장 |

특히 **Configuration File**을 활용하면 명령줄 옵션 대신 YAML 파일로 클러스터 구성을 관리할 수 있어, 버전 관리나 재현 가능한 배포에 유리하다.

<br>

# 마무리

`kubeadm init`은 컨트롤 플레인을 부트스트래핑하는 핵심 명령어다. 내부적으로 14개의 단계를 거치며, 각 단계에서 인증서, kubeconfig, Static Pod 매니페스트 등을 생성한다.

Kubernetes The Hard Way에서 수동으로 수행했던 작업들이 어떻게 자동화되는지 비교해보면:

| 수동 작업 (The Hard Way) | kubeadm init 단계 |
| --- | --- |
| OpenSSL로 CA/인증서 생성 | `certs` |
| kubectl로 kubeconfig 생성 | `kubeconfig` |
| etcd systemd 서비스 구성 | `etcd` (Static Pod) |
| 컨트롤 플레인 systemd 서비스 구성 | `control-plane` (Static Pod) |
| kubelet 설정 및 시작 | `kubelet-start` |

kubeadm은 이 모든 작업을 자동화하면서도, 각 단계를 개별적으로 실행할 수 있는 유연성을 제공한다. 이러한 설계 덕분에 커스텀 클러스터 구성이나 트러블슈팅이 가능하다.

다음 글에서는 실제로 kubeadm을 설치하고, `kubeadm init`을 실행하여 컨트롤 플레인을 구성해 본다.
