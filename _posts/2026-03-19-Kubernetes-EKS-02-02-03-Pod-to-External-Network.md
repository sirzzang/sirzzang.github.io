---
title: "[EKS] EKS: Networking - 4. 파드와 외부 간 통신"
excerpt: "VPC CNI 환경에서 파드가 인터넷과 통신할 때 SNAT이 어떻게 동작하는지 tcpdump와 iptables로 확인한다."
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
  - SNAT
  - iptables
  - tcpdump
  - conntrack
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 파드의 외부 통신은 **두 가지로 나뉜다**: `hostNetwork: true` 파드는 노드 IP를 그대로 쓰므로 SNAT이 불필요하고, 일반 파드는 VPC 사설 IP를 쓰므로 SNAT이 필요하다
- 어느 쪽이든 쿠버네티스 "NAT 없이" 원칙에 위배되지 않는다 — 원칙은 파드 간 직접 통신에만 적용된다
- VPC CNI는 기본적으로 iptables `AWS-SNAT-CHAIN-0`에서 파드 IP → 노드 Primary ENI IP로 SNAT한다
- tcpdump에서 **veth는 파드 IP**, **ens5는 노드 IP**가 찍힌다 — 그 사이에서 SNAT이 일어난다
- `EXTERNAL_SNAT=true` 설정으로 VPC CNI의 SNAT을 끌 수 있다. Private subnet + NAT Gateway 구조에서는 이중 SNAT을 방지하기 위해 이 설정을 권장한다

<br>

# 들어가며

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %})에서 파드 간 통신이 VPC CNI의 와이어링과 policy routing으로 NAT 없이 동작하는 것을 확인했다. 파드 IP가 출발지부터 목적지까지 한 번도 변하지 않았다.

그런데 파드가 클러스터 **외부**(인터넷)와 통신할 때는 상황이 다르다. 파드 IP는 VPC의 사설 IP이므로 인터넷에서는 응답이 돌아올 수 없다. **SNAT이 필요하다.**

이 글에서는 아래 내용에 대해 알아 본다. 

- Host Networking처럼 SNAT이 불필요한 경우와 일반 파드처럼 SNAT이 필요한 경우의 구분
- SNAT이 필요할 때, VPC CNI가 iptables로 이를 어떻게 구현하는지
- tcpdump로 SNAT 전후를 비교
- `EXTERNAL_SNAT` 설정으로 SNAT 동작을 제어하는 방법

<br>

# 외부 통신과 SNAT

[쿠버네티스 네트워킹 모델]({% post_url 2026-03-19-Kubernetes-EKS-02-00-00-Kubernetes-Networking-Model %}#원칙의-적용-범위)에서 정리한 것처럼, "NAT 없이" 원칙은 **파드 ↔ 파드 직접 통신**에만 적용된다. 파드가 클러스터 외부와 통신할 때 SNAT을 적용하는 것은 원칙 위반이 아니다. 다만 모든 파드가 SNAT을 필요로 하는 것은 아니다. 파드의 네트워크 모드에 따라 SNAT 필요 여부가 갈린다.

| 네트워크 모드 | 파드 IP | SNAT 필요 여부 | 이유 |
|--------------|---------|---------------|------|
| `hostNetwork: true` | 노드 IP | 불필요 | 이미 노드 IP를 사용하므로 변환할 것이 없음 |
| 일반 파드 | VPC 사설 IP | **필요** | 사설 IP로는 인터넷 응답이 돌아올 수 없음 |


## Host Networking: SNAT이 불필요한 경우

`hostNetwork: true`로 설정된 파드는 별도의 네트워크 네임스페이스 없이 **노드의 네트워크 스택을 직접 사용**한다. 파드 IP가 곧 노드 IP이므로 IP 변환 자체가 필요 없다.

대표적인 Host Networking 파드는 기존 클러스터 구성 확인 시 이미 여러 차례 살펴 봤다:

| 파드 | 역할 |
|------|------|
| `kube-proxy` | Service iptables/ipvs 규칙 관리 |
| `aws-node` (VPC CNI) | ENI 관리, IP 할당, iptables SNAT 규칙 설정 |

이 파드들이 외부와 통신할 때 패킷의 소스 IP는 이미 노드 IP다. 노드가 인터넷에 도달 가능하면(public IP + IGW, 또는 NAT Gateway 경유) 추가 SNAT 없이 그대로 통신할 수 있다.


## 일반 파드: SNAT이 필요한 경우

Host Networking이 아닌 일반 파드는 고유한 네트워크 네임스페이스를 가지고, VPC CNI가 할당한 VPC 대역의 사설 IP(예: `192.168.4.248`)를 사용한다. 이 IP는 VPC 안에서는 라우팅되지만, VPC 밖(인터넷)에서는 사설 IP이므로 **응답 패킷이 돌아올 경로가 없다**. 따라서 파드가 외부와 통신하려면 공인 IP를 가진 지점에서 SNAT이 일어나야 한다.

<br>

# VPC CNI의 SNAT: 기본 동작

일반 파드의 외부 통신에 SNAT이 필요하다면, 이를 누가, 어떻게 수행하는가? VPC CNI는 **기본적으로** 노드의 iptables에 SNAT 규칙을 설정하여 직접 처리한다.

<!--TODO: 쿠버네티스 서비스 기본 글 완성 시 참조할 것. vpc cni도 iptables 변경하기 때문에 -->

## iptables 규칙

AWS VPC CNI의 [설계 문서(Proposal)](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/cni-proposal.md)에 정의된 NAT 규칙 원형은 다음과 같다:

```bash
-A POSTROUTING ! -d <VPC-CIDR> -m comment --comment "kubernetes: SNAT for outbound traffic from cluster" \
  -m addrtype ! --dst-type LOCAL -j SNAT --to-source <Primary IP on the Primary ENI>
```

핵심 로직은 간단하다:

1. **VPC CIDR 내부 목적지는 RETURN** — 파드 간 통신(같은 VPC)은 SNAT 없이 통과
2. **그 외(외부) 목적지는 SNAT** — 소스 IP를 노드의 Primary ENI IP로 변환

실제 노드에서 확인하면 이 원형이 `AWS-SNAT-CHAIN-0`이라는 별도 체인으로 분리되어 있다:

```bash
# POSTROUTING 체인에서 AWS-SNAT-CHAIN-0으로 점프
-A POSTROUTING -m comment --comment "AWS SNAT CHAIN" -j AWS-SNAT-CHAIN-0

# AWS-SNAT-CHAIN-0 내부
-A AWS-SNAT-CHAIN-0 -d 192.168.0.0/16 -m comment --comment "AWS SNAT CHAIN" -j RETURN
-A AWS-SNAT-CHAIN-0 ! -o vlan+ -m comment --comment "AWS, SNAT" \
  -m addrtype ! --dst-type LOCAL -j SNAT --to-source 192.168.4.12 --random-fully
```

첫 번째 규칙이 VPC CIDR(`192.168.0.0/16`) 내부 트래픽을 걸러내고, 두 번째 규칙이 나머지 트래픽의 소스를 노드 IP(`192.168.4.12`)로 변환한다. `--random-fully`는 SNAT 시 소스 포트를 완전 랜덤으로 선택하여 포트 충돌을 줄인다.

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %}#tcpdump-검증)에서 파드 간 통신을 tcpdump로 확인했을 때 모든 인터페이스에서 파드 IP가 그대로 찍혔던 이유가 바로 이 첫 번째 규칙이다. 목적지가 VPC CIDR 내부(다른 파드)이므로 `RETURN`되어 SNAT이 적용되지 않았던 것이다.

## Host Networking 파드와 SNAT 규칙

앞서 Host Networking 파드는 SNAT이 불필요하다고 했다. iptables 규칙 관점에서 보면 그 이유가 더 명확해진다. `hostNetwork: true` 파드의 소스 IP는 이미 노드 IP다. SNAT 규칙의 `--to-source`도 노드 IP이므로, 규칙에 매칭되더라도 소스 IP가 바뀌지 않는다 — **변환이 일어나지만 결과가 동일**하다. 실질적으로 SNAT이 의미가 없는 셈이다.

<br>

# 통신 흐름

파드에서 외부(예: `8.8.8.8`)로 ping을 보낼 때의 전체 경로를 추적한다. 이전 글의 환경을 기준으로, 노드 1(192.168.4.12, Public: 3.34.254.164)의 netshoot 파드(192.168.4.248)에서 `www.google.com`으로 ping을 보내는 경우:

![파드에서 외부 통신 구조]({{site.url}}/assets/images/eks-w2-networking-pod-to-external-structure.png){: .align-center}

각 노드의 파드 네임스페이스, veth pair, 호스트 네임스페이스(iptables SNAT), ENI, 서브넷 게이트웨이, VPC, IGW까지의 전체 경로가 표현되어 있다. 단계별로 보면:

1. **파드 → veth**: netshoot 파드(`192.168.4.248`)가 `8.8.8.8`로 ping 전송. 기본 게이트웨이 `169.254.1.1`(= veth 호스트 측 MAC)로 L2 전달
2. **iptables SNAT**: 호스트 네임스페이스에서 `AWS-SNAT-CHAIN-0`이 소스 IP를 파드 IP(`192.168.4.248`) → 노드 IP(`192.168.4.12`)로 변환
3. **노드 → 서브넷 게이트웨이**: `default via 192.168.4.1 dev ens5` 경로를 타고 ENI0(ens5)을 통해 서브넷 게이트웨이(`192.168.4.1`)로 나감
4. **VPC → IGW**: VPC 라우팅 테이블에 따라 IGW로 전달. IGW가 노드 private IP(`192.168.4.12`) → public IP(`3.34.254.164`)로 변환
5. **IGW → 인터넷**: public IP로 `www.google.com`에 도달

[이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %}#크로스-노드-통신)의 파드 간 통신에서는 SNAT 없이 파드 IP가 그대로 VPC 패브릭을 타고 상대 노드로 전달됐다. 여기서는 **2단계(iptables SNAT)**와 **4단계(IGW 변환)**에서 소스 IP가 두 번 바뀐다는 것이 핵심 차이다.

<br>

# 패킷 흐름

![pod-to-external-sequence]({{site.url}}/assets/images/eks-proposal-pod-to-external-sequence.png){: .align-center}

<center><sup><a href="https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/cni-proposal.md#life-of-a-pod-to-external-packet">AWS VPC CNI Proposal</a>의 Pod to External 통신 시퀀스. 파드 eth0 → veth → iptables SNAT → 노드 eth0(ens5) → VPC 패브릭 → 인터넷.</sup></center>

예시 IP: 파드 IP = `192.168.4.248`, 노드 private IP = `192.168.4.12`, 노드 public IP = `3.x.x.x`

## 나가는 경로

| 단계 | 구간 | 패킷 IP | 설명 |
|------|------|---------|------|
| 1 | 파드 eth0 | src=`192.168.4.248`, dst=`8.8.8.8` | L3 lookup → 목적지가 서브넷 밖 → default gw(`169.254.1.1`) |
| 2 | eth0 → veth | src=`192.168.4.248`, dst=`8.8.8.8` | [veth pair]({% post_url 2026-03-19-Kubernetes-EKS-02-00-01-Kubernetes-Pod-to-Pod-Networking %}#veth-pair로-네임스페이스-벽을-관통한다)를 통해 노드 네임스페이스로 전달 |
| 3 | veth → **iptables** → ens5 | src=**`192.168.4.12`**, dst=`8.8.8.8` | POSTROUTING `AWS-SNAT-CHAIN-0`에서 소스 IP가 파드 → 노드로 변환 |
| 4 | ens5 → VPC 패브릭 | src=`192.168.4.12`, dst=`8.8.8.8` | VPC 라우팅 테이블에 따라 IGW로 전달 |
| 5 | VPC 패브릭 → 인터넷 | src=**`3.x.x.x`**, dst=`8.8.8.8` | IGW에서 노드 private IP → public IP로 변환 |

## 돌아오는 경로

| 단계 | 구간 | 패킷 IP | 설명 |
|------|------|---------|------|
| 6 | 인터넷 → VPC 패브릭 | src=`8.8.8.8`, dst=`3.x.x.x` | 응답 패킷 |
| 7 | VPC 패브릭 → ens5 | src=`8.8.8.8`, dst=`192.168.4.12` | IGW가 public → private IP로 역변환 |
| 8 | ens5 → **conntrack** → veth | src=`8.8.8.8`, dst=**`192.168.4.248`** | conntrack이 원래 연결(파드 IP)을 기억하고 있어 목적지를 노드 IP → 파드 IP로 복원 |
| 9 | veth → 파드 eth0 | src=`8.8.8.8`, dst=`192.168.4.248` | 파드가 응답 수신 |

핵심은 **3번(SNAT)**과 **8번(역NAT)**이다. 나가는 길에서 파드 IP → 노드 IP로 바뀌고, 돌아오는 길에서 conntrack이 이를 복원한다. 이전 글의 [파드 간 통신]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %}#크로스-노드-통신)에서는 경로 전체에서 IP가 한 번도 바뀌지 않았던 것과 대조된다.

## 주요 사항

- **1~2 파드 → veth → 호스트**: L3 lookup → default gateway(`169.254.1.1`) → veth pair를 통해 노드 네임스페이스에 전달. 여기까지는 파드→파드와 완전히 동일하다.
- **3 SNAT이 일어나는 이유**: `AWS-SNAT-CHAIN-0`에서 목적지(`8.8.8.8`)가 VPC CIDR 밖이므로 `-d 192.168.0.0/16 -j RETURN` 규칙을 통과한다. 다음 규칙의 `--to-source 192.168.4.12`가 매칭되어 **소스 IP가 파드 IP → 노드 IP로 변환**된다. [이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %}#패킷-흐름)의 파드 간 통신에서는 목적지가 VPC CIDR 안이라 이 규칙에서 RETURN되어 SNAT이 적용되지 않았다.
- **5 IGW 변환**: IGW가 노드 private IP(`192.168.4.12`) → public IP(`3.x.x.x`)로 변환한다. 파드→파드에서는 VPC 패브릭이 ENI의 secondary IP를 직접 라우팅했지만, 외부 통신은 VPC 밖으로 나가야 하므로 IGW에서 추가 변환이 필요하다.
- **8 conntrack 역NAT**: 응답이 돌아올 때 conntrack이 3번의 SNAT 매핑을 기억하고 있어 목적지를 노드 IP → 파드 IP로 자동 복원한다. 파드→파드에서는 SNAT이 없었으므로 conntrack/역NAT 자체가 불필요했다.
- **tcpdump에서의 차이**: 파드→파드에서는 ens5에서 파드 IP가 그대로 찍힌다. 파드→외부에서는 ens5에서 **노드 IP가 찍힌다** (SNAT 후). 아래 [실습](#실습-외부-통신-확인)에서 이를 직접 확인한다.

<br>

# 실습: 외부 통신 확인

## 외부 ping 테스트

파드에서 외부로 ping을 보내 통신이 되는지 확인한다.

```bash
kubectl exec -it $PODNAME1 -- ping -c 1 www.google.com
```

```
PING www.google.com (142.251.156.119) 56(84) bytes of data.
64 bytes from 142.251.156.119 (142.251.156.119): icmp_seq=1 ttl=106 time=28.0 ms

--- www.google.com ping statistics ---
1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 28.039/28.039/28.039/0.000 ms
```

파드에서 외부 인터넷으로의 통신이 정상 동작한다.


## 퍼블릭 IP 확인

파드가 외부에서 어떤 IP로 보이는지 확인한다.

```bash
# 노드별 퍼블릭 IP
for i in w2-node-1 w2-node-2 w2-node-3; do
  echo ">> node $i <<"
  ssh $i curl -s ipinfo.io/ip
  echo; echo
done

# 파드별 퍼블릭 IP
for i in $PODNAME1 $PODNAME2 $PODNAME3; do
  echo ">> Pod : $i <<"
  kubectl exec -it $i -- curl -s ipinfo.io/ip
  echo; echo
done
```

파드에서 `curl ipinfo.io/ip`로 확인한 퍼블릭 IP가 해당 파드가 실행 중인 **노드의 퍼블릭 IP와 동일**하다. 파드의 소스 IP가 노드 IP로 SNAT된 후, IGW에서 다시 퍼블릭 IP로 변환되기 때문이다.


## tcpdump로 SNAT 전후 비교

파드에서 외부로 ping을 보내면서 워커 노드에서 인터페이스별로 tcpdump를 실행한다.

### 전체 인터페이스 (`-i any`)

```bash
sudo tcpdump -i any -nn icmp
```

```
03:31:36.492634 eni31b43252b24 In  IP 192.168.4.248 > 142.251.154.119: ICMP echo request, id 2, seq 1, length 64
03:31:36.492654 ens5  Out IP 192.168.4.12 > 142.251.154.119: ICMP echo request, id 47885, seq 1, length 64
03:31:36.515189 ens5  In  IP 142.251.154.119 > 192.168.4.12: ICMP echo reply, id 47885, seq 1, length 64
03:31:36.515222 eni31b43252b24 Out IP 142.251.154.119 > 192.168.4.248: ICMP echo reply, id 2, seq 1, length 64
```

4개 패킷에서 SNAT 전후가 모두 보인다:

| 순서 | 인터페이스 | 방향 | src → dst | 의미 |
|------|-----------|------|-----------|------|
| 1 | `eni31b43252b24` (veth) | **In** | `192.168.4.248` → google | 파드 IP 그대로. SNAT **전** |
| 2 | `ens5` | **Out** | `192.168.4.12` → google | 노드 IP로 변환됨. SNAT **후** |
| 3 | `ens5` | **In** | google → `192.168.4.12` | 응답이 노드 IP로 도착 |
| 4 | `eni31b43252b24` (veth) | **Out** | google → `192.168.4.248` | 역NAT 후 파드 IP로 복원 |

veth에서는 파드 IP(`192.168.4.248`), ens5에서는 노드 IP(`192.168.4.12`)가 찍힌다. **그 사이에서 SNAT이 일어난다.** ICMP id도 `2`(파드 측) → `47885`(ens5 측)로 변경된다. iptables SNAT이 source port/id까지 변환하기 때문이다.


### ens5만 (`-i ens5`)

```bash
sudo tcpdump -i ens5 -nn icmp
```

```
03:32:08.498934 IP 192.168.4.12 > 142.251.157.119: ICMP echo request, id 64098, seq 1, length 64
03:32:08.521202 IP 142.251.157.119 > 192.168.4.12: ICMP echo reply, id 64098, seq 1, length 64
```

ens5에서는 **SNAT이 끝난 패킷만** 보인다. 파드 IP(`192.168.4.248`)는 전혀 나타나지 않고 노드 IP(`192.168.4.12`)만 찍힌다.


### 결과 비교

| 캡처 지점 | 소스 IP | 의미 |
|-----------|---------|------|
| `-i any` veth 구간 | `192.168.4.248` (파드) | SNAT 전 |
| `-i any` ens5 구간 | `192.168.4.12` (노드) | SNAT 후 |
| `-i ens5` 단독 | `192.168.4.12` (노드) | SNAT 후만 보임 |

`-i any` vs `-i ens5` 비교가 **iptables SNAT의 존재를 확인하는 가장 직관적인 방법**이다. [이전 글]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %}#tcpdump-검증)의 파드 간 통신에서는 veth와 ens5 모두에서 파드 IP 그대로 찍혔던 것과 대조된다.


## iptables SNAT 규칙 분석

tcpdump에서 확인한 SNAT이 어떤 iptables 규칙에 의해 일어나는지 살펴본다.

### AWS-SNAT-CHAIN-0

```bash
sudo iptables -t nat -S | grep 'A AWS-SNAT-CHAIN'
```

```bash
-A AWS-SNAT-CHAIN-0 -d 192.168.0.0/16 -m comment --comment "AWS SNAT CHAIN" -j RETURN
-A AWS-SNAT-CHAIN-0 ! -o vlan+ -m comment --comment "AWS, SNAT" -m addrtype ! --dst-type LOCAL \
  -j SNAT --to-source 192.168.4.12 --random-fully
```

두 규칙은 아래와 같이 동작한다:

1. **RETURN**: 목적지가 VPC CIDR(`192.168.0.0/16`) 내부이면 SNAT하지 않고 통과 → 파드 간 통신은 여기서 빠진다
2. **SNAT**: 그 외 모든 트래픽의 소스 IP를 `192.168.4.12`(노드 Primary ENI IP)로 변환

### 패킷 카운터 확인

ping을 보내면서 실시간으로 카운터를 관찰하면, 어떤 규칙이 매칭되는지 확인할 수 있다.

```bash
# 카운터 초기화
sudo iptables -t nat --zero

# 실시간 모니터링
watch -d 'sudo iptables -v --numeric --table nat --list AWS-SNAT-CHAIN-0'
```

```
Chain AWS-SNAT-CHAIN-0 (1 references)
 pkts bytes target     prot opt in     out     source               destination
    9   540 RETURN     all  --  *      *       0.0.0.0/0            192.168.0.0/16       /* AWS SNAT CHAIN */
   21  1292 SNAT       all  --  *      !vlan+  0.0.0.0/0            0.0.0.0/0            /* AWS, SNAT */
              ADDRTYPE match dst-type !LOCAL to:192.168.4.12 random-fully
```

VPC 내부 트래픽은 `RETURN` 규칙의 카운터가, 외부 트래픽은 `SNAT` 규칙의 카운터가 증가한다. 파드에서 외부로 ping을 보낼 때마다 SNAT 카운터가 올라가는 것을 확인할 수 있다.


### AWS-CONNMARK-CHAIN-0

SNAT과 함께 동작하는 CONNMARK 메커니즘도 확인한다.

```bash
# PREROUTING 체인
-A PREROUTING -i eni+ -m comment --comment "AWS, outbound connections" -j AWS-CONNMARK-CHAIN-0
-A PREROUTING -m comment --comment "AWS, CONNMARK" -j CONNMARK --restore-mark --nfmask 0x80 --ctmask 0x80

# AWS-CONNMARK-CHAIN-0
-A AWS-CONNMARK-CHAIN-0 -d 192.168.0.0/16 -m comment --comment "AWS CONNMARK CHAIN, VPC CIDR" -j RETURN
-A AWS-CONNMARK-CHAIN-0 -m comment --comment "AWS, CONNMARK" -j CONNMARK --set-xmark 0x80/0x80
```

ENI 인터페이스(`eni+` = veth)에서 들어오는 패킷 중 VPC 외부로 나가는 트래픽에 `0x80` 마크를 설정한다. 이 마크는 `ip rule`의 `fwmark 0x80/0x80 lookup main`(우선순위 1024) 규칙과 연결되어, SNAT된 응답 트래픽이 올바르게 main 테이블을 통해 라우팅되도록 보장한다.

### KUBE-POSTROUTING

kube-proxy가 설정하는 POSTROUTING 규칙도 같은 체인을 거치지만, 외부 통신에서는 매칭되지 않는다.

```bash
-A KUBE-POSTROUTING -m mark ! --mark 0x4000/0x4000 -j RETURN
-A KUBE-POSTROUTING -j MARK --set-xmark 0x4000/0x0
-A KUBE-POSTROUTING -m comment --comment "kubernetes service traffic requiring SNAT" -j MASQUERADE --random-fully
```

`0x4000` 마크는 Service 트래픽에 대해 kube-proxy가 설정하는 것이다. 파드 → 외부 통신에는 이 마크가 없으므로 첫 번째 규칙에서 `RETURN`된다. 외부 통신의 SNAT은 kube-proxy가 아니라 **VPC CNI의 `AWS-SNAT-CHAIN-0`**이 담당한다.


## conntrack 확인

conntrack은 커널이 유지하는 연결 추적 테이블이다. SNAT 전후의 IP 매핑을 기록한다.

```bash
sudo conntrack -L -n | grep -v '169.254.169'
```

```
icmp     1 28 src=172.30.66.58 dst=8.8.8.8 type=8 code=0 id=34392 \
  src=8.8.8.8 dst=172.30.85.242 type=0 code=0 id=50705 mark=128 use=1
```

이 한 줄에 왕복 매핑이 담겨 있다:

- **원본**: `src=172.30.66.58(파드)` → `dst=8.8.8.8`
- **응답 기대**: `src=8.8.8.8` → `dst=172.30.85.242(노드)`

conntrack이 이 매핑을 기억하고 있으므로, 응답 패킷의 목적지(`172.30.85.242`)를 원래 파드 IP(`172.30.66.58`)로 복원할 수 있다. `mark=128`(`0x80`)은 `AWS-CONNMARK-CHAIN-0`이 설정한 마크다.

> ICMP conntrack 엔트리의 TTL은 기본 30초다. 위 출력의 `28`이 남은 시간(초)이다. ping이 끝난 후 30초 이상 지나면 엔트리가 만료되어 조회되지 않는다. 확인하려면 ping을 계속 보내면서(`ping -i 0.1 8.8.8.8`) 다른 터미널에서 conntrack을 조회해야 한다.

<br>

# SNAT 동작 제어: EXTERNAL_SNAT

VPC CNI는 `AWS_VPC_K8S_CNI_EXTERNALSNAT` 환경변수로 SNAT 동작을 제어할 수 있다.

## 기본값 (`false`): VPC CNI가 SNAT

VPC CNI Plugin이 iptables로 직접 SNAT을 수행한다. 파드 IP → 노드 Primary ENI IP로 변환한다. 별도 설정 없이 동작하므로 간편하다.

```
파드 IP → (VPC CNI SNAT) → 노드 IP → (VPC 라우팅) → (IGW: private→public) → 인터넷
```

파드의 외부 통신이 가능하려면 노드가 인터넷에 도달 가능해야 한다. 두 가지 방법이 있다:

- **Public subnet**: 노드에 public/elastic IP를 할당하고, 서브넷의 라우팅 테이블에 IGW 경로를 설정한다
- **Private subnet + NAT Gateway**: 노드는 private subnet에 두고, 서브넷의 라우팅 테이블이 NAT Gateway(public subnet에 위치)를 가리키게 한다

SNAT 후 패킷의 소스 IP가 노드 IP가 되므로, 노드 자체가 인터넷에 도달할 수 있어야 응답도 돌아올 수 있다.


## `true`로 설정: VPC CNI가 SNAT하지 않음

```bash
kubectl set env daemonset -n kube-system aws-node AWS_VPC_K8S_CNI_EXTERNALSNAT=true
```

VPC CNI가 SNAT을 수행하지 않는다. 파드 IP가 그대로 VPC 내부를 돌아다니고, NAT Gateway 등 외부 장치가 SNAT을 대신 처리해야 한다.

```
파드 IP → (SNAT 안 함) → 파드 IP 그대로 → (NAT GW가 SNAT) → NAT GW IP → 인터넷
```


## 시나리오: Private subnet + NAT Gateway

실무에서 가장 흔한 구성이다. 보안상 노드는 private subnet에 배치하고, 외부 통신은 public subnet의 NAT Gateway를 경유한다.

### 기본 동작의 문제: `EXTERNAL_SNAT=false`

```
파드 IP → (VPC CNI가 SNAT) → 노드 IP → (NAT GW가 또 SNAT) → NAT GW IP → 인터넷
```

**이중 SNAT**이 발생한다. VPC 내부(다른 서브넷 등)에서 파드를 볼 때도 파드의 실제 IP가 아니라 노드 IP로 보여서, 디버깅이나 보안 정책 적용이 어려워진다.

### 해결: `EXTERNAL_SNAT=true`

```
파드 IP → (SNAT 안 함) → 파드 IP 그대로 → (NAT GW가 SNAT) → NAT GW IP → 인터넷
```

VPC CNI의 SNAT을 끄면 파드 IP가 VPC 내부에서 그대로 보이고, NAT Gateway 한 곳에서만 SNAT이 처리된다.

> AWS 문서에서도 노드를 private subnet에 배치할 것을 [권장](https://docs.aws.amazon.com/eks/latest/userguide/external-snat.html)한다. Private subnet + NAT Gateway + `EXTERNAL_SNAT=true`가 프로덕션 EKS에서 가장 많이 사용되는 구성이다.


## 참고: VPC Peering과 플러그인 1.8.0 미만

VPC CNI 1.8.0 미만 버전에서는 VPC Peering/Transit VPC/Direct Connect로 연결된 외부 리소스가 secondary ENI에 할당된 파드에게 **먼저** 통신을 시작할 수 없는 제약이 있었다. 파드가 먼저 요청하면 conntrack으로 응답이 돌아올 수 있지만, 외부에서 먼저 시작하는 통신은 불가능했다. 이 경우 `EXTERNAL_SNAT=true`로 설정하면 파드 IP가 그대로 노출되어 양방향 통신이 가능해졌다.

1.8.0 이후에는 secondary ENI에 대한 라우팅 규칙이 개선되어 이 제약이 해결됐으므로, 이 시나리오에서 `EXTERNAL_SNAT` 설정이 더 이상 필요하지 않다.

<br>

# 정리

| 항목 | 내용 |
|------|------|
| **Host Networking 파드** | 노드 IP를 그대로 사용하므로 SNAT 불필요 |
| **일반 파드** | VPC 사설 IP를 사용하므로 외부 통신에 SNAT 필수 |
| **"NAT 없이" 원칙** | 파드 간 직접 통신에만 적용. 외부 통신 SNAT은 원칙 위반 아님 |
| **VPC CNI 기본 동작** | `AWS-SNAT-CHAIN-0`에서 파드 IP → 노드 Primary ENI IP로 SNAT |
| **tcpdump 확인** | veth: 파드 IP / ens5: 노드 IP → SNAT 전후 비교 가능 |
| **conntrack** | SNAT 매핑을 기록하여 응답 패킷의 역NAT 수행 |
| **SNAT 제어** | `EXTERNAL_SNAT=true`로 VPC CNI SNAT을 끄고 NAT Gateway 등에 위임 |
| **프로덕션 권장** | Private subnet + NAT Gateway + `EXTERNAL_SNAT=true` |

이전 글에서 파드 간 통신은 tcpdump 모든 인터페이스에서 파드 IP가 그대로 찍혔다. 이 글에서는 같은 tcpdump 기법으로, **외부 통신에서는 SNAT이 일어나 veth와 ens5의 소스 IP가 다르다**는 것을 확인했다. 두 결과를 대비하면 VPC CNI의 "NAT 없는 파드 간 통신" vs "외부 통신 SNAT"이 명확히 구분된다.

<br>
