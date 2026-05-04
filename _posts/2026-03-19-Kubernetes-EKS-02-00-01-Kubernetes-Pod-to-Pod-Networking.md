---
title:  "[EKS] EKS: Networking - 0. 쿠버네티스 네트워킹 모델 - 1. 파드 간 통신"
excerpt: "EKS 시리즈에서 AWS VPC CNI를 다루기 전에, 파드 간 통신을 푸는 세 가지 방식과 VPC CNI가 그중 어디에 해당하는지를 짧게 짚어 보자."
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
  - veth
  - bridge
  - overlay
  - BGP
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

AWS VPC CNI가 어떤 문제를 어떻게 푸는지 보기 전에, 먼저 일반적인 파드 간 통신이 어떻게 동작하는지부터 정리하고 간다. 같은 노드의 veth + bridge 구조, 다른 노드의 오버레이 / BGP / 클라우드 네이티브 라우팅 비교, 각 방식의 패킷 검증 같은 일반 쿠버네티스 영역은 [파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}) 글에 정리했다. 여기서는 그 결론을 짧게 추리고, AWS VPC CNI가 어느 칸에 들어가는지를 짚는다.

<br>

# TL;DR

- 파드 간 통신은 같은 노드 → 다른 노드 두 단계로 분해된다
  - 같은 노드: **veth pair**로 네임스페이스 벽을 관통하고 **브릿지(cni0)**가 L2 스위치 역할로 묶는다
  - 다른 노드: 물리 네트워크가 파드 IP를 모르는 것이 근본 문제. 해결책은 셋이다
- 다른 노드 통신을 푸는 세 가지 방식은 다음과 같다
  - **오버레이** (Flannel VXLAN, Calico IPIP): 파드 패킷을 노드 IP로 캡슐화해 터널링
  - **BGP** (Calico BGP 모드): 라우팅 정보를 물리 네트워크에 직접 전파
  - **클라우드 네이티브 라우팅** (**AWS VPC CNI**, GKE VPC-native, Azure CNI): 인프라가 라우팅 가능한 IP를 파드에 부여
- 세 방식 모두 src/dst IP가 한 번도 변하지 않아 "NAT 없이"를 충족한다 — **결과는 같고 방법이 다르다**
- 세 방식의 정의·노드 내부 구조·세 시나리오의 단계별 패킷 검증은 [Kubernetes 네트워킹 — 파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}) 글에 정리했다

<br>

# 들어가며

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %})에서 쿠버네티스 네트워킹의 4가지 문제와 ["NAT 없이"]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#nat-없이-원칙--eks-관점) 원칙을 짚었다. 이 원칙이 적용되는 핵심 영역이 **문제 2 — 파드 간 통신**이다. AWS VPC CNI를 본격적으로 분석하기 전에, 이 영역을 짧게 정리하고 가자.

<br>

# 같은 노드의 파드 간 통신 — 한 줄 정리

파드는 각자 자기 네트워크 네임스페이스를 가지므로, 같은 노드 안에서도 그대로는 서로 통신할 수 없다. CNI 플러그인은 두 가지 가상 인터페이스로 이 문제를 푼다.

| 구성 요소 | 역할 |
| --- | --- |
| **veth pair** | 파드 네임스페이스와 호스트 네임스페이스를 잇는 가상 케이블 — 파드의 `eth0`과 호스트의 `veth-xxx`가 한 쌍 |
| **브릿지 (`cni0`)** | 같은 노드의 모든 veth들을 묶는 L2 스위치. MAC 학습으로 프레임을 올바른 veth로 전달 |

```
파드 A(10.244.0.2) → veth → cni0 브릿지 → veth → 파드 B(10.244.0.3)
```

`cni0`이 같은 L2 세그먼트를 만들어주므로 src/dst IP가 변할 일이 없다 — NAT 없이. veth pair / cni0 / MAC 학습 / 패킷 흐름의 자세한 다이어그램은 [Kubernetes 네트워킹 — 같은 노드의 파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#같은-노드의-파드-간-통신) 절에서 확인할 수 있다.

<br>

# 다른 노드의 파드 간 통신 — 세 가지 해결 방식

같은 노드 안에서는 브릿지로 끝났지만, **노드 경계를 넘어가면 물리 네트워크가 파드 IP 대역을 모른다**는 근본적인 문제가 생긴다. 이 문제를 푸는 접근은 셋이다.

| 방식 | 핵심 발상 | 파드 IP 대역 | 캡슐화 | 대표 구현 |
| --- | --- | --- | --- | --- |
| **오버레이** | 물리 네트워크를 **우회** — 노드 IP로 감싸서 터널링 | 별도 대역 (`10.244.x.x`) | O (VXLAN, IPIP, Geneve) | Flannel(VXLAN), Calico(IPIP), Cilium(Geneve) |
| **BGP** | 물리 네트워크에 **알려줌** — 라우팅 정보를 BGP로 전파 | 별도 대역 (`10.244.x.x`) | X | Calico BGP 모드 |
| **클라우드 네이티브 라우팅** | 인프라가 **원래부터 앎** — 인프라가 라우팅 가능한 IP를 파드에 부여 | 인프라의 라우팅 도메인 IP (VPC 대역 등) | X | **AWS VPC CNI**, GKE VPC-native, Azure CNI |

세 방식 모두 src/dst IP가 한 번도 변하지 않아 "NAT 없이"를 충족한다. 자세한 패킷 검증·노드 내부 구조 비교·요구사항 충족 분석은 [Kubernetes 네트워킹 — 다른 노드의 파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#다른-노드의-파드-간-통신) 절에 정리했다. 오버레이의 캡슐화 디테일(VTEP, `onlink`, FDB)은 [CNI 동작 흐름]({% post_url 2026-03-19-Kubernetes-CNI-Flow %}) 글에서 다룬다.

<br>

# AWS VPC CNI는 어디에 위치하는가

위 표의 **클라우드 네이티브 라우팅** 칸이 AWS VPC CNI다. 그래서 노드 내부 구조도 오버레이/BGP와 다르다.

```
[오버레이 / BGP]
호스트 NIC (192.168.1.10)       ← 물리 네트워크가 아는 IP는 이것뿐
 └ cni0 브릿지
    ├ veth → Pod A (10.244.1.5)   ← 인프라가 모르는 대역
    └ veth → Pod B (10.244.1.6)   ← 물리 네트워크는 이 IP를 모름

[AWS VPC CNI]
호스트 ENI (192.168.1.10)
 ├ 보조 IP: 192.168.1.11 → Pod A에 할당   ← VPC가 라우팅 가능한 IP
 ├ 보조 IP: 192.168.1.12 → Pod B에 할당
 └ VPC가 이 IP들을 다 알고 있음
```

1주차에서 확인했던 [VPC CNI Secondary ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}#vpc에-eni가-6개인-이유)와 [aws-k8s-agent]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %}#노드--api-서버-ss--tnp)는 바로 이 메커니즘의 구성 요소였다. ENI에 보조 IP를 추가하고 파드에 할당하는 방식으로, VPC 패브릭이 파드 IP를 1급 시민으로 라우팅한다.

여기까지가 세 방식의 분류와 위치 짚기다. AWS VPC CNI가 보조 IP를 어떻게 관리하는지(`ipamd`, 웜 풀, max-pods 계산) — 다시 말해 클라우드 네이티브 방식의 **구체 구현** — 는 [AWS VPC CNI — IP 관리]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}) 글에서 다룬다.

<br>

# 정리

| 항목 | EKS 시리즈에서의 위치 |
| --- | --- |
| 같은 노드: veth + cni0 + MAC 학습의 디테일 | 별도 시리즈 [Ch1 — 같은 노드]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#같은-노드의-파드-간-통신) |
| 다른 노드: 오버레이 / BGP / 클라우드 네이티브 비교, 단계별 패킷 검증 | 별도 시리즈 [Ch1 — 다른 노드]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#다른-노드의-파드-간-통신) |
| 오버레이 캡슐화의 디테일 (VTEP, `onlink`, FDB) | 별도 시리즈 [Ch3 — CNI 동작 흐름]({% post_url 2026-03-19-Kubernetes-CNI-Flow %}) |
| AWS VPC CNI = 클라우드 네이티브 라우팅의 구체 구현 | EKS 시리즈 [02-01-01]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}) |

[다음 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-02-Kubernetes-Networking-Service %})에서는 쿠버네티스 네트워킹의 문제 3 — Service와 kube-proxy의 동작을 정리한다.

<br>
