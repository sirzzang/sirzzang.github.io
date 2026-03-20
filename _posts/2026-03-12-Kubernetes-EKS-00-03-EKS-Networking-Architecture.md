---
title:  "[EKS] EKS: 네트워킹 아키텍처 개요"
excerpt: "EKS에서 컨트롤 플레인과 데이터 플레인이 어떻게 통신하는지, AWS 네트워킹 기초와 EKS Owned ENI의 역할을 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - VPC
  - ENI
  - Networking
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **EKS 네트워킹 아키텍처의 핵심 구조**를 다룬다.

- **AWS 네트워킹 기초**: VPC, 서브넷, Internet Gateway, NAT Gateway, ENI
- **쿠버네티스 네트워킹**: 컨트롤 플레인 ↔ 노드 간 통신은 Hub-and-spoke 패턴으로, API 서버가 유일한 접점
- **EKS의 문제**: 컨트롤 플레인(AWS 관리 VPC)과 데이터 플레인(사용자 VPC)이 서로 다른 VPC, 심지어 다른 AWS 계정에 있음
- **해답 — EKS Owned ENI**: 사용자 VPC 서브넷에 존재하지만 AWS 컨트롤 플레인에 attach된 가상 네트워크 인터페이스. Cross-Account ENI Attachment와 AWS SDN으로 동작

<br>

# 들어가며

[EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %})에서 EKS 아키텍처의 큰 그림을 그렸다. 컨트롤 플레인은 **AWS Managed VPC**에서 관리형으로 동작하고, 데이터 플레인은 **사용자의 Custom VPC**에서 동작하며, 둘은 **EKS Owned ENI**를 통해 연결된다.

여기서 의문이 생긴다. 서로 다른 VPC에 있다는 건, 기본적으로 네트워크가 격리되어 있다는 뜻이다. 심지어 AWS 계정까지 다르다. 그런데 어떻게 컨트롤 플레인의 API 서버가 워커 노드의 kubelet과 통신하고, 워커 노드의 kubelet이 API 서버에 상태를 보고할 수 있을까?

이 글에서는 그 메커니즘을 개요 수준에서 정리한다. 먼저 아키텍처 그림을 읽는 데 필요한 AWS 네트워킹 기초 개념을 짚고, 쿠버네티스의 컨트롤 플레인 ↔ 노드 통신 구조를 확인한 뒤, EKS가 이를 어떻게 구현하는지 살펴본다.

<br>

# AWS 네트워킹 기초

EKS 네트워킹을 이해하려면, 먼저 아키텍처 그림에 등장하는 AWS 네트워킹 구성 요소들을 알아야 한다. AWS 네트워킹 전체를 다루는 것은 이 글의 범위를 벗어나므로, EKS 아키텍처를 읽는 데 필요한 최소한의 개념만 짚는다.

## VPC (Virtual Private Cloud)

VPC는 AWS 클라우드 안에서 **논리적으로 격리된 가상 네트워크**다. 온프레미스의 데이터센터 네트워크에 대응하는 개념으로, VPC를 만들 때 **CIDR 블록**(예: `192.168.0.0/16`)을 지정하여 사용할 IP 범위를 정의한다.

![AWS VPC 리소스 맵](/assets/images/aws-vpc-resource-map.png)
<center><sup>출처: <a href="https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html">How Amazon VPC works — Amazon VPC User Guide</a></sup></center>

위 그림은 AWS 콘솔의 VPC 리소스 맵이다. 하나의 VPC 안에 서브넷, 라우팅 테이블, Internet Gateway 등의 구성 요소가 어떻게 연결되는지 보여준다. [Terraform 코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#네트워크-구성)에서는 이 구조를 `vpc.tf`의 VPC 모듈로 정의했고, [배포 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#vpc)에서 실제 생성된 VPC를 콘솔에서 확인했다.

핵심은 **격리**다. VPC는 기본적으로 다른 VPC와 통신할 수 없다. 같은 AWS 계정 안에 있더라도, 별도 설정(VPC Peering, Transit Gateway 등) 없이는 서로 독립된 네트워크로 동작한다. 다른 AWS 계정의 VPC라면 격리 수준은 더 강해진다.

### EKS 아키텍처와의 연결

[EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %})에서 살펴본 것처럼, EKS 아키텍처에는 2개의 VPC가 등장한다.

| VPC | 소유자 | 역할 |
| --- | --- | --- |
| **AWS Managed VPC** | AWS 계정 | 컨트롤 플레인 (API Server, etcd 등) |
| **Custom VPC** | 사용자 계정 | 데이터 플레인 (워커 노드, 파드 등) |

두 VPC는 서로 다른 AWS 계정에 속해 있으므로, 기본적으로 통신이 불가능하다. 이 격리를 넘어서 통신을 가능하게 하는 것이 후술할 EKS Owned ENI다.

## 서브넷과 가용 영역

VPC의 IP 범위를 더 작은 블록으로 나눈 것이 **서브넷(Subnet)**이다. 각 서브넷은 하나의 **가용 영역(Availability Zone, AZ)**에 속한다. AZ는 AWS 리전 내의 물리적으로 분리된 데이터센터 그룹이다.

예를 들어 VPC CIDR이 `192.168.0.0/16`이면, 이를 AZ별로 나눌 수 있다.

| 서브넷 | AZ | CIDR |
| --- | --- | --- |
| Public Subnet 1 | ap-northeast-2a | `192.168.1.0/24` |
| Public Subnet 2 | ap-northeast-2b | `192.168.2.0/24` |
| Public Subnet 3 | ap-northeast-2c | `192.168.3.0/24` |

서브넷을 여러 AZ에 분산 배치하는 것은 **고가용성**을 위한 기본 설계다. 하나의 AZ에 장애가 발생하더라도 다른 AZ의 서브넷이 서비스를 계속할 수 있다. EKS 아키텍처 그림에서 컨트롤 플레인과 워커 노드가 모두 여러 AZ에 걸쳐 배치되는 것이 이 때문이다.

## Internet Gateway와 NAT Gateway

VPC를 생성하면 인터넷과 **완전히 격리된 상태**다. 인터넷과 통신하려면 별도의 게이트웨이를 연결해야 한다.

**Internet Gateway(IGW)**는 VPC와 인터넷 사이의 **양방향 관문**이다. VPC에 IGW를 부착하고, 서브넷의 라우팅 테이블에 `0.0.0.0/0 → IGW` 경로를 추가하면, 해당 서브넷의 리소스가 인터넷과 직접 통신할 수 있게 된다. 인터넷에서 들어오는 트래픽도, 인터넷으로 나가는 트래픽도 모두 IGW를 경유한다.

**NAT Gateway**는 **단방향 관문**이다. 프라이빗 서브넷의 리소스가 인터넷에 나가야 할 때(예: 소프트웨어 업데이트, ECR 이미지 풀) 사용한다. NAT Gateway 자체는 퍼블릭 서브넷에 위치하며, 프라이빗 서브넷의 라우팅 테이블에 `0.0.0.0/0 → NAT Gateway` 경로를 추가한다. 프라이빗 서브넷 → 인터넷 방향의 아웃바운드만 허용하고, 인터넷 → 프라이빗 서브넷 방향의 인바운드는 차단된다.

| | Internet Gateway | NAT Gateway |
| --- | --- | --- |
| **방향** | 양방향 (인바운드 + 아웃바운드) | 단방향 (아웃바운드만) |
| **위치** | VPC에 부착 | 퍼블릭 서브넷에 위치 |
| **용도** | 퍼블릭 서브넷의 리소스가 인터넷과 직접 통신 | 프라이빗 서브넷의 리소스가 인터넷에 나감 |
| **비유** | 데이터센터의 정문 (출입 모두 가능) | 데이터센터의 후문 (나가기만 가능) |

## 퍼블릭 서브넷 vs. 프라이빗 서브넷

서브넷은 **퍼블릭(Public)**과 **프라이빗(Private)** 두 종류로 나뉜다. 구분 기준은 서브넷의 **라우팅 테이블에 IGW로의 경로가 있는가**이다.

| 서브넷 유형 | 라우팅 테이블 | 인터넷 접근 |
| --- | --- | --- |
| **퍼블릭 서브넷** | `0.0.0.0/0 → IGW` 경로 있음 | 인터넷과 직접 양방향 통신 가능 (공인 IP 필요) |
| **프라이빗 서브넷** | `0.0.0.0/0 → NAT Gateway` 경로 (또는 경로 없음) | 아웃바운드만 가능 (NAT Gateway 경유) 또는 인터넷 접근 불가 |

정리하면, 퍼블릭/프라이빗의 구분은 서브넷 자체의 속성이 아니라 **라우팅 테이블이 트래픽을 어디로 보내는가**에 따라 결정된다.

![VPC with public/private subnets and NAT](/assets/images/aws-vpc-private-subnets-nat.png)
<center><sup>출처: <a href="https://docs.aws.amazon.com/vpc/latest/userguide/vpc-example-private-subnets-nat.html">Example: VPC with servers in private subnets and NAT — Amazon VPC User Guide</a></sup></center>

위 그림은 퍼블릭/프라이빗 서브넷이 모두 있는 VPC 구조를 보여준다. 퍼블릭 서브넷에는 NAT Gateway와 Application Load Balancer가 있고, 프라이빗 서브넷에는 서버(EC2 인스턴스)가 Auto Scaling Group으로 배치되어 있다. 프라이빗 서브넷의 서버가 인터넷에 나가야 할 때는 NAT Gateway를 경유하고, 외부에서 서버에 접근할 때는 Load Balancer를 경유한다.

## ENI (Elastic Network Interface)

ENI는 AWS에서 제공하는 **가상 네트워크 카드(virtual NIC)**다. 물리 서버의 네트워크 카드처럼, EC2 인스턴스 등 AWS 리소스에 부착되어 네트워크 연결을 제공한다. 다만 물리적 하드웨어가 아니라 **소프트웨어로 정의된 가상 인터페이스**다.

ENI에는 다음이 연결된다.

- 사설 IP 주소 (VPC CIDR 범위 내에서 할당)
- 보안그룹
- MAC 주소
- 선택적으로 공인 IP 주소

하나의 EC2 인스턴스에 여러 ENI를 부착할 수 있으며, ENI를 다른 인스턴스로 옮겨 붙일 수도 있다. 보안그룹의 경우에도 인스턴스가 아닌 ENI 수준에서 연결되기 때문에, 하나의 인스턴스에 부착된 ENI마다 서로 다른 보안그룹을 적용할 수 있다. 즉, ENI가 가상 방화벽의 부착 지점이 되는 셈이다.

## 정리

위 개념들을 하나의 그림으로 정리하면 다음과 같다.

```
                              Internet
                                 |
                              [  IGW  ]
                                 |
+--------------------------------+---------------------------------+
|                               VPC                                |
|                          (192.168.0.0/16)                        |
|                                                                  |
|   +--- AZ-a -------------------+  +--- AZ-b -------------------+ |
|   |                            |  |                            | |
|   | Public Subnet              |  | Public Subnet              | |
|   | (192.168.1.0/24)           |  | (192.168.2.0/24)           | |
|   |                            |  |                            | |
|   |   +--[EC2]--+   [NAT GW]   |  |   +--[EC2]--+   [NAT GW]   | |
|   |   | ENI     |       |      |  |   | ENI     |       |      | |
|   |   | - IP    |       |      |  |   | - IP    |       |      | |
|   |   | - SG    |       |      |  |   | - SG    |       |      | |
|   |   +---------+       |      |  |   +---------+       |      | |
|   +---------------------|------+  +---------------------|------+ |
|   +---------------------v------+  +---------------------v------+ |
|   |                            |  |                            | |
|   | Private Subnet             |  | Private Subnet             | |
|   | (192.168.3.0/24)           |  | (192.168.4.0/24)           | |
|   |                            |  |                            | |
|   |   +--[EC2]--+              |  |   +--[EC2]--+              | |
|   |   | ENI     |              |  |   | ENI     |              | |
|   |   | - IP    |              |  |   | - IP    |              | |
|   |   | - SG    |              |  |   | - SG    |              | |
|   |   +---------+              |  |   +---------+              | |
|   +----------------------------+  +----------------------------+ |
+-------------------------------------------------------------------+
```

VPC 안에 퍼블릭/프라이빗 서브넷이 AZ별로 존재한다. 퍼블릭 서브넷의 EC2 인스턴스는 IGW를 통해 인터넷과 양방향 통신하고, 같은 서브넷에 NAT Gateway가 위치한다. 프라이빗 서브넷의 EC2 인스턴스는 인터넷에 나갈 때 NAT Gateway를 경유한다. 모든 EC2 인스턴스는 ENI를 통해 네트워크에 연결된다. 이것이 EKS 아키텍처에서 사용자 VPC에 해당하는 기본 구조다.

<br>

# 쿠버네티스 네트워킹: 컨트롤 플레인 ↔ 노드 통신

AWS 네트워킹 기초를 짚었으니, 이제 쿠버네티스 자체의 통신 구조를 보자. [쿠버네티스 공식 문서](https://kubernetes.io/docs/concepts/architecture/control-plane-node-communication/)에 따르면, 컨트롤 플레인과 노드 간 통신은 두 방향으로 나뉜다.

## Node → Control Plane

쿠버네티스는 **Hub-and-spoke API 패턴**을 사용한다. 노드(또는 노드 위의 파드)에서 나가는 모든 API 요청은 **API 서버가 유일한 접점**이다. 다른 컨트롤 플레인 컴포넌트(etcd, scheduler, controller manager)는 외부에 서비스를 노출하지 않는다.

- kubelet이 API 서버에 노드 상태를 보고
- 파드가 API 서버에 접근 (ServiceAccount 토큰 사용)
- kube-proxy가 Service/Endpoint 정보를 watch

모두 **HTTPS(443)**를 통해 API 서버로만 향한다.

## Control Plane → Node

API 서버에서 노드로 향하는 통신 경로는 두 가지다.

**API 서버 → kubelet**

- `kubectl logs`로 파드 로그 조회
- `kubectl exec`로 파드에 접속
- `kubectl port-forward`로 포트 포워딩

이 기능들은 API 서버가 **각 노드의 kubelet HTTPS 엔드포인트(포트 10250)**에 직접 연결해야 동작한다.

**API 서버 → 노드/파드/서비스 (프록시)**

API 서버의 프록시 기능을 통해 노드, 파드, 서비스에 접근할 수 있다.

## 온프레미스에서는?

온프레미스 환경에서는 컨트롤 플레인과 워커 노드가 **같은 네트워크(또는 직접 라우팅 가능한 네트워크)**에 있었으므로, 이 통신이 자연스러웠다. API 서버와 kubelet이 서로의 IP로 직접 통신할 수 있었다.

하지만 EKS에서는 상황이 다르다. 컨트롤 플레인이 AWS의 별도 VPC에 있고, 워커 노드는 사용자 VPC에 있다. 앞서 살펴봤듯 **VPC 간에는 기본적으로 통신이 불가능**하다. 그러면 이 두 방향 통신을 EKS는 어떻게 구현할까?

<br>

# EKS 네트워킹 아키텍처

## 아키텍처 개요

![EKS 네트워킹 아키텍처 개요](/assets/images/eks-networking-architecture-overview.png)
<center><sup>출처: <a href="https://docs.aws.amazon.com/ko_kr/eks/latest/best-practices/control-plane.html">Amazon EKS Best Practices Guide — Control Plane</a></sup></center>

그림을 읽어 보자.

- **위쪽 — AWS VPC**: AWS가 관리하는 VPC다. API Server와 etcd가 2개 이상의 가용 영역에 걸쳐 고가용성으로 배치되어 있다.
- **아래쪽 — Your VPC**: 사용자가 소유한 VPC다. 워커 노드(kubelet, kube-proxy)가 가용 영역별로 분산 배치되어 있다.
- **보라색 아이콘 — EKS Owned ENI**: 각 가용 영역의 서브넷에 위치하며, 사용자 VPC와 AWS VPC를 연결하는 다리 역할을 한다. 워커 노드의 kubelet은 이 ENI를 통해 API 서버와 사설 통신을 한다.
- **오른쪽 — EKS Public Endpoint**: kubectl 같은 외부 클라이언트가 API 서버에 접근하는 공개 엔드포인트다. NLB(Network Load Balancer) 뒤에 API 서버가 위치한다.

이 그림에서 가장 중요한 것은, 두 VPC 사이를 잇는 **EKS Owned ENI**의 존재다.

## EKS Owned ENI

### 정의

EKS Owned ENI는 **사용자 VPC 서브넷에 존재하지만, AWS 컨트롤 플레인에 attach된 ENI**다.

앞서 ENI가 "소프트웨어로 정의된 가상 네트워크 카드"라고 했다. EKS Owned ENI도 일반 ENI와 물리적 형태는 같다. 다만, 일반적인 ENI가 같은 계정의 EC2 인스턴스에 붙는 것과 달리, EKS Owned ENI는 **내 계정의 서브넷에 생성되면서 AWS 계정의 컨트롤 플레인 인스턴스에 연결**된다는 점이 특별하다.

AWS 콘솔에서 확인하면 Owner(소유자) ID는 **사용자 자신의 AWS 계정 ID**로 표시된다. ENI가 사용자 VPC 서브넷에 생성되기 때문이다. 단, 이 ENI는 **requester-managed ENI**로, EKS 서비스가 요청해서 만든 것이라 사용자가 임의로 삭제하거나 수정할 수 없다.

### 동작 원리: Cross-Account ENI Attachment

EKS Owned ENI의 동작 원리를 단계별로 보면 다음과 같다.

**1. ENI 생성**

EKS 클러스터를 생성하면, AWS가 사용자 VPC의 서브넷 안에 ENI를 생성한다. 이 ENI는 사용자 VPC의 CIDR 범위에서 **사설 IP**를 받는다. 예를 들어 VPC CIDR이 `192.168.0.0/16`이고 서브넷이 `192.168.2.0/24`이면, ENI는 `192.168.2.185` 같은 IP를 받는다.

**2. Cross-Account Attachment**

이 ENI의 **소유자(Owner)는 사용자 AWS 계정**이지만, **연결 대상(Attachment)은 AWS 컨트롤 플레인 계정의 인스턴스**다. AWS 내부 네트워크 패브릭(SDN)을 통해, 이 ENI가 컨트롤 플레인 VPC의 API 서버 인스턴스에 연결된다.

**3. 사설 통신 경로 형성**

워커 노드 입장에서는, EKS Owned ENI가 **같은 VPC 안의 사설 IP**를 가지고 있으므로, 일반적인 VPC 내부 통신처럼 사설 IP로 접근할 수 있다. 실제로는 그 ENI 뒤에 AWS 컨트롤 플레인이 연결되어 있지만, 네트워크 레벨에서는 같은 서브넷 안의 통신으로 보인다.

```
+--- AWS Managed VPC (AWS Account) ----------+
|                                             |
|   [API Server] [API Server]                 |
|        |             |                      |
|   (AWS internal SDN fabric)                 |
+--------|-------------|----------------------+
         |             |
         | Cross-Account ENI Attachment
         |             |
+--------|-------------|----------------------+
|   +----+----+   +----+----+                 |
|   |EKS Owned|   |EKS Owned|                 |
|   |  ENI    |   |  ENI    |                 |
|   |192.168  |   |192.168  |                 |
|   | .1.x    |   | .2.x    |                 |
|   +----+----+   +----+----+                 |
|        |             |                      |
|   [Worker Node] [Worker Node]               |
|                                             |
+--- Your VPC (Your Account) ----------------+
```

이 구조 덕분에, [쿠버네티스 네트워킹](#쿠버네티스-네트워킹-컨트롤-플레인--노드-통신)에서 다룬 두 방향의 통신이 모두 가능해진다.

- **Node → Control Plane**: kubelet이 EKS Owned ENI의 사설 IP를 통해 API 서버에 HTTPS(443) 요청
- **Control Plane → Node**: API 서버가 EKS Owned ENI를 통해 kubelet의 HTTPS 엔드포인트(10250)에 접근

> **참고: SDN (Software Defined Network)**
>
> Cross-Account ENI Attachment가 가능한 이유는, AWS의 물리 서버들이 전부 **SDN(Software Defined Network)** 위에서 동작하기 때문이다. SDN은 하드웨어(스위치, 라우터)에 의존하지 않고 소프트웨어로 네트워크를 제어·구성하는 기술이다. AWS Nitro 시스템의 하이퍼바이저가 이를 처리하며, "내 계정의 ENI"를 "AWS 계정의 인스턴스"에 연결하는 것이 물리적 케이블 없이 가능하다. 지금 수준에서 자세한 내부 구현을 알 필요는 없고, **소프트웨어로 네트워크를 제어하기 때문에 계정 간·VPC 간 연결이 가능하다**는 점만 이해하면 된다.

### VirtualBox 가상 NIC와의 비교

EKS Owned ENI를 이해하기 어렵다면, VirtualBox의 가상 네트워크 카드를 떠올리면 도움이 된다.

VirtualBox에서 **Host-Only Adapter**나 **Bridge Adapter**를 만들면, 호스트 OS와 게스트 VM이 같은 네트워크에 있는 것처럼 통신할 수 있다. 물리 NIC 없이, 소프트웨어로 가상 네트워크 인터페이스를 만들어서 격리된 두 영역(호스트 ↔ 게스트)을 연결하는 것이다.

EKS Owned ENI도 본질은 같다. **소프트웨어로 가상 네트워크 인터페이스를 만들어서, 격리된 두 영역(사용자 VPC ↔ AWS 관리 VPC)을 연결한다.**

| | VirtualBox | EKS |
| --- | --- | --- |
| **가상 NIC** | 호스트 OS 안에 소프트웨어로 생성 | 사용자 VPC 서브넷 안에 소프트웨어로 생성 |
| **연결 대상** | 호스트 ↔ 게스트 VM | 사용자 VPC(워커 노드) ↔ AWS VPC(컨트롤 플레인) |
| **경계** | 같은 머신 안에서 OS 간 경계 | AWS 계정 간 경계 (Cross-Account) |
| **핵심** | 물리 NIC 없이 통신 가능 | 물리 케이블 없이 계정 간 통신 가능 |

차이점이 있다면, VirtualBox는 같은 물리 머신 안에서의 격리인 반면, AWS는 **완전히 별개의 계정·VPC 간 격리**를 넘는다는 점이다. 규모와 복잡도는 다르지만 원리의 본질은 같다.

### veth pair와의 비교

리눅스 네트워크 네임스페이스에서의 veth pair가 떠오를 수 있다. veth pair는 리눅스 커널 내부에서 두 네트워크 네임스페이스를 연결하는 가상 디바이스 쌍이다.

EKS Owned ENI는 veth pair가 아니라 실제 ENI(Elastic Network Interface)이며, 동작하는 레이어도 다르다. veth pair는 같은 호스트의 리눅스 커널 안에서 동작하고, EKS Owned ENI는 AWS SDN 위에서 계정·VPC 경계를 넘어 동작한다. 하지만 **"격리된 두 네트워크 영역을 잇는 다리"라는 역할은 같다.** veth pair가 두 네임스페이스를 이어 주듯, EKS Owned ENI는 사용자 VPC(데이터 플레인)와 AWS 관리 VPC(컨트롤 플레인)를 이어 준다.


| | veth pair | EKS Owned ENI |
| --- | --- | --- |
| **동작 레벨** | 리눅스 커널 (같은 호스트 내) | AWS SDN (계정·VPC 간) |
| **연결 대상** | 네트워크 네임스페이스 ↔ 네트워크 네임스페이스 | 사용자 VPC ↔ AWS 관리 VPC |
| **구현** | 커널이 패킷을 한쪽에서 다른 쪽으로 전달 | AWS SDN이 패킷을 올바른 목적지로 포워딩 |
| **공통점** | 격리된 두 네트워크 영역을 연결하는 가상 인터페이스 | 동일 |

> 참고로, EKS의 VPC CNI에서도 파드의 네트워크 네임스페이스와 호스트를 연결할 때 veth pair가 사용된다. ENI가 확보한 IP를 파드에 할당하는 과정에서, 실제 네임스페이스 간 연결은 veth pair가 담당한다.


<br>

# 결론

## 정리

| 항목 | 내용 |
| --- | --- |
| **문제** | 컨트롤 플레인(AWS VPC)과 데이터 플레인(사용자 VPC)이 서로 다른 VPC·계정에 격리 |
| **해답** | EKS Owned ENI — 사용자 VPC에 존재하면서 AWS 컨트롤 플레인에 attach된 가상 네트워크 인터페이스 |
| **동작 원리** | Cross-Account ENI Attachment + AWS SDN |
| **결과** | 워커 노드가 같은 VPC 안의 사설 IP로 통신하는 것처럼, 실제로는 컨트롤 플레인과 사설 통신 |
| **엔드포인트** | Public/Private 조합으로 외부 접근 경로와 내부 통신 경로가 달라짐 |

## 온프레미스와의 비교

| 관점 | 온프레미스 | EKS |
| --- | --- | --- |
| **CP-DP 네트워크** | 같은 네트워크(또는 직접 라우팅) | VPC 격리. EKS Owned ENI로 연결 |
| **API 서버 접근** | 직접 IP 또는 LB 경유 | NLB(Public Endpoint) 또는 ENI(Private Endpoint) |
| **네트워크 격리** | 물리 네트워크 세그먼트, VLAN | VPC 단위 격리 (AWS 계정 경계까지) |
| **통신 보안** | iptables, TLS 인증서 | 보안그룹(ENI 레벨) + TLS + 엔드포인트 모드 |

온프레미스에서는 컨트롤 플레인과 워커 노드가 같은 네트워크에 있어서 통신이 자연스러웠다. EKS에서는 관리형 서비스의 특성상 **네트워크 격리가 전제**이고, 이를 EKS Owned ENI라는 메커니즘으로 해결한다. "VPC가 다르면 기본적으로 통신 불가 → ENI로 다리를 놓는다"는 구조를 이해하면, 이후 보안그룹 아키텍처, 엔드포인트 모드별 네트워크 경로 분석 등을 더 깊이 있게 따라갈 수 있다.

## 앞으로

이 글에서는 EKS Owned ENI의 존재와 역할을 개괄적 수준에서 정리했다. 실제로 EKS Owned ENI가 어떻게 식별되는지, 어떤 보안그룹이 붙는지, dig로 확인하면 어떤 IP가 나오는지 — 이런 구체적인 확인은 실습을 통해 추후 직접 확인해 보자.

<br>
