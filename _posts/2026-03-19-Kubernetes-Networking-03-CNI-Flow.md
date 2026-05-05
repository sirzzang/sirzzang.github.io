---
title:  "[Kubernetes] CNI 동작 흐름: Pod 생성부터 노드 간 통신까지"
excerpt: "CNI 솔루션 설치, Pod 생성, 같은/다른 노드 통신, 외부 통신까지 — Flannel(VXLAN) 시나리오로 따라가는 패킷 흐름과 VTEP/onlink/FDB의 역할."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - CNI
  - Networking
  - VXLAN
  - Flannel
  - overlay

---
앞선 [네트워킹 모델]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %})·[파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %})·[CNI 표준]({% post_url 2026-01-05-Kubernetes-Networking-02-CNI %})에서 다룬 개념들이 실제로 어떤 순서로 동작하는지, 어떤 네임스페이스에서 무슨 인터페이스가 만들어지고, 어떤 라우팅 규칙이 설정되는지를 **Flannel(VXLAN) 클러스터에서 Pod이 만들어지고 노드 간에 패킷이 오가는 한 시나리오**로 따라간다. 노드 간 도달 메커니즘이 왜 세 가지(오버레이/BGP/클라우드 네이티브)로 나뉘는지는 [파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}) 글의 분류·검증을 먼저 보면 도움이 된다. 이 토대 위에 Service 라우팅 계층이 얹히는 과정은 [Service와 kube-proxy]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %})에서 이어진다.

시나리오 기준:
- CNI 솔루션: **Flannel (VXLAN 모드)** — 오버레이 분류의 가장 보편적인 구현
- Node 1: `192.168.1.10`, Pod CIDR `10.244.0.0/24`
- Node 2: `192.168.1.20`, Pod CIDR `10.244.1.0/24`

<br>

# Phase 0. CNI 솔루션 설치

클러스터에 CNI 솔루션을 설치하면, 각 노드에 DaemonSet Pod이 배포되고 네트워크 인프라가 준비된다. Pod이 생성되기 전에 일어나는 단계다.

![flannel-flow-overview](/assets/images/flannel-flow-overview.png)

## 단계별 상세

**1. DaemonSet 배포**

```bash
kubectl apply -f flannel.yaml
```

각 노드에 Flannel DaemonSet Pod이 생성된다.

**2-3. init container: 바이너리 및 설정 파일 배포**

init container가 실행되면서 두 가지를 노드에 복사한다:

```bash
/opt/cni/bin/
├── flannel       # Flannel CNI 바이너리
├── bridge        # bridge 플러그인 (Flannel이 delegate)
└── host-local    # IPAM 플러그인

/etc/cni/net.d/
└── 10-flannel.conflist   # CNI 설정 파일
```

**4. 메인 컨테이너(에이전트) 시작**

init container가 끝나면 메인 컨테이너가 시작된다. Flannel 에이전트로서 상시 실행된다.

**5. VTEP 인터페이스 생성**

에이전트가 `flannel.1` 가상 인터페이스를 생성한다. 이 인터페이스가 VXLAN 캡슐화/역캡슐화를 수행하는 VTEP이다.

**6. 토폴로지 공유**

에이전트들이 서로 직접 통신하는 것이 아니다. 각 에이전트가 **kube-apiserver를 통해** 간접적으로 클러스터 네트워크 토폴로지를 공유한다:

1. 각 에이전트가 자기 노드의 정보를 **Kubernetes Node 오브젝트의 annotation**에 기록
2. kube-apiserver를 **watch**하면서 다른 노드들의 annotation을 읽어옴

결과적으로 각 에이전트는 다음과 같은 매핑을 알게 된다:

- Node 1 → Pod CIDR: `10.244.0.0/24`, Node IP: `192.168.1.10`
- Node 2 → Pod CIDR: `10.244.1.0/24`, Node IP: `192.168.1.20`

**7. 라우팅 규칙 설정**

에이전트가 토폴로지 정보를 바탕으로 노드에 세 가지 테이블을 설정한다. 이 세 테이블이 함께 동작해야 VXLAN 캡슐화가 가능하다:

```bash
# Node 1 기준

# (1) 라우팅 테이블: "이 대역은 어느 인터페이스, 어느 next-hop으로 보낼지"
10.244.0.0/24 dev cni0                                    # 자기 노드 대역 → bridge (cni0 생성 후)
10.244.1.0/24 via 10.244.1.0 dev flannel.1 onlink         # Node 2 대역 → VTEP

# (2) ARP/neighbor 테이블: "next-hop IP의 MAC 주소"
# ip neigh add 10.244.1.0 lladdr aa:bb:cc:dd:ee:f2 dev flannel.1 nud permanent

# (3) FDB(forwarding database): "이 MAC을 가진 VTEP의 물리 노드 IP"
# bridge fdb add aa:bb:cc:dd:ee:f2 dev flannel.1 dst 192.168.1.20
```

패킷 전송 시 커널은 이 세 테이블을 순서대로 참조한다:

| 순서 | 테이블 | 질문 | 답 (예시) |
| --- | --- | --- | --- |
| 1 | 라우팅 테이블 | `10.244.1.2`는 어디로? | next-hop `10.244.1.0`, dev `flannel.1` |
| 2 | ARP/neighbor | `10.244.1.0`의 MAC은? | `aa:bb:cc:dd:ee:f2` |
| 3 | FDB | 이 MAC은 물리적으로 어디? | `192.168.1.20` (Node 2) |

최종적으로 커널은 `192.168.1.20`을 외부 목적지로 하는 VXLAN 캡슐화 패킷을 만든다.

**`onlink` 플래그**: 커널은 라우팅 엔트리를 추가할 때 "next-hop IP가 이 인터페이스의 직접 연결된 서브넷 안에 있는가?"를 확인한다. Node 1의 `flannel.1` IP는 `10.244.0.0/32`인데, next-hop `10.244.1.0`은 이 `/32` 범위에 포함되지 않으므로 커널이 라우트 추가를 거부한다. `onlink`는 이 서브넷 체크를 건너뛰라는 지시다.

새 노드가 추가되면 kube-apiserver에 새 Node 오브젝트가 생기고, 각 에이전트가 이를 watch로 감지하여 해당 노드의 엔트리를 세 테이블 모두에 자동으로 추가한다.

## Phase 0 완료 후 노드 상태

```
Node 1 (192.168.1.10)
┌─────────────────────────────────────────────────┐
│                User Space                       │
│  ┌───────────────────────────────────────────┐  │
│  │ flannel agent (DaemonSet Pod)             │  │
│  │  - watches kube-apiserver for Node info   │  │
│  │  - topology: Node2=10.244.1.0/24          │  │
│  │  - manages routing rules                  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│                Kernel                           │
│  ┌───────────────────────────────────────────┐  │
│  │ Routing table:                            │  │
│  │  10.244.1.0/24 via flannel.1              │  │
│  ├───────────────────────────────────────────┤  │
│  │ flannel.1 (VTEP)     eth0 (192.168.1.10)  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘

아직 cni0 bridge는 없다 (첫 번째 Pod이 생성될 때 만들어진다)
```

<br>

# Phase 1. Pod 생성

Node 1에 Pod이 스케줄링되면, kubelet → containerd → CNI 바이너리 순서로 네트워크가 설정된다.

![flannel-phase-1](/assets/images/flannel-phase-1.png)

## 단계별 상세

**8. 스케줄링**

kube-apiserver가 Pod을 Node 1에 스케줄링한다.

**9. kubelet → containerd**

Node 1의 kubelet이 이를 감지하고, containerd에 컨테이너 생성을 요청한다.

**10. 네트워크 네임스페이스 생성**

containerd가 새로운 네트워크 네임스페이스를 생성한다:

```bash
/var/run/netns/cni-xxxx-yyyy
```

이 시점에서 네임스페이스 안에는 `lo` (loopback) 인터페이스만 있다.

**11. CNI 바이너리 호출**

containerd가 `/etc/cni/net.d/10-flannel.conflist`를 읽고, `/opt/cni/bin/flannel`을 fork/exec한다:

```bash
CNI_COMMAND=ADD \
CNI_CONTAINERID=abc123 \
CNI_NETNS=/var/run/netns/cni-xxxx-yyyy \
CNI_IFNAME=eth0 \
CNI_PATH=/opt/cni/bin \
/opt/cni/bin/flannel < /etc/cni/net.d/10-flannel.conflist
```

**12. flannel → bridge delegate**

flannel 바이너리는 실제 네트워크 구성을 bridge 플러그인에 위임(delegate)한다.

**13. cni0 bridge 생성 (최초 1회)**

bridge 플러그인이 `cni0` bridge가 없으면 생성하고, 게이트웨이 IP를 할당한다:

```bash
ip link add cni0 type bridge
ip addr add 10.244.0.1/24 dev cni0
ip link set cni0 up
```

두 번째 Pod부터는 이미 존재하므로 건너뛴다.

**14. veth pair 생성 + 연결**

```bash
# veth pair 생성
ip link add vethXXX type veth peer name eth0

# 한쪽을 Pod 네임스페이스로 이동
ip link set eth0 netns /var/run/netns/cni-xxxx-yyyy

# 다른 쪽을 cni0 bridge에 연결
ip link set vethXXX master cni0
ip link set vethXXX up
```

**15. IPAM 플러그인 호출**

bridge 플러그인이 host-local IPAM 플러그인을 호출한다. host-local은 `10.244.0.0/24` 서브넷에서 사용 가능한 IP를 선택하여 반환한다:

```bash
# host-local이 로컬 파일로 IP 할당 기록
/var/lib/cni/networks/cbr0/10.244.0.2
```

**16. Pod 네임스페이스 내 설정**

bridge 플러그인이 반환받은 IP로 Pod 네임스페이스 안을 설정한다:

```bash
ip netns exec cni-xxxx-yyyy ip addr add 10.244.0.2/24 dev eth0
ip netns exec cni-xxxx-yyyy ip link set eth0 up
ip netns exec cni-xxxx-yyyy ip route add default via 10.244.0.1
```

**17. 결과 반환**

바이너리가 JSON 결과를 stdout으로 반환한다. containerd가 이를 수신한다.

**18. 컨테이너 프로세스 시작**

containerd가 runc를 통해 컨테이너 프로세스를 시작한다. 네트워크와 프로세스가 모두 준비되면 Pod이 Running 상태가 된다.

## Phase 1 완료 후 노드 상태

Pod A(`10.244.0.2`)와 Pod B(`10.244.0.3`)가 생성된 후의 상태:

```
Node 1 (192.168.1.10)
┌─────────────────────────────────────────────────────────────────────┐
│                         User Space                                  │
│  ┌─────────────────────────┐                                        │
│  │ flannel agent(DaemonSet)│                                        │
│  └─────────────────────────┘                                        │
│  ┌─────────────────┐  ┌─────────────────┐                           │
│  │ Pod A           │  │ Pod B           │                           │
│  │ (container proc)│  │ (container proc)│                           │
│  └─────────────────┘  └─────────────────┘                           │
│─────────────────────────────────────────────────────────────────────│
│                         Kernel                                      │
│                                                                     │
│  Pod A netns:              Pod B netns:                             │
│  ┌──────────────────┐     ┌──────────────────┐                      │
│  │ lo               │     │ lo               │                      │
│  │ eth0 (10.244.0.2)│     │ eth0 (10.244.0.3)│                      │
│  │  route: default  │     │  route: default  │                      │
│  │  via 10.244.0.1  │     │  via 10.244.0.1  │                      │
│  └────────┬─────────┘     └────────┬─────────┘                      │
│           │ veth pair              │ veth pair                      │
│  Host netns:                                                        │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ vethXXX ──┐                                              │       │
│  │ vethYYY ──┤── cni0 (bridge, 10.244.0.1)                  │       │
│  │           │                                              │       │
│  │ flannel.1 (VTEP)                                         │       │
│  │ eth0 (192.168.1.10)                                      │       │
│  ├──────────────────────────────────────────────────────────┤       │
│  │ Routing table:                                           │       │
│  │  10.244.0.0/24 dev cni0                                  │       │
│  │  10.244.1.0/24 via 10.244.1.0 dev flannel.1              │       │
│  ├──────────────────────────────────────────────────────────┤       │
│  │ iptables (MASQUERADE):                                   │       │
│  │  -s 10.244.0.0/16 ! -d 10.244.0.0/16 -j MASQUERADE       │       │
│  │  (Pod → 클러스터 외부 시 SNAT)                               │       │
│  └──────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```


<br>

# Phase 2. 같은 노드 내 Pod 간 통신

Pod A(`10.244.0.2`) → Pod B(`10.244.0.3`)

![flannel-phase-2](/assets/images/flannel-phase-2.png)

## 단계별 상세

**19.** Pod A의 프로세스가 `10.244.0.3`으로 패킷 전송

**20.** Pod A 네임스페이스의 라우팅 테이블 확인:
- `10.244.0.0/24 dev eth0` → 같은 서브넷이므로 eth0으로 직접 전송

**21.** 패킷이 eth0 → veth pair → 호스트의 `vethXXX` → `cni0` bridge 도착

**22.** `cni0` bridge가 L2 스위치로서 MAC 주소 테이블을 확인하고, `10.244.0.3`의 MAC이 `vethYYY`에 연결되어 있음을 알고 해당 포트로 전달

**23.** `vethYYY` → veth pair → Pod B의 `eth0`에 도착

오버레이나 VTEP은 관여하지 않는다. 같은 bridge에 연결된 Pod끼리는 L2 스위칭만으로 통신한다.

<br>

# Phase 3. 다른 노드의 Pod과 통신

Pod A(`10.244.0.2`, Node 1) → Pod C(`10.244.1.2`, Node 2)

![flannel-phase-3](/assets/images/flannel-phase-3.png)

## 단계별 상세

### 출발: Node 1

**24.** Pod A의 프로세스가 `10.244.1.2`로 패킷 전송

**25.** Pod A 네임스페이스의 라우팅 테이블 확인:
- `10.244.1.2`는 `10.244.0.0/24` (같은 서브넷)에 해당하지 않음
- `default via 10.244.0.1` → 기본 게이트웨이(cni0 bridge)로 전송

**26.** 패킷이 eth0 → veth pair → `cni0` bridge → 호스트 네임스페이스

**27.** 호스트 커널이 라우팅 테이블 확인:

```
10.244.1.0/24 via 10.244.1.0 dev flannel.1
```

→ `flannel.1` (VTEP)으로 전달

### 캡슐화

**28.** VTEP(`flannel.1`)이 원본 L2 프레임을 캡슐화:

```
Original:
  [src MAC | dst MAC | src: 10.244.0.2 | dst: 10.244.1.2 | data]

Encapsulated:
  [outer src: 192.168.1.10 | outer dst: 192.168.1.20 | UDP:4789 | VXLAN hdr | original L2 frame]
```

에이전트의 토폴로지 정보로 `10.244.1.0/24` → `Node 2 (192.168.1.20)`임을 알고 있다.

### 물리 네트워크 전달

**29.** 캡슐화된 패킷이 노드의 `eth0` (`192.168.1.10`)을 통해 전송

**30.** 물리 네트워크(스위치, 라우터)가 `192.168.1.10 → 192.168.1.20`으로 라우팅. 물리 네트워크는 Pod IP(`10.244.x.x`)를 전혀 모른다. 언더레이 대역(`192.168.1.x`)의 일반 트래픽으로만 보인다.

### 도착: Node 2

**31.** Node 2의 커널이 `UDP:4789` 패킷 수신 → VXLAN으로 식별

**32.** Node 2의 VTEP(`flannel.1`)이 역캡슐화 → 원본 L2 프레임 복원

**33.** 커널이 라우팅 테이블 확인:

```
10.244.1.0/24 dev cni0
```

→ `cni0` bridge로 전달

**34.** `cni0` → MAC 테이블 lookup → `vethZZZ` → Pod C의 `eth0` 도착

### 응답 패킷

Pod C → Pod A 응답은 정확히 역방향으로 동일한 과정을 거친다. Node 2의 VTEP이 캡슐화하고, Node 1의 VTEP이 역캡슐화한다.

<br>

# Phase 4. Pod → 클러스터 외부 통신

Pod A(`10.244.0.2`) → 외부 서버(`8.8.8.8`)

![flannel-phase-4](/assets/images/flannel-phase-4.png)

## 단계별 상세

**35.** Pod A가 `8.8.8.8`로 패킷 전송

**36.** Pod 네임스페이스: `default via 10.244.0.1` → cni0 bridge로

**37.** 호스트 커널 라우팅 테이블: `8.8.8.8`은 Pod CIDR(`10.244.x.x`)에 해당하지 않음 → 호스트의 default gateway로

**38.** iptables MASQUERADE 규칙 적용:

```bash
-s 10.244.0.0/16 ! -d 10.244.0.0/16 -j MASQUERADE
```

출발지가 Pod CIDR이고 목적지가 Pod CIDR이 **아닌** 경우 → SNAT 적용. 출발지 IP가 `10.244.0.2` → `192.168.1.10` (노드 IP)으로 변환된다.

**39.** 패킷이 `eth0`을 통해 외부로 전송. 외부 네트워크는 노드 IP(`192.168.1.10`)만 본다.

**40.** 응답 패킷이 `192.168.1.10`으로 돌아오면, conntrack이 역변환하여 `10.244.0.2`로 전달한다.

> 이 MASQUERADE 규칙은 CNI 플러그인 또는 에이전트가 설정한다. Pod 간 통신(10.244.x.x → 10.244.x.x)은 MASQUERADE 대상이 아니므로 NAT 없이 직접 통신한다는 Kubernetes 네트워킹 모델의 원칙이 지켜진다.

<br>

# 단면도: 노드의 네트워크 스택

두 노드에 각각 Pod이 있는 상태의 전체 구조:


```
Node 1 (192.168.1.10)                                  Node 2 (192.168.1.20)
Pod CIDR: 10.244.0.0/24                                Pod CIDR: 10.244.1.0/24

┌────────────────────────────────────────┐     ┌────────────────────────────────────────┐
│              User Space                │     │              User Space                │
│  ┌──────────┐  ┌──────────┐            │     │            ┌──────────┐  ┌──────────┐  │
│  │  Pod A   │  │  Pod B   │            │     │            │  Pod C   │  │  Pod D   │  │
│  │  .0.2    │  │  .0.3    │            │     │            │  .1.2    │  │  .1.3    │  │
│  └────┬─────┘  └────┬─────┘            │     │            └────┬─────┘  └────┬─────┘  │
│═══════╪══════════════╪═════════════════│     │═════════════════╪═════════════╪════════│
│       │    Kernel     │                │     │                 │    Kernel   │        │
│  Pod netns:          Pod netns:        │     │          Pod netns:         Pod netns: │
│  ┌─────────┐    ┌─────────┐            │     │            ┌─────────┐    ┌─────────┐  │
│  │eth0     │    │eth0     │            │     │            │eth0     │    │eth0     │  │
│  │10.244.  │    │10.244.  │            │     │            │10.244.  │    │10.244.  │  │
│  │0.2      │    │0.3      │            │     │            │1.2      │    │1.3      │  │
│  └────┬────┘    └────┬────┘            │     │            └────┬────┘    └────┬────┘  │
│       │veth          │veth             │     │                 │veth          │veth   │
│  Host netns:                           │     │           Host netns:                  │
│  ┌────────────────────────────────┐    │     │    ┌────────────────────────────────┐  │
│  │  vethXXX─┐                     │    │     │    │                     ┌─vethZZZ  │  │
│  │  vethYYY─┤  cni0 (10.244.0.1)  │    │     │    │ (10.244.1.1) cni0   ├─vethWWW  │  │
│  │          └────────┬────────────│    │     │    │────────────┬────────┘          │  │
│  │                   │            │    │     │    │            │                   │  │
│  │  flannel.1 (VTEP) │            │    │     │    │            │ flannel.1 (VTEP)  │  │
│  │          └────────┤            │    │     │    │            ├────────┘          │  │
│  │                   │            │    │     │    │            │                   │  │
│  │          eth0 (192.168.1.10)   │    │     │    │   eth0 (192.168.1.20)          │  │
│  ├────────────────────────────────┤    │     │    ├────────────────────────────────┤  │
│  │ Routing:                       │    │     │    │ Routing:                       │  │
│  │  10.244.0.0/24 dev cni0        │    │     │    │  10.244.1.0/24 dev cni0        │  │
│  │  10.244.1.0/24 dev flannel.1   │    │     │    │  10.244.0.0/24 dev flannel.1   │  │
│  ├────────────────────────────────┤    │     │    ├────────────────────────────────┤  │
│  │ iptables:                      │    │     │    │ iptables:                      │  │
│  │  MASQUERADE (Pod→external)     │    │     │    │  MASQUERADE (Pod→external)     │  │
│  └───────────┬────────────────────┘    │     │    └────────────────────┬───────────┘  │
└──────────────┼─────────────────────────┘     └─────────────────────────┼──────────────┘
               │       Physical Network (192.168.1.0/24)                 │
               └─────────────────────────────────────────────────────────┘
                     overlay: UDP:4789 (VXLAN)
                     underlay: 192.168.1.x routing
```

<br>

# 정리

| Phase | 일어나는 일 | 주체 | 시점 |
| --- | --- | --- | --- |
| **0. CNI 설치** | 바이너리 배포, VTEP 생성, 라우팅 규칙 설정 | DaemonSet 에이전트 | 클러스터 1회 |
| **1. Pod 생성** | namespace 생성, veth pair, cni0 bridge, IP 할당 | containerd → CNI 바이너리 | Pod마다 |
| **2. 같은 노드 통신** | cni0 bridge가 L2 스위칭 | 커널 (bridge) | 패킷마다 |
| **3. 다른 노드 통신** | 라우팅 → VTEP → 캡슐화 → 물리 네트워크 → 역캡슐화 | 커널 (routing + VTEP) | 패킷마다 |
| **4. 외부 통신** | iptables MASQUERADE (SNAT) | 커널 (netfilter) | 패킷마다 |

<br>
