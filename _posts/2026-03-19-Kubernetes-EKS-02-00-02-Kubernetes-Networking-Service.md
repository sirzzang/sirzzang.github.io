---
title:  "[EKS] EKS: Networking - 0. 쿠버네티스 네트워킹 모델 - 2. Service와 kube-proxy"
excerpt: "쿠버네티스 Service와 kube-proxy가 제공하는 고수준 네트워킹 추상화에 대해 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - Networking
  - Service
  - kube-proxy
  - iptables
  - IPVS
  - nftables
  - eBPF
  - ClusterIP
  - NodePort
  - LoadBalancer
  - netfilter
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2
  
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- **Service**는 파드 IP의 휘발성을 해결하는 추상화 계층이다. label selector로 파드를 선택하고, **Endpoints**가 실제 IP:Port 매핑을 추적한다
- Service 타입: ClusterIP(내부) → NodePort(노드 포트) → LoadBalancer(외부 LB)로 점진 확장된다
- **kube-proxy**는 모든 워커 노드에서 DaemonSet으로 동작하며, Endpoints 변경을 watch해서 커널에 DNAT/로드밸런싱 규칙을 설치한다
- 네트워크 규칙을 설치하는 두 컴포넌트:
  - **kube-proxy**: Service 추상화 — DNAT(ClusterIP → Pod IP) + MASQUERADE(리턴 경로 보장)
  - **CNI 플러그인**: 파드 네트워크 — SNAT(파드의 외부 통신 시 Pod IP → Node IP)
- 둘 다 POSTROUTING에 규칙을 설치하지만 **매칭 조건이 다르므로 충돌하지 않는다**. 이 NAT들은 "NAT 없이" 원칙에 **위배되지 않는다**
- kube-proxy 모드: **userspace**(초기, 프로세스가 직접 프록시) → **iptables**(기본, 커널 DNAT) → **IPVS**(해시 O(1)) → **nftables**(iptables 후속) → **eBPF**(커널 스택 우회, Cilium)

<br>

# 들어가며

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %})에서 쿠버네티스 네트워킹의 핵심인 **문제 2 — 파드 간 통신**을 다뤘다. 같은 노드에서는 veth pair + 브릿지로, 다른 노드에서는 오버레이/BGP/클라우드 네이티브 라우팅으로 NAT 없이 파드 간 직접 통신을 구현하는 방식이었다.

이 글에서는 [첫 번째 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#문제-3-파드--서비스)에서 간단히 언급했던 **문제 3 — 파드 ↔ 서비스**, 그리고 **문제 4 — 외부 ↔ 서비스** 통신을 본격적으로 다룬다.

여기서 다루는 Service 계층은, 앞선 두 글에서 다뤘던 인프라 계층과 성격이 다르다. 컨테이너 네트워킹(같은 노드 내 파드 간 통신)과 CNI(다른 노드 파드 간 통신)가 **"파드 IP로 직접 통신할 수 있는 flat network"를 만드는 인프라**라면, Service는 그 인프라 위에 얹히는 **추상화 계층**이다. 아래에서는 이 추상화가 무엇을 해결하고, 어떻게 동작하며, 왜 가상 IP라는 형태를 취하는지를 살펴본다.

<br>

# Service

## 배경: 파드 IP의 한계

파드 간 직접 통신(문제 2)이 해결되면, 파드 A가 파드 B의 IP를 알기만 하면 바로 통신할 수 있다. 그런데 실제 운영 환경에서는 이것만으로 부족하다.

**파드 IP는 휘발성**이다. 파드가 죽으면 IP가 사라지고, 새 파드가 뜨면 다른 IP를 받는다. Deployment로 3개의 nginx 파드를 띄웠다면, 스케일링이나 롤링 업데이트 때마다 IP가 바뀐다. 클라이언트가 특정 파드 IP를 하드코딩하면 파드가 재시작되는 순간 통신이 끊긴다.

이것은 쿠버네티스의 설계 철학에서 비롯된 의도된 결과다:

- **불변 인프라(Immutable Infrastructure)**: 쿠버네티스는 고장 난 파드를 고치지 않고 교체한다. 파드는 수리 대상이 아니라 교체 대상이다. 교체가 일상이니 IP도 매번 새로 할당되는 것이 자연스럽다. IP를 유지하려면 "이전 파드의 상태를 기억하고 복원"해야 하는데, 이는 불변 인프라 원칙에 위배된다.
- **스케줄링 자유도**: 파드 IP가 안정적이려면 IP가 특정 노드나 네트워크 위치에 묶여야 한다. 그러면 스케줄러가 "이 IP가 있는 노드에만 파드를 배치"해야 하는 제약이 생긴다. 쿠버네티스 스케줄러는 리소스, affinity, taint 등 다양한 조건으로 **아무 노드에나** 파드를 배치할 수 있어야 하므로, IP를 노드에 종속시키면 이 자유도가 깨진다.
- **정체성과 위치의 분리**: 가장 근본적인 설계 결정이다. 쿠버네티스는 서비스의 정체성(이름, 역할)과 네트워크 위치(IP)를 의도적으로 분리한다. "nginx 서비스"라는 정체성은 안정적이어야 하지만, 그 뒤에서 실제로 트래픽을 처리하는 파드들의 IP는 언제든 바뀔 수 있다. 이 분리 덕분에 스케일링, 롤링 업데이트, 자가 치유 모두 클라이언트에 영향 없이 동작한다.

쿠버네티스에서 파드는 **cattle(가축)이지 pet(반려동물)이 아니다**. 전통적인 서버 관리에서 서버는 pet — 이름을 붙이고, 아프면 밤새 치료하고, 하나하나 소중히 관리하는 대상이었다. 쿠버네티스의 파드는 cattle — 번호를 매기고, 아프면 치료하지 않고 교체하는 대상이다. 파드는 언제든 죽을 수 있고, 죽어도 괜찮게 설계하는 것이 원칙이다. 개별 파드의 정체성(IP, 상태)에 의존하지 않는 구조를 만들어야 한다.

이 휘발성이 만드는 문제를 해결하기 위해 쿠버네티스가 도입한 추상화가 바로 **Service**다.

## 정의

서비스는 파드 집합에 대한 **안정적인 네트워크 접점(고정 IP + DNS)**을 제공하는 추상화 계층입니다.



```
[Service 없이]
Client → 10.244.1.5 (Pod A)   ← Pod A가 죽으면? 연결 끊김

[Service 있음]
Client → 10.100.0.10 (Service ClusterIP) → 10.244.1.5 (Pod A)       ← Pod A가 죽어도 Service IP는 유지
                                          → 10.244.1.6 (Pod B)
                                          → 10.244.1.7 (Pod C)
                                          
```

Service는 파드 IP의 휘발성 문제를 해결하기 위해 **안정적인 가상 IP(ClusterIP)**와 **DNS 이름**을 제공한다. 클라이언트는 Service IP(또는 `my-service.default.svc.cluster.local` 같은 DNS)로만 요청하면 된다.

### Endpoints와 label selector

Service는 **label selector**로 백엔드 파드를 선택한다. `selector: app=nginx`를 지정하면, `app=nginx` 레이블을 가진 모든 파드가 이 Service의 백엔드가 된다.

쿠버네티스는 selector에 매칭되는 파드들의 실제 IP:Port 목록을 **Endpoints**(또는 **EndpointSlice**) 오브젝트에 기록한다. 파드가 생성되면 Endpoints에 추가되고, 죽으면 제거된다. Service 자체는 "어떤 파드를 선택할지"만 정의하고, 실제 IP:Port 매핑의 추적은 Endpoints가 담당한다.

```
Service (app=nginx, ClusterIP: 10.100.0.10)
  └→ Endpoints
       ├ 10.244.1.5:80  (Pod A - Running, Ready)
       ├ 10.244.1.6:80  (Pod B - Running, Ready)
       └ 10.244.1.7:80  (Pod C - Running, Ready)
```

### kube-proxy의 역할

**kube-proxy**는 모든 워커 노드에서 DaemonSet으로 동작하며, API 서버를 watch하면서 Service와 Endpoints의 변경을 감지한다. 변경이 생기면 각 노드의 커널에 네트워크 규칙(iptables/IPVS/nftables)을 생성·갱신하여, Service의 가상 IP로 들어오는 패킷을 실제 파드 IP로 변환(DNAT)하고 로드 밸런싱한다.

정리하면:

| 구성 요소 | 역할 |
|-----------|------|
| **Service** | 안정적인 가상 IP + DNS 이름 제공. label selector로 백엔드 정의 |
| **Endpoints** | selector에 매칭되는 파드의 실제 IP:Port 목록을 추적 |
| **kube-proxy** | Endpoints 변경을 watch → 각 노드 커널에 DNAT/로드밸런싱 규칙 설치 |

### 추상화 계층으로서의 Service

쿠버네티스 네트워킹 모델을 밑에서부터 쌓아 올려 보면, Service가 차지하는 위치가 명확해진다:

| 계층 | 해결하는 문제 | 핵심 메커니즘 | 결과 |
| --- | --- | --- | --- |
| **컨테이너 네트워킹** | 같은 파드 내 컨테이너 간 통신 | pause 컨테이너의 공유 네트워크 네임스페이스 | `localhost`로 통신 |
| **파드 네트워킹 (같은 노드)** | 같은 노드의 파드 간 통신 | veth pair + 브릿지 (L2 스위치) | 하나의 네트워크 세그먼트 |
| **파드 네트워킹 (다른 노드)** | 다른 노드의 파드 간 통신 | CNI 플러그인 (오버레이/BGP/클라우드 네이티브) | 모든 파드가 NAT 없이 직접 통신 가능한 **flat network** |
| **Service** | 파드 IP의 휘발성, 서비스 디스커버리 | kube-proxy + 가상 IP(ClusterIP) + Endpoints | 안정적인 접점 + 로드밸런싱 |

아래 세 계층이 **"모든 파드가 고유 IP로 직접 통신 가능한 flat network"**을 만든다. Service는 이 flat network을 **전제**로, 그 위에서 동작하는 추상화다. 순서를 뒤집으면 성립하지 않는다 — 문제 2(파드 간 통신)가 풀려야 DNAT 이후의 실제 파드 도달이 가능하다. kube-proxy가 ClusterIP를 파드 IP로 아무리 잘 변환해도, 그 파드 IP로 패킷이 도달할 수 있는 인프라가 없으면 Service는 동작하지 않는다. Service가 할 일은 "어떤 파드로 보낼지"를 결정하는 것뿐이고, "그 파드에 어떻게 도달할지"는 아래 계층이 이미 풀어 놓은 문제다.

이 계층 구조를 인식하면, Service의 가상 IP라는 설계도 자연스럽게 이해된다. Service는 인프라 계층이 아니라 추상화 계층이므로, 네트워크 인터페이스에 바인딩된 "실제" IP를 가질 이유가 없다. ClusterIP는 어떤 NIC에도 할당되지 않고, 라우팅 테이블에도 없다. 오직 커널의 netfilter 규칙 안에서만 존재하면서, 파드 IP라는 실체로의 매핑을 수행한다. 가상 IP인 것은 제약이 아니라 **추상화의 본질**이다 — 변하지 않는 접점을 제공하되, 실제 네트워크 토폴로지에는 관여하지 않는 것이다.

## 유형

Service 타입은 **어디에서 Service에 접근할 수 있느냐**를 결정한다. 세 가지 타입이 점진적으로 확장되는 구조다.

### ClusterIP

**클러스터 내부에서만** 접근 가능한 가상 IP를 할당한다. Service의 기본 타입이다.

ClusterIP는 어떤 노드의 인터페이스에도 바인딩되지 않는 가상 IP다. kube-proxy가 설정한 iptables/IPVS 규칙에 의해서만 의미를 갖는다. 클러스터 외부에서는 이 IP로 도달할 수 없다.

### NodePort

ClusterIP에 더해, **모든 노드의 특정 포트**(기본 30000-32767)를 열어 외부에서 접근할 수 있게 한다.

NodePort는 ClusterIP를 **포함**한다. NodePort Service를 만들면 ClusterIP도 자동으로 할당된다. 외부에서 `노드IP:NodePort`로 접근하면 kube-proxy 규칙이 실제 파드로 전달한다.

### LoadBalancer

NodePort에 더해, **외부 로드 밸런서**를 프로비저닝하여 단일 진입점을 제공한다.

LoadBalancer는 NodePort를 **포함**한다. 즉 **ClusterIP + NodePort + 외부 LB**라는 3계층 구조다. 클라우드 환경에서는 Cloud Controller Manager가 클라우드 API를 호출하여 로드 밸런서(AWS에서는 NLB/CLB)를 자동으로 생성하고, 노드의 NodePort로 트래픽을 전달한다.

### Service 타입과 네트워킹 문제의 관계

[첫 번째 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#쿠버네티스-네트워킹의-4가지-문제)의 문제 분류와 연결해 각 서비스 타입이 4가지 네트워킹 문제 중 어느 문제를 해결하는지 확인해 보자.

| Service 타입 | 해결하는 문제 |
| --- | --- |
| **ClusterIP** | 문제 3 (파드 ↔ 서비스): 클러스터 내부에서 안정적인 서비스 디스커버리 |
| **NodePort** | 문제 4 (외부 ↔ 서비스): 노드 포트를 통한 외부 접근 |
| **LoadBalancer** | 문제 4 (외부 ↔ 서비스): 외부 LB를 통한 단일 진입점 |

ClusterIP가 문제 3의 기본 해결이다. NodePort와 LoadBalancer는 문제 4(외부 접근)를 풀지만, 내부적으로 ClusterIP를 **포함**한다는 것이 핵심이다. 외부에서 `노드IP:NodePort`로 들어온 트래픽도 결국 ClusterIP의 DNAT 규칙을 거쳐 파드에 도달한다. 즉 문제 4의 해결은 문제 3(ClusterIP)이 기반이고, 문제 3의 DNAT 이후 마지막 홉에서는 문제 2(파드 간 통신)의 인프라 위에서 실제 파드에 도달한다. **문제 2 → 문제 3 → 문제 4**가 순서대로 쌓이는 계층 구조다.

<br>

# Service의 동작 원리

## ClusterIP는 가상 IP다

Service의 ClusterIP는 어떤 노드의 어떤 인터페이스에도 바인딩되지 않는 **가상 IP**다. 네트워크 인프라(온프레미스 라우터든, 클라우드 SDN이든)도 이 IP를 모르고, 라우팅 테이블에도 없다. 파드 IP는 CNI 플러그인이 네트워크 인터페이스에 실제로 할당한 IP이기 때문에 커널의 기본 라우팅만으로 도달 가능하지만, ClusterIP로 패킷을 보내면 커널은 이 IP를 모르므로 그대로 드롭한다.

이것이 바로 Service가 추상화 계층임을 보여주는 지점이다. 파드 IP는 인프라 계층에서 "실제로" 존재한다 — CNI가 네트워크 인터페이스에 할당하고, 커널 라우팅 테이블에 경로가 있고, flat network 어디서든 도달 가능하다. 반면 ClusterIP는 인프라 계층에 존재하지 않는다. 그 존재 근거는 오직 netfilter 규칙뿐이다. 인프라가 만든 flat network 위에서, 커널 규칙이라는 소프트웨어적 메커니즘만으로 "안정적인 접점"이라는 추상화를 구현하는 것이다.

## 커널에 규칙을 설치해야 한다

따라서 Service가 동작하려면 **누군가가 커널에 규칙을 설치해야 한다**. ClusterIP로 온 패킷을 실제 파드 IP로 바꾸는 DNAT 규칙, 리턴 경로를 보장하는 MASQUERADE 규칙, 외부 통신을 위한 SNAT 규칙 등 — 커널이 이 가상 IP를 인식하고 처리할 수 있도록 별도의 규칙을 설치해야 한다.

이 규칙을 설치하는 주체는 두 컴포넌트다: **kube-proxy**와 **CNI 플러그인**. 전체 네트워킹 인프라 관점에서 보면 두 컴포넌트의 목적이 뚜렷하게 나뉜다:

| 컴포넌트 | 목적 | 설치하는 규칙 |
|----------|------|-------------|
| **kube-proxy** | Service 추상화 — 가상 IP를 실제 파드 IP로 변환 | DNAT(ClusterIP → Pod IP), MASQUERADE(리턴 경로 보장) |
| **CNI 플러그인** | 파드 네트워크 통신 — 파드가 외부와 통신할 수 있게 함 | SNAT(Pod IP → Node IP, 외부 통신 시) |

kube-proxy는 Service라는 **상위 추상화 계층**의 규칙을, CNI는 **파드 네트워크 자체**의 규칙을 담당한다. 각각이 설치하는 규칙을 kubeadm 클러스터 기준으로 [이전에 정리한 적]({% post_url 2026-01-18-Kubernetes-Networking-Linux-Stack %})이 있다.

## kube-proxy가 설치하는 규칙

kube-proxy는 아래와 같은 역할을 한다: 

- **UDP, TCP, SCTP**를 프록시한다. HTTP를 이해하지 않는 L4 프록시다
- **로드 밸런싱**을 제공한다. Service 뒤의 여러 파드에 트래픽을 분산한다
- **Service에 대한 접근에만** 사용된다. 파드 간 직접 통신(문제 2)과는 무관하다

kube-proxy가 설치하는 규칙은 두 곳에 들어간다:

### PREROUTING / OUTPUT: DNAT

```
PREROUTING (외부/파드에서 들어오는 패킷)
  └→ KUBE-SERVICES
       └→ DNAT: Service ClusterIP:Port → Pod IP:Port

OUTPUT (노드 자체 프로세스가 Service에 접근할 때)
  └→ KUBE-SERVICES
       └→ DNAT: Service ClusterIP:Port → Pod IP:Port
```

패킷의 목적지를 Service의 가상 IP에서 실제 파드 IP로 바꾼다. PREROUTING은 외부나 파드에서 들어오는 패킷을, OUTPUT은 노드 자체 프로세스(kubelet 등)가 보내는 패킷을 처리한다.

### POSTROUTING: MASQUERADE

```
POSTROUTING
  └→ KUBE-POSTROUTING
       └→ mark 0x4000인 패킷만 → MASQUERADE (src IP를 노드 IP로 변경)
```

kube-proxy는 DNAT을 수행할 때 패킷에 마크(`0x4000`)를 찍는다. POSTROUTING에서 이 마크가 있는 패킷만 골라 MASQUERADE를 적용한다. 목적은 **DNAT된 Service 트래픽의 리턴 패킷이 반드시 DNAT을 수행한 노드로 돌아오도록** 소스 IP를 노드 IP로 바꾸는 것이다.

> 왜 리턴 경로를 보장해야 하는가? 파드 B가 응답을 보낼 때 dst는 원래 클라이언트 IP인데, 만약 src가 바뀌지 않았다면 응답이 DNAT을 수행한 노드를 거치지 않고 직접 클라이언트로 갈 수 있다. 그러면 클라이언트는 자신이 보낸 적 없는 IP(파드 IP)에서 응답을 받게 되어 TCP 연결이 깨진다.

## CNI 플러그인이 설치하는 규칙

CNI 플러그인(여기서는 AWS VPC CNI를 예시로)도 POSTROUTING에 규칙을 설치한다. 목적은 kube-proxy와 완전히 다르다.

### POSTROUTING: SNAT

```
POSTROUTING
  └→ AWS-SNAT-CHAIN-0
       └→ dest가 VPC CIDR 밖인 패킷 → SNAT (Pod IP → Node Primary IP)
```

파드가 **VPC CIDR 외부**(인터넷 등)로 통신할 때, Pod IP를 Node의 Primary IP로 변환한다. VPC 내부 통신에는 적용하지 않는다. 파드 IP가 VPC의 실제 IP이므로 VPC 안에서는 라우팅 가능하기 때문이다.

> `AWS_VPC_K8S_CNI_EXTERNALSNAT=true`로 설정하면 이 SNAT을 비활성화하고, 외부 NAT Gateway에게 맡길 수도 있다.

## POSTROUTING에서의 공존

kube-proxy와 CNI 플러그인 모두 POSTROUTING 체인에 규칙을 설치하지만, **매칭 조건이 다르므로 충돌하지 않는다**:

| 누가 | 체인 | 매칭 조건 | 동작 | 목적 |
| --- | --- | --- | --- | --- |
| kube-proxy | `KUBE-POSTROUTING` | mark `0x4000` 있는 패킷 | MASQUERADE | Service DNAT 리턴 경로 보장 |
| AWS VPC CNI | `AWS-SNAT-CHAIN-0` | dest가 VPC CIDR 밖 | SNAT → Node IP | 파드의 외부 통신 |

kube-proxy는 "DNAT했다"는 마크가 찍힌 패킷만, CNI는 "VPC 밖으로 나가는" 패킷만 각각 처리한다.

## "NAT 없이" 원칙과의 관계

여기서 의문이 생길 수 있다. 쿠버네티스 네트워킹 모델은 ["NAT 없이"]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#핵심-원칙-nat-없이)를 대원칙으로 내세우는데, kube-proxy의 DNAT과 MASQUERADE, CNI의 SNAT은 전부 NAT이 아닌가?

[첫 번째 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#원칙의-적용-범위)에서 정리했듯이, **위배되지 않는다**. "NAT 없이" 원칙은 **문제 2(파드 ↔ 파드 직접 통신 경로)**에만 적용된다.

- **kube-proxy의 DNAT/MASQUERADE**: Service는 파드 간 직접 통신 위에 얹히는 **상위 추상화 계층**이다. "파드 A가 파드 B의 IP로 직접 패킷을 보내는" 경로가 아니라, "파드 A가 Service의 가상 IP로 보내면 kube-proxy가 파드 B의 IP로 바꿔주는" 경로다. 계층이 다르다.
- **CNI의 외부 SNAT**: 파드가 클러스터 **외부**(인터넷)와 통신하는 것은 파드 ↔ 파드 직접 통신의 범위 **밖**이다.

파드 A가 파드 B의 IP를 직접 목적지로 지정하고 패킷을 보내면, 그 경로의 어느 지점에서도 IP가 변조되지 않는다. 이것이 "NAT 없이" 원칙이 보호하는 것이고, Service DNAT과 외부 SNAT은 이 경로와 다른 계층/범위에서 동작한다.

<br>

# kube-proxy 동작 모드

kube-proxy는 Service의 가상 IP를 실제 파드 IP로 변환하는 규칙을 관리한다. 이 규칙을 **어떤 메커니즘으로** 관리하느냐에 따라 동작 모드가 나뉜다. 역사적으로 userspace → iptables → IPVS → nftables → eBPF 순서로 발전해 왔다.

## userspace 모드

kube-proxy의 **최초 구현**(v1.0 기본값)이다. 이름 그대로 kube-proxy **프로세스가 직접 프록시 역할**을 했다. 현재는 사용되지 않지만, 이후 모드들이 왜 커널 기능을 사용하게 됐는지 이해하는 데 중요하다.

Service `10.96.0.100:80` → 백엔드 Pod `10.244.1.5:8080`으로 트래픽을 보내는 상황을 가정한다.

![userspace 모드]({{site.url}}/assets/images/eks-w2-kube-proxy-userspace-mode.png){: .align-center}

<center><sup>userspace 모드. 패킷이 커널↔유저 경계를 4번 넘는다.</sup></center>

userspace 모드에서는 iptables REDIRECT로 Service IP 트래픽을 kube-proxy의 로컬 포트로 전환하고, kube-proxy 프로세스가 직접 `recv()` → 백엔드 선택 → `connect()` + `send()`를 수행한다.

```
# 1) iptables가 Service IP 트래픽을 kube-proxy의 로컬 포트로 REDIRECT
iptables -t nat -A PREROUTING \
  -d 10.96.0.100 -p tcp --dport 80 \
  -j REDIRECT --to-port 34567

# 2) kube-proxy 프로세스가 :34567에서 listen
#    recv()로 패킷 수신 → 백엔드 선택 → 새 TCP 연결 생성
#    connect(10.244.1.5:8080) → send(data)
```

이 과정에서 패킷 데이터가 커널 버퍼(`sk_buff`)에서 kube-proxy의 userspace 버퍼로 복사되고, 다시 새 소켓을 통해 커널로 돌아간다. 패킷 하나당 **커널↔유저 경계를 4번** 넘는다.

### 성능 문제

| 문제 | 설명 |
|------|------|
| **Context switch** | 커널↔유저 전환마다 레지스터 저장/복원, TLB flush, 스택 전환이 발생한다. 1회에 ~1-5μs인데, 초당 수만 패킷이면 누적된다 |
| **Memory copy** | `recv()` 시 `sk_buff` → 유저 버퍼, `send()` 시 유저 버퍼 → `sk_buff`로 2번 복사한다. 커널 모드에서는 `sk_buff`의 헤더만 수정하면 되므로 복사가 없다 |
| **Double TCP state** | client→kube-proxy, kube-proxy→backend로 TCP 연결이 **2개** 필요하다. 핸드셰이크, 윈도우 관리, 타이머가 모두 2배다 |
| **SPOF** | kube-proxy 프로세스가 죽으면 **모든 Service 트래픽이 즉시 중단**된다. 프로세스가 패킷 경로 한가운데 있기 때문이다 |

Kubernetes 초기(2014~2015)에는 클러스터가 수십 노드·수백 파드 규모였고, 이 스케일에서는 userspace 프록시의 오버헤드가 체감되지 않았다. 설계 우선순위가 성능보다 정확성과 구현 단순성이었기 때문에, Go로 `net.Listener` + `net.Dial` 몇 줄이면 동작하는 가장 단순한 구현을 택한 것이다. Kubernetes가 급속히 성장하면서 성능 문제가 드러나자 커널 기반으로 전환했고, 이름만 "proxy"로 남았다.

## iptables 모드

커널 netfilter 서브시스템의 **iptables API**로 패킷 포워딩 규칙을 관리하는 모드다. v1.2부터 기본값이 되었고, EKS를 포함한 대부분의 쿠버네티스 클러스터에서 현재도 **기본값**으로 사용된다.

![커널 모드]({{site.url}}/assets/images/eks-w2-kube-proxy-kernel-mode.png){: .align-center}

<center><sup>iptables 모드(커널 모드). 패킷이 커널 메모리 안에서만 움직인다.</sup></center>

userspace 모드와의 핵심 차이는 kube-proxy가 **직접 프록시를 하지 않는다**는 것이다. kube-proxy는 netfilter 규칙만 설정하고, 실제 패킷 처리는 커널의 netfilter가 전부 담당한다.

```
# netfilter PREROUTING chain에서 바로 DNAT — userspace를 거치지 않는다
iptables -t nat -A PREROUTING \
  -d 10.96.0.100 -p tcp --dport 80 \
  -j DNAT --to-destination 10.244.1.5:8080
```

패킷의 dst IP 헤더가 커널 메모리(`sk_buff`) 안에서 직접 `10.96.0.100` → `10.244.1.5`로 바뀌고, 그대로 라우팅되어 파드에 도달한다. context switch도 memcpy도 없다.

- kube-proxy의 역할: iptables 규칙 생성·갱신 (규칙 관리)
- netfilter의 역할: 패킷 매칭 → DNAT 수행 (실제 패킷 처리)

kube-proxy가 죽어도 **이미 설정된 규칙은 커널에 남아 있으므로** 기존 Service 통신은 계속된다. 규칙 추가·삭제만 안 될 뿐이다. userspace 모드에서는 kube-proxy가 패킷 경로 한가운데에 있어서 죽으면 Service 통신이 전부 끊겼던 것(SPOF)과 대비된다.

<br>

![kube-proxy iptables 체인 구조]({{site.url}}/assets/images/kube-proxy-iptables-introduction.png){: .align-center}

<center><sup>iptables 모드의 체인 구조. KUBE-SERVICES → KUBE-SVC-* → KUBE-SEP-* → 실제 Pod IP(DNAT)로 체인을 순서대로 탐색한다. 출처: <a href="https://ssunghwan.tistory.com/64" target="_blank" rel="noopener noreferrer">하늘을 나는 펭귄 — 2 Week (2) - EKS Service</a>.</sup></center>

<br>

iptables 체인의 패킷 흐름을 정리하면:

1. 패킷이 노드에 들어오면(**PREROUTING**) 또는 로컬 프로세스가 보내면(**OUTPUT**), `KUBE-SERVICES` 체인으로 진입한다
2. `KUBE-SERVICES`에서 목적지 ClusterIP:Port를 매칭하여 해당 서비스의 `KUBE-SVC-*` 체인으로 분기한다
3. `KUBE-SVC-*` 체인에서 확률 기반으로 백엔드 파드를 선택한다 — **랜덤 로드 밸런싱**. 예를 들어 파드가 3개면 각각 1/3, 1/2, 1 확률로 iptables 규칙이 체이닝된다
4. 선택된 `KUBE-SEP-*` 체인에서 **DNAT**을 수행한다. 목적지 IP:Port를 실제 파드 IP:Port로 변환한다

**한계**: 서비스 수가 늘어나면 `KUBE-SERVICES` 체인이 길어진다. iptables는 규칙을 **선형 탐색(O(n))**하므로, 서비스가 수천 개를 넘어가면 성능이 저하된다. 또한 규칙을 업데이트할 때 **전체 테이블을 재작성**해야 한다.

## IPVS 모드

커널의 **IPVS(IP Virtual Server)**와 iptables API를 함께 사용하는 모드다. IPVS는 리눅스 커널에서 제공하는 L4 로드 밸런서로, netfilter 훅을 기반으로 하지만 **해시 테이블**을 사용하여 **커널 스페이스**에서 동작한다.

```
iptables: 선형 탐색 O(n) → 규칙이 많을수록 느려짐
IPVS:     해시 조회 O(1) → 규칙 수에 무관하게 일정한 성능
```

iptables 모드 대비 핵심 차이는:

- **조회 성능**: 해시 기반 O(1) 조회로, 서비스가 수천~수만 개여도 성능이 일정하다
- **업데이트 비용**: 전체 재작성 대신 **테이블 항목 단위**로 수정할 수 있다
- **다양한 LB 알고리즘**: iptables는 랜덤만 지원하는 반면, IPVS는 Round Robin(RR), Least Connection(LC), Source Hashing(SH) 등 **6가지 알고리즘**을 지원한다

IPVS 모드를 사용하려면 노드에 `ip_vs` 커널 모듈이 로드되어 있어야 한다. 모듈이 없으면 kube-proxy가 iptables 모드로 자동 폴백한다.

> **IPVS 모드 지원 중단 예정**: Kubernetes v1.35부터 kube-proxy의 [IPVS 모드 지원이 중단](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/#deprecation-of-ipvs-mode-in-kube-proxy)될 예정이다 ([KEP-5495](https://github.com/kubernetes/enhancements/issues/5495)). 대안으로 nftables 모드가 권장된다. [실습 환경 확인 편]({% post_url 2026-03-19-Kubernetes-EKS-02-02-01-Installation-Result %})에서도 확인한다.

## nftables 모드

커널 netfilter 서브시스템의 **nftables API**로 규칙을 관리하는 모드다. nftables는 iptables의 **후속 기술**이다.

> 커널 5.13 이상이 필요하다. Kubernetes 1.31 기준 아직 상대적으로 새로운 모드다.

nftables가 iptables를 대체하려는 이유는 명확하다:

- **셋(set) 기반 조회 O(1)**: iptables의 선형 탐색 대신 셋 자료구조를 사용한다
- **업데이트 효율**: 전체 재작성 없이 **셋 항목만 수정**하면 된다
- **API 통합**: iptables, ip6tables, arptables, ebtables가 각각 별도였던 것을 nftables 하나로 통합한다

iptables와 nftables의 관계를 짚으면, 둘 다 커널의 **netfilter** 서브시스템 위에서 동작한다. netfilter가 커널의 패킷 처리 프레임워크이고, iptables와 nftables는 이 프레임워크를 **제어하는 인터페이스(API)**다. nftables는 iptables보다 효율적인 방식으로 netfilter를 제어한다.

## eBPF 모드 (Cilium)

kube-proxy를 **완전히 대체**하는 방식이다. Cilium CNI가 eBPF(extended Berkeley Packet Filter) 프로그램을 커널에 로드하여, **netfilter/iptables 스택 자체를 우회**한다.

```
[iptables/IPVS/nftables 모드]
패킷 → netfilter 훅 → 규칙 매칭 → DNAT → 전달

[eBPF 모드 (Cilium)]
패킷 → XDP/TC 훅 → eBPF 맵 조회 → 직접 전달   ← netfilter 스택을 거치지 않음
```

eBPF 프로그램이 커널의 XDP(eXpress Data Path)나 TC(Traffic Control) 훅에 붙어서, 패킷이 네트워크 스택을 타기 **전에** 처리한다. netfilter 체인을 거치는 오버헤드가 없으므로 가장 높은 성능을 낸다. 맵(map) 기반 O(1) 조회를 사용하고, L7 정책 적용도 가능하다.

Cilium CNI + 커널 4.9 이상이 필요하다. kube-proxy를 아예 배포하지 않고(`--kube-proxy-replacement=true`) Cilium이 Service 구현을 전부 담당한다.

## 모드 비교 정리

| 항목 | userspace | iptables | IPVS | nftables | eBPF (Cilium) |
| --- | --- | --- | --- | --- | --- |
| **처리 위치** | kube-proxy 프로세스 | netfilter 훅 | netfilter + IPVS | netfilter nftables | XDP / TC (스택 우회) |
| **패킷 경로** | 커널↔유저 왕복 | 커널 내부에서 완결 | 커널 내부에서 완결 | 커널 내부에서 완결 | 커널 내부에서 완결 |
| **조회 방식** | 프로세스 내 선택 | 선형 탐색 O(n) | 해시 조회 O(1) | 셋 조회 O(1) | 맵 조회 O(1) |
| **업데이트 비용** | 없음 (런타임 선택) | 전체 재작성 | 테이블 항목 수정 | 셋 항목만 수정 | 맵 항목만 수정 |
| **LB 알고리즘** | Round Robin | 랜덤만 | RR, LC, SH 등 6종 | 랜덤 | 다양 + L7 가능 |
| **kube-proxy 필요** | 필요 (SPOF) | 필요 | 필요 | 필요 | **불필요** (대체) |
| **요구사항** | — | 기본 내장 | `ip_vs` 모듈 필요 | 커널 5.13+ | Cilium CNI + 커널 4.9+ |
| **상태** | **v1.0 기본 → 폐기** | 현재 기본값 | v1.35 deprecated | beta (v1.31+) | Cilium 전용 |

userspace → iptables로의 전환이 가장 근본적인 변화다. 프로세스가 패킷을 직접 처리하던 구조에서 커널이 처리하는 구조로 바뀌면서 성능과 안정성이 모두 해결됐다. 이후 iptables → IPVS → nftables → eBPF는 **커널 내부에서 어떤 자료구조와 API를 쓰느냐**의 차이다.

EKS 기본값은 **iptables**다. 서비스가 수천 개 이상이면 nftables 전환을 고려하고, 고성능 + L7 정책이 필요하면 Cilium eBPF를 검토한다.

<br>

# 네트워크 스택과 패킷 흐름

앞에서 Service의 개념과 네트워크 규칙을 다뤘다. 이제 이것들이 **노드의 네트워크 스택에서 실제로 어떻게 배치되고, 패킷이 어떤 경로를 타는지** 살펴본다.

## 단일 노드 네트워크 스택

먼저 한 노드 안에 어떤 레이어가 있고, 누가(kube-proxy, CNI) 어디에 규칙을 설치하는지 전체 그림을 잡는다.

![단일 노드 네트워크 스택]({{site.url}}/assets/images/kubernetes-networking-stack.png){: .align-center}

<center><sup>워커 노드의 네트워크 스택. User Space(파드/호스트 네임스페이스), Kernel Space(netfilter 체인), Device Driver, NIC Hardware로 구성된다.</sup></center>

### 구성 요소

| 레이어 | 요소 | 설명 |
| --- | --- | --- |
| User Space / Pod NS | Pod A, Pod B | pause + app 컨테이너. 각자 lo, eth0, IP를 가진다 |
| User Space / Pod NS | veth pair | Pod NS와 Host NS를 연결하는 가상 이더넷 케이블 |
| User Space / Host NS | veth-a, veth-b | veth pair의 호스트 측 끝 |
| User Space / Host NS | cni0 bridge | L2 스위치 역할 (Flannel/Calico bridge 모드). VPC CNI는 bridge 없이 호스트 라우트 사용 |
| User Space / Host NS | Local Processes | kubelet, kube-proxy, aws-node(CNI), sshd 등 |
| Kernel Space | PREROUTING | kube-proxy가 `KUBE-SERVICES` 점프 설치 (DNAT) |
| Kernel Space | ROUTING DECISION | dest IP 기반 분기: 노드 자체면 INPUT, 다른 곳이면 FORWARD |
| Kernel Space | INPUT | 노드 자체 수신 → Socket → local process |
| Kernel Space | OUTPUT | local process → Socket → kube-proxy `KUBE-SERVICES` 점프 (DNAT) |
| Kernel Space | FORWARD | 파드 트래픽 전달 (veth → veth 또는 veth → NIC) |
| Kernel Space | POSTROUTING | CNI: `AWS-SNAT-CHAIN-0`(외부 SNAT), kube-proxy: `KUBE-POSTROUTING`(Service MASQUERADE) |
| Kernel Space | Socket, TCP/UDP | 프로토콜 스택. INPUT ↔ Socket ↔ OUTPUT 경로 |
| Device Driver | eth0/ens5 | 물리/가상 NIC (192.168.1.10) |
| Hardware | NIC RX/TX | 패킷 수신/송신 하드웨어 |

### netfilter 체인과 규칙 설치자

핵심은 **누가 어떤 체인에 무엇을 설치하는가**다:

| 체인 | 설치자 | 규칙 | 설명 |
| --- | --- | --- | --- |
| **PREROUTING** | kube-proxy | `KUBE-SERVICES` → DNAT | Service ClusterIP → Pod IP 변환 |
| **OUTPUT** | kube-proxy | `KUBE-SERVICES` → DNAT | 노드 자체 프로세스가 Service 접근 시 |
| **POSTROUTING** | kube-proxy | `KUBE-POSTROUTING` → MASQUERADE | mark `0x4000` 패킷의 src IP를 노드 IP로 변환 |
| **POSTROUTING** | CNI (aws-node) | `AWS-SNAT-CHAIN-0` → SNAT | Pod IP → Node IP (외부 통신) |

### CNI 방식별 변형

위 다이어그램은 Flannel/Calico의 bridge 모드 기준이다. CNI에 따라 **Host Namespace 영역 — veth와 커널 사이의 연결 방식 — 이 달라진다**. Kernel Space 이하(netfilter 체인, Device Driver, NIC)는 동일하다.


<center><sup>CNI 방식별 Host Namespace 변형. bridge 모드(L2 스위치), VPC CNI(L3 호스트 라우트), Cilium(eBPF 훅)의 차이를 보여준다.</sup></center>

| CNI | Host NS 연결 방식 | 특징 |
| --- | --- | --- |
| **Flannel/Calico (bridge)** | veth들이 `cni0` bridge(L2 스위치)에 연결 | 같은 노드의 파드 간 통신이 bridge에서 바로 스위칭된다 |
| **VPC CNI** | bridge 없음. 각 veth에 대한 호스트 라우트(`/32 dev eniXXX`) + policy routing(`ip rule`) | 파드 IP가 VPC IP이므로 L3 라우팅으로 직접 연결 |
| **Cilium (eBPF)** | TC/XDP 훅이 veth에 부착. eBPF가 netfilter 일부를 바이패스 | netfilter 체인을 거치지 않고 eBPF에서 직접 패킷 처리 → 성능 향상 |

<br>

## ClusterIP 패킷 흐름

클러스터 내부 파드가 Service ClusterIP를 통해 다른 파드에 접근하는 경우다. VPC CNI 기준으로, **다른 노드에 있는 파드**로의 흐름을 설명한다.

<br>

![ClusterIP 패킷 흐름]({{site.url}}/assets/images/eks-w2-k8s-service-clusterip-packet-flow.png){: .align-center}

<center><sup>ClusterIP 패킷 흐름(크로스 노드). Node A의 Pod A가 ClusterIP를 통해 Node B의 Pod B에 접근한다. Node A에서 DNAT이 완료되고, Node B는 평범한 Pod IP 패킷을 수신하여 FORWARD로 전달한다.</sup></center>

<br>

**시작점은 NIC(RX)가 아니라 파드의 veth**다. ClusterIP는 클러스터 내부 접근이므로, 패킷이 외부에서 NIC로 들어오는 게 아니라 파드의 veth에서 호스트 네임스페이스로 진입한다. 커널 입장에서는 패킷이 물리 NIC(eth0)에서 오든 가상 인터페이스(veth-red)에서 오든 **그냥 "인터페이스에서 패킷이 도착했다"일 뿐**이다. 그래서 veth로 들어오는 트래픽도 NIC에서 들어오는 트래픽과 동일하게 PREROUTING부터 시작한다.



### Node A (송신 측)

| 단계 | 위치 | 동작 |
| --- | --- | --- |
| 1 | Pod A eth0 → veth-red | 파드가 `ClusterIP:port`로 패킷 전송. veth pair를 통해 호스트 NS 진입 |
| 2 | PREROUTING | veth에서 수신된 패킷. `KUBE-SERVICES` 체인에서 **DNAT**: `ClusterIP:port` → `PodB_IP:targetPort` |
| 3 | ROUTING DECISION | DNAT 후 dest가 Pod B IP로 변경됨. `local` 라우팅 테이블에 없으므로 `dest = other` → FORWARD |
| 4 | FORWARD | Pod B IP에 대한 라우트 조회. 다른 노드이므로 `default via GW` 매칭 → ENI 방향으로 전달 |
| 5 | POSTROUTING | `AWS-SNAT-CHAIN-0`: dest가 VPC CIDR 내부 → **RETURN**(SNAT 미적용). `KUBE-POSTROUTING`: mark `0x4000` 없음 → **RETURN**(MASQUERADE 미적용) |
| | NIC(TX) → VPC | 패킷이 ENI를 통해 VPC 라우팅 패브릭으로 전송. `src=PodA_IP`, `dst=PodB_IP` — 둘 다 VPC ENI 보조 IP이므로 캡슐화 없이 직접 전달 |

### Node B (수신 측)

Node A에서 DNAT이 이미 완료되었으므로, Node B에 도착하는 패킷은 `src=PodA_IP, dst=PodB_IP`인 **평범한 Pod-to-Pod 패킷**이다. ClusterIP의 흔적은 없다.

| 단계 | 위치 | 동작 |
| --- | --- | --- |
| 6 | NIC(RX) → PREROUTING | VPC로부터 패킷 수신. `KUBE-SERVICES` 체인 확인 — dst가 ClusterIP가 아니므로 매칭 없음. 그냥 통과 |
| 7 | ROUTING DECISION | `dest=PodB_IP`. 이 IP는 Pod의 네트워크 네임스페이스에 있지, 호스트의 `local` 테이블에는 없다. `dest = other` → FORWARD |
| 8 | FORWARD | 라우팅 테이블에서 `PodB_IP/32 dev veth-purple` (host route) 매칭 → veth-purple 방향으로 전달 |
| 9 | ROUTING DECISION | 출력 인터페이스 = veth-purple 결정 |
| 10 | POSTROUTING | `KUBE-POSTROUTING`: mark 없음 → RETURN. `AWS-SNAT-CHAIN-0`: VPC 내부 → RETURN. **SNAT 없음** |
| 11 | veth-purple → Pod B eth0 | veth pair를 통해 Pod B의 네트워크 네임스페이스로 진입. `src=PodA_IP, dst=PodB_IP` — 양쪽 모두 변경 없음 |

### Node B(수신 측)에서 INPUT이 아닌 FORWARD인 이유

Node B의 ROUTING DECISION(7단계)에서 `dest = self`인지 `dest = other`인지 판단하는 기준은 커널의 `local` 라우팅 테이블이다.

```bash
# Node B의 local 테이블
local 192.168.1.11 dev eth0 proto kernel scope host   # "self" — 노드 자신의 IP
local 127.0.0.1 dev lo proto kernel scope host        # "self"
# 10.244.1.3은 여기에 없다

# Node B의 메인 라우팅 테이블
10.244.1.3/32 dev veth-purple scope link              # 포워딩 경로일 뿐
```

Pod B의 IP(`10.244.1.3`)는 Pod B의 네트워크 네임스페이스 안에 있는 eth0에 할당되어 있다. Host 네임스페이스의 `local` 테이블에는 없으므로 커널은 `dest = other`로 판단한다. `/32 host route`는 "이 IP로 가려면 veth-purple로 보내라"는 포워딩 지시이지, "이 IP가 내 것이다"라는 선언이 아니다. 즉, **Node B는 이 패킷의 최종 목적지가 아니라 중간 라우터 역할**을 한다.

다이어그램에서 POSTROUTING(10단계) 이후 패킷이 NIC(TX)가 아닌 veth-purple(위쪽)로 올라가는 이유도 여기에 있다. netfilter 체인은 논리적 처리 순서이고, POSTROUTING 이후 패킷이 나가는 방향은 ROUTING DECISION에서 결정된 출력 인터페이스에 따른다. 출력 인터페이스가 eth0이면 아래로(NIC TX), veth-purple이면 위로(Pod B) 향한다.

### POSTROUTING에서 SNAT이 발생하지 않는 이유

POSTROUTING에는 kube-proxy와 CNI 플러그인이 각각 설치한 두 체인이 있다. 이 둘은 "나가는 쪽/들어오는 쪽"으로 나뉘는 게 아니라, **같은 POSTROUTING에서 하나의 패킷에 대해 순서대로 평가**된다. 매칭 조건이 다를 뿐이다:

| 체인 | 설치자 | 무엇을 보나 | 언제 SNAT/MASQUERADE 하나 |
| --- | --- | --- | --- |
| `KUBE-POSTROUTING` | kube-proxy | 패킷의 **mark** (`0x4000`) | Service DNAT 후 hairpin, NodePort `externalTrafficPolicy: Cluster` 등 |
| `AWS-SNAT-CHAIN-0` | CNI (aws-node) | 패킷의 **dest IP** (VPC CIDR 안/밖) | 파드가 VPC 밖(인터넷)으로 통신할 때 |

**kube-proxy — `KUBE-POSTROUTING`**: mark `0x4000`이 설정된 패킷만 MASQUERADE한다. 이 mark는 `KUBE-MARK-MASQ` 체인에서 설정되는데, ClusterIP의 경우 **hairpin**(Pod A가 자기 자신이 백엔드인 Service에 접근하는 경우)일 때만 mark가 찍힌다. 일반적인 Pod A → Service → Pod B(A≠B) 흐름에서는 mark가 없으므로 RETURN.

```
-A KUBE-POSTROUTING -m mark ! --mark 0x4000/0x4000 -j RETURN
-A KUBE-POSTROUTING -j MASQUERADE
```

**CNI 플러그인 — SNAT 체인**: CNI마다 체인 이름과 판단 기준은 다르지만, "클러스터 내부 트래픽이면 SNAT 안 한다"는 결과는 동일하다:

| CNI | POSTROUTING 규칙 | ClusterIP 크로스 노드에서의 동작 |
| --- | --- | --- |
| **VPC CNI** | `AWS-SNAT-CHAIN-0`: dest가 VPC CIDR 내부? | Pod IP = VPC IP → **RETURN** (SNAT 안 함) |
| **Flannel (VXLAN)** | `-s 10.244.0.0/16 ! -d 10.244.0.0/16 -j MASQUERADE` | dest가 Pod CIDR 안 → 규칙 매칭 안 됨 → **skip** |
| **Calico (BGP/IPIP)** | 유사 구조: dest가 Pod CIDR이면 MASQUERADE 제외 | Pod CIDR 내부 → **skip** |

이 두 체크는 **Node A(5단계)와 Node B(10단계) 모두**에서 일어난다. 어느 쪽에서든 SNAT/MASQUERADE가 적용되지 않으므로, 패킷의 src는 처음부터 끝까지 Pod A IP로 유지된다.


<br>

## NodePort 패킷 흐름

외부 클라이언트가 `NodeIP:NodePort`로 접근하는 경우다.

**ClusterIP와의 핵심 차이는 시작점**이다. ClusterIP는 veth에서 시작하지만, NodePort는 **NIC(RX)**에서 시작한다. 외부에서 노드 IP로 패킷이 들어오기 때문이다. 그리고 `externalTrafficPolicy` 설정에 따라 POSTROUTING에서 MASQUERADE 적용 여부가 달라진다.

![NodePort 패킷 흐름]({{site.url}}/assets/images/eks-w2-k8s-service-nodeport-packet-flow.png){: .align-center}

<center><sup>NodePort 패킷 흐름. 외부 클라이언트 → NIC(RX) → PREROUTING(DNAT) → ROUTING DECISION → 같은 노드(클라이언트 IP 보존) 또는 다른 노드(externalTrafficPolicy에 따라 분기).</sup></center>

| 단계 | 위치 | 동작 |
| --- | --- | --- |
| 1 | NIC(RX) → PREROUTING | 외부에서 `NodeIP:NodePort`로 도착. `KUBE-NODEPORTS`에서 **DNAT** |
| 2 | ROUTING DECISION | DNAT 후 dest가 Pod IP로 변경. 이 IP가 어디에 있는지 판단 |
| 3-A | FORWARD → veth | **이 노드에 Pod 있음**: host route → veth → Pod. SNAT 없음 → 클라이언트 IP 보존 |
| 3-B | FORWARD → POSTROUTING | **다른 노드에 Pod 있음**: FORWARD 후 POSTROUTING |
| 4 | POSTROUTING | `Cluster` 정책 → **MASQUERADE**(src=ClientIP → Node1IP). `Local` 정책 → 이 노드에 Pod 없으면 DROP |
| 5 | Pod | 수신. Case A: src=Client IP. Case B(Cluster): src=Node1 IP (*클라이언트 IP 손실*) |

### externalTrafficPolicy

`externalTrafficPolicy`는 NodePort/LoadBalancer에서 외부 트래픽이 다른 노드로 전달될 때의 동작을 결정한다:

| 정책 | 장점 | 단점 |
| --- | --- | --- |
| `Cluster` (기본) | 모든 노드가 트래픽 수용, 부하 분산 | 클라이언트 IP 손실(SNAT), 추가 홉 |
| `Local` | 클라이언트 IP 보존, 홉 감소 | Pod 없는 노드는 DROP, 불균등 분배 |

<br>

## LoadBalancer 패킷 흐름

LoadBalancer = **NodePort 앞에 외부 로드 밸런서를 추가**한 것이다. 로드 밸런서의 Target Mode에 따라 두 가지 경로가 나뉜다.

![LoadBalancer 패킷 흐름]({{site.url}}/assets/images/eks-w2-k8s-service-loadbalancer-packet-flow.png){: .align-center}

<center><sup>LoadBalancer 패킷 흐름. Instance Target Mode(NodePort 흐름과 동일)와 IP Target Mode(파드 직접 도달)의 비교.</sup></center>

### Instance Target Mode (기본)

LB가 **노드 IP:NodePort**로 트래픽을 보낸다. 노드에서의 처리는 **NodePort 흐름과 완전히 동일**하다. PREROUTING에서 DNAT하고, FORWARD를 거쳐 파드에 도달한다.

### IP Target Mode

VPC CNI + NLB 조합에서 사용 가능하다. LB가 **파드 IP:Port로 직접** 트래픽을 보낸다. 파드 IP가 VPC에서 라우팅 가능한 IP이므로, LB가 NodePort를 거치지 않고 파드에 직접 도달할 수 있다. NodePort → DNAT 단계를 **통째로 건너뛴다**.

| Mode | LB 목적지 | 노드에서의 처리 | 비고 |
| --- | --- | --- | --- |
| **Instance** (기본) | Node IP:NodePort | NodePort 흐름과 동일 (DNAT → FORWARD → ...) | 모든 CNI에서 사용 가능 |
| **IP** | Pod IP:Port 직접 | DNAT 불필요. PREROUTING → FORWARD → veth → Pod | VPC CNI + NLB. 파드 IP가 VPC에서 라우팅 가능하므로 직접 도달 |

> IP Target Mode는 VPC CNI의 "파드 IP = VPC IP" 특성을 활용한다. 이 구조의 세부 동작 — `externalTrafficPolicy` 설정, Pod Readiness Gate, 헬스 체크 등 — 은 EKS 서비스 실습에서 구체적으로 다룬다.

<br>

# 정리

이 글에서는 쿠버네티스 네트워킹의 **문제 3(파드 ↔ 서비스)**과 **문제 4(외부 ↔ 서비스)**를 다뤘다.

- **Service**:
    - 파드 IP의 휘발성을 해결하는 추상화 계층. label selector로 파드를 선택하고, Endpoints가 실제 IP:Port를 추적한다
    - 유형: ClusterIP(내부) → NodePort(노드 포트) → LoadBalancer(외부 LB)로 점진 확장

- **네트워크 규칙** (두 컴포넌트가 각각의 목적으로 설치):
    - kube-proxy(모든 워커 노드의 DaemonSet): Service 추상화 — DNAT(ClusterIP → Pod IP) + MASQUERADE(리턴 경로 보장)
    - CNI 플러그인: 파드 네트워크 — SNAT(파드의 외부 통신 시 Pod IP → Node IP)
    - 둘 다 POSTROUTING에 있지만 매칭 조건이 다르므로 충돌하지 않는다. "NAT 없이" 원칙에 위배되지 않는다

- **kube-proxy 모드**: userspace(초기, SPOF) → iptables(기본, 커널 DNAT) → IPVS(해시) → nftables(후속) → eBPF(스택 우회)
- **패킷 흐름**:
    - ClusterIP: veth → PREROUTING(DNAT) → FORWARD → veth(같은 노드) 또는 ENI(다른 노드)
    - NodePort: NIC(RX) → PREROUTING(DNAT) → FORWARD → Pod. `externalTrafficPolicy`에 따라 MASQUERADE 분기
    - LoadBalancer: Instance mode는 NodePort와 동일, IP target mode는 DNAT 없이 파드 직접 도달

돌아보면, 쿠버네티스 네트워킹은 **인프라 계층이 만든 flat network 위에 추상화 계층을 얹는 구조**다. 컨테이너 네트워킹(문제 1)과 파드 간 통신(문제 2)이 "모든 파드가 고유 IP로 NAT 없이 직접 통신할 수 있는" 평면 네트워크를 만들고, Service(문제 3, 4)가 그 위에서 안정적인 접점과 로드밸런싱이라는 추상화를 제공한다. 이 추상화 안에서 일어나는 DNAT과 MASQUERADE는 인프라 계층의 flat network을 훼손하지 않는다 — 파드 A가 파드 B의 IP로 직접 패킷을 보내면, 그 경로에서 IP는 여전히 변하지 않는다. Service를 거치는 경로에서만 가상 IP가 실제 파드 IP로 변환될 뿐이다. "NAT 없이" 원칙과 Service의 NAT은 서로 다른 계층에서 작동하기에 모순이 아니라 **역할 분담**이다.

여기까지 쿠버네티스 네트워킹 모델의 세 가지 문제를 개념 수준에서 정리했다. [다음 글]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %})부터는 EKS 환경에서 이 개념들이 어떻게 구현되는지 본격적으로 살펴본다.

<br>

# 참고 링크

- [Kubernetes Service 공식 문서](https://kubernetes.io/ko/docs/concepts/services-networking/service/)
- [Virtual IPs and Service Proxies](https://kubernetes.io/docs/reference/networking/virtual-ips/)
- [kube-proxy 공식 문서](https://kubernetes.io/docs/concepts/cluster-administration/proxies/)
- [하늘을 나는 펭귄 — 2 Week (2) - EKS Service](https://ssunghwan.tistory.com/64)
- [커피고래 - k8s network 02](https://coffeewhale.com/k8s/network/2019/05/11/k8s-network-02/)
- [Finda Tech - Kubernetes 네트워크 정리](https://medium.com/finda-tech/kubernetes-%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC-%EC%A0%95%EB%A6%AC-fccd4fd0ae6)
- [IPVS - Linux Virtual Server](http://www.linuxvirtualserver.org/software/ipvs.html)
- [nftables 프로젝트](https://netfilter.org/projects/nftables/)
- [iptables와 nftables의 관계 - Red Hat](https://developers.redhat.com/blog/2020/08/18/iptables-the-two-variants-and-their-relationship-with-nftables)

<br>