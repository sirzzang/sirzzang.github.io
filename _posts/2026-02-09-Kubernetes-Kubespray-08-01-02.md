---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8.1.2. NTP / DNS"
excerpt: "폐쇄망 환경에서 노드 간 시간 동기화를 위한 NTP 서버와, 내부 도메인 이름 해석을 위한 DNS 서버를 구축한다."
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
  - NTP
  - chrony
  - DNS
  - BIND
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 폐쇄망 환경에서 **NTP 서버**(chrony)와 **DNS 서버**(BIND)를 구축한다.

- **NTP Server**: admin에서 외부 NTP 서버와 동기화하고, 내부망 노드들에 시간을 제공
- **NTP Client**: k8s-node가 admin을 NTP 서버로 사용하도록 설정
- **DNS Server**: admin에서 BIND를 설치하고, 내부망 노드들의 도메인 질의를 처리
- **DNS Client**: k8s-node가 admin을 DNS 서버로 사용하도록 설정

| 구성요소 | 서버 (admin) | 클라이언트 (k8s-node) |
|----------|-------------|----------------------|
| NTP | chrony 서버 설정 (`allow`, `local stratum`) | `server 192.168.10.10 iburst` |
| DNS | BIND 설치 + `named.conf` 설정 | `resolv.conf`에 admin IP 지정 |

<br>

# 왜 NTP / DNS가 필요한가

## NTP (Network Time Protocol)

노드 간 시간이 맞지 않으면 다양한 문제가 발생한다.

| 문제 | 설명 |
|------|------|
| 인증서 검증 실패 | TLS 인증서의 유효 기간을 시간 기준으로 판단 |
| etcd 합의 장애 | etcd는 리더 선출 시 타임스탬프 기반 판단을 사용 |
| 로그 분석 불가 | 노드마다 시간이 다르면 로그 순서를 파악할 수 없음 |

온라인 환경에서는 `time.google.com`, `pool.ntp.org` 같은 공인 NTP 서버를 사용하면 된다. 폐쇄망에서는 이 서버들에 접근할 수 없으므로, **admin이 외부 NTP 서버와 동기화한 뒤, 내부망 노드들에 시간을 제공**하는 구조가 필요하다.

```
[온라인]  pool.ntp.org → admin (chrony 서버)
[내부망]  admin → k8s-node1, k8s-node2 (chrony 클라이언트)
```

## DNS (Domain Name System)

내부 서비스(Registry, Repo 등)에 도메인으로 접근하려면 내부 DNS 서버가 필요하다. 폐쇄망에서는 공인 DNS(`8.8.8.8` 등)를 사용할 수 없다.

| 문제 | 설명 |
|------|------|
| 도메인 접근 불가 | 내부 Registry, Repo 등에 도메인으로 접근할 수 없음 |
| 호스트명 해석 불가 | 노드 간 호스트명 기반 통신 불가 |
| 외부 도메인 해석 불가 | admin 경유 인터넷 접근 시에도 도메인 해석이 안 됨 |

admin에 DNS 서버를 구축하고, **내부망 질의는 직접 처리하고 외부 도메인은 상위 DNS(forwarder)에 전달**하는 구조로 만든다.

```
[k8s-node] → admin (BIND DNS 서버) → 내부 도메인: 직접 응답
                                    → 외부 도메인: forwarder(168.126.63.1, 8.8.8.8)에 전달
```

<br>

# 배경지식

## chrony

chrony는 NTP 프로토콜의 구현체로, Rocky Linux 10에 기본 설치되어 있다. `chronyd` 데몬이 시간 동기화를 수행하고, `chronyc` 명령어로 상태를 확인한다.

### chrony.conf 주요 설정

| 설정 | 의미 |
|------|------|
| `server` / `pool` | 시간을 받아올 NTP 서버 지정. `pool`은 여러 서버를 묶은 그룹 |
| `iburst` | 서비스 시작 직후 4~8개의 패킷을 짧은 간격으로 보내 빠르게 초기 동기화 |
| `allow` | 이 서버에 접속해 시간 동기화를 허용할 네트워크 대역 |
| `local stratum N` | 외부 연결이 끊겨도 로컬 시계를 기준으로 stratum N으로 시간 제공 |
| `driftfile` | 내부 시계의 시간 편차를 기록. 네트워크 끊겨도 이 기록으로 오차 보정 |
| `makestep 1.0 3` | 시간 차이가 1초 이상일 경우, 초기 3번의 업데이트 내에서 즉시 시간 맞춤 |
| `rtcsync` | 시스템 시계의 동기화 결과를 하드웨어 시계(RTC)에 주기적으로 복사 |

### chronyc 주요 명령어

| 명령어 | 용도 |
|--------|------|
| `chronyc sources -v` | 어떤 NTP 서버와 동기화 중인지, 현재 기준 서버(`*`) 확인 |
| `chronyc clients` | 이 NTP 서버를 사용하는 클라이언트 목록 확인 |
| `timedatectl status` | 시스템 시간, NTP 동기화 상태 확인 |

`chronyc sources`의 출력에서 `*`는 현재 기준 서버, `+`는 대안 서버, `-`는 사용하지 않는 서버를 의미한다.

## BIND

BIND(Berkeley Internet Name Domain)는 가장 널리 사용되는 DNS 서버 구현체다. Rocky Linux에서는 `bind` 패키지로 설치하며, `named` 데몬이 DNS 서비스를 제공한다.

### named.conf 주요 설정

| 설정 | 의미 |
|------|------|
| `listen-on port 53 { any; }` | 모든 인터페이스에서 DNS 요청 수신 |
| `allow-query` | DNS 쿼리를 허용할 네트워크 범위 |
| `allow-recursion` | 재귀 쿼리를 허용할 네트워크 범위 |
| `forwarders` | 이 서버가 답을 모를 때 질의를 전달할 상위 DNS 서버 |
| `recursion yes` | 재귀 쿼리 활성화 (클라이언트 대신 상위 서버에 질의) |

**재귀 쿼리(recursion)**란, 클라이언트가 "google.com의 IP는?"이라고 물으면 DNS 서버가 직접 루트 서버부터 타고 내려가 답을 찾아주는 것이다. `forwarders`가 설정되어 있으면 먼저 forwarder에 물어보고, 없으면 직접 탐색한다.

### DNS 클라이언트 설정 포인트

k8s-node에서 DNS 서버를 admin으로 변경하려면, `/etc/resolv.conf`에 admin IP를 지정해야 한다. 그런데 NetworkManager가 기본적으로 `resolv.conf`를 자동 관리하기 때문에, 수동으로 수정해도 NM이 덮어쓸 수 있다. 이를 방지하기 위해 NM의 DNS 관리를 꺼야 한다.

```ini
# /etc/NetworkManager/conf.d/99-dns-none.conf
[main]
dns=none
```

이 설정으로 NetworkManager가 `resolv.conf`를 건드리지 않게 한 뒤, 직접 `resolv.conf`를 설정한다.

<br>

# NTP 실습

## [admin] NTP 서버 설정

admin에서 chrony를 NTP 서버로 설정한다. 외부 한국 공용 NTP 서버에서 시간을 받아오고, 내부망(`192.168.10.0/24`)에 시간을 제공한다.

핵심 설정 3가지:

| 설정 | 역할 |
|------|------|
| `server pool.ntp.org iburst` | 외부 NTP 서버에서 시간을 받아옴 |
| `allow 192.168.10.0/24` | 내부망 노드의 시간 동기화 요청을 허용 |
| `local stratum 10` | 외부 연결이 끊겨도 로컬 시계 기반으로 시간 제공 (폐쇄망 대비) |

```shell
# 현재 chrony 상태 확인
root@admin:~# systemctl status chronyd.service --no-pager

# 실행 결과
● chronyd.service - NTP client/server
     Loaded: loaded (/usr/lib/systemd/system/chronyd.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-02-08 16:33:24 KST; 2h 43min ago
...

# 주석 제외한 현재 설정 확인
root@admin:~# grep "^[^#]" /etc/chrony.conf
pool 2.rocky.pool.ntp.org iburst
sourcedir /run/chrony-dhcp
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
ntsdumpdir /var/lib/chrony
logdir /var/log/chrony

# 현재 동기화 중인 NTP 서버 확인 (^*가 기준 서버)
root@admin:~# chronyc sources -v

# 실행 결과
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^* 211.108.117.211               2   8   377   176   -396us[ -454us] +/- 3122us
^- ec2-3-39-176-65.ap-north>     2   9   377   432   +246us[ +157us] +/- 7170us
^- mail.innotab.com              3   9   377   306  -5692us[-5766us] +/-   27ms
^- mail.zeroweb.kr               3   9   377   304  +1583us[+1509us] +/-   48ms
```

기본 설정에서는 `2.rocky.pool.ntp.org`와 동기화하고 있고, 내부망 클라이언트에 시간을 제공하는 설정(`allow`)은 없다. 설정을 변경한다.

```shell
# 설정 백업 후 변경
root@admin:~# cp /etc/chrony.conf /etc/chrony.bak
root@admin:~# cat << EOF > /etc/chrony.conf
# 외부 한국 공용 NTP 서버 설정
server pool.ntp.org iburst
server kr.pool.ntp.org iburst

# 내부망(192.168.10.0/24)에서 이 서버에 접속하여 시간 동기화 허용
allow 192.168.10.0/24

# 외부망이 끊겼을 때도 로컬 시계를 기준으로 내부망에 시간 제공
local stratum 10

# 로그
logdir /var/log/chrony
EOF

# 서비스 재시작
root@admin:~# systemctl restart chronyd.service

# 상태 확인
root@admin:~# timedatectl status

# 실행 결과
               Local time: Sun 2026-02-08 19:18:08 KST
           Universal time: Sun 2026-02-08 10:18:08 UTC
                 RTC time: Sun 2026-02-08 12:33:16
                Time zone: Asia/Seoul (KST, +0900)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no

# 동기화 서버 확인
root@admin:~# chronyc sources -v

# 실행 결과
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^- 121.174.142.82                3   6    17     7   +139us[ +139us] +/-   53ms
^* 121.134.215.104               2   6    17     7    +18us[+4953ns] +/- 2793us
```

`kr.pool.ntp.org`의 서버들과 동기화가 정상 동작하고 있다. `System clock synchronized: yes`와 `NTP service: active`로 시간 동기화가 활성 상태임을 확인할 수 있다.

## [k8s-node] NTP 클라이언트 설정

k8s-node에서 chrony 클라이언트 설정을 변경하여, admin(`192.168.10.10`)을 NTP 서버로 사용하도록 한다.

### k8s-node1

```shell
# 변경 전: 외부 NTP 서버와 직접 동기화
root@week06-week06-k8s-node1:~# chronyc sources -v
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^- ipv4.ntp3.rbauman.com         2   6   377    24   -553us[ -553us] +/-   22ms
^- 121.134.215.104               2   6   177    24   +623us[ +623us] +/- 3241us
^- 193.123.243.2                 3   8     3   148   -334us[ -334us] +/- 3563us
^* 211.108.117.211               2   8     3   154   -270us[ -330us] +/- 5861us

# chrony 설정 변경: admin을 NTP 서버로 지정
root@week06-week06-k8s-node1:~# cp /etc/chrony.conf /etc/chrony.bak
root@week06-week06-k8s-node1:~# cat << EOF > /etc/chrony.conf
server 192.168.10.10 iburst
logdir /var/log/chrony
EOF

root@week06-week06-k8s-node1:~# systemctl restart chronyd.service

# 변경 후: admin과 동기화 확인
root@week06-week06-k8s-node1:~# chronyc sources -v
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^* admin                         3   6    17     5  +7456ns[  +57us] +/- 2964us
```

`^* admin`으로 표시되어, admin을 기준 서버로 시간 동기화가 정상 동작하고 있다.

### k8s-node2

동일하게 설정한다.

```shell
# admin을 NTP 서버로 설정 + 서비스 재시작
root@week06-week06-k8s-node2:~# cp /etc/chrony.conf /etc/chrony.bak
root@week06-week06-k8s-node2:~# cat << EOF > /etc/chrony.conf
server 192.168.10.10 iburst
logdir /var/log/chrony
EOF

root@week06-week06-k8s-node2:~# systemctl restart chronyd.service
root@week06-week06-k8s-node2:~# chronyc sources -v

# 실행 결과
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^* admin                         3   6    17     5    -16us[  -80us] +/- 4274us
```

## [admin] 클라이언트 확인

admin에서 `chronyc clients`로 이 NTP 서버를 사용하는 클라이언트를 확인한다.

```shell
root@admin:~# chronyc clients

# 실행 결과
Hostname                      NTP   Drop Int IntL Last     Cmd   Drop Int  Last
===============================================================================
week06-k8s-node1                6      0   5   -    18       0      0   -     -
week06-k8s-node2                5      0   4   -     6       0      0   -     -
```

k8s-node1과 k8s-node2가 NTP 클라이언트로 등록되어 있다. `NTP` 컬럼은 해당 클라이언트에서 받은 NTP 요청 수를 나타낸다.

<br>

# DNS 실습

## [admin] DNS 서버(BIND) 설정

admin에서 BIND를 설치하고 DNS 서버를 구성한다. 내부망(`192.168.10.0/24`)의 DNS 질의를 처리하고, 외부 도메인은 forwarder(`168.126.63.1`, `8.8.8.8`)에 전달한다.

핵심 설정 3가지:

| 설정 | 역할 |
|------|------|
| `allow-query { 127.0.0.1; 192.168.10.0/24; }` | 로컬과 내부망에서만 DNS 질의 허용 |
| `allow-recursion { 127.0.0.1; 192.168.10.0/24; }` | 재귀 쿼리도 내부망에만 허용 |
| `forwarders { 168.126.63.1; 8.8.8.8; }` | 외부 도메인은 KT DNS, Google DNS에 전달 |

```shell
# BIND 설치
root@admin:~# dnf install -y bind bind-utils

# 실행 결과
...
Installed:
  bind-32:9.18.33-10.el10_1.2.aarch64
  bind-dnssec-utils-32:9.18.33-10.el10_1.2.aarch64
  openssl-fips-provider-1:3.5.1-7.el10_1.aarch64
Complete!

# named.conf 설정 백업 후 변경
root@admin:~# cp /etc/named.conf /etc/named.bak
root@admin:~# cat <<EOF > /etc/named.conf
options {
        listen-on port 53 { any; };              # 모든 인터페이스에서 DNS 요청 수신
        listen-on-v6 port 53 { ::1; };
        directory       "/var/named";
        dump-file       "/var/named/data/cache_dump.db";
        statistics-file "/var/named/data/named_stats.txt";
        memstatistics-file "/var/named/data/named_mem_stats.txt";
        secroots-file   "/var/named/data/named.secroots";
        recursing-file  "/var/named/data/named.recursing";
        allow-query     { 127.0.0.1; 192.168.10.0/24; };    # 내부망에서만 질의 허용
        allow-recursion { 127.0.0.1; 192.168.10.0/24; };    # 내부망에서만 재귀 질의 허용

        forwarders {                             # 외부 도메인 질의 전달 대상
                168.126.63.1;
                8.8.8.8;
        };

        recursion yes;                           # 재귀 쿼리 활성화

        dnssec-validation yes;

        managed-keys-directory "/var/named/dynamic";
        geoip-directory "/usr/share/GeoIP";

        pid-file "/run/named/named.pid";
        session-keyfile "/run/named/session.key";

        include "/etc/crypto-policies/back-ends/bind.config";
};

logging {
        channel default_debug {
                file "data/named.run";
                severity dynamic;
        };
};

zone "." IN {
        type hint;
        file "named.ca";
};

include "/etc/named.rfc1912.zones";
include "/etc/named.root.key";
EOF

# 문법 검증 (출력 없으면 정상)
root@admin:~# named-checkconf /etc/named.conf

# 서비스 활성화 및 시작
root@admin:~# systemctl enable --now named
Created symlink '/etc/systemd/system/multi-user.target.wants/named.service' → '/usr/lib/systemd/system/named.service'.

# admin 자체 DNS 설정 (자기 자신을 DNS 서버로 사용) + 동작 확인
root@admin:~# echo "nameserver 192.168.10.10" > /etc/resolv.conf

root@admin:~# dig +short google.com @192.168.10.10
172.217.209.113
172.217.209.139
172.217.209.138
172.217.209.102
172.217.209.100
172.217.209.101

root@admin:~# dig +short google.com
172.217.209.102
172.217.209.100
172.217.209.138
172.217.209.139
172.217.209.113
172.217.209.101
```

DNS 서버가 정상 동작하고 있다. `@192.168.10.10`으로 직접 질의하든, `resolv.conf`를 통해 질의하든 모두 응답이 온다.

## [k8s-node] DNS 클라이언트 설정

k8s-node에서 admin(`192.168.10.10`)을 DNS 서버로 사용하도록 설정한다. NetworkManager가 `resolv.conf`를 자동 관리하므로, 먼저 NM의 DNS 관리를 비활성화해야 한다.

> `99-dns-none.conf`로 NM의 DNS 관리를 끄지 않으면, `nmcli connection up` 등의 이벤트에서 `resolv.conf`가 NM에 의해 덮어쓰여져 admin DNS 설정이 사라진다.

### k8s-node1

```shell
# NetworkManager에서 DNS 관리 끄기
root@week06-week06-k8s-node1:~# cat << EOF > /etc/NetworkManager/conf.d/99-dns-none.conf
[main]
dns=none
EOF

root@week06-week06-k8s-node1:~# systemctl restart NetworkManager

# DNS 서버를 admin으로 설정 + 동작 확인
root@week06-week06-k8s-node1:~# echo "nameserver 192.168.10.10" > /etc/resolv.conf

root@week06-week06-k8s-node1:~# dig +short google.com @192.168.10.10
172.217.211.139
172.217.211.138
172.217.211.102
172.217.211.113
172.217.211.100
172.217.211.101

root@week06-week06-k8s-node1:~# dig +short google.com
172.217.211.113
172.217.211.138
172.217.211.102
172.217.211.101
172.217.211.139
172.217.211.100
```

node1은 `enp0s8`이 내려가 있어 인터넷에 직접 접근할 수 없지만, admin에 DNS 질의를 하고 admin이 forwarder를 통해 외부 도메인을 해석해주기 때문에 도메인 질의가 가능하다.

### k8s-node2

동일하게 설정한다.

```shell
# NetworkManager DNS 관리 끄기 + admin DNS 설정
root@week06-week06-k8s-node2:~# cat << EOF > /etc/NetworkManager/conf.d/99-dns-none.conf
[main]
dns=none
EOF

root@week06-week06-k8s-node2:~# systemctl restart NetworkManager
root@week06-week06-k8s-node2:~# echo "nameserver 192.168.10.10" > /etc/resolv.conf

root@week06-week06-k8s-node2:~# dig +short google.com @192.168.10.10
172.217.211.138
172.217.211.102
172.217.211.100
172.217.211.113
172.217.211.101
172.217.211.139

root@week06-week06-k8s-node2:~# dig +short google.com
172.217.211.101
172.217.211.138
172.217.211.113
172.217.211.100
172.217.211.102
172.217.211.139
```

<br>

# 정리

이번 글에서는 폐쇄망 기반 인프라의 핵심 구성요소인 NTP 서버와 DNS 서버를 구축했다.

| 구성요소 | 서버 (admin) | 클라이언트 (k8s-node) | 확인 방법 |
|----------|-------------|----------------------|-----------|
| NTP | chrony: 외부 NTP → 내부 제공 | `server 192.168.10.10` | `chronyc sources -v` (`^* admin`) |
| DNS | BIND: 내부 질의 처리 + 외부 전달 | `resolv.conf` → admin IP | `dig +short google.com` |

현재까지의 폐쇄망 인프라 구성 상태:

| 구성요소 | 상태 |
|----------|------|
| Network Gateway | 완료 ([8.1.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})) |
| NTP Server / Client | 완료 (본 글) |
| DNS Server / Client | 완료 (본 글) |
| Local Package Repository | 미구성 |
| Private Container Registry | 미구성 |

<br>

# 참고 자료

- [이전 글: 8.1.1 Network Gateway]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})
- [chrony Documentation](https://chrony-project.org/documentation.html)
- [BIND 9 Administrator Reference Manual](https://bind9.readthedocs.io/)
- [NTP Pool Project](https://www.pool.ntp.org/)

<br>
