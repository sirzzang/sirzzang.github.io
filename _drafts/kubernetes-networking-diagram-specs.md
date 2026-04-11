# 쿠버네티스 네트워킹 다이어그램 설계서

각 다이어그램의 요소, 배치, 화살표, 주석을 정의한다. 그리는 도구에서 이 문서를 참고한다.

> Diagram 0(단일 노드 네트워크 스택)과 Diagram 1(ClusterIP)은 블로그 포스트에 반영 완료 — 삭제됨.


---


## Diagram 2: NodePort — External → Service → Pod

**목적**: 외부 클라이언트가 NodePort를 통해 파드에 접근하는 패킷 흐름.

**고정**: VPC CNI, NodePort
**변수**: target pod이 이 노드 vs 다른 노드, externalTrafficPolicy

### 핵심 포인트

- NodePort = ClusterIP + 노드 포트 매핑. Diagram 1의 DNAT 메커니즘 위에 NIC 진입점이 추가.
- **Diagram 1과의 차이**: 시작점이 veth가 아니라 **NIC(RX)**

### 레이아웃

```
  외부 클라이언트
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Node 1 (192.168.1.10)                                   │
│                                                         │
│  NIC (RX) ← 외부에서 Node1_IP:30080 으로 도착           │
│       │                                                  │
│  ┌────▼─────────────────────────────────────────────┐   │
│  │ Kernel (netfilter)                                │   │
│  │                                                   │   │
│  │  ① PREROUTING                                     │   │
│  │     └→ KUBE-SERVICES                              │   │
│  │        └→ KUBE-NODEPORTS                          │   │
│  │           └→ DNAT: NodeIP:30080                   │   │
│  │                 → PodX_IP:80                       │   │
│  │                                                   │   │
│  │  ② ROUTING DECISION                               │   │
│  │     dest = PodX_IP                                │   │
│  │                                                   │   │
│  │     ┌──── Case A: Pod가 이 노드 ────┐            │   │
│  │     │ ③ FORWARD                      │            │   │
│  │     │    host route → veth → Pod     │            │   │
│  │     └────────────────────────────────┘            │   │
│  │                                                   │   │
│  │     ┌──── Case B: Pod가 다른 노드 ───────────┐   │   │
│  │     │ ③ FORWARD                               │   │   │
│  │     │ ④ POSTROUTING                           │   │   │
│  │     │                                         │   │   │
│  │     │   externalTrafficPolicy: Cluster (기본)  │   │   │
│  │     │   └→ KUBE-POSTROUTING: MASQUERADE       │   │   │
│  │     │      src = Client IP → Node1 IP ★       │   │   │
│  │     │      (원래 클라이언트 IP 사라짐)          │   │   │
│  │     │                                         │   │   │
│  │     │   externalTrafficPolicy: Local           │   │   │
│  │     │   └→ 이 노드에 Pod 없으면 DROP          │   │   │
│  │     │      있으면 Case A로 (SNAT 안 함)       │   │   │
│  │     │                                         │   │   │
│  │     │   → ENI → VPC → Node 2                  │   │   │
│  │     └─────────────────────────────────────────┘   │   │
│  └───────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─ Pod (이 노드에 있는 경우) ─┐                        │
│  │  ⑤ 패킷 수신               │                        │
│  │  src: Client IP (Case A)    │                        │
│  │  src: Node1 IP  (Case B, Cluster) ★                 │
│  └─────────────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

### 단계별 설명

| 단계 | 위치 | 동작 |
|------|------|------|
| ① | NIC(RX) → PREROUTING | 외부에서 `NodeIP:NodePort`로 도착. KUBE-NODEPORTS에서 **DNAT** |
| ② | ROUTING DECISION | DNAT 후 dest가 Pod IP로 변경. 이 IP가 어디에 있는지 판단 |
| ③-A | FORWARD → veth | 이 노드에 Pod 있음: host route → veth → Pod. SNAT 없음 → **클라이언트 IP 보존** |
| ③-B | FORWARD → POSTROUTING | 다른 노드에 Pod 있음: FORWARD 후 POSTROUTING 거침 |
| ④ | POSTROUTING | `externalTrafficPolicy: Cluster` → **MASQUERADE** (src=ClientIP → Node1IP). `Local` → 이 노드에 Pod 없으면 DROP |
| ⑤ | Pod | 수신. Case A: src=ClientIP. Case B(Cluster): src=Node1IP (★ 클라이언트 IP 손실) |

### externalTrafficPolicy 비교 (사이드 테이블)

| 정책 | 장점 | 단점 |
|------|------|------|
| `Cluster` (기본) | 모든 노드가 트래픽 수용, 부하 분산 | 클라이언트 IP 손실 (SNAT), 추가 홉 |
| `Local` | 클라이언트 IP 보존, 홉 감소 | Pod 없는 노드는 DROP, 불균등 분배 |

### Diagram 1과의 관계 강조

```
NodePort = ClusterIP + 포트 매핑

Diagram 1 (ClusterIP):
  Pod veth → PREROUTING(DNAT) → FORWARD → ...

Diagram 2 (NodePort):
  NIC(RX) → PREROUTING(DNAT) → FORWARD → ...
  ~~~~~~~~~~                             
  이 부분만 다르다 (진입점)
  + externalTrafficPolicy에 의한 SNAT 분기
```


---


## Diagram 3: LoadBalancer (간략)

**목적**: LoadBalancer = NodePort + 외부 LB. Diagram 2 앞에 LB 블록만 추가.

### 레이아웃

```
  외부 클라이언트
       │
       ▼
┌──────────────────────────────────┐
│ Cloud Load Balancer              │
│ (AWS NLB/ALB)                    │
│                                  │
│  ┌─ Instance Target Mode ─┐     │   ┌─ IP Target Mode ─┐
│  │ LB → Node:NodePort     │     │   │ LB → Pod IP:Port │
│  │ (= Diagram 2와 동일)   │     │   │ (NodePort 안 거침) │
│  └─────────────────────────┘     │   └───────────────────┘
└──────────────────────────────────┘
       │                                       │
       ▼                                       ▼
┌──── Node ────┐                     ┌──── Node ────┐
│ NIC(RX)      │                     │ NIC(RX)      │
│ PREROUTING   │ ← Diagram 2        │ PREROUTING   │
│ DNAT         │    그대로           │ (DNAT 불필요)│
│ FORWARD      │                     │ FORWARD      │
│ ...          │                     │ → veth → Pod │
└──────────────┘                     └──────────────┘
```

### 두 가지 Target Mode

| Mode | LB 목적지 | 노드에서의 처리 | 비고 |
|------|----------|----------------|------|
| **Instance** (기본) | Node IP:NodePort | Diagram 2와 동일 (DNAT → FORWARD → ...) | NodePort 필수 |
| **IP** | Pod IP:Port 직접 | DNAT 불필요. PREROUTING → FORWARD → veth → Pod | VPC CNI + NLB IP target. 파드 IP가 VPC에서 라우팅 가능하므로 직접 도달 |

### 핵심 메시지

- Instance mode: Diagram 2(NodePort)를 그대로 재사용하고 앞에 LB 블록만 추가
- IP target mode: VPC CNI의 "파드 IP = VPC IP" 특성을 활용. NodePort → DNAT 단계를 통째로 건너뜀


---


## Diagram 4: CNI 구현 차이 — 크로스 노드 구간

**목적**: 노드 내부 경로는 동일하고, **노드 밖으로 나간 후 상대 노드에 도착하기까지** 구간만 달라지는 것을 보여줌.

**고정**: pod → pod 크로스 노드 (Service 없음)
**변수**: CNI 구현 방식

### 핵심 포인트

- 노드 내부(veth → kernel → ENI out)와 상대 노드(ENI in → kernel → veth)는 모든 CNI에서 동일
- **POSTROUTING 이후 ~ 상대 PREROUTING 이전** 구간만 CNI마다 다르다

### 레이아웃

```
  Node 1                                                 Node 2
┌──────────────┐                                 ┌──────────────┐
│ Pod A        │                                 │ Pod B        │
│   eth0       │                                 │   eth0       │
│     │        │                                 │     ▲        │
│     ▼        │                                 │     │        │
│   veth       │                                 │   veth       │
│     │        │                                 │     ▲        │
│   Kernel     │                                 │   Kernel     │
│  (FORWARD)   │                                 │  (FORWARD)   │
│     │        │                                 │     │        │
│  POSTROUTING │                                 │  PREROUTING  │
│     │        │                                 │     ▲        │
│   ENI out    │                                 │   ENI in     │
└──────┬───────┘                                 └──────┬───────┘
       │                                                ▲
       │         ┌──────────────────────────┐           │
       └────────→│   크로스 노드 구간       │──────────→┘
                 │   (CNI마다 다른 부분)     │
                 └──────────────────────────┘
```

### CNI별 크로스 노드 구간 상세

#### (a) Overlay — Flannel VXLAN

```
  Node 1 ENI out                                    Node 2 ENI in
       │                                                 ▲
       ▼                                                 │
  ┌─────────────┐                               ┌──────────────┐
  │ flannel.1   │                               │ flannel.1    │
  │ (VTEP)      │                               │ (VTEP)       │
  │             │                               │              │
  │ VXLAN 캡슐화│                               │ VXLAN 디캡슐화│
  │ Outer:      │                               │ Inner 패킷   │
  │  src=Node1IP│                               │  src=PodA IP │
  │  dst=Node2IP│                               │  dst=PodB IP │
  │ Inner:      │                               │ 그대로 전달   │
  │  src=PodA IP│                               │              │
  │  dst=PodB IP│                               │              │
  └──────┬──────┘                               └──────▲───────┘
         │                                             │
         │      물리 네트워크 (노드 IP로 라우팅)        │
         └────────────────────────────────────────────→┘
                   UDP:8472 (VXLAN)
```

**특징**: 물리 네트워크는 노드 IP만 알면 된다. 파드 IP를 몰라도 됨.
**오버헤드**: 캡슐화/디캡슐화 처리. 패킷 크기 증가 (VXLAN 헤더 50 bytes).

#### (b) BGP — Calico BGP 모드

```
  Node 1 ENI out                                    Node 2 ENI in
       │                                                 ▲
       ▼                                                 │
  ┌──────────┐    BGP Peer    ┌──────────┐             │
  │ BIRD     │←──────────────→│ BIRD     │             │
  │ (BGP     │   파드 CIDR    │ (BGP     │             │
  │  agent)  │   경로 교환    │  agent)  │             │
  └──────────┘                └──────────┘             │
       │                                                 │
       │    물리 라우터/스위치가 파드 CIDR 경로를 알고 있음  │
       │    캡슐화 없이 직접 전달                         │
       │                                                 │
       │      src=PodA IP, dst=PodB IP (그대로)          │
       └────────────────────────────────────────────────→┘
```

**특징**: 캡슐화 없음. 물리 네트워크가 파드 CIDR 경로를 알아야 함.
**제약**: 물리 라우터가 BGP를 지원해야 함. 클라우드 환경에서는 제한적.

#### (c) Cloud Native — AWS VPC CNI

```
  Node 1 ENI out                                    Node 2 ENI in
       │                                                 ▲
       │   파드 IP = ENI 보조 IP (VPC가 직접 라우팅)      │
       │                                                 │
       │      src=PodA IP, dst=PodB IP (그대로)          │
       │                                                 │
       │   ┌───────────────────────────────────────┐     │
       └──→│         VPC 라우팅 패브릭              │────→┘
            │                                       │
            │  VPC가 ENI 보조 IP를 알고 있으므로     │
            │  추가 캡슐화/라우팅 설정 불필요        │
            └───────────────────────────────────────┘
```

**특징**: 캡슐화 없음. 별도 라우팅 설정 불필요. VPC 네이티브 성능.
**제약**: 파드 수 = ENI 보조 IP 수에 제한. VPC IP 대역 소비.

#### (d) eBPF — Cilium

```
  Node 1                                            Node 2
  ┌───────────────┐                          ┌───────────────┐
  │   veth        │                          │   veth        │
  │     │         │                          │     ▲         │
  │  [TC egress]  │ ← eBPF 훅              │  [TC ingress] │ ← eBPF 훅
  │     │         │   netfilter              │     │         │   netfilter
  │     │         │   바이패스 가능          │     │         │   바이패스 가능
  │     ▼         │                          │     │         │
  │   ENI out     │                          │   ENI in      │
  └───────┬───────┘                          └───────▲───────┘
          │                                          │
          │   크로스 노드: VXLAN 또는 네이티브 라우팅   │
          │   (Cilium 설정에 따라 선택)               │
          └─────────────────────────────────────────→┘
```

**특징**: netfilter(iptables) 체인을 바이패스하고 TC/XDP 훅에서 직접 처리 → 성능 향상.
크로스 노드 전송 자체는 VXLAN 또는 네이티브 라우팅 중 선택 가능.

### 4가지 비교 요약 테이블 (다이어그램 하단에 배치)

| CNI | 캡슐화 | 물리 네트워크 요구 | 파드 IP | 성능 |
|-----|--------|------------------|---------|------|
| Overlay (VXLAN) | O (UDP:8472) | 노드 간 IP 통신만 | 가상 대역 | 캡슐화 오버헤드 |
| BGP | X | BGP 지원 필요 | 가상 대역 (라우팅됨) | 네이티브 |
| VPC CNI | X | VPC 라우팅 | VPC 실제 IP | 네이티브 |
| eBPF (Cilium) | 선택 | 설정에 따라 | 설정에 따라 | netfilter 바이패스 |


---


## 다이어그램 간 관계 요약

```
Diagram 0 (기반: 정적 스택)
│
├─ "여기에 화살표를 그린다"
│
├── Diagram 1 (ClusterIP)
│     시작점: Pod veth
│     핵심: PREROUTING DNAT
│     분기: 같은 노드 / 다른 노드
│
├── Diagram 2 (NodePort)
│     시작점: NIC (RX)
│     핵심: PREROUTING DNAT + externalTrafficPolicy SNAT
│     분기: 같은 노드 / 다른 노드 + Cluster/Local 정책
│
├── Diagram 3 (LoadBalancer)
│     = Diagram 2 앞에 LB 블록 추가
│     + IP target mode 변형
│
└── Diagram 4 (CNI 차이)
      고정: pod→pod 크로스 노드
      변수: 크로스 노드 구간만
      4가지: Overlay / BGP / VPC CNI / eBPF
```
