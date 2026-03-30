---
title:  "[EKS] EKS: Networking - 0. 쿠버네티스 네트워킹 모델"
excerpt: "쿠버네티스 네트워킹의 4가지 문제와 핵심 원칙인 'NAT 없이'에 대해 알아보자."
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

# TL;DR

- 쿠버네티스 네트워킹은 통신 범위에 따라 **4가지 문제**로 나뉜다: 컨테이너 간, 파드 간, 파드-서비스, 외부-서비스
- 핵심 원칙은 **"NAT 없이"**: 모든 파드가 고유 IP로 직접 통신할 수 있어야 한다 (flat network)
- 이 원칙은 **파드 간 직접 통신(문제 2)**에만 적용된다. Service DNAT(문제 3)과 외부 SNAT(문제 4 영역)은 위반이 아니다
- 파드 간 통신의 해결 방식은 세 가지: 오버레이, BGP, 클라우드 네이티브 라우팅. AWS VPC CNI는 클라우드 네이티브에 해당한다

<br>

# 들어가며

1주차에서 EKS 클러스터를 배포하고 내부 구조를 확인하면서, 이미 AWS VPC CNI의 흔적을 여러 번 만났다.

- [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}#vpc에-eni가-6개인-이유): 워커 노드마다 **VPC CNI Secondary ENI**가 생성되어 파드 IP 할당을 준비하고 있었다
- [엔드포인트 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %}#노드--api-서버-ss--tnp): `ss -tnp`에서 **aws-k8s-agent**(VPC CNI 에이전트)가 API 서버와 연결을 유지하며 ENI 관리와 IP 할당 정보를 동기화하고 있었다

2주차의 주제는 이 AWS VPC CNI를 비롯한 EKS 네트워킹을 본격적으로 파헤치는 것이다. 그런데 EKS 네트워킹의 핵심인 AWS VPC CNI가 "무엇을 해결하는지"를 이해하려면, 먼저 **쿠버네티스가 네트워킹에 대해 무엇을 요구하는지**를 알아야 한다. VPC CNI든 Flannel이든 Calico든, 모든 CNI 플러그인은 쿠버네티스의 네트워킹 모델이 정한 요구사항을 구현하는 것이기 때문이다.

이 글에서는 쿠버네티스 네트워킹의 전체 그림을 먼저 잡는다. 4가지 문제가 무엇이고, 핵심 원칙인 "NAT 없이"가 어디까지 적용되는지를 정리한다.

<br>

# 쿠버네티스 네트워킹의 4가지 문제

쿠버네티스 공식 문서는 클러스터 네트워킹을 통신 범위에 따라 [4가지 문제](https://kubernetes.io/docs/concepts/cluster-administration/networking/)로 분류한다:

| # | 문제 | 해결 주체 |
| --- | --- | --- |
| 1 | **컨테이너 ↔ 컨테이너** (같은 파드 내) | Pause 컨테이너가 만든 공유 네트워크 네임스페이스 + localhost |
| 2 | **파드 ↔ 파드** (같은/다른 노드) | CNI 플러그인 (veth + 브릿지, 오버레이/BGP/클라우드 네이티브) |
| 3 | **파드 ↔ 서비스** | kube-proxy (iptables/IPVS 규칙으로 Service ClusterIP → 파드 IP 변환) |
| 4 | **외부 ↔ 서비스** | NodePort, LoadBalancer, Ingress 등 |

## 문제 1: 컨테이너 ↔ 컨테이너

같은 파드 안의 컨테이너끼리는 **localhost**로 통신할 수 있어야 한다.

일반적인 Docker 컨테이너는 각자 자기만의 네트워크 네임스페이스를 갖는다. 그런데 쿠버네티스의 파드는 여러 컨테이너가 들어갈 수 있고, 이 컨테이너들이 **하나의 네트워크 네임스페이스를 공유해야 한다**.

이걸 가능하게 하는 게 **pause 컨테이너**다. 파드가 생성되면 가장 먼저 pause 컨테이너가 뜨고, 이 pause가 네트워크 네임스페이스를 만든다. 이후에 뜨는 앱 컨테이너(nginx, sidecar 등)들은 자기만의 네트워크 네임스페이스를 만드는 대신 **pause의 네트워크 네임스페이스에 합류**한다. pause는 사실상 아무 일도 하지 않고(무한 sleep) 네트워크 네임스페이스를 유지하는 역할만 한다. 앱 컨테이너가 죽었다가 재시작되어도 pause가 살아 있으면 네트워크 네임스페이스(IP, 라우팅 테이블)가 유지된다.

CNI가 구현해야 할 네트워킹 요구사항이라기보다는, 쿠버네티스 공식 문서의 [파드 모델](https://kubernetes.io/docs/concepts/workloads/pods/#how-pods-manage-multiple-containers)에서 "Containers within a Pod share network namespace including the IP address and network ports"로 명시된 **파드 정의 자체에 내포된 전제**다.

## 문제 2: 파드 ↔ 파드

쿠버네티스 네트워킹의 **핵심 문제**다. 쿠버네티스 [공식 문서](https://kubernetes.io/docs/concepts/services-networking/#the-kubernetes-network-model)는 파드 네트워크에 다음을 요구한다:

1. **모든 파드는 같은 노드든 다른 노드든, NAT 없이 다른 모든 파드와 직접 통신할 수 있어야 한다**
2. **노드의 에이전트(kubelet 등 시스템 데몬)는 동일한 노드의 모든 파드와 통신할 수 있어야 한다**

> All pods can communicate with all other pods, whether they are on the same node or on different nodes. Pods can communicate with each other directly, without the use of proxies or address translation (NAT).

핵심은 요구사항 1이다. 같은 노드뿐 아니라 **다른 노드에 있는 파드까지** NAT 없이 도달 가능해야 한다. 이 요구사항이 바로 아래에서 다룰 ["NAT 없이"](#핵심-원칙-nat-없이) 원칙의 근거다.

> **참고**: [AWS EKS Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/networking.html#kubernetes-networking-model)에서는 이를 세 가지로 나누어 기술한다 — 1. 같은 노드 파드 간 NAT 없이, 2. 시스템 데몬과 파드 간 통신, 3. host network를 사용하는 파드가 다른 노드의 파드와 NAT 없이 통신. 공식 문서의 요구사항 1이 같은/다른 노드를 모두 포함하므로, 본질적으로 같은 내용이다.

공식 문서는 이 요구사항과 함께 "every Pod in a cluster gets its own unique cluster-wide IP address"라는 원칙을 명시한다. 이를 통해 파드를 VM이나 물리 호스트처럼 포트 할당, 네이밍, 서비스 디스커버리, 로드 밸런싱 관점에서 동일하게 다룰 수 있다.

이 문제의 해결 방식은 세 가지다:

- **오버레이** (Flannel VXLAN 등): 파드 패킷을 노드 IP로 캡슐화하여 터널링
- **BGP** (Calico BGP 모드): 라우팅 정보를 물리 네트워크에 직접 전파
- **클라우드 네이티브 라우팅** (AWS VPC CNI): 파드에게 인프라가 라우팅 가능한 IP를 부여

세 방식 모두 파드 간 통신에서 src/dst IP가 한 번도 변하지 않는다. 방법만 다를 뿐 "NAT 없이 파드 IP로 직접 통신"이라는 결과는 동일하다. [다음 글]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %})에서 각 방식을 상세히 다룬다.

> AWS VPC CNI의 [설계 문서(Proposal)](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/cni-proposal.md)는 쿠버네티스의 기본 요구사항에 더해, 파드 네트워킹이 EC2 수준의 처리량과 지연을 제공해야 하고, VPC Flow Logs/라우팅 정책/보안 그룹을 파드 트래픽에도 적용할 수 있어야 한다는 추가 목표를 정의한다. 이 시리즈에서 이 목표가 어떻게 달성되는지 살펴본다.

## 문제 3: 파드 ↔ 서비스

파드 IP는 파드가 죽으면 사라진다. 안정적인 엔드포인트를 제공하기 위해 쿠버네티스는 **Service**라는 추상화를 둔다. kube-proxy가 iptables/IPVS 규칙으로 Service의 ClusterIP를 실제 파드 IP로 변환(DNAT)한다.

문제 2(파드 간 통신)가 풀려야 이 DNAT 이후의 실제 파드 도달이 가능하다. Service는 파드 간 통신 **위에** 얹히는 추상화 계층이다.

## 문제 4: 외부 ↔ 서비스

클러스터 외부의 클라이언트가 클러스터 내부의 서비스에 접근하는 문제다. NodePort, LoadBalancer, Ingress 등이 이를 해결한다. 역시 문제 2가 기반이다.

<br>

# 핵심 원칙: "NAT 없이"

4가지 문제를 관통하는 키워드는 **"NAT 없이"**다. 이 말의 무게를 이해하려면 NAT의 본질부터 짚어야 한다.

## NAT이란

NAT(Network Address Translation)은 패킷이 네트워크 경계를 넘을 때, **패킷의 IP 헤더를 열어서 출발지/목적지 IP를 다른 값으로 변경**하는 L3 계층의 주소 변조 기술이다. ([NAT 개념 참고]({% post_url 2026-02-09-Dev-VirtualBox-Network %}#nat란))

- **SNAT (Source NAT)**: **출발지 IP**를 변경한다. 가장 대표적인 용도는 사설 네트워크에서 외부로 나가는 것이다. 사설 IP 대역(10.x, 172.16.x, 192.168.x)은 인터넷에서 라우팅되지 않는다. SNAT 없이 사설 IP가 출발지인 패킷이 밖으로 나가면, 응답 패킷의 목적지가 사설 IP가 되어 **인터넷 상에서 돌아올 경로가 없다**. 엄밀히 말하면 "나갈 수는 있지만 응답이 올 수 없으니" 실질적으로 통신이 불가능하다. 집에서 공유기를 쓸 때 내 PC의 사설 IP(192.168.0.10)가 공유기를 나가면서 공인 IP로 바뀌는 것이 SNAT의 전형적인 예시다.

  ```
  [원본 패킷]  src=192.168.1.10   dst=93.184.216.34
    ↓ SNAT 적용
  [변조 패킷]  src=203.0.113.5    dst=93.184.216.34   ← 출발지 IP가 공인 IP로 바뀜
  ```

- **DNAT (Destination NAT)**: **목적지 IP**를 변경한다. 외부에서 내부로 들어올 때 사용한다. 외부 클라이언트가 `공인 IP:포트`로 요청하면, 그 목적지를 내부 `사설 IP:포트`로 바꿔 내부 장비에 전달한다.

  ```
  [원본 패킷]  src=203.0.113.50  dst=192.168.1.10:8080
       ↓ DNAT 적용
  [변조 패킷]  src=203.0.113.50  dst=172.17.0.2:80       ← 목적지 IP:포트가 바뀜
  ```

> **참고**: SNAT의 가장 대표적인 용도는 "사설 → 공인" 방향의 통신을 가능하게 하는 것이지만, SNAT 자체는 "출발지 IP를 변경하는 것"이므로 공인→공인, 사설→사설 변환에도 사용될 수 있다. DNAT도 마찬가지다.


## "NAT 없이"의 의미

이것이 왜 중요한 대원칙인지, 왜 어려운 일인지 생각해 보자.

집 공유기를 떠올려 보면, 같은 공유기에 연결된 내 PC와 엄마 PC는 NAT 없이 통신한다. 공유기 내부 스위치가 L2로 처리하기 때문이다. 하지만 내 PC가 **공유기 밖** — 인터넷 너머의 외부 서버 — 과 통신하려면 NAT이 필요하다. 공유기 경계를 넘는 순간, 사설 IP로는 도달할 수 없기 때문이다.

쿠버네티스 네트워킹 모델이 요구하는 것은, **수백~수천 개의 파드가 여러 노드에 흩어져 있는데도, 마치 거대한 하나의 공유기 안에 있는 것처럼 동작해야 한다**는 것이다. 노드 경계를 넘어서도 NAT 없이. 일종의 **flat network** 요구다.

> **참고: flat network** — 모든 노드가 같은 L2/L3 도메인에 있어서, 별도의 NAT이나 터널링 없이 서로 직접 통신 가능한 네트워크. 쿠버네티스 네트워킹 모델이 요구하는 것과 정확히 부합한다.

다만 "NAT 없이"라는 대원칙은 **파드 ↔ 파드 직접 통신 경로(인프라 계층)**에 한정된다. 구체적으로, 파드 A가 파드 B에게 패킷을 보낼 때 그 경로의 **어느 지점에서도 IP가 변조되면 안 된다**는 것이다. SNAT이든 DNAT이든 하나라도 있으면 "NAT 없이"를 충족하지 못한다.

```
파드 A(10.244.1.2) → 파드 B(10.244.1.3)로 HTTP 요청

[요청]
  파드 A가 보낸 패킷:  src=10.244.1.2  dst=10.244.1.3
  파드 B가 받은 패킷:  src=10.244.1.2  dst=10.244.1.3  ← 동일해야 함

[응답]
  파드 B가 보낸 응답:  src=10.244.1.3  dst=10.244.1.2
  파드 A가 받은 응답:  src=10.244.1.3  dst=10.244.1.2  ← 동일해야 함
```

요청과 응답 양방향 모두에서 src/dst IP가 **한 번도 변하지 않아야** 한다는 것이다. 즉:

- 파드 B 입장에서 "이 요청은 10.244.1.2에서 왔다"고 정확히 인식할 수 있어야 한다
- 파드 A 입장에서 "이 응답은 10.244.1.3에서 왔다"고 정확히 인식할 수 있어야 한다

모든 파드가 마치 하나의 거대한 스위치에 연결된 것처럼, 자기 IP로 직접 식별되고 직접 통신할 수 있어야 한다.

## 원칙의 적용 범위

"NAT 없이" 원칙은 **문제 2(파드 ↔ 파드 직접 통신)**에만 적용된다. 문제 3, 4에서는 NAT이 사용되지만, 이것은 원칙에 위배되지 않는다.

**Service DNAT (문제 3: 파드 ↔ 서비스)**

kube-proxy가 Service ClusterIP를 실제 파드 IP로 변환하는 DNAT을 수행한다. **위배되지 않는다.** 요구사항이 말하는 "NAT 없이"는 **파드 ↔ 파드 직접 통신 경로(인프라 계층)**에 대한 것이고, Service는 그 위의 **상위 추상화 계층**이기 때문이다. 실제로 [엔드포인트 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-07-Public-Public-Endpoint %}#핵심-발견-노드-프로세스-vs-pod의-경로-차이)에서 확인했던 것처럼, Pod가 kubernetes Service의 ClusterIP(10.100.0.1)로 요청하면 kube-proxy의 iptables가 파드 IP로 DNAT하는 것도 이 Service 추상화 계층의 동작이다.

**외부 통신 SNAT (문제 4 영역: 파드 → 인터넷)**

파드가 클러스터 외부(인터넷)와 통신할 때, 노드 IP(또는 NAT Gateway IP)로 SNAT하는 것도 **위배되지 않는다.** "NAT 없이" 원칙은 **파드 ↔ 파드 직접 통신**에만 적용되며, 외부 통신은 그 범위 밖이다.

이것은 CNI 방식과 무관한 **기능적 필수**다:

- **오버레이/BGP**: 파드 대역(10.244.x.x)은 클러스터 내부에서만 의미 있는 사설 IP다. 인터넷 라우터가 이 대역을 모르므로 응답 패킷이 돌아올 경로가 없다.
- **클라우드 네이티브(VPC CNI)**: 파드 IP가 VPC 대역이라 VPC 안에서는 라우팅되지만, VPC 밖(인터넷)에서는 여전히 사설 IP다.

어느 CNI든 파드의 외부 통신에는 SNAT이 필요하다. 커널의 netfilter POSTROUTING 체인에서 "목적지가 파드/클러스터 대역이 아닌 트래픽"에 대해서만 SNAT이 적용되며, 파드 간 직접 통신은 이 규칙에 매칭되지 않아 NAT 없이 그대로 전달된다.

**정리**: "NAT 없이" 원칙이 보호하는 것은 **문제 2(파드 ↔ 파드)**의 직접 통신 경로다. 문제 3(Service DNAT)과 문제 4 영역(외부 SNAT)의 NAT은 이 원칙과 다른 계층/범위에서 동작하며, 파드 간 통신의 투명성을 훼손하지 않는다.

<br>

# 정리

이 글에서는 쿠버네티스 네트워킹의 전체 그림을 잡았다. 4가지 문제의 구조와, "NAT 없이" 원칙이 어디까지 적용되는지를 정리했다.

다음 글부터 각 문제를 구체적으로 풀어 나간다:

- [파드 간 통신]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %}): 문제 2의 세 가지 해결 방식 (오버레이, BGP, 클라우드 네이티브)
- [Service와 kube-proxy]({% post_url 2026-03-19-Kubernetes-EKS-02-00-02-Kubernetes-Networking-Service %}): 문제 3의 해결 — Service 추상화와 kube-proxy 동작 모드
- [AWS VPC CNI — IP 관리]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}): 클라우드 네이티브 방식의 구체적 구현 (ipamd, 웜 풀, 설정 조합)
- 이후 실습에서 검증

<br>
