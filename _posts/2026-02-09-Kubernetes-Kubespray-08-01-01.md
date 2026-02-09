---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: The Hard Way - 1. Network Gateway"
excerpt: "폐쇄망 환경 시뮬레이션을 위해 admin을 NAT Gateway로 구성하고, k8s-node의 인터넷 직접 접근을 차단해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Air-Gapped
  - Offline
  - Network
  - iptables
  - nftables
  - NAT
  - MASQUERADE
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **admin VM을 NAT Gateway로 구성**하여, k8s-node들이 admin을 통해서만 외부에 접근할 수 있도록 만든다. 폐쇄망 환경 시뮬레이션의 첫 번째 단계다.

- **네트워크 격리**: k8s-node의 인터넷 직접 연결(`enp0s8`) 차단
- **패킷 포워딩**: k8s-node에서 admin으로의 디폴트 라우트 추가, admin에서 `ip_forward` 활성화
- **주소 변환(MASQUERADE)**: admin에서 iptables NAT 설정으로 출발지 IP 변환
- **폐쇄망 복원**: MASQUERADE 제거 및 디폴트 라우팅 제거로 완전한 폐쇄망 환경 구성
- **(도전 과제)** iptables 대신 nftables로 동일한 NAT Gateway 구현


| 순서 | 설정 | 위치 | 목적 |
|------|------|------|------|
| 1 | `nmcli connection down enp0s8` | k8s-node | 인터넷 직접 연결 차단 |
| 2 | `+ipv4.routes "0.0.0.0/0 192.168.10.10"` | k8s-node | admin을 게이트웨이로 지정 |
| 3 | `iptables -t nat -A POSTROUTING -o enp0s8 -j MASQUERADE` | admin | 출발지 IP 변환 (NAT Gateway) |

<br>

# Network Gateway 구성의 필요성

[이전 글(8.1.0)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-00 %})에서 Vagrant로 실습 환경을 배포했다. 현재 모든 VM은 `enp0s8`(NAT)을 통해 인터넷에 직접 접근할 수 있다. 하지만 **폐쇄망 환경**에서는 이 인터넷 접근이 차단되어야 한다.

실제 기업 환경의 폐쇄망에서는 내부 서버가 직접 인터넷에 나갈 수 없고, **Bastion Server나 Admin Server를 경유**해서만 외부 리소스에 접근할 수 있다. 이를 시뮬레이션하기 위해 *의도적으로* 다음과 같은 구성을 만든다.

```
[인터넷 직접 접속]      node → enp0s8(NAT) → 인터넷
[admin 경유 접속]     node → enp0s9 → admin → enp0s8 → 인터넷  (MASQUERADE)
[폐쇄망]             node → enp0s9 → admin만 통신 가능, 인터넷 X
```

이 구성을 위해서는 3가지 핵심 설정이 맞물려야 한다.

| 순서 | 설정 | 위치 | 역할 | 없으면? |
|------|------|------|------|---------|
| 1 | 네트워크 격리 (`enp0s8 down`) | k8s-node | 인터넷 직접 연결 차단 | node가 admin 안 거치고 직접 나감 |
| 2 | 패킷 포워딩 (`ip_forward` + 디폴트 라우트) | admin + k8s-node | 커널이 패킷을 중계하도록 허용 + 경로 지정 | admin이 node 패킷을 버림 / node가 어디로 보낼지 모름 |
| 3 | 주소 변환 (`MASQUERADE`) | admin | 출발지 IP를 admin 것으로 변환 | 패킷은 나가지만 응답이 못 돌아옴 |

<br>

# 배경지식

## 네트워크 인터페이스

이 실습 환경의 VM에는 네트워크 인터페이스가 2개 있다.

| 인터페이스 | 네트워크 종류 | IP | 역할 |
|------------|--------------|-----|------|
| `enp0s8` | NAT | 10.0.2.15 (VirtualBox 기본값) | 외부 인터넷 접속용. `vagrant ssh`는 이 인터페이스의 포트포워딩을 사용 |
| `enp0s9` | Host-Only | 192.168.10.x (수동) | 호스트 - VM, VM - VM 내부 통신용. Vagrantfile에서 IP 직접 지정. 인터넷 불가 |

## 접속 방식: vagrant ssh vs ssh root@IP

두 접속 방식은 경유하는 인터페이스가 다르다. **enp0s8을 내리는 작업은 반드시 enp0s9 경로로 접속한 상태에서 해야** 세션이 끊기지 않는다.

| 접속 방법 | 경유 인터페이스 | enp0s8 내리면? |
|-----------|----------------|----------------|
| `vagrant ssh` 또는 `ssh -p 60001 127.0.0.1` | enp0s8 (NAT 포트포워딩) | 세션 끊김 |
| `ssh root@192.168.10.x` (호스트에서 직접) | enp0s9 (Host-Only) | 정상 유지 |

root 로그인은 프로비저닝 스크립트(`admin.sh`, `init_cfg.sh`)에서 `PermitRootLogin yes`와 비밀번호(`qwe123`)를 설정했기 때문에 가능하다.

## IP Forwarding

리눅스는 기본적으로 **"내 IP로 온 패킷만 처리하고, 나머지는 버린다"**. 보안상 일반 서버는 라우터가 아니므로, 자기 패킷이 아닌 것을 멋대로 중계하면 안 되기 때문이다.

```
node(192.168.10.11) → admin(192.168.10.10)으로 패킷 도착
  목적지: 8.8.8.8 (admin의 IP가 아님)

ip_forward = 0 (기본): "이거 내 패킷 아닌데?" → 버림
ip_forward = 1      : "내 패킷은 아니지만 forward 켜져있으니 전달해주자"
                        → enp0s8을 통해 8.8.8.8로 전달
```

| ip_forward | 용도 | 예시 |
|------------|------|------|
| `0` (기본) | 일반 서버/PC | 웹 서버, DB 서버 등 |
| `1` | 라우터/게이트웨이 역할 | 공유기, VPN 서버, **이 실습의 admin** |

이 실습에서는 `admin.sh`의 TASK 5에서 `ip_forward = 1`을 이미 설정했다.

## netfilter와 제어 도구 (iptables, nftables)

리눅스 커널 안에는 **netfilter**라는 패킷 처리 프레임워크가 있다. 네트워크 패킷이 커널을 통과할 때 특정 지점(hook)에서 룰을 적용해 패킷을 허용/차단/변환할 수 있게 해주는 엔진이다. netfilter는 패킷 흐름의 5개 지점에 hook을 제공한다.

| hook | 시점 | 대표 용도 |
|------|------|-----------|
| `PREROUTING` | 패킷이 들어온 직후, 라우팅 결정 전 | DNAT (목적지 변환) |
| `INPUT` | 라우팅 후, 로컬 프로세스로 전달될 때 | 방화벽 (들어오는 패킷 필터링) |
| `FORWARD` | 라우팅 후, 다른 인터페이스로 전달될 때 | 포워딩 패킷 필터링 |
| `OUTPUT` | 로컬 프로세스가 패킷을 생성했을 때 | 나가는 패킷 제어 |
| `POSTROUTING` | 패킷이 나가기 직전 | **MASQUERADE, SNAT (출발지 변환)** |

이 실습에서는 **POSTROUTING** hook을 사용한다. 패킷이 admin의 enp0s8으로 나가기 직전에 출발지 IP를 변환(MASQUERADE)하는 것이다. MASQUERADE와 SNAT은 둘 다 출발지 IP를 변환하지만, SNAT은 고정 IP를 직접 지정하고(`--to-source 10.0.2.15`), MASQUERADE는 나가는 인터페이스의 IP를 자동으로 사용한다. DHCP처럼 IP가 바뀔 수 있는 환경에서는 MASQUERADE가 편리하다.

<br>

netfilter를 제어하는 도구가 **iptables**(레거시)와 **nftables**(후속)이다.

```
커널: netfilter (패킷 처리 엔진)
  ↑
도구: iptables / nftables (명령어로 netfilter에 룰 등록)
  ↑
실습: iptables -t nat -A POSTROUTING -o enp0s8 -j MASQUERADE
       └ "nat 테이블에 MASQUERADE 룰을 등록해라"
```

| 항목 | iptables | nftables |
|------|----------|----------|
| 시기 | 2001년~ (레거시) | 2014년~ (후속) |
| 커널 모듈 | x_tables | nf_tables |
| 테이블 | 고정 (filter, nat, mangle, raw) | 자유롭게 생성 |
| 명령어 | `iptables`, `ip6tables`, `ebtables` 따로 | `nft` 하나로 통합 |
| 성능 | 룰이 많으면 순차 탐색 | set/map 등 최적화 가능 |

> Rocky Linux 9+, Ubuntu 22.04+ 등 최근 배포판은 nftables가 기본이고, `iptables` 명령어도 내부적으로 nftables 백엔드를 쓰는 호환 래퍼(`iptables-nft`)인 경우가 많다.

### iptables 테이블 구조

iptables는 4개의 고정 테이블을 가진다. 이 실습에서는 출발지 IP를 변환(MASQUERADE)해야 하므로 **nat 테이블**을 사용한다.

| 테이블 | 용도 | 예시 |
|--------|------|------|
| **filter** | 패킷 허용/차단 (방화벽) | 80번 포트만 허용 |
| **nat** | 주소/포트 변환 | MASQUERADE, DNAT, SNAT |
| **mangle** | 패킷 헤더 수정 | TTL 변경, TOS 마킹 |
| **raw** | conntrack 예외 처리 | 특정 패킷 추적 제외 |

### 실습에서 사용하는 iptables 명령어

| 명령어 | 용도 |
|--------|------|
| `iptables -t nat -S` | nat 테이블의 현재 룰을 명령어 형식으로 출력 (복사/재사용 가능) |
| `iptables -t nat -L -n -v` | nat 테이블의 현재 룰을 표 형식으로 출력 (pkts/bytes 통계 포함) |
| `iptables -t nat -A POSTROUTING -o enp0s8 -j MASQUERADE` | POSTROUTING 체인에 MASQUERADE 룰 추가 |
| `iptables -t nat -D POSTROUTING -o enp0s8 -j MASQUERADE` | POSTROUTING 체인에서 MASQUERADE 룰 삭제 |

`-A`(**A**ppend)는 룰 추가, `-D`(**D**elete)는 룰 삭제다.

### nftables 테이블 구조

nftables는 테이블 이름을 직접 만들며, 체인의 type과 hook으로 용도를 지정한다.

```bash
# 테이블 생성 (이름 자유)
nft add table ip nat
nft add table ip my_firewall

# 체인 생성 (type과 hook으로 용도 지정)
nft add chain ip nat postrouting { type nat hook postrouting priority srcnat \; }

# 룰 추가
nft add rule ip nat postrouting oifname "enp0s8" masquerade
```

## MASQUERADE와 conntrack

### ip_forward와 MASQUERADE의 관계

```
패킷 흐름: node → admin 도착 → 1. ip_forward → 2. MASQUERADE → 인터넷

1. ip_forward = 패킷을 "전달할지 말지" 결정 (관문)
2. MASQUERADE = 전달할 때 "출발지 IP를 바꿀지" 결정 (변환)
```

`ip_forward`와 MASQUERADE가 **둘 다 있어야 NAT Gateway가 완성된다.**

1. `ip_forward`가 꺼져있으면 → 패킷이 1단계에서 버려짐 → MASQUERADE까지 도달 못 함
2. `ip_forward`만 켜고 MASQUERADE가 없으면 → 패킷은 나가지만 응답이 못 돌아옴


### MASQUERADE 동작 원리

MASQUERADE는 나갈 때 출발지 IP를 바꾸고 기록하고, 돌아올 때 기록을 보고 원래 주소로 되돌린다. 이 연결 추적을 커널의 **conntrack**이 담당한다.

<br>

**나갈 때** (node → 인터넷):

| 항목 | 변환 전 | 변환 후 |
|------|---------|---------|
| 출발지 IP | 192.168.10.11 (node) | 10.0.2.15 (admin의 enp0s8) |
| 출발지 Port | 54321 (임의) | 60789 (admin이 새로 할당) |
| 목적지 IP | 8.8.8.8 | 8.8.8.8 (변경 없음) |

admin 커널의 conntrack 테이블에 매핑이 기록된다.

```
{proto=UDP, src=192.168.10.11:54321, dst=8.8.8.8:53}
  → NAT to {src=10.0.2.15:60789, dst=8.8.8.8:53}
```

<br>

**돌아올 때** (인터넷 → node):

1. 응답 패킷이 admin의 enp0s8(`10.0.2.15`)에 도착
2. 커널이 conntrack 테이블 조회: "포트 60789는 아까 `192.168.10.11:54321`에서 온 거"
3. 역변환(reverse NAT) 수행: 목적지 IP `10.0.2.15` → `192.168.10.11`로 복원
4. enp0s9를 통해 node로 전달

<br>

**전체 패킷 흐름**:

```
k8s-node1 → ping 8.8.8.8

1. k8s-node1 (src: 192.168.10.11) → admin enp0s9로 전달
2. admin: "enp0s8로 내보내야지"
   MASQUERADE → src를 192.168.10.11 → 10.0.2.15로 변환
3. 외부 서버 응답 → dst: 10.0.2.15 → admin이 받음
4. admin: conntrack 조회 → dst를 10.0.2.15 → 192.168.10.11로 복원
5. k8s-node1이 응답 수신
```

<br>

# 실습

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | k8s-node | `enp0s8` 내리기 + `enp0s9`에 디폴트 라우트 추가 | 인터넷 차단 + admin 경유 경로 설정 |
| 2 | admin | `iptables MASQUERADE` 설정 | NAT Gateway 활성화 |
| 3 | k8s-node + admin | 통신 확인 (`ping`, `conntrack`) | admin 경유 통신 검증 |
| 4 | admin | `iptables MASQUERADE` 제거 | NAT Gateway 비활성화 |
| 5 | k8s-node | 디폴트 라우트 제거 | 완전한 폐쇄망 복원 |

## 1. [k8s-node] 네트워크 격리 + 디폴트 라우팅

k8s-node의 인터넷 직접 연결(`enp0s8`)을 끊고, 외부 통신 시 admin(`192.168.10.10`)을 게이트웨이로 사용하도록 디폴트 라우트를 추가한다.

> **주의**: `enp0s8`을 내리기 전에 반드시 **enp0s9(Host-Only) 경로(`ssh root@192.168.10.x`)로 접속**해야 한다. `vagrant ssh`로 접속한 상태에서 `enp0s8`을 내리면 현재 SSH 세션이 끊긴다.

### k8s-node2

호스트에서 Host-Only IP로 접속한 뒤 작업을 진행한다.

```bash
# 호스트에서 접속
ssh root@192.168.10.12
# 비밀번호: qwe123
```

```bash
# 현재 라우팅 경로 확인: 8.8.8.8이 enp0s8(NAT)을 통해 직접 나가고 있다
root@week06-week06-k8s-node2:~# ip route get 8.8.8.8
8.8.8.8 via 10.0.2.2 dev enp0s8 src 10.0.2.15 uid 0
    cache

# 인터넷(NAT) 인터페이스 비활성화
root@week06-week06-k8s-node2:~# nmcli connection down enp0s8
Connection 'enp0s8' successfully deactivated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/2)

# 인터넷 차단 확인
root@week06-week06-k8s-node2:~# ping 8.8.8.8
ping: connect: Network is unreachable

root@week06-week06-k8s-node2:~# ip route get 8.8.8.8
RTNETLINK answers: Network is unreachable

# 재부팅 후에도 자동 연결 안 되도록 설정
root@week06-week06-k8s-node2:~# nmcli connection modify enp0s8 connection.autoconnect no
root@week06-week06-k8s-node2:~# cat /etc/NetworkManager/system-connections/enp0s8.nmconnection

# 실행 결과
[connection]
id=enp0s8
uuid=7f94e839-e070-4bfe-9330-07090381d89f
type=ethernet
autoconnect=false
interface-name=enp0s8
...

# enp0s9에 디폴트 라우트 추가: "인터넷 가려면 admin(192.168.10.10)한테 보내라"
# 메트릭 200: 우선순위를 낮게 설정
root@week06-week06-k8s-node2:~# nmcli connection modify enp0s9 +ipv4.routes "0.0.0.0/0 192.168.10.10 200"
root@week06-week06-k8s-node2:~# cat /etc/NetworkManager/system-connections/enp0s9.nmconnection

# 실행 결과 (route1 추가됨)
[ipv4]
address1=192.168.10.12/24
method=manual
never-default=true
route1=0.0.0.0/0,192.168.10.10,200

# 변경된 설정 적용
root@week06-week06-k8s-node2:~# nmcli connection up enp0s9
Connection successfully activated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/7)

# DNS 설정 복구 (enp0s8을 내리면서 resolv.conf가 초기화됨)
root@week06-week06-k8s-node2:~# cat /etc/resolv.conf
# Generated by NetworkManager

root@week06-week06-k8s-node2:~# cat << EOF > /etc/resolv.conf
nameserver 168.126.63.1
nameserver 8.8.8.8
EOF
```

 이 시점에서 `ping 8.8.8.8`을 해도 응답이 오지 않는다. 라우팅 경로는 설정했지만, admin에서 MASQUERADE가 아직 설정되지 않았기 때문이다. Step 2에서 admin을 설정한 뒤에 통신이 가능해진다.

### k8s-node1

동일한 작업을 k8s-node1에서도 진행한다. `ssh root@192.168.10.11`로 접속 후:

```bash
# enp0s8 비활성화
root@week06-week06-k8s-node1:~# nmcli connection down enp0s8
Connection 'enp0s8' successfully deactivated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/6)

# 자동 연결 비활성화 + 디폴트 라우트 추가 + 적용
root@week06-week06-k8s-node1:~# nmcli connection modify enp0s8 connection.autoconnect no
root@week06-week06-k8s-node1:~# nmcli connection modify enp0s9 +ipv4.routes "0.0.0.0/0 192.168.10.10 200"
root@week06-week06-k8s-node1:~# nmcli connection up enp0s9
Connection successfully activated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/8)

# 라우팅 확인
root@week06-week06-k8s-node1:~# ip route
default via 192.168.10.10 dev enp0s9 proto static metric 200
192.168.10.0/24 dev enp0s9 proto kernel scope link src 192.168.10.11 metric 100
```

active connection을 확인하면 enp0s8이 사라진 것을 볼 수 있다.

```bash
root@week06-week06-k8s-node1:~# nmcli connection show --active
NAME    UUID                                  TYPE      DEVICE
enp0s9  66b6560d-3511-49a3-9bec-e9531b7397bb  ethernet  enp0s9
lo      8c2c8970-6550-4551-8086-8eed054e17f0  loopback  lo
```

DNS 설정도 동일하게 복구한다.

```bash
root@week06-week06-k8s-node1:~# cat << EOF > /etc/resolv.conf
nameserver 168.126.63.1
nameserver 8.8.8.8
EOF
```

### Troubleshooting

**vagrant ssh로 접속한 상태에서 enp0s8을 내리면 세션이 멈춘다.**

```bash
vagrant ssh week06-node1
root@week06-week06-k8s-node1:~# nmcli connection down enp0s8
# (응답 없음... 멈춤)
```

`vagrant ssh`는 enp0s8의 NAT 포트포워딩(`60001 → 22`)을 통해 들어온 연결이다. 바로 그 인터페이스를 내리면 **자기가 타고 있는 SSH 연결을 끊어버리는** 셈이다.

**해결**:
- 현재 터미널에서 `~.` (틸드 + 점)을 입력하면 SSH 세션을 강제 종료할 수 있다
- 이후 Host-Only 인터페이스(`ssh root@192.168.10.x`)로 재접속한다

<br>

**enp0s8을 내렸는데 `ip addr show`에서 여전히 UP으로 보인다.**

```bash
root@week06-week06-k8s-node1:~# ip addr show enp0s8
2: enp0s8: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP ...
    link/ether 08:00:27:90:ea:eb brd ff:ff:ff:ff:ff:ff
    altname enx08002790eaeb
```

`state UP`은 **물리 링크 상태**이지 NM connection 상태가 아니다.

| 계층 | 확인 명령 | 의미 |
|------|-----------|------|
| 물리 링크 (L1/L2) | `ip addr show` → `state UP` | 네트워크 카드가 물리적으로 연결되어 있음 |
| NM connection (L3) | `nmcli connection show --active` | IP 주소 할당, 라우팅 등 논리적 네트워크 설정이 활성화됨 |

VirtualBox 가상 NIC가 연결되어 있으니 물리적으로는 여전히 UP이다. 케이블을 뽑은 게 아니라 "IP 설정만 해제"한 것이기 때문이다. IPv4 주소(`inet 10.0.2.15`)가 사라졌다면 connection down은 정상 동작한 것이다. 실제 connection 상태는 `nmcli connection show --active`로 확인해야 한다.

<br>

## 2. [admin] NAT Gateway (MASQUERADE) 설정

admin에서 MASQUERADE를 설정하여 NAT Gateway(공유기) 역할을 하도록 한다. `ip_forward`는 `admin.sh`에서 이미 설정되어 있으므로, MASQUERADE만 추가하면 된다.

`iptables -t nat -A POSTROUTING -o enp0s8 -j MASQUERADE` 명령의 의미:

| 부분 | 의미 |
|------|------|
| `-t nat` | nat 테이블에 규칙 추가 |
| `-A POSTROUTING` | 패킷이 나가기 직전(POSTROUTING 체인)에 적용 |
| `-o enp0s8` | enp0s8(인터넷)으로 나가는 패킷만 |
| `-j MASQUERADE` | 출발지 IP를 admin의 enp0s8 IP(`10.0.2.15`)로 변환 |

```bash
# ip_forward 확인 (admin.sh TASK 5에서 이미 설정됨)
root@admin:~# sysctl net.ipv4.ip_forward
net.ipv4.ip_forward = 1

# MASQUERADE 설정
root@admin:~# iptables -t nat -A POSTROUTING -o enp0s8 -j MASQUERADE

# 설정 확인 (명령어 형식)
root@admin:~# iptables -t nat -S
-P PREROUTING ACCEPT       # -P: 기본 정책(Policy). 매칭되는 룰이 없으면 ACCEPT
-P INPUT ACCEPT
-P OUTPUT ACCEPT
-P POSTROUTING ACCEPT
-A POSTROUTING -o enp0s8 -j MASQUERADE   # -A: 추가한 룰. POSTROUTING 체인에 MASQUERADE 등록됨

# 설정 확인 (표 형식, pkts/bytes로 룰 매칭 여부 확인 가능)
root@admin:~# iptables -t nat -L -n -v

# 실행 결과
Chain POSTROUTING (policy ACCEPT 0 packets, 0 bytes)
 pkts bytes target     prot opt in     out     source               destination
    4   304 MASQUERADE  all  --  *      enp0s8  0.0.0.0/0            0.0.0.0/0
```

## 3. 통신 확인

k8s-node에서 외부 통신이 admin을 경유하는지 확인한다.

```bash
root@week06-week06-k8s-node2:~# ip route get 8.8.8.8
8.8.8.8 via 192.168.10.10 dev enp0s9 src 192.168.10.12 uid 0
    cache
```

enp0s8이 아닌 **enp0s9를 통해 admin(192.168.10.10)을 경유**하는 것을 확인할 수 있다. 비교하면:

```
enp0s8 활성 시:              node2 → enp0s8(10.0.2.2) → 인터넷  (NAT 직접)
enp0s8 down + MASQUERADE 후: node2 → enp0s9(192.168.10.10) → admin → enp0s8 → 인터넷  (admin 경유)
```

admin에서 `conntrack`으로 연결 추적 테이블을 확인하면, MASQUERADE가 실제로 동작하고 있음을 볼 수 있다.

```bash
root@admin:~# conntrack -L

# 실행 결과 (ICMP 부분)
icmp     1 29 src=192.168.10.12 dst=8.8.8.8 type=8 code=0 id=3 src=8.8.8.8 dst=10.0.2.15 type=0 code=0 id=3 ...
```

`src=192.168.10.12`(node2)에서 `dst=8.8.8.8`로 나간 패킷이, 응답에서는 `dst=10.0.2.15`(admin)로 돌아오는 것을 확인할 수 있다. conntrack이 이 매핑을 기록하고 있기 때문에 admin이 응답을 node2로 되돌릴 수 있다.

## 4. [admin] MASQUERADE 제거

admin에서 MASQUERADE 룰을 제거하면, node는 다시 인터넷에 접근할 수 없게 된다.

```bash
# 제거 전 확인
root@admin:~# iptables -t nat -S
-P PREROUTING ACCEPT
-P INPUT ACCEPT
-P OUTPUT ACCEPT
-P POSTROUTING ACCEPT
-A POSTROUTING -o enp0s8 -j MASQUERADE

# MASQUERADE 룰 삭제 (-A 대신 -D 사용)
root@admin:~# iptables -t nat -D POSTROUTING -o enp0s8 -j MASQUERADE

# 제거 후 확인: POSTROUTING 체인에 룰이 없음
root@admin:~# iptables -t nat -S
-P PREROUTING ACCEPT
-P INPUT ACCEPT
-P OUTPUT ACCEPT
-P POSTROUTING ACCEPT
```

node에서 확인하면, 패킷 손실률 100%로 인터넷 통신이 불가능하다.

```bash
root@week06-week06-k8s-node1:~# ping -c 1 8.8.8.8
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.

--- 8.8.8.8 ping statistics ---
1 packets transmitted, 0 received, 100% packet loss, time 0ms
```

MASQUERADE가 제거되어, 패킷은 admin까지 도달하고 외부로 나가지만 출발지 IP가 사설 IP(`192.168.10.x`)인 채로 나가기 때문에 응답이 돌아오지 못한다.

## 5. [k8s-node] 디폴트 라우팅 제거 → 폐쇄망

admin을 통한 외부 경로 자체를 없애서, 내부(`192.168.10.0/24`) 통신만 가능한 완전한 폐쇄망으로 만든다. `+ipv4.routes`가 추가였다면, `-ipv4.routes`가 제거다.

k8s-node1:

```bash
# 디폴트 라우트 제거 (+ 대신 - 사용) + 설정 적용
root@week06-week06-k8s-node1:~# nmcli connection modify enp0s9 -ipv4.routes "0.0.0.0/0 192.168.10.10 200"
root@week06-week06-k8s-node1:~# nmcli connection up enp0s9
Connection successfully activated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/10)

root@week06-week06-k8s-node1:~# ip route
192.168.10.0/24 dev enp0s9 proto kernel scope link src 192.168.10.11 metric 100
```

k8s-node2:

```bash
# 디폴트 라우트 제거 + 설정 적용
root@week06-week06-k8s-node2:~# nmcli connection modify enp0s9 -ipv4.routes "0.0.0.0/0 192.168.10.10 200"
root@week06-week06-k8s-node2:~# nmcli connection up enp0s9
Connection successfully activated (D-Bus active path: /org/freedesktop/NetworkManager/ActiveConnection/7)

root@week06-week06-k8s-node2:~# ip route
192.168.10.0/24 dev enp0s9 proto kernel scope link src 192.168.10.12 metric 100
```

디폴트 라우트가 사라지고, 내부 네트워크(`192.168.10.0/24`)만 남았다. 외부로 나가는 경로 자체가 없으므로 완전한 폐쇄망 상태다.

> 디폴트 라우팅 제거는 Gateway 실습을 모두 마친 후에 진행해야 한다. 라우트가 남아 있으면 admin 경유로 외부 통신이 가능하므로 폐쇄망이 아니다. 이후 본격적인 폐쇄망 서비스(NTP, DNS, 로컬 Repo 등) 실습을 위해 이 상태를 유지한다.

## (도전 과제) nftables로 MASQUERADE 구현

iptables 대신 nftables로 동일한 NAT Gateway를 구현해 본다. Rocky Linux 10에는 nftables가 기본으로 설치되어 있다.

이 도전 과제를 진행하려면, 먼저 Step 5에서 제거한 k8s-node의 디폴트 라우트를 다시 추가해야 한다.

### iptables와 nftables 동시 사용 시 주의 사항

iptables와 nftables는 모두 커널의 **netfilter hook**에 체인을 등록한다. 같은 hook 지점(예: `POSTROUTING`)에 양쪽 체인이 걸려 있으면, priority(우선순위 숫자)에 따라 **순서대로 모두 실행**된다.

```
패킷 → netfilter POSTROUTING hook
         ├─ nftables 체인 (priority 100)  ← 먼저 실행
         └─ iptables 체인 (priority 100)  ← 그 다음 실행
         (같은 priority면 등록 순서에 따름)
```

따라서 둘을 동시에 사용하면 의도하지 않은 동작이 발생할 수 있다.

| 상황 | 결과 |
|------|------|
| iptables ACCEPT + nftables DROP | **DROP** (하나라도 DROP하면 차단) |
| iptables MASQUERADE + nftables MASQUERADE | 이중 NAT 가능성 (예측 불가) |
| iptables 룰 없음 + nftables MASQUERADE | 정상 동작 |

따라서 실무에서는 iptables와 nftables 중 하나만 사용하는 것이 좋다. 같은 hook 지점에 체인이 여러 개 있어도 동작 자체는 하지만, 의도하지 않은 중복 룰이 생기기 쉽다. iptables를 쓸 거면 nftables 룰을 비우고, nftables를 쓸 거면 iptables 룰을 비워야 한다.

### iptables 룰 제거

nftables로 전환하기 전에, 기본 실습에서 적용한 iptables MASQUERADE 룰을 **반드시 먼저 제거**한다.

```bash
# iptables NAT 룰 제거
root@admin:~# iptables -t nat -F POSTROUTING

# 제거 확인
root@admin:~# iptables -t nat -S
-P PREROUTING ACCEPT
-P INPUT ACCEPT
-P OUTPUT ACCEPT
-P POSTROUTING ACCEPT
```

`POSTROUTING` 체인에 룰이 없는 상태(`-P POSTROUTING ACCEPT`만 남아 있는 상태)가 되면 정상이다.

### nftables MASQUERADE 설정

admin에서 nftables를 설정한다.

```bash
# 테이블 생성
root@admin:~# nft add table ip nat

# POSTROUTING 체인 생성
root@admin:~# nft add chain ip nat postrouting { type nat hook postrouting priority srcnat \; }

# MASQUERADE 룰 추가
root@admin:~# nft add rule ip nat postrouting oifname "enp0s8" masquerade

# 확인
root@admin:~# nft list ruleset
table ip nat {
	chain POSTROUTING {
		type nat hook postrouting priority srcnat; policy accept;
	}

	chain postrouting {
		type nat hook postrouting priority srcnat; policy accept;
		oifname "enp0s8" masquerade
	}
}
```

출력을 보면 체인이 두 개다. 이름이 비슷하지만 출처가 다르다.

| 체인 | 출처 | 룰 |
|------|------|------|
| `POSTROUTING` (대문자) | iptables 호환 레이어가 자동 생성 | 없음 (비어 있음) |
| `postrouting` (소문자) | `nft add chain`으로 직접 생성 | `masquerade` |

동작에 문제는 없지만, 깔끔하게 정리하려면 빈 체인을 삭제한다.

```bash
root@admin:~# nft delete chain ip nat POSTROUTING
root@admin:~# nft list ruleset
table ip nat {
	chain postrouting {
		type nat hook postrouting priority srcnat; policy accept;
		oifname "enp0s8" masquerade
	}
}
```

이 상태에서 `iptables -t nat -S`를 실행하면 다음과 같은 경고가 나온다.

```bash
root@admin:~# iptables -t nat -S
# Table `nat' contains incompatible base-chains, use 'nft' tool to list them.
-P PREROUTING ACCEPT
-P INPUT ACCEPT
-P OUTPUT ACCEPT
-P POSTROUTING ACCEPT
```

`incompatible base-chains` 경고는 iptables가 nftables 방식으로 만든 체인을 읽을 수 없다는 의미다. nftables가 정상 동작하고 있음을 오히려 확인해 주는 것이니 무시해도 된다.

### 통신 확인

node에서 확인하면, nftables로도 동일하게 NAT Gateway가 동작하는 것을 볼 수 있다.

```bash
root@week06-week06-k8s-node1:~# ping -c 1 8.8.8.8
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=254 time=34.0 ms

--- 8.8.8.8 ping statistics ---
1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 33.966/33.966/33.966/0.000 ms

root@week06-week06-k8s-node1:~# ip route get 8.8.8.8
8.8.8.8 via 192.168.10.10 dev enp0s9 src 192.168.10.11 uid 0
    cache
```

<br>

# 정리

이번 글에서는 admin을 NAT Gateway로 구성하여 폐쇄망 환경을 시뮬레이션했다.

| 순서 | 위치 | 설정 | 목적 |
|------|------|------|------|
| 1 | admin | `net.ipv4.ip_forward = 1` | admin이 패킷을 중계(포워딩)하도록 허용 |
| 2 | k8s-node | `+ipv4.routes "0.0.0.0/0 192.168.10.10 200"` | "인터넷 가려면 admin한테 보내라" |
| 3 | admin | `iptables -t nat -A POSTROUTING -o enp0s8 -j MASQUERADE` | 출발지 IP를 admin 것으로 변환 |

- 1이 없으면 → admin이 node에서 온 패킷을 버림 (중계 거부)
- 2가 없으면 → node가 8.8.8.8으로 보낼 경로 자체를 모름
- 3이 없으면 → 패킷은 나가지만, 응답이 사설 IP로 돌아와야 하는데 외부 라우터가 그 사설 IP를 모르므로 응답이 못 돌아옴

`admin.sh`에서 1은 이미 설정되어 있으므로, 실습에서는 2(node에서)와 3(admin에서)만 직접 구성하면 된다. Gateway 실습을 마친 후 디폴트 라우팅을 제거하면, k8s-node는 admin과의 내부 통신만 가능한 완전한 폐쇄망 상태가 된다.

<br>

# 참고 자료

- [iptables Tutorial](https://www.frozentux.net/iptables-tutorial/iptables-tutorial.html)
- [nftables Wiki](https://wiki.nftables.org/)
- [Linux IP Forwarding - Kernel Documentation](https://www.kernel.org/doc/Documentation/networking/ip-sysctl.txt)

<br>
