---
title:  "[EKS] EKS: Networking - 0. 쿠버네티스 네트워킹 모델 - 2. Service와 kube-proxy"
excerpt: "EKS 시리즈에서 LoadBalancer Controller를 다루기 전에, Service / kube-proxy / LoadBalancer Instance vs IP Target Mode를 짧게 정리해 보자."
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

EKS의 LoadBalancer 통합을 보기 전에, 먼저 쿠버네티스의 Service 추상화가 어떻게 동작하는지부터 정리하고 간다. Service 정의·Endpoints·kube-proxy 모드(iptables/IPVS/nftables/eBPF) 비교·ClusterIP/NodePort/LoadBalancer 패킷 흐름 같은 일반 쿠버네티스 영역은 [Service와 kube-proxy]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}) 글에 정리했다. 여기서는 그 결론을 짧게 추리고, **AWS LoadBalancer의 Instance Mode vs IP Target Mode** 차이를 한 번 더 짚는다.

<br>

# TL;DR

- **Service**: 파드 IP의 휘발성을 해결하는 추상화 계층. label selector + Endpoints/EndpointSlice
- **kube-proxy**: 모든 워커 노드의 DaemonSet. Endpoints 변경을 watch해 커널에 DNAT/로드밸런싱 규칙 설치 — iptables / IPVS / nftables / eBPF 모드 중 하나
- 두 종류의 NAT가 같은 POSTROUTING에서 공존하지만 매칭 조건이 달라 충돌하지 않는다 — kube-proxy의 **Service DNAT/MASQUERADE**는 추상화 계층, CNI의 **외부 통신 SNAT**은 인프라 계층. "NAT 없이" 원칙과 모순 아님
- LoadBalancer 두 모드 (EKS 핵심):
  - **Instance Mode** — LB가 `Node IP:NodePort`로 보냄 → NodePort 흐름과 동일 (DNAT, FORWARD, ...)
  - **IP Target Mode** — VPC CNI + NLB 조합. LB가 `Pod IP:Port`로 직접 보냄 → DNAT 단계 통째로 건너뜀
- 자세한 모드 비교·패킷 흐름 검증·`externalTrafficPolicy` 분석은 [Kubernetes 네트워킹 — Service와 kube-proxy]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}) 글에 정리

<br>

# 들어가며

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %})에서 **문제 2 — 파드 간 통신**을 다뤘다. 같은 노드에서는 veth + 브릿지로, 다른 노드에서는 오버레이/BGP/클라우드 네이티브 라우팅 중 하나로 NAT 없이 파드 간 직접 통신을 구현했다. 그렇게 만든 **flat network 위에**, Service라는 추상화 계층이 얹혀 **문제 3 — 파드 ↔ 서비스**와 **문제 4 — 외부 ↔ 서비스**를 푼다.

여기서는 EKS 시리즈에 필요한 만큼만 정리하고, EKS-specific 포인트인 **LoadBalancer 두 모드**는 한 번 더 짚는다.

<br>

# Service / kube-proxy 핵심만

## 추상화 계층

| 개념 | 역할 |
| --- | --- |
| **Service** | 파드 집합에 대한 안정적인 네트워크 접점 (`ClusterIP`라는 가상 IP + DNS). label selector로 파드 매칭 |
| **Endpoints / EndpointSlice** | Service가 가리키는 실제 `Pod IP:Port` 매핑. 파드 변경을 따라간다 |
| **kube-proxy** | 모든 워커 노드의 DaemonSet. Endpoints 변경을 watch → 커널 DNAT 규칙 설치 |

> 자세한 정의·Service 유형 비교·Endpoints/EndpointSlice 차이는 [Kubernetes 네트워킹 — Service]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#service) 절에서 다룬다.

<br>

## kube-proxy 모드 한눈에 보기

| 모드 | 동작 위치 | 룩업 | 비고 |
| --- | --- | --- | --- |
| **userspace** (deprecated) | 사용자 공간 프로세스 | O(N) | 초기. SPOF, 컨텍스트 스위칭 비용 |
| **iptables** (기본) | 커널 netfilter | O(N) | 가장 보편적. 룰 개수 많아지면 매칭 비용 증가 |
| **IPVS** (deprecated, v1.35) | 커널 IPVS | O(1) (해시) | 대규모 클러스터용. v1.35에서 deprecated |
| **nftables** | 커널 nftables | O(1) | iptables 후속 표준 |
| **eBPF** | 커널 eBPF | O(1) | Cilium, kube-proxy 자체 대체. Linux 4.19+ / 5.10+ 권장 |

> 모드별 정확한 배경·deprecation 시점·커널 버전 요건은 [Kubernetes 네트워킹 — kube-proxy 동작 모드]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#kube-proxy-동작-모드) 절에서 다룬다. EKS는 기본적으로 iptables 모드로 동작한다.

<br>

## 두 종류의 NAT — 충돌하지 않는 이유

같은 POSTROUTING 체인에 두 종류의 NAT 규칙이 공존한다.

| 컴포넌트 | NAT | 매칭 조건 | 목적 |
| --- | --- | --- | --- |
| **kube-proxy** | DNAT (ClusterIP → Pod IP) + MASQUERADE | Service ClusterIP로 들어오는 패킷 | Service 추상화 |
| **CNI 플러그인** | SNAT/MASQUERADE (Pod IP → Node IP) | 파드 → 클러스터 외부로 나가는 패킷 | 파드 외부 통신 |

매칭 조건이 다르므로 한 패킷이 두 규칙에 동시에 걸리지 않는다. 이 두 NAT은 ["NAT 없이"]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#nat-없이-원칙--eks-관점) 원칙에 **위배되지 않는다** — 그 원칙은 파드 ↔ 파드 직접 통신 경로(인프라 계층)에 한정되고, Service DNAT은 그 위의 추상화 계층, 외부 SNAT은 그 범위 밖이기 때문이다.

> 자세한 분석은 [Kubernetes 네트워킹 — POSTROUTING에서의 공존]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#postrouting에서의-공존) 절에서 다룬다.

<br>

# LoadBalancer — Instance Mode vs IP Target Mode

EKS 시리즈에서 가장 중요한 부분이다. 외부 LB가 클러스터로 트래픽을 보내는 방식이 두 가지다.

| Mode | LB 목적지 | 노드에서의 처리 | CNI 요건 |
| --- | --- | --- | --- |
| **Instance** (기본) | `Node IP:NodePort` | NodePort 흐름과 동일 — `PREROUTING(DNAT)` → `FORWARD` → veth → Pod | 모든 CNI에서 사용 가능 |
| **IP** | `Pod IP:Port` 직접 | `DNAT` 단계 **불필요**. `PREROUTING` → `FORWARD` → veth → Pod | **VPC CNI + NLB** (또는 ALB IP target). 파드 IP가 VPC에서 라우팅 가능해야 함 |

IP Target Mode는 [클라우드 네이티브 라우팅]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %}#aws-vpc-cni는-어디에-위치하는가)이라는 VPC CNI의 특성을 가장 직접적으로 활용한다. 파드 IP가 VPC IP이므로 LB가 노드를 거치지 않고 파드에 바로 도달할 수 있다. NodePort/`externalTrafficPolicy` 우회·홉 감소·헬스 체크 단순화 등 여러 이점이 있다.

> Instance Mode와 IP Target Mode의 패킷 흐름 다이어그램·`externalTrafficPolicy: Local`/`Cluster` 차이·SNAT 발생 여부 검증은 [Kubernetes 네트워킹 — LoadBalancer 패킷 흐름]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#loadbalancer-패킷-흐름) 절에 정리했다. EKS의 Pod Readiness Gate, AWS Load Balancer Controller 통합, 헬스 체크 동작 등 EKS-specific 디테일은 EKS Service(예정) 글에서 다룰 예정이다.

<br>

# 정리

| 항목 | EKS 시리즈에서의 위치 |
| --- | --- |
| Service / Endpoints / 추상화 정의 | 별도 시리즈 [Ch4 — Service]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#service) |
| kube-proxy 모드 비교 (iptables/IPVS/nftables/eBPF) | 별도 시리즈 [Ch4 — kube-proxy 동작 모드]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#kube-proxy-동작-모드) |
| ClusterIP / NodePort 패킷 흐름 검증 | 별도 시리즈 [Ch4 — 네트워크 스택과 패킷 흐름]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#네트워크-스택과-패킷-흐름) |
| LoadBalancer Instance vs IP Target Mode | 본 글 + [Ch4 — LoadBalancer 패킷 흐름]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}#loadbalancer-패킷-흐름) |
| EKS LoadBalancer Controller, Pod Readiness Gate, ALB/NLB 통합 | EKS 시리즈 [02-01-02](예정) |

[다음 글]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %})부터는 EKS 환경에서 이 개념들이 어떻게 구현되는지 — AWS VPC CNI의 IP 관리부터 — 본격적으로 살펴본다.

<br>
