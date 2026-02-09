---
title:  "[CS] VirtualBox + Vagrant 네트워크 어댑터 이해하기"
excerpt: "Vagrant + VirtualBox 환경에서 반복적으로 등장하는 NAT, Host-Only 네트워크 구조를 정리한다."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - VirtualBox
  - Vagrant
  - Network
  - NAT
  - Host-Only

---

<br>

# 들어가며

Kubernetes 클러스터 환경을 구성하는 실습을 진행하면서 VirtualBox와 Vagrant를 자주 사용하게 되었다. Multi-Node 클러스터를 로컬에서 구성하기 위해서는 여러 대의 VM이 필요하고, 이들 간의 네트워크 통신이 필수적이다. 

특히 최근 Kubespray를 이용한 온프레미스 클러스터 구성, 폐쇄망 환경 시뮬레이션 등을 실습하면서 NAT, Host-Only 네트워크 어댑터를 반복적으로 설정하게 되었다. 매번 설정할 때마다 각 네트워크 타입의 역할과 차이점을 다시 찾아보게 되어, 이참에 VirtualBox + Vagrant 네트워크 구조를 정리해두고자 한다.

<br>

# TL;DR

Vagrant + VirtualBox VM은 기본적으로 **2개의 네트워크 인터페이스(NIC)**를 가진다.

```
호스트
 ├─ [NAT] ──────── enp0s8 (10.0.2.15)    → 인터넷 O, 호스트에서 포트포워딩으로만 접속
 └─ [Host-Only] ── enp0s9 (192.168.10.x) → 인터넷 X, 호스트에서 IP로 직접 접속
```

| NIC | 어댑터 타입 | IP 예시 | 용도 |
|-----|------------|---------|------|
| NIC1 | NAT | `10.0.2.15` | Vagrant 관리 + 인터넷 접근 |
| NIC2 | Host-Only | `192.168.10.x` | VM 간 통신 + 호스트-VM 통신 |


> 참고: **인터페이스 이름**
> 
>  VirtualBox 버전, 게스트 OS, Vagrant box 이미지에 따라 NIC 이름이 달라질 수 있다. 
> `bento/rockylinux-10.0`에서는 `enp0s8`/`enp0s9`, `bento/debian-12`에서는 `eth0`/`eth1` 또는 `enp0s3`/`enp0s8`이 될 수 있다. 
> 중요한 것은 이름이 아니라 **어댑터 타입(NAT vs Host-Only)**이다.

<br>

# VirtualBox와 Vagrant

## VirtualBox

**VirtualBox**는 가상 머신(VM)을 만들고 실행하는 하이퍼바이저다. 하나의 물리 머신 위에 여러 개의 가상 머신을 올릴 수 있고, 각 VM에 CPU, 메모리, 디스크, **네트워크 어댑터** 등 가상 하드웨어를 할당한다. 이 글에서 다루는 NAT, Host-Only는 VirtualBox가 VM에 제공하는 **네트워크 어댑터의 동작 모드**다.

## Vagrant

**Vagrant**는 VirtualBox 같은 하이퍼바이저를 **코드로 제어**하는 도구다. `Vagrantfile` 하나에 VM 스펙, 네트워크, 프로비저닝을 정의해 두면 `vagrant up` 한 줄로 환경을 재현할 수 있다.

## 관계

```
Vagrantfile (코드)
    │
    ▼
  Vagrant (자동화 도구)
    │  "VirtualBox야, 이 스펙대로 VM 만들어줘"
    ▼
  VirtualBox (하이퍼바이저)
    │  VM 생성, 네트워크 어댑터 할당, 실행
    ▼
  VM (가상 머신)
```

Vagrant는 VirtualBox에 **지시를 내리는 쪽**이고, VirtualBox는 실제로 VM과 네트워크를 **만드는 쪽**이다. Vagrantfile에 `private_network`라고 쓰면 Vagrant가 VirtualBox API를 호출해서 Host-Only 어댑터를 생성한다. `forwarded_port`라고 쓰면 VirtualBox의 NAT 포트포워딩을 설정한다.

<br>

# NAT 어댑터

## NAT란

**NAT(Network Address Translation)**은 사설 IP 주소를 공인 IP 주소로 변환하는 기술이다. 집에서 공유기를 사용하는 것을 생각하면 된다. 공유기 뒤에 있는 여러 기기(192.168.0.x)는 외부에서 직접 접근할 수 없지만, 공유기가 주소를 변환해주어 인터넷을 사용할 수 있다.

```
[사설 IP: 192.168.0.10] → [공유기 (NAT)] → [공인 IP: 203.0.113.1] → 인터넷
```

핵심은 두 가지다:

- **안에서 밖으로**: 사설 IP를 가진 기기가 패킷을 보내면, 공유기가 출발지 주소를 자신의 공인 IP로 바꿔서 인터넷으로 내보낸다. 응답이 돌아오면 다시 사설 IP로 변환해서 기기에 전달한다. 덕분에 사설 IP 기기도 인터넷에 접근할 수 있다
- **밖에서 안으로**: 외부에서는 공유기 뒤에 어떤 기기가 있는지 알 수 없다. 사설 IP로 직접 접근할 수 없고, 포트포워딩을 설정해야만 접근할 수 있다

<br>

## VirtualBox에서 NAT이 필요한 이유

VirtualBox VM은 호스트 안에서 동작하는 가상 머신이다. VM이 인터넷에 접근하려면 호스트의 네트워크를 거쳐야 하는데, VM에 호스트 네트워크의 IP를 직접 할당하면 여러 문제가 생긴다 — IP 충돌, 네트워크 관리 복잡성, 보안 등. 그래서 VirtualBox는 **가상 NAT 장치**를 제공한다. 마치 VM 전용 미니 공유기를 하나 달아주는 것이다.

원리도 공유기와 같다:

- **VM(안) → 인터넷(밖)**: VM이 `10.0.2.15`로 패킷을 보내면, VirtualBox NAT이 호스트의 IP로 변환해서 인터넷으로 내보낸다. `dnf install`, `curl` 등이 동작하는 이유다
- **인터넷(밖) → VM(안)**: 외부에서는 VM의 `10.0.2.15`에 직접 접근할 수 없다. 호스트에서조차 안 된다. 접근하려면 **포트포워딩**이 필요하다 (공유기에서 특정 포트를 열어주는 것과 같다)

이 방식의 장점은 아래와 같다:

- VM이 **호스트 네트워크 설정에 영향을 주지 않으면서** 인터넷 사용 가능
- VM 네트워크가 **호스트 네트워크와 격리**되어 안전
- 별도의 네트워크 설정 없이 **즉시 동작** (기본 어댑터)

## NAT 어댑터의 구조

VirtualBox의 NAT 어댑터는 VM마다 독립된 가상 NAT 환경을 만든다.

```
┌────────────────────────────────────┐
│  VirtualBox NAT Network            │
│                                    │
│  VM ──► 10.0.2.15                  │
│           │                        │
│           ▼                        │
│       10.0.2.2 (Virtual Gateway)   │
│           │                        │
│           ▼                        │
│       Host Network → Internet      │
└────────────────────────────────────┘
```

NAT 네트워크의 IP 체계는 VirtualBox에서 고정되어 있다.

| IP | 역할 |
|----|------|
| `10.0.2.2` | 가상 게이트웨이 |
| `10.0.2.3` | 가상 DNS 프록시 ([NAT DNS Proxy](https://www.virtualbox.org/manual/ch09.html#nat-adv-dns) 활성화 시) |
| `10.0.2.15` | VM에 할당되는 IP |

<br>

이 값들은 **OS, Vagrant box, VirtualBox 버전과 무관하게 모든 NAT 모드 VM에서 동일**하다. VM 3개를 띄우면 3개 모두 `10.0.2.15`를 가진다. 그럼에도 각 VM은 **독립된 NAT 환경**에 있으므로 **충돌하지 않는다**.

<br>

**핵심은 각 VM이 독립된 NAT 환경에 있다는 점이다.** `10.0.2.15`는 **호스트 네트워크에 존재하는 IP가 아니다**. VirtualBox NAT 모드에서는 VM마다 **독립된 가상 NAT 장치**가 붙는다. VM들이 하나의 네트워크를 공유하는 게 아니라, 각 VM이 **자기만의 미니 공유기**를 갖는 구조다.

```
호스트 (실제 네트워크: 172.30.1.x)
 │
 ├── [VM1 전용 NAT 장치] ── VM1 (10.0.2.15)
 ├── [VM2 전용 NAT 장치] ── VM2 (10.0.2.15)
 └── [VM3 전용 NAT 장치] ── VM3 (10.0.2.15)
      ↑ 각각 독립된 가상 네트워크. 서로 보이지 않음
```

`10.0.2.x` 대역은 호스트 OS의 네트워크 스택에 등록되지 않는다. 호스트에서 `ifconfig`나 `ip addr`을 해도 이 대역은 나타나지 않는다. VM이 `10.0.2.2`(게이트웨이)로 보내는 패킷은 호스트의 네트워크 인터페이스에 도달하기 전에 **VirtualBox의 NAT 엔진이 하이퍼바이저 레벨에서 가로채서, 출발지 IP를 호스트의 실제 IP로 변환(NAT)한 뒤 호스트의 네트워크로 내보낸다**. 

집집마다 공유기 내부 네트워크가 모두 `192.168.0.0/24`이지만 서로 충돌하지 않는 것과 같은 원리다. 같은 이유로, 호스트가 `10.0.2.0/24` 대역이어도 문제없다.

## DNS

NAT 모드에서 DNS는 기본적으로 **호스트의 DNS 설정이 DHCP를 통해 VM에 그대로 전달**된다. 따라서 VM의 `/etc/resolv.conf`에는 `10.0.2.3`이 아니라 호스트가 사용 중인 실제 DNS 서버가 나온다. `10.0.2.3`은 NAT DNS Proxy를 명시적으로 활성화했을 때만 사용되는 주소다.

## Vagrant에서의 포트포워딩

Vagrant는 NAT 인터페이스를 **VM 관리 전용**으로 사용한다. `vagrant up`(프로비저닝), `vagrant ssh`(접속) 모두 이 인터페이스를 통한다.

NAT이므로 호스트에서 VM에 직접 접근할 수 없고, **포트포워딩**으로 우회한다:

```ruby
# Vagrantfile
subconfig.vm.network "forwarded_port", guest: 22, host: "60001"
```

VirtualBox가 호스트의 60001번 포트를 열어두고, 그 포트로 들어오는 트래픽을 VM의 22번 포트로 전달한다.

```
vagrant ssh week06-node1
  = ssh -p 60001 vagrant@127.0.0.1
  = 호스트 localhost:60001 → VirtualBox NAT 변환 → VM enp0s8:22
```

NAT IP(`10.0.2.15`)는 VirtualBox 내부에서만 의미 있는 주소이므로, 호스트에서 `ssh root@10.0.2.15`는 **동작하지 않는다**.

<br>

# Host-Only 어댑터

## 구조

Host-Only 어댑터는 호스트와 VM 사이에 만든 **사설 네트워크**다. 이름 그대로 호스트(Host)와 VM만(Only) 통신할 수 있다.

```
              ┌─ admin     (192.168.10.10)
맥 (Host) ────┼─ k8s-node1 (192.168.10.11)
192.168.10.1  └─ k8s-node2 (192.168.10.12)
                 ↑ 이 네트워크는 외부 인터넷과 연결되지 않음
```

- VirtualBox가 호스트에 **가상 네트워크 인터페이스**(macOS에서는 `bridge100` 또는 `vboxnet0`)를 생성한다
- 호스트와 VM들이 같은 `192.168.10.0/24` 대역으로 직접 통신할 수 있다
- 이 네트워크를 통해서는 **인터넷으로 나갈 수 없다**
- 호스트에서 `ssh root@192.168.10.11`로 **직접 접속할 수 있다**

NAT과 달리, Host-Only 네트워크는 호스트 OS의 네트워크 스택에 **실제 인터페이스가 등록**된다. VM들이 하나의 서브넷을 공유하므로, **각 VM에 고유한 IP를 지정해야 한다**.

## Vagrant에서의 설정

```ruby
# Vagrantfile
subconfig.vm.network "private_network", ip: "192.168.10.11"
```

`private_network`이 VirtualBox의 Host-Only 네트워크를 만들고, `ip:`로 고정 IP를 지정한다.

## never-default 설정

Host-Only NIC에는 **`never-default=true`** 설정이 필요하다. 이 설정이 없으면 Host-Only NIC도 default route를 생성하려 하면서 NAT NIC과 라우팅 충돌이 발생할 수 있다.

```bash
# 프로비저닝 스크립트에서 설정
nmcli connection modify enp0s9 ipv4.never-default yes
nmcli connection up enp0s9
```

<br>

# 접속 방식 정리

| 접속 방식 | 명령어 | 경유 NIC | 계정 | 원리 |
|----------|--------|---------|------|------|
| `vagrant ssh` | `ssh -p 60001 vagrant@127.0.0.1` | NAT (포트포워딩) | vagrant | Vagrant가 자동으로 SSH 키 세팅 |
| 직접 SSH | `ssh root@192.168.10.11` | Host-Only | root | 프로비저닝에서 root 로그인 허용 + 비밀번호 설정 |

<br>

# 실제 확인

개념만으로는 와닿지 않을 수 있다. VM 안팎에서 실제로 확인해 보자.

## vagrant up 로그

VM 생성 시 어댑터 할당과 포트포워딩 설정을 볼 수 있다:

```
==> test: Preparing network interfaces based on configuration...
    test: Adapter 1: nat              ← NAT 어댑터 (NIC1)
==> test: Forwarding ports...
    test: 22 (guest) => 2222 (host) (adapter 1)
```

`private_network`을 설정한 경우 두 번째 어댑터도 나타난다:

```
    test: Adapter 1: nat
    test: Adapter 2: hostonly         ← Host-Only 어댑터 (NIC2)
```

## VM 내부: ip route

```bash
root@admin:~# ip route
default via 10.0.2.2 dev enp0s8 proto dhcp src 10.0.2.15 metric 100
10.0.2.0/24 dev enp0s8 proto kernel scope link src 10.0.2.15 metric 100
192.168.10.0/24 dev enp0s9 proto kernel scope link src 192.168.10.10 metric 101
```

| 항목 | NIC | 의미 |
|------|-----|------|
| `default via 10.0.2.2` | enp0s8 (NAT) | 인터넷으로 나가는 기본 경로. `10.0.2.2`가 NAT 게이트웨이 |
| `10.0.2.0/24` | enp0s8 (NAT) | NAT 네트워크 대역 |
| `192.168.10.0/24` | enp0s9 (Host-Only) | 내부 통신 네트워크 |

`metric` 값이 낮을수록 우선순위가 높다. NAT(100)이 Host-Only(101)보다 우선이므로, 인터넷 트래픽은 NAT을 통해 나간다.

## VM 내부: ifconfig

```bash
root@admin:~# ifconfig
enp0s8: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.0.2.15  netmask 255.255.255.0  broadcast 10.0.2.255
        ether 08:00:27:90:ea:eb  ...

enp0s9: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.10.10  netmask 255.255.255.0  broadcast 192.168.10.255
        ether 08:00:27:3d:1a:94  ...
```

`enp0s8`이 NAT(`10.0.2.15`), `enp0s9`이 Host-Only(`192.168.10.10`)임을 확인할 수 있다.

## VM 내부: DNS

프로비저닝이 없는 빈 VM에서 확인하면 호스트의 DNS가 그대로 전달된 것을 볼 수 있다:

```bash
vagrant@localhost:~$ cat /etc/resolv.conf
# Generated by NetworkManager
nameserver 168.126.63.1
nameserver 168.126.63.2
```

`168.126.63.1`, `168.126.63.2`는 KT DNS다. 호스트가 KT 네트워크를 사용하고 있으므로, VirtualBox NAT의 DHCP가 이 DNS 설정을 그대로 전달한 것이다.

## vagrant ssh 로그인 메시지

`vagrant ssh`로 접속하면, VM 입장에서는 접속 출발지가 NAT 게이트웨이(`10.0.2.2`)로 보인다:

```
Last login: Mon Feb  9 21:40:46 2026 from 10.0.2.2
```

NAT 포트포워딩을 통해 들어오기 때문이다.

## 호스트: 가상 인터페이스

호스트에서도 VirtualBox가 만든 Host-Only 가상 인터페이스를 확인할 수 있다:

```bash
# macOS
ifconfig | grep -A 3 "bridge100\|vboxnet"

bridge100: flags=8a63<UP,BROADCAST,SMART,RUNNING,ALLMULTI,SIMPLEX,MULTICAST>
    inet 192.168.10.1 netmask 0xffffff00 broadcast 192.168.10.255
```

`192.168.10.1`이 호스트의 Host-Only IP다. 이 인터페이스 덕분에 호스트와 VM이 같은 서브넷에 있게 된다.

## VM 내부: NIC 설정 파일

Rocky Linux 10 등 최신 RHEL 계열에서는 `/etc/NetworkManager/system-connections/` 아래의 `.nmconnection` 파일로 NIC이 설정된다.

```ini
# NAT NIC: /etc/NetworkManager/system-connections/enp0s8.nmconnection
[ipv4]
method=auto          # DHCP로 IP 자동 할당

# Host-Only NIC: /etc/NetworkManager/system-connections/enp0s9.nmconnection
[ipv4]
address1=192.168.10.10/24
method=manual        # 고정 IP
never-default=true   # default route를 생성하지 않음
```

<br>

# NAT IP 문제: 왜 자꾸 10.0.2.15가 문제를 일으키는가

Vagrant + VirtualBox 환경에서 Kubernetes를 구성할 때 **가장 빈번하게 마주치는 문제**다.

## 문제 상황

모든 VM이 NAT 인터페이스에서 동일한 `10.0.2.15`를 가진다. Kubernetes 컴포넌트(kubelet, API Server 등)나 Kubespray 같은 자동화 도구가 이 IP를 자동 감지해서 사용하면:

- API Server가 `10.0.2.15:6443`에서 리스닝 → Worker 노드가 접속 시도 → **자기 자신의 10.0.2.15에 접속**하게 됨
- kubelet이 `10.0.2.15`를 Node IP로 등록 → 모든 노드가 같은 IP → **Pod 간 통신 불가**

```
Worker 노드 → kubeadm join → https://10.0.2.15:6443 
                               ↑ 이건 Worker 자기 자신의 NAT IP!
                               ↓ connection refused
```

## 해결: 항상 Host-Only IP를 명시

### kubeadm

```bash
kubeadm init --apiserver-advertise-address=192.168.10.100
```

kubelet에도 `--node-ip` 설정이 필요하다.

### Kubespray

인벤토리에 `ip` 변수를 **반드시** 명시한다:

```ini
[all]
controller-0 ansible_host=192.168.10.100 ip=192.168.10.100
worker-0     ansible_host=192.168.10.101 ip=192.168.10.101
```

### Flannel CNI

Flannel도 올바른 인터페이스를 지정해야 한다:

```yaml
flannel_interface: enp0s9
```

## 기억할 것

**Vagrant + VirtualBox 환경에서는 항상 Host-Only IP를 명시적으로 지정해야 한다.** 자동 감지에 맡기면 NAT IP(`10.0.2.15`)가 선택되어 노드 간 통신이 실패한다.

<br>

# 전체 구조 요약

```
![VirtualBox Network Architecture](/assets/images/virtualbox-network-diagram.png)
```

<br>

# 참고 자료

- [VirtualBox - Networking](https://www.virtualbox.org/manual/ch06.html)
- [VirtualBox - NAT DNS](https://www.virtualbox.org/manual/ch09.html#nat-adv-dns)
- [Vagrant - Networking](https://developer.hashicorp.com/vagrant/docs/networking)
- [Vagrant - VirtualBox Provider](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox/networking)

<br>
