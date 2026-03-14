---
title:  "[Kubernetes] Kubernetes Networking: CNI (Container Network Interface)"
excerpt: "CNI의 배경, 개념, 동작 방식, 설정 구조, 그리고 오버레이 네트워크까지 정리해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
hidden: true

---

<br>

Kubernetes에서 Pod이 생성될 때 네트워크 인터페이스는 어떻게 구성되고, IP는 어떻게 할당되며, 다른 노드의 Pod과는 어떻게 통신할까? 이 모든 것의 중심에 **CNI(Container Network Interface)**가 있다. 이번 글에서는 CNI의 배경부터 동작 방식, 설정 구조, 그리고 오버레이 네트워크까지 정리한다.

<br>

# TL;DR

- **배경과 필요성**: 컨테이너 네트워킹의 기본 절차, 런타임마다 제각각인 문제, Kubernetes 네트워킹 모델, 표준화 동기
- **CNI 개념**: Spec 정의, 핵심 용어, Runtime과 Plugin의 책임 분리, "CNI"와 "CNI 플러그인" 용어 구분
- **플러그인 구조**: 네트워크 플러그인과 IPAM 플러그인 분리 설계, Reference Plugins vs 서드파티, 생태계 비교
- **동작 방식**: kubelet → containerd → CNI 플러그인 호출 → 네트워크 설정의 흐름
- **Pod 네트워킹 구조**: veth pair, bridge, 네트워크 네임스페이스, 인터페이스 생성 주체
- **CNI 설정**: 바이너리 경로, 설정 파일 경로/구조, IPAM 방식, 두 레이어(바이너리 + 컨트롤 플레인)
- **오버레이 네트워크**: 캡슐화를 통한 노드 간 Pod 통신

<br>

# 배경과 필요성

## 컨테이너 네트워킹의 기본 절차

![container-networking-overview]({{site.url}}/assets/images/container-networking-overview.webp)
<center><sup>https://medium.com/@rifewang/overview-of-kubernetes-cni-network-models-veth-bridge-overlay-bgp-ea9bfa621d32</sup></center>

컨테이너를 네트워크에 연결하려면 리눅스 네임스페이스 기반으로 다음과 같은 단계를 거쳐야 한다:

1. 네트워크 네임스페이스 생성
2. 브릿지 네트워크/인터페이스 생성
3. veth pair(가상 케이블) 생성
4. veth 한쪽을 네임스페이스에 연결
5. 다른쪽을 브릿지에 연결
6. IP 주소 할당
7. 인터페이스 활성화
8. NAT/IP 마스커레이드 설정

Docker, rkt, Mesos 등 다양한 컨테이너 런타임이 이 과정을 각자의 방식으로 구현했다. 하는 일은 거의 같지만 구현이 조금씩 달랐다.

## 표준화의 필요성

동일한 네트워킹 문제를 해결하면서도 통일된 접근 방식이 없었다. [CNI 공식 문서](https://www.cni.dev/docs/#why-develop-cni)도 이 문제를 직접 언급한다:

> Application containers on Linux are a rapidly evolving area, and within this area networking is not well addressed as it is highly environment-specific. We believe that many container runtimes and orchestrators will seek to solve the same problem of making the network layer pluggable.

이 문제를 해결하기 위해, 네트워킹 절차를 전담하는 **별도의 플러그인 프로그램**을 만들자는 아이디어가 나왔다. 예를 들어 `bridge`라는 플러그인은 컨테이너를 브릿지 네트워크에 연결하기 위한 모든 작업을 수행한다:

```bash
bridge add <container-id> /var/run/netns/<namespace-id>
```

컨테이너 런타임은 새 컨테이너를 생성한 후 이 플러그인을 호출하고, 컨테이너 ID와 네임스페이스를 전달하면 네트워킹이 구성된다. 플러그인이 처리하기 때문에 **컨테이너 런타임은 네트워킹에서 해방**된다.

이와 같은 프로그램의 사양과, 컨테이너 런타임이 이 프로그램을 호출하기 위한 방법의 단일 표준이 바로 **CNI(Container Network Interface)**다.

## Kubernetes 네트워킹 모델

Kubernetes는 네트워킹 솔루션을 내장하지 않고, **요구사항만 정의**한다. CNI 플러그인이 이를 구현한다.

3가지 핵심 요구사항:

1. 모든 Pod가 **고유한 IP 주소**를 가져야 한다
2. 같은 노드의 모든 Pod끼리 **통신 가능**해야 한다
3. 다른 노드의 Pod과도 **NAT 없이 직접 통신** 가능해야 한다

IP 대역, 서브넷 등 세부사항은 중요하지 않다. IP 자동 할당 + NAT 없는 Pod 간 연결만 구현하면 된다. Pod IP는 클러스터 내에서 고유하며, CNI 플러그인이 IPAM으로 관리한다.

<br>

# CNI 개념

## Spec이 정의하는 것

[CNI Spec](https://www.cni.dev/docs/spec/#overview)에 따르면, CNI는 **Linux 애플리케이션 컨테이너를 위한 범용 플러그인 기반 네트워킹 솔루션**이다. Spec이 정의하는 핵심 용어는 다음과 같다:

- **container**: 네트워크 격리 도메인. 네트워크 네임스페이스나 가상 머신이 될 수 있다.
- **plugin**: 지정된 네트워크 설정을 적용하는 프로그램.
- **runtime**: CNI 플러그인을 실행하는 프로그램. (containerd, CRI-O 등)

그리고 [CNI Spec이 정의하는 것](https://www.cni.dev/docs/spec/#summary)은 다음 다섯 가지다:

1. 관리자가 네트워크 설정을 정의하는 **형식** (JSON 설정 파일)
2. 컨테이너 런타임이 네트워크 플러그인에 요청하는 **프로토콜** (ADD/DEL/CHECK 등)
3. 설정을 기반으로 플러그인을 실행하는 **절차**
4. 플러그인이 다른 플러그인에 기능을 위임하는 **절차** (IPAM 등)
5. 플러그인이 런타임에 결과를 반환하는 **데이터 타입**

정리하면, CNI는 "**네트워크 플러그인을 어떻게 만들고, 런타임이 어떻게 호출하는가**"를 정의하는 표준 인터페이스다. 이 표준을 준수하는 한, 어떤 런타임이든 어떤 플러그인이든 조합해서 사용할 수 있다.

## Runtime과 Plugin의 책임 분리

CNI 표준은 런타임과 플러그인 각각의 책임을 명확히 나눈다.

**Container Runtime**의 책임:
- 네트워크 네임스페이스 생성
- 컨테이너가 연결할 네트워크 식별
- 컨테이너 ADD 시 네트워크 플러그인 호출
- 컨테이너 DEL 시 네트워크 플러그인 호출
- JSON 형식의 네트워크 설정 전달

**Plugin**의 책임:
- ADD, DEL, CHECK 명령어 지원
- container id, network ns 등 파라미터 지원
- Pod에 대한 IP 주소 할당 관리
- 결과를 특정 형식으로 반환

책임을 분리함으로써, 아래와 같은 효과를 얻는다.

1. **런타임은 네트워킹을 몰라도 된다**: containerd는 "ADD 호출하고 JSON 넘기면 끝"이라는 규약만 알면 된다. 네트워크가 bridge인지 VXLAN인지 BGP인지 신경 쓸 필요 없다.
2. **플러그인은 런타임을 몰라도 된다**: Calico는 containerd든 CRI-O든 같은 방식으로 호출되니, 런타임별로 따로 구현할 필요 없다.
3. **독립적으로 교체/업데이트할 수 있다**: containerd 버전 올리면서 Calico를 건드릴 필요 없고, Flannel에서 Cilium으로 바꿔도 containerd를 수정할 필요 없다.

## 용어 구분: "CNI"와 "CNI 플러그인"

"CNI"와 "CNI 플러그인"은 다르다.

- **CNI (Container Network Interface)**: 사양/표준/인터페이스 (문서)
  - 표준 인터페이스: stdin으로 JSON을 받고, stdout으로 JSON을 반환하는 단순한 규약
- **CNI 플러그인**: 그 사양을 구현한 바이너리 실행 파일
  - containerd가 필요할 때마다 fork/exec으로 실행
  - 이 표준을 준수하는 한, 모든 런타임은 표준을 준수하는 플러그인을 무엇이든 사용할 수 있어야 함

> 실무에서는 "CNI 설치했어?", "어떤 CNI 써?"처럼 혼용되기도 한다. 마치 USB는 표준 규격이지만 일상에서 "USB 샀어"라고 말하는 것과 같다. 하지만 정확히 뭘 말하는지 구분할 수 있어야 한다.

<br>

# CNI 플러그인 구조

## Spec과 Reference Plugins

CNI 프로젝트는 두 가지를 함께 제공한다:

| 구분 | 설명 | 예시 |
| --- | --- | --- |
| **CNI Spec** | 인터페이스 규약 | ADD/DEL/CHECK 명령, JSON 설정 형식 |
| **Reference Plugins** | Spec의 참조 구현체 (CNI 프로젝트가 직접 제공) | `bridge`, `vlan`, `ipvlan`, `macvlan`, `host-local`, `dhcp` |

Spec만 있으면 실제로 동작하는지 검증할 수 없으므로, **"이 Spec대로 만들면 이렇게 동작한다"**를 보여주는 참조 구현이 함께 필요하다. 단순한 네트워킹 시나리오에서는 기본 플러그인만으로도 충분하기 때문에 실용성도 있다.

> 비유하면 JDBC는 인터페이스(Spec)이지만 JDK에 기본 드라이버가 포함된 것과 유사하다. CSI(Container Storage Interface)도 Spec이지만 기본 provisioner가 있는 것과 같다.

이 Spec을 기반으로 Calico, Flannel, Cilium, Weave 등 **서드파티 플러그인**이 만들어진다. 모두 같은 CNI Spec을 구현하므로, 컨테이너 런타임 입장에서는 어떤 플러그인이든 동일한 방식으로 호출할 수 있다.

## 네트워크 플러그인과 IPAM 플러그인

CNI Spec이 정의한 역할 기준으로, CNI 플러그인은 **네트워크 플러그인**(메인)과 **IPAM 플러그인** 두 종류로 나뉜다. CNI Spec은 이 둘을 조합해서 사용하도록 설계되어 있다.

**네트워크 플러그인 (메인 플러그인)**: bridge, veth pair 생성, 오버레이 네트워크 등 **네트워크 연결 자체**를 담당한다. [설정 파일](#설정-파일-구조)의 `"type"` 필드로 지정한다.

- 기본 플러그인(Reference): `bridge`, `loopback`, `vlan`, `macvlan`
- 서드파티 플러그인: `flannel`, `calico`, `weave-net`, `cilium`

**IPAM 플러그인**: **IP 주소 할당/관리만** 전담하는 별도 플러그인이다. [설정 파일](#설정-파일-구조)의 `"ipam"` 섹션으로 지정한다.

- `host-local`: 각 노드가 로컬 파일로 IP 관리
- `dhcp`: 외부 DHCP 서버에서 IP 임대

CNI 스펙이 의도적으로 **네트워크 구성**과 **IP 관리**를 분리해서 설계한 이유는 다음과 같다:

- 네트워크 플러그인은 "어떻게 연결할지"만 신경 쓰고
- IPAM 플러그인은 "어떤 IP를 줄지"만 신경 쓰면 된다
- **조합**이 가능해진다 (bridge + host-local, bridge + dhcp, flannel + host-local, ...)

> Weave나 Calico 같은 솔루션은 **자체 IPAM**을 내장하고 있어 `host-local`을 쓰지 않을 수도 있다. 어느 쪽이든 설정 파일의 `ipam` 섹션에서 지정한다.

## 플러그인 생태계

[Reference Plugins](#spec과-reference-plugins)(`bridge`, `host-local` 등)만으로는 노드 간 Pod 통신을 구성할 수 없다. 노드 내 네트워킹이나 IP 할당 같은 한 조각만 담당하기 때문이다.

실제 Kubernetes 클러스터에서는 오버레이, IPAM, NetworkPolicy 등을 묶어서 제공하는 **Solution 플러그인**을 사용한다. `Calico`, `Flannel`, `Cilium` 등이 여기에 해당한다. 단, 모든 솔루션이 모든 기능을 제공하는 것은 아니다:

|  | 노드 내 네트워킹 | 크로스 노드 네트워킹 (오버레이) | IPAM | NetworkPolicy |
| --- | --- | --- | --- | --- |
| **bridge** (Reference) | O | X | 조합 필요 (`host-local` 등) | X |
| **Flannel** | 내부적으로 bridge 사용 | O (VXLAN) | `host-local` | X |
| **Calico** | 자체 구현 | O (BGP/VXLAN) | 자체 IPAM | O |
| **Cilium** | 자체 구현 (eBPF) | O (Geneve 등) | 자체 IPAM | O |
| **Canal** (Flannel + Calico) | Flannel 담당 | O (VXLAN) | `host-local` | Calico 담당 |

Flannel은 오버레이까지는 해주지만 NetworkPolicy가 없다. 그래서 Flannel의 네트워크 연결에 Calico의 NetworkPolicy 엔진만 얹은 **Canal**이라는 조합이 존재한다. Calico나 Cilium은 네트워킹, IPAM, NetworkPolicy를 모두 자체적으로 제공하는 올인원 솔루션이다.

## 설정 파일로 보는 구조

Solution 플러그인이라고 해서 Spec의 메인/IPAM 분리 구조를 무시하는 것은 아니다. 설정 파일을 비교하면 어떤 플러그인이든 `type` + `ipam.type` 구조는 동일하고, 값만 달라진다.

**bridge + host-local** (Reference 조합):

```json
{
  "type": "bridge",
  "bridge": "cni0",
  "ipam": {
    "type": "host-local",
    "subnet": "10.244.1.0/24"
  }
}
```

**Calico** (올인원 솔루션):

```json
{
  "type": "calico",
  "ipam": {
    "type": "calico-ipam"
  }
}
```

**Flannel**:

```json
{
  "type": "flannel",       // Flannel CNI 플러그인 호출
  "delegate": {            // 실제 네트워킹은 bridge 플러그인에 위임
    "isDefaultGateway": true
  }
  // ipam 없음: flanneld 데몬이 host-local + 할당된 서브넷으로 자동 구성
}
```

bridge는 `type`과 `ipam.type`을 각각 지정해서 조합한다. Calico는 메인(`calico`)과 IPAM(`calico-ipam`)을 한 프로젝트에서 함께 제공하지만, CNI Spec의 분리 구조는 그대로 따른다.

Flannel은 조금 다르다. Flannel CNI 플러그인 자체는 "설정 생성기 + 위임자" 역할이다:

1. **flanneld**(데몬)가 클러스터 CIDR에서 이 노드의 서브넷(예: `10.244.1.0/24`)을 할당하고 `/run/flannel/subnet.env`에 기록한다
2. **Flannel CNI 플러그인**이 호출되면, 그 서브넷 정보를 읽어서 `delegate`에 지정된 **bridge** 플러그인에 네트워킹을 위임한다
3. IPAM은 **host-local**로 자동 설정하되, 서브넷을 flanneld가 할당한 값으로 채운다

> `/opt/cni/bin/`을 보면 이 구조가 눈에 보인다. Calico를 설치하면 `calico`와 `calico-ipam` 두 바이너리가 들어있고, Flannel을 설치하면 `flannel`과 `bridge`, `host-local`이 함께 있다.

Reference 플러그인만 사용하면 실제로 어떻게 되는지 예를 들면, `bridge` + `host-local`만으로는 **같은 노드 내 Pod 간 통신만 가능**하다. 다른 노드의 Pod와 통신하려면 각 노드의 라우팅 테이블에 다른 노드의 Pod CIDR 경로를 수동으로 추가해야 한다:

```bash
ip route add 10.200.1.0/24 via 192.168.10.102
```

이것이 바로 Solution 플러그인이 자동으로 해주는 일이다. Flannel이나 Calico 같은 솔루션은 DaemonSet으로 각 노드에 에이전트를 배포하고, 오버레이 네트워크나 라우팅 설정을 자동으로 관리한다.

<br>

# 동작 방식

## Kubernetes에서의 전체 흐름

```
kube-apiserver → kubelet → containerd → CNI 플러그인 → 네트워크 설정
                                ↓
                              runc → 컨테이너 프로세스 시작
```

kubelet이 직접 CNI를 호출하는 것이 아니다. kubelet → containerd → CNI 순서로, **containerd가 `/etc/cni/net.d/` 설정을 읽고 `/opt/cni/bin/` 바이너리를 실행**한다.

## containerd → CNI 플러그인 호출

containerd가 CNI 플러그인 실행을 위해 CNI 플러그인 설정 파일을 읽는다. `/etc/cni/net.d/` 하위에 CNI 플러그인 별 설정이 저장된다.

```bash
/etc/cni/net.d/
├── 10-bridge.conf          # bridge 플러그인 설정
├── 10-calico.conflist      # Calico 설정
├── 10-flannel.conflist     # Flannel 설정
└── 99-loopback.conf        # loopback 설정
```

- 숫자 prefix (10-, 20-, 99-): 선택 우선순위 (낮은 번호가 먼저 선택됨)
- containerd는 사전순으로 **첫 번째 설정 파일 하나만** 사용하며, 나머지는 무시한다

CNI 실행 파일은 `/opt/cni/bin` 하위에 위치한다. containerd가 CNI 플러그인을 실행할 때는 환경 변수와 stdin을 통해 정보를 전달한다.

```bash
CNI_COMMAND=ADD \
CNI_CONTAINERID=abc123 \
CNI_NETNS=/var/run/netns/abc123 \
CNI_IFNAME=eth0 \
CNI_PATH=/opt/cni/bin \
/opt/cni/bin/bridge < /etc/cni/net.d/10-bridge.conf
```

주요 환경 변수는 다음과 같다.

- `CNI_COMMAND`: 수행할 작업 (ADD: 네트워크 연결, DEL: 네트워크 해제)
- `CNI_CONTAINERID`: 컨테이너의 고유 식별자
- `CNI_NETNS`: 컨테이너의 network namespace 경로
- `CNI_IFNAME`: 컨테이너 내부에 생성할 네트워크 인터페이스 이름
- `CNI_PATH`: CNI 플러그인 바이너리 검색 경로

## CNI 플러그인 실행

바이너리에 stdin으로 설정이 전달되고, 바이너리가 네트워크 설정을 수행한 후 stdout으로 결과를 반환한다.

네트워크 설정 과정에서 하는 일은 여러 가지가 있지만, 핵심은 veth pair 생성, IP 주소 할당, 네트워크 인터페이스 활성화, 라우팅 테이블 구성 등이다. 예를 들어 다음과 같은 작업들을 수행한다:

```bash
ip netns exec cni-abc123 ip addr add 10.244.1.5/24 dev eth0
ip netns exec cni-abc123 ip link set eth0 up
ip netns exec cni-abc123 ip route add default via 10.244.1.1
```

## 메인 플러그인과 IPAM 플러그인의 협력

메인 플러그인과 IPAM 플러그인의 협력 과정을 정리하면 다음과 같다:

```
Pod 생성 시:
1. containerd가 메인 CNI 플러그인 호출 (예: bridge)
2. 메인 플러그인이:
   ├── cni0 bridge가 없으면 생성 (최초 1회)
   ├── veth pair 생성 + 연결
   └── "IP가 필요하네" → ipam 섹션에 명시된 IPAM 플러그인 호출
3. IPAM 플러그인 (예: host-local)이:
   └── 서브넷에서 사용 가능한 IP를 골라서 반환
4. 메인 플러그인이 반환받은 IP를 Pod의 eth0에 설정
```

<br>

# Pod 네트워킹 구조

## veth pair + bridge

각 Pod은 **자기만의 네트워크 네임스페이스**를 가진다. Pod과 노드는 **veth pair**로 연결된다:

- veth pair의 한쪽 → Pod 네임스페이스 안의 `eth0`
- veth pair의 다른쪽 → 호스트의 `vethXXX`, **cni0 bridge에 연결** (`master cni0`)

`cni0`은 가상 브릿지(스위치)로, 같은 노드의 Pod들이 이 bridge를 통해 통신한다.

```
호스트 네임스페이스                        Pod 네임스페이스
┌───────────────────┐                ┌────────────────────────┐
│ cni0 (bridge)     │                │ Pod A                  │
│  ├─ 7: vethXXX ───┼──veth pair───► │  3: eth0 (10.244.0.2)  │
│  │                │                └────────────────────────┘
│  │                │                ┌────────────────────────┐
│  │                │                │ Pod B                  │
│  └─ 8: vethYYY ───┼──veth pair───► │  3: eth0 (10.244.0.3)  │
└───────────────────┘                └────────────────────────┘
```

## 인터페이스 생성 주체

| 인터페이스 | 누가 만드나 | 설명 |
| --- | --- | --- |
| `eth0` (노드) | 인프라/클라우드 | 노드의 기본 네트워크 인터페이스 |
| `flannel.1` | **Flannel 데몬** | 노드 간 오버레이 네트워크용 VXLAN 인터페이스 |
| `cni0` | **CNI bridge 플러그인** | Pod들이 연결되는 브릿지 (가상 스위치) |
| `vethXXX` | **CNI 플러그인** | Pod과 cni0을 연결하는 veth pair |

- **containerd**: 컨테이너 생성 + 네트워크 네임스페이스 생성까지만. 네트워크 설정은 CNI에 위임
- **CNI 플러그인**: `cni0`, `veth`, `flannel.1` 등 네트워크 구성 전체 담당

> Docker의 `docker0`은 Docker 데몬이 직접 만들지만, Kubernetes의 `cni0`은 CNI 플러그인이 만든다는 차이가 있다.

## Docker vs Kubernetes

|  | **Docker (기본)** | **Kubernetes CNI** |
| --- | --- | --- |
| **bridge 이름** | `docker0` | `cni0` |
| **bridge 생성 주체** | Docker 데몬이 직접 | CNI 플러그인이 생성 |
| **veth 생성 위치** | 호스트에서 생성 → 한 쪽을 컨테이너로 이동 | 네임스페이스 안에서 직접 생성 가능 |
| **index 부여** | 호스트 global 카운터 → 보통 안 겹침 | 네임스페이스별 독립 → 겹칠 수 있음 |

## @ifN 표기법

`ip addr`에서 `vethXXX@if3`의 `@if3`은 **peer가 속한 네임스페이스 안에서의 index**를 뜻한다.

각 Pod 네임스페이스는 독립적으로 index를 부여한다:
- `1: lo` (loopback)
- `2: tunl0` (터널 인터페이스)
- **`3: eth0`** ← veth pair의 Pod 쪽 끝

따라서 **여러 veth가 모두 `@if3`**인 것은 정상이다. 서로 다른 네임스페이스이므로 index 충돌이 아니다.

```bash
# 호스트에서 보면
7: vethb42afc2f@if3  ← Pod A 네임스페이스의 index 3 (eth0)
8: veth4301c17b@if3  ← Pod B 네임스페이스의 index 3 (eth0)
```

확인 방법:

```bash
# Pod 네임스페이스 안에서 확인
ip netns exec <cni-namespace-id> ip link
# 3: eth0@if7  ← 호스트의 7번 인터페이스와 pair
```

<br>

# CNI 설정

## CNI 솔루션의 두 레이어

"CNI 솔루션을 설치한다"는 것은 실제로 **두 레이어**를 설치하는 것이다:

```
containerd
    ↓ fork/exec (CNI Spec)
/opt/cni/bin/calico             ← 1. CNI 바이너리
    ↓ 통신 (Unix socket/API)
calico-node DaemonSet           ← 2. 컨트롤 플레인 컴포넌트
    ├── 오버레이 터널 관리
    ├── 라우팅 테이블 관리
    └── NetworkPolicy → iptables/eBPF 규칙 변환
```

| 레이어 | 정체 | 역할 | 생명주기 |
| --- | --- | --- | --- |
| **CNI 바이너리** | `/opt/cni/bin/`의 실행 파일 | Pod 생성 시 veth pair 생성, IP 할당 등 1회성 네트워크 설정 | Pod마다 호출되고 종료 |
| **컨트롤 플레인** | DaemonSet, CRD 등 Kubernetes 리소스 | 오버레이 터널 유지, 라우팅 관리, NetworkPolicy 적용 등 클러스터 전체의 지속적 네트워크 관리 | 노드에 상시 실행 |

containerd는 CNI Spec밖에 모른다. DaemonSet Pod에 직접 요청하는 게 아니라, `/opt/cni/bin/calico`를 fork/exec하고, **이 바이너리가 Calico 에이전트(DaemonSet)와 통신**해서 네트워크를 설정한다. 바이너리는 containerd(CNI Spec의 세계)와 솔루션의 컨트롤 플레인(Kubernetes의 세계) 사이의 **접점**이다.

`kubectl apply -f calico.yaml`을 실행하면 DaemonSet이 배포되고, DaemonSet의 **init container가 바이너리를 `/opt/cni/bin/`에 복사**하고, **설정 파일을 `/etc/cni/net.d/`에 생성**한다. 이후 메인 컨테이너가 에이전트로서 상시 실행된다.

## 바이너리 (`/opt/cni/bin/`)

containerd가 CNI 플러그인을 찾는 경로다. containerd 설정 파일(`/etc/containerd/config.toml`)의 CRI 플러그인 CNI 섹션에서 변경할 수 있다:

```toml
[plugins."io.containerd.grpc.v1.cri".cni]
  bin_dir = "/opt/cni/bin"
```

```bash
ls /opt/cni/bin/
bandwidth  calico      dhcp     firewall     host-local  loopback  portmap  sbr     tap     vlan
bridge     calico-ipam dummy    flannel      host-device ipvlan    macvlan  ptp     static  tuning  vrf
```

여러 플러그인의 바이너리가 함께 있지만, **출처가 다르다**:

| 출처 | 바이너리 예시 | 설치 시점 |
| --- | --- | --- |
| **CNI Reference Plugins 패키지** | `bridge`, `host-local`, `loopback`, `vlan`, `macvlan`, `ipvlan`, `ptp`, `bandwidth`, `portmap`, `firewall`, `tuning` 등 | 노드 초기 설정 시 (`kubernetes-cni` 패키지 또는 직접 다운로드) |
| **Solution 플러그인 DaemonSet** | `calico`, `calico-ipam`, `flannel` | CNI 솔루션 설치 시 (init container가 복사) |

바이너리가 있다고 전부 사용되는 것은 아니다. **`/etc/cni/net.d/`의 설정 파일에서 `type`으로 지정한 바이너리만** containerd가 실행한다. 나머지는 디스크에 있을 뿐이다.

## 설정 파일 (`/etc/cni/net.d/`)

containerd가 CNI 플러그인 실행을 위해 읽는 설정 파일 경로다. 이 역시 같은 섹션에서 변경할 수 있다:

```toml
[plugins."io.containerd.grpc.v1.cri".cni]
  conf_dir = "/etc/cni/net.d"
```

```bash
ls /etc/cni/net.d/
# 10-canal.conflist, 10-flannel.conflist 등
```

여러 파일이 있으면 **알파벳 순서로 첫 번째 파일만 선택**한다. 파일명 앞의 숫자 접두사(prefix)로 우선순위를 제어한다.

> 사용하지 않을 플러그인의 설정 파일이 알파벳 순으로 더 앞에 있으면 그 파일이 선택된다. 사용하지 않는 설정 파일은 삭제하거나 다른 디렉토리로 이동하는 것이 안전하다.

### 설정 파일 잔존 시 주의사항

containerd는 새 Pod을 만들 때마다 `/etc/cni/net.d/`의 설정 파일을 읽어서 CNI 플러그인을 호출한다. 설정 파일을 완전히 정리하지 않으면 문제가 발생할 수 있다:

1. **플러그인 바이너리는 없는데 설정만 남아있는 경우**: containerd가 삭제된 플러그인을 호출하려 시도 → 네트워크 설정 실패 → 새 Pod이 `ContainerCreating`에서 멈춤
2. **새 CNI를 설치했지만 이전 설정 파일이 남아있는 경우**: `/etc/cni/net.d/`에 파일이 여러 개 있으면 알파벳 순서로 첫 번째 파일이 선택됨 → 이전 플러그인 설정이 먼저 걸리면 새 CNI가 아닌 (이미 없는) 이전 플러그인이 선택되어 역시 실패

CNI 플러그인을 교체할 때는 이전 플러그인의 설정 파일을 반드시 삭제하거나 다른 디렉토리로 이동해야 한다.

## 설정 파일 구조

```json
{
    "cniVersion": "0.2.0",
    "name": "mynet",
    "type": "bridge",
    "isGateway": true,
    "ipMasq": true,
    "ipam": {
        "type": "host-local",
        "subnet": "10.22.0.0/16",
        "routes": [
            { "dst": "0.0.0.0/0" }
        ]
    }
}
```

| 필드 | 설명 |
| --- | --- |
| `cniVersion` | CNI 스펙 버전 (런타임과 플러그인 간 호환성) |
| `name` | 네트워크 이름 (식별용) |
| `type` | 사용할 CNI 플러그인 이름 → `/opt/cni/bin/`에서 해당 바이너리를 찾음 |
| `isGateway` | bridge에 IP를 할당해서 게이트웨이로 사용할지 여부 |
| `ipMasq` | Pod가 외부로 나갈 때 IP 마스커레이드(SNAT) 적용 여부 |
| `ipam.type` | IP 할당 방식 (`host-local`, `dhcp`) |
| `ipam.subnet` | Pod에 할당할 IP 대역 |
| `ipam.routes` | Pod 내부 라우팅 테이블 (`0.0.0.0/0` = default gateway) |

파일 확장자에 따라 단일 플러그인(`.conf`)과 여러 플러그인 체이닝(`.conflist`)을 구분한다. `.conflist`는 bridge + portmap 등 여러 플러그인을 순서대로 실행할 때 사용한다.

## IPAM

IPAM(IP Address Management)은 Pod에 IP 주소를 할당하는 방식이다. CNI 설정 파일의 `ipam` 섹션에서 지정한다.

### host-local

각 노드가 **로컬에서 독립적으로** IP를 관리한다. Kubernetes에서 사실상 표준이다.

| 항목 | 내용 |
| --- | --- |
| **IP 관리 주체** | 노드 자신 (로컬 파일) |
| **저장 위치** | `/var/lib/cni/networks/<name>/` |
| **동작 방식** | 설정된 서브넷 범위에서 순차 할당 |
| **외부 의존성** | 없음 (자체 완결) |

"로컬로 관리"의 의미: 각 노드에 겹치지 않는 서브넷이 할당되고(`--pod-network-cidr`), 노드가 **자기 서브넷 내에서 IP를 직접 파일로 기록/관리**한다. 외부 서버에 묻지 않고 혼자서 할당/해제한다.

### dhcp

외부 DHCP 서버에서 IP를 임대(lease)받는 방식이다. DHCP 서버와 노드에 DHCP 데몬이 필요하여, Kubernetes에서는 거의 사용하지 않는다.

### 자체 IPAM

Weave나 Calico 같은 솔루션은 **자체 IPAM**을 내장하고 있다. `host-local`이나 `dhcp`를 쓰지 않고 자기만의 IP 관리 방식을 사용한다. 예를 들어 Weave는 전체 클러스터 CIDR을 에이전트끼리 분산 합의해서 나눈다.

<br>

# 오버레이 네트워크

## 개념

Kubernetes에서는 각 Pod가 클러스터 전체에서 고유한 IP를 가지고, 서로 다른 노드의 Pod끼리 NAT 없이 직접 통신해야 한다. 그런데 노드들은 서로 다른 물리(또는 가상) 네트워크에 있을 수 있다.

**오버레이 네트워크(Overlay Network)**는 이 문제를 해결한다. 기존 물리 네트워크(언더레이, Underlay) 위에 **논리적인 가상 네트워크**를 한 겹 더 구성하여, 서로 다른 L3 네트워크에 있는 노드들이 마치 같은 L2 네트워크에 있는 것처럼 통신할 수 있게 한다.

동작 원리는 **캡슐화(Encapsulation)**다:

1. 원본 패킷을 한 번 더 감싸서(캡슐화) 물리 네트워크를 통과시킨다
2. 목적지 노드에서 다시 꺼내어(역캡슐화, Decapsulation) 원본 패킷을 전달한다

## 캡슐화 방식 비교

| 방식 | 캡슐화 | 특징 | 대표 CNI |
| --- | --- | --- | --- |
| **VXLAN** | L2 프레임 → UDP | 범용적, L3 네트워크 간 통신 가능 | Flannel, Calico |
| **IPIP** | IP 패킷 → IP 패킷 | 오버헤드가 적음, L3 네트워크 간 통신 가능 | Calico |
| **Geneve** | L2 프레임 → UDP (확장 가능) | VXLAN의 확장 버전, 메타데이터 추가 가능 | Cilium, OVN |
| **WireGuard** | IP 패킷 → UDP (암호화) | 암호화 오버레이 | Calico, Cilium |

> 참고: **오버레이 없는 방식**
>
> 캡슐화를 사용하지 않는 방식도 있다. Flannel의 **host-gw** 모드나 Calico의 **BGP 모드**는 각 노드의 라우팅 테이블을 직접 조작하여 Pod CIDR을 라우팅한다. 캡슐화 오버헤드가 없어 성능이 좋지만, 모든 노드가 같은 L2 네트워크에 있어야 한다는 제약이 있다. AWS VPC CNI처럼 클라우드 네이티브 방식으로 오버레이를 아예 쓰지 않는 경우도 있다.

## VXLAN

Kubernetes 환경에서 가장 널리 쓰이는 캡슐화 방식이 **VXLAN(Virtual Extensible LAN)**이다.

VXLAN은 L2 이더넷 프레임을 UDP 패킷으로 캡슐화하는 터널링 프로토콜이다. 캡슐화된 패킷 구조는 다음과 같다:

```
[          VTEP이 덧씌우는 오버레이 헤더            ][ Pod이 보낸 원본 패킷  ]
[ 외부 IP 헤더 | UDP 헤더 (port 4789) | VXLAN 헤더 |    원본 L2 프레임    ]
  ↑ 노드 IP                                           ↑ Pod 패킷
```

오른쪽의 원본 L2 프레임이 Pod이 보내려 했던 패킷 그대로이고, 왼쪽의 외부 IP/UDP/VXLAN 헤더가 VTEP이 오버레이 네트워크 전달을 위해 바깥에 덧씌우는 부분이다. Pod은 이 과정을 인지하지 못하며, 마치 같은 L2 네트워크에 있는 것처럼 통신한다.

각 노드에 **VTEP(VXLAN Tunnel Endpoint)**이라는 가상 인터페이스가 생성되어 캡슐화와 역캡슐화를 수행한다:

1. Pod에서 다른 노드의 Pod로 패킷을 보내면, 원본 L2 프레임이 VTEP에 도달한다
2. VTEP이 프레임을 UDP 패킷으로 **캡슐화**한다
3. 캡슐화된 패킷이 물리 네트워크를 통해 목적지 노드로 전달된다
4. 목적지 노드의 VTEP이 **역캡슐화**하여 원본 프레임을 꺼내고, 해당 Pod로 전달한다

Flannel의 `flannel.1`, Canal(Flannel + Calico)의 `flannel.1`, Calico의 `vxlan.calico` 인터페이스가 모두 VTEP 역할을 한다.

### 왜 UDP인가

터널링 프로토콜의 전송 수단으로 TCP가 아닌 UDP를 사용하는 데는 이유가 있다.

- **연결 설정이 불필요하다**: TCP처럼 handshake 없이 캡슐화한 패킷을 바로 보낼 수 있다.
- **기존 네트워크 인프라를 그대로 통과한다**: UDP는 라우터, 스위치, 방화벽이 별도 상태 관리 없이 전달할 수 있다.
- **TCP-over-TCP meltdown을 방지한다**: 터널 계층에서도 TCP를 쓰면, 원본 패킷의 TCP와 터널의 TCP가 각각 독립적으로 재전송을 시도하여 성능이 급격히 저하되는 문제가 발생한다.

UDP 자체는 전송 보장이 없지만, 여기서 UDP는 터널의 전송 수단("봉투")일 뿐이다. 신뢰성은 원본 패킷의 프로토콜이 담당한다:

```
[ 외부 IP | UDP (터널) | VXLAN | 원본 IP | TCP (앱) | 데이터 ]
                                          ↑
                              여기서 재전송을 책임짐
```

- 원본이 **TCP**라면: 캡슐화된 UDP 패킷이 소실되어도, 원본 TCP가 재전송한다.
- 원본이 **UDP**라면: 애초에 소실 가능성을 감수한 통신이므로 터널 계층에서도 마찬가지다.

## 노드 간 패킷 전달 과정

CNI 플러그인 설치 시 **모든 노드에 에이전트(데몬)가 DaemonSet으로 배포**된다. 에이전트들이 서로 통신하면서 **전체 클러스터 네트워크 토폴로지를 공유**한다. 즉 "어떤 Pod IP가 어느 노드에 있는지" 매핑 정보를 모든 에이전트가 알고 있다.

Pod A(노드 1, `10.244.1.3`) → Pod B(노드 2, `10.244.2.5`)로의 패킷 전달 과정:

**Step 1. 출발 노드의 에이전트가 가로챔**

Pod A가 패킷을 보내면 veth pair → cni0 bridge → 호스트 네임스페이스로 올라온다. 노드 1의 CNI 에이전트가 이 패킷을 가로채고, 토폴로지 정보에서 목적지 `10.244.2.5`가 **노드 2**에 있음을 확인한다.

**Step 2. 캡슐화(Encapsulation)**

에이전트가 원본 패킷을 새로운 패킷의 payload에 통째로 넣는다. 새 패킷의 목적지를 **노드 2의 실제 물리 IP**(`192.168.1.20`)로 설정한다. 물리 네트워크 인프라가 이 패킷을 라우팅할 수 있게 된다.

```
원본 패킷: [src: 10.244.1.3 (Pod A)] → [dst: 10.244.2.5 (Pod B)]
    ↓ 캡슐화
새 패킷:  [src: 192.168.1.10 (노드1)] → [dst: 192.168.1.20 (노드2)]
           └─ payload: 원본 패킷 통째로 들어있음
```

**Step 3. 물리 네트워크 전달**

캡슐화된 패킷이 일반 네트워크 인프라(스위치, 라우터 등)를 통해 노드 2에 도달한다. 물리 네트워크 입장에서는 `192.168.1.10 → 192.168.1.20` 트래픽으로만 보인다. Pod IP(`10.244.x.x`)는 전혀 모른다. 오버레이가 **물리 네트워크에 투명**하게 동작하는 것이다.

**Step 4. 역캡슐화(Decapsulation)**

노드 2의 CNI 에이전트가 도착한 패킷의 캡슐을 벗겨서 원본 패킷을 꺼낸다. 원본 패킷의 목적지(`10.244.2.5`)를 확인하고 해당 Pod B에게 전달한다.

```
새 패킷 도착: [src: 192.168.1.10 (노드1)] → [dst: 192.168.1.20 (노드2)]
    ↓ 역캡슐화
원본 패킷:    [src: 10.244.1.3 (Pod A)] → [dst: 10.244.2.5 (Pod B)]
               → cni0 bridge → veth pair → Pod B의 eth0
```

## CNI 플러그인별 비교

| CNI 플러그인 | 캡슐화 방식 | 특징 |
| --- | --- | --- |
| **Flannel** (기본) | VXLAN | L2 over L3, 간단하고 안정적 |
| **Weave Net** | 자체 프로토콜 (sleeve) 또는 VXLAN (fast datapath) | 암호화 지원, 자동 토폴로지 발견 |
| **Calico** (VXLAN 모드) | VXLAN | NetworkPolicy 지원이 강점 |
| **Calico** (BGP 모드) | **캡슐화 없음** (순수 L3 라우팅) | 오버헤드 최소, 같은 L2 서브넷 또는 BGP 피어링 필요 |

> 모든 CNI 플러그인이 오버레이를 쓰는 것은 아니다. Calico BGP 모드처럼 순수 라우팅 방식도 있다.

<br>

# 참고: Docker와 CNI

Docker는 CNI가 아닌 **CNM(Container Network Model)**이라는 자체 네트워크 표준을 사용한다. Docker에 CNI 플러그인을 직접 지정하는 것은 불가능하다.

하지만 CNI와 Docker를 전혀 같이 사용할 수 없다는 의미는 아니다. Kubernetes가 Docker를 사용하던 시절에는 이를 우회하는 방식을 썼다:

1. `--network=none`으로 Docker 컨테이너를 생성
2. CNI 플러그인을 수동으로 호출하여 네트워크 구성

```bash
# 1. 네트워크 없이 컨테이너 생성
docker run --network=none nginx

# 2. CNI 플러그인으로 네트워크 설정
bridge add <container-id> /var/run/netns/<namespace-id>
```

> 현재 Kubernetes는 Docker를 직접 사용하지 않고 containerd를 사용하므로, 이 우회 방식은 역사적 맥락으로 이해하면 된다.

<br>

# 참고 링크

- [CNI Specification (v1.1.0)](https://www.cni.dev/docs/spec/) -- CNI 공식 Spec 문서. 용어 정의, 설정 형식, 실행 프로토콜, 플러그인 위임 등 전체 규약.
- [CNI Project](https://www.cni.dev/docs/) -- CNI 프로젝트 소개, 사용 중인 런타임/플러그인 목록, Reference Plugins 안내.
- [CNI GitHub - containernetworking/cni](https://github.com/containernetworking/cni) -- CNI Spec 소스 저장소.
- [CNI Plugins GitHub - containernetworking/plugins](https://github.com/containernetworking/plugins) -- CNI Reference Plugins (bridge, host-local 등) 소스 저장소.
