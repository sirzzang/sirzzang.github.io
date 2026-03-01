---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.2. 환경 확인 및 사전 설정"
excerpt: "kubeadm 클러스터 구성을 위해 실습 환경을 확인하고, 시간 동기화·SELinux·Swap·커널 모듈 등 사전 설정을 수행해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **kubeadm 클러스터 구성을 위한 환경 확인 및 사전 설정**이다.

- **기본 정보 확인**: CPU, 메모리, 디스크, 네트워크, cgroup 버전 확인
- **사전 설정**: 시간 동기화, SELinux, 방화벽, Swap, 커널 모듈/파라미터, hosts 설정

모든 설정은 **컨트롤 플레인과 워커 노드 모두에 적용**한다.

<br>

# 실습 환경

## 주요 버전 정보

| 항목 | 버전 | 비고 |
| --- | --- | --- |
| Rocky Linux | 10.0-1.6 | RHEL 10 기반 |
| containerd | v2.1.5 | CRI Version(v1), k8s 1.32~1.35 지원 |
| runc | v1.3.3 | containerd와 함께 설치됨 |
| kubelet | v1.32.11 | kubeadm과 동일 버전 |
| kubeadm | v1.32.11 | |
| kubectl | v1.32.11 | |

<br>

## 노드 구성

| 호스트명 | IP | 역할 |
| --- | --- | --- |
| k8s-ctr | 192.168.10.100 | Control Plane |
| k8s-w1 | 192.168.10.101 | Worker Node |
| k8s-w2 | 192.168.10.102 | Worker Node |

- [Vagrantfile](https://github.com/gasida/vagrant-lab/blob/main/k8s-kubeadm/Vagrantfile)

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %})에서 `kubeadm init`의 동작 원리와 14개 단계를 살펴보았다. 이번 글부터는 실제로 kubeadm을 사용하여 클러스터를 구성한다. 설치 목표 클러스터 버전은 1.32다.

kubeadm을 사용하기 전에 먼저 몇 가지 사전 설정이 필요하다. Kubernetes [공식 문서](https://v1-32.docs.kubernetes.io/ko/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)에서 안내하는 요구사항을 충족해야 한다. 이 글에서 다루는 모든 설정은 **컨트롤 플레인 노드와 워커 노드 모두**에 적용해야 한다. 실습에서는 k8s-ctr, k8s-w1, k8s-w2 세 노드에 동일하게 진행한다.

<br>

# 기본 정보 확인

`vagrant ssh k8s-ctr` 명령으로 노드에 접속한 후, 기본 정보를 확인한다. Kubernetes 클러스터 구축 전에 시스템 요구사항을 충족하는지 확인하는 것이 중요하다.

## User 정보

현재 사용자가 root가 아님을 확인한다. kubeadm 설치 및 클러스터 초기화는 root 권한이 필요하므로, 이후 `sudo su -`로 전환해야 한다.

```bash
whoami      # vagrant
id          # uid=1000(vagrant) gid=1000(vagrant) groups=1000(vagrant)
pwd         # /home/vagrant
```

<br>

## CPU 및 아키텍처

kubeadm은 **최소 2 CPU**를 요구한다. 또한 아키텍처를 확인하여 컨테이너 이미지 선택 시 호환성을 고려해야 한다.

```bash
lscpu
# Architecture:             aarch64
#   CPU op-mode(s):         64-bit
#   Byte Order:             Little Endian
# CPU(s):                   4
#   On-line CPU(s) list:    0-3
# Vendor ID:                Apple
#   Model name:             -
#     Thread(s) per core:   1
#     Core(s) per cluster:  4
```

현재 4 CPU이므로 요구사항을 충족한다. 아키텍처는 `aarch64`(Apple Silicon ARM64)이므로 arm64 호환 이미지를 사용해야 한다.


## 메모리

kubeadm은 **최소 2GB RAM**을 요구한다. 컨트롤 플레인은 etcd, API Server 등 여러 컴포넌트가 실행되므로 메모리 여유가 있는 것이 좋다.

```bash
free -h
#                total        used        free      shared  buff/cache   available
# Mem:           2.8Gi       xxx         xxx        xxx         xxx         xxx
```

현재 약 2.8GB이므로 요구사항을 충족한다.


## 디스크

컨테이너 이미지, 로그, etcd 데이터 등을 저장할 충분한 디스크 공간이 필요하다.

```bash
lsblk
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
# sda      8:0    0   64G  0 disk 
# ├─sda1   8:1    0  600M  0 part /boot/efi
# ├─sda2   8:2    0  3.8G  0 part [SWAP]
# └─sda3   8:3    0 59.6G  0 part /

df -hT
# Filesystem     Type      Size  Used Avail Use% Mounted on
# /dev/sda3      xfs        60G  2.5G   58G   5% /
# /dev/sda1      vfat      599M   13M  587M   3% /boot/efi
```

현재 루트 파티션(`/`)에 **58GB 가용 공간**이 있어 충분하다. `sda2`에 `[SWAP]`이 보이므로 **스왑은 아직 켜져 있는 상태**이며, 이후 [Swap 비활성화](#swap-비활성화)에서 비활성화한다.

> `/boot/efi` 파티션은 EFI 부팅을 위한 것으로, Vagrant VM이 UEFI 부팅을 사용함을 알 수 있다.


## 네트워크

Kubernetes 노드 간 통신에 사용할 네트워크 인터페이스와 IP 주소를 파악한다. Vagrant 환경에서는 보통 여러 네트워크 인터페이스가 있으므로 클러스터 통신에 사용할 인터페이스를 정확히 식별해야 한다. 
> VirtualBox의 NAT/Host-Only 어댑터 구조에 대해서는 [VirtualBox + Vagrant 네트워크 어댑터 이해하기]({% post_url 2026-02-09-Dev-VirtualBox-Network %})를 참고하자.

```bash
ip -br -c -4 addr
# lo               UNKNOWN        127.0.0.1/8 
# enp0s8           UP             10.0.2.15/24 
# enp0s9           UP             192.168.10.100/24 

ip -c route
# default via 10.0.2.2 dev enp0s8 proto dhcp src 10.0.2.15 metric 100 
# default via 192.168.10.1 dev enp0s9 proto static metric 101 
# 10.0.2.0/24 dev enp0s8 proto kernel scope link src 10.0.2.15 metric 100 
# 192.168.10.0/24 dev enp0s9 proto kernel scope link src 192.168.10.100 metric 101 
```

| 인터페이스 | IP | 용도 |
| --- | --- | --- |
| `enp0s8` | 10.0.2.15/24 | NAT 네트워크 (외부 인터넷 접근용) |
| `enp0s9` | 192.168.10.100/24 | Host-only 네트워크 (**클러스터 통신용**) |

라우팅 테이블에서 metric 값이 낮은 `enp0s8`이 기본 경로이지만, 클러스터 통신은 `enp0s9`를 사용한다. `kubeadm init` 시 `--apiserver-advertise-address`에 **192.168.10.100**을 지정하여 클러스터 내부 통신에 사용한다.

<br>

## 호스트 정보 및 커널

OS와 커널 버전이 Kubernetes/kubeadm과 호환되는지 확인한다. 또한 hostname이 클러스터에서 노드를 식별하는 이름이 된다.

```bash
hostnamectl
#  Static hostname: k8s-ctr
#        Icon name: computer
#       Machine ID: b31bad896d6f42cbae09a700647ef3ec
#          Boot ID: 8c04598dc69d422fadd25891687fa257
# Operating System: Rocky Linux 10.0 (Red Quartz)      
#      CPE OS Name: cpe:/o:rocky:rocky:10::baseos
#   OS Support End: Thu 2035-05-31
#           Kernel: Linux 6.12.0-55.39.1.el10_0.aarch64
#     Architecture: arm64

uname -r               # 6.12.0-55.39.1.el10_0.aarch64
rpm -aq | grep release # rocky-release-10.0-1.6.el10.noarch
```

| 항목 | 값 | 의미 |
| --- | --- | --- |
| Hostname | k8s-ctr | 클러스터에서 이 노드를 식별하는 이름 |
| OS | Rocky Linux 10.0 | RHEL 계열, dnf 패키지 관리자 사용 |
| Kernel | 6.12.0 | 최신 LTS 커널, cgroup v2 기본 지원 |
| Architecture | arm64 | Apple Silicon (M1/M2/M3) |

OS 지원 종료일은 2035년 5월 31일까지이므로 장기 운영에 적합하다. 커널 6.12는 cgroup v2, eBPF 등 최신 기능을 지원하여 Kubernetes 운영에 유리하다.

## cgroup 버전 확인

Kubernetes는 컨테이너의 리소스(CPU, 메모리 등)를 제한하기 위해 Linux 커널의 **cgroup(Control Groups)** 기능을 사용한다. cgroup에는 v1과 v2가 있으며, Kubernetes 1.25부터 **cgroup v2가 권장**된다.

### 파일시스템 타입 확인

`stat -fc %T` 명령어로 `/sys/fs/cgroup` 디렉토리의 파일시스템 타입을 확인한다. `-f`는 파일시스템 정보를, `%T`는 타입만 출력한다.

```bash
stat -fc %T /sys/fs/cgroup   # cgroup2fs (v1이면 tmpfs)
```

`cgroup2fs`가 출력되면 cgroup v2를 사용 중이다. cgroup v1이면 `tmpfs`가 출력된다.


### 마운트 정보 확인

`findmnt`와 `mount` 명령어로 cgroup이 어떻게 마운트되어 있는지 확인한다.

```bash
findmnt | grep cgroup
# │ ├─/sys/fs/cgroup    cgroup2    cgroup2    rw,nosuid,nodev,noexec,relatime,seclabel,nsdelegate,memory_recursiveprot

mount | grep cgroup
# cgroup2 on /sys/fs/cgroup type cgroup2 (rw,nosuid,nodev,noexec,relatime,seclabel,nsdelegate,memory_recursiveprot)
```

| 옵션 | 의미 |
| --- | --- |
| `nsdelegate` | 네임스페이스 위임 활성화 (컨테이너가 자체 cgroup 관리 가능) |
| `memory_recursiveprot` | 재귀적 메모리 보호 (하위 cgroup에 메모리 보호 전파) |

### systemd cgroup 계층 구조 확인

`systemd-cgls` 명령어로 현재 시스템의 cgroup 계층 구조를 트리 형태로 확인한다.

```bash
systemd-cgls --no-pager
# CGroup /:
# -.slice
# ├─user.slice
# │ └─user-1000.slice
# │   ├─user@1000.service …
# │   │ └─init.scope
# │   │   ├─4488 /usr/lib/systemd/systemd --user
# │   │   └─4490 (sd-pam)
# │   └─session-4.scope
# │     ├─ 4483 sshd-session: vagrant [priv]
# │     ├─ 4505 sshd-session: vagrant@pts/0
# │     └─ 4507 -bash
# ├─init.scope
# │ └─1 /usr/lib/systemd/systemd --switched-root --system ...
# └─system.slice
#   ├─irqbalance.service
#   ├─chronyd.service
#   ├─sshd.service
#   ├─NetworkManager.service
#   └─...
```

| 항목 | 설명 |
| --- | --- |
| `user.slice` | 사용자 세션 관련 프로세스 (vagrant 로그인 세션 등) |
| `system.slice` | 시스템 서비스 (sshd, chronyd, NetworkManager 등) |
| `init.scope` | PID 1 (systemd) |

Kubernetes가 설치되면 이 계층 구조에 `kubelet.slice`와 컨테이너별 cgroup이 추가된다.


### cgroup 드라이버: cgroupfs vs systemd

Linux 시스템에서 cgroup을 관리할 수 있는 주체가 두 개 있다:

| 관리자 | 설명 |
| --- | --- |
| **systemd** | Linux의 init 시스템. 부팅 시 모든 서비스를 시작하고 관리 |
| **kubelet** | Kubernetes 노드 에이전트. 컨테이너 리소스를 관리 |

kubelet이 cgroup을 **어떤 방식으로** 관리할지 결정하는 것이 **cgroup 드라이버**다.

#### cgroupfs 드라이버

kubelet이 `/sys/fs/cgroup` 파일시스템을 **직접 조작**한다.

- systemd 기반 시스템에서는 **비권장**이다. 
  - systemd는 자신이 **유일한 cgroup 관리자**라고 기대한다.
  - kubelet이 cgroupfs로 직접 cgroup을 조작하면 **관리 주체가 둘이 되어 충돌**할 수 있다.
  - 충돌 시 systemd가 kubelet이 만든 cgroup을 인식하지 못해 정리해버리거나, 리소스 제한이 의도대로 적용되지 않아 Pod가 불안정해지거나 노드 전체가 불안정해질 수 있다.
- systemd가 없는 환경(*예: Alpine Linux(OpenRC)*) 등 systemd가 없는 환경에서는 cgroup 관리자가 kubelet 하나뿐이므로, cgroupfs를 써도 충돌 문제가 없다.

> Kubernetes 1.28부터 systemd가 기본값으로 변경되었다. 대부분의 프로덕션 서버가 systemd 기반이므로, systemd가 없는 환경이 아니라면 아래의 systemd 드라이버를 사용해야 한다.

<br>

#### systemd 드라이버 (권장)

kubelet이 **systemd를 통해** cgroup을 관리한다.

- kubelet이 cgroup 작업을 systemd에 위임한다.
- systemd가 일관되게 cgroup을 관리하므로 **충돌이 발생하지 않는다**.
- cgroup 계층 구조에 systemd의 slice 네이밍(`kubepods.slice`, `kubepods-burstable.slice` 등)이 적용된다.

#### 설정 방법

containerd 설정에서 `SystemdCgroup = true`로 지정한다:

```toml
# /etc/containerd/config.toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  SystemdCgroup = true
```

이 설정이 있으면 containerd가 컨테이너 생성 시 systemd를 통해 cgroup을 생성한다. Rocky Linux 10은 systemd를 사용하므로, 이후 실습에서 이 설정을 적용한다.

## 프로세스 확인

Kubernetes 설치 전 **베이스라인 스냅샷**을 남겨둔다. 이후 `kubeadm init` / `join` 후에 다시 실행하여 무엇이 달라졌는지 비교하기 위한 것이다.

### 프로세스 트리 확인

```bash
pstree
# systemd─┬─NetworkManager───3*[{NetworkManager}]
#         ├─VBoxService───8*[{VBoxService}]
#         ├─agetty
#         ├─anacron
#         ├─atd
#         ├─auditd─┬─sedispatch
#         │        └─2*[{auditd}]
#         ├─chronyd
#         ├─crond
#         ├─dbus-broker-lau───dbus-broker
#         ├─firewalld───{firewalld}
#         ├─gssproxy───5*[{gssproxy}]
#         ├─irqbalance───{irqbalance}
#         ├─lsmd
#         ├─polkitd───3*[{polkitd}]
#         ├─rpcbind
#         ├─rsyslogd───2*[{rsyslogd}]
#         ├─sshd───sshd-session───sshd-session───bash───pstree
#         ├─systemd───(sd-pam)
#         ├─systemd-hostnam
#         ├─systemd-journal
#         ├─systemd-logind
#         ├─systemd-udevd
#         ├─systemd-userdbd───3*[systemd-userwor]
#         └─tuned───3*[{tuned}]
```

`systemd` 아래 `sshd`, `VBoxService` 등 기본 데몬만 보인다. 아직 Kubernetes 컴포넌트가 없는 깨끗한 상태다. kubeadm으로 설치 후에는 `containerd`, `containerd-shim-runc-v2` 등이 트리에 새로 나타나는 것을 확인할 수 있다.

### 네임스페이스 목록 확인

```bash
lsns
#         NS TYPE   NPROCS   PID USER    COMMAND
# 4026531834 time        2  4533 vagrant -bash
# 4026531835 cgroup      2  4533 vagrant -bash
# 4026531836 pid         2  4533 vagrant -bash
# 4026531837 user        2  4533 vagrant -bash
# 4026531838 uts         2  4533 vagrant -bash
# 4026531839 ipc         2  4533 vagrant -bash
# 4026531840 net         2  4533 vagrant -bash
# 4026531841 mnt         2  4533 vagrant -bash
```

현재 시스템에 존재하는 Linux 네임스페이스 목록이다. 설치 전에는 모든 네임스페이스가 하나씩(호스트 네임스페이스)만 존재한다. Kubernetes 설치 후 컨테이너(Pod)가 뜨면 각 컨테이너마다 별도의 네임스페이스가 생성되어 `lsns` 출력이 크게 늘어난다. 컨테이너 격리가 실제로 네임스페이스 단위로 이루어지고 있음을 직접 확인할 수 있다.

| 명령어 | 확인 목적 |
| --- | --- |
| `pstree` | 프로세스 계층 구조 → K8s 설치 전후 프로세스 변화 비교 |
| `lsns` | 네임스페이스 목록 → 컨테이너 격리 상태 전후 비교 |

<br>

# 사전 설정

root 권한으로 전환 후 진행한다.

```bash
sudo su -
```

## 시간 동기화 설정

인증서 만료 시간, 로그 타임스탬프 등 클러스터 내 모든 노드의 시간이 동기화되어야 한다.

### 현재 시간 설정 확인

```bash
timedatectl status
# Time zone: UTC, NTP service: active, RTC in local TZ: yes
# Warning: The system is configured to read the RTC time in the local time zone. ...
```

### RTC를 UTC로 설정

`RTC in local TZ: yes`인 경우 Warning이 발생한다. RTC(하드웨어 시계)를 UTC로 설정하여 해결한다.

```bash
timedatectl set-local-rtc 0
timedatectl status
#           RTC in local TZ: no   <- Warning 해결
```

> **RTC(Real Time Clock)**는 컴퓨터가 꺼져 있을 때도 시간을 유지하는 하드웨어 시계다. RTC를 로컬 타임존으로 설정하면 DST(일광 절약 시간) 변경이나 타임존 변경 시 시간이 꼬일 수 있다. RTC는 항상 UTC로 유지하고, 표시만 로컬 타임존으로 변환하는 것이 권장된다.

### 타임존 설정

시스템 타임존을 한국(KST, UTC+9)으로 설정한다.

```bash
date                               # Thu Jan 22 03:44:02 PM UTC 2026
timedatectl set-timezone Asia/Seoul
date                               # Fri Jan 23 12:44:11 AM KST 2026
```

### NTP 동기화 활성화

NTP(Network Time Protocol)를 통해 시간을 자동 동기화한다.

```bash
timedatectl set-ntp true
timedatectl status  # Time zone: Asia/Seoul (KST), NTP: active, RTC in local TZ: no
```

NTP 서버 동기화 상태를 확인한다. Rocky Linux 9/10에서는 기본적으로 chrony를 사용한다.

```bash
chronyc sources -v
#   .-- Source mode  '^' = server, '=' = peer, '#' = local clock.
#  / .- Source state '*' = current best, '+' = combined, '-' = not combined,
# | /             'x' = may be in error, '~' = too variable, '?' = unusable.
# ...
# MS Name/IP address         Stratum Poll Reach LastRx Last sample               
# ===============================================================================
# ^- mail.zeroweb.kr               3   9   377   448   +290us[ +290us] +/-   48ms
# ^+ mail.innotab.com              3   9   377    31   -907us[ -907us] +/-   20ms
# ^- kr.timeadjust.org             3   8   377   331    -38ms[  -38ms] +/-   78ms
# ^* 175.210.18.47                 2   9   377   152   +490us[ +478us] +/-   11ms
```

| 항목 | 의미 |
| --- | --- |
| `^*` | 현재 사용 중인 NTP 서버 (best source) |
| `^+` | 결합된 소스 (combined) |
| `^-` | 결합되지 않은 소스 |
| Stratum 2 | 원자 시계(Stratum 0)로부터 2단계 떨어진 서버. 신뢰도 높음 |
| Reach 377 | 최근 8회 폴링 모두 응답 성공 (8진수 377 = 2진수 11111111) |
| Last sample | 시간 오차. `+490us`는 0.49ms 빠름을 의미 |

<br>

시스템 시간 동기화 상태를 더 자세히 확인하려면 `chronyc tracking` 명령어를 사용한다.

```bash
chronyc tracking
# Reference ID: 175.210.18.47, System time: 0.85ms fast, Leap status: Normal
```

| 항목 | 설명 |
| --- | --- |
| **Reference ID** | 현재 동기화 중인 NTP 서버 |
| **System time** | NTP 시간과의 오차 (약 0.85ms 빠름) |
| **Leap status: Normal** | 윤초 조정 상태 정상 |

<br>

## SELinux 설정

**SELinux(Security-Enhanced Linux)**는 Linux 커널의 보안 모듈로, 프로세스가 파일, 포트, 다른 프로세스에 접근하는 것을 세밀하게 제어한다.

| 모드 | 설정값 | 설명 |
| --- | --- | --- |
| **Enforcing** | 1 | 정책 위반 시 접근 차단 + 로그 기록 |
| **Permissive** | 0 | 정책 위반 시 접근 허용 + 로그 기록 (경고만) |
| **Disabled** | — | SELinux 완전 비활성화. `setenforce`로 전환 불가, 커널 부팅 옵션 `selinux=0` 필요 후 재부팅 |

`setenforce 0`(Permissive), `setenforce 1`(Enforcing)으로 런타임 전환 가능하다.

<br>

Kubernetes는 SELinux를 **Permissive 모드**로 설정하는 것을 권장한다. 그 이유는 아래와 같다:

- 컨테이너가 호스트 파일시스템(예: Pod 네트워크, 볼륨)에 접근할 때 SELinux 정책에 의해 차단될 수 있다.
- Enforcing 모드에서는 kubelet, 컨테이너 런타임 등이 필요한 리소스에 접근하지 못해 오류가 발생할 수 있다.
- Permissive 모드는 정책 위반을 로그로 기록하되 차단하지 않아, 문제 발생 시 원인 파악이 용이하다.

### 현재 상태 확인

```bash
getenforce   # Enforcing
sestatus     # SELinux status: enabled, Current mode: enforcing
```

### Permissive 모드로 변경

`setenforce 0` 명령어로 즉시 Permissive 모드로 변경한다.

```bash
setenforce 0
getenforce # Permissive
sestatus
# Current mode:                   permissive
# Mode from config file:          enforcing   <- 아직 설정 파일은 enforcing
```

### 재부팅 시에도 Permissive 적용

`setenforce`는 런타임 설정이므로 재부팅하면 원래대로 돌아간다. `/etc/selinux/config` 파일을 수정하여 영구 적용한다.

```bash
cat /etc/selinux/config | grep ^SELINUX
# SELINUX=enforcing
# SELINUXTYPE=targeted

sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config

cat /etc/selinux/config | grep ^SELINUX
# SELINUX=permissive
# SELINUXTYPE=targeted
```

<br>

## 방화벽 비활성화

실습 환경에서는 방화벽을 비활성화한다. 프로덕션 환경에서는 필요한 포트만 열어두는 것이 좋다.

```bash
# firewalld 상태 확인 및 비활성화
systemctl status firewalld
systemctl disable --now firewalld
systemctl status firewalld
```

> 참고: **프로덕션 환경에서 필요한 포트**
> 
> - Control Plane: 6443(API Server), 2379-2380(etcd), 10250(kubelet), 10259(scheduler), 10257(controller-manager)
> - Worker Node: 10250(kubelet), 30000-32767(NodePort)

<br>

## Swap 비활성화

Kubernetes는 스왑 비활성화를 권장한다. kubeadm으로 클러스터를 구성할 때는 스왑이 활성화되어 있으면 [preflight 검사에서 실패](https://v1-32.docs.kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/#swap-configuration)하여 초기화가 진행되지 않는다. 

> 참고: **왜 Swap을 비활성화해야 하는가?** 
> 
> 스케줄링 부정확, OOM Killer 지연, 성능 저하 등 상세한 이유와 NodeSwap 기능은 [쿠버네티스와 스왑]({% post_url 2026-01-23-Kubernetes-Swap %}) 글을 참고한다. 스왑의 동작 원리·Thrashing·`vm.swappiness`는 [메모리, 페이지, 스왑]({% post_url 2026-01-23-CS-Memory-Page-Swap %}), kubelet swap 설정(`failSwapOn`, `memorySwap.swapBehavior`)은 [Kubernetes The Hard Way - kubelet 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}#swap-설정)을 참고한다.

### 현재 Swap 상태 확인

```bash
lsblk
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
# sda      8:0    0   64G  0 disk 
# ├─sda1   8:1    0  600M  0 part /boot/efi
# ├─sda2   8:2    0  3.8G  0 part [SWAP]
# └─sda3   8:3    0 59.6G  0 part /

free -h
#                total        used        free      shared  buff/cache   available
# Mem:           2.8Gi       343Mi       2.3Gi        18Mi       261Mi       2.4Gi
# Swap:          3.8Gi          0B       3.8Gi
```

`lsblk` 출력을 보면 64GB 디스크가 다음과 같이 파티셔닝되어 있다:

| 파티션 | 크기 | 용도 |
| --- | --- | --- |
| sda1 | 600M | EFI 부트 파티션 |
| sda2 | 3.8G | Swap 파티션 (일반적으로 RAM 크기와 비슷하게 설정) |
| sda3 | 59.6G | 루트 파일시스템 (`/`) |

Swap 파티션(sda2)이 `[SWAP]`으로 마운트되어 있고, `free -h`에서도 3.8GB Swap이 활성화되어 있다.

### Swap 비활성화

```bash
swapoff -a

lsblk
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
# sda      8:0    0   64G  0 disk 
# ├─sda1   8:1    0  600M  0 part /boot/efi
# ├─sda2   8:2    0  3.8G  0 part          <- [SWAP] 표시 사라짐
# └─sda3   8:3    0 59.6G  0 part /

free -h | grep -i swap
# Swap:             0B          0B          0B
```

`swapoff -a` 실행 후 sda2의 `[SWAP]` 표시가 사라지고, `free -h`에서 Swap이 0B로 변경되었다.

### 재부팅 시에도 Swap 비활성화 유지

`swapoff`는 런타임 설정이므로 재부팅하면 다시 활성화된다. `/etc/fstab`에서 swap 라인을 삭제하여 영구 적용한다.

```bash
cat /etc/fstab | grep swap
# UUID=2270fed4-fef4-43c1-909f-b08a96bb14e9 none   swap    defaults   0 0

sed -i '/swap/d' /etc/fstab

cat /etc/fstab | grep swap
# (출력 없음 - swap 라인 삭제됨)
```

<br>

## 커널 모듈 및 파라미터 설정

Kubernetes 네트워킹에 필요한 커널 모듈을 로드하고 파라미터를 설정한다.

### 커널 모듈 로드

containerd와 Kubernetes 네트워킹에 필요한 커널 모듈을 로드한다. `overlay`는 컨테이너 이미지 레이어링에, `br_netfilter`는 Pod 간 네트워크 통신에, `fuse`는 lazy loading snapshotter용으로 필요하다.

```bash
# 현재 로드된 모듈 확인 (아직 로드되지 않음)
lsmod | grep -i br_netfilter
# (출력 없음)

# 커널 모듈 로드
modprobe overlay
modprobe br_netfilter
modprobe fuse

# 로드 확인
lsmod | grep -iE 'overlay|br_netfilter|fuse'
# br_netfilter           32768  0
# bridge                327680  1 br_netfilter
# overlay               200704  0
# fuse                  204800  1
```

| 모듈 | 설명 |
| --- | --- |
| `overlay` | 컨테이너 이미지 레이어링에 사용되는 OverlayFS 드라이버 |
| `br_netfilter` | 브릿지 네트워크 트래픽을 iptables에서 처리할 수 있게 함 |
| `fuse` | lazy loading snapshotter(stargz 등)에 필요한 FUSE(Filesystem in Userspace) 드라이버 |

`br_netfilter`를 로드하면 의존성으로 `bridge` 모듈도 함께 로드된다.

```bash
# 재부팅 시에도 자동 로드되도록 설정
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
fuse
EOF
# overlay
# br_netfilter
# fuse
```

```bash
tree /etc/modules-load.d/
# /etc/modules-load.d/
# └── k8s.conf
#
# 1 directory, 1 file
```

### 커널 파라미터 설정

Kubernetes 네트워킹이 정상 동작하려면 브릿지 트래픽이 iptables를 통과하고, IP 포워딩이 활성화되어야 한다.

> **참고**: Kubernetes의 Service(ClusterIP, NodePort 등)는 kube-proxy가 설정한 iptables 규칙(DNAT/SNAT)으로 동작한다. Pod 간 트래픽은 Linux bridge(cni0 등)를 통과하는데, 기본적으로 bridge를 통과하는 패킷은 iptables를 거치지 않는다. `bridge-nf-call-iptables`를 켜지 않으면 같은 노드 안에서 Pod → Service ClusterIP로 가는 트래픽이 iptables 규칙을 타지 않아 라우팅이 실패한다. IP 포워딩도 마찬가지로, 커널은 기본적으로 자신의 IP가 아닌 패킷을 drop한다. Kubernetes 노드는 Pod 간 트래픽이나 Pod → 외부 트래픽을 중계(라우팅)해야 하므로 `ip_forward`가 반드시 활성화되어야 한다.

```bash
# 커널 파라미터 설정 파일 생성
cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
# net.bridge.bridge-nf-call-iptables  = 1
# net.bridge.bridge-nf-call-ip6tables = 1
# net.ipv4.ip_forward                 = 1
```

| 파라미터 | 설명 |
| --- | --- |
| `net.bridge.bridge-nf-call-iptables` | 브릿지를 통과하는 IPv4 트래픽을 iptables로 처리. Pod에서 나가는 트래픽이 iptables 규칙(SNAT, DNAT 등)을 거치도록 함 |
| `net.bridge.bridge-nf-call-ip6tables` | 브릿지를 통과하는 IPv6 트래픽을 ip6tables로 처리 |
| `net.ipv4.ip_forward` | IP 포워딩 활성화. 노드가 라우터 역할을 하여 Pod 간 통신, Service 트래픽 전달에 필요 |


<br>

설정 파일을 생성했지만 아직 적용되지 않았다. `sysctl --system` 명령어로 모든 sysctl 설정 파일을 다시 로드한다.

```bash
sysctl --system
# * Applying /usr/lib/sysctl.d/10-default-yama-scope.conf ...
# * Applying /usr/lib/sysctl.d/50-default.conf ...
# ...
# * Applying /etc/sysctl.d/k8s.conf ...        <- k8s.conf 적용
# * Applying /etc/sysctl.conf ...
# ...
# net.bridge.bridge-nf-call-iptables = 1
# net.bridge.bridge-nf-call-ip6tables = 1
# net.ipv4.ip_forward = 1
```

적용되었는지 확인한다.

```bash
sysctl net.bridge.bridge-nf-call-iptables   # = 1
sysctl net.ipv4.ip_forward                  # = 1
```

<br>

## hosts 설정

각 노드가 호스트명으로 서로를 찾을 수 있도록 `/etc/hosts`를 설정한다.

### 기존 항목 확인 및 정리

```bash
cat /etc/hosts
# 127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
# ::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
# 127.0.1.1 k8s-ctr k8s-ctr    <- 문제가 되는 라인
```

Vagrant가 자동으로 `127.0.1.1 <hostname>` 항목을 추가한다. 이 라인이 있으면 hostname이 `127.0.1.1`(localhost)로 resolve되어 문제가 발생한다.

- kubelet이 API Server에 자신을 등록할 때 `127.0.1.1`로 등록되면 다른 노드에서 접근 불가
- 컨트롤 플레인 컴포넌트들이 localhost로 통신하려고 시도

```bash
# 127.0.1.1 또는 127.0.2.1로 시작하는 라인 삭제
sed -i '/^127\.0\.\(1\|2\)\.1/d' /etc/hosts

cat /etc/hosts
# 127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
# ::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
# (127.0.1.1 라인 삭제됨)
```

### 클러스터 노드 정보 추가

```bash
cat << EOF >> /etc/hosts
192.168.10.100 k8s-ctr
192.168.10.101 k8s-w1
192.168.10.102 k8s-w2
EOF

cat /etc/hosts
# 127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
# ::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
# 192.168.10.100 k8s-ctr
# 192.168.10.101 k8s-w1
# 192.168.10.102 k8s-w2
```

### 연결 확인
호스트명이 실제 IP(192.168.10.x)로 resolve되는 것을 확인할 수 있다.
```bash
ping -c 1 k8s-ctr  # 192.168.10.100 → OK
ping -c 1 k8s-w1   # 192.168.10.101 → OK
ping -c 1 k8s-w2   # 192.168.10.102 → OK
```


<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

| 항목 | 결과 |
| --- | --- |
| 시간 동기화 | chrony를 통한 NTP 동기화 설정 |
| SELinux | Permissive 모드 |
| 방화벽 | 비활성화 |
| Swap | 비활성화 |
| 커널 모듈 | overlay, br_netfilter 로드 |
| 커널 파라미터 | bridge-nf-call-iptables, ip_forward 활성화 |
| hosts | 클러스터 노드 정보 추가 |

<br>

[다음 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %})에서 containerd와 kubeadm/kubelet/kubectl을 설치한다.
