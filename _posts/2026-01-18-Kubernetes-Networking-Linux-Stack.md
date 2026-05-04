---
title:  "[Kubernetes] 네트워킹: Linux 네트워크 스택 이해하기 - iptables와 conntrack"
excerpt: "Kubernetes 네트워킹이 Linux 네트워크 스택(iptables, conntrack) 위에서 어떻게 동작하는지 살펴보자."
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

# TL;DR

이번 글의 목표는 **Linux 네트워크 스택에서의 Kubernetes 네트워킹 이해**이다.

- **Kubernetes 네트워킹 개요**: 컴포넌트별 Linux 네트워크 활용 방식
- **iptables 규칙**: kube-proxy와 Flannel이 추가하는 nat, filter 테이블 규칙
- **conntrack**: 연결 추적을 통한 Service DNAT 동작 확인

<br>

# 들어가며

Kubernetes 네트워킹은 Linux 네트워크 스택 위에서 동작한다. [kubeadm을 이용한 클러스터 구성 실습]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %})에서 kube-proxy와 Flannel CNI가 배포된 시점을 기준으로, Linux 네트워크 스택을 살펴보며 Kubernetes 네트워킹이 어떻게 동작하는지 이해해 보자.

<br>

# Kubernetes 네트워킹 개요

Kubernetes 네트워킹의 핵심은 **Linux 네트워크 스택(특히 iptables)을 동적으로 조작**하는 것이다. Pod가 생성되거나 Service가 추가될 때마다 iptables 규칙이 자동으로 업데이트되어 트래픽이 올바른 목적지로 라우팅된다.
- [클러스터 네트워킹](https://kubernetes.io/ko/docs/concepts/cluster-administration/networking/)
- [Service](https://kubernetes.io/ko/docs/concepts/services-networking/service/)


<br>

지금까지 설치한 컴포넌트들이 어떻게 Linux 네트워크를 활용하는지 정리해 보자.

| 컴포넌트 | 설치 시점 | Linux 네트워크 활용 |
| --- | --- | --- |
| **kube-proxy** | [kubeadm init]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#static-pod-매니페스트) 시 DaemonSet 배포 | iptables로 Service → Pod 라우팅 |
| **Flannel** | [CNI 플러그인으로 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}#flannel-설치) | veth, bridge, VXLAN, iptables로 Pod 네트워크 구성 |

> **참고: kube-proxy 모드**
>
> kube-proxy는 Service 라우팅 구현 방식에 따라 여러 모드를 지원한다:
> - **iptables** (기본값): iptables 규칙으로 DNAT 수행. 대부분의 환경에서 사용
> - **IPVS**: Linux IPVS(IP Virtual Server)를 사용한 L4 로드밸런싱. 대규모 클러스터에서 더 나은 성능
> - **nftables**: iptables의 후속 기술. Kubernetes 1.29+에서 지원
>
> IPVS나 nftables를 사용하려면 [kubeadm 설정 파일]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#kubeadm-설정-파일)에서 `KubeProxyConfiguration`의 `mode` 필드를 명시해야 한다. 이전 글에서 별도 설정 없이 기본값을 사용했으므로 iptables 모드다.
>
> ```bash
> # kube-proxy ConfigMap에서 현재 모드 확인
> kubectl get cm kube-proxy -n kube-system -o yaml | grep mode
> #     mode: ""   # 빈 문자열 = iptables (기본값)
> ```

<br>

두 컴포넌트 모두 **iptables**를 사용하지만 목적이 다르다:
- **kube-proxy**: Service 추상화 (ClusterIP → Pod IP 변환)
- **Flannel**: Pod 네트워크 통신 (SNAT, 포워딩 허용)

<br>

# iptables 규칙

iptables 규칙을 확인하여 Kubernetes 네트워킹이 Linux 수준에서 어떻게 구현되는지 이해해 보자.

## iptables 개요

iptables는 Linux 커널의 패킷 필터링 프레임워크다. 패킷이 들어오면 **테이블**(nat, filter 등) 내의 **체인**(PREROUTING, FORWARD 등)을 순서대로 거치며, 각 체인의 규칙에 따라 패킷이 처리된다.

Kubernetes에서 iptables 규칙은 **Flannel**과 **kube-proxy**가 각각 다른 시점에 추가한다:

| 컴포넌트 | 규칙 추가 시점 | 체인 | 역할 |
| --- | --- | --- | --- |
| **Flannel** | flanneld 시작 시 | `FLANNEL-POSTRTG` (nat) | Pod → 외부 통신 시 SNAT |
| **Flannel** | flanneld 시작 시 | `FLANNEL-FWD` (filter) | Pod 네트워크 트래픽 포워딩 허용 |
| **kube-proxy** | Service 생성 시 | `KUBE-SERVICES` (nat) | Service ClusterIP 매칭 진입점 |
| **kube-proxy** | Service 생성 시 | `KUBE-SVC-*` (nat) | 서비스별 로드밸런싱 |
| **kube-proxy** | Service 생성 시 | `KUBE-SEP-*` (nat) | 실제 Pod IP로 DNAT |
| **kube-proxy** | Service 생성 시 | `KUBE-FORWARD` (filter) | 마킹된 패킷 포워딩 허용 |

## nat 테이블

nat 테이블은 주소 변환(NAT)을 담당한다. Service ClusterIP → Pod IP 변환(DNAT)과 Pod → 외부 통신 시 IP 변환(SNAT)이 여기서 처리된다.

<br>

### Flannel이 추가한 규칙: flanneld 시작 시

```bash
# Pod → 외부 통신 시 SNAT (--ip-masq 옵션)
iptables -t nat -S | grep FLANNEL
# -A POSTROUTING -m comment --comment "flanneld masq" -j FLANNEL-POSTRTG
# -A FLANNEL-POSTRTG -s 10.244.0.0/16 ! -d 224.0.0.0/4 ... -j MASQUERADE
```

Pod(`10.244.0.0/16`)에서 외부로 나가는 트래픽의 출발지 IP를 노드 IP로 변환(SNAT)한다. 이렇게 해야 외부 네트워크에서 응답을 노드로 돌려보낼 수 있고, 노드가 다시 Pod로 전달한다. `--ip-masq` 옵션이 이 규칙을 활성화한다.


### kube-proxy가 추가한 규칙: Service 생성 시

현재 시점에 이미 존재하는 Service들이 있어서 kube-proxy가 해당 규칙을 생성해 둔 상태다:

| Service | ClusterIP | 생성 시점 |
| --- | --- | --- |
| `default/kubernetes` | 10.96.0.1:443 | [kubeadm init]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#kubeadm-init-실행) 시 자동 생성 (API Server) |
| `kube-system/kube-dns` | 10.96.0.10:53 | [CoreDNS addon]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#coredns-kube-proxy) 배포 시 생성 |

```bash
# kube-dns Service (10.96.0.10:53) → CoreDNS Pod로 DNAT
iptables -t nat -S | grep "kube-dns:dns ->"
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... --probability 0.50000000000 -j KUBE-SEP-YIL6JZP7A3QYXJU2
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... -j KUBE-SEP-6E7XQMQ4RAYOWTTM
# (2개의 CoreDNS Pod에 50% 확률로 로드밸런싱)
```

<details markdown="1">
<summary>nat 테이블 전체 규칙</summary>

```bash
iptables -t nat -S
# -P PREROUTING ACCEPT
# -P INPUT ACCEPT
# -P OUTPUT ACCEPT
# -P POSTROUTING ACCEPT
# -N FLANNEL-POSTRTG
# -N KUBE-MARK-MASQ
# -N KUBE-NODEPORTS
# -N KUBE-POSTROUTING
# -N KUBE-SEP-6E7XQMQ4RAYOWTTM
# -N KUBE-SEP-ETI7FUQQE3BS2IXE
# ... (생략)
# -N KUBE-SERVICES
# -N KUBE-SVC-ERIFXISQEP7F7OF4
# -N KUBE-SVC-NPX46M4PTMTKRN6Y
# -N KUBE-SVC-TCOU7JCQXEZGVUNU
# [kube-proxy] 모든 들어오는/나가는 패킷을 KUBE-SERVICES 체인으로 전달
# [kube-proxy] 들어오는/나가는 패킷을 KUBE-SERVICES 체인으로 전달
# -A PREROUTING -m comment --comment "kubernetes service portals" -j KUBE-SERVICES
# -A OUTPUT -m comment --comment "kubernetes service portals" -j KUBE-SERVICES
# -A POSTROUTING -m comment --comment "kubernetes postrouting rules" -j KUBE-POSTROUTING
#
# [Flannel] Pod → 외부 통신 시 SNAT 처리를 위해 FLANNEL-POSTRTG로 전달
# -A POSTROUTING -m comment --comment "flanneld masq" -j FLANNEL-POSTRTG
#
# [Flannel] Pod CIDR에서 출발하는 트래픽을 노드 IP로 MASQUERADE (SNAT)
# -A FLANNEL-POSTRTG -s 10.244.0.0/16 ! -d 224.0.0.0/4 ... -j MASQUERADE --random-fully
#
# [kube-proxy] kube-dns Service (10.96.0.10:53) → CoreDNS Pod로 DNAT
# -A KUBE-SERVICES -d 10.96.0.10/32 -p udp --dport 53 -j KUBE-SVC-TCOU7JCQXEZGVUNU
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... --probability 0.50 -j KUBE-SEP-YIL6JZP7A3QYXJU2
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... -j KUBE-SEP-6E7XQMQ4RAYOWTTM
# -A KUBE-SEP-YIL6JZP7A3QYXJU2 -p udp -j DNAT --to-destination 10.244.0.2:53
# -A KUBE-SEP-6E7XQMQ4RAYOWTTM -p udp -j DNAT --to-destination 10.244.0.3:53
#
# [kube-proxy] kubernetes Service (10.96.0.1:443) → API Server로 DNAT
# -A KUBE-SERVICES -d 10.96.0.1/32 -p tcp --dport 443 -j KUBE-SVC-NPX46M4PTMTKRN6Y
# -A KUBE-SVC-NPX46M4PTMTKRN6Y ... -j KUBE-SEP-ETI7FUQQE3BS2IXE
# -A KUBE-SEP-ETI7FUQQE3BS2IXE -p tcp -j DNAT --to-destination 192.168.10.100:6443
```

</details>

<br>

## filter 테이블

filter 테이블은 패킷 필터링(허용/차단)을 담당한다. Pod 네트워크 트래픽의 포워딩 허용이 여기서 처리된다.

### Flannel이 추가한 규칙: flanneld 시작 시

```bash
# Pod 네트워크 트래픽 포워딩 허용
iptables -t filter -S | grep FLANNEL
# -A FORWARD -m comment --comment "flanneld forward" -j FLANNEL-FWD
# -A FLANNEL-FWD -s 10.244.0.0/16 ... -j ACCEPT
# -A FLANNEL-FWD -d 10.244.0.0/16 ... -j ACCEPT
```

Pod CIDR(`10.244.0.0/16`)에서 출발하거나 도착하는 트래픽의 포워딩을 허용한다.

### kube-proxy가 추가한 규칙: Service 생성 시

```bash
# 마킹된 패킷 포워딩 허용
iptables -t filter -S | grep KUBE-FORWARD
# -A KUBE-FORWARD -m conntrack --ctstate INVALID -j DROP
# -A KUBE-FORWARD -m mark --mark 0x4000/0x4000 -j ACCEPT
# -A KUBE-FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
```

kube-proxy가 마킹한 패킷(`0x4000`)과 기존 연결의 응답 패킷(`RELATED,ESTABLISHED`)을 포워딩 허용한다. 잘못된 패킷(`INVALID`)은 드롭한다.

<details markdown="1">
<summary>filter 테이블 전체 규칙</summary>

```bash
iptables -t filter -S
# -P INPUT ACCEPT
# -P FORWARD ACCEPT
# -P OUTPUT ACCEPT
# -N FLANNEL-FWD
# -N KUBE-EXTERNAL-SERVICES
# -N KUBE-FIREWALL
# -N KUBE-FORWARD
# -N KUBE-NODEPORTS
# -N KUBE-SERVICES
#
# [Flannel] Pod 네트워크 트래픽 포워딩 허용
# -A FORWARD -m comment --comment "flanneld forward" -j FLANNEL-FWD
# -A FLANNEL-FWD -s 10.244.0.0/16 -m comment --comment "flanneld forward" -j ACCEPT
# -A FLANNEL-FWD -d 10.244.0.0/16 -m comment --comment "flanneld forward" -j ACCEPT
#
# [kube-proxy] 마킹된 패킷 및 기존 연결 포워딩 허용
# -A KUBE-FORWARD -m conntrack --ctstate INVALID -j DROP
# -A KUBE-FORWARD -m mark --mark 0x4000/0x4000 -j ACCEPT
# -A KUBE-FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
```

</details>

<br>

# conntrack

conntrack 테이블을 확인하여 iptables NAT 규칙이 적용된 연결이 어떻게 추적되는지 이해해 보자.

## conntrack 개요

**conntrack(Connection Tracking)**은 Linux 커널의 네트워크 연결 상태 추적 시스템이다. kube-proxy가 Service의 ClusterIP를 Pod IP로 변환(DNAT)할 때 conntrack 테이블을 사용하여 응답 패킷을 올바른 출발지로 되돌린다.

| 역할 | 설명 |
| --- | --- |
| **NAT 상태 추적** | DNAT 규칙이 적용된 연결의 원본 주소를 기억하여 응답 패킷을 올바르게 라우팅 |
| **연결 상태 관리** | TCP 연결의 상태(ESTABLISHED, TIME_WAIT 등)를 추적하여 stateful 방화벽 기능 제공 |
| **Service 로드밸런싱** | 동일 클라이언트의 후속 패킷이 같은 Pod로 전달되도록 연결 유지 |
| **성능 최적화** | 이미 추적된 연결은 iptables 규칙을 다시 평가하지 않고 빠르게 처리 |

```bash
# conntrack 도구 설치
dnf install -y conntrack-tools
```

## 전체 conntrack 엔트리 조회

```bash
# 전체 conntrack 엔트리 조회
conntrack -L
# conntrack v1.4.8 (conntrack-tools): 286 flow entries have been shown.
```

<details markdown="1">
<summary>전체 출력 보기 (286 entries)</summary>

```
tcp      6 65 TIME_WAIT src=127.0.0.1 dst=127.0.0.1 sport=56844 dport=2381 src=127.0.0.1 dst=127.0.0.1 sport=2381 dport=56844 [ASSURED] mark=0
tcp      6 15 TIME_WAIT src=10.244.0.1 dst=10.244.0.2 sport=46574 dport=8080 src=10.244.0.2 dst=10.244.0.1 sport=8080 dport=46574 [ASSURED] mark=0
tcp      6 86399 ESTABLISHED src=127.0.0.1 dst=127.0.0.1 sport=46870 dport=2379 src=127.0.0.1 dst=127.0.0.1 sport=2379 dport=46870 [ASSURED] mark=0
tcp      6 86383 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED] mark=0
tcp      6 86399 ESTABLISHED src=192.168.10.100 dst=192.168.10.100 sport=54874 dport=6443 src=192.168.10.100 dst=192.168.10.100 sport=6443 dport=54874 [ASSURED] mark=0
udp      17 27 src=10.0.2.15 dst=175.195.167.194 sport=56947 dport=123 src=175.195.167.194 dst=10.0.2.15 sport=123 dport=56947 mark=0
udp      17 26 src=10.0.2.15 dst=168.126.63.1 sport=46942 dport=53 src=168.126.63.1 dst=10.0.2.15 sport=53 dport=46942 mark=0
tcp      6 86400 ESTABLISHED src=10.0.2.2 dst=10.0.2.15 sport=61614 dport=22 src=10.0.2.15 dst=10.0.2.2 sport=22 dport=61614 [ASSURED] mark=0
... (이하 생략)
```

</details>

<br>

## conntrack 엔트리 형식

```
tcp 6 86399 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED]
```

| 필드 | 예시 값 | 설명 |
| --- | --- | --- |
| 프로토콜 | `tcp` | 프로토콜 이름 |
| 프로토콜 번호 | `6` | 6=TCP, 17=UDP |
| TTL | `86399` | 연결 만료까지 남은 시간 (초) |
| 연결 상태 | `ESTABLISHED` | TCP 상태 (ESTABLISHED, TIME_WAIT, CLOSE 등) |
| **원본 패킷 (요청)** | `src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443` | CoreDNS Pod → kubernetes Service ClusterIP |
| **응답 패킷 (DNAT 역변환)** | `src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242` | API Server → CoreDNS Pod |
| 플래그 | `[ASSURED]` | 양방향 트래픽이 확인된 연결 |

## TCP 연결만 조회

```bash
# TCP 연결만 보기
conntrack -L -p tcp
# conntrack v1.4.8 (conntrack-tools): 279 flow entries have been shown.
```

## ESTABLISHED 상태만 조회

```bash
# ESTABLISHED 상태만 보기 (활성 연결)
conntrack -L -p tcp --state ESTABLISHED
# tcp  6 86376 ESTABLISHED src=127.0.0.1 dst=127.0.0.1 sport=47672 dport=2379 ... [ASSURED]        # etcd 연결
# tcp  6 86388 ESTABLISHED src=192.168.10.100 dst=192.168.10.100 sport=38154 dport=6443 ... [ASSURED]  # API Server 연결
# tcp  6 86375 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED]  # Service DNAT
# tcp  6 86399 ESTABLISHED src=10.0.2.2 dst=10.0.2.15 sport=61614 dport=22 ... [ASSURED]           # SSH 연결
# ... (68 flow entries)
```

### 주요 ESTABLISHED 연결 분석

| 연결 유형 | 예시 | 설명 |
| --- | --- | --- |
| etcd 연결 | `127.0.0.1:* → 127.0.0.1:2379` | API Server, Controller Manager 등이 etcd에 연결 (다수) |
| API Server 연결 | `192.168.10.100:* → 192.168.10.100:6443` | 컴포넌트들이 API Server에 연결 |
| **Service DNAT** | `10.244.0.3:48242 → 10.96.0.1:443` ↔ `192.168.10.100:6443 → 10.244.0.3` | CoreDNS가 `kubernetes` Service를 통해 API Server에 연결 |
| SSH 연결 | `10.0.2.2:61614 → 10.0.2.15:22` | Vagrant SSH 연결 |

> **Service DNAT 추적 예시**: `10.244.0.3`(CoreDNS Pod)이 `10.96.0.1:443`(kubernetes Service ClusterIP)에 접속하면, conntrack은 이 연결을 추적하고 응답 패킷이 `192.168.10.100:6443`(실제 API Server)에서 올 때 원래 목적지인 `10.244.0.3`으로 정확히 전달한다.

## 특정 포트 관련 연결

```bash
# Service(443) 관련 연결 확인
conntrack -L | grep dport=443
# tcp  6 86376 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED]
# tcp  6 86389 ESTABLISHED src=10.0.2.15 dst=10.96.0.1 sport=39156 dport=443 src=192.168.10.100 dst=10.0.2.15 sport=6443 dport=6826 [ASSURED]
# tcp  6 86383 ESTABLISHED src=10.244.0.2 dst=10.96.0.1 sport=40304 dport=443 src=192.168.10.100 dst=10.244.0.2 sport=6443 dport=40304 [ASSURED]
```

위 결과에서 `dst=10.96.0.1`(kubernetes Service ClusterIP)로 향하는 연결이 실제로는 `192.168.10.100:6443`(API Server)으로 DNAT되어 처리됨을 확인할 수 있다.

## 실시간 이벤트 추적

```bash
# 실시간 conntrack 이벤트 추적 (Ctrl+C로 종료)
conntrack -E
#     [NEW] tcp      6 120 SYN_SENT src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [UNREPLIED]
#  [UPDATE] tcp      6 60 SYN_RECV src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443
#  [UPDATE] tcp      6 86400 ESTABLISHED src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
#  [UPDATE] tcp      6 120 FIN_WAIT src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
#  [UPDATE] tcp      6 300 CLOSE_WAIT src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
#  [UPDATE] tcp      6 10 CLOSE src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
```

TCP 연결의 전체 생명주기를 실시간으로 관찰할 수 있다: `SYN_SENT` → `SYN_RECV` → `ESTABLISHED` → `FIN_WAIT` → `CLOSE_WAIT` → `CLOSE`.

## conntrack 커널 파라미터

```bash
# conntrack 관련 커널 파라미터 확인
sysctl -a | grep conntrack
# net.netfilter.nf_conntrack_buckets = 65536
# net.netfilter.nf_conntrack_count = 420              # 현재 추적 중인 연결 수
# net.netfilter.nf_conntrack_max = 131072             # 최대 추적 가능 연결 수
# net.netfilter.nf_conntrack_tcp_timeout_close = 10
# net.netfilter.nf_conntrack_tcp_timeout_close_wait = 3600
# net.netfilter.nf_conntrack_tcp_timeout_established = 86400
# net.netfilter.nf_conntrack_tcp_timeout_fin_wait = 120
# net.netfilter.nf_conntrack_tcp_timeout_syn_recv = 60
# net.netfilter.nf_conntrack_tcp_timeout_syn_sent = 120
# net.netfilter.nf_conntrack_tcp_timeout_time_wait = 120
# net.netfilter.nf_conntrack_udp_timeout = 30
# net.netfilter.nf_conntrack_udp_timeout_stream = 120
# ... (이하 생략)
```

| 파라미터 | 값 | 설명 |
| --- | --- | --- |
| `nf_conntrack_max` | 131072 | conntrack 테이블 최대 크기(최대 엔트리 수) |
| `nf_conntrack_count` | 420 | 현재 추적 중인 연결 수(현재 사용 중) |
| `nf_conntrack_buckets` | 65536 | 해시 테이블 버킷 수 |
| `nf_conntrack_tcp_timeout_established` | 86400초 (24시간) | ESTABLISHED 연결 유지 시간 |
| `nf_conntrack_tcp_timeout_close_wait` | 3600초 (1시간) | CLOSE_WAIT 상태 유지 시간 |
| `nf_conntrack_tcp_timeout_time_wait` | 120초 | TIME_WAIT 상태 유지 시간 |
| `nf_conntrack_udp_timeout` | 30초 | UDP 연결 타임아웃 |

> **트러블슈팅 팁**: 대규모 클러스터에서 `nf_conntrack: table full, dropping packet` 에러가 발생하면 `nf_conntrack_max` 값을 증가시켜야 한다. 현재 사용률은 `count/max = 420/131072 ≈ 0.3%`로 여유롭다. `conntrack -S`로 통계를 확인하여 drop된 패킷 수를 모니터링할 수 있다.

<br>

# 정리

Kubernetes 네트워킹은 iptables와 conntrack이라는 Linux 네트워크 스택의 두 축 위에서 동작한다.

## iptables: 패킷 경로 결정

iptables의 nat 테이블과 filter 테이블은 **kube-proxy**와 **Flannel** 두 컴포넌트가 각자의 목적에 맞게 사용한다.

| 구분 | kube-proxy | Flannel (VXLAN) |
| --- | --- | --- |
| **목적** | Service → Pod 라우팅 (ClusterIP, NodePort) | Pod 간 [오버레이 네트워크]({% post_url 2026-03-19-Kubernetes-CNI-Flow %}) 통신 |
| **nat 테이블** | KUBE-SERVICES, KUBE-SVC-*, KUBE-SEP-* 체인으로 Service IP를 Pod IP로 DNAT | FLANNEL-POSTRTG 체인으로 오버레이 트래픽 SNAT/MASQUERADE |
| **filter 테이블** | KUBE-FIREWALL, KUBE-FORWARD 체인으로 패킷 필터링 및 포워딩 허용 | 직접 filter 규칙을 추가하지 않음 |
| **규칙 특징** | Service/Endpoint 변경 시 동적으로 갱신 | 노드 부팅 시 설정, 비교적 정적 |

## conntrack: 연결 상태 추적

conntrack은 iptables의 DNAT/SNAT 규칙이 만든 **주소 변환 상태를 기억**하여, 응답 패킷이 원래 요청자에게 돌아갈 수 있도록 한다.

- **역할**: 요청 시 DNAT된 연결의 원본/변환 주소 쌍을 저장하고, 응답 시 자동으로 reverse NAT 수행
- **엔트리 구조**: 프로토콜, 상태, 타임아웃, 원본 tuple(src→dst), 변환 tuple(src→dst) 포함
- **운영 포인트**: `nf_conntrack_max`(테이블 크기)와 타임아웃 값이 대규모 클러스터에서 성능에 영향

## 핵심 흐름

클라이언트가 Service IP로 요청을 보내면:

1. **iptables nat** → Service IP를 실제 Pod IP로 DNAT (kube-proxy 규칙)
2. **conntrack** → 변환 전후 주소 쌍을 엔트리로 저장
3. **Pod 응답** → conntrack 엔트리를 참조하여 reverse DNAT 수행, 원래 클라이언트에게 전달

이 구조 덕분에 사용자는 Pod의 실제 IP를 몰라도 안정적인 Service IP로 통신할 수 있고, Pod이 재시작되어 IP가 바뀌어도 Service 접근에는 영향이 없다.

<br>
