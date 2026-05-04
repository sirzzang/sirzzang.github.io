---
title:  "[EKS] EKS: Networking - 0. 쿠버네티스 네트워킹 모델"
excerpt: "EKS 네트워킹 시리즈를 시작하기 전에, AWS VPC CNI가 구현해야 하는 쿠버네티스 네트워킹 모델의 4가지 문제와 'NAT 없이' 원칙을 짧게 확인해 보자."
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
  - CNI
  - NAT
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

AWS VPC CNI를 본격적으로 파헤치기 전에, 먼저 모든 CNI 플러그인이 구현해야 하는 쿠버네티스 네트워킹 모델부터 짚고 간다. 모델 자체의 정의·증명은 [Kubernetes 네트워킹 모델]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %}) 글에 정리했고, 여기서는 EKS 맥락에서 그 모델이 왜 중요한지를 확인해 본다.

<br>

# TL;DR

- 쿠버네티스 네트워킹은 통신 범위에 따라 **4가지 문제**로 나뉜다: 컨테이너 간, 파드 간, 파드-서비스, 외부-서비스
- 핵심 원칙은 **"NAT 없이"** — 모든 파드가 고유 IP로 직접 통신할 수 있어야 한다 (flat network). 단, 이 원칙은 **파드 ↔ 파드 직접 통신(문제 2)** 경로에만 적용된다
- 파드 간 통신의 해결 방식은 셋: **오버레이 / BGP / 클라우드 네이티브 라우팅**. AWS VPC CNI는 클라우드 네이티브 방식이다
- 자세한 모델 정의·NAT 적용 범위 분석은 [Kubernetes 네트워킹 모델]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %}) 글에서 다룬다

<br>

# 들어가며

1주차에서 EKS 클러스터를 배포하고 내부 구조를 확인하면서, 이미 AWS VPC CNI의 흔적을 여러 번 만났다.

- [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}#vpc에-eni가-6개인-이유): 워커 노드마다 **VPC CNI Secondary ENI**가 생성되어 파드 IP 할당을 준비하고 있었다
- [엔드포인트 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %}#노드--api-서버-ss--tnp): `ss -tnp`에서 **aws-k8s-agent**(VPC CNI 에이전트)가 API 서버와 연결을 유지하며 ENI 관리와 IP 할당 정보를 동기화하고 있었다

2주차의 주제는 이 AWS VPC CNI를 비롯한 EKS 네트워킹을 본격적으로 파헤치는 것이다. 그런데 EKS 네트워킹의 핵심인 AWS VPC CNI가 "무엇을 해결하는지"를 이해하려면, 먼저 **쿠버네티스가 네트워킹에 대해 무엇을 요구하는지**를 알아야 한다. VPC CNI든 Flannel이든 Calico든, 모든 CNI 플러그인은 쿠버네티스의 네트워킹 모델이 정한 요구사항을 구현하는 것이기 때문이다.

이 모델의 정의·이론은 [Kubernetes 네트워킹 모델]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %}) 글에서 정리했다. 여기서는 EKS 시리즈 진행에 필요한 핵심만 한 화면 분량으로 추린다.

<br>

# 4가지 문제 한눈에 보기

쿠버네티스 공식 문서는 클러스터 네트워킹을 통신 범위에 따라 [4가지 문제](https://kubernetes.io/docs/concepts/cluster-administration/networking/)로 분류한다.

| # | 문제 | 해결 주체 | EKS에서 |
| --- | --- | --- | --- |
| 1 | **컨테이너 ↔ 컨테이너** (같은 파드 내) | pause 컨테이너 + 공유 네트워크 네임스페이스 + localhost | EKS도 동일 |
| 2 | **파드 ↔ 파드** (같은/다른 노드) | CNI 플러그인 | **AWS VPC CNI**가 담당 — 시리즈 후반의 주제 |
| 3 | **파드 ↔ 서비스** | kube-proxy (iptables/IPVS DNAT) | EKS도 동일하나 [VPC CNI Service](#) 글에서 LoadBalancer 통합 부분을 확장 |
| 4 | **외부 ↔ 서비스** | NodePort, LoadBalancer, Ingress | AWS Load Balancer Controller로 ALB/NLB와 통합 |

문제 2가 본 시리즈의 핵심이다. 문제 1·3·4의 자세한 내용과 각 항목의 상호 관계는 [Kubernetes 네트워킹 모델 — 4가지 문제]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %}#쿠버네티스-네트워킹의-4가지-문제) 절에서 확인할 수 있다.

<br>

# "NAT 없이" 원칙 — EKS 관점

쿠버네티스 [네트워킹 모델](https://kubernetes.io/docs/concepts/services-networking/#the-kubernetes-network-model)은 다음을 요구한다.

> All pods can communicate with all other pods, whether they are on the same node or on different nodes. Pods can communicate with each other directly, without the use of proxies or address translation (NAT).

핵심은 두 가지다.

1. **파드 ↔ 파드 직접 통신 경로의 어느 지점에서도 IP가 변조되면 안 된다** (SNAT/DNAT 모두 금지)
2. **이 원칙은 문제 2에만 적용된다** — 문제 3의 Service DNAT, 문제 4 영역의 외부 SNAT은 이 원칙과 다른 계층에서 동작하므로 위배가 아니다

이 원칙이 의미하는 "flat network"의 정의, 왜 이게 어려운 일인지, 그리고 NAT 적용 범위에 대한 자세한 분석은 [Kubernetes 네트워킹 모델 — "NAT 없이" 원칙]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %}#핵심-원칙-nat-없이) 절에 정리했다. 본 시리즈의 EKS 글들은 이 원칙을 전제로, AWS VPC CNI가 어떻게 이를 만족시키는지를 검증한다.

문제 2의 해결 방식은 셋이다.

- **오버레이** (Flannel VXLAN 등): 파드 패킷을 노드 IP로 캡슐화하여 터널링
- **BGP** (Calico BGP 모드): 라우팅 정보를 물리 네트워크에 직접 전파
- **클라우드 네이티브 라우팅** (**AWS VPC CNI**, GKE VPC-native, Azure CNI): 파드에게 인프라가 라우팅 가능한 IP를 부여

세 방식 모두 src/dst IP가 한 번도 변하지 않아 "NAT 없이"를 충족한다. 자세한 비교는 [파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#다른-노드의-파드-간-통신) 글에서 다룬다.

> AWS VPC CNI의 [설계 문서(Proposal)](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/cni-proposal.md)는 위 모델 요구사항에 더해, 파드 네트워킹이 EC2 수준의 처리량과 지연을 제공해야 하고, VPC Flow Logs/라우팅 정책/보안 그룹을 파드 트래픽에도 적용할 수 있어야 한다는 추가 목표를 정의한다. 이 시리즈에서 이 목표가 어떻게 달성되는지 살펴본다.

<br>

# 정리

| 항목 | EKS 시리즈에서의 위치 |
| --- | --- |
| 4가지 문제, "NAT 없이" 원칙의 정의·증명 | 별도 시리즈 [Ch0]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %}) |
| 파드 간 통신 3가지 방식 비교 | 별도 시리즈 [Ch1]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}) + EKS 시리즈 [02-00-01]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %}) |
| AWS VPC CNI = 클라우드 네이티브 라우팅의 구체 구현 | EKS 시리즈 [02-01-01]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}) |
| Service DNAT, kube-proxy | 별도 시리즈 [Ch4]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %}) + EKS 시리즈 [02-00-02]({% post_url 2026-03-19-Kubernetes-EKS-02-00-02-Kubernetes-Networking-Service %}) |
| EKS Service / LoadBalancer 통합| EKS 시리즈 02-01-02(예정) |

다음 글에서는 문제 2(파드 간 통신)의 세 해결 방식과 AWS VPC CNI가 "클라우드 네이티브"에 해당한다는 점을 짚고 넘어간다.

<br>
