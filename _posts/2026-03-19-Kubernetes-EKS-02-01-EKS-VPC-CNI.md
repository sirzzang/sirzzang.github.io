---
title:  "[EKS] EKS: Networking - AWS VPC CNI"
excerpt: "AWS VPC CNI의 구조와 동작 원리에 대해 살펴보자."
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
  - VPC-CNI
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- AWS VPC CNI는 파드에게 **VPC의 실제 IP**를 부여하는 쿠버네티스 CNI 플러그인이다. 오버레이 없이 VPC 패브릭이 파드 IP를 직접 라우팅한다.
- VPC IP는 AWS 컨트롤 플레인이 관리하므로, IP 하나를 받으려면 **EC2 API 호출**이 필요하다. 매번 호출하면 느리고 위험하다.
- 이 문제를 **ipamd**(L-IPAM)가 해결한다. 장기 실행 데몬으로서 ENI/IP를 **미리 확보해 로컬 웜 풀로 관리**하고, 파드 생성 시에는 로컬 gRPC로 즉시 응답한다.
- IP 할당 모드(Secondary IP, Prefix Delegation, Custom Networking)와 웜 풀 전략(`WARM_ENI_TARGET`, `WARM_IP_TARGET`, `WARM_PREFIX_TARGET`)의 조합에 따라 파드 밀도와 서브넷 소비가 크게 달라진다.

<br>

# 들어가며

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-Kubernetes-Networking-Model %})에서 쿠버네티스 네트워킹 모델의 요구사항과 이를 충족하는 세 가지 방식(오버레이, BGP, 클라우드 네이티브 라우팅)을 살펴봤다. AWS VPC CNI는 **클라우드 네이티브 라우팅** 방식에 해당하며, EKS 클러스터의 기본 네트워킹 플러그인으로 설치된다.

VPC CNI의 핵심은 **파드에게 VPC의 실제 IP를 부여**하는 것이다. 노드의 ENI(Elastic Network Interface)에 보조 IP를 추가하고 그것을 파드에 할당하므로, VPC 패브릭이 파드 IP를 직접 라우팅할 수 있다. 1주차에서 확인했던 [Secondary ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}#vpc에-eni가-6개인-이유)가 바로 이 메커니즘의 일부였다.

AWS 공식 문서에서도 이 점을 "underlay mode"라는 키워드로 설명하고 있다.

> Amazon EKS officially supports Amazon VPC CNI plugin to implement Kubernetes Pod networking. The VPC CNI provides native integration with AWS VPC and **works in underlay mode**. In underlay mode, Pods and hosts are located at the same network layer and share the network namespace. The IP address of the Pod is consistent from the cluster and VPC perspective.
>
> — [AWS EKS Best Practices: Networking](https://docs.aws.amazon.com/eks/latest/best-practices/networking.html)

오버레이 네트워크를 한 겹 더 얹지 않고(underlay mode), 파드 IP와 노드 IP가 같은 네트워크 계층에 있으므로 VPC Flow Logs, VPC 라우팅 정책, 보안 그룹을 파드 트래픽에도 그대로 적용할 수 있다.

그런데 VPC의 실제 IP를 파드에 부여한다는 것은, 단순해 보이는 만큼 고유한 문제도 따라온다. 이 글에서는 그 문제가 무엇이고, VPC CNI가 어떤 구조로 해결하는지, 그리고 VPC CNI의 다양한 설정 옵션 및 그에 따른 동작 원리 등에 대해 살펴 본다.

<br>

# VPC CNI의 문제: IP를 AWS에 물어봐야 한다

## VPC IP는 AWS가 관리한다

AWS VPC CNI가 쓰는 IP는 "가상의 로컬 IP"가 아니라 **VPC의 실제 IP**다. AWS가 관리하는 IP이므로, 하나를 받으려면 반드시 EC2 API를 통해야 한다:

- ENI를 붙이려면 `AttachNetworkInterface`
- 보조 IP를 추가하려면 `AssignPrivateIpAddresses`
- IP를 반납하려면 `UnassignPrivateIpAddresses`

모든 IP 변경이 AWS API 호출을 수반한다. 파드 하나 뜰 때마다 이 호출이 발생한다면:

1. **지연(Latency)**: EC2 API 한 번 호출 = HTTPS 왕복 + AWS 내부 처리 → 수백ms~수초. 파드 시작이 느려진다.
2. **스로틀링(Throttling)**: AWS API에는 계정/리전별 초당 호출 제한이 있다. 이 제한에 걸리면 `RequestLimitExceeded` 에러가 발생하고, 파드가 IP를 못 받아 Pending 상태가 된다. 예를 들어 노드 100대에서 동시에 파드 수십 개씩 뜨는 상황이라면 쉽게 도달할 수 있다.
3. **신뢰성(Reliability)**: API 호출은 실패할 수 있다. 파드 생성 critical path에 원격 API 호출이 있으면 장애가 전파된다.

## 범용 CNI에서는 왜 문제가 안 되는가

범용 CNI에서는 이 문제가 크게 부각되지 않는다. IP를 외부에 물어볼 필요가 없기 때문이다.

[CNI 스펙](https://github.com/containernetworking/cni/blob/main/SPEC.md)에서 IP 할당은 **IPAM 플러그인**이 담당한다. 메인 플러그인(veth pair 생성, 라우팅 설정 등)이 "IP가 필요하다"고 IPAM에 위임하면, IPAM이 사용 가능한 IP를 골라 돌려주는 구조다. ([CNI 플러그인 실행 참고]({% post_url 2026-01-05-Kubernetes-CNI %}#cni-플러그인-실행))

범용 CNI에서 가장 흔한 IPAM인 `host-local`은, 노드에 할당된 CIDR 대역(예: `10.244.1.0/24`) 안에서 순번대로 IP를 골라 파드에 부여한다. 할당 기록은 로컬 파일(`/var/lib/cni/networks/`)에 기록만 하면 끝이다. 외부 API 호출이 없으니 파일 I/O 한 번(수μs)으로 완결된다.

VPC CNI는 이 자리에 EC2 API 호출(수백ms~수초 + throttling 위험)이 들어간다. 파드가 뜰 때마다 이 호출을 동기적으로 수행하는 방식은 대규모 클러스터에서 성립하지 않는다. AWS는 이 문제를 어떻게 풀었을까.

<br>

# 해결: ipamd — 장기 실행 IPAM 데몬

## 핵심 아이디어: 미리 받아서 로컬에 캐싱

핵심은 **파드 생성 시점이 아니라, 미리 EC2 API를 호출해서 ENI/IP를 로컬에 캐싱**해두는 것이다. 파드가 뜰 때는 로컬 캐시에서 꺼내 주기만 하면 되므로, 앞서 언급한 세 가지 문제(지연, 스로틀링, 신뢰성)가 모두 해결된다.

이처럼 미리 준비해 둔 리소스 풀을 **웜 풀(warm pool)**이라 한다. cold start 방지를 위해 인프라에서 일반적으로 쓰이는 패턴으로, DB connection pool과 비슷하게 이해하면 된다:

- **DB connection pool**: 미리 연결을 만들어 놓고, 요청이 오면 바로 꺼내 줌 → 매번 TCP handshake를 하지 않아도 됨
- **IP warm pool**: 미리 AWS API를 호출해서 ENI에 보조 IP를 받아 놓고, 파드가 뜨면 바로 꺼내 줌 → 매번 EC2 API를 호출하지 않아도 됨

VPC CNI에서 이 웜 풀을 관리하는 것이 **ipamd**(IP Address Management Daemon)다. 각 노드에서 상시 실행되는 데몬으로, 관리하는 상태는 다음과 같다:

- ENI를 몇 개 붙였는지
- 각 ENI에 보조 IP가 몇 개 남았는지
- 어떤 IP가 어떤 파드에 할당되었는지
- 웜 풀이 부족하면 언제 AWS API를 호출해서 추가 확보할지

## 범용 CNI와의 핵심 차이: IPAM의 생명 주기

범용 CNI에서 `host-local` 같은 IPAM은 1회성 바이너리다. kubelet이 호출하면 로컬 파일에서 다음 IP를 읽고 쓴 뒤 바로 종료한다. AWS API 호출이 필요 없으니 이것으로 충분하다. 반면 ipamd는 다음과 같은 작업을 지속적으로 수행해야 한다:

- ENI 풀을 모니터링하면서 부족하면 미리 추가
- 사용자 설정 정책(`WARM_ENI_TARGET`, `WARM_IP_TARGET` 등)에 따라 주기적으로 조정
- 파드 삭제 후 30초 cool-down 관리

호출될 때만 실행되는 1회성 바이너리로는 이런 상시 관리가 불가능하다. 그래서 ipamd는 DaemonSet 컨테이너 안에서 **gRPC 서버**로 상시 실행되면서, CNI 바이너리가 gRPC로 IP를 요청하면 웜 풀에서 즉시 응답하는 구조를 택했다.

|  | 범용 CNI (Calico, Flannel 등) | AWS VPC CNI |
| --- | --- | --- |
| 메인 플러그인 | 바이너리 (1회성) | 바이너리 (1회성) ← 같음 |
| IPAM | 바이너리 (1회성, `host-local`) | **ipamd 데몬 (상시 실행)** ← 다름 |

결론적으로 **EC2 API 호출은 ipamd가 백그라운드에서 비동기로** 하고, 파드 생성/삭제의 **critical path에는 로컬 통신만** 있는 구조다:

1. **ipamd 시작** — `DescribeInstances`로 현재 상태를 파악하고, `WARM_ENI_TARGET` 등 설정을 확인한 뒤, `CreateNetworkInterface` + `AttachNetworkInterface`로 ENI를 확보하고, `AssignPrivateIpAddresses`로 보조 IP를 받아 로컬 웜 풀에 저장한다.
2. **파드 생성** — CNI 바이너리가 ipamd에 gRPC로 IP를 요청하면, ipamd가 웜 풀에서 꺼내 즉시 응답한다. **EC2 API 호출 없음**.
3. **웜 풀 부족 감지** — 백그라운드에서 다시 `AssignPrivateIpAddresses`를 호출해 IP를 보충한다.
4. **파드 삭제** — IP를 30초 cooldown 후 웜 풀로 반환한다. 여분이 설정값을 초과하면 `UnassignPrivateIpAddresses`로 AWS에 반납한다.

<br>

# 아키텍처

## aws-node DaemonSet

VPC CNI는 워커 노드에 `aws-node`라는 DaemonSet으로 배포된다. EKS 클러스터 프로비저닝 시 기본으로 설치되며, 바닐라 쿠버네티스처럼 별도로 CNI를 설치할 필요가 없다. ([실제 배포 확인 참고]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %}#aws-node-vpc-cni))

> **참고**: DaemonSet 구조 자체는 범용 CNI와 크게 다르지 않다. 예를 들어 Calico도 `calico-node`라는 메인 컨테이너가 각 노드에서 상시 실행되며 오버레이 터널, BGP 피어링, 라우팅 테이블, NetworkPolicy를 관리한다. 차이는 **무엇을 상시 관리하느냐**다. 범용 CNI는 네트워크 경로를, VPC CNI의 ipamd는 **AWS 리소스(ENI/IP)**를 관리한다. VPC 네이티브이므로 오버레이가 필요 없는 대신, AWS 리소스 관리가 필요한 것이다.

aws-node 파드는 init 컨테이너 1개 + 일반 컨테이너 2개로 구성된다:

| 컨테이너 | 이미지 | 역할 |
| --- | --- | --- |
| `aws-vpc-cni-init` (init) | `amazon-k8s-cni-init` | CNI 바이너리를 호스트의 `/opt/cni/bin`에 설치 |
| `aws-node` (메인) | `amazon-k8s-cni` | **ipamd** — ENI/IP 웜 풀 관리, gRPC 서버 (포트 50051) |
| `aws-eks-nodeagent` | `aws-network-policy-agent` | Kubernetes NetworkPolicy 적용 |

init 컨테이너가 CNI 바이너리를 노드의 `/opt/cni/bin`에 복사하고, 메인 컨테이너가 ipamd를 실행한다. ipamd의 health check는 gRPC probe(`/app/grpc-health-probe -addr=:50051`)로 이루어진다.

## 컴포넌트 간 관계

![eks-vpc-cni-architecture]({{site.url}}/assets/images/eks-vpc-cni-architecture.png){: .align-center}

<center><sup>VPC CNI 아키텍처 — 출처: <a href="https://docs.aws.amazon.com/eks/latest/best-practices/vpc-cni.html">AWS EKS Best Practices</a></sup></center>

- **kubelet → CNI 바이너리**: `CNI Add/Delete` — 파드 생성/삭제 시 kubelet(→containerd)이 CNI 바이너리를 호출한다. 호출 체인은 `kubelet → containerd → /opt/cni/bin/aws-cni`다.
- **ipamd(L-IPAM) → VPC CNI 바이너리**: `Update Configs` — ipamd가 현재 ENI/IP 풀 상태 등 플러그인 설정을 CNI 바이너리에게 전달한다. 파드 생성 시 CNI 바이너리가 ipamd에게 gRPC(포트 50051)로 IP를 요청하는 흐름은 이 다이어그램에 별도 표시되어 있지 않다.
- **ipamd(L-IPAM) → Kernel API**: `Add/Update Routes` — ipamd가 ENI 연결 시 라우팅 테이블과 룰을 설정한다.
- **ipamd → iptables**: `NAT Rules` — ipamd가 SNAT 등 NAT 규칙을 설정한다.
- **ipamd ↔ EC2 Control Plane**: `Attach New ENI and IPs` — ipamd가 백그라운드에서 EC2 API로 ENI/IP를 확보한다.

> **참고: ipamd의 EC2 API 호출 권한**
>
> ipamd가 EC2 API를 호출하려면 IAM 권한이 필요하다. EKS에서 이 권한을 부여하는 방식으로는 대표적으로 아래와 같은 것들이 있다:
>
> - **EC2 인스턴스의 Node IAM Role** (기본): 워커 노드의 IAM Role에 `AmazonEKS_CNI_Policy` 관리형 정책이 포함됨. aws-node 파드가 `hostNetwork: true`로 실행되므로 IMDS에 접근하여 인스턴스 역할의 임시 자격 증명을 사용한다.
> - **IRSA (IAM Roles for Service Accounts)** (권장): aws-node ServiceAccount에 IAM Role을 직접 연결. 노드 역할에서 CNI 관련 권한을 분리할 수 있어 최소 권한 원칙에 부합한다.
>
> `AmazonEKS_CNI_Policy`에 포함된 주요 권한은 다음과 같다:
> - ENI 관리: `CreateNetworkInterface`, `AttachNetworkInterface`, `DetachNetworkInterface`, `DeleteNetworkInterface`
> - IP 관리: `AssignPrivateIpAddresses`, `UnassignPrivateIpAddresses`
> - 조회: `DescribeInstances`, `DescribeNetworkInterfaces`, `DescribeSubnets`


<br>

# 동작 원리

## 파드 생성 시: IP 할당

![eks-vpc-cni-pod-creation]({{site.url}}/assets/images/eks-vpc-cni-pod-creation.png){: .align-center}

<center><sup>파드 생성 시 IP 할당 과정 — EC2 API 호출 없이 로컬에서 완결된다. 하단의 왼쪽 ENI(eth0)에서 초록 화살표는 이미 Running Pods에 할당된 IP이고, 오른쪽 ENI(eth1)에서 주황 화살표 하나가 New Pod로 연결되어 이번에 새로 할당되는 IP를 나타낸다.</sup></center>

1. **Schedule Pod** — Scheduler가 노드를 결정하고, kubelet이 API Server를 통해 파드를 전달받음
2. **Add** — kubelet이 containerd를 통해 CNI 바이너리 호출
3. **Get Pod IP** — CNI 바이너리가 ipamd에게 gRPC로 IP 요청
4. **Return Pod IP** — ipamd가 웜 풀에서 사용 가능한 IP를 꺼내 반환
5. **Setup Network NS** — CNI 바이너리가 Kernel API로 veth pair, 라우팅, iptables 설정
6. **Return Pod IP** — CNI 바이너리가 kubelet에게 "이 IP로 세팅 완료" 응답
7. **Assign Pod IP** — kubelet이 파드에 IP를 최종 할당, 파드 시작

이 과정에서 **EC2 API 호출이 없다**. ipamd가 이미 확보해 둔 IP를 로컬에서 꺼내 주는 것이기 때문이다.

## IP 풀 고갈 시: ENI 추가 확보

![eks-vpc-cni-pool-exhaustion]({{site.url}}/assets/images/eks-vpc-cni-pool-exhaustion.png){: .align-center}

<center><sup>IP 풀이 고갈되면 ipamd가 백그라운드에서 EC2 API를 호출해 새 ENI를 확보한다. 하단에서 eth0, eth1의 주황 화살표는 이미 할당된 IP이고, 새로 추가된 eth2(초록)와 그 초록 화살표가 이번에 EC2 API를 통해 확보한 ENI와 IP다. 오른쪽 점선 박스(New Pods)가 이 새 IP를 받아 생성될 파드를 나타낸다.</sup></center>

파드가 계속 늘어나서 웜 풀이 바닥나면:

1. **ipamd가 웜 풀 부족을 감지**한다 — 웜 풀 설정(`WARM_ENI_TARGET`, `WARM_IP_TARGET` 등)에 따라 여유가 설정값 이하로 떨어지면 트리거된다.
2. **EC2 API를 호출하여 새 ENI를 확보**한다 — `CreateNetworkInterface` → `AttachNetworkInterface` → `AssignPrivateIpAddresses` 순서로 새 ENI를 생성하고 인스턴스에 붙인 뒤, 보조 IP를 할당받는다.
3. **NAT 규칙과 라우팅을 추가**한다 — 새 ENI/IP에 대한 iptables 규칙과 라우팅 테이블 엔트리를 설정한다.
4. **확보된 IP가 웜 풀에 추가**된다 — 이후 파드 생성 요청에 다시 로컬에서 즉시 응답할 수 있다.

이 과정은 노드가 인스턴스 타입의 **ENI 최대 개수**에 도달할 때까지 반복된다.

## 파드 삭제 시: IP 반환

파드가 삭제되면 VPC CNI는 파드의 IP를 즉시 웜 풀로 돌려보내지 않고, **30초 cool-down cache**에 배치한다.

- cool-down 기간 동안 해당 IP는 새 파드에 할당되지 않는다
- 이 기간은 모든 클러스터 노드에서 kube-proxy가 iptables 규칙 업데이트를 완료할 시간을 보장한다. IP를 조기에 재활용하면, 이전 파드를 가리키는 iptables 규칙이 아직 남아 있을 때 새 파드가 그 IP를 받아 의도치 않은 트래픽이 전달될 수 있다.
- cool-down이 끝나면 IP가 웜 풀로 복귀한다
- 여분이 웜 풀 설정값을 초과하면 ipamd가 `UnassignPrivateIpAddresses`로 IP를, `DetachNetworkInterface` + `DeleteNetworkInterface`로 ENI를 AWS에 반납한다

<br>


# 설정

VPC CNI는 `aws-node` DaemonSet의 환경 변수로 설정한다. 설정을 이해하기 전에, VPC CNI의 IP 관리 단위인 **슬롯(slot)**이라는 개념을 먼저 짚고 넘어가자.

## 슬롯: IP 관리의 기본 단위

ENI에는 인스턴스 타입이 정하는 수만큼의 **슬롯**이 있다. 각 슬롯에는 1개의 IP 주소 또는 1개의 /28 prefix가 들어간다. /28은 [EC2 API 수준에서 고정된 크기](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-prefix-eni.html)로, 사용자가 변경할 수 없다. 슬롯 중 첫 번째(slot 1)는 ENI 자체의 **주 IP(primary IP)**로 예약되어 파드에 할당할 수 없다. 파드가 쓸 수 있는 건 나머지 슬롯의 **보조 IP(secondary IP)**뿐이다.

이 구조에서 노드당 최대 파드 수 공식이 나온다:

```
Max Pods = ENI 수 × (ENI당 슬롯 수 - 1) + 2
```

- `- 1`: 각 ENI의 주 IP(slot 1)를 빼는 것이다.
- `+ 2`: `hostNetwork: true`로 실행되는 인프라 파드(aws-node, kube-proxy)를 더하는 것이다. 이 파드들은 **VPC IP를 소비하지 않는다**.

예를 들어 m5.large(ENI 3개, ENI당 슬롯 10개)는 `3 × (10 - 1) + 2 = 29`개(순수 IP 27개), t3.small(ENI 3개, ENI당 슬롯 4개)은 `3 × (4 - 1) + 2 = 11`개(순수 IP 9개)다. 이 공식은 **Secondary IP 모드 기준**이며, Prefix Delegation에서는 슬롯 하나에 /28 prefix(16개 IP)가 할당되므로 16배가 된다(`ENI 수 × (슬롯 수 - 1) × 16`).

> 이 공식은 ENI/슬롯에서 나오는 **순수 IP 수용량**이다. 실제 운영에서는 `max-pods`, AWS 권장 상한 등 추가 제한이 겹친다. 이에 대해서는 설정을 모두 살펴본 뒤 [노드당 파드 수와 IP 설계](#노드당-파드-수와-ip-설계)에서 정리한다.

새 파드가 생성되면 VPC CNI는 다음 흐름으로 슬롯을 찾는다:

![eks-vpc-cni-slot-assignment-flow]({{site.url}}/assets/images/eks-vpc-cni-slot-assignment-flow.png){: .align-center width="600"}

<center><sup>슬롯 할당 흐름 — Primary ENI → 웜 풀의 Secondary ENI → 새 ENI 부착 순서로 시도한다. 인스턴스의 ENI 상한에 도달하면 실패한다. 출처: <a href="https://docs.aws.amazon.com/eks/latest/best-practices/vpc-cni.html">AWS EKS Best Practices</a></sup></center>

이 "슬롯"이라는 추상 단위 덕분에, 이후 설정 섹션에서 다루는 Secondary IP와 Prefix Delegation은 **슬롯에 뭘 넣는가**의 차이로 이해할 수 있다.

VPC CNI 설정은 크게 두 축이 있다:

1. **IP 할당 설정**: ENI 슬롯에 뭘 넣고, 어느 서브넷에서 가져오는가
2. **웜 풀 전략**: 얼마나 미리 확보해 둘 것인가

## IP 할당 설정

VPC CNI의 IP 할당에는 두 가지 독립된 축이 있다: **ENI 슬롯에 뭘 넣는가**(Secondary IP vs Prefix Delegation)와 **어느 서브넷에서 가져오는가**(기본 서브넷 vs Custom Networking). 두 축은 독립적이므로 조합이 가능하다(예: Prefix Delegation + Custom Networking).

### ENI 슬롯에 뭘 넣는가: Secondary IP vs Prefix Delegation

**Secondary IP 모드 (기본값)**

![eks-vpc-cni-secondary-ip-mode]({{site.url}}/assets/images/eks-vpc-cni-secondary-ip-mode.png){: .align-center}

위에서 설명한 슬롯 하나에 **개별 /32 IP 주소 1개**가 들어간다. 파드 1개 = IP 1개이므로, [위의 공식](#슬롯-ip-관리의-기본-단위)대로 m5.large는 최대 27개 파드다. 기본 모드이며, IP를 아껴 쓰는 소규모 클러스터에 적합하다.

![eks-vpc-cni-secondary-ip-mode-aws-doc]({{site.url}}/assets/images/eks-vpc-cni-secondary-ip-mode-aws-doc.png){: .align-center width="600"}

<center><sup>t3.small의 Secondary IP 모드 — ENI 3개 × 슬롯 4개(주 IP 1개 + 보조 IP 3개). 보조 IP 9개가 파드에 할당된다. 출처: <a href="https://docs.aws.amazon.com/eks/latest/best-practices/vpc-cni.html">AWS EKS Best Practices</a></sup></center>

<br>

**Prefix Delegation 모드**

![eks-vpc-cni-prefix-delegation-mode]({{site.url}}/assets/images/eks-vpc-cni-prefix-delegation-mode.png){: .align-center}

ENI의 각 슬롯에 개별 IP가 아니라 **/28 prefix 블록(IP 16개)**이 할당된다. 슬롯 수는 동일하지만, 슬롯 하나가 품는 IP 수가 1개에서 16개로 바뀐다. "이 16개짜리 블록은 너(노드)한테 위임(delegate)할 테니 네가 알아서 써라"는 것이다.

m5.large로 계산하면, 기본 모드에서는 `3 × 9 = 27`개인데, Prefix Delegation에서는 `3 × 9 × 16 = 432`개까지 **IP 수용량**이 늘어난다.

**그러면 무조건 파드를 많이 쓸 수 있으니 이 모드가 좋은 것 아닌가 생각할 수 있지만** 그렇지 않다. 핵심 트레이드오프는 **IP 낭비**다:

- 슬롯 하나를 쓰면 무조건 16개 IP가 서브넷에서 예약된다. 파드가 1개만 떠도 16개가 잡힌다.
- /28 블록은 16개 단위로 **정렬(aligned)된 연속 IP**여야 한다. 서브넷에 빈 IP가 총 30개 남아 있더라도, 16개가 연속으로 비어 있는 구간이 없으면 블록 할당이 실패한다(fragmentation). 서브넷이 `/24`처럼 작으면, 노드 몇 대만으로 서브넷이 고갈될 수 있다.
- 그래서 Prefix Delegation을 쓸 때는 **전용 서브넷을 충분히 크게**(`/20` 이상) 잡는 것이 권장된다.

> **참고: EC2가 디프래그해 주면 안 되나?**
>
> 이미 할당된 IP는 해당 리소스가 사용하는 한 다른 주소로 옮길 수 없다. 같은 서브넷에서 개별 secondary IP(RDS, ELB, Lambda ENI 등)가 하나씩 흩어져 할당되면, 시간이 지나며 연속 공간이 사라진다. EC2가 빈 공간을 재배치하려면 실행 중인 리소스의 IP를 바꿔야 하는데, 그건 허용되지 않는다. AWS는 이 문제를 위해 [서브넷 CIDR 예약(Subnet CIDR Reservation)](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-cidr-reservation.html)을 제공한다. 서브넷의 일부 구간을 prefix 전용으로 예약하면 개별 IP 할당이 그 구간에 들어오지 않아 fragmentation을 방지할 수 있다.

대부분의 워크로드에서는 노드당 27개 파드로 충분하고, VPC IP 공간이 더 귀중하기 때문에 Secondary IP가 기본값이다. 파드 밀도 문제가 발생할 때 Prefix Delegation을 고려한다.

![eks-vpc-cni-secondary-vs-prefix-aws-doc]({{site.url}}/assets/images/eks-vpc-cni-secondary-vs-prefix-aws-doc.png){: .align-center width="600"}

<center><sup>Secondary IP 모드(왼쪽)와 Prefix Delegation 모드(오른쪽) 비교 — 같은 슬롯 수지만, 슬롯에 담기는 것이 개별 IP인지 /28 prefix인지가 다르다. 출처: <a href="https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html">AWS EKS Best Practices</a></sup></center>

<br>

### 어느 서브넷에서 가져오는가: Custom Networking

![eks-vpc-cni-custom-networking]({{site.url}}/assets/images/eks-vpc-cni-custom-networking.gif){: .align-center}

<center><sup>Custom Networking — 노드와 파드가 서로 다른 서브넷을 사용한다. 출처: <a href="https://docs.aws.amazon.com/eks/latest/best-practices/ip-opt.html">AWS EKS Best Practices</a></sup></center>

노드와 파드의 IP 대역을 **완전히 분리**한다. 기본적으로 VPC CNI는 노드의 기본 ENI에 할당된 서브넷에서 파드 IP를 가져오지만, Custom Networking에서는 **ENIConfig**라는 CRD로 "파드용 ENI는 이 서브넷에서 만들어라"고 지정한다:

- 노드 서브넷: `10.0.0.0/16` (primary CIDR)
- 파드 서브넷: `100.64.0.0/16` (secondary CIDR)

파드가 아무리 많아져도 노드 서브넷의 IP는 건드리지 않는다. CG-NAT 대역(`100.64.0.0/10`)은 기업 환경에서 잘 쓰이지 않아 충돌 가능성이 낮기 때문에 권장된다.

[이전 글에서 정리한 것]({% post_url 2026-03-19-Kubernetes-EKS-02-00-Kubernetes-Networking-Model %}#해결-방식)처럼, 대역이 다르더라도 VPC의 secondary CIDR이므로 VPC 라우팅 도메인 안에 있다. 핵심 메커니즘(ENI에 보조 IP를 붙이고, VPC 패브릭이 라우팅)은 동일하며, **보조 IP를 어느 서브넷에서 가져오느냐**만 다르다.

> **참고: `EXTERNAL_SNAT`과 Instance/IP mode**
>
> Custom Networking 다이어그램 하단의 `EXTERNAL_SNAT`은 **파드에서 인터넷(외부)으로 나가는 트래픽**에 대한 설정이다. 쿠버네티스 네트워킹 모델의 "NAT 없이" 원칙은 파드 간 직접 통신 경로에만 적용되므로, 외부 트래픽의 SNAT은 대원칙과 무관하다. Instance mode vs IP mode도 ELB에서 파드까지의 인바운드 경로(외부 ↔ 서비스) 설정이며, 파드 간 통신이 아니다.

<br>

### 조합 종합 비교

두 축의 조합을 한눈에 정리하면 다음과 같다(m5.large 기준, ENI 3개 × 슬롯 9개):

| | 기본 서브넷 | Custom Networking |
| --- | --- | --- |
| **Secondary IP** | 슬롯당 IP 1개, 최대 27 파드. 파드 IP가 노드와 **같은 서브넷**에서 나온다. | 동일하지만, 파드 IP가 **별도 서브넷**(secondary CIDR)에서 나온다. 노드 IP 공간을 보존한다. |
| **Prefix Delegation** | 슬롯당 /28(IP 16개), 최대 432 파드. 파드 밀도가 높지만 IP 낭비 위험이 크다. | 동일하지만, /28 블록이 **별도 서브넷**에서 할당된다. 큰 서브넷(`/20` 이상)을 파드 전용으로 확보하기 좋다. |

네 가지 조합 모두 VPC 네이티브 라우팅이며, ENI에 부착 → VPC 패브릭이 라우팅하는 메커니즘은 동일하다.

<br>

## 웜 풀 전략

얼마나 미리 확보해 둘 것인가를 제어하는 설정이다. ENI 단위와 IP 단위 두 가지 전략이 있으며, **상호 배타적**이다.

### 전략 1: ENI 단위 — `WARM_ENI_TARGET`

`WARM_ENI_TARGET` (기본값 1)은 **현재 사용 중이 아닌 여유 ENI 수**를 지정한다.

예를 들어 t3.small(ENI당 보조 IP 3개)에서 `WARM_ENI_TARGET=1`이면:

- 파드 0개: ENI 1개(IP 3개)가 이미 확보됨 → 여유 ENI 1개 충족
- 파드 1개: 첫 ENI에서 IP 1개 사용 → 이 ENI는 더 이상 "여유"가 아님 → 여유 ENI 0개 → 새 ENI를 붙여서 다시 1개 유지
- 파드 3개: 첫 ENI의 IP가 다 소진 → 두 번째 ENI가 여유 → 여유 ENI 1개 충족(추가 없음)
- 파드 4개: 두 번째 ENI에서도 IP 1개 사용 → 여유 ENI 0개 → 세 번째 ENI를 붙여서 다시 1개 유지
- 파드 5개: ENI 2개로 부족, 여유 유지를 위해 ENI 3개 → IP 9개 확보, 여유 IP 4개

ENI를 통째로 가져오므로 IP 확보 속도가 가장 빠르지만, **과잉 확보**가 될 수 있다.

### 전략 2: IP 단위 — `WARM_IP_TARGET` + `MINIMUM_IP_TARGET`

- `WARM_IP_TARGET`: **현재 할당되지 않은 여유 IP 수**. 파드에 할당되지 않은 IP가 이 값 이상이 되도록 유지한다.
- `MINIMUM_IP_TARGET`: **노드에 확보된 총 IP의 하한선**. 사용 중이든 아니든 합산해서 이 값 이상을 유지한다. 초기 대규모 스케일아웃에 대비한다.

둘 중 **더 많은 IP를 요구하는 쪽**이 이긴다. `WARM_IP_TARGET`이 설정되면 `WARM_ENI_TARGET`은 무시된다.

같은 t3.small에서 `WARM_IP_TARGET=1, MINIMUM_IP_TARGET=1`이면:

- 파드 0개: IP 1개만 확보 → ENI 1개, 여유 IP 1개
- 파드 1개: 필요 IP 1 + 여유 1 = 2개 → ENI 1개(IP 3개)로 충분 → **새 ENI 없이** 기존 ENI에서 해결
- 파드 5개: 필요 IP 5 + 여유 1 = 6개 → ENI 2개면 충분 → IP 6개 확보

`WARM_ENI_TARGET=1`에서는 파드 1개만 떠도 새 ENI를 붙였지만, `WARM_IP_TARGET=1`에서는 여유 IP가 남아 있으면 ENI를 추가하지 않는다. 같은 파드 5개에서도 ENI 단위(ENI 3개, IP 9개) 대비 ENI를 하나 덜 쓴다. 서브넷 IP가 부족한 환경에서 유리하다.

### Prefix Delegation 전용: `WARM_PREFIX_TARGET`

Prefix Delegation 모드에서는 **여유 /28 블록 수**를 직접 제어하는 `WARM_PREFIX_TARGET`을 사용할 수 있다. `WARM_PREFIX_TARGET=1`이면 /28 블록 1개(=IP 16개)를 웜 풀로 유지한다.

기존 `WARM_IP_TARGET`도 Prefix 모드에서 동작하지만, IP를 블록 단위로 가져오므로 의도보다 훨씬 많은 IP를 잡아먹게 된다. 블록 단위로 직접 제어하는 `WARM_PREFIX_TARGET`이 더 자연스럽다.

### 참고: 설정별 실제 ENI/IP 소비

아래 표는 [AWS VPC CNI 공식 문서](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/eni-and-ip-target.md)에서 발췌한 것으로, 인스턴스 타입과 웜 풀 설정에 따라 실제 ENI/IP가 어떻게 소비되는지 보여준다.

**t3.small** (ENI당 보조 IP 3개):

| `WARM_ENI_TARGET` | `WARM_IP_TARGET` | `MINIMUM_IP_TARGET` | 파드 수 | 부착 ENI | 보조 IP | 미사용 IP |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | - | - | 0 | 1 | 3 | 3 |
| 1 | - | - | 5 | 3 | 9 | 4 |
| 1 | - | - | 9 | 3 | 9 | 0 |
| - | 1 | 1 | 0 | 1 | 1 | 1 |
| - | 1 | 1 | 5 | 2 | 6 | 1 |
| - | 1 | 1 | 9 | 3 | 9 | 0 |
| - | 2 | 5 | 0 | 2 | 5 | 5 |
| - | 2 | 5 | 5 | 3 | 7 | 2 |
| - | 2 | 5 | 9 | 3 | 9 | 0 |

**p3dn.24xlarge** (ENI당 보조 IP 49개):

| `WARM_ENI_TARGET` | `WARM_IP_TARGET` | `MINIMUM_IP_TARGET` | 파드 수 | 부착 ENI | 보조 IP | 미사용 IP |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | - | - | 0 | 1 | 49 | 49 |
| 1 | - | - | 3 | 2 | 98 | 95 |
| 1 | - | - | 95 | 3 | 147 | 52 |
| - | 5 | 10 | 0 | 1 | 10 | 10 |
| - | 5 | 10 | 7 | 1 | 12 | 5 |
| - | 5 | 10 | 15 | 1 | 20 | 5 |
| - | 5 | 10 | 45 | 2 | 50 | 5 |

표에서 읽을 수 있는 핵심은 아래와 같다:

- **인스턴스가 클수록 `WARM_ENI_TARGET`의 IP 낭비가 심하다.** t3.small에서는 전략 간 차이가 미미하지만, p3dn.24xlarge에서는 `WARM_ENI_TARGET=1`만으로 파드 3개에 미사용 IP 95개가 잡힌다. ENI 단위로 통째로 확보하기 때문이다.
- **`WARM_IP_TARGET`은 IP 단위로 조밀하게 제어한다.** 같은 p3dn.24xlarge에서 `WARM_IP_TARGET=5`로 전환하면, 파드 3개일 때 미사용 IP가 95개 → 5개로 줄어든다. 서브넷 IP가 부족한 환경에서는 이 차이가 곧 서브넷 고갈 여부를 결정한다.
- **`MINIMUM_IP_TARGET`은 초기 확보 하한선이다.** t3.small에서 `MINIMUM_IP_TARGET=5`로 설정하면, 파드 0개에서도 IP 5개(ENI 2개)를 미리 확보한다. 노드 시작 직후 대량 스케줄링이 예상되는 배치 워크로드에 유용하다.

### 조합 정리

| 할당 모드 | 웜 풀 전략 | 사용 파라미터 |
| --- | --- | --- |
| Secondary IP | ENI 단위 | `WARM_ENI_TARGET` |
| Secondary IP | IP 단위 | `WARM_IP_TARGET` + `MINIMUM_IP_TARGET` |
| Prefix Delegation | ENI 단위 | `WARM_ENI_TARGET` |
| Prefix Delegation | IP 단위 | `WARM_IP_TARGET` + `MINIMUM_IP_TARGET` |
| Prefix Delegation | Prefix 단위 | `WARM_PREFIX_TARGET` |

ENI 단위와 IP 단위는 상호 배타이고, Prefix 단위는 Prefix Delegation 모드 전용이다.

## 모드별 서브넷 소비 비교

t3.small (최대 ENI 3개, ENI당 보조 IP 슬롯 3개) 기준, 파드 5개일 때:

| 모드 | 웜 풀 전략 | 확보 IP | 서브넷 소비 | 소비 대역 |
| --- | --- | --- | --- | --- |
| Secondary IP | `WARM_ENI_TARGET=1` | 9 | 9개 | 노드 서브넷 |
| Secondary IP | `WARM_IP_TARGET=1, MIN=1` | 6 | 6개 | 노드 서브넷 |
| Secondary IP + Custom | `WARM_ENI_TARGET=1` | 9 | 9개 | 파드 서브넷 |
| Secondary IP + Custom | `WARM_IP_TARGET=1, MIN=1` | 6 | 6개 | 파드 서브넷 |
| Prefix Delegation | `WARM_ENI_TARGET=1` | 144 | 144개 | 노드 서브넷 |
| Prefix Delegation | `WARM_PREFIX_TARGET=1` | 16 | 16개 | 노드 서브넷 |
| Prefix Delegation | `WARM_IP_TARGET=1, MIN=1` | 16 | 16개 | 노드 서브넷 |
| Prefix + Custom | `WARM_PREFIX_TARGET=1` | 16 | 16개 | 파드 서브넷 |

같은 파드 5개인데, 모드 + 전략 조합에 따라 서브넷 소비가 **6개 ~ 144개**까지 차이난다. Prefix + `WARM_ENI_TARGET` 조합이 가장 낭비가 심하고, Secondary IP + `WARM_IP_TARGET` 조합이 가장 절약된다.

## 노드당 파드 수와 IP 설계

[앞서 본 공식](#슬롯-ip-관리의-기본-단위)은 ENI/슬롯에서 나오는 순수 IP 수용량이다. **IP/서브넷 설계 시에는 `+ 2`(hostNetwork 파드)를 빼고**, 순수 할당 가능 IP인 `ENI 수 × (슬롯 수 - 1)`만 보면 된다. m5.large는 순수 IP 27개, t3.small은 9개다.

하지만 이 숫자가 곧 실제 파드 수 상한은 아니다. **세 겹의 제한**이 겹친다:

| 제한 | 결정 주체 | 변경 가능 여부 |
| --- | --- | --- |
| **ENI/슬롯 수** | EC2 인스턴스 타입 | 불가 ([하드 리밋](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-eni.html#AvailableIpPerENI)) |
| **`max-pods`** | kubelet 설정 (EKS AMI 기본값 내장) | 가능 (부트스트랩 스크립트에서 오버라이드) |
| **AWS 권장 상한** | Prefix Delegation 시 vCPU 기준 | 권장값 (30 vCPU 미만 = 110, 이상 = 250) |

실제 파드 상한 = `min(max-pods, 할당 가능 IP 수)`다. EKS AMI 기본 `max-pods`는 **Secondary IP 모드 기준**으로 계산되어 있으므로(m5.large = 29), Prefix Delegation을 켜면 IP 수용량은 수백 개로 늘어나지만 **`max-pods`를 함께 올리지 않으면 기본값에 막혀** 효과를 볼 수 없다. 예를 들어 m5.large(2 vCPU)는 PD 모드에서 IP 수용량이 432개이지만, AWS 권장 상한(110개)과 `max-pods` 설정이 실제 한계를 결정한다.

<br>

# 정리

VPC CNI는 쿠버네티스 네트워킹 모델을 AWS 인프라 위에서 클라우드 네이티브하게 구현한 CNI 플러그인이다. 그 구조를 한 문장으로 요약할 수 있다.

> **ipamd가 EC2 API를 미리 호출해서 ENI/IP를 로컬 웜 풀에 확보해 두고, 파드 생성 시에는 로컬 gRPC로 즉시 IP를 할당한다.**

이해해야 할 핵심 축은 두 가지다:

1. **왜 ipamd가 필요한가**: VPC IP는 AWS가 관리 → EC2 API 호출 필수 → 매번 호출하면 느림/위험 → 미리 받아서 캐싱
2. **설정을 어떻게 조합하는가**: IP 할당 모드(Secondary IP / Prefix Delegation / Custom Networking)와 웜 풀 전략(`WARM_ENI_TARGET` / `WARM_IP_TARGET` / `WARM_PREFIX_TARGET`)의 조합이 파드 밀도와 서브넷 소비를 결정

<br>
