---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 6. EKS Owned ENI 확인"
excerpt: "EKS 클러스터에 생성된 네트워크 인터페이스를 콘솔에서 확인하고, EKS Owned ENI의 정체를 파악해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - ENI
  - VPC
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

[EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#데이터-플레인)에서 데이터 플레인이 **EKS Owned ENI를 통해 컨트롤 플레인과 연결된다**고 했다. 이번 글에서는 그 ENI를 콘솔에서 **직접 식별**하고, 왜 그렇게 보이는지 확인한다.

- **EKS Owned ENI**: ENI 소유자는 내 계정, 연결된 인스턴스 소유자는 AWS EKS 서비스 계정 → **계정 불일치**가 핵심 식별 기준
- **역할**: 컨트롤 플레인이 kubelet에 명령(exec, logs 등)을 내리거나, 워커 노드가 API 서버에 접근할 때 이 ENI를 통해 **사설 네트워크로 통신**
- **연결 대상**: AWS 관리형 VPC의 **API 서버 EC2 인스턴스**에 cross-account로 연결됨 (NLB가 아님)
- **ENI 6개**: 워커 노드 2대 × (기본 ENI + VPC CNI 추가 ENI) + EKS Owned ENI 2개

<br>


# 들어가며

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에서 SSH로 워커 노드에 접속해 내부 구조를 확인했다. `ens5`(Primary ENI), `ens6`(Secondary ENI) 등 네트워크 인터페이스를 보았고, iptables에서 `default/kubernetes` Service의 백엔드 IP(`192.168.1.61`, `192.168.2.250`)가 컨트롤 플레인의 ENI IP라는 것도 확인했다.

그런데 이 ENI들은 정확히 **무엇**이고, **누구의 것**인가? [EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#데이터-플레인)에서 "EKS Owned ENI를 통해 컨트롤 플레인 영역과 연결된다"고만 언급했을 뿐, 실제로 확인해 본 적은 없다.

엔드포인트 액세스를 분석하기 전에, 먼저 VPC에 생성된 네트워크 인터페이스를 콘솔에서 확인하고, 컨트롤 플레인과 데이터 플레인을 잇는 EKS Owned ENI의 정체를 파악해 보자.

<br>


# EKS Owned ENI란

EKS 클러스터는 두 개의 VPC에 걸쳐 동작한다.

| VPC | 소유자 | 구성 요소 |
| --- | --- | --- |
| **AWS Managed VPC** | AWS EKS 서비스 | API 서버, etcd, 컨트롤러 등 컨트롤 플레인 |
| **Customer VPC** | 사용자 (내 계정) | 워커 노드, 파드, 서비스 등 데이터 플레인 |

이 두 VPC를 연결하는 것이 **EKS Owned ENI**(Cross-Account ENI, X-ENI)다. EKS가 클러스터 생성 시 사용자의 VPC 서브넷에 자동으로 생성하는 네트워크 인터페이스로, 한쪽 끝은 내 VPC에 있고 다른 쪽 끝은 AWS 관리형 VPC의 컨트롤 플레인 인스턴스에 연결된다.

이 ENI를 통해 다음과 같은 통신이 이루어진다.

| 방향 | 통신 내용 | 예시 |
| --- | --- | --- |
| **컨트롤 플레인 → 워커 노드** | API 서버가 kubelet에 명령 전달 | `kubectl exec`, `kubectl logs`, webhook 호출 |
| **워커 노드 → 컨트롤 플레인** | kubelet/kube-proxy가 API 서버에 접근 | 노드 등록, watch, 상태 보고 |

> **참고**: 워커 노드 → API 서버 통신 경로는 [엔드포인트 모드]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %})(Public/Private)에 따라 달라진다. Public-Public 구성에서는 워커 노드도 공인 경로를 사용하지만, Private 엔드포인트가 활성화되면 이 EKS Owned ENI를 통한 사설 경로를 사용한다. 컨트롤 플레인 → 워커 노드 방향은 항상 이 ENI를 사용한다.

<br>


# 콘솔에서 EKS Owned ENI 식별

AWS 콘솔의 EC2 > 네트워크 인터페이스에서 VPC에 생성된 모든 ENI를 확인할 수 있다. 여기서 EKS Owned ENI를 식별해 보자.

## EKS Owned ENI

VPC에 있는 네트워크 인터페이스 중 두 개가 눈에 띈다.

![eks-aws-owned-eni-1921681227]({{site.url}}/assets/images/eks-aws-owned-eni-1921681227.png){: .align-center}

<center><sup>192.168.1.227 IP를 가진 네트워크 인터페이스</sup></center>

![eks-aws-owned-eni-192168382]({{site.url}}/assets/images/eks-aws-owned-eni-192168382.png){: .align-center}

<center><sup>192.168.3.82 IP를 가진 네트워크 인터페이스</sup></center>

이 두 ENI의 공통점을 정리하면 다음과 같다.

| 필드 | 값 | 의미 |
| --- | --- | --- |
| **소유자** | 내 AWS 계정 ID | ENI가 내 VPC 서브넷에 있으므로 소유자는 나 |
| **연결된 인스턴스** | `-` (빈칸) | 연결된 인스턴스가 **다른 AWS 계정**에 있어서 내 콘솔에서 안 보임 |
| **인스턴스 소유자** | 내 계정과 **다른** AWS 계정 ID | 이 ENI가 실제로 연결(attach)된 인스턴스는 AWS EKS 서비스 계정 소유 |

**"소유자는 나인데, 인스턴스 소유자는 다른 계정"**이다. 여기서 나타나는 **계정 불일치**가 EKS Owned ENI의 핵심 특징이다.

일반 ENI라면 소유자와 연결된 인스턴스 소유자가 같은 계정이다. 계정이 다르다는 것 자체가 **"AWS EKS 서비스가 컨트롤 플레인 연결용으로 사용하는 ENI"**라는 증거다.

연결된 인스턴스가 빈칸으로 보이는 이유도 같은 맥락이다. 연결된 인스턴스가 **없는** 것이 아니라, **다른 계정**(AWS 관리형 VPC)에 있는 인스턴스라서 내 콘솔에서 볼 권한이 없을 뿐이다. "인스턴스 소유자" 필드에 다른 계정 ID가 찍혀 있는 것이 인스턴스가 존재한다는 증거다.

## 일반 ENI와 비교

같은 VPC에 있는 다른 네트워크 인터페이스를 보면 차이가 명확하다.

![eks-non-aws-owned-eni]({{site.url}}/assets/images/eks-non-aws-owned-eni.png){: .align-center}

<center><sup>일반 ENI — 워커 노드에 연결된 네트워크 인터페이스</sup></center>

| 필드 | EKS Owned ENI | 일반 ENI |
| --- | --- | --- |
| **소유자** | 내 계정 | 내 계정 |
| **연결된 인스턴스** | `-` (빈칸) | `i-0abc...` (인스턴스 ID 표시) |
| **인스턴스 소유자** | **다른 계정** (AWS EKS 서비스) | **내 계정** (동일) |
| **요청자 ID** | EKS 서비스 계정 ID | 없음 |

일반 ENI는 소유자와 인스턴스 소유자가 같고, 연결된 인스턴스를 따라가면 내 EC2 인스턴스(워커 노드)가 나온다. 계정 불일치가 없다.

<br>


# 요청자(Requester) 필드

EKS Owned ENI에는 **요청자(Requester) ID**가 찍혀 있고, 일반 ENI에는 없다. 이것은 AWS의 [Requester-Managed Network Interface](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/requester-managed-eni.html) 개념과 연결된다.

Requester-Managed ENI는 **AWS 서비스가 사용자의 VPC에 대신 생성한** 네트워크 인터페이스다. RDS 인스턴스, NAT 게이트웨이, VPC 엔드포인트 등이 생성하는 ENI도 같은 유형이다. EKS Owned ENI도 EKS 서비스가 컨트롤 플레인 연결을 위해 내 VPC에 생성한 것이므로 여기에 해당한다.

주요 특징은 아래와 같다:

- **요청자 ID(Requester ID)**: ENI를 생성한 서비스의 AWS 계정 ID 또는 별칭이 표시됨
- **수동 분리 불가**: 사용자가 임의로 detach할 수 없음. 연결된 리소스(EKS 클러스터)를 삭제해야 자동으로 정리됨
- **태그만 수정 가능**: 다른 속성(보안그룹, IP 등)은 서비스가 관리하므로 직접 변경 불가

EKS Owned ENI의 요청자 ID에 찍히는 계정은 AWS EKS 서비스 계정이다. 이 값이 인스턴스 소유자 필드의 계정 ID와 동일하다면, **같은 AWS 서비스 계정이 ENI를 생성하고 자신의 인스턴스에 연결한 것**이라는 의미가 된다.

<br>


# 연결된 인스턴스의 정체

콘솔에서 "인스턴스 소유자"에 다른 계정 ID가 찍혀 있으면, 그 인스턴스가 무엇인지 궁금해진다. EKS Owned ENI에 연결된 인스턴스는 AWS 관리형 VPC의 **API 서버 EC2 인스턴스**다.

[EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#컨트롤-플레인)에서 확인한 것처럼, EKS 컨트롤 플레인은 AWS 관리형 VPC에서 최소 2개의 API 서버와 3개의 etcd 인스턴스를 분산 배치한다. EKS Owned ENI는 이 API 서버 EC2 인스턴스에 cross-account로 연결된 것이다.

```
┌─ Customer VPC ─────────────────────┐    ┌─ AWS Managed VPC ──────────────┐
│                                    │    │                                │
│  Worker Node (EC2)                 │    │  API Server (EC2)              │
│   ├── ens5 (Primary ENI)           │    │   └── [cross-account attach]   │
│   ├── ens6 (CNI Secondary ENI)     │    │                                │
│   └── ...                          │    │  API Server (EC2)              │
│                                    │    │   └── [cross-account attach]   │
│  EKS Owned ENI ──────────────────────────── ↗                            │
│  (192.168.1.227)                   │    │                                │
│                                    │    │                                │
│  EKS Owned ENI ──────────────────────────── ↗                            │
│  (192.168.3.82)                    │    │                                │
│                                    │    │                                │
└────────────────────────────────────┘    └────────────────────────────────┘
```

외부 클라이언트(kubectl 등)가 API 서버에 접근하는 **공인 경로**는 이 ENI와 별개의 구성 요소를 통해 제공되며, [다음 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %})에서 상세히 분석한다.

<br>


# VPC에 ENI가 6개인 이유

실습 환경의 VPC에서 네트워크 인터페이스를 조회하면 총 6개가 보인다. 구성은 다음과 같다.

| ENI | 용도 | 개수 | 설명 |
| --- | --- | --- | --- |
| **워커 노드 Primary ENI** | 노드의 메인 네트워크 인터페이스 | 2 | 워커 노드 2대 × 1개. [이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %}#네트워크-인터페이스)의 `ens5` |
| **VPC CNI Secondary ENI** | 파드 IP 할당을 위한 추가 ENI | 2 | 워커 노드 2대 × 1개. [이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %}#네트워크-인터페이스)의 `ens6` |
| **EKS Owned ENI** | 컨트롤 플레인 연결 | 2 | 192.168.1.227, 192.168.3.82 |
| | | **합계 6** | |

VPC CNI가 생성하는 Secondary ENI는 **warm pool** 특성 때문에 존재한다. 파드가 아직 많지 않아도 VPC CNI는 미리 ENI를 추가로 확보해 두어, 파드 생성 시 IP 할당 지연 없이 즉시 할당할 수 있도록 한다. 이 warm pool 동작과 ENI당 IP 할당 구조(`maxPods: 17`의 근거)는 2주차에서 상세히 다룬다.

EKS Owned ENI는 일반적으로 **지정된 서브넷당 1개씩** 생성된다. 클러스터 생성 시 지정한 서브넷에 배치되며, 워커 노드 수와는 독립적이다. 워커 노드를 0대로 설정해도 EKS Owned ENI는 생성된다.

<br>


# EKS Owned ENI IP와 kubernetes Service 엔드포인트

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %}#iptables-분석)에서 iptables를 분석했을 때, `default/kubernetes` Service(10.100.0.1:443)의 백엔드 IP가 `192.168.1.61`과 `192.168.2.250`이었다.

```
kubernetes (API)  10.100.0.1:443  →  192.168.1.61, 192.168.2.250
```

이 백엔드 IP들은 **EKS Owned ENI의 프라이빗 IP**다. 워커 노드에서 `kubectl`이 아닌 kubelet이 API 서버와 통신할 때, Service IP(10.100.0.1)로 요청하면 iptables가 이 ENI IP 중 하나로 DNAT하는 것이다.

콘솔에서 확인한 EKS Owned ENI의 IP(192.168.1.227, 192.168.3.82)와 iptables 백엔드 IP(192.168.1.61, 192.168.2.250)가 **일치하지 않는** 것은, EKS가 서브넷 설정에 따라 여러 개의 cross-account ENI를 생성할 수 있고, 각 ENI가 프라이머리 IP 외에 보조 IP를 가질 수 있기 때문이다. 또한, 컨트롤 플레인 업데이트 시 [기존 ENI가 새 ENI로 교체](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html)되므로 시점에 따라 IP가 달라질 수 있다.

중요한 것은 이 IP들이 모두 **내 VPC CIDR 범위**(192.168.0.0/16) 안에 있다는 점이다. 컨트롤 플레인의 API 서버가 내 VPC의 사설 IP를 통해 도달 가능하다는 것이 EKS Owned ENI의 존재 이유다.

<br>


# 정리

| 항목 | 내용 |
| --- | --- |
| **EKS Owned ENI** | AWS EKS가 사용자 VPC 서브넷에 생성하는 cross-account ENI |
| **식별 기준** | ENI 소유자(내 계정) ≠ 인스턴스 소유자(AWS EKS 계정) → 계정 불일치 |
| **연결 대상** | AWS 관리형 VPC의 API 서버 EC2 인스턴스 (NLB 아님) |
| **요청자(Requester)** | EKS 서비스 계정. Requester-Managed ENI로 분류되어 수동 분리 불가 |
| **역할** | 컨트롤 플레인 ↔ 워커 노드 사설 네트워크 통신 경로 |
| **ENI 수** | 서브넷 설정에 따라 결정. 워커 노드 수와 독립적 |

[EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#데이터-플레인)에서 한 줄로 언급되었던 "EKS Owned ENI를 통해 컨트롤 플레인 영역과 연결된다"의 실체를 확인했다. 이 ENI가 존재하기 때문에 컨트롤 플레인과 데이터 플레인이 서로 다른 VPC에 있어도 사설 네트워크로 통신할 수 있다.

[다음 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %})에서는 이 사설 경로와 대비되는 **공인 엔드포인트 경로** — 외부 클라이언트와 워커 노드가 NLB를 통해 API 서버에 접근하는 구조 — 를 분석한다.

<br>
