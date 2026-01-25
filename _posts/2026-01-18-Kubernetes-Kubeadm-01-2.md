---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.2. 사전 설정 및 구성 요소 설치"
excerpt: "kubeadm을 사용한 클러스터 구성을 위해 필요한 사전 설정, CRI(containerd) 설치, kubeadm/kubelet/kubectl 설치를 수행한다."
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

이번 글의 목표는 **kubeadm 클러스터 구성을 위한 사전 설정 및 구성 요소 설치**다.

- **사전 설정**: 시간 동기화, SELinux, 방화벽, Swap, 커널 모듈/파라미터, hosts 설정
- **CRI 설치**: containerd v2.1.5 설치 및 SystemdCgroup 활성화
- **kubeadm 설치**: kubeadm, kubelet, kubectl v1.32.11 설치

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

현재 루트 파티션(`/`)에 **58GB 가용 공간**이 있어 충분하다. `/boot/efi` 파티션은 EFI 부팅을 위한 것으로, Vagrant VM이 UEFI 부팅을 사용함을 알 수 있다.


## 네트워크

Kubernetes 노드 간 통신에 사용할 네트워크 인터페이스와 IP 주소를 파악한다. Vagrant 환경에서는 보통 여러 네트워크 인터페이스가 있으므로 클러스터 통신에 사용할 인터페이스를 정확히 식별해야 한다.

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

#### cgroupfs 드라이버 (비권장)

kubelet이 `/sys/fs/cgroup` 파일시스템을 **직접 조작**한다.

- systemd는 자신이 **유일한 cgroup 관리자**라고 기대한다.
- kubelet이 cgroupfs로 직접 cgroup을 조작하면 **systemd의 관리와 충돌**할 수 있다.

#### systemd 드라이버 (권장)

kubelet이 **systemd를 통해** cgroup을 관리한다.

- kubelet이 cgroup 작업을 systemd에 위임한다.
- systemd가 일관되게 cgroup을 관리하므로 **충돌이 발생하지 않는다**.

#### 설정 방법

containerd 설정에서 `SystemdCgroup = true`로 지정한다:

```toml
# /etc/containerd/config.toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  SystemdCgroup = true
```

이 설정이 있으면 containerd가 컨테이너 생성 시 systemd를 통해 cgroup을 생성한다. Rocky Linux 10은 systemd를 사용하므로, 이후 실습에서 이 설정을 적용한다.

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

시스템 시간 동기화 상태를 더 자세히 확인하려면 `chronyc tracking` 명령어를 사용한다.

```bash
chronyc tracking
# Reference ID: 175.210.18.47, System time: 0.85ms fast, Leap status: Normal
```

- **Reference ID**: 현재 동기화 중인 NTP 서버
- **System time**: NTP 시간과의 오차 (약 0.85ms 빠름)
- **Leap status: Normal**: 윤초 조정 상태 정상

<br>

## SELinux 설정

**SELinux(Security-Enhanced Linux)**는 Linux 커널의 보안 모듈로, 프로세스가 파일, 포트, 다른 프로세스에 접근하는 것을 세밀하게 제어한다.

| 모드 | 설명 |
| --- | --- |
| **Enforcing** | 정책 위반 시 접근 차단 + 로그 기록 |
| **Permissive** | 정책 위반 시 접근 허용 + 로그 기록 (경고만) |
| **Disabled** | SELinux 완전 비활성화 |

Kubernetes는 SELinux를 **Permissive 모드**로 설정하는 것을 권장한다. 그 이유는:

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

> 프로덕션 환경에서 필요한 포트:
> - Control Plane: 6443(API Server), 2379-2380(etcd), 10250(kubelet), 10259(scheduler), 10257(controller-manager)
> - Worker Node: 10250(kubelet), 30000-32767(NodePort)

<br>

## Swap 비활성화

Kubernetes는 Swap이 활성화되어 있으면 [kubelet이 시작되지 않는다](https://v1-32.docs.kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/#swap-configuration). 

> 참고: **왜 Swap을 비활성화해야 하는가?** 
> 
> 1. **스케줄링 부정확**: Kubernetes 스케줄러는 Pod에 요청된 메모리를 기반으로 노드에 배치한다. Swap이 활성화되어 있으면 실제 메모리 상태를 정확히 파악할 수 없어 스케줄링이 부정확해진다.
> 2. **OOM Killer 지연**: 메모리가 부족할 때 Swap이 없으면 OOM Killer가 즉시 문제 프로세스를 종료하고, kubelet이 이를 감지하여 Pod를 재스케줄링한다. 하지만 Swap이 있으면 메모리 부족 상황에서도 Swap을 사용해 버티기 때문에 OOM Killer 발동이 지연되고, 문제 컨테이너가 극도로 느린 상태로 계속 실행되어 전체 노드 성능이 저하된다. 이 현상이 심해지면 **Thrashing**이 발생한다.
> 3. **성능 저하**: Swap은 디스크 I/O를 사용하므로 메모리보다 훨씬 느리다. 컨테이너가 Swap을 사용하면 성능이 급격히 저하된다.
>
> 스왑의 동작 원리, Thrashing, `vm.swappiness` 등 자세한 내용은 [메모리, 페이지, 스왑]({% post_url 2026-01-23-CS-Memory-Page-Swap %}) 글을 참고한다. kubelet의 swap 관련 설정(`failSwapOn`, `memorySwap.swapBehavior`)은 [Kubernetes The Hard Way - kubelet 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}#swap-설정)에서 확인할 수 있다.

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

containerd와 Kubernetes 네트워킹에 필요한 커널 모듈을 로드한다. `overlay`는 컨테이너 이미지 레이어링에, `br_netfilter`는 Pod 간 네트워크 통신에 필요하다.

```bash
# 현재 로드된 모듈 확인 (아직 로드되지 않음)
lsmod | grep -iE 'overlay|br_netfilter'
# (출력 없음)

# 커널 모듈 로드
modprobe overlay
modprobe br_netfilter

# 로드 확인
lsmod | grep -iE 'overlay|br_netfilter'
# br_netfilter           32768  0
# bridge                327680  1 br_netfilter
# overlay               200704  0
```

| 모듈 | 설명 |
| --- | --- |
| `overlay` | 컨테이너 이미지 레이어링에 사용되는 OverlayFS 드라이버 |
| `br_netfilter` | 브릿지 네트워크 트래픽을 iptables에서 처리할 수 있게 함 |


`br_netfilter`를 로드하면 의존성으로 `bridge` 모듈도 함께 로드된다.

```bash
# 재부팅 시에도 자동 로드되도록 설정
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
# overlay
# br_netfilter
```

### 커널 파라미터 설정

Kubernetes 네트워킹이 정상 동작하려면 브릿지 트래픽이 iptables를 통과하고, IP 포워딩이 활성화되어야 한다.

| 파라미터 | 설명 |
| --- | --- |
| `net.bridge.bridge-nf-call-iptables` | 브릿지를 통과하는 IPv4 트래픽을 iptables로 처리. Pod에서 나가는 트래픽이 iptables 규칙(SNAT, DNAT 등)을 거치도록 함 |
| `net.bridge.bridge-nf-call-ip6tables` | 브릿지를 통과하는 IPv6 트래픽을 ip6tables로 처리 |
| `net.ipv4.ip_forward` | IP 포워딩 활성화. 노드가 라우터 역할을 하여 Pod 간 통신, Service 트래픽 전달에 필요 |

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

적용 확인:

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

# CRI 설치: containerd

Kubernetes는 컨테이너 런타임으로 CRI(Container Runtime Interface)를 준수하는 런타임을 사용한다. 이 실습에서는 containerd v2.1.5를 설치한다.

> containerd는 CNCF ['graduated'](https://landscape.cncf.io/?selected=containerd) 프로젝트로, 업계 표준 컨테이너 런타임이다. 단순성, 견고성, 이식성에 중점을 두고 설계되었다.

## containerd와 Kubernetes 버전 호환성

이 실습에서는 Kubernetes 1.32를 설치하고, 이후 1.33, 1.34로 업그레이드할 예정이다. containerd도 호환되는 버전을 사용해야 한다.

| Kubernetes Version | containerd Version | CRI Version |
| --- | --- | --- |
| **1.32** | **2.1.0+**, 2.0.1+, 1.7.24+, 1.6.36+ | v1 |
| **1.33** | **2.1.0+**, 2.0.4+, 1.7.24+, 1.6.36+ | v1 |
| **1.34** | **2.1.3+**, 2.0.6+, 1.7.28+, 1.6.36+ | v1 |
| 1.35 | 2.2.0+, 2.1.5+, 1.7.28+ | v1 |

> 참고: [containerd Kubernetes support](https://containerd.io/releases/#kubernetes-support)

containerd **2.1.5**를 설치하면 Kubernetes 1.32 ~ 1.35까지 모두 호환된다.

### config.toml 버전 주의

containerd는 `/etc/containerd/config.toml` 설정 파일을 사용하는데, **containerd 버전에 따라 config.toml 규격이 다르다**.

| containerd Version | config.toml Version |
| --- | --- |
| 1.x (1.7 이하) | version 2 |
| 2.x | **version 3** |

containerd 1.7에서 2.x로 업그레이드할 때 config.toml 규격이 달라지므로 주의가 필요하다. 이 실습에서는 처음부터 **containerd 2.x**를 설치하여 이러한 복잡성을 피한다.

<br>

## Docker 저장소 추가

containerd는 Docker 저장소에서 제공하는 패키지를 사용한다.

```bash
# 현재 저장소 확인
dnf repolist
# repo id          repo name
# appstream        Rocky Linux 10 - AppStream
# baseos           Rocky Linux 10 - BaseOS
# extras           Rocky Linux 10 - Extras

tree /etc/yum.repos.d/
# /etc/yum.repos.d
# ├── rocky-addons.repo
# ├── rocky-devel.repo
# ├── rocky-extras.repo
# └── rocky.repo
```

```bash
# Docker 저장소 추가
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
# Adding repo from: https://download.docker.com/linux/centos/docker-ce.repo

dnf repolist
# repo id              repo name
# appstream            Rocky Linux 10 - AppStream
# baseos               Rocky Linux 10 - BaseOS
# docker-ce-stable     Docker CE Stable - aarch64    <- 추가됨
# extras               Rocky Linux 10 - Extras

# 메타데이터 캐시 생성
dnf makecache
# Metadata cache created.
```

```bash
# 설치 가능한 containerd.io 버전 확인
dnf list --showduplicates containerd.io
# Available Packages
# containerd.io.aarch64    1.7.23-3.1.el10    docker-ce-stable
# containerd.io.aarch64    1.7.24-3.1.el10    docker-ce-stable
# ...
# containerd.io.aarch64    1.7.29-1.el10      docker-ce-stable
# containerd.io.aarch64    2.1.5-1.el10       docker-ce-stable   <- 설치할 버전
# containerd.io.aarch64    2.2.0-2.el10       docker-ce-stable
# containerd.io.aarch64    2.2.1-1.el10       docker-ce-stable
```

1.7.x와 2.x 버전이 모두 제공되는 것을 확인할 수 있다. 앞서 설명한 대로 **2.1.5**를 설치한다.

<br>

## containerd 설치

```bash
# containerd 2.1.5 설치
dnf install -y containerd.io-2.1.5-1.el10
# Installed: containerd.io-2.1.5-1.el10.aarch64
```

설치가 완료되면 함께 설치된 구성 요소들을 확인한다.

```bash
runc --version        # runc version 1.3.3 (OCI 스펙 준수 컨테이너 런타임)
containerd --version  # containerd.io v2.1.5 (컨테이너 라이프사이클 관리)
ctr --version         # ctr containerd.io v2.1.5 (디버깅용 CLI)
```

기본 설정 파일과 systemd 서비스 파일을 확인한다.

```bash
# 기본 설정 파일 확인
cat /etc/containerd/config.toml
# ...
# disabled_plugins = ["cri"]  # 기본 설정에서는 CRI 플러그인이 비활성화됨!
# ...

# systemd 서비스 파일 위치
tree /usr/lib/systemd/system | grep containerd
# ├── containerd.service

# 서비스 파일 내용 확인
cat /usr/lib/systemd/system/containerd.service
# [Unit]
# Description=containerd container runtime
# Documentation=https://containerd.io
# After=network.target dbus.service
#
# [Service]
# ExecStartPre=-/sbin/modprobe overlay
# ExecStart=/usr/bin/containerd
# Type=notify
# Delegate=yes          # cgroup 관리 위임
# KillMode=process
# Restart=always
# RestartSec=5
# LimitNPROC=infinity
# LimitCORE=infinity
# TasksMax=infinity
# OOMScoreAdjust=-999   # OOM Killer 대상에서 제외
#
# [Install]
# WantedBy=multi-user.target
```

> **주의**: 기본 설정 파일에서 `disabled_plugins = ["cri"]`로 CRI 플러그인이 비활성화되어 있다. Kubernetes에서 사용하려면 이 설정을 변경하고 systemd cgroup 드라이버를 활성화해야 한다. 다음 단계에서 설정 파일을 새로 생성한다.

<br>

## containerd 설정

### 기본 설정 생성 및 SystemdCgroup 활성화

**매우 중요한 단계**다. containerd가 systemd cgroup 드라이버를 사용하도록 설정해야 한다.

```bash
# 기본 설정 파일 생성
containerd config default | tee /etc/containerd/config.toml
# version = 3
# root = '/var/lib/containerd'
# state = '/run/containerd'
# ...
# disabled_plugins = []   # CRI 플러그인 활성화됨!
# ...

# 설정 파일 확인 (version = 3은 containerd 2.0 이상)
head /etc/containerd/config.toml
# version = 3
# root = '/var/lib/containerd'
# state = '/run/containerd'
# temp = ''
# disabled_plugins = []
# required_plugins = []
# oom_score = 0
# imports = []
#
# [grpc]
```

<details markdown="1">
<summary>containerd config default 전체 출력 (클릭하여 펼치기)</summary>

```toml
version = 3
root = '/var/lib/containerd'
state = '/run/containerd'
temp = ''
disabled_plugins = []
required_plugins = []
oom_score = 0
imports = []

[grpc]
  address = '/run/containerd/containerd.sock'
  tcp_address = ''
  tcp_tls_ca = ''
  tcp_tls_cert = ''
  tcp_tls_key = ''
  uid = 0
  gid = 0
  max_recv_message_size = 16777216
  max_send_message_size = 16777216

[ttrpc]
  address = ''
  uid = 0
  gid = 0

[debug]
  address = ''
  uid = 0
  gid = 0
  level = ''
  format = ''

[metrics]
  address = ''
  grpc_histogram = false

[plugins]
  [plugins.'io.containerd.cri.v1.images']
    snapshotter = 'overlayfs'
    disable_snapshot_annotations = true
    discard_unpacked_layers = false
    max_concurrent_downloads = 3
    # ...

    [plugins.'io.containerd.cri.v1.images'.pinned_images]
      sandbox = 'registry.k8s.io/pause:3.10'

    [plugins.'io.containerd.cri.v1.images'.registry]
      config_path = ''

  [plugins.'io.containerd.cri.v1.runtime']
    enable_selinux = false
    # ...

    [plugins.'io.containerd.cri.v1.runtime'.containerd]
      default_runtime_name = 'runc'

      [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes]
        [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc]
          runtime_type = 'io.containerd.runc.v2'
          sandboxer = 'podsandbox'

          [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc.options]
            BinaryName = ''
            SystemdCgroup = false    # <- 이 값을 true로 변경해야 함!

    [plugins.'io.containerd.cri.v1.runtime'.cni]
      bin_dirs = ['/opt/cni/bin']
      conf_dir = '/etc/cni/net.d'

  [plugins.'io.containerd.grpc.v1.cri']
    disable_tcp_service = true
    stream_server_address = '127.0.0.1'
    stream_server_port = '0'
    stream_idle_timeout = '4h0m0s'

  # ... (기타 플러그인 설정 생략)

[cgroup]
  path = ''

[timeouts]
  'io.containerd.timeout.bolt.open' = '0s'
  'io.containerd.timeout.cri.defercleanup' = '1m0s'
  'io.containerd.timeout.shim.cleanup' = '5s'
  'io.containerd.timeout.shim.load' = '5s'
  'io.containerd.timeout.shim.shutdown' = '3s'
  'io.containerd.timeout.task.state' = '2s'

[stream_processors]
  [stream_processors.'io.containerd.ocicrypt.decoder.v1.tar']
    accepts = ['application/vnd.oci.image.layer.v1.tar+encrypted']
    returns = 'application/vnd.oci.image.layer.v1.tar'
    path = 'ctd-decoder'

  [stream_processors.'io.containerd.ocicrypt.decoder.v1.tar.gzip']
    accepts = ['application/vnd.oci.image.layer.v1.tar+gzip+encrypted']
    returns = 'application/vnd.oci.image.layer.v1.tar+gzip'
    path = 'ctd-decoder'
```

</details>

<br>

기본 설정에서 `disabled_plugins = []`로 CRI 플러그인이 활성화되어 있다. 하지만 **SystemdCgroup = false**가 기본값이므로 이를 활성화해야 한다. 이 설정이 없으면 kubelet과 containerd 간 cgroup 관리 충돌이 발생할 수 있다.

```bash
# SystemdCgroup 설정 확인 (기본값은 false)
cat /etc/containerd/config.toml | grep -i systemdcgroup
#             SystemdCgroup = false

# SystemdCgroup 활성화
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

# 변경 확인
cat /etc/containerd/config.toml | grep -i systemdcgroup
#             SystemdCgroup = true
```

> 참고: **containerd 1.x vs 2.x 설정 차이**
>
> | containerd 버전 | config version | CRI 플러그인 경로 |
> | --- | --- | --- |
> | 1.x | version = 2 | `plugins."io.containerd.grpc.v1.cri"` |
> | **2.x** | **version = 3** | `plugins.'io.containerd.cri.v1.images'` |

<br>

### containerd 서비스 시작

```bash
systemctl daemon-reload
systemctl enable --now containerd
systemctl status containerd --no-pager  # Active: active (running)
```

상세 로그를 확인하면 **SystemdCgroup:true** 설정이 적용된 것을 확인할 수 있다.

```bash
journalctl -u containerd.service --no-pager
# Jan 23 01:12:46 k8s-ctr systemd[1]: Starting containerd.service - containerd container runtime...
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="starting containerd" ... version=v2.1.5
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="loading plugin" id=io.containerd.snapshotter.v1.overlayfs ...
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="starting cri plugin" config="...\"SystemdCgroup\":true..."
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... level=error msg="failed to load cni during init..." 
#   error="cni config load failed: no network config found in /etc/cni/net.d: ..."
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="containerd successfully booted in 0.030233s"
# Jan 23 01:12:46 k8s-ctr systemd[1]: Started containerd.service - containerd container runtime.
```

> CNI 관련 에러(`failed to load cni during init`)는 아직 CNI 플러그인을 설치하지 않았기 때문에 발생하는 것으로, 정상이다. CNI는 `kubeadm init` 후 네트워크 플러그인(Calico 등)을 설치하면 구성된다.

프로세스 트리와 cgroup 계층을 확인한다.

```bash
# containerd 프로세스 트리 확인
pstree -alnp | grep containerd
#   `-containerd,11617
#       |-{containerd},11619
#       |-{containerd},11620
#       ...

# cgroup 계층에서 containerd 확인
systemd-cgls --no-pager
# CGroup /:
# -.slice
# ├─user.slice
# │ └─...
# └─system.slice
#   ├─containerd.service …
#   │ └─11617 /usr/bin/containerd
#   ├─chronyd.service
#   │ └─666 /usr/sbin/chronyd -F 2
#   ...
```

`systemd-cgls` 출력에서 containerd가 `system.slice/containerd.service` cgroup 아래에서 실행되는 것을 확인할 수 있다. systemd cgroup 드라이버가 정상적으로 작동하고 있다.

<br>

### 소켓 및 플러그인 확인

```bash
# containerd 유닉스 도메인 소켓 확인 (kubelet, ctr, crictl이 이 소켓 사용)
ls -l /run/containerd/containerd.sock  # srw-rw----. 1 root root 0 ...
ss -xl | grep containerd               # .sock.ttrpc(gRPC), .sock(TTRPC) LISTEN 확인
ctr version                            # Client/Server: v2.1.5
```

플러그인 상태를 확인한다. Kubernetes에서 사용하는 주요 플러그인이 `ok` 상태인지 확인한다.

```bash
ctr plugins ls
# TYPE                                   ID                  PLATFORMS        STATUS
# io.containerd.content.v1               content             -                ok      # 이미지 레이어 저장
# io.containerd.snapshotter.v1           overlayfs           linux/arm64/v8   ok      # Kubernetes 기본 snapshotter
# io.containerd.snapshotter.v1           native              linux/arm64/v8   ok
# io.containerd.metadata.v1              bolt                -                ok      # 메타데이터 DB
# io.containerd.monitor.task.v1          cgroups             linux/arm64/v8   ok      # cgroup 모니터링
# io.containerd.runtime.v2               task                linux/arm64/v8   ok      # 런타임 (runc)
# io.containerd.cri.v1                   images              -                ok      # CRI 이미지 서비스
# io.containerd.cri.v1                   runtime             linux/arm64/v8   ok      # CRI 런타임 서비스
# io.containerd.grpc.v1                  cri                 -                ok      # CRI gRPC 인터페이스
# io.containerd.podsandbox.controller.v1 podsandbox          -                ok      # Pod sandbox 관리
# ...
```

> **핵심 플러그인 확인 포인트**
> - `io.containerd.cri.v1`: CRI 플러그인 - kubelet이 containerd와 통신하는 인터페이스
> - `io.containerd.snapshotter.v1 overlayfs`: 컨테이너 파일시스템 레이어 관리
> - `io.containerd.runtime.v2 task`: 실제 컨테이너 실행 (runc 연동)

> **참고: Lazy-loading Snapshotter**
> 
> 기본 `overlayfs` snapshotter는 컨테이너 시작 전 **전체 이미지를 다운로드**해야 한다. 대용량 이미지(ML 모델, 데이터 분석 도구 등)의 경우 이미지 pull 시간이 컨테이너 시작 시간의 대부분을 차지할 수 있다.
> 
> 이런 경우 **lazy-loading snapshotter**를 고려할 수 있다:
> - [**eStargz (stargz-snapshotter)**](https://github.com/containerd/stargz-snapshotter): CNCF containerd 프로젝트. 이미지를 부분적으로 다운로드하며 필요한 파일만 on-demand로 fetch
> - [**SOCI Snapshotter**](https://github.com/awslabs/soci-snapshotter): AWS에서 개발. 기존 OCI 이미지를 수정 없이 사용하면서 lazy-loading 지원 ([AWS 블로그](https://aws.amazon.com/ko/blogs/tech/under-the-hood-lazy-loading-container-images-with-seekable-oci-and-aws-fargate/))
>
> 이러한 snapshotter를 사용하면 이미지 크기와 관계없이 컨테이너를 빠르게 시작할 수 있어, 스케일링이 빈번한 워크로드에 유리하다.

<br>

# kubeadm, kubelet, kubectl 설치

이제 Kubernetes 핵심 도구들을 설치한다.

| 도구 | 역할 |
| --- | --- |
| **kubeadm** | 클러스터 부트스트래핑 도구 |
| **kubelet** | 각 노드에서 Pod를 관리하는 에이전트 |
| **kubectl** | 클러스터와 상호작용하는 CLI 도구 |

<br>

## Kubernetes 저장소 추가

```bash
# 현재 저장소 확인
dnf repolist
tree /etc/yum.repos.d/

# Kubernetes 저장소 추가
# exclude: dnf update 시 실수로 kubelet 자동 업그레이드 방지
cat <<EOF | tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF
dnf makecache
```

<br>

## 설치 가능 버전 확인

```bash
# exclude 설정이 적용된 경우 목록이 비어 있음
dnf list --showduplicates kubelet
# Error: No matching Packages to list

# --disableexcludes 옵션으로 exclude 규칙 무시 (1회성)
dnf list --showduplicates kubelet --disableexcludes=kubernetes
# Available Packages
# kubelet.aarch64    1.32.0-150500.1.1    kubernetes
# kubelet.aarch64    1.32.1-150500.1.1    kubernetes
# ...
# kubelet.aarch64    1.32.10-150500.1.1   kubernetes
# kubelet.aarch64    1.32.11-150500.1.1   kubernetes  <- 최신 버전

dnf list --showduplicates kubeadm --disableexcludes=kubernetes
# Available Packages
# kubeadm.aarch64    1.32.0-150500.1.1    kubernetes
# ...
# kubeadm.aarch64    1.32.11-150500.1.1   kubernetes

dnf list --showduplicates kubectl --disableexcludes=kubernetes
# Available Packages
# kubectl.aarch64    1.32.0-150500.1.1    kubernetes
# ...
# kubectl.aarch64    1.32.11-150500.1.1   kubernetes
```

> **참고**: `exclude=kubelet kubeadm kubectl` 설정이 적용되어 있어 일반 `dnf list`로는 패키지가 보이지 않는다. `--disableexcludes=kubernetes` 옵션을 사용하면 해당 저장소의 exclude 규칙을 일시적으로 무시할 수 있다. Kubernetes 1.32.x 버전이 제공되는 것을 확인할 수 있다.

<br>

## kubeadm, kubelet, kubectl 설치

```bash
# 설치 (버전 미지정 시 최신 버전 설치)
dnf install -y kubelet kubeadm kubectl --disableexcludes=kubernetes
# Installed:
#   kubeadm-1.32.11    kubectl-1.32.11    kubelet-1.32.11
#   cri-tools-1.32.0   kubernetes-cni-1.6.0

# kubelet 서비스 활성화 (실제 시작은 kubeadm init 후)
systemctl enable --now kubelet
# Created symlink '/etc/systemd/system/multi-user.target.wants/kubelet.service' 
#   → '/usr/lib/systemd/system/kubelet.service'.

# 프로세스 확인 - 아직 실행되지 않음 (kubeadm init 전까지 crashloop)
ps -ef | grep kubelet
# root   11973   10950  0 01:19 pts/1    00:00:00 grep --color=auto kubelet
```

> **참고**: kubelet은 `systemctl enable --now`로 활성화해도 아직 실행되지 않는다. `kubeadm init` 또는 `kubeadm join`이 완료되어 필요한 설정 파일이 생성되기 전까지 kubelet은 시작 직후 종료되는 crashloop 상태가 된다. 이는 정상적인 동작이다.

<br>

## 설치 확인

```bash
# kubeadm 버전 확인
which kubeadm && kubeadm version -o yaml
# /usr/bin/kubeadm
# clientVersion:
#   buildDate: "2025-12-16T18:06:36Z"
#   compiler: gc
#   gitCommit: 2195eae9e91f2e72114365d9bb9c670d0c08de12
#   gitTreeState: clean
#   gitVersion: v1.32.11
#   goVersion: go1.24.11
#   major: "1"
#   minor: "32"
#   platform: linux/arm64

# kubectl 버전 확인
which kubectl && kubectl version --client=true
# /usr/bin/kubectl
# Client Version: v1.32.11
# Kustomize Version: v5.5.0

# kubelet 버전 확인
which kubelet && kubelet --version
# /usr/bin/kubelet
# Kubernetes v1.32.11
```

<br>

## crictl 설정

`crictl`은 CRI 호환 컨테이너 런타임을 위한 CLI 도구다.

```bash
# crictl 버전 확인 (설정 파일 없으면 경고 발생)
which crictl && crictl version
# /usr/bin/crictl
# WARN[0000] Config "/etc/crictl.yaml" does not exist, trying next: "/usr/bin/crictl.yaml" 
# WARN[0000] runtime connect using default endpoints: [unix:///run/containerd/containerd.sock ...]. 
#   As the default settings are now deprecated, you should set the endpoint instead. 
# Version:  0.1.0
# RuntimeName:  containerd
# RuntimeVersion:  v2.1.5
# RuntimeApiVersion:  v1

# crictl 설정 파일 생성
cat << EOF > /etc/crictl.yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
EOF
```

<details markdown="1">
<summary>crictl info 전체 출력 (클릭하여 펼치기)</summary>

```json
{
  "cniconfig": {
    "Networks": [
      {
        "Config": {
          "CNIVersion": "0.3.1",
          "Name": "cni-loopback",
          "Plugins": [{ "Network": { "type": "loopback" } }]
        },
        "IFName": "lo"
      }
    ],
    "PluginConfDir": "/etc/cni/net.d",
    "PluginDirs": ["/opt/cni/bin"]
  },
  "config": {
    "cni": {
      "binDirs": ["/opt/cni/bin"],
      "confDir": "/etc/cni/net.d"
    },
    "containerd": {
      "defaultRuntimeName": "runc",
      "runtimes": {
        "runc": {
          "options": {
            "SystemdCgroup": true
          },
          "runtimeType": "io.containerd.runc.v2",
          "sandboxer": "podsandbox"
        }
      }
    },
    "containerdEndpoint": "/run/containerd/containerd.sock",
    "containerdRootDir": "/var/lib/containerd"
  },
  "golang": "go1.24.9",
  "lastCNILoadStatus": "cni config load failed: no network config found in /etc/cni/net.d",
  "status": {
    "conditions": [
      { "status": true, "type": "RuntimeReady" },              // containerd 런타임 정상
      { 
        "message": "Network plugin returns error: cni plugin not initialized",
        "reason": "NetworkPluginNotReady",
        "status": false,                                        // CNI 미설치 (정상)
        "type": "NetworkReady"
      },
      { "status": true, "type": "ContainerdHasNoDeprecationWarnings" }  // deprecation 경고 없음
    ]
  }
}
```

</details>

<br>

| 항목 | 값 | 의미 |
| --- | --- | --- |
| `RuntimeReady` | `true` | containerd 런타임 정상 - containerd가 CRI를 통해 정상적으로 컨테이너를 실행할 준비가 됨 |
| `NetworkReady` | `false` | CNI 미설치 (정상) - CNI 플러그인이 아직 설치되지 않음. `kubeadm init` 후 Calico 등 CNI를 설치하면 `true`가 됨 |
| `SystemdCgroup` | `true` | systemd cgroup 드라이버 사용 |
| `ContainerdHasNoDeprecationWarnings` | `true` | containerd 설정에 deprecated 옵션이 없음 |
| `containerdEndpoint` | `/run/containerd/containerd.sock` | CRI 소켓 경로 |

<br>

## CNI 바이너리 및 설정 디렉토리 확인

`kubernetes-cni` 패키지가 함께 설치되며, CNI 바이너리 파일들이 `/opt/cni/bin`에 위치한다.

```bash
# CNI 바이너리 확인
ls -al /opt/cni/bin
# total 63200
# drwxr-xr-x. 2 root root    4096 Jan 23 01:19 .
# drwxr-xr-x. 3 root root      17 Jan 23 01:19 ..
# -rwxr-xr-x. 1 root root 3239200 Dec 12  2024 bandwidth
# -rwxr-xr-x. 1 root root 3731632 Dec 12  2024 bridge
# -rwxr-xr-x. 1 root root 9123544 Dec 12  2024 dhcp
# -rwxr-xr-x. 1 root root 3379872 Dec 12  2024 dummy
# -rwxr-xr-x. 1 root root 3742888 Dec 12  2024 firewall
# -rwxr-xr-x. 1 root root 3383408 Dec 12  2024 host-device
# -rwxr-xr-x. 1 root root 2812400 Dec 12  2024 host-local
# -rwxr-xr-x. 1 root root 3380928 Dec 12  2024 ipvlan
# -rwxr-xr-x. 1 root root 2953200 Dec 12  2024 loopback
# -rwxr-xr-x. 1 root root 3448024 Dec 12  2024 macvlan
# -rwxr-xr-x. 1 root root 3312488 Dec 12  2024 portmap
# -rwxr-xr-x. 1 root root 3524072 Dec 12  2024 ptp
# ...

tree /opt/cni
# /opt/cni
# └── bin
#     ├── bandwidth
#     ├── bridge
#     ├── dhcp
#     ├── dummy
#     ├── firewall
#     ├── host-device
#     ├── host-local
#     ├── ipvlan
#     ├── loopback
#     ├── macvlan
#     ├── portmap
#     ├── ptp
#     ├── sbr
#     ├── static
#     ├── tap
#     ├── tuning
#     ├── vlan
#     └── vrf
#
# 2 directories, 20 files

# CNI 설정 디렉토리 (아직 비어 있음)
tree /etc/cni
# /etc/cni
# └── net.d
```

> CNI 바이너리(`/opt/cni/bin/`)는 `kubernetes-cni` 패키지로 설치된다. 설정 파일(`/etc/cni/net.d/`)은 비어 있으며, `kubeadm init` 후 Calico 등 CNI 플러그인을 설치하면 생성된다.

<br>

## kubelet 서비스 파일 확인

```bash
# kubelet 서비스 상태 확인
systemctl is-active kubelet
# activating    <- 계속 재시작 시도 중

systemctl status kubelet --no-pager
# ● kubelet.service - kubelet: The Kubernetes Node Agent
#      Loaded: loaded (/usr/lib/systemd/system/kubelet.service; enabled; preset: disabled)
#     Drop-In: /usr/lib/systemd/system/kubelet.service.d
#              └─10-kubeadm.conf
#      Active: activating (auto-restart) (Result: exit-code) since Fri 2026-01-23 01:26:18 KST; 9s ago
#     Process: 12363 ExecStart=/usr/bin/kubelet $KUBELET_KUBECONFIG_ARGS $KUBELET_CONFIG_ARGS 
#              $KUBELET_KUBEADM_ARGS $KUBELET_EXTRA_ARGS (code=exited, status=1/FAILURE)
#    Main PID: 12363 (code=exited, status=1/FAILURE)

journalctl -u kubelet --no-pager
# Jan 23 01:19:38 k8s-ctr systemd[1]: Started kubelet.service - kubelet: The Kubernetes Node Agent.
# Jan 23 01:19:38 k8s-ctr (kubelet)[11963]: kubelet.service: Referenced but unset environment variable 
#   evaluates to an empty string: KUBELET_KUBEADM_ARGS
# Jan 23 01:19:38 k8s-ctr kubelet[11963]: E0123 01:19:38.610461   11963 run.go:72] "command failed" 
#   err="failed to load kubelet config file, path: /var/lib/kubelet/config.yaml, 
#   error: open /var/lib/kubelet/config.yaml: no such file or directory"
# Jan 23 01:19:38 k8s-ctr systemd[1]: kubelet.service: Main process exited, code=exited, status=1/FAILURE
# Jan 23 01:19:38 k8s-ctr systemd[1]: kubelet.service: Failed with result 'exit-code'.
# Jan 23 01:19:48 k8s-ctr systemd[1]: kubelet.service: Scheduled restart job, restart counter is at 1.
# ... (계속 반복)

# kubelet 서비스 파일 확인
tree /usr/lib/systemd/system | grep kubelet -A1
# ├── kubelet.service
# ├── kubelet.service.d
# │   └── 10-kubeadm.conf

cat /usr/lib/systemd/system/kubelet.service
# [Unit]
# Description=kubelet: The Kubernetes Node Agent
# Documentation=https://kubernetes.io/docs/
# Wants=network-online.target
# After=network-online.target
#
# [Service]
# ExecStart=/usr/bin/kubelet
# Restart=always
# StartLimitInterval=0
# RestartSec=10
#
# [Install]
# WantedBy=multi-user.target

cat /usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf
# # Note: This dropin only works with kubeadm and kubelet v1.11+
# [Service]
# Environment="KUBELET_KUBECONFIG_ARGS=--bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf 
#              --kubeconfig=/etc/kubernetes/kubelet.conf"
# Environment="KUBELET_CONFIG_ARGS=--config=/var/lib/kubelet/config.yaml"
# # This is a file that "kubeadm init" and "kubeadm join" generates at runtime, 
# # populating the KUBELET_KUBEADM_ARGS variable dynamically
# EnvironmentFile=-/var/lib/kubelet/kubeadm-flags.env
# # KUBELET_EXTRA_ARGS should be sourced from this file.
# EnvironmentFile=-/etc/sysconfig/kubelet
# ExecStart=
# ExecStart=/usr/bin/kubelet $KUBELET_KUBECONFIG_ARGS $KUBELET_CONFIG_ARGS $KUBELET_KUBEADM_ARGS $KUBELET_EXTRA_ARGS
```

`10-kubeadm.conf`는 systemd drop-in 파일로, 기본 `kubelet.service`의 설정을 오버라이드한다. 여기서 참조하는 파일들:

| 파일 | 설명 | 생성 시점 |
| --- | --- | --- |
| `/etc/kubernetes/bootstrap-kubelet.conf` | 부트스트랩 kubeconfig | `kubeadm init/join` |
| `/etc/kubernetes/kubelet.conf` | kubelet kubeconfig | `kubeadm init/join` |
| `/var/lib/kubelet/config.yaml` | kubelet 설정 파일 | `kubeadm init/join` |
| `/var/lib/kubelet/kubeadm-flags.env` | kubeadm이 생성하는 플래그 | `kubeadm init/join` |
| `/etc/sysconfig/kubelet` | 사용자 정의 추가 인자 | 수동 생성 (선택) |

> 참고: **kubelet crashloop 원인**
> 
> kubelet이 계속 재시작되는 것은 **정상**이다. 로그에서 확인할 수 있듯이:
> - `KUBELET_KUBEADM_ARGS` 환경변수가 설정되지 않음
> - `/var/lib/kubelet/config.yaml` 파일이 없음
> 
> 이 파일들은 `kubeadm init` 또는 `kubeadm join` 실행 시 생성된다. 지금은 crashloop 상태가 정상이다.

<br>

## 현재 상태 확인

```bash
# kubernetes 관련 디렉토리 확인 (아직 비어 있음)
tree /etc/kubernetes
# /etc/kubernetes
# └── manifests
#
# 2 directories, 0 files

tree /var/lib/kubelet
# /var/lib/kubelet
#
# 0 directories, 0 files   <- config.yaml 등 아직 없음

# kubelet 추가 인자 설정 파일
cat /etc/sysconfig/kubelet
# KUBELET_EXTRA_ARGS=
```

cgroup 계층 구조에서 containerd가 정상적으로 실행 중인지 확인한다.

```bash
systemd-cgls --no-pager
# CGroup /:
# -.slice
# ├─user.slice
# │ └─...
# └─system.slice
#   ├─containerd.service …
#   │ └─11617 /usr/bin/containerd      <- containerd 실행 중
#   ├─chronyd.service
#   │ └─666 /usr/sbin/chronyd -F 2
#   ...

# namespace 정보 확인 (컨테이너가 없으므로 시스템 namespace만 존재)
lsns
#         NS TYPE   NPROCS   PID USER    COMMAND
# 4026531834 time      135     1 root    /usr/lib/systemd/systemd ...
# 4026531835 cgroup    135     1 root    /usr/lib/systemd/systemd ...
# 4026531836 pid       135     1 root    /usr/lib/systemd/systemd ...
# 4026531837 user      134     1 root    /usr/lib/systemd/systemd ...
# 4026531838 uts       125     1 root    /usr/lib/systemd/systemd ...
# 4026531839 ipc       135     1 root    /usr/lib/systemd/systemd ...
# 4026531840 net       133     1 root    /usr/lib/systemd/systemd ...
# 4026531841 mnt       116     1 root    /usr/lib/systemd/systemd ...
# ...

# containerd 소켓 확인
ls -l /run/containerd/containerd.sock
# srw-rw----. 1 root root 0 Jan 23 01:12 /run/containerd/containerd.sock

ss -xl | grep containerd
# u_str LISTEN 0  4096  /run/containerd/containerd.sock.ttrpc 79929  * 0   
# u_str LISTEN 0  4096  /run/containerd/containerd.sock       79930  * 0
```

현재 상태 요약:
- `/etc/kubernetes/manifests`: 비어 있음 (static pod manifest가 없음)
- `/var/lib/kubelet`: 비어 있음 (`config.yaml` 등 아직 없음)
- containerd: `system.slice`에서 정상 실행 중
- namespace: 시스템 기본 namespace만 존재 (컨테이너 미실행)
- containerd 소켓: `/run/containerd/containerd.sock` 정상 LISTEN

<br>

# 설정 전후 비교용 기본 정보 저장

`kubeadm init` 전후로 시스템 상태 변화를 비교하기 위해 현재 상태를 저장해 둔다.

```bash
# 기본 환경 정보 저장
crictl images | tee -a crictl_images-1.txt
crictl ps -a | tee -a crictl_ps-1.txt
cat /etc/sysconfig/kubelet | tee -a kubelet_config-1.txt
tree /etc/kubernetes  | tee -a etc_kubernetes-1.txt
tree /var/lib/kubelet | tee -a var_lib_kubelet-1.txt
tree /run/containerd/ -L 3 | tee -a run_containerd-1.txt
pstree -alnp | tee -a pstree-1.txt
systemd-cgls --no-pager | tee -a systemd-cgls-1.txt
lsns | tee -a lsns-1.txt
ip addr | tee -a ip_addr-1.txt 
ss -tnlp | tee -a ss-1.txt
df -hT | tee -a df-1.txt
findmnt | tee -a findmnt-1.txt
sysctl -a | tee -a sysctl-1.txt
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
| containerd | v2.1.5 설치, SystemdCgroup 활성화 |
| kubeadm | v1.32.11 설치 |
| kubelet | v1.32.11 설치, 서비스 활성화 |
| kubectl | v1.32.11 설치 |

<br>

현재 상태에서는 아직 클러스터가 구성되지 않았다:
- `/etc/kubernetes/` 디렉토리가 비어 있음
- `/var/lib/kubelet/` 디렉토리가 비어 있음
- kubelet이 재시작을 반복함 (정상)
- CNI가 설치되지 않아 NetworkReady 상태가 false

다음 글에서는 `kubeadm init`을 실행하여 컨트롤 플레인을 구성하고, Flannel CNI를 설치한다.
