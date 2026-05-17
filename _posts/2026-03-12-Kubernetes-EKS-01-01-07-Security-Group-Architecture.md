---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 7. 보안그룹 아키텍처"
excerpt: "EKS 클러스터에 생성된 보안그룹을 분석하고, 컨트롤 플레인과 데이터 플레인의 통신 구조를 이해해보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - Security-Group
  - VPC
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

[배포 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#보안그룹)에서 워커 노드에 연결된 보안그룹 2개를 콘솔로 간단히 확인했다. 이번 글에서는 `aws ec2 describe-security-groups`로 **VPC 안의 보안그룹 전체를 조회**하고, 각 규칙이 어떤 통신을 허용하는지 분석한다.

- 보안그룹은 총 **5개**: VPC 기본 1개, EKS 모듈 생성 2개, EKS 자동 생성 1개, Terraform 직접 정의 1개
- **컨트롤 플레인 → 노드** 통신에 열려 있는 포트와 그 이유
- **노드 ↔ 노드** 통신에 필요한 포트 (CoreDNS, ephemeral ports)
- FromPort/ToPort, IpPermissions/IpPermissionsEgress의 의미

<br>

# 보안그룹 기본 개념

## 보안그룹이란

AWS 보안그룹(Security Group)은 **ENI(Elastic Network Interface) 수준의 가상 방화벽**이다. EC2 인스턴스, EKS 노드, RDS, Lambda(VPC 모드) 등 ENI가 붙는 모든 리소스에 적용된다.

<!-- TODO: 온프레미스 방화벽/iptables와의 비교 한 줄 -->

핵심 특성:

| 특성 | 설명 |
| --- | --- |
| **허용 규칙만** | 거부(deny) 규칙은 없다. 매칭되지 않으면 자동 차단 |
| **상태 저장(Stateful)** | 인바운드로 허용된 요청의 응답 트래픽은 아웃바운드 규칙 없이도 자동 허용 |
| **ENI 단위** | 하나의 인스턴스에 여러 보안그룹 부착 가능. 규칙은 **합집합(OR)** |
| **소스/대상에 SG 지정 가능** | CIDR 대신 다른 보안그룹 ID를 소스로 지정하면, 해당 SG가 붙은 모든 ENI에서 오는 트래픽을 허용 |

## AWS API 필드 읽는 법

`aws ec2 describe-security-groups` 출력의 핵심 필드:

| 필드 | 의미 |
| --- | --- |
| `IpPermissions` | **인바운드(Ingress)** 규칙 |
| `IpPermissionsEgress` | **아웃바운드(Egress)** 규칙 |
| `IpProtocol` | 프로토콜. `"-1"`은 **모든 프로토콜** |
| `FromPort` / `ToPort` | **대상 포트 범위**. "어디서 온" 포트가 아니라, "**이 포트 범위로 들어오는 트래픽**"을 허용한다는 뜻 |
| `IpRanges` | CIDR 기반 소스/대상 |
| `UserIdGroupPairs` | **보안그룹 기반 소스/대상**. GroupId로 다른 SG를 참조 |

> **FromPort/ToPort 주의**: 이름이 "From/To"라서 출발지 포트처럼 오해하기 쉽지만, 실제로는 **허용할 대상 포트의 시작/끝 범위**다. `FromPort: 443, ToPort: 443`이면 "포트 443으로 들어오는 트래픽을 허용"이라는 뜻이다. `FromPort: 1025, ToPort: 65535`이면 "포트 1025~65535 범위로 들어오는 트래픽을 허용"이다.

<br>

# 보안그룹 전체 조회

```bash
aws ec2 describe-security-groups | jq
```

<details markdown="1">
<summary>전체 출력</summary>

```json
<!-- TODO: 유저가 제공한 전체 JSON 출력 -->
```

</details>

EKS VPC(`vpc-0bbe44f398f6fc948`)에 속한 보안그룹은 총 **5개**다.

| # | Name | GroupId | 생성 주체 | 적용 대상 |
| --- | --- | --- | --- | --- |
| 1 | `myeks-VPC-default` | `sg-073486a208c8d2710` | VPC 생성 시 자동 | VPC 기본 SG (미사용) |
| 2 | `myeks-node` | `sg-05759c46248be71f5` | EKS Terraform 모듈 | 워커 노드 ENI (node shared SG) |
| 3 | `myeks-node-group-sg` | `sg-0a6afe6fd37744d7f` | Terraform 직접 정의 (`eks.tf`) | 워커 노드 ENI (추가 SG) |
| 4 | `eks-cluster-sg-myeks-*` | `sg-0776f9de59b07e26a` | **EKS 서비스 자동 생성** | 컨트롤 플레인 ENI + 워커 노드 ENI (primary/cluster SG) |
| 5 | `myeks-cluster` | `sg-07ca47ee2acbb5ccd` | EKS Terraform 모듈 | 컨트롤 플레인 ENI |

> 기본 VPC(`vpc-0c4484c1cccb8e8fe`)의 default SG는 EKS와 무관하므로 제외한다.

<!-- TODO: 어떤 SG가 어떤 리소스에 붙는지 다이어그램 또는 시각화 -->

<br>

# 보안그룹 상세 분석

## 1. `myeks-VPC-default` — VPC 기본 보안그룹 {#sg-vpc-default}

```
Description: "default VPC security group"
GroupId: sg-073486a208c8d2710
```

| 방향 | 규칙 |
| --- | --- |
| 인바운드 | 없음 |
| 아웃바운드 | 없음 |

VPC를 생성하면 자동으로 만들어지는 기본 보안그룹이다. Terraform VPC 모듈이 `manage_default_security_group = true`로 설정하여 기본 규칙(자기 자신 참조)을 제거한 상태다.

<!-- TODO: 이 설정이 어디서 오는지 vpc.tf 또는 모듈 확인 -->

실제로 어떤 리소스에도 명시적으로 연결되어 있지 않다.

<br>

## 2. `myeks-node` — EKS 노드 공유 보안그룹 {#sg-node-shared}

```
Description: "EKS node shared security group"
GroupId: sg-05759c46248be71f5
```

EKS Terraform 모듈(`terraform-aws-modules/eks/aws`)이 자동으로 생성하는 **워커 노드용 보안그룹**이다. 규칙이 가장 많고, EKS 클러스터의 핵심 통신 경로를 정의한다.

### 인바운드 규칙

| FromPort | ToPort | Protocol | 소스 SG | Description | 용도 |
| --- | --- | --- | --- | --- | --- |
| 443 | 443 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node groups | HTTPS. API 서버 → 노드 API 통신 |
| 4443 | 4443 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node 4443/tcp webhook | VPC Admission Webhook 등 |
| 6443 | 6443 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node 6443/tcp webhook | <!-- TODO: 어떤 컴포넌트가 6443을 쓰는지 --> |
| 8443 | 8443 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node 8443/tcp webhook | <!-- TODO: 어떤 컴포넌트가 8443을 쓰는지 --> |
| 9443 | 9443 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node 9443/tcp webhook | AWS Load Balancer Controller 등 |
| 10250 | 10250 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node kubelets | kubelet API. `kubectl logs`, `kubectl exec` 등 |
| 10251 | 10251 | TCP | `sg-07ca47ee2acbb5ccd` (cluster) | Cluster API to node 10251/tcp webhook | <!-- TODO: kube-scheduler 레거시 포트? 확인 --> |
| 53 | 53 | TCP | `sg-05759c46248be71f5` (self) | Node to node CoreDNS | DNS 쿼리 (TCP) |
| 53 | 53 | UDP | `sg-05759c46248be71f5` (self) | Node to node CoreDNS UDP | DNS 쿼리 (UDP) |
| 1025 | 65535 | TCP | `sg-05759c46248be71f5` (self) | Node to node ingress on ephemeral ports | 노드 간 통신 (ephemeral ports) |

### 아웃바운드 규칙

| Protocol | 대상 | Description |
| --- | --- | --- |
| `-1` (전체) | `0.0.0.0/0` | Allow all egress |

### 규칙 해석

<!-- TODO: 컨트롤 플레인 → 노드 통신 포트별 설명 -->

**컨트롤 플레인 → 노드 (소스: cluster SG `sg-07ca47ee2acbb5ccd`)**

API 서버가 워커 노드의 각종 포트로 접근해야 하는 이유:

- **10250 (kubelet)**: `kubectl exec`, `kubectl logs`, 메트릭 수집 등 API 서버가 kubelet에 직접 통신
- **443, 4443, 6443, 8443, 9443 (webhooks)**: Kubernetes Admission Webhook, Mutating/Validating Webhook을 실행하는 파드들이 노드에서 돌아감. API 서버가 요청 검증/변환을 위해 이 파드들에 접근
<!-- TODO: 각 포트를 구체적으로 어떤 컴포넌트가 쓰는지 정리 -->
- **10251**: <!-- TODO: 확인 필요 -->

**노드 ↔ 노드 (소스: self SG `sg-05759c46248be71f5`)**

- **53 (DNS)**: CoreDNS 파드가 노드에서 실행됨. 다른 노드의 파드가 DNS 쿼리를 보내려면 노드 간 53 포트 통신이 필요
  - DNS는 기본적으로 **UDP**를 먼저 사용하고, 응답이 512바이트를 초과하거나 zone transfer 시 **TCP** fallback
- **1025–65535 (ephemeral ports)**: 노드 간 파드 통신에 사용. 커널이 동적으로 할당하는 임시 포트 범위(ephemeral port range). Linux 기본값은 보통 `32768–60999`이지만, AWS는 더 넓게 `1025–65535`로 설정

<!-- TODO: ephemeral ports를 왜 이렇게 넓게 잡는지 설명 보강 -->

**아웃바운드: 전체 허용**

노드에서 나가는 트래픽은 전부 허용한다. ECR에서 이미지 풀, API 서버 통신, 인터넷 통신 등 다양한 외부 접근이 필요하기 때문이다.

<br>

## 3. `myeks-node-group-sg` — Terraform 직접 정의 보안그룹 {#sg-node-group}

```
Description: "Security group for EKS Node Group"
GroupId: sg-0a6afe6fd37744d7f
```

[코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#보안그룹)에서 살펴본 `aws_security_group.node_group_sg`다. `eks.tf`에서 직접 정의하고, `vpc_security_group_ids`로 노드 그룹에 연결했다.

### 인바운드 규칙

| Protocol | 소스 CIDR | 용도 |
| --- | --- | --- |
| `-1` (전체) | `121.xxx.xxx.xxx/32` | `var.ssh_access_cidr` — 내 공인 IP |
| `-1` (전체) | `192.168.1.100/32` | bastion host용 예비 허용 |

### 아웃바운드 규칙

없음.

### 규칙 해석

`protocol = "-1"`(모든 프로토콜, 모든 포트)로 설정했기 때문에 지정된 IP에서 오는 **모든 트래픽**을 허용한다. SSH(22)뿐만 아니라 ping(ICMP), HTTP 등 모든 접근이 가능하다.

아웃바운드 규칙이 없지만, 보안그룹이 **Stateful**이므로 인바운드로 들어온 요청의 응답은 자동으로 나간다. 노드에서 먼저 시작하는 외부 통신(ECR pull 등)은 같이 붙어 있는 `myeks-node` SG의 전체 허용 아웃바운드가 커버한다.

> [배포 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#보안그룹)에서 콘솔로 확인한 것과 동일한 보안그룹이다.

<br>

## 4. `eks-cluster-sg-myeks-*` — EKS Primary 보안그룹 {#sg-primary}

```
Description: "EKS created security group applied to ENI that is attached to EKS Control Plane master nodes, as well as any managed workloads."
GroupId: sg-0776f9de59b07e26a
```

**EKS 서비스가 클러스터 생성 시 자동으로 만드는** 보안그룹이다. Terraform 모듈이 아닌 AWS EKS 자체가 생성한다. 컨트롤 플레인 ENI와 관리형 노드 그룹 ENI **양쪽 모두**에 연결된다.

### 인바운드 규칙

| Protocol | 소스 SG | Description |
| --- | --- | --- |
| `-1` (전체) | `sg-0776f9de59b07e26a` (**자기 자신**) | Allows EFA traffic, which is not matched by CIDR rules. |

### 아웃바운드 규칙

| Protocol | 대상 | Description |
| --- | --- | --- |
| `-1` (전체) | `0.0.0.0/0` | (기본 아웃바운드) |
| `-1` (전체) | `sg-0776f9de59b07e26a` (**자기 자신**) | Allows EFA traffic, which is not matched by CIDR rules. |

### 규칙 해석

<!-- TODO: self-referencing SG의 의미 설명 -->

자기 자신을 소스로 참조하는 **self-referencing** 규칙이다. 이 SG가 붙은 모든 ENI 간에 전체 통신이 허용된다. 컨트롤 플레인과 워커 노드 양쪽에 이 SG가 붙어 있으므로, **컨트롤 플레인 ↔ 워커 노드 간 모든 포트가 양방향으로 열린다**.

앞서 `myeks-node` SG에서 포트별로 세밀하게 열어 놓은 것과 중복이지만, 이 SG는 EKS가 자체적으로 관리하는 **기본 통신 보장 레이어**다.

> **EFA(Elastic Fabric Adapter)** 언급은 HPC(고성능 컴퓨팅) 워크로드용이지만, 실제로는 self-referencing으로 전체 트래픽을 허용하는 범용 규칙이다.

<br>

## 5. `myeks-cluster` — EKS 클러스터 보안그룹 {#sg-cluster}

```
Description: "EKS cluster security group"
GroupId: sg-07ca47ee2acbb5ccd
```

EKS Terraform 모듈이 생성하는 **컨트롤 플레인 전용 보안그룹**이다.

### 인바운드 규칙

| FromPort | ToPort | Protocol | 소스 SG | Description |
| --- | --- | --- | --- | --- |
| 443 | 443 | TCP | `sg-05759c46248be71f5` (node shared) | Node groups to cluster API |

### 아웃바운드 규칙

없음.

### 규칙 해석

**노드 → API 서버** 방향의 HTTPS(443) 통신만 허용한다. kubelet이 API 서버에 상태를 보고하고, 파드가 API 서버에 접근할 때 이 경로를 사용한다.

아웃바운드 규칙이 없지만, 보안그룹이 Stateful이므로 인바운드 요청(노드 → API 서버)의 응답은 자동으로 나간다. API 서버에서 먼저 시작하는 통신(kubelet 접근, webhook 호출 등)은 primary SG(`eks-cluster-sg-myeks-*`)의 self-referencing 규칙이 커버한다.

<br>

# 통신 경로 정리

## 생성 주체별 분류

| 생성 주체 | 보안그룹 | 역할 |
| --- | --- | --- |
| **AWS VPC** | `myeks-VPC-default` | VPC 기본 SG. 사용 안 함 |
| **EKS 서비스 (AWS)** | `eks-cluster-sg-myeks-*` | Primary SG. 컨트롤·데이터 플레인 간 전체 통신 보장 |
| **EKS Terraform 모듈** | `myeks-node` | 워커 노드 세밀한 인바운드 포트 관리 |
| **EKS Terraform 모듈** | `myeks-cluster` | 컨트롤 플레인 인바운드(443) 관리 |
| **Terraform 직접 정의** | `myeks-node-group-sg` | SSH/관리 접근용 CIDR 기반 허용 |

<!-- TODO: EKS 모듈이 생성하는 SG vs EKS 서비스가 생성하는 SG 차이 명확히 -->

## 통신 방향별 정리

<!-- TODO: 도식 또는 Mermaid로 통신 흐름 시각화 -->

### 컨트롤 플레인 → 워커 노드

| 포트 | 프로토콜 | 용도 | 허용하는 SG |
| --- | --- | --- | --- |
| 443 | TCP | HTTPS (API 통신) | `myeks-node` |
| 4443 | TCP | Webhook (VPC Admission 등) | `myeks-node` |
| 6443 | TCP | Webhook | `myeks-node` |
| 8443 | TCP | Webhook | `myeks-node` |
| 9443 | TCP | Webhook (ALB Controller 등) | `myeks-node` |
| 10250 | TCP | kubelet API | `myeks-node` |
| 10251 | TCP | Webhook | `myeks-node` |
| 전체 | 전체 | self-ref | `eks-cluster-sg-myeks-*` |

### 워커 노드 → 컨트롤 플레인

| 포트 | 프로토콜 | 용도 | 허용하는 SG |
| --- | --- | --- | --- |
| 443 | TCP | kubelet → API 서버, 파드 → API 서버 | `myeks-cluster` |
| 전체 | 전체 | self-ref | `eks-cluster-sg-myeks-*` |

### 워커 노드 ↔ 워커 노드

| 포트 | 프로토콜 | 용도 | 허용하는 SG |
| --- | --- | --- | --- |
| 53 | TCP/UDP | CoreDNS | `myeks-node` |
| 1025–65535 | TCP | 파드 간 통신 (ephemeral ports) | `myeks-node` |
| 전체 | 전체 | self-ref | `eks-cluster-sg-myeks-*` |

### 외부 → 워커 노드

| 포트 | 프로토콜 | 소스 | 허용하는 SG |
| --- | --- | --- | --- |
| 전체 | 전체 | `121.xxx.xxx.xxx/32` (내 IP) | `myeks-node-group-sg` |
| 전체 | 전체 | `192.168.1.100/32` (예비) | `myeks-node-group-sg` |

<br>

# 이중 보안 구조

<!-- TODO: 왜 EKS primary SG(전체 허용)와 모듈 SG(포트별 허용)가 동시에 있는지 설명 -->

EKS 클러스터에는 **두 겹의 보안그룹 레이어**가 있다:

1. **Primary SG** (`eks-cluster-sg-myeks-*`): EKS 서비스가 자동 생성. self-referencing으로 컨트롤·데이터 플레인 간 **전체 통신을 보장**. EKS 내부 동작이 깨지지 않도록 하는 안전망
2. **모듈 SG** (`myeks-node`, `myeks-cluster`): Terraform 모듈이 생성. **포트 단위로 세밀하게 제어**. 커스터마이징 가능

Primary SG만으로도 통신은 되지만, 모듈 SG가 있어야 불필요한 포트를 차단하는 **최소 권한 원칙(Least Privilege)**을 적용할 수 있다. 반대로 모듈 SG만 있으면 새로운 EKS 기능이 추가될 때 포트를 직접 열어야 하므로, Primary SG가 기본 동작을 보장한다.

<!-- TODO: 온프레미스에서는 이걸 어떻게 했는지 비교 -->

<br>

# 온프레미스 비교

| 관점 | 온프레미스 (kubeadm) | EKS |
| --- | --- | --- |
| 방화벽 위치 | OS `iptables`/`firewalld` 또는 물리 방화벽 | AWS 보안그룹 (ENI 레벨) |
| 관리 방식 | 수동으로 포트 열기 (`6443`, `10250`, `2379-2380` 등) | EKS 모듈 + EKS 서비스가 자동 구성 |
| 컨트롤 플레인 포트 | `6443`(API), `2379-2380`(etcd), `10250-10252`(kubelet/scheduler/controller) | etcd는 관리형이라 불필요. API는 NLB 뒤에 위치 |
| 노드 간 통신 | 보통 같은 L2 네트워크에서 제한 없이 통신 | 보안그룹 self-referencing으로 허용 |
| 커스텀 접근 | 직접 iptables 규칙 작성 | `vpc_security_group_ids`로 추가 SG 연결 |

<!-- TODO: kubeadm 설치 시 열어야 하는 포트 목록 링크 추가 -->

<br>

# 정리

<!-- TODO: 핵심 요약 -->
<!-- TODO: 다음 글 링크 -->
