---
title: "[EKS] EKS: Networking - 4. 파드 간 통신"
excerpt: "VPC CNI가 파드 네트워크를 구성하는 와이어링 과정과 파드 간 패킷 흐름을 tcpdump로 추적해 보자."
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
  - VPC-CNI
  - CNI
  - Policy-Routing
  - tcpdump
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- VPC CNI Plugin은 파드 생성 시 **7단계 와이어링**(veth pair 생성 → 파드 네임스페이스 이동 → `/32` IP 할당 → link-local 게이트웨이 → static ARP → 호스트 라우트 → ip rule)을 수행한다
- [이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-01-Installation-Result %})에서 관찰한 파드 내부 구조(`eth0 /32`, `169.254.1.1` 게이트웨이, 호스트 라우트)가 이 와이어링의 결과물이다
- `169.254.1.1`은 실제로 존재하지 않는 **link-local 주소**다. static ARP로 veth 호스트 측 MAC 주소를 주입해 게이트웨이처럼 동작시킨다
- Secondary ENI에 할당된 파드는 **policy routing**(`ip rule` + ENI별 라우팅 테이블)으로 올바른 ENI를 통해 송신한다
- tcpdump로 확인하면 **파드 IP가 경로 전체에서 한 번도 변환되지 않는다** — VPC CNI의 "NAT 없는 통신"

<br>

# 들어가며

이전 글([EKS: Networking - 3. 실습 환경 네트워크 확인]({% post_url 2026-03-19-Kubernetes-EKS-02-02-01-Installation-Result %}))에서 테스트 파드를 배포하고, 파드 내부 네트워크를 확인하고, 크로스 노드 ping이 동작하는 것까지 확인했다. 이 글에서는 한 발 더 들어가 파드 간 통신이 어떻게 이뤄지는지 살펴 본다.

- VPC CNI Plugin이 파드 네트워크를 **구성하는 과정** (와이어링)
- 파드 간 패킷이 **흐르는 경로** (policy routing)
- **tcpdump**로 실제 패킷 흐름을 검증한다

<br>

# CNI 와이어링

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-01-Installation-Result %}#파드-내부-네트워크-확인)에서 파드 내부를 확인했을 때 다음과 같은 결과가 나왔다.

- `eth0`에 `/32` IP 할당 (예: `192.168.2.151/32`)
- 기본 게이트웨이 `169.254.1.1` (link-local)
- 호스트에는 파드 IP로의 호스트 라우트 (예: `192.168.2.151 dev eniac70eec268d scope link`)

모두 CNI Plugin이 파드 생성 시 수행하는 와이어링의 결과물이다.

## VPC CNI Plugin Sequence

AWS VPC CNI의 [설계 문서(Proposal)](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/cni-proposal.md)에 정의된 와이어링 순서다.

```bash
# 1. L-IPAMD가 인스턴스에 할당한 보조 IP를 받아 온다

# 2. veth pair를 생성하고, 한쪽은 호스트 네임스페이스에, 다른 한쪽은 파드 네임스페이스에 연결한다
ip link add veth-1 type veth peer name veth-1c
ip link set veth-1c netns ns1
ip link set veth-1 up
ip netns exec ns1 ip link set veth-1c up

# 3. 파드 네임스페이스 안에서 IP를 할당하고, 게이트웨이와 라우트를 설정한다
ip netns exec ns1 ip addr add 20.0.49.215/32 dev veth-1c
ip netns exec ns1 ip route add 169.254.1.1 dev veth-1c
ip netns exec ns1 ip route add default via 169.254.1.1 dev veth-1c

# 4. 게이트웨이(169.254.1.1)의 MAC을 veth 호스트 측 MAC으로 고정한다
ip netns exec ns1 arp -i veth-1c -s 169.254.1.1 <veth-1's MAC>

# 5. 호스트 측에서 파드 IP로의 호스트 라우트와 ip rule을 추가한다
ip route add 20.0.49.215/32 dev veth-1
ip rule add from all to 20.0.49.215/32 table main prio 512

# 6. 파드 IP가 Secondary ENI에 속하는 경우, from-pod rule도 추가한다
ip rule add from 20.0.49.215/32 table 2 prio 1536
```


## 실습 결과와의 대조

각 단계가 어떤 결과를 만들어내는지 이전 글의 [파드 내부 네트워크 확인]({% post_url 2026-03-19-Kubernetes-EKS-02-02-01-Installation-Result %}#파드-내부-네트워크-확인) 및 [네트워크 변화 확인]({% post_url 2026-03-19-Kubernetes-EKS-02-02-01-Installation-Result %}#네트워크-변화-확인) 결과와 대조해 보자.


| 단계 | 와이어링 명령 | 실습 결과 |
|------|-------------|---------------------|
| veth pair 생성 | `ip link add veth-1 type veth peer name veth-1c` | 호스트: `eni73af7ba7811@if3`, 파드: `eth0@if5` |
| 네임스페이스 이동 | `ip link set veth-1c netns ns1` | `ip link`에서 `link-netns cni-f6c99138...` 표시 |
| IP 할당 (`/32`) | `ip addr add .../32 dev veth-1c` | 파드 안: `inet 192.168.11.173/32 scope global eth0` |
| 게이트웨이 설정 | `ip route add default via 169.254.1.1` | 파드 안: `default via 169.254.1.1 dev eth0` |
| 호스트 라우트 | `ip route add .../32 dev veth-1` | 호스트: `192.168.11.173 dev eni73af7ba7811 scope link` |
| to-pod rule | `ip rule add from all to .../32 table main` | `ip rule`: `512: from all to 192.168.4.248 lookup main` |

CNI Plugin이 실행한 명령의 결과가 그대로 관찰된다.

대부분의 단계는 직관적이지만, 한 가지 의문이 남는다. 게이트웨이로 설정된 `169.254.1.1`은 어디에도 할당되지 않은 IP다. 실제로 존재하지 않는 주소가 어떻게 게이트웨이 역할을 할 수 있는 걸까.

## 169.254.1.1: link-local 게이트웨이

핵심은 와이어링 4단계의 **static ARP**다.

```bash
ip netns exec ns1 arp -i veth-1c -s 169.254.1.1 <veth-1's MAC>
```

이 명령이 파드의 ARP 테이블에 `169.254.1.1 → veth 호스트 측 MAC`을 고정한다. 파드가 패킷을 보낼 때 게이트웨이 `169.254.1.1`의 MAC을 ARP 요청 없이 곧바로 알 수 있으므로, veth의 호스트 측으로 L2 프레임을 직접 전달한다.

이런 방식을 쓰는 이유는 다음과 같다:

- **/32 서브넷**: 파드 IP가 `/32`로 할당되므로 같은 서브넷에 다른 호스트가 없다. 일반적인 게이트웨이 IP를 사용할 수 없다
- **충돌 방지**: `169.254.0.0/16`은 [Link-Local](https://www.rfc-editor.org/rfc/rfc3927) 대역으로, VPC의 실제 IP와 절대 충돌하지 않는다
- **단순성**: 모든 파드가 동일한 게이트웨이 주소를 사용하므로 CNI 로직이 단순해진다

> AWS VPC CNI만의 방식은 아니다. Calico도 동일한 link-local 게이트웨이 패턴을 사용한다.

<br>

# Policy Routing

## ENI별 라우팅이 필요한 이유

VPC는 ENI를 통과하는 패킷의 소스 IP가 해당 ENI에 할당된 IP인지 검사한다(**소스/목적지 검사**). Secondary ENI(ens6)에 할당된 보조 IP를 가진 파드가 Primary ENI(ens5)를 통해 패킷을 보내면 VPC가 드롭한다.

이 문제를 해결하기 위해 VPC CNI는 **policy routing**을 설정한다. 각 ENI마다 별도의 라우팅 테이블을 만들고, `ip rule`로 "이 IP에서 나가는 트래픽은 이 테이블을 써라"고 지정한다.

## ip rule 확인

노드 1(192.168.4.12)에서 확인한 routing policy database를 살펴 보자.

```bash
ip rule
```

```
0:      from all lookup local
512:    from all to 192.168.5.1 lookup main
512:    from all to 192.168.4.248 lookup main
1024:   from all fwmark 0x80/0x80 lookup main
32765:  from 192.168.7.41 lookup 2
32766:  from all lookup main
32767:  from all lookup default
```

우선순위별로 정리하면 다음과 같다.

| 우선순위 | 규칙 | 의미 |
|---------|------|------|
| 0 | `from all lookup local` | 로컬 주소 매칭 (기본) |
| 512 | `to 192.168.5.1 lookup main` | coredns 파드로 가는 트래픽 → main 테이블 |
| 512 | `to 192.168.4.248 lookup main` | netshoot 파드로 가는 트래픽 → main 테이블 |
| 1024 | `fwmark 0x80/0x80 lookup main` | SNAT 마킹된 트래픽 → main 테이블 |
| 32765 | `from 192.168.7.41 lookup 2` | ENI1(ens6) IP에서 나가는 트래픽 → table 2 |
| 32766 | `from all lookup main` | 나머지 전부 → main 테이블 |

**to-pod 규칙**(우선순위 512)이 가장 먼저 매칭되어 파드로 들어오는 트래픽을 main 테이블로 라우팅한다. main 테이블에는 파드별 호스트 라우트(`192.168.4.248 dev eni31b43252b24 scope link`)가 있으므로 올바른 veth pair로 전달된다.

## ENI별 라우팅 테이블

`ip rule`이 "어떤 테이블을 볼지"를 정하는 규칙이라면, 실제로 그 테이블 안에 어떤 경로가 들어 있는지도 확인해야 한다.

```bash
ip route show table main
```

```
default via 192.168.4.1 dev ens5 proto dhcp src 192.168.4.12 metric 512
192.168.0.2 via 192.168.4.1 dev ens5 proto dhcp src 192.168.4.12 metric 512
192.168.4.0/22 dev ens5 proto kernel scope link src 192.168.4.12 metric 512
192.168.4.1 dev ens5 proto dhcp scope link src 192.168.4.12 metric 512
192.168.4.248 dev eni31b43252b24 scope link
192.168.5.1 dev enifdec4b696ce scope link
```

```bash
ip route show table 2
```

```
default via 192.168.4.1 dev ens6
192.168.4.1 dev ens6 scope link
```

table 2는 ens6을 통해 나가는 경로만 갖고 있다. `from 192.168.7.41 lookup 2` 규칙에 의해, ens6의 IP에서 출발하는 트래픽은 이 테이블을 사용하여 ens6을 통해 나간다.

현재 실습 환경에서는 두 파드(coredns, netshoot) 모두 ENI0(ens5)의 보조 IP를 사용하므로, ENI1 전용 from-pod 규칙(`from <pod_ip> lookup 2 prio 1536`)은 아직 보이지 않는다. 이후 ENI1의 보조 IP가 파드에 할당되면 해당 규칙이 자동으로 추가된다.

> 와이어링 마지막 단계(`ip rule add from 20.0.49.215/32 table 2 prio 1536`)가 바로 이 from-pod 규칙이다. CNI Plugin이 파드 IP가 어느 ENI에 속하는지 판단하여 필요한 경우에만 추가한다.

<br>

# 파드 간 통신 흐름

## 같은 노드 내 통신

같은 노드에 있는 두 파드 간 통신은 호스트의 라우팅만으로 완결된다.

```
파드A (eth0) → veth pair → 호스트 라우팅 테이블 → veth pair → 파드B (eth0)
```

1. 파드A가 파드B의 IP로 패킷을 보내면 기본 게이트웨이 `169.254.1.1`(= veth 호스트 측)로 전달
2. 호스트의 main 테이블에서 `파드B_IP dev eniXXX scope link` 매칭
3. 해당 veth pair를 통해 파드B의 네임스페이스로 전달

VPC 밖으로 나가지 않으므로 ENI도 거치지 않는다.

## 크로스 노드 통신

다른 노드에 있는 파드 간 통신은 VPC 라우팅 패브릭을 거친다. 이전 글의 환경을 기준으로, 파드 1(192.168.2.151, 노드 2)에서 파드 2(192.168.4.248, 노드 1)로 ping을 보내는 경우:

![크로스 노드 파드 간 통신 구조]({{site.url}}/assets/images/eks-w2-networking-pod-to-pod-structure.png){: .align-center}

각 노드의 파드 네임스페이스, veth pair, 호스트 네임스페이스(ENI), 서브넷 게이트웨이, VPC 라우팅까지의 전체 경로가 표현되어 있다. 단계별로 보면:

1. **파드 1 → veth**: 파드 1이 `192.168.4.248`로 패킷 전송. 기본 게이트웨이 `169.254.1.1`(= veth 호스트 측 MAC)로 L2 전달
2. **노드 2 라우팅**: 호스트의 main 테이블에 `192.168.4.248`에 대한 호스트 라우트가 **없다**(다른 노드의 파드이므로). `default via 192.168.0.1 dev ens5`를 타고 ENI0을 통해 VPC로 나간다
3. **VPC 라우팅**: VPC 라우팅 테이블이 `192.168.4.248`을 노드 1의 ENI로 전달한다. VPC CNI에서 파드 IP는 ENI의 보조 IP이므로, VPC가 해당 ENI의 위치를 알고 있다
4. **노드 1 수신**: 패킷이 ENI0(ens5)으로 도착. `ip rule`의 `512: from all to 192.168.4.248 lookup main`이 매칭
5. **호스트 → veth**: main 테이블의 `192.168.4.248 dev eni31b43252b24 scope link`로 veth pair를 통해 파드 2에 전달

이 과정에서 패킷의 **소스 IP(192.168.2.151)**와 **목적지 IP(192.168.4.248)**는 한 번도 변하지 않는다. NAT도 오버레이 캡슐화도 없다.

<br>

# tcpdump 검증

실제로 패킷이 위 경로를 따르는지 tcpdump로 확인한다. **수신 노드**(노드 1, 파드 2가 있는 노드)에서 인터페이스별로 캡처한다. 하나의 인터페이스에서만 잡으면 "패킷이 도착했다"는 사실만 알 수 있지만, ENI(ens5, ens6)와 veth를 각각 따로 잡으면 **패킷이 어떤 경로로 흘러가는지**(어느 ENI로 들어와서 어느 veth로 전달되는지) 정확히 추적할 수 있다.

## 캡처 방법

파드 1(노드 2)에서 파드 2(노드 1)로 `ping -c 2`를 보내면서, 노드 1에서 인터페이스별로 tcpdump를 실행한다.

```bash
# 전체 인터페이스
sudo tcpdump -i any -nn icmp

# ENI0 (Primary)
sudo tcpdump -i ens5 -nn icmp

# ENI1 (Secondary)
sudo tcpdump -i ens6 -nn icmp

# 파드2의 veth pair (호스트 측)
sudo tcpdump -i eni31b43252b24 -nn icmp
```

## 인터페이스별 결과

### 전체 인터페이스 (`-i any`)

```
16:34:02.537302 ens5  In  IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 3, seq 1, length 64
16:34:02.537366 eni31b43252b24 Out IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 3, seq 1, length 64
16:34:02.537379 eni31b43252b24 In  IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 3, seq 1, length 64
16:34:02.537386 ens5  Out IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 3, seq 1, length 64
16:34:03.538413 ens5  In  IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 3, seq 2, length 64
16:34:03.538443 eni31b43252b24 Out IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 3, seq 2, length 64
16:34:03.538458 eni31b43252b24 In  IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 3, seq 2, length 64
16:34:03.538468 ens5  Out IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 3, seq 2, length 64
```

8개 패킷이 캡처되었다. `ping -c 2`이므로 ICMP 요청 2개 + 응답 2개 = 4개인데, `-i any`는 패킷이 통과하는 **모든 인터페이스에서** 잡으므로 ens5에서 4개 + veth에서 4개 = 8개다.

한 패킷의 수신 경로를 타임스탬프로 추적해 보면, 요청이 `ens5 In → veth Out`으로 흐르고, 응답이 `veth In → ens5 Out`으로 나간다. 앞서 설명한 크로스 노드 통신 경로와 정확히 일치한다.

| 시간 | 인터페이스 | 방향 | 의미 |
|------|-----------|------|------|
| .537302 | ens5 | In | VPC에서 ENI0으로 도착 |
| .537366 | eni31b43252b24 | Out | 호스트 → veth → 파드로 전달 |
| .537379 | eni31b43252b24 | In | 파드가 응답, veth → 호스트 |
| .537386 | ens5 | Out | 호스트 → ENI0 → VPC로 송신 |



### ENI0 (`-i ens5`)

```
16:34:51.424926 IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 4, seq 1, length 64
16:34:51.424992 IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 4, seq 1, length 64
16:34:52.458979 IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 4, seq 2, length 64
16:34:52.459035 IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 4, seq 2, length 64
```

4개 패킷. 요청 2개가 ens5로 들어오고, 응답 2개가 ens5로 나간다. 파드 2의 IP(`192.168.4.248`)가 **ENI0의 보조 IP**이므로 ens5를 통과하는 것이 정상이다.

### ENI1 (`-i ens6`)

```
(캡처 없음 — 0개)
```

파드 2의 IP가 ENI1 소속이 아니므로 ens6을 통과하는 ICMP 패킷이 없다. Policy routing이 올바르게 동작하고 있다는 증거이기도 하다.

### 파드 veth (`-i eni31b43252b24`)

```
16:38:30.894643 IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 7, seq 1, length 64
16:38:30.894655 IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 7, seq 1, length 64
16:38:31.899026 IP 192.168.2.151 > 192.168.4.248: ICMP echo request, id 7, seq 2, length 64
16:38:31.899047 IP 192.168.4.248 > 192.168.2.151: ICMP echo reply, id 7, seq 2, length 64
```

4개 패킷. veth pair를 통해 파드로 들어가고 나오는 트래픽만 캡처된다.

## 결과 종합

| 인터페이스 | 캡처 패킷 수 | 의미 |
|-----------|-------------|------|
| `-i any` | 8개 | ens5(4) + veth(4) 합산 |
| `-i ens5` (ENI0) | 4개 | VPC ↔ 노드 구간 |
| `-i ens6` (ENI1) | 0개 | 파드 IP가 ENI0 소속이라 미통과 |
| `-i eni31b43252b24` (veth) | 4개 | 노드 ↔ 파드 구간 |

모든 캡처에서 **소스 IP(`192.168.2.151`)와 목적지 IP(`192.168.4.248`)가 그대로 찍혀 있다**. 오버레이 CNI(예: Flannel VXLAN)라면 `tcpdump -i ens5`에서 파드 IP 대신 노드 IP가 보일 것이다. VPC CNI에서는 파드 IP가 VPC의 실제 IP이므로 변환 없이 그대로 전달된다.

<br>

# 정리

| 구성 요소 | 역할 |
|-----------|------|
| veth pair | 파드 네임스페이스 ↔ 호스트 네임스페이스 연결 |
| `/32` IP 할당 | point-to-point 파드 IP 설정 |
| `169.254.1.1` + static ARP | link-local 가상 게이트웨이 |
| 호스트 라우트 (`dev eniXXX scope link`) | 파드 IP → veth pair 매핑 |
| `ip rule` to-pod (prio 512) | 파드로 향하는 트래픽을 main 테이블로 라우팅 |
| `ip rule` from-pod (prio 1536) | Secondary ENI 파드의 송신 트래픽을 올바른 ENI로 라우팅 |
| VPC 라우팅 패브릭 | 크로스 노드 파드 통신을 ENI 보조 IP 기반으로 직접 전달 |

VPC CNI는 파드에게 VPC의 실제 IP를 부여하고, veth + 호스트 라우트 + policy routing으로 패킷 경로를 구성한다. 그 결과 오버레이나 NAT 없이 파드 간 직접 통신이 가능하다. tcpdump 결과에서 확인했듯이 패킷은 출발지부터 목적지까지 **파드 IP 그대로** 전달된다.

<br>
