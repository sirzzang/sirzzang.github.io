---
title:  "[Kubernetes] 쿠버네티스 네트워킹: CNI (Container Network Interface)"
excerpt: "CNI 표준의 배경과 개념, 플러그인 분류(Reference/Solution), 설정 구조(IPAM 포함), 그리고 kubelet → containerd → CNI 바이너리 호출의 동작 방식을 정리한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Networking
  - CNI

---

<br>

Kubernetes에서 Pod이 생성될 때 네트워크 인터페이스는 어떻게 구성되고, IP는 어떻게 할당될까? 이 질문의 중심에 **CNI(Container Network Interface)**가 있다. 이번 글에서는 CNI의 배경, 개념, 플러그인 분류, 설정 구조, 그리고 컨테이너 런타임이 CNI 바이너리를 어떻게 호출하는지를 정리한다.

Pod 간 통신이 어떤 문제를 풀어야 하는지는 [네트워킹 모델]({% post_url 2026-05-04-Kubernetes-Networking-00-Model %})과 [파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %})에서 다루고, 그 통신이 실제로 어떤 순서로 동작하는지는 [CNI 동작 흐름]({% post_url 2026-03-19-Kubernetes-Networking-03-CNI-Flow %})에서 시나리오로 짚는다. 이 글은 그 모든 글의 토대가 되는 **CNI 표준 자체**에 집중한다.

<br>

# TL;DR

- **배경**: 컨테이너 네트워킹의 기본 절차, 표준화 동기, CNI와 Kubernetes의 관계, Kubernetes 네트워킹 모델 속 CNI의 위치
- **CNI 개념**: "CNI"와 "CNI 플러그인" 용어 구분, CNI 프로젝트의 구성 (Spec + Reference Plugins)
- **CNI Spec**: 정의 범위, 설계 원칙(Runtime과 Plugin의 책임 분리)
- **CNI 플러그인**: 네트워크/IPAM 플러그인 분리, Reference vs Solution, 솔루션의 두 레이어(바이너리 + 노드 에이전트)
- **CNI 설정**: 바이너리/설정 파일 경로, 설정 파일 구조(`type` + `ipam.type` 패턴, 플러그인별 차이), IPAM 방식
- **동작 방식**: kubelet → containerd → CNI 플러그인 호출 흐름, 같은 노드 내 1회성 설정(바이너리), 노드 간은 에이전트가 담당한다는 두 레이어 구분
- **노드 간 통신 분류**: 오버레이 / BGP / 클라우드 네이티브 라우팅 — 어떤 카테고리가 있는지만 짚고, 자세한 비교는 [파드 간 통신]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}) 글로

<br>

# 배경

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

## 표준화의 필요성

Docker, rkt, Mesos 등 다양한 컨테이너 런타임은 위의 과정을 각자의 방식으로 구현했다. 하는 일은 거의 같지만 구현이 조금씩 달랐다.

동일한 네트워킹 문제를 해결하면서도 통일된 접근 방식이 없었다. 이 문제를 해결하기 위해, 네트워킹 절차를 전담하는 **별도의 플러그인 프로그램**을 만들자는 아이디어가 나왔다. 예를 들어 `bridge`라는 플러그인은 컨테이너를 브릿지 네트워크에 연결하기 위한 모든 작업을 수행한다:

```bash
bridge add <container-id> /var/run/netns/<namespace-id>
```

컨테이너 런타임은 새 컨테이너를 생성한 후 이 플러그인을 호출하고, 컨테이너 ID와 네임스페이스를 전달하면 네트워킹이 구성된다. 플러그인이 처리하기 때문에 **컨테이너 런타임은 네트워킹에서 해방**된다.

이와 같은 프로그램의 사양과, 컨테이너 런타임이 이 프로그램을 호출하기 위한 방법의 단일 표준이 바로 **CNI(Container Network Interface)**다.

[CNI 공식 문서](https://www.cni.dev/docs/#why-develop-cni)도 이 문제를 직접 언급한다:

> Application containers on Linux are a rapidly evolving area, and within this area networking is not well addressed as it is highly environment-specific. We believe that many container runtimes and orchestrators will seek to solve the same problem of making the network layer pluggable.

## CNI와 Kubernetes

CNI는 원래 CoreOS가 자신들의 컨테이너 런타임인 **rkt**를 위해 만든 범용 표준이었다. 당시 Docker는 CNI 대신 자체 표준인 CNM(Container Network Model)을 밀었고, 두 진영이 경쟁하는 구도였다.

그런데 rkt는 사실상 사라졌고, Docker도 CNI를 채택하지 않았다. CNI가 살아남은 이유는 **Kubernetes가 Pod 네트워킹 표준으로 CNI를 채택**했기 때문이다.

- containerd, CRI-O가 CNI를 지원하는 이유 → Kubernetes의 CRI 구현체이기 때문
- Calico, Cilium, Flannel 같은 플러그인 생태계가 발전한 이유 → Kubernetes의 멀티 노드 Pod 통신, NetworkPolicy 등의 요구사항 때문
- 단독 Docker 환경에서 Calico나 Cilium을 쓴다는 이야기를 듣기 어려운 이유 → Docker는 CNI가 아니라 자체 CNM으로 `docker0` bridge를 만들고 네트워킹을 하기 때문

**Spec은 범용이지만, 생태계와 실질적인 존재 이유는 Kubernetes에 있다.** "CNI 플러그인"이라 하면 사실상 "Kubernetes 네트워킹 솔루션"을 의미한다.

## Kubernetes 네트워킹 모델

앞에서는 단일 호스트 내에서 컨테이너를 네트워크에 연결하는 문제와, 그 표준화로서의 CNI를 살펴봤다. Kubernetes의 네트워킹은 이보다 훨씬 넓다.

[Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/services-networking/#the-kubernetes-network-model)에 따르면, Kubernetes 네트워킹 모델은 다음과 같은 요소로 구성된다:

- **Pod 네트워크** (cluster network): 각 Pod이 클러스터 전체에서 고유한 IP를 가지고, 모든 Pod이 NAT 없이 직접 통신
- **Service API**: Pod이 변해도 안정적인 IP/hostname을 제공 (EndpointSlice, service proxy)
- **Gateway API / Ingress**: 클러스터 외부에서 Service에 접근
- **NetworkPolicy**: Pod 간 또는 Pod과 외부 간 트래픽 제어

Kubernetes가 직접 구현하는 부분도 있지만, 많은 영역에서 API와 요구사항만 정의하고 실제 구현은 빌트인 컴포넌트 또는 외부 컴포넌트가 담당한다:

| 영역 | Kubernetes 자체 제공 | 외부 컴포넌트 |
| --- | --- | --- |
| Pod network namespace 생성 | — | CRI 구현체 (containerd, CRI-O) |
| **Pod 네트워크** (IP 할당, Pod 간 통신) | — | **CNI 플러그인** |
| Service API (객체 정의) | O (빌트인 API) | — |
| EndpointSlice 관리 | O (빌트인 컨트롤러) | — |
| Service proxy (트래픽 라우팅) | O (kube-proxy 기본 제공) | 또는 Cilium 등이 대체 |
| NetworkPolicy (API 정의) | O (빌트인 API) | — |
| NetworkPolicy (규칙 적용) | — | CNI 솔루션 (Calico, Cilium 등) |
| Gateway API / Ingress | O (API 정의만) | Ingress Controller, Gateway Controller 등 |
| type: LoadBalancer | O (API 정의만) | Cloud Controller Manager |

Service API, EndpointSlice 컨트롤러, kube-proxy처럼 Kubernetes가 직접 제공하는 것도 있지만, Pod 네트워크, NetworkPolicy 적용, Ingress/Gateway 구현 등 실제 데이터 플레인 동작은 외부 컴포넌트가 담당한다.

## Kubernetes Pod 네트워킹 모델

**이 글에서 다루는 CNI는 이 중 Pod 네트워크를 담당한다.** 앞서 살펴본 네임스페이스, veth pair, bridge, 라우팅, NAT라는 building block이 바로 CNI 플러그인이 Pod 네트워크를 구현할 때 사용하는 요소다.

Pod 네트워킹에 대한 핵심 요구사항([Cluster Networking](https://kubernetes.io/docs/concepts/cluster-administration/networking/#the-kubernetes-network-model))은 다음 세 가지다:

1. 모든 Pod가 **고유한 IP 주소**를 가져야 한다
2. 같은 노드의 모든 Pod끼리 **통신 가능**해야 한다
3. 다른 노드의 Pod과도 **NAT 없이 직접 통신** 가능해야 한다

Kubernetes는 IP 대역이나 서브넷 같은 세부 구현을 정의하지 않는다. 위 세 가지만 충족하면 어떤 방식으로든 상관없으며, 그 구현은 컨테이너 런타임을 통해 외부 플러그인에 위임된다. [공식 문서](https://kubernetes.io/docs/concepts/cluster-administration/networking/#how-to-implement-the-kubernetes-network-model)의 표현을 빌리면:

> The network model is implemented by the container runtime on each node. The most common container runtimes use **Container Network Interface (CNI)** plugins to manage their network and security capabilities.

"most common"이라는 표현을 쓰고 있지만, 현재 Kubernetes에서 지원하는 컨테이너 런타임(containerd, CRI-O)은 모두 CNI를 네트워크 플러그인 인터페이스로 사용한다. 사실상 **CNI가 유일한 경로**이며, 위 요구사항을 아무리 완벽하게 구현해도 CNI Spec을 따르지 않으면 Kubernetes에서 사용할 수 없다.

단, 이 요구사항은 **Kubernetes가 정의한 것**이지 CNI가 정의한 것이 아니다. CNI는 "런타임이 플러그인을 어떻게 호출하는가"를 정의하는 인터페이스 표준일 뿐이다. 따라서 CNI 플러그인이라고 해서 위 요구사항을 반드시 충족하는 것은 아니며, 이 차이는 [뒤에서](#reference-plugins의-한계와-solution-플러그인) 다시 다룬다.

<br>

# CNI 개념

"CNI"라는 단어는 두 가지를 가리킨다:

- **CNI (Container Network Interface)**: 컨테이너 런타임과 네트워크 플러그인 사이의 **표준 인터페이스**(사양). stdin으로 JSON을 받고, stdout으로 JSON을 반환하는 규약을 정의한다.
- **CNI 플러그인**: 그 사양을 구현한 바이너리 실행 파일. containerd가 필요할 때마다 fork/exec으로 실행하며, 이 표준을 준수하는 한 어떤 플러그인이든 어떤 런타임과도 조합할 수 있다.

> 실무에서는 "CNI 설치했어?", "어떤 CNI 써?"처럼 혼용되기도 한다. 마치 USB는 표준 규격이지만 일상에서 "USB 샀어"라고 말하는 것과 같다. 하지만 정확히 뭘 말하는지 구분할 수 있어야 한다.

실제로 [CNI 프로젝트](https://github.com/containernetworking)도 이 두 가지를 함께 제공한다:

| 구분 | 설명 | 예시 |
| --- | --- | --- |
| **CNI Spec** | 인터페이스 규약 | ADD/DEL/CHECK 명령, JSON 설정 형식 |
| **Reference Plugins** | Spec의 참조 구현체 (CNI 프로젝트가 직접 제공) | `bridge`, `vlan`, `ipvlan`, `macvlan`, `host-local`, `dhcp` |

Spec만 있으면 실제로 동작하는지 검증할 수 없으므로, **"이 Spec대로 만들면 이렇게 동작한다"**를 보여주는 참조 구현이 함께 필요하다. 단순한 네트워킹 시나리오에서는 Reference Plugins만으로도 충분하기 때문에 실용성도 있다. 이 Spec을 기반으로 Calico, Flannel, Cilium, Weave 등 **서드파티 플러그인**이 만들어진다.

> 비유하면 JDBC는 인터페이스(Spec)이지만 JDK에 기본 드라이버가 포함된 것과 유사하다. CSI(Container Storage Interface)도 Spec이지만 기본 provisioner가 있는 것과 같다.

이하 **Spec**과 **플러그인**을 각각 다룬다.

<br>

# CNI Spec

## 정의 범위

[CNI Spec](https://www.cni.dev/docs/spec/#overview)에 따르면, CNI는 **Linux 애플리케이션 컨테이너를 위한 범용 플러그인 기반 네트워킹 솔루션**이다. Spec이 정의하는 핵심 용어는 다음과 같다:

- **container**: 네트워크 격리 도메인. 네트워크 네임스페이스나 가상 머신이 될 수 있다.
- **plugin**: 지정된 네트워크 설정을 적용하는 프로그램.
- **runtime**: CNI 플러그인을 실행하는 프로그램. (containerd, CRI-O 등)

이 용어를 기반으로, [CNI Spec](https://www.cni.dev/docs/spec/#summary)은 다음 다섯 가지를 규정한다:

1. 관리자가 네트워크 설정을 정의하는 **형식** (`/etc/cni/net.d/`의 JSON 설정 파일)
2. 컨테이너 런타임이 네트워크 플러그인에 요청하는 **프로토콜** (ADD/DEL/CHECK 등)
3. 설정을 기반으로 플러그인을 실행하는 **절차**
4. 플러그인이 다른 플러그인에 기능을 위임하는 **절차** (IPAM 등)
5. 플러그인이 런타임에 결과를 반환하는 **데이터 타입**

정리하면, CNI Spec은 "**네트워크 플러그인을 어떻게 만들고, 런타임이 어떻게 호출하는가**"를 정의하는 표준 인터페이스다. 이 표준을 준수하는 한, 어떤 런타임이든 어떤 플러그인이든 조합해서 사용할 수 있다.

## 설계 원칙: 책임 분리

위 5가지 항목을 관통하는 핵심 설계 원칙은 **런타임과 플러그인의 책임 분리**다.

**Container Runtime의 책임:**

- 네트워크 네임스페이스 생성
- 컨테이너가 연결할 네트워크 식별
- 컨테이너 ADD 시 네트워크 플러그인 호출
- 컨테이너 DEL 시 네트워크 플러그인 호출
- JSON 형식의 네트워크 설정 전달

**Plugin의 책임:**

- ADD, DEL, CHECK 명령어 지원
- container id, network ns 등 파라미터 지원
- Pod에 대한 IP 주소 할당 관리
- 결과를 특정 형식으로 반환

이 분리가 가져오는 효과는 아래와 같다.

1. **런타임은 네트워킹을 몰라도 된다**: containerd는 "ADD 호출하고 JSON 넘기면 끝"이라는 규약만 알면 된다. 네트워크가 bridge인지 VXLAN인지 BGP인지 신경 쓸 필요 없다.
2. **플러그인은 런타임을 몰라도 된다**: Calico는 containerd든 CRI-O든 같은 방식으로 호출되니, 런타임별로 따로 구현할 필요 없다.
3. **독립적으로 교체/업데이트할 수 있다**: containerd 버전 올리면서 Calico를 건드릴 필요 없고, Flannel에서 Cilium으로 바꿔도 containerd를 수정할 필요 없다.

<br>

# CNI 플러그인

모든 CNI 플러그인은 같은 Spec을 구현하므로, 컨테이너 런타임 입장에서는 어떤 플러그인이든 동일한 방식으로 호출할 수 있다. 이 섹션에서는 플러그인이 어떤 종류로 나뉘고, 어떻게 조합되며, 생태계가 어떻게 구성되는지를 다룬다.

## 구분: 네트워크 플러그인과 IPAM 플러그인

CNI Spec이 정의한 역할 기준으로, CNI 플러그인은 **네트워크 플러그인**(메인)과 **IPAM 플러그인** 두 종류로 나뉜다. CNI Spec은 이 둘을 조합해서 사용하도록 설계되어 있다.

**네트워크 플러그인 (메인 플러그인)**: bridge, veth pair 생성, 오버레이 네트워크 등 **네트워크 연결 자체**를 담당한다. 여기서 오버레이 네트워크란, 물리 네트워크 위에 가상 네트워크를 한 겹 더 구성하여 서로 다른 노드의 Pod이 직접 통신할 수 있게 하는 방식이다(자세한 내용은 [CNI 동작 흐름]({% post_url 2026-03-19-Kubernetes-Networking-03-CNI-Flow %}) 글의 VXLAN 시나리오 참고). [설정 파일](#설정-파일-구조)의 `"type"` 필드로 지정한다.

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

## Reference Plugins의 한계와 Solution 플러그인

여기서 중요한 점은, **CNI Spec을 만족하는 것과 Kubernetes Pod 네트워킹 모델을 만족하는 것은 별개**라는 것이다. CNI Spec은 "런타임이 플러그인을 어떻게 호출하는가"만 정의하지, "모든 Pod이 고유 IP를 갖고 노드 간 NAT 없이 통신해야 한다"는 요구하지 않는다. 그건 Kubernetes가 정의한 요구사항이다.

`bridge` + `host-local` 같은 Reference 조합은 CNI Spec을 완벽하게 만족하는 유효한 플러그인이다. 하지만 Kubernetes 입장에서는 부족하다. **같은 노드 내 Pod 간 통신만 가능**하고, 노드 간 Pod 통신(오버레이)이나 NetworkPolicy 같은 Kubernetes가 요구하는 기능은 제공하지 않기 때문이다.

실제 대부분의 Kubernetes 클러스터에서는 이런 기능들(오버레이, IPAM, NetworkPolicy 등)을 묶어서 제공하는 **Solution 플러그인**을 사용한다. Calico, Flannel, Cilium 등이 여기에 해당한다. 단, 모든 솔루션이 모든 기능을 제공하는 것은 아니다:

|  | 노드 내 네트워킹 | 크로스 노드 네트워킹 (오버레이) | IPAM | NetworkPolicy |
| --- | --- | --- | --- | --- |
| **bridge** (Reference) | O | X | 조합 필요 (`host-local` 등) | X |
| **Flannel** | 내부적으로 bridge 사용 | O (VXLAN) | `host-local` | X |
| **Calico** | 자체 구현 | O (BGP/VXLAN) | 자체 IPAM | O |
| **Cilium** | 자체 구현 (eBPF) | O (Geneve 등) | 자체 IPAM | O |
| **Canal** (Flannel + Calico) | Flannel 담당 | O (VXLAN) | `host-local` | Calico 담당 |

어떤 솔루션을 선택할지는 클러스터의 요구사항에 따라 달라진다. 예를 들어 Flannel은 오버레이까지는 해주지만 NetworkPolicy가 없어서, NetworkPolicy가 필요하면 Calico의 정책 엔진만 얹은 **Canal** 조합을 쓰거나, 처음부터 Calico·Cilium 같은 올인원 솔루션을 선택한다.

## 솔루션 플러그인의 구성

`kubectl apply -f calico.yaml` 같은 명령으로 CNI 솔루션을 설치하면, 실제로 **두 레이어**가 배포된다:

| 레이어 | 정체 | 역할 | 생명주기 |
| --- | --- | --- | --- |
| **CNI 바이너리** | `/opt/cni/bin/`의 실행 파일 | Pod 생성 시 veth pair 생성, IP 할당 등 1회성 네트워크 설정 | Pod마다 호출되고 종료 |
| **노드 에이전트** | DaemonSet으로 각 노드에 배포되는 Pod (+ CRD 등) | 오버레이 터널 유지, 라우팅 관리, NetworkPolicy 적용 등 클러스터 전체의 지속적 네트워크 관리 | 각 노드에 상시 실행 |

설치 과정을 보면 이 구조가 드러난다:

1. `kubectl apply` → DaemonSet 배포
2. DaemonSet의 **init container**가 바이너리를 `/opt/cni/bin/`에 복사하고, 설정 파일을 `/etc/cni/net.d/`에 생성
3. 메인 컨테이너가 에이전트로서 상시 실행

이 DaemonSet Pod은 **`hostNetwork: true`**로 실행된다. 노드의 네트워크 네임스페이스를 직접 사용하므로, CNI 플러그인 호출 없이 노드의 `eth0`으로 통신한다. CNI가 아직 준비되지 않은 상태에서 CNI 플러그인 Pod 자체를 띄워야 하는 닭과 달걀(chicken-and-egg) 문제를 이렇게 해결한다.

이 두 레이어가 런타임에 어떻게 연동되는지는 [동작 방식](#동작-방식)에서 다룬다.

<br>


# CNI 설정

CNI 솔루션의 구성(바이너리 + 컨트롤 플레인)은 [앞서](#솔루션-플러그인의-구성) 살펴봤다. 이제 바이너리와 설정 파일이 실제로 어디에 위치하고, 어떤 구조로 되어 있는지 살펴 보자.

## 바이너리 (`/opt/cni/bin/`)

컨테이너 런타임(containerd, CRI-O 등)이 CNI 플러그인을 찾는 경로다. containerd 기준으로 설정 파일(`/etc/containerd/config.toml`)의 CRI 플러그인 CNI 섹션에서 변경할 수 있다:

```toml
[plugins."io.containerd.grpc.v1.cri".cni]
  bin_dir = "/opt/cni/bin"
```

Flannel을 설치한 노드를 예로 들면:

```bash
ls /opt/cni/bin/
# Reference Plugins (kubernetes-cni 패키지로 설치됨)
bandwidth  bridge  dhcp     firewall     host-device  host-local  ipvlan
loopback   macvlan portmap  ptp          sbr          static      tap
tuning     vlan    vrf
# Flannel DaemonSet의 init container가 복사한 바이너리
flannel
```

여러 바이너리가 함께 있지만, **출처가 다르다**:

| 출처 | 바이너리 예시 | 설치 시점 |
| --- | --- | --- |
| **CNI Reference Plugins 패키지** | `bridge`, `host-local`, `loopback`, `vlan`, `macvlan`, `ipvlan`, `ptp`, `bandwidth`, `portmap`, `firewall`, `tuning` 등 | 노드 초기 설정 시 (`kubernetes-cni` 패키지 또는 직접 다운로드) |
| **Solution 플러그인 DaemonSet** | `flannel` (또는 Calico라면 `calico`, `calico-ipam`) | CNI 솔루션 설치 시 (init container가 복사) |

Reference 플러그인 바이너리는 어떤 CNI 솔루션을 쓰든 노드 설정 시 함께 설치된다. Flannel처럼 내부적으로 `bridge`, `host-local`에 위임하는 솔루션이 이 바이너리들을 사용하기 때문이다.

바이너리가 있다고 전부 사용되는 것은 아니다. **`/etc/cni/net.d/`의 설정 파일에서 `type`으로 지정한 바이너리만** 컨테이너 런타임이 실행한다. 나머지는 디스크에 있을 뿐이다.

## 설정 파일 (`/etc/cni/net.d/`)

containerd가 CNI 플러그인 실행을 위해 읽는 설정 파일 경로다. 이 역시 같은 섹션에서 변경할 수 있다:

```toml
[plugins."io.containerd.grpc.v1.cri".cni]
  conf_dir = "/etc/cni/net.d"
```

실제 설정 파일 경로에서 설정 파일을 확인할 수 있다.

```bash
ls /etc/cni/net.d/
# 10-canal.conflist, 10-flannel.conflist 등
```

여러 파일이 있으면 **알파벳 순서로 첫 번째 파일만 선택**한다. 파일명 앞의 숫자 접두사(prefix)로 우선순위를 제어한다.

### 설정 파일 잔존 시 주의사항

containerd는 새 Pod을 만들 때마다 `/etc/cni/net.d/`의 설정 파일을 읽어서 CNI 플러그인을 호출한다. 설정 파일을 완전히 정리하지 않으면 문제가 발생할 수 있다:

1. **플러그인 바이너리는 없는데 설정만 남아있는 경우**: containerd가 삭제된 플러그인을 호출하려 시도 → 네트워크 설정 실패 → 새 Pod이 `ContainerCreating`에서 멈춤
2. **새 CNI를 설치했지만 이전 설정 파일이 남아있는 경우**: `/etc/cni/net.d/`에 파일이 여러 개 있으면 알파벳 순서로 첫 번째 파일이 선택됨 → 이전 플러그인 설정이 먼저 걸리면 새 CNI가 아닌 (이미 없는) 이전 플러그인이 선택되어 역시 실패

CNI 플러그인을 교체할 때는 이전 플러그인의 설정 파일을 반드시 삭제하거나 다른 디렉토리로 이동해야 한다.

## 설정 파일 구조

Reference 플러그인이든 Solution 플러그인이든, 설정 파일의 기본 구조는 동일하다. [앞서](#구분-네트워크-플러그인과-ipam-플러그인) 본 네트워크/IPAM 분리 원칙이 설정 파일에도 그대로 반영되어, 어떤 플러그인이든 `type` + `ipam.type`으로 구성된다.

**bridge + host-local** (Reference 조합):

```json
{
  "cniVersion": "1.0.0",
  "name": "mynet",
  "type": "bridge",
  "bridge": "cni0",
  "isGateway": true,
  "ipMasq": true,
  "ipam": {
    "type": "host-local",
    "subnet": "10.244.1.0/24",
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

이 조합만으로는 같은 노드 내 Pod 간 통신만 가능하다. Kubernetes Pod 네트워킹 모델의 세 가지 요구사항 중 "다른 노드의 Pod과 NAT 없이 통신"은 충족하지 못한다.

이를 보완하려면 노드 간 네트워크를 직접 구성해야 한다. [Kubernetes the Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way)가 이 방식을 사용하는데, 모든 노드가 같은 L2 네트워크에 있는 환경에서 각 노드에 다른 노드의 Pod CIDR로 가는 라우팅 규칙을 수동으로 추가한다:

```bash
# node-0에서: node-1의 Pod 대역으로 가는 패킷은 node-1(192.168.10.102)로
ip route add 10.200.1.0/24 via 192.168.10.102

# node-1에서: node-0의 Pod 대역으로 가는 패킷은 node-0(192.168.10.101)로
ip route add 10.200.0.0/24 via 192.168.10.101
```

bridge + 수동 라우팅으로 Kubernetes 요구사항을 충족할 수는 있지만, 한계가 분명하다:
- 노드가 추가/삭제될 때마다 모든 노드의 라우팅 테이블을 수동으로 갱신해야 한다
- 모든 노드가 같은 L2 네트워크에 있어야 한다 (다른 서브넷이면 이 방식 자체가 안 됨)
- 라우팅 설정이 휘발성이라 재부팅 시 사라진다

Solution 플러그인은 이 전체 과정을 자동으로 처리한다. 같은 L2가 아닌 환경에서도 오버레이 터널(VXLAN 등)이나 BGP를 통해 노드 간 통신을 구성하고, 노드 추가/삭제 시 라우팅을 동적으로 갱신한다.

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

세 설정 모두 `type` + `ipam.type` 구조를 따르지만, 채우는 방식이 다르다:

- **bridge**: `type`과 `ipam.type`을 각각 명시적으로 지정해서 조합한다.
- **Calico**: 메인(`calico`)과 IPAM(`calico-ipam`)을 한 프로젝트에서 함께 제공하지만, Spec의 분리 구조는 그대로 따른다.
- **Flannel**: CNI 플러그인 자체는 "설정 생성기 + 위임자" 역할이다. flanneld(데몬)가 노드의 서브넷을 할당하면, Flannel CNI 플러그인이 그 정보를 읽어서 `delegate`에 지정된 bridge 플러그인에 네트워킹을 위임하고, IPAM은 host-local로 자동 구성한다.

> `/opt/cni/bin/`을 보면 이 차이가 눈에 보인다. Calico를 설치하면 `calico`와 `calico-ipam` 두 바이너리가 들어있고, Flannel을 설치하면 `flannel`과 `bridge`, `host-local`이 함께 있다.

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

"로컬로 관리"한다는 것은, 각 노드에 겹치지 않는 서브넷이 할당되고(`--pod-network-cidr`), 노드가 **자기 서브넷 내에서 IP를 직접 파일로 기록/관리**한다는 것을 의미한다. 외부 서버에 묻지 않고 혼자서 할당/해제한다.

### dhcp

외부 DHCP 서버에서 IP를 임대(lease)받는 방식이다. DHCP 서버와 노드에 DHCP 데몬이 필요하여, Kubernetes에서는 거의 사용하지 않는다.

### 자체 IPAM

Weave나 Calico 같은 솔루션은 **자체 IPAM**을 내장하고 있다. `host-local`이나 `dhcp`를 쓰지 않고 자기만의 IP 관리 방식을 사용한다. 예를 들어 Weave는 전체 클러스터 CIDR을 에이전트끼리 분산 합의해서 나눈다.

<br>

# 동작 방식

지금까지 CNI의 개념, Spec, 플러그인 구조를 살펴봤다. 이제 Pod가 생성될 때 이 요소들이 실제로 어떻게 동작하는지 보자. [앞서](#kubernetes-네트워킹-모델) 본 Pod 네트워킹의 세 가지 요구사항이 CNI 플러그인에 의해 어떻게 구현되는지가 이 섹션의 핵심이다:

| 요구사항 | 구현 | 담당 |
| --- | --- | --- |
| 모든 Pod가 고유한 IP를 가진다 | IPAM 플러그인이 서브넷에서 IP 할당 | 바이너리 (1회성) |
| 같은 노드의 Pod끼리 통신 가능 | veth pair + cni0 bridge | 바이너리 (1회성) |
| 다른 노드의 Pod과 NAT 없이 통신 | 오버레이 터널 / BGP 라우팅 | DaemonSet 에이전트 (상시) |

## Kubernetes에서의 전체 흐름

Pod 생성 요청이 들어오면 다음과 같은 순서로 처리된다:

```
kube-apiserver → kubelet → containerd ──┬──→ CNI Plugin ─→ 네트워크 설정
                                        └──→ runc ───────→ 컨테이너 프로세스 시작
```

1. `kube-apiserver`가 Pod을 노드에 스케줄링한다
2. 해당 노드의 `kubelet`이 이를 감지하고 `containerd`에 컨테이너 생성을 요청한다
3. `containerd`가 네트워크 네임스페이스를 생성하고, **CNI 플러그인을 호출**하여 네트워크를 설정한다
4. 동시에 `runc`를 통해 컨테이너 프로세스를 시작한다

여기서 주의할 점은 kubelet이 직접 CNI를 호출하는 것이 아니라, **containerd가 `/etc/cni/net.d/` 설정을 읽고 `/opt/cni/bin/` 바이너리를 실행**한다는 것이다.

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

### 같은 노드 내 Pod 간 통신: 바이너리의 1회성 설정

바이너리 실행 내부에서는 메인 플러그인과 IPAM 플러그인이 협력한다:

```
Pod 생성 시:
1. containerd가 메인 CNI 플러그인 호출 (예: bridge)
2. 메인 플러그인이:
   ├── cni0 bridge가 없으면 생성 (최초 1회)
   ├── veth pair 생성 + 연결
   └── "IP가 필요하네" → ipam 섹션에 명시된 IPAM 플러그인 호출
3. IPAM 플러그인 (예: host-local)이:
   └── 서브넷에서 사용 가능한 IP를 골라서 반환
4. 메인 플러그인이 반환받은 IP를 Pod network namespace의 eth0에 할당
```

`cni0` bridge는 노드에 **처음 Pod이 생성될 때** bridge 플러그인이 만든다. DaemonSet 에이전트가 아니라 CNI 바이너리가 생성하며, 이미 존재하면 건너뛴다:

```bash
ip link add cni0 type bridge            # bridge 생성 (최초 1회)
ip addr add 10.244.1.1/24 dev cni0      # 게이트웨이 IP 할당
ip link set cni0 up                     # 활성화
```

이후 Pod마다 바이너리가 수행하는 핵심 작업은 다음과 같다:

```bash
# veth pair 생성 + 연결
ip link add vethXXX type veth peer name eth0
ip link set eth0 netns cni-abc123          # 한쪽을 Pod 네임스페이스로 이동
ip link set vethXXX master cni0            # 다른 쪽을 cni0 bridge에 연결
ip link set vethXXX up

# Pod 네임스페이스 내 설정
ip netns exec cni-abc123 ip addr add 10.244.1.5/24 dev eth0   # IP 할당
ip netns exec cni-abc123 ip link set eth0 up                   # 인터페이스 활성화
ip netns exec cni-abc123 ip route add default via 10.244.1.1   # 기본 게이트웨이 (cni0)
```

이 설정만으로도 같은 노드 내 Pod 간 통신은 가능하다. Pod들이 같은 cni0 bridge에 연결되어 있으므로, bridge가 L2 스위치 역할을 해서 트래픽을 전달한다.

### 다른 노드 간 Pod 통신: DaemonSet 에이전트의 상시 관리

Kubernetes 클러스터는 보통 여러 노드로 구성된다. 다른 노드의 Pod과 통신하려면 오버레이 터널이나 BGP 라우팅 같은 클러스터 수준의 네트워크가 필요한데, 1회성으로 실행되고 종료되는 바이너리만으로는 이를 구성하고 유지할 수 없다. 이 역할을 담당하는 것이 **DaemonSet 에이전트**다:

```
containerd
    ↓ fork/exec (CNI Spec)
/opt/cni/bin/calico                  ← CNI 바이너리 (Pod마다 호출, 종료)
    ↓ 통신 (Unix socket/API)
calico-node DaemonSet Pod            ← 노드 에이전트 (각 노드에 상시 실행)
    ├── 오버레이 터널 관리            cross-node Pod 통신 경로 확보
    ├── 라우팅 테이블 동적 관리       새 노드/Pod 추가 시 경로 갱신
    └── NetworkPolicy 적용           iptables/eBPF 규칙 변환
```

바이너리는 DaemonSet 에이전트와 협력하여 Pod-level 네트워크를 설정하고(예: IP 할당 시 에이전트의 IPAM과 조율), 에이전트는 그와 별개로 클러스터 전체의 네트워크를 **상시** 관리한다. containerd는 CNI Spec만 알면 되고, 솔루션의 에이전트는 모른다. 바이너리가 그 사이의 **접점** 역할을 한다.

bridge 같은 Reference 플러그인은 이런 에이전트 레이어 없이 바이너리만으로 구성된 가벼운 플러그인이므로, 같은 노드 내 통신까지만 가능하다. 대부분의 솔루션 플러그인(Calico, Cilium, Flannel 등)은 DaemonSet 에이전트를 포함하고 있어 노드 간 Pod 통신까지 처리한다.

## 노드 간 통신 분류

그렇다면 DaemonSet 에이전트가 노드 간 Pod 통신을 **어떻게** 만드는지가 다음 질문이다. 이 글에서는 카테고리만 짚고, 자세한 비교와 패킷 검증은 시리즈 다른 글로 미룬다.

Pod의 IP 대역(`10.244.0.0/16` 등)과 노드의 물리 네트워크 대역(`192.168.1.0/24` 등)이 다른 환경에서, "물리 네트워크가 모르는 Pod IP를 어떻게 다른 노드까지 도달시킬 것인가"는 결국 세 가지 접근 중 하나로 귀결된다:

| 분류 | 핵심 발상 | 대표 구현 | 자세히 |
| --- | --- | --- | --- |
| **오버레이** | Pod 패킷을 노드 IP로 캡슐화해서 물리 네트워크를 우회 | Flannel(VXLAN), Calico(VXLAN/IPIP), Cilium(Geneve), WireGuard | [파드 간 통신 — 오버레이]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#오버레이-별도-대역--터널링) / [CNI 동작 흐름]({% post_url 2026-03-19-Kubernetes-Networking-03-CNI-Flow %}) |
| **BGP 라우팅** | 물리 네트워크 라우터에 Pod 대역의 경로를 광고 | Calico(BGP) | [파드 간 통신 — BGP]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#bgp-별도-대역--라우팅-정보-전파) |
| **클라우드 네이티브 라우팅** | Pod에게 인프라가 라우팅 가능한 IP를 직접 부여 | AWS VPC CNI, GKE VPC-native, Azure CNI | [파드 간 통신 — 클라우드 네이티브]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#클라우드-네이티브-라우팅-인프라가-파드-ip를-직접-라우팅) / [EKS VPC CNI]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}) |

오버레이/BGP는 "Pod 대역 ≠ 노드 대역"을 전제로 도달 문제를 해결한다. 클라우드 네이티브 라우팅은 그 전제 자체를 없앤다 — Pod에게 VPC 서브넷의 IP를 부여하면 인프라가 원래부터 라우팅한다. 어느 분류든 CNI Spec과는 직교한다. CNI는 "런타임이 플러그인을 어떻게 호출하는가"를 정할 뿐이고, 노드 간 도달 메커니즘은 솔루션의 선택이다.

<br>

# 마무리

CNI는 결국 "컨테이너 런타임과 네트워크 플러그인 사이의 약속"이다. 이 약속 덕분에 containerd는 네트워크 구현을 몰라도 되고, Calico나 Flannel은 런타임에 종속되지 않는다.

[앞서](#kubernetes-pod-네트워킹-모델) 본 Kubernetes Pod 네트워킹의 세 가지 요구사항을 다시 짚으면:

1. 모든 Pod가 **고유한 IP 주소**를 가져야 한다
2. 같은 노드의 모든 Pod끼리 **통신 가능**해야 한다
3. 다른 노드의 Pod과도 **NAT 없이 직접 통신** 가능해야 한다

이 글에서 살펴본 CNI 표준은 위 요구사항이 **어떻게 구현되는지**가 아니라, **누가 어떤 책임을 지고 어떻게 호출되는지**를 정한다. 실제 구현 — IPAM이 IP를 어떻게 고르는지, veth + bridge가 어떻게 같은 노드 통신을 만드는지, 노드 간 통신이 오버레이/BGP/클라우드 네이티브 중 어느 방식으로 흐르는지 — 는 시리즈 다른 글에서 이어 본다.

- 같은 노드 Pod 간 통신의 veth pair / cni0 bridge 구조: [파드 간 통신 — 같은 노드]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#같은-노드의-파드-간-통신)
- 노드 간 통신 3가지 방식의 비교와 검증: [파드 간 통신 — 다른 노드]({% post_url 2026-05-04-Kubernetes-Networking-01-Pod-to-Pod %}#다른-노드의-파드-간-통신)
- Flannel VXLAN 시나리오로 따라가는 동작 흐름(VTEP, onlink, FDB, 캡슐화 단계): [CNI 동작 흐름]({% post_url 2026-03-19-Kubernetes-Networking-03-CNI-Flow %})
- AWS VPC CNI의 클라우드 네이티브 라우팅 구현: [EKS VPC CNI]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %})
- Service 라우팅(kube-proxy/iptables/IPVS/eBPF): [Service와 kube-proxy]({% post_url 2026-05-04-Kubernetes-Networking-04-Service %})

<br>

# 참고: Docker와 CNI

## Docker vs Kubernetes 네트워크 비교

|  | **Docker (기본)** | **Kubernetes CNI** |
| --- | --- | --- |
| **bridge 이름** | `docker0` | `cni0` |
| **bridge 생성 주체** | Docker 데몬이 직접 | CNI 플러그인이 생성 |
| **veth 생성 위치** | 호스트에서 생성 → 한 쪽을 컨테이너로 이동 | 네임스페이스 안에서 직접 생성 가능 |
| **index 부여** | 호스트 global 카운터 → 보통 안 겹침 | 네임스페이스별 독립 → 겹칠 수 있음 |

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

# 참고: @ifN 표기법

`ip addr`에서 `vethXXX@if3`의 `@if3`은 **veth pair 반대쪽 끝(peer)이 속한 네임스페이스 안에서의 index**를 뜻한다. 호스트에서 보이는 `vethXXX`의 peer는 Pod 네임스페이스 안의 `eth0`이므로, `@if3`은 "peer인 `eth0`이 Pod 네임스페이스에서 index 3번"이라는 뜻이다.

각 Pod 네임스페이스는 독립적으로 index를 부여한다:
- `1: lo` (loopback)
- `2: tunl0` (터널 인터페이스)
- **`3: eth0`** ← veth pair의 Pod 쪽 끝

따라서 **여러 veth가 모두 `@if3`**인 것은 정상이다. 서로 다른 네임스페이스이므로 index 충돌이 아니다.

```bash
7: vethb42afc2f@if3   # Pod A namespace index 3 (eth0)
8: veth4301c17b@if3   # Pod B namespace index 3 (eth0)
```

확인 방법:

```bash
ip netns exec <cni-namespace-id> ip link
# 3: eth0@if7  ← paired with host interface 7
```

<br>

# 참고 링크

- [CNI Specification (v1.1.0)](https://www.cni.dev/docs/spec/) -- CNI 공식 Spec 문서. 용어 정의, 설정 형식, 실행 프로토콜, 플러그인 위임 등 전체 규약.
- [CNI Project](https://www.cni.dev/docs/) -- CNI 프로젝트 소개, 사용 중인 런타임/플러그인 목록, Reference Plugins 안내.
- [CNI GitHub - containernetworking/cni](https://github.com/containernetworking/cni) -- CNI Spec 소스 저장소.
- [CNI Plugins GitHub - containernetworking/plugins](https://github.com/containernetworking/plugins) -- CNI Reference Plugins (bridge, host-local 등) 소스 저장소.

<br>