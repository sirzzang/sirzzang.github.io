---
title:  "[CS] 컨테이너 네트워킹 기본 원리: 네임스페이스 네트워킹"
excerpt: "리눅스 네트워크 네임스페이스를 이용해 컨테이너 네트워킹의 기본 원리를 직접 구성해 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - Container
  - Networking
  - namespace
  - veth
  - bridge
  - NAT
hidden: true

---

<br>

컨테이너 네트워킹은 결국 리눅스 네트워크 네임스페이스 위에 만들어진다. Docker의 `docker0` bridge, Kubernetes의 `cni0` bridge, Pod의 `eth0` — 이 모든 것이 네임스페이스, veth pair, bridge, 라우팅, NAT라는 동일한 building block 위에 서 있다. 이번 글에서는 이 building block을 하나씩 직접 구성하며, 컨테이너 네트워킹의 기본 원리를 이해한다.

<br>

# TL;DR

- **네임스페이스 격리**: `ip netns add`로 격리된 네트워크 공간을 만든다. 각 네임스페이스는 독립된 인터페이스, ARP, 라우팅 테이블을 가진다.
- **veth pair (1:1 연결)**: 가상 케이블로 두 네임스페이스를 직접 연결한다. 네임스페이스가 많아지면 O(N²) 연결이 필요해 확장성이 없다.
- **bridge (N:N 연결)**: 가상 스위치(bridge)를 두고, 각 네임스페이스의 veth를 bridge에 연결한다. N개의 네임스페이스가 bridge 하나로 통신할 수 있다.
- **호스트 ↔ 네임스페이스**: bridge에 IP를 부여하면 호스트도 네임스페이스 네트워크에 참여한다.
- **외부 통신**: 라우팅 + NAT(MASQUERADE)로 outbound, 포트포워딩(DNAT)으로 inbound 트래픽을 처리한다.

<br>

# 실습 환경

> **TODO**: 실습 환경 프로비저닝 방법 정리. VM, Vagrant, multipass 등 사용할 환경에 맞게 작성할 것.

실습에는 리눅스 호스트가 필요하다. 네트워크 네임스페이스(`ip netns`)를 사용하므로 root 권한이 필요하다.

필요한 도구:

- `iproute2` (`ip` 명령어)
- `iptables`
- `ping` (연결 확인용)

```bash
# 도구 확인
ip -V
iptables -V
```

> 실습이 끝난 후 정리:
> ```bash
> ip netns del red
> ip netns del blue
> ip link del v-net-0
> iptables -t nat -F
> ```

<br>

# 네임스페이스 생성 및 격리 확인

<!-- TODO: 네임스페이스 격리 개념도 -->

네트워크 네임스페이스는 프로세스에게 독립된 네트워크 스택(인터페이스, ARP 테이블, 라우팅 테이블, iptables 규칙)을 제공한다. 컨테이너가 각자의 `eth0`을 가질 수 있는 이유다.

```bash
ip netns add red
ip netns add blue

ip netns
# red
# blue
```

네임스페이스 안에서 인터페이스를 확인하면 loopback만 보인다. 호스트의 `eth0` 등은 보이지 않는다:

```bash
ip netns exec red ip link
# 1: lo: <LOOPBACK> ...

ip -n red link
# 동일한 결과 (축약 문법)
```

ARP 테이블, 라우팅 테이블도 호스트와 완전히 별개다:

```bash
ip netns exec red arp
ip netns exec red route
```

<br>

# 네임스페이스 간 연결

격리된 네임스페이스끼리 통신하려면 가상 케이블(veth pair)이 필요하다. 연결 방식은 두 가지다:

- **veth pair 직접 연결 (1:1)**: 두 네임스페이스를 케이블로 직접 연결
- **bridge 경유 (N:N)**: 가상 스위치(bridge)를 두고 각 네임스페이스를 연결

어느 방식이든 공통 절차는 동일하다:

1. 격리된 공간을 만든다: `ip netns add`
2. 가상 케이블을 만든다: `ip link add ... type veth peer ...`
3. 케이블 끝을 원하는 곳에 꽂는다: `ip link set ... netns ...` 또는 `ip link set ... master ...`
4. IP 주소를 붙인다: `ip addr add`
5. 인터페이스를 활성화한다: `ip link set ... up`

## veth pair로 1:1 직접 연결

veth pair는 양 끝이 있는 가상 케이블이다. 한쪽에 패킷을 넣으면 다른 쪽으로 나온다.

### 가상 케이블 생성

<!-- TODO: veth pair 생성 다이어그램 -->

```bash
ip link add veth-red type veth peer name veth-blue
```

두 개의 가상 인터페이스(`veth-red`, `veth-blue`)가 한 쌍으로 생성된다.

### 각 인터페이스를 네임스페이스에 연결

<!-- TODO: veth를 네임스페이스에 연결하는 다이어그램 -->

```bash
ip link set veth-red netns red
```

```bash
ip link set veth-blue netns blue
```

각 끝을 해당 네임스페이스에 꽂는다. 물리 케이블의 한쪽을 기기에 꽂는 것과 같다.

### IP 주소 할당

<!-- TODO: IP 할당 다이어그램 -->

```bash
ip -n red addr add 192.168.15.1/24 dev veth-red
```

```bash
ip -n blue addr add 192.168.15.2/24 dev veth-blue
```

### 인터페이스 활성화

<!-- TODO: 인터페이스 활성화 다이어그램 -->

```bash
ip -n red link set veth-red up
```

```bash
ip -n blue link set veth-blue up
```

### 확인

통신 확인:

```bash
ip netns exec red ping 192.168.15.2
```

ARP 테이블 확인 — 각 네임스페이스에서 상대방의 MAC 주소가 등록되어 있다:

<!-- TODO: ARP 테이블 확인 스크린샷 -->

```bash
ip netns exec red arp
# 192.168.15.2 → blue의 MAC 주소

ip netns exec blue arp
# 192.168.15.1 → red의 MAC 주소
```

호스트의 ARP 테이블에는 네임스페이스 내부의 veth IP가 보이지 않는다. 네임스페이스가 격리된 것이다:

```bash
arp
```

## bridge 경유 N:N 연결

veth pair의 1:1 직접 연결은 네임스페이스가 많아질수록 O(N²) 연결이 필요하다. 가상 스위치(bridge)를 두면 N개의 네임스페이스가 하나의 bridge를 통해 통신할 수 있다.

### 기존 veth pair 삭제

<!-- TODO: veth pair 삭제 다이어그램 -->

veth pair는 한쪽을 삭제하면 다른 쪽도 자동 삭제된다:

```bash
ip -n red link del veth-red
```

### bridge 인터페이스 생성

<!-- TODO: bridge 생성 다이어그램 -->

```bash
ip link add v-net-0 type bridge
```

호스트 입장에서 bridge는 `eth0` 같은 또 다른 네트워크 인터페이스일 뿐이다:

```bash
ip link
# ...
# 6: v-net-0: <BROADCAST,MULTICAST> mtu 1500 qdisc noop ...
```

생성 직후 인터페이스는 DOWN 상태다. 활성화해야 한다:

```bash
ip link set dev v-net-0 up
```

### 가상 케이블 생성

<!-- TODO: bridge용 veth pair 다이어그램 -->

이번에는 veth pair의 한쪽 이름에 `-br` 접미사를 붙여 bridge에 연결될 쪽임을 나타낸다:

```bash
ip link add veth-red type veth peer name veth-red-br
ip link add veth-blue type veth peer name veth-blue-br
```

### 네임스페이스 및 bridge에 연결

1:1 직접 연결에서는 veth 양쪽을 각각의 네임스페이스에 넣었지만, 이번에는 한쪽을 네임스페이스에, 다른 쪽을 bridge에 연결한다.

<!-- TODO: 네임스페이스 + bridge 연결 단계별 다이어그램 -->

```bash
ip link set veth-red netns red
ip link set veth-red-br master v-net-0

ip link set veth-blue netns blue
ip link set veth-blue-br master v-net-0
```

> `-br` 접미사 네이밍 컨벤션으로 어떤 네임스페이스와 관련된 bridge 쪽 인터페이스인지 알 수 있다.

### IP 주소 할당

각 네임스페이스 쪽 veth에 IP를 할당한다. bridge 인터페이스는 스위치 역할만 하면 되니 IP를 할당하지 않는다:

<!-- TODO: IP 할당 다이어그램 -->

```bash
ip -n red addr add 192.168.15.1/24 dev veth-red
ip -n blue addr add 192.168.15.2/24 dev veth-blue
```

### 인터페이스 활성화

```bash
ip -n red link set veth-red up
ip -n blue link set veth-blue up
```

<!-- TODO: 최종 bridge 연결 완성 다이어그램 -->

이제 모든 네임스페이스가 가상 스위치(bridge)에 연결되었고, 서로 통신할 수 있다.

<br>

# 호스트 ↔ 네임스페이스 연결

<!-- TODO: 호스트-네임스페이스 연결 다이어그램 -->

## 문제

호스트와 네임스페이스의 네트워크 스택은 분리되어 있다. 호스트에서 네임스페이스 내부 IP(`192.168.15.x`)로 ping해도 도달할 수 없다.

## 해결: bridge에 IP 부여

```bash
ip addr add 192.168.15.5/24 dev v-net-0
```

IP를 부여하는 것만으로 되는 이유는 L2 연결이 이미 갖춰져 있기 때문이다:

1. bridge(`v-net-0`)는 이미 UP 상태
2. 네임스페이스들의 veth pair가 이미 bridge에 연결됨
3. 네임스페이스 안의 veth에 IP가 이미 할당됨

**IP 부여가 트리거하는 일:**

1. 호스트 커널이 bridge를 **자기 인터페이스 중 하나**로 인식한다 (마치 `eth0`처럼)
2. 커널이 **자동으로 라우팅 테이블에 경로를 추가**한다: `192.168.15.0/24 dev v-net-0`
3. 호스트가 `192.168.15.x`로 패킷을 보내면, 커널이 bridge로 전달하고, bridge가 L2 스위칭으로 올바른 veth에 전달한다

비유하자면, bridge는 이미 네임스페이스들에 물리적으로 꽂혀 있는 스위치다. IP를 주기 전에는 호스트가 이 스위치에 연결되지 않은 상태였고, IP를 주는 순간 호스트도 이 스위치에 랜선을 꽂은 것이다.

## 확인

```bash
ping 192.168.15.1   # red 네임스페이스
ping 192.168.15.2   # blue 네임스페이스

ip route
# 192.168.15.0/24 dev v-net-0 proto kernel scope link src 192.168.15.5
```

<br>

# 네임스페이스 ↔ 외부 네트워크

여태까지의 네트워크는 호스트 내부에 격리되어 있다. 외부 세계로 통하는 유일한 관문은 호스트의 ethernet port(`eth0`)다.

## 네임스페이스 → 외부 (Outbound)

### 1단계: 라우팅 추가

<!-- TODO: 라우팅 추가 전 unreachable 다이어그램 -->

네임스페이스에서 LAN(`192.168.1.0/24`)으로 ping하면 `Network is unreachable`:

```bash
ip netns exec blue ping 192.168.1.3  # unreachable
ip netns exec blue route              # 외부 경로 없음
```

bridge IP(`192.168.15.5`)를 게이트웨이로 지정하는 라우팅을 추가한다:

<!-- TODO: 라우팅 추가 후 다이어그램 -->

```bash
ip netns exec blue ip route add 192.168.1.0/24 via 192.168.15.5
```

호스트는 두 네트워크 모두에 발을 걸치고 있으므로(`192.168.15.5` + `192.168.1.x`) 패킷을 전달할 수 있다.

### 2단계: NAT 설정

<!-- TODO: NAT 설정 다이어그램 -->

라우팅을 추가해서 `unreachable`은 해결됐지만, 응답이 돌아오지 않는다. 패킷은 나가지만, 외부 호스트가 `192.168.15.x`(private IP)로 응답을 보낼 방법이 없기 때문이다.

호스트에서 MASQUERADE(SNAT) 설정으로 나가는 패킷의 출발지 IP를 호스트 IP로 변환한다:

```bash
iptables -t nat -A POSTROUTING -s 192.168.15.0/24 -j MASQUERADE
```

### 3단계: 디폴트 게이트웨이 추가

<!-- TODO: 디폴트 게이트웨이 다이어그램 -->

LAN 대역은 통신되지만, 인터넷(예: `8.8.8.8`)은 여전히 `unreachable`이다:

```bash
ip netns exec blue ping 8.8.8.8       # unreachable
ip netns exec blue route
# 192.168.15.0   ← 자기 네트워크
# 192.168.1.0    ← 1단계에서 추가한 LAN 대역
# → 그 외 대역에 대한 경로가 없음
```

디폴트 게이트웨이를 추가하여 모든 알 수 없는 대역을 bridge를 통해 호스트로 보낸다:

```bash
ip netns exec blue ip route add default via 192.168.15.5
```

## 외부 → 네임스페이스 (Inbound)

### 방법 1: 외부 호스트에 라우팅 추가

`192.168.15.0/24`는 `192.168.1.2`를 통하라고 외부 호스트에 설정한다. 모든 외부 호스트에 일일이 설정해야 하므로 확장성이 없다.

### 방법 2: 포트포워딩 (DNAT)

<!-- TODO: 포트포워딩 다이어그램 -->

호스트의 특정 포트로 들어오는 트래픽을 네임스페이스로 전달한다:

```bash
iptables -t nat -A PREROUTING -p tcp --dport 80 --to-destination 192.168.15.2:80 -j DNAT
```

패킷 흐름:

1. 외부 클라이언트가 `192.168.1.2:80`으로 요청
2. 패킷이 호스트의 `eth0`에 도착
3. **PREROUTING** 체인에서 DNAT 적용: 목적지를 `192.168.1.2:80` → `192.168.15.2:80`으로 변경
4. 호스트가 `192.168.15.2`를 보고 bridge를 통해 blue 네임스페이스로 전달
5. blue 네임스페이스의 프로세스가 응답
6. 응답 시 커널의 conntrack이 자동으로 출발지를 `192.168.15.2` → `192.168.1.2`로 되돌림

외부에서는 호스트 IP만 알면 된다. 네임스페이스 내부 IP를 노출할 필요 없다. 단, 호스트 IP + 매핑된 포트는 알아야 한다. Docker의 `-p 80:80` 포트 매핑이 바로 이 원리다.

### 수동 DNAT의 한계

위 예시는 포트 하나(80)에 대한 매핑일 뿐이다. 컨테이너가 많아지면 호스트 포트를 수동으로 매핑해야 하고, 포트 충돌도 수동으로 관리해야 한다.

이 섹션은 컨테이너 네트워킹의 building block을 보여주는 것일 뿐이다. Docker, Kubernetes Service, Ingress가 이 한계를 자동화하고 확장한다:

- **Kubernetes Service (ClusterIP)**: 포트가 아니라 가상 IP + DNS 이름으로 접근. kube-proxy가 iptables 규칙을 자동 관리
- **Kubernetes NodePort**: 모든 노드에서 같은 포트(30000~32767)로 접근 가능하도록 자동 설정
- **Ingress**: 80/443 하나로 들어와서 도메인/경로 기반으로 여러 서비스에 라우팅

<br>

# 정리

| 요소 | 역할 | 없으면? |
| --- | --- | --- |
| **Namespace** | 격리된 네트워크 공간 | 격리할 대상이 없음 |
| **veth pair** | 격리된 공간을 연결하는 가상 케이블 | 패킷이 네임스페이스 밖으로 못 나감 |
| **Bridge** | N:N 내부 통신을 위한 가상 스위치 | 1:1로만 연결 가능 |
| **Routing + ip_forward** | 외부로의 경로 | 호스트 내부에 갇힘 |
| **iptables/NAT** | 주소 변환 | 패킷은 나가지만 응답이 안 돌아옴 |

각 요소를 좀 더 풀어 보면:

**veth pair** — 양 끝이 있는 가상 케이블. 격리된 네임스페이스를 외부와 물리적으로 잇는 유일한 수단이다.

- `ip link add veth-red type veth peer name veth-red-br`로 두 개의 가상 인터페이스가 한 쌍으로 생성된다
- 한쪽에 패킷을 넣으면 다른 쪽으로 나온다. 물리 케이블과 동일한 동작
- **1:1 직접 연결**: 양쪽을 각각의 네임스페이스에 넣는다
- **bridge 경유**: 한쪽을 네임스페이스에, 다른 쪽을 bridge에 연결한다 (`ip link set ... master v-net-0`)

**bridge** — 이중 역할을 할 수 있다:

- **L2 스위치 역할**: 네임스페이스끼리 통신 → IP 없이도 된다
- **L3 게이트웨이 역할**: 호스트가 네임스페이스에 접근 → IP가 필요하다

**routing + ip_forward** — 외부로 나가기 위한 경로 결정:

- 네임스페이스에 게이트웨이 라우팅 추가 (`ip route add ... via`)
- 호스트에서 `ip_forward` 활성화 (패킷 전달 허용)
- 이게 없으면 패킷이 bridge에서 멈춘다

**iptables/NAT** — 주소 변환. 라우팅만으로는 응답이 돌아오지 않는다 (private IP 문제):

- **SNAT/MASQUERADE**: 나가는 패킷의 출발지를 호스트 IP로 변환 (outbound)
- **DNAT/포트포워딩**: 들어오는 패킷의 목적지를 네임스페이스 IP로 변환 (inbound)

<br>

# 참고 링크

> **TODO**: 참고 자료 링크 추가
